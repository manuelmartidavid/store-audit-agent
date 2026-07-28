# Human read: `runs/narrator-v0.1-run1.json` (entry 02, run 1)

**This is an agent's read, not the project owner's.** Decision 3's editing-cost
criterion (`PROJECT-STATE.md`: "If >~30% of the narrative needs rewriting
before a client could receive it, the translation layer failed") calls for a
human read of a client artifact. There is no client artifact yet — this
narrative is the closest available proxy, and this read is a proxy for the
human read the criterion actually wants, done by the agent that ran the
pipeline rather than by a person who would send the report. Treat the figure
below as a baseline signal, not a substitute for someone reading it who isn't
the one that built it. The number is reported as found, not adjusted toward a
target in either direction.

Source: `runs/narrator-v0.1-run1.json`, output only (`summary` + 19 findings ×
3 fields each = 58 client-facing text fields). Cross-checked against
`briefs/02-sabotaged.brief.json` for `title`/`category`/`severity`.

## 1. Editing cost

**Estimate: roughly 5% (about 3 of 58 fields) need rewriting on content
grounds before this could go to a client**, well under decision 3's >~30%
kill line. That is the honest content-accuracy number; a separate, larger
stylistic-monotony concern is noted under Q2 and is not folded into this
figure, because decision 3's test is about needing rewriting, not about a
polish pass a careful editor would still make.

Three fields drove the estimate:

- **`F-14.change`**: *"Add a main heading to the home page describing what
  the shop sells."* The finding's title is "Home page has no level-one
  heading" — a structural/accessibility-SEO defect about the H1 element
  existing at all. The prompt's own contract for `change` says it must
  follow from `title` and `category` and nothing else; "describing what the
  shop sells" is not supported by either. It happens to be *plausible*
  advice, but it is scope the model added, not scope the finding licensed —
  exactly the fabrication risk the contract calls out. I'd cut it to "Add a
  level-one heading (H1) to the home page."
- **`F-11.consequence`**: *"Supporting text on collection and product pages
  is faint enough that some shoppers simply cannot read it."* The finding is
  medium severity ("axe violation off the purchase path" — i.e. hygiene, not
  a blocker). "Simply cannot read it" describes total inability; a contrast
  failure at this severity band more often means difficulty, not
  impossibility. Mild overstatement relative to the finding's own severity
  rationale — see also Q4.
- **`F-06.consequence`** (paired with `F-05.consequence`, see Q4): the two
  read at nearly the same intensity despite one finding being `high` (10.5s
  mobile LCP) and the other `medium` (3.9s, inside the 2.5-4.0s band). I'm
  counting this as one edit (soften F-06, or differentiate the two) rather
  than two.

Everything else — 55 of 58 fields — reads as sendable without a rewrite. No
digits, no jargon (LCP/CLS/axe never appear, matching the prompt's ban), no
hedging stacks, no stacked adjectives ("catastrophic", "severe" do not
appear).

## 2. Does it read like a person, or like slots?

The one stated risk of the bounded-field contract does show up, but mostly in
one field, not across the narrative.

**Best example** — the summary's second sentence has real rhythm and doesn't
read like a template fill:

> "Below that sits a layer of friction — dead links on the home page, slow
> loading on phones, faint button text, and missing shipping, tax and returns
> detail at the moments buyers decide."

That's a sentence a person would write to open a report: it groups four
unrelated defects into one image ("a layer of friction") instead of listing
them. `F-08.consequence` — *"Pages pull down far heavier images than they
actually display, so shoppers wait on their data for nothing."* — has the
same quality; "wait on their data for nothing" is a phrase with a point of
view, not a slot fill.

**Worst example (structural, not any single sentence)** — the `affects`
field, 15 words max, converges on one shape across most of the 19 findings:
"Every visitor who...", "Every shopper who...", "Every cart shopper...",
"Every home page visitor...", "Every visitor who does not use a mouse.",
"Every shopper on a product page." Read individually each is fine and
accurate; read as a set of 19 in a row, the repetition of "Every ___ who/on
___" is the tell that a script is walking a list rather than a person writing
continuous prose. This is a direct consequence of the 15-word cap plus
"which visitors" being the only thing that field can say — the contract
narrows the field so hard that a human writer would also converge on similar
phrasing, but a human editor would still vary three or four of them for a
finished report. This is real texture cost, but it's a polish pass, not a
correctness problem, which is why it isn't folded into the Q1 percentage.

## 3. Is any `change` wrong?

Checked all 19 against `title` + `category` in the brief. Eighteen of
nineteen follow directly from the title with no invented cause — including
the two performance findings without an obvious mechanism (`F-05`, `F-06`),
where the model correctly used the prompt's escape hatch ("Have a developer
find what delays the product/home page on phones and reduce it.") rather
than guessing a cause, which is exactly what the prompt's "one thing you must
not invent" section asks for.

One is over-scoped rather than factually wrong: **`F-14.change`** (see Q1
above) adds "describing what the shop sells" to a fix that the title only
supports as "add an H1." It isn't a wrong remediation — adding an H1 that
states what the shop sells is a reasonable thing to do — but it's added
specificity the title didn't license, which is the fabrication risk this
contract's `change` field deliberately accepted rather than closed.

The `F-21` (noted/security) change — *"Review that product page copy and its
hidden metadata, and remove text not meant for shoppers."* — is appropriately
non-committal for a `noted` finding with no severity, and it does not repeat
the injected text or call it an attack, which the prompt specifically
forbids for this bucket. Correct.

## 4. Is any `consequence` overstated relative to severity?

Two candidates, both mild:

- **`F-11`** (medium, "axe violation off the purchase path"): "some shoppers
  simply cannot read it" reads closer to a `high`/blocking claim than a
  medium hygiene one. See Q1.
- **`F-06`** (medium, 3.9s mobile LCP, "inside 2.5-4.0s band") vs. **`F-05`**
  (high, 10.5s mobile LCP): "The home page takes a noticeable beat to show
  anything on a phone, and impatient visitors leave first" (F-06) sits at
  almost the same intensity as "A shopper on a phone waits at a mostly blank
  product page long enough that many give up" (F-05), despite the underlying
  LCP being roughly 2.7x worse for F-05. The numeral ban makes this harder to
  avoid — neither field may say "10.5s" vs "3.9s" — but the prompt does
  license directional language ("long enough that many will leave" is given
  as an example), so there was room to write F-06 more mildly than F-05 and
  the run didn't take it.

No finding reads as understated relative to its severity; both misses run in
the same direction (slightly hot, never slightly cold).

## 5. Did the advisory checks catch anything real?

**No — every advisory hit in this run's gate output is a false positive**,
and each one is the exact failure mode the harness's own docstrings warn
about:

- `template_containment_notes` flagged `F-02`, `F-01`, `F-09`, `F-14` for
  mentioning "search" or "cart" outside their declared templates. In every
  case the word is being used generically — "search engines" (F-02, F-09,
  F-14) or "add a card to the **cart**" describing the on-page action (F-01)
  — not a claim that the defect appears on the site's `search` or `cart`
  template. This is precisely the false-positive case
  `eval_narrative.py`'s docstring calls out by name ("'cannot add this
  product to the cart' is correct English about a PDP defect").
- `quantity_word_notes` flagged `F-07.affects` ("most of all on phones") —
  an idiom meaning "especially," not a quantity claim; and `F-05.affects`
  ("Mobile shoppers, who are most of your traffic") — which *is* a magnitude
  claim, but a licensed one: `store.mobile_share` is `0.7` in the brief, the
  prompt's own example of allowed directional language is "most mobile
  shoppers," and no digit appears. Correctly not a numeral violation, and my
  read agrees it doesn't need editing.

So: advisory correctly stayed advisory. Nothing it flagged corresponds to an
actual problem in this run, and the two real content issues I found (Q1/Q4)
were not caught by either advisory check — they are exactly the category the
harness's own comments say is "not mechanically checkable at all... the
human read's job."

## Bottom line

Editing cost ≈ 5% of fields on content grounds, clear of the >~30% kill
line, from a single-run, agent-conducted read. The one stated structural risk
(slot-assembled `affects` phrasing) is visible but didn't rise to "needs
rewriting" by itself. The one place fabrication risk materialized
(`F-14.change`) is a mild over-specification, not a wrong remediation. This
is a baseline from N=1, by a non-target reader — it should not be read as
"decision 3 is satisfied" so much as "decision 3's instrument produced its
first real number, and the number was good."
