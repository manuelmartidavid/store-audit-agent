// Runs Lighthouse against the browser Python already launched (spec §7).
//
//   node lighthouse_runner.mjs <port> <targets.json> <out.json>
//
// targets.json: [{ "template": "pdp", "url": "https://…" }, …]
// out.json:     [{ "template", "url", "ok", "lhr"?, "error"? }, …]
//
// One template failing is recorded and the run carries on.
//
// Invariant: use the Node API, not the Lighthouse CLI. The CLI can't carry the
// storefront-gate session and would audit the password page six times.

import fs from "node:fs";
import lighthouse from "lighthouse";

// The mobile-4g-slow profile, spelled out rather than left to Lighthouse's
// defaults so a change on their side shows up as a version bump, not drift.
const CONFIG = {
  extends: "lighthouse:default",
  settings: {
    formFactor: "mobile",
    throttlingMethod: "simulate",
    throttling: {
      rttMs: 150,
      throughputKbps: 1638.4,
      requestLatencyMs: 150 * 3.75,
      downloadThroughputKbps: 1638.4 * 0.9,
      uploadThroughputKbps: 750 * 0.9,
      cpuSlowdownMultiplier: 4,
    },
    screenEmulation: {
      mobile: true,
      width: 412,
      height: 823,
      deviceScaleFactor: 1.75,
      disabled: false,
    },
  },
};

const [, , portArg, targetsPath, outPath] = process.argv;
const port = Number(portArg);
const targets = JSON.parse(fs.readFileSync(targetsPath, "utf8"));
const results = [];

// Invariant: keep disableStorageReset on. Lighthouse audits in the browser's
// default context, where the crawler mirrored the gate cookie — clearing
// storage between templates would drop it and audit the password page instead.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const GAP_MS = 2000; // be polite between full page loads
const RETRY_MS = 5000; // give a throttled store time to recover before retrying

// Audit one target, retrying once. Returns { ok: true, lhr } or { ok: false, error }.
//
// Invariant: Lighthouse doesn't throw when a page fails to load — it returns a
// result carrying a `runtimeError` and null metrics. Treat that as a failure,
// or a template gets reported as audited when it wasn't.
async function audit(target) {
  let lastError = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt > 0) await sleep(RETRY_MS);
    try {
      const run = await lighthouse(
        target.url,
        { port, output: "json", logLevel: "error", disableStorageReset: true },
        CONFIG
      );
      if (!run || !run.lhr) throw new Error("lighthouse returned no result");
      const runtimeError = run.lhr.runtimeError;
      if (runtimeError && runtimeError.code && runtimeError.code !== "NO_ERROR") {
        lastError = `${runtimeError.code}: ${String(runtimeError.message || "").slice(0, 200)}`;
        continue;
      }
      return { template: target.template, url: target.url, ok: true, lhr: run.lhr };
    } catch (error) {
      lastError = String((error && error.message) || error).slice(0, 300);
    }
  }
  return { template: target.template, url: target.url, ok: false, error: lastError };
}

for (let i = 0; i < targets.length; i++) {
  if (i > 0) await sleep(GAP_MS);
  results.push(await audit(targets[i]));
}

fs.writeFileSync(outPath, JSON.stringify(results), "utf8");
