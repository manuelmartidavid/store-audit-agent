# Runbook — the 0.3.0 capture wave

    written:  2026-07-31, for Marti, to be followed top to bottom.
    what this is:     the order of operations, with copy-pasteable commands.
    what this is NOT: the reasoning. Every step here has a "why" in
                      `evals/FREEZE-CHECKLIST.md` — this file deliberately does
                      not repeat it, so the two cannot drift apart.
    when in doubt:    the checklist wins.

**Total time:** roughly half a day. Phases 0–2 are ~40 minutes. Phase 3 is the
long one. Phase 5 is mine, not yours.

---

## At a glance

| Phase | What | Time | Whose |
|---|---|---|---|
| 0 | Fix the machine's IPv6 preference | 2 min | yours |
| 0b | Fix the router (optional) | 15–30 min | yours |
| 1 | Pre-flight | 5 min | yours |
| 2 | Screen the two stores we don't own | 10 min | yours |
| 3 | Capture five fixtures | 1–2 hr | yours |
| 4 | Archive + record provenance | 20 min | yours |
| 5 | Re-label, re-measure, prompt v1.1 | — | mine |

**Do phases 1–4 in one sitting.** Don't update Node, Lighthouse, axe or Chrome
partway through — tool versions and `throttling` must match across all five
entries, and drift mid-wave silently invalidates every comparison between them.

---

## Phase 0 — Machine fixes

### ▢ 0.1 Prefer IPv4 (2 minutes, do this first)

Your router advertises IPv6 with no working route, so anything using Python's
`urllib` waits ~60 seconds per fetch before falling back. Measured: **63.81 s
versus 0.16 s** on the same URL.

**Open PowerShell as administrator:** Start → type `powershell` → right-click
*Windows PowerShell* → **Run as administrator** → Yes.

```powershell
netsh interface ipv6 set prefixpolicy ::ffff:0:0/96 60 4
```

**Check it worked:**

```powershell
netsh interface ipv6 show prefixpolicies
```

| | |
|---|---|
| ✅ Good | `::ffff:0:0/96` shows precedence **60** |
| ❌ Not applied | it shows **35** (the default) |

**To undo:** `netsh interface ipv6 reset prefixpolicies`

> This does **not** disable IPv6. It only changes preference order.

**Then ping me** — I'll re-run the 63.81 s measurement and confirm it took effect
machine-wide.

### ▢ 0.2 Fix the router (optional — 0.1 already unblocks the wave)

1. **Power-cycle.** Unplug 30 s, replug, wait for full sync. Then test:
   ```powershell
   ping -6 -n 2 2001:4860:4860::8888
   ```
   ✅ replies · ❌ *Destination host unreachable* (what you get today)

2. **Open the router admin page:**
   ```powershell
   ipconfig | findstr /i "Default Gateway"
   ```
   Browse to that IPv4 address. Login is usually on a sticker on the unit.

3. **Go to WAN → IPv6 status** and answer one question: **does the WAN side have a
   global IPv6 address and a delegated prefix?**

   - **LAN has a prefix, WAN has none** → that's your fault confirmed. The router
     advertises a prefix it can't route. Go to 4.
   - **Anything else** → screenshot it and send it to me.

4. **Pick one:**
   - Set IPv6 WAN mode to **Native** or **DHCPv6-PD** (whichever your ISP uses),
     save, reboot, re-test.
   - **Or turn IPv6 off at the router entirely.** This is a legitimate fix, not
     giving up — no Router Advertisement means no device ever tries the dead
     route. Half-working IPv6 is worse than none.

5. **Calling the ISP?** Say exactly this: *"Is IPv6 provisioned on my account? My
   router gets a WAN prefix but no upstream route — traffic to public IPv6 dies
   one hop past the gateway."* Your prefix `2001:4450::/32` is a real allocation,
   so they do have IPv6 deployed. That phrasing skips a tier of scripted
   troubleshooting.

---

## Phase 1 — Pre-flight

### ▢ 1.1 Record the toolchain

```powershell
cd C:\Users\Marti\Documents\Projects\StoreAuditAgent
node --version
npx lighthouse --version
```

Write both down — they go into every `context.yaml` in phase 4.

### ▢ 1.2 Confirm the password is loadable

`.env` must still hold `TSCC_STOREFRONT_PASSWORD`. Entries 02 and 05 are dead
without it.

### ▢ 1.3 Confirm the suite is green before you start

```powershell
python -m pytest tests/ -q
```

✅ **624 passed, 1 skipped.** Takes ~8–16 minutes. Start it and do phase 0.2 while
it runs.

---

## Phase 2 — Screen the stores we don't own

Entries 01 and 04 aren't ours, so the criteria that selected them get re-verified
immediately before capture. **Do this before any capture** — finding out a store
no longer qualifies is much cheaper now than after five captures.

```powershell
python -m planting.screen_candidate --entry 01
python -m planting.screen_candidate --entry 04
```

| Exit | Meaning | Do |
|---|---|---|
| **0** | every hard gate passed | continue |
| **2** | ❌ a hard gate failed | **STOP.** That store needs re-selecting — talk to me |
| **3** | perf gates never ran | fine if you passed `--skip-perf`; otherwise investigate |
| **1** | operational failure | investigate |

**Entry 04 prints a `perf (recorded, NOT a gate…)` block, and that is correct.**
Its LCP/CLS are measured but not disqualifying (decision 32) — the perf bar is
entry 01's selection criterion, and entry 04 exists to exercise the reduced path
and the null-AOV trap on a store that matches the ICP. Expect exit **0** with a
trailing line naming the measurements that sit over the rubric line. **Those are
labels, not a re-selection trigger.** Entry 01's bar is unchanged: the same
numbers still exit 2 there.

### ▢ 2.1 Characterise entry 04's `cls:pdp` before capturing

Its first screen read **0.000–0.301 across two runs** — bimodal, straddling the
0.25 line, so whichever value the fixture catches decides between a `high` finding
and no finding at all.

```powershell
python -m planting.screen_candidate --entry 04 --runs 5
```

If it stays bimodal, tell me — it becomes a recorded label-fragility note, or
grounds to accept CLS isn't a label for this entry. Either way it's a labelling
decision, not a reason to drop the store.

**Other expected quirks:**
- Both reports should print a `resolver: IPv4 tried before IPv6` line. If it's
  missing, you're running old code.
- Don't compare gate *counts* to older notes. The count is a property of the
  screen and changes with the code; compare verdicts.

---

## Phase 3 — Capture

### ▢ 3.1 The freshness gate — the one that bites

**This has no automation. If you skip it, everything downstream still reports
success.**

A TSCC page once froze for **4+ hours**. Theme pushes, editor saves, an
unpublish/republish and UA changes all failed to bust it. A capture of a frozen
page labels a planted defect out of existence with no error anywhere.

Run this for **home, collection, the pinned PDP, and cart**:

```powershell
python -m planting.inspect_lcp https://torontosportscard.myshopify.com/ --password-env TSCC_STOREFRONT_PASSWORD
```

Check the `compiled_assets/styles.css ?v=` stamp is current on each.

> ⚠️ **Stale stamp = STOP.** Note the `{% stylesheet %}` compile can itself lag ~4h
> behind a push, so stale doesn't always mean a stale document — but it always
> means find out which before capturing.

### ▢ 3.2 Run the captures

**Order matters** — 02 first, because it's the one that unblocks everything else.

```powershell
# 1. the critical path
python -m crawler --context evals/golden/02-sabotaged/context.yaml --out fixtures/02-sabotaged/

# 2. same store, no password (the blocked path)
python -m crawler --context evals/golden/02-sabotaged/context.yaml --out fixtures/05/ --no-password

# 3. clean theme — the first real precision test
python -m crawler --context evals/golden/01-clean-theme/context.yaml --out fixtures/01/

# 4. WooCommerce — also a live test of the 0.3.0 cart fix
python -m crawler --context evals/golden/04-woocommerce/context.yaml --out fixtures/04/

# 5. app-heavy, confirm as entry 03
python -m crawler --origin https://makerlab-electronics-ph.myshopify.com --out fixtures/makerlab/
```

> Entry 04 takes ~2.5 minutes longer than the rest, entirely in `Crawl-delay`
> waiting. **That's arithmetic, not a hang.**

### ▢ 3.3 Read each crawl's verdict before moving on

Open `fixtures/<name>/crawl.json` and check:

| Check | ✅ Good | ❌ Stop |
|---|---|---|
| `status` | `complete` | anything else |
| templates | 6/6 (0/6 `blocked` for entry 05) | fewer, unexplained |
| `crawler_version` | `0.3.0` | anything else |
| `fingerprint.platform` | matches the entry, with evidence | **`unknown` on a reachable store** |
| **PDP url** | **the product you intended** | any other product |

> 🔴 **The PDP check is the big one.** Discovery resolving to the wrong product has
> cost this project two entire recaptures. Entries 01, 02 and 04 all pin their
> PDP, so this should hold — but verify it, don't assume.

**Entry 04 has one extra check.** Its `cart` is deliberately *not* pinned, so
discovery has to find `/basket/` unaided — this is the live test of the 0.3.0 fix:

| `templates.cart.url` | Meaning |
|---|---|
| `…/basket/` | ✅ the fix works on a real store |
| `…/cart` or `absent` | 🔴 real regression — stop and tell me |

---

## Phase 4 — Freeze

### ▢ 4.1 Archive each fixture

`fixtures/` is gitignored, so **a lost capture is a lost golden entry** — and for
entries 01 and 04 the archive is the only recoverable copy.

```powershell
python -m crawler.archive fixtures/02-sabotaged -o archives/02-sabotaged.tar.gz
python -m crawler.archive fixtures/05          -o archives/05.tar.gz
python -m crawler.archive fixtures/01          -o archives/01.tar.gz
python -m crawler.archive fixtures/04          -o archives/04.tar.gz
python -m crawler.archive fixtures/makerlab    -o archives/makerlab.tar.gz
```

### ▢ 4.2 Record provenance in each `context.yaml`

Update the `eval.fixtures` block for every entry:

- `manifest_sha256` ← from the new `manifest.yaml` (**this is the pin the labels
  are scored against**)
- `captured_at`
- `lighthouse_version`, `axe_core_version`, `chrome_version` (from phase 1.1)
- `throttling` — must be identical across all five
- `theme_id` (entry 02)

---

## Phase 5 — Hand it to me

Once the fixtures exist, this part is mine:

- Re-label entry 02 from the new fixture — price and stock are now detectable, so
  the presence checklist gains two items back and the label set likely grows past
  17, which means recomputing the composite and the `expect` range
- Measure the new pack: `python -m triage.pack_evidence fixtures/02-sabotaged --stats`
- `finding-triager` v1.1 restoring the two checklist items
- Decision 31's deferred rubric §1 clarification
- Re-run the evals with all five provenance pins

### 📩 Send me this as soon as capture #1 finishes

Before you do the other four:

1. `fixtures/02-sabotaged/manifest.yaml`
2. The `templates` block from `fixtures/02-sabotaged/crawl.json`

That tells us immediately whether the distiller fix actually worked — **prices
surviving into the distilled tree** — which is the whole point of the wave. If it
didn't, better to know before you capture four more.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| A fetch hangs ~60 s | IPv6 preference not applied | Phase 0.1 |
| Screen exits 2 | a hard gate failed | **Stop** — re-selection trigger, talk to me |
| `platform: unknown` on a live store | fingerprint found no evidence | Check the page actually loaded; don't proceed |
| PDP is the wrong product | discovery raced the cache | Check the pin in `context.yaml`; re-capture |
| Entry 04 cart is `/cart` or absent | 0.3.0 cart discovery regressed | **Stop** and tell me |
| Capture seems stuck on entry 04 | honouring `Crawl-delay: 10` | Normal — ~2.5 min of waiting |
| Password appears in a fixture | — | Can't happen silently: `redaction.assert_absent` is fatal and deletes the file |
| Suite fails before you start | something already broken | Don't capture on a red suite |

---

## The three things most likely to waste your day

1. **Skipping the freshness gate** (3.1). No automation, no error, and it poisons
   the fixture silently.
2. **Not checking the PDP resolved correctly** (3.3). Has cost two recaptures.
3. **Updating a tool partway through the wave.** Versions must match across all
   five entries or cross-entry comparison is void.
