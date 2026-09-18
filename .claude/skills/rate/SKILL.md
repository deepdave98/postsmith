---
name: rate
description: Records Deep's 1-5 rating and tags for generated drafts (blind, before verdicts are shown), for corpus posts, or reviews a month of ratings and performance; grows lessons, the lexicon's user tells and the persona's Never list, and runs calibration every 20 ratings. Use when Deep says "rate", "/rate blind", "rate the corpus", "that one sounds like AI", "not me", or "monthly review".
argument-hint: "blind [run] | <draft-id> <li|x> <1-5> [tags] [note] | corpus | review"
disable-model-invocation: true
allowed-tools: Read Write AskUserQuestion Bash(uv run *)
metadata:
  skill_version: "1.0"
---

# /rate

Request: $ARGUMENTS

Project state (pending ratings, calibration due, versions):
!`uv run tools/status.py --brief || true`

## Why this exists
Ratings are the only ground truth about Deep's taste. Judges approximate it; `calibrate.py` measures how well, and every proposal to change a lexicon, an anchor or a threshold rests on these rows. A rating taken after Deep has seen PASSED or DID NOT PASS inherits the judge's verdict and measures nothing, so a run is rated blind first: texts only, no labels, no scores, no order that gives the finalist away. Corpus ratings are blind by construction because no verdict exists for them.

Tag vocabulary (contract §13; nothing else is recorded): `too_safe not_funny sounds_ai not_me too_long too_short hook_weak copycat wrong_facts too_mean great_hook great_ending media_miss media_great`. A tag with a cited phrase is worth more than a score: `sounds_ai` with the phrase becomes a user tell, `not_me` with a reason becomes a `## Never` line.

## Modes
Read the mode from the arguments; when the draft id is fuzzy (`agents li 4`), `uv run tools/draft_id.py <draft-id> <li|x> --json` resolves it to `{run, cid, platform, path}` from finished drafts; when it returns `ok: false` with `candidates`, ask which one and rerun.

**blind [run]**: the default after every `/post`. Run = the argument, else the newest run the status brief lists as unrated, else the newest directory under `drafts/` that is not `eval_*`, `learn_*` or `trending`. The blind set is `drafts/<run>/final/blind.json`, which `assemble_report.py` writes at deliver: `{"run", "items": [{"key": "A"|"B"|"C", "platform", "text"}], "seed"}`, two or three texts (the finalist, an alternate and one that did not pass, when available), lettered in an order shuffled by a seed from the run id, carrying no cid and no verdict, so nothing you hold before the rating says which one passed. Show each `text` under its key exactly as it is (line breaks intact) and open nothing else: not `report.md`, not `lineage.json`, no `scores/` or `candidates/` file, until the ratings are in. When `blind.json` is missing, run `uv run tools/assemble_report.py <run> --json` first (it writes the file and reveals nothing to you) and continue. Say nothing about verdicts, scores, rounds, writers or moves before the ratings are recorded. Collect per text: a 1-5 score (options), tags (multi-select from the vocabulary, optional), and an optional note, in one or two `AskUserQuestion` calls per text. Record each with `uv run tools/rate_record.py --kind generated --blind --ref <run>:<key> --score N [--tags a,b] [--note "..."] --json`; the tool maps the key back to the cid through `final/blind.json`. Then reveal: `uv run tools/assemble_report.py <run> --json` (with a blind row present it renders the verdicts; `--show-verdicts` forces them) and print the key, cid, verdict and a one-line judge evidence for each, calling out disagreements (Deep >= 4 on a fail, or <= 2 on a pass): those are the rows calibration lives on, so ask for the phrase or reason when the tag is `sounds_ai` or `not_me` and it is missing.

**<draft-id> <li|x> <1-5> [tags] [note]**: direct rating of a variant Deep has already looked at. If the run has no blind rating yet, offer `blind` first and record the direct rating only if he declines; the ref is `<run>/<cid>` and the row is written without `--blind` so calibration can weight it.

**corpus**: batches of five train posts from `corpus/posts/` that have no rating yet (`uv run tools/rate_record.py --list-rated --kind corpus --json` returns `{"ok", "ids": [...]}`, the rated corpus ids, because `corpus/ratings.jsonl` is denied to this thread; heldout posts are never shown and never rated here). Show each text without author, engagement or card fields, collect score and tags, record with `uv run tools/rate_record.py --kind corpus --ref <post_id> --score N [--tags a,b] --json`. After each rating show the card's one-line thesis and archetype from `corpus/cards/<post_id>.md` for a yes/no: this is where a sarcastic post read literally gets caught. On "no", take Deep's one-line correction and write it to `corpus/cards/_reviews/<post_id>.user.md`; `/learn --only cards` re-annotates flagged cards and hands that line to a fresh annotator verbatim (annotators cannot open reviews). Offer another batch; stop when he says so.

**review**: monthly. `uv run tools/calibrate.py --json` for kappa, rho, per-tag false negatives and proposals (after 20 posted variants it also proposes PREFER/AVOID by angle family, move, lens, media and length); `uv run tools/topics.py scoreboard --json` to rewrite the moves scoreboard. Then group posted variants by angle family, move, lens, media decision and length band using `memory/performance.jsonl`, `memory/published/*.md` front matter and each run's `final/lineage.json`, and rewrite `## Proven angles` in `memory/topics.md` as rows `| angle | family | n | median views | median comments | best draft_id/platform | last posted |`. Performance never changes a judge score; it informs the matrix and `/trending` only.

## After every rating
`uv run tools/rate_record.py --proposals --json` says when something is due. Apply nothing without a yes, and apply in this order because each step is cheaper and more reversible than the next:
1. **User tell** (`sounds_ai`/`not_me` with a cited phrase): append `{phrase, added: <date>, source: "rate:<cid>"}` to `user_tells` in `style/lexicon.yaml`, bump `lexicon_version`, set `updated`, then `uv run tools/health_run.py --scope deterministic --write --json` so the golden set proves the new pattern breaks nothing.
2. **Anchor**: make the rated post an anchor for the disagreeing dimension (weak at <= 2, strong at >= 4). Anchors, thresholds and anchor text live in an immutable rubric version, so write a new `evals/rubric/v<N+1>/` copied from `current`, change only that, add a CHANGELOG line, and leave `current` alone; `/eval health --promote` switches it once health is green.
3. **Threshold** by one, same versioning.
4. **Anchor text** reworded, same versioning.
Every 20 ratings `calibrate.py` runs (the proposals output says so); kappa is withheld until 8 rated system-fails exist and verdicts stay "advisory" in reports until kappa >= 0.4 on n >= 30, which is why the did-not-pass text in blind mode matters.

**Lessons**: only when the proposals output shows >= 3 ratings sharing a tag and you can name one cause from their notes and cids. Write it in the contract §13 shape (`- L-nnn (<date>, run <run>; tag <tag> x<n>) AVOID|PREFER: ... Evidence: <cid> "<short quote>"; ...`) via `uv run tools/lessons.py add --json` (its `--help` lists the field flags); entries cite tags and cids, never scores. Every 20 ratings `uv run tools/lessons.py consolidate --json`; `lessons.py retire` moves entries unreinforced for 90 days.

**Persona**: a confirmed `not_me` proposes one line for `## Never` in `style/persona.md` with the cid as evidence; append it only on a yes.

## Boundaries
Never show a verdict, score, or judge evidence before a blind rating is recorded. Never read `corpus/heldout/`, `corpus/ratings.jsonl` or `evals/calibration.jsonl` directly; the tools read them. Never edit candidate or corpus text. Never edit a promoted rubric version in place. Never record a tag outside the vocabulary or a score Deep did not give.
