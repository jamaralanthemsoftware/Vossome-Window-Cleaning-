// Run against a seeded Django preview: WINDOW_CHECK_URL=https://.../services/window-cleaning/ node scripts/check_window_responsive.mjs
// Other service URLs are resolved relative to the Window Cleaning URL.
// Requires Node 22+ and Chromium (set CHROMIUM_PATH if it is not on PATH).
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const windowUrl = process.env.WINDOW_CHECK_URL ?? "http://localhost:8000/services/window-cleaning/";
const widths = [320, 375, 390, 768, 1440];
const services = [
  { name: "Window Cleaning", url: windowUrl, selector: ".window-hero", inspect: "window" },
  ...["pressure-washing", "gutter-cleaning", "concrete-patio-cleaning"].map((slug) => ({
    name: slug, url: new URL(`../${slug}/`, windowUrl).href,
    selector: `.service-hero--${slug}`, inspect: "service",
  })),
];
const chromium = process.env.CHROMIUM_PATH ?? "chromium";
const profile = await mkdtemp(join(tmpdir(), "vossome-responsive-"));
let browser;
let socket;

async function debuggerPort() {
  for (let attempt = 0; attempt < 60; attempt++) {
    if (browser.exitCode !== null) throw new Error(`Chromium exited with code ${browser.exitCode}`);
    try {
      return Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]);
    } catch {
      await delay(100);
    }
  }
  throw new Error("Chromium did not open its debugging port");
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.addEventListener("open", () => resolve(ws), { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
}

const pending = new Map();
let nextId = 0;
function send(method, params = {}) {
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const result = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function waitForPage(service) {
  for (let attempt = 0; attempt < 80; attempt++) {
    if (await evaluate(`document.readyState === "complete" && !!document.querySelector(${JSON.stringify(service.selector)})`)) {
      await evaluate("document.fonts.ready");
      return;
    }
    await delay(100);
  }
  throw new Error(`${service.name} page did not load at ${service.url} (check the URL and seeded CMS data)`);
}

// Read the actual rendered CMS sections rather than assuming fixed chapter numbers or copy.
const inspect = `(() => {
  const errors = [];
  const width = document.documentElement.clientWidth;
  const required = (selector, label) => {
    const element = document.querySelector(selector);
    if (!element) errors.push("Missing " + label + " (" + selector + ")");
    return element;
  };
  const hero = required(".window-hero", "hero");
  const title = required(".window-hero h1", "hero title");
  const visual = required(".window-hero-visual img", "hero image");
  const pricing = required(".window-section.window-pricing", "pricing section");
  const cards = [...document.querySelectorAll(".window-pricing-grid > div")];
  if (cards.length < 2) errors.push("Expected at least two pricing cards");
  const sections = [...document.querySelectorAll("article.window-content > .window-section")];
  const pricingIndex = sections.indexOf(pricing);
  if (pricingIndex < 1 || pricingIndex >= sections.length - 1) {
    errors.push("Expected CMS chapters both before and after pricing");
  }
  const later = sections.slice(pricingIndex + 1);
  const cta = required("article.window-content > .window-section:last-child .window-final-action", "final CTA");
  if (visual && (!visual.complete || !visual.naturalWidth)) errors.push("Hero image did not load");

  const regions = [["hero", hero], ["hero title", title], ["hero image", visual],
    ["pricing", pricing], ...cards.map((card, index) => ["pricing card " + (index + 1), card]),
    ...later.map((section, index) => ["later CMS chapter " + (index + 1), section]),
    ["final CTA", cta]];
  if (document.documentElement.scrollWidth > width + 2)
    errors.push("Page scrollWidth " + document.documentElement.scrollWidth + " exceeds viewport " + width);
  for (const [label, element] of regions) {
    if (!element) continue;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height || rect.right < 0 || rect.left > width)
      errors.push(label + " is empty or off-screen");
    if (rect.left < -2 || rect.right > width + 2)
      errors.push(label + " extends past viewport: [" + Math.round(rect.left) + ", " + Math.round(rect.right) + "]");
    for (const text of element.querySelectorAll("h1,h2,h3,p,a.button")) {
      const box = text.getBoundingClientRect();
      // Tight heading line-height can make scrollHeight exceed clientHeight even
      // when no ancestor clips the glyphs; only assert horizontal overflow here.
      if (box.left < -2 || box.right > width + 2 || text.scrollWidth > text.clientWidth + 2) {
        errors.push(label + " text clipped: " + text.tagName.toLowerCase() + " " +
          text.textContent.trim().slice(0, 55) + " (box " + Math.round(box.left) + ".." +
          Math.round(box.right) + ", scroll/client " + text.scrollWidth + "/" + text.clientWidth + ")");
      }
    }
  }
  return errors;
})()`;

// The non-window service pages use the shared service-hero/service-detail branch.
// Inspect rendered content, including descendants hidden by an overflow-clipped hero.
const inspectService = `(() => {
  const errors = [];
  const width = document.documentElement.clientWidth;
  const required = (selector, label) => {
    const element = document.querySelector(selector);
    if (!element) errors.push("Missing " + label + " (" + selector + ")");
    return element;
  };
  const hero = required(".service-hero", "hero");
  const image = required(".service-hero > img", "hero image");
  const title = required(".service-hero-content h1", "hero title");
  const summary = required(".service-hero-content .lead", "hero summary");
  const body = required(".service-detail .service-copy", "service copy");
  const cta = required(".service-detail .service-cta", "final CTA");
  const ctaTitle = required(".service-cta h2", "final CTA heading");
  const heroActions = [...document.querySelectorAll(".service-hero .hero-actions a.button")];
  const ctaActions = [...document.querySelectorAll(".service-cta a.button")];
  if (heroActions.length < 2) errors.push("Expected call and text hero actions");
  if (ctaActions.length < 2) errors.push("Expected call and text final CTA actions");
  if (image && (!image.complete || !image.naturalWidth)) errors.push("Hero image did not load");
  for (const [label, element] of [["hero title", title], ["hero summary", summary], ["service copy", body], ["final CTA heading", ctaTitle]]) {
    if (element && !element.textContent.trim()) errors.push(label + " has no content");
  }
  const regions = [["hero", hero], ["hero title", title], ["hero summary", summary],
    ...heroActions.map((action, index) => ["hero action " + (index + 1), action]),
    ["service copy", body], ["final CTA", cta],
    ...ctaActions.map((action, index) => ["final CTA action " + (index + 1), action])];
  if (document.documentElement.scrollWidth > width + 2)
    errors.push("Page scrollWidth " + document.documentElement.scrollWidth + " exceeds viewport " + width);
  for (const [label, element] of regions) {
    if (!element) continue;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height || rect.right < 0 || rect.left > width)
      errors.push(label + " is empty or off-screen");
    if (rect.left < -2 || rect.right > width + 2)
      errors.push(label + " extends past viewport: [" + Math.round(rect.left) + ", " + Math.round(rect.right) + "]");
    for (const text of element.querySelectorAll("h1,h2,h3,p,a.button")) {
      const box = text.getBoundingClientRect();
      if (box.left < -2 || box.right > width + 2 || text.scrollWidth > text.clientWidth + 2)
        errors.push(label + " text clipped: " + text.tagName.toLowerCase() + " " +
          text.textContent.trim().slice(0, 55) + " (box " + Math.round(box.left) + ".." +
          Math.round(box.right) + ", scroll/client " + text.scrollWidth + "/" + text.clientWidth + ")");
    }
  }
  return errors;
})()`;

try {
  for (const service of services) {
    const response = await fetch(service.url);
    if (!response.ok) throw new Error(`${service.url} returned HTTP ${response.status}; fix the preview before checking layout`);
  }
  if (spawnSync(chromium, ["--version"], { stdio: "ignore" }).status !== 0) {
    throw new Error(`Chromium not found (${chromium}); set CHROMIUM_PATH to its executable`);
  }
  browser = spawn(chromium, [
    "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run",
    "--remote-allow-origins=*", "--remote-debugging-port=0",
    `--user-data-dir=${profile}`, "about:blank",
  ], { stdio: "ignore" });
  const port = await debuggerPort();
  const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  socket = await connect(pages.find((target) => target.type === "page").webSocketDebuggerUrl);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id) return;
    const request = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) request.reject(new Error(message.error.message));
    else request.resolve(message.result);
  });
  await send("Page.enable");
  await send("Runtime.enable");
  for (const service of services) {
    for (const width of widths) {
      await send("Emulation.setDeviceMetricsOverride", {
        width, height: 900, deviceScaleFactor: 1, mobile: width < 768,
      });
      await send("Page.navigate", { url: service.url });
      await waitForPage(service);
      const errors = await evaluate(service.inspect === "window" ? inspect : inspectService);
      if (errors.length) throw new Error(`${service.name} (${service.url}) at ${width}px:\n  ${errors.join("\n  ")}`);
      console.log(`PASS ${service.name} ${width}px: ${service.inspect === "window" ? "hero, pricing cards, later CMS chapters, final CTA" : "hero, service copy, final CTA"}`);
    }
  }
} catch (error) {
  console.error(`FAIL responsive service check: ${error.message}`);
  process.exitCode = 1;
} finally {
  socket?.close();
  if (browser && browser.exitCode === null) {
    browser.kill();
    await new Promise((resolve) => browser.once("exit", resolve));
  }
  await rm(profile, { recursive: true, force: true });
}