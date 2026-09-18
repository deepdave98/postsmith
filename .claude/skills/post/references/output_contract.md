# Output contract for `/post`

`uv run tools/assemble_report.py <run> [--copy]` writes `drafts/<run>/final/` from the merged scores, the Tier 2
files and the media briefs, and prints the terminal layout to stdout. The orchestrator prints that stdout verbatim
(Deep reads the terminal, not the files) and adds only what section 4 lists. Verdict labels come from
`scores/<cid>.merged.json` via the tool, never from the orchestrator.

## 1. `drafts/<run>/final/` layout

### `<cid>.md`, one per delivered variant
Front matter: `platform`, `chars`, `x_len` (X only, as X counts), `fold_preview` (LinkedIn: the text before the
140-character cut), `lens`, `moves`, `round`, `verdict` (`pass | fail | hold | needs_your_call | passed_tier1_only`;
withheld while verdicts are hidden, see section 3), `scores_path`, `tier2_tested: true|false`, `reply_1` (X only).
Body, in order:
1. The post text in a fenced block, exactly as it is pasted: line breaks, casing, emoji and trailing punctuation
   untouched. This block is the deliverable; nothing in it is ever edited after the writer wrote it.
2. `reply_1` for X: the link or line that goes in the first reply (an X body never carries a link).
3. "Why this works": two or three sentences citing the moves by slug from `style/moves.md` and the angle from the
   candidate's `angle_sheet.pick`, so Deep can learn the mechanism, not just the post.
4. Media: `decision` + `decision_reason` citing the rule id (M1–M7) and the `delete_test`; `alt_text`; one fenced
   block per tool prompt preceded by a settings line (tool, aspect ratio, resolution or duration, fallback tool);
   or `real_capture_direction` with what to open, type, crop and redact; or "No media: <delete-test reason>".
5. "Confirm before posting": every `needs_confirmation` claim with its persona line, when any.

### `clipboard.md`
Post texts only, separated by `=====`, each preceded by a one-word header (`LINKEDIN`, `X`, `X1`) and, for X, a
`reply_1:` line after the text. Nothing else, so a paste never carries a label or a score. `--copy` pipes the top
LinkedIn variant to `pbcopy`.

### `report.md`
- Header line: topic · run · rubric version · profile version · lexicon version · `health: green` or `health:
  stale for rubric sha …` · `small-corpus mode: lineup uses train posts` when on · `lineup advisory` when the pool
  could not supply fillers · `voice anchor: weak (self n=…)` when self is below the bar · matrix fallback rung when
  used · `quick: no lineup, no pairwise` under `--quick` · rounds · calls · wall time.
- Per variant, the full table, one row per check and dimension, every one shown separately, never blended:
  `id | class | value or score | threshold | result (pass/fail/na/hold/unscored) | one-line evidence quote`. Tier 0
  checks (`P*`, `O*`, `E1` with the out-of-envelope features and numbers), Tier 1 dimensions with jury votes and
  median when a jury ran, Tier 2: lineup picks with confidence and tell, pairwise wins/ties/losses per order,
  paraphrase verdict, claims table (`text | status | source | needs_confirmation`), media check and media judge
  sub-results. Rounds and what changed between them (the packet's items and whether each cleared).
- Sections in this order: finalists, alternates (`passed Tier 0-1, not lineup-tested`), needs your call (holds,
  unscored gates, persona claims awaiting confirmation), did not pass (each with its failing dimensions and the
  quoted evidence), ops reminders (unrated drafts, metrics due, calibration due).
- `final/blind.json` is written at deliver beside the report: `{run, seed, items: [{key, letter, cid, platform, text,
  text_path}]}`, two or three variants lettered in a seeded order; `/rate blind` shows only `key` and `text` from it
  and `rate_record.py --blind --ref <run>:<key>` maps the key back to the cid.
- Verdict handling: `--hide-verdicts` is the default until `evals/calibration.jsonl` holds a blind rating row for
  this run. Hidden means the PASSED / DID NOT PASS / needs-your-call words, the scores and the failing evidence sit
  in one collapsed section titled "After blind rating" at the end of the file; the tables above it still list every
  check id and its evidence quote but no result column. Deep's rating must not inherit the judge's, which is the
  whole point of the blind step.

### `lineage.json`
`{run, topic, flags, versions: {rubric, rubric_sha, profile, lexicon}, brief: {facts, obvious_takes,
user_detail | story_id}, matrix_rung, variants: [{cid, writer, assignment, angle_sheet, exemplars_seen,
lessons_used, rounds, final_sha, scores_path, media_path, verdict, tier2_tested, waived: []}]}`.
Waivers (`--waive <check>`) appear here and nowhere else.

## 2. Terminal layout (printed verbatim by `assemble_report.py`; the orchestrator relays it unchanged)
````
# <topic> · <run> · rubric v1 · profile p3 · health green · 2 rounds · 51 calls · 9m40s

## LinkedIn · PASSED (1,420 chars · fold: "We killed our AI strategy last week." · lineup 1/3 picked at conf 2 · pairwise win/tie)
```text
<post>
```
Image · 4:5 · Nano Banana Pro (fallback GPT Image) · why: the form is the punchline · delete test: caption ends on a setup with no receipt
```text
<Nano Banana prompt>
```
Confirm before posting: "6 weeks in prod" (persona.can_claim#4)
Rate it: /rate blind <run>     Log it: /posted <run> li <url>

## X · PASSED (271/280 as X counts · lineup 0/3 · paraphrase clean vs 2 exemplars)
```text
<post>
```
reply_1: <link or line for the first reply>
No media: the line is the joke.
Rate it: /rate blind <run>     Log it: /posted <run> x <url>

## Alternates (passed Tier 0-1, not lineup-tested; run --wide to test)
LinkedIn B (short deadpan): ```text ... ```
## Needs your call
r2-w1-li: persona_fit 3, claim "3 domains in staging" needs confirmation (persona.story#2)
## Did not pass
r2-w3-x: humor 3 (jury 3/3/2), evidence: "..."
Files: drafts/<run>/final/  report.md  clipboard.md  lineage.json
````

The pairwise clause in a variant header is `pairwise <outcome>` when a reference-mode score exists; else
`paraphrase clean|hit vs N exemplars` from the exemplar gate Tier 2 always runs; else `pairwise skipped, lineup
clean` when no pairwise ran and the lineup was clean, or `pairwise not run`.

## 3. Hidden-verdict mode (the default until `/rate blind <run>` has run)
Same layout with these substitutions, so nothing on screen tells Deep what the judges decided before he rates:
- Variant headers carry no label: `## LinkedIn · A (1,420 chars · fold: "…")`, `## X · A (271/280 as X counts)`.
  Lineup, pairwise and jury numbers are omitted from the header.
- The alternates, needs-your-call and did-not-pass sections are merged into `## Also delivered` with the texts and
  headers only; failing dimensions and evidence are not printed.
- "Confirm before posting" lines still print: a claim needing Deep's confirmation is his information, not a verdict.
- One closing line: `Verdicts, scores and evidence: hidden until /rate blind <run>; then in
  drafts/<run>/final/report.md.`
- The disclosures in the header line (health, small-corpus mode, lineup advisory, voice anchor, rung, quick) are
  never hidden; they describe the run, not the posts.

## 4. Follow-up lines and what the orchestrator adds
Under every delivered variant, exactly:
```
Rate it: /rate blind <run>     Log it: /posted <run> <li|x> <url>
```
After a blind rating exists, `/rate <run> <li|x> N [tags] ["note"]` rates a variant directly; `draft_id.py` makes
the run id fuzzy, so `<run>` may be typed as its slug.
After the tool's output the orchestrator prints only: the `memory/topics.md` row it added, the persona story marked
`used_in:` if one was used, and any stop reason from `run_next` notes, quoted as written.
