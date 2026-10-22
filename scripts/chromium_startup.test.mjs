import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { launchChromium } from "./chromium_startup.mjs";

async function fakeBrowser(t, body) {
  const dir = await mkdtemp(join(tmpdir(), "vossome-startup-test-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const executable = join(dir, "browser");
  const record = join(dir, "launch.json");
  await writeFile(executable, `#!${process.execPath}
const fs = require("node:fs");
const profile = process.argv.find(arg => arg.startsWith("--user-data-dir=")).split("=")[1];
fs.writeFileSync(${JSON.stringify(record)}, JSON.stringify({profile, pid: process.pid, args: process.argv}));
${body}
`, { mode: 0o700 });
  return {
    executable,
    record: async () => JSON.parse(await readFile(record, "utf8")),
  };
}

async function assertCleaned(record) {
  await assert.rejects(readFile(join(record.profile, "DevToolsActivePort")), { code: "ENOENT" });
  await assert.rejects(readFile(record.profile), { code: "ENOENT" });
  assert.throws(() => process.kill(record.pid, 0), { code: "ESRCH" });
}

test("missing executable reports spawn error instead of waiting or crashing", async () => {
  await assert.rejects(launchChromium("/nonexistent/vossome-chromium"), /could not start:.*ENOENT/s);
});

test("early exit preserves useful stderr and exit status", async (t) => {
  const fake = await fakeBrowser(t, 'console.error("missing shared library: libExample.so"); process.exit(23);');
  await assert.rejects(launchChromium(fake.executable), /code=23.*libExample\.so/s);
  await assertCleaned(await fake.record());
});

test("signal exit is reported without waiting for the startup timeout", async (t) => {
  const fake = await fakeBrowser(t, 'process.kill(process.pid, "SIGTERM");');
  await assert.rejects(launchChromium(fake.executable), /signal=SIGTERM/);
  await assertCleaned(await fake.record());
});

test("stalled startup fails with bounded stderr, kills an uncooperative child and removes profile", async (t) => {
  const fake = await fakeBrowser(t, `
process.on("SIGTERM", () => {});
console.error("x".repeat(20000) + " startup stalled");
setInterval(() => {}, 1000);`);
  await assert.rejects(launchChromium(fake.executable, { timeoutMs: 500 }), (error) => {
    assert.match(error.message, /startup timed out.*DevToolsActivePort.*startup stalled/s);
    assert.ok(error.message.length < 10000);
    return true;
  });
  await assertCleaned(await fake.record());
});

test("invalid debugging port is not mistaken for a ready browser", async (t) => {
  const fake = await fakeBrowser(t, `
fs.writeFileSync(profile + "/DevToolsActivePort", "not-a-port");
setInterval(() => {}, 1000);`);
  await assert.rejects(launchChromium(fake.executable, { timeoutMs: 500 }), /invalid port/);
  await assertCleaned(await fake.record());
});

test("allows startup beyond the old six-second limit and keeps credentials out of the child", async (t) => {
  const key = "VOSSOME_STARTUP_TEST_SECRET";
  process.env[key] = "must-not-reach-browser";
  t.after(() => { delete process.env[key]; });
  const fake = await fakeBrowser(t, `
if (process.env.${key}) { console.error("credential inherited"); process.exit(9); }
const server = require("node:http").createServer((req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify({Browser: "fake Chromium", webSocketDebuggerUrl: "ws://127.0.0.1/fake"}));
});
setTimeout(() => server.listen(0, "127.0.0.1", () => {
  fs.writeFileSync(profile + "/DevToolsActivePort", String(server.address().port));
}), 6500);`);
  const session = await launchChromium(fake.executable, { timeoutMs: 10_000 });
  try {
    assert.ok(session.port > 0);
    const record = await fake.record();
    assert.ok(record.args.includes("--disable-dev-shm-usage"));
    assert.ok(record.args.includes("--remote-debugging-address=127.0.0.1"));
  } finally {
    await session.stop();
  }
  await assertCleaned(await fake.record());
});
