// Launch Chromium through a Singapore mobile line, check the exit IP, rotate, check again.
// Standalone: needs only Playwright.
//
//   npm install playwright && npx playwright install chromium
//   export SMP_PROXY="host:port:user:pass"          # HTTP line from your dashboard
//   export SMP_ROTATE_URL="https://.../rotate/..."  # rotation link from your dashboard
//   node playwright_rotate.mjs
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const IP_INFO_URL = process.env.SMP_IP_INFO_URL || "https://ipinfo.io/json";

// Accepts the dashboard format host:port:user:pass, or http://user:pass@host:port.
export function parseProxy(line) {
  if (!line) throw new Error("set SMP_PROXY to the HTTP line from your dashboard (host:port:user:pass)");
  if (line.includes("://")) {
    const u = new URL(line);
    return { server: `http://${u.hostname}:${u.port}`, username: decodeURIComponent(u.username),
             password: decodeURIComponent(u.password) };
  }
  const [host, port, ...rest] = line.trim().split(":");
  const [username = "", ...pw] = rest;
  return { server: `http://${host}:${port}`, username, password: pw.join(":") }; // the password may contain ':'
}

// A fresh context per check: an old one can keep a connection open to the pre-rotation IP.
async function exitIp(browser) {
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await page.goto(IP_INFO_URL, { timeout: 30_000 });
    return JSON.parse(await page.innerText("body"));
  } finally {
    await context.close();
  }
}

async function rotate() {
  const res = await fetch(process.env.SMP_ROTATE_URL, { signal: AbortSignal.timeout(45_000) });
  if (res.status === 429) {
    throw new Error(`line is cooling down, try again in ${res.headers.get("retry-after")}s`);
  }
  if (!res.ok) throw new Error(`rotation failed: HTTP ${res.status} ${await res.text()}`);
}

async function main() {
  const browser = await chromium.launch({ proxy: parseProxy(process.env.SMP_PROXY) });
  try {
    const before = await exitIp(browser);
    console.log("before:", before.ip, before.country, before.org);

    await rotate();
    let after;
    for (let i = 0; i < 30 && !after; i++) {
      try {
        after = await exitIp(browser);
      } catch {
        await new Promise((r) => setTimeout(r, 3000)); // modem still redialling
      }
    }
    if (!after) throw new Error("the proxy did not come back within 90s");
    console.log("after: ", after.ip, after.country, after.org);
    if (after.ip === before.ip) console.log("the carrier handed back the same IP; rotate again after the cooldown");
  } finally {
    await browser.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((e) => { console.error(e.message); process.exit(1); });
}
