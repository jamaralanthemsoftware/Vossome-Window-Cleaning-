import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

// Do not pass application credentials to the browser or its startup diagnostics.
const browserEnvironment = () => Object.fromEntries(
  ["PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LD_LIBRARY_PATH",
    "FONTCONFIG_FILE", "FONTCONFIG_PATH", "XDG_RUNTIME_DIR", "XDG_CACHE_HOME"]
    .filter((key) => process.env[key] !== undefined)
    .map((key) => [key, process.env[key]]),
);

export async function launchChromium(executable, { timeoutMs = 30_000 } = {}) {
  const profile = await mkdtemp(join(tmpdir(), "vossome-responsive-"));
  const args = [
    "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run",
    "--disable-dev-shm-usage", "--no-default-browser-check",
    "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
    `--user-data-dir=${profile}`, "about:blank",
  ];
  const browser = spawn(executable, args, {
    env: browserEnvironment(), stdio: ["ignore", "ignore", "pipe"],
  });
  let stderr = "";
  let launchError;
  let closed = false;
  const onClose = new Promise((resolve) => browser.once("close", () => {
    closed = true;
    resolve();
  }));
  browser.once("error", (error) => { launchError = error; });
  browser.stderr.on("data", (chunk) => { stderr = (stderr + chunk).slice(-8192); });

  const stop = async () => {
    if (!closed) {
      browser.kill("SIGTERM");
      const forceKill = setTimeout(() => browser.kill("SIGKILL"), 2000);
      try {
        await onClose;
      } finally {
        clearTimeout(forceKill);
      }
    }
    // Chrome helpers may finish touching the profile just after the parent closes.
    await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  };

  const started = Date.now();
  let lastProbe = "DevToolsActivePort has not been written";
  try {
    while (Date.now() - started < timeoutMs) {
      if (launchError) throw new Error(`Chromium could not start: ${launchError.message}`);
      if (closed || browser.exitCode !== null || browser.signalCode !== null) {
        throw new Error(`Chromium exited (code=${browser.exitCode}, signal=${browser.signalCode})`);
      }
      try {
        const text = await readFile(join(profile, "DevToolsActivePort"), "utf8");
        const port = Number(text.split("\n")[0]);
        if (!Number.isInteger(port) || port < 1 || port > 65535) {
          throw new Error("DevToolsActivePort contains an invalid port");
        }
        const response = await fetch(`http://127.0.0.1:${port}/json/version`, {
          signal: AbortSignal.timeout(Math.max(1, Math.min(1000, timeoutMs - (Date.now() - started)))),
        });
        if (!response.ok) throw new Error(`DevTools returned HTTP ${response.status}`);
        const version = await response.json();
        if (!version.webSocketDebuggerUrl) throw new Error("DevTools is not ready");
        console.log(`Chromium ready: ${version.Browser ?? "unknown version"} (${Date.now() - started}ms)`);
        return { browser, port, stop };
      } catch (error) {
        lastProbe = error.code === "ENOENT" ? "DevToolsActivePort has not been written" : error.message;
      }
      await delay(100);
    }
    throw new Error(`Chromium startup timed out after ${timeoutMs}ms: ${lastProbe}`);
  } catch (error) {
    try {
      await stop();
    } catch (cleanupError) {
      error.message += `\nChromium cleanup failed: ${cleanupError.message}`;
    }
    throw new Error(`${error.message}\nExecutable: ${executable}\nFlags: ${args.join(" ")}\n` +
      `Chromium stderr (last 8 KiB):\n${stderr.trim() || "(no stderr output)"}`);
  }
}
