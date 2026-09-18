---
name: learn
description: >-
  Rebuilds the learned style layer from the corpus without ingesting anything: re-annotates and re-verifies
  cards, recomputes envelopes, rebuilds author profiles, self.md, common.md, moves.md, media_habits.md,
  exemplars.md and the lexicon do_not_reuse block. Use when Deep says "learn", "rebuild the profiles",
  "re-annotate", "redo the cards", "rebuild moves", after a taxonomy or card-spec change, or when /status
  reports missing or unverified cards.
argument-hint: "[--force] [--only cards|profiles|moves] [--author slug]"
disable-model-invocation: true
allowed-tools: Read Write Glob Grep Agent AskUserQuestion Bash(uv run *)
effort: high
metadata:
  skill_version: "1.0"
---

# /learn

Request: $ARGUMENTS

Project state (versions, counts, health, nags):
!`uv run tools/status.py --brief || true`

## What this is for
/ingest runs the learn phase automatically; /learn re-enters it on purpose. That is needed after a taxonomy edit
(old device or archetype ids no longer resolve), after a change to the card spec or the quality bar, when cards were
left unverified, or when a profile reads wrong and Deep wants it rebuilt from the cards. Nothing here touches post
text or the split; the corpus is input only. The output is the same as /ingest's learn phase: cards under
`corpus/cards/` and `corpus/heldout/cards/`, envelopes in `style/profile.json`, and the files under `style/` that
writers read. The card format and annotator bar are in `.claude/skills/learn/references/card_spec.md`.

Tools run from the project root as `uv run tools/<name>.py ... --json`; read the JSON; if `ok` is false stop and
show the error.

## Scope flags
- `--only cards`: 4a through 4c and the confirmation, then stop. `--only profiles`: 4d through 4f.
  `--only moves`: one wave-2 builder with a moves-only assignment (`style/moves.md` plus its CHANGELOG line), then
  `moves_lint.py` and the leak check. No `--only`: everything, cards first.
- `--force`: re-annotate every post in scope even if its card is verified (a taxonomy change invalidates ids, a
  spec change invalidates shape); for profiles, rebuild from the cards instead of editing the existing text, while
  keeping move ids stable through aliases so the scoreboard and old cards still resolve.
- `--author slug`: restrict the posts to that author and the profile wave to `style/authors/<slug>.md`. The
  wave-2 builder still runs, because common.md, moves.md and exemplars.md are derived from every author.
- Without `--force`, a post is (re)annotated when it has no card, when `card_lint.py` fails its card, or when its
  card is `verified: false` and `--author` names its author. That last condition keeps a twice-rejected card from
  looping on every /learn. Verified cards are kept: re-annotating a good card costs a verifier and can only add
  noise.

## 4a. Stylometry
`uv run tools/stylometry.py --corpus --json` on the whole corpus; it is cheap and the envelopes need every post.

## 4b. Cards (`post-annotator`, batches of up to 8 prompt files, in parallel)
Annotators never open a post: `tools/card_prompts.py` writes one self-contained prompt file per post under
`drafts/learn_<date>/prompts/<post_id>.annotate.md` (post text inside `<untrusted_post>`, media preview paths,
the `profile_version` to record, the spec pointer, the card output path `corpus/cards/<id>.md` or
`corpus/heldout/cards/<id>.md`), and the agent receives the prompt file path and the output path. The session-wide
`Read(corpus/heldout/**)` deny applies to every agent; this is how heldout cards get written without anyone
reading a heldout file, and it means you never open a prompt file either.
`uv run tools/card_prompts.py build --all-uncarded --kind annotate --json` for the posts without a card;
`uv run tools/card_prompts.py build --post <id> --kind annotate --json` for each post you re-annotate for another
reason (its card fails `card_lint.py`, it is `verified: false` and `--author` names its author, a
`corpus/cards/_reviews/<id>.user.md` correction from `/rate corpus` exists, or `--force`; the tool overwrites the
old prompt and the annotator overwrites the card without ever seeing it). A `.user.md` correction is one line you
can read (train cards only); paste it verbatim under that post's pair as Deep's correction. Take `prompt_file`
and `output_path` per post from the tool's JSON. One `post-annotator` per batch of at most 8 prompt files, all at
once, at most 20 concurrent; the delegation is `prompt_file:` / `output_path:` pairs and nothing else. Annotators
reply `post_id | archetype | thesis` per card plus any prompt file they could not complete; keep those lines for
the confirmation. `uv run tools/card_lint.py --post <id> --json` on each new or changed card before verification
(annotators have no shell); problems go back once to a fresh annotator with the same pair and the `problems` rows
under it, then lint again.

## 4c. Verification (`card-verifier`, 100% of changed cards)
`uv run tools/card_prompts.py build --all-uncarded --kind verify --json` writes `<post_id>.verify.md` for every
card without a current review (post text, the card inline, the round, the review output path
`corpus/cards/_reviews/<id>.md` or `corpus/heldout/cards/_reviews/<id>.md`); `--post <id>` after a rewrite. One
`card-verifier` per batch of at most 8 prompt files, in parallel, `prompt_file:` / `output_path:` pairs only.
Objections send the card back once: `card_prompts.py build --post <id> --kind annotate --json` (the new prompt
inlines the review's objections; annotators cannot open reviews), a fresh `post-annotator`, lint, `--kind verify
--post <id>`, a fresh verifier. A second rejection leaves `verified: false` and the card is ignored by the builders
and listed in the report. The review file is the record; mirror its `verified` value onto the card with a one-line
edit where the card is readable (train, self). The value comes from the review, never from your own reading.

Confirmation with Deep: show `post_id | archetype | thesis` for every card whose thesis or archetype changed (all of
them under `--force`), then one question for the batch: which ids are wrong, with a one-line correction, or "all
good". A "no" goes back to a fresh annotator: rebuild its annotate prompt with `--post <id>`, put the correction
verbatim under the pair, then lint and verification again. When the last card is settled, `uv run
tools/card_prompts.py archive --json` moves the learn prompt files to `drafts/learn_<date>/archive/`
(`quote_leak_check.py` ignores `drafts/learn_*`; the archive keeps heldout text away from every later agent).

## 4d. Envelopes
`uv run tools/profile_stats.py --write --json`: new `profile_version`, previous kept as `style/profile.p<N>.json`.

## 4e. Profiles (`profile-builder`, two waves)
Wave 1 in parallel: one builder per author with at least `corpus.author_profile_min_posts` posts in the manifest
(config; 6), or only `--author`; plus one for `style/self.md` when self cards exist. Wave 2 after wave 1 returns:
one builder owning `style/common.md`, `style/moves.md`, `style/media_habits.md`, `style/exemplars.md`, the
`do_not_reuse` block of `style/lexicon.yaml` and the `style/CHANGELOG.md` entry, with the changelog lines wave 1
returned. Two waves because common and moves derive from the author profiles; a single writer for CHANGELOG and
lexicon.yaml avoids clobbering. Builders quote train and self posts only; heldout reaches them only as numbers via
`profile_stats.py`, enforced by hook. Then `uv run tools/moves_lint.py --json`; problems go back once to wave 2.

## 4f. Leak check and health
`uv run tools/quote_leak_check.py --json`: a heldout 6-gram in any writer-visible file is a stop; the file and
phrase go back to its builder and nothing is reported done until clean. Then
`uv run tools/health_run.py --scope deterministic --write --json`; report green or the failing section by name.
A profile rebuild changes envelopes and base rates, which is exactly what the deterministic checks depend on, so
this is not optional. If heldout posts exist whose oracle control has not run, print the `/eval health` reminder.

## Report
Scope used (flags), cards re-annotated, verified, unverified (with objections), envelope drift (the biggest
movers from CHANGELOG), profiles rebuilt, moves added, merged, aliased, still-uncited seeds, profile version,
lexicon version, leak check, health, prompt files an agent could not complete. Counts come from tool JSON and
agent replies, not memory.

## Boundaries
- Never annotate, verify or build a profile yourself; the value of each artifact is the context that produced
  it (post only; post and card only; verified cards only).
- Never edit post text, the manifest or the split; never read `corpus/heldout/**`, `corpus/ratings.jsonl` or
  `evals/calibration.jsonl` (scripts do); never open a file under `drafts/learn_*/prompts/` or
  `drafts/learn_*/archive/` (heldout text sits inline there for the annotators and verifiers alone).
- Never rewrite a card to apply Deep's correction; hand the correction to an annotator that re-reads the post.
- Verified means the review file says so; green means `health_run.py` says so; clean means
  `quote_leak_check.py` says so.
