// Lighthouse sidecar — spec §7.
//
// Runs via the Node API against the *shared* browser, not the CLI — the CLI
// cannot carry the storefront-gate session, so it would audit the password page
// six times and report it as the store. Python launches Chromium with
// --remote-debugging-port and passes that port here; Lighthouse opens its tabs
// in that browser's default context, into which the crawler has mirrored the
// gate cookie (see below).
//
//   node lighthouse_runner.mjs <port> <targets.json> <out.json>
//
// targets.json: [{ "template": "pdp", "url": "https://…" }, …]
// out.json:     [{ "template", "url", "ok", "lhr"?, "error"? }, …]
//
// A failure on one template is recorded and the run continues (spec §7).
// Partial evidence is recorded as partial, never interpolated.

import fs from "node:fs";
import lighthouse from "lighthouse";

// mobile-4g-slow, pinned explicitly. These are Lighthouse's own mobile defaults
// today; pinning them means a Lighthouse default change shows up as a version
// bump in manifest.yaml rather than as silent fixture drift.
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

// Lighthouse opens its tabs in the browser's default context. Before invoking
// this, the crawler mirrors the storefront-gate cookie from its own isolated
// context into that default context (session.mirror_session_to_default), so
// these audits hit the store behind the gate rather than /password (spec §7).
// disableStorageReset keeps that cookie from being cleared between templates.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const GAP_MS = 2000; // politeness between full page loads on a store we don't own
const RETRY_MS = 5000; // let a throttled dev store recover before a second try

// Lighthouse does not throw on a load failure — it returns an LHR carrying a
// `runtimeError` (ERRORED_DOCUMENT_REQUEST, etc.) with null metrics. Treating
// that as success would report a template as audited when it was not, so a
// runtimeError is a failure here, retried once (slow dev stores throttle under
// back-to-back audits) and then recorded as failed — never interpolated (§7).
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
