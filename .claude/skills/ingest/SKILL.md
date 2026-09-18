---
name: ingest
description: >-
  Ingests reference posts from a CSV, Google Sheet, Markdown or JSON file (plus local media) into the corpus and
  runs the learn phase (stylometry, annotation cards, fresh-context card verification, author profiles, moves,
  deterministic health, a rating offer). Use when Deep says "ingest", "add these posts", "load the sheet",
  "import the references", "add my own posts" or "ingest --self", or has dropped files into corpus/inbox/.
argument-hint: "[path | sheet name/url | --self] [--author X] [--platform linkedin|x]"
disable-model-invocation: true
allowed-tools: Read Write Glob Grep Agent AskUserQuestion Bash(uv run *) Bash(ffmpeg *) Bash(ffprobe *) Bash(pdftoppm *) Bash(sips *) Bash(curl *)
effort: high
metadata:
  skill_version: "1.0"
---

# /ingest

Request: $ARGUMENTS

Project state (versions, counts, health, nags):
!`uv run tools/status.py --brief || true`

## What this is for
Reference posts are the only training signal this project has. /ingest turns a drop of files into the three things
everything else depends on: verbatim post files with a split that never moves, a verified card per post that records
what the post does and why it works (mechanisms, never sentences), and the learned style layer under `style/`
(author profiles, the moves catalogue, the common bar, media habits, exemplars, the do-not-reuse lexicon). `/post`,
the judges and the lineup are only as good as this pass, so every learned claim must cite post ids and every card
must survive a checker that has seen only the post.

Tools run from the project root as `uv run tools/<name>.py ... --json`. Read the JSON they print; if `ok` is false,
stop and show the error rather than working around it. Formats, header synonyms and the Sheet requirements are in
`.claude/skills/ingest/references/formats.md`; the card format and annotator bar are in
`.claude/skills/learn/references/card_spec.md`. Point Deep at formats.md when a source cannot be mapped.

## Stage 1: normalize (one row shape, so nothing downstream cares about CSV quirks)
- No argument: every file directly under `corpus/inbox/` (never `done/`, never `media/`). A path: that file. `--self`:
  Deep's own writing, routed to `corpus/self/` with author slug `self` (pass `--self` to normalize and commit both).
  `--author` and `--platform` pass through to the tool.
- A Google Sheet name or a `docs.google.com` URL: ask once for the tab's "File > Share > Publish to web > CSV"
  URL and fetch it with `curl -L -o corpus/inbox/gsheet_<id>_<date>.csv` (`<id>` is the file id between
  `/spreadsheets/d/` and the next `/`; further tabs: `gsheet_<id>_<tab-slug>_<date>.csv`), then proceed as CSV.
  This is the documented route because it needs nothing but the Bash prefixes in `allowed-tools` above. If this
  thread happens to carry Google Drive connector tools (`search_files` / `read_file_content` /
  `download_file_content` under an `mcp__<drive-server>__` prefix), they are a fine shortcut: save each tab
  verbatim to the same paths and continue identically. Never assume they are there. Never fetch a LinkedIn or
  X URL: that is scraping, and the corpus is user-supplied by design.
- Run `uv run tools/ingest_normalize.py <source> --kind auto [--author X] [--platform linkedin|x] [--self] --json`.
  When `needs` is non-empty, ask one AskUserQuestion that covers everything it needs (author, platform, column
  mapping) and re-run with `--author`, `--platform`, `--mapping '{...}'`. Ask once per source, not once per need.
- `unmapped_columns` go into the report; they are not silently dropped and not silently used.

## Stage 2: commit (dedupe and a sticky split, because heldout posts are the oracle and the lineup fillers)
- `uv run tools/ingest_commit.py corpus/inbox/normalized_<sha>.jsonl [--self] --json`. It dedupes against
  `corpus/manifest.jsonl`, assigns the split once and forever, writes the post files, copies local media, moves the
  source into `corpus/inbox/done/`. Re-running the same source yields 0 new; `skipped`, `variants` and `crossposts`
  are outcomes to report, not problems.
- Remote media. The first run lists `remote_media` it did not fetch. Show the list and ask one question for consent.
  On yes, re-run with `--consent-media` for direct file URLs. `drive.google.com` links: download each with the
  connector's `download_file_content` into `corpus/inbox/media/`, then point the row's `media[].path_or_url` at the
  local file in the normalized JSONL (an intermediate, not corpus text) before committing. LinkedIn, X and twitter.com
  page URLs are refused whatever the consent: they are pages, not files; the post stays text-only and the report
  says to save the media locally because CDN links expire.
- Small-corpus mode. When the output says `small_corpus_mode: true`, the report header says so in one line: "small-
  corpus mode: no heldout split; the oracle is leave-one-out and lineups use train posts". The full split switches
  on by itself once the corpus crosses the configured bar and stays sticky from then on. Do not hide this; it is
  why early lineups are advisory.

## Stage 3: media prep (so annotators look at media instead of guessing from the caption)
`uv run tools/media_prepare.py --post <id> --json` for each ingested post with media (`--all` on a cold corpus).
Previews, keyframes, contact sheets and, when a stream exists, audio land under `corpus/media/<id>/` and
`corpus/frames/<id>/`; the post's `media` entries are updated by the tool. A failure marks the item
`kind: unavailable` and the post stays text-only; list those in the report.

## Stage 4: learn
### 4a. Stylometry
`uv run tools/stylometry.py --corpus --json`: features for every post, heldout ones under `corpus/heldout/features/`.
Cheap, deterministic, and the envelopes need every post, so run it on the whole corpus every time.

### 4b. Cards (`post-annotator`, batches of up to 8 prompt files, all in parallel)
The roster is the tool's. `uv run tools/card_prompts.py build --all-uncarded --kind annotate --json` selects every
post in `corpus/manifest.jsonl` (train, heldout and self) that has no `corpus/cards/<id>.md` or
`corpus/heldout/cards/<id>.md` and writes one self-contained prompt file per post at
`drafts/learn_<date>/prompts/<post_id>.annotate.md`: the post text inside `<untrusted_post>`, the media preview and
contact-sheet paths under `corpus/media/` and `corpus/frames/`, the `profile_version` to record, the spec pointer
and the card output path. Heldout and self posts are carded too: heldout cards feed the lineup fillers and the
oracle from inside the denied path, self cards feed `self.md`. The tool's JSON lists, per post, the prompt file and
the output path; take both from the JSON and never open a prompt file yourself: the heldout text sits inline
there, which is the point. The session-wide `Read(corpus/heldout/**)` deny applies to every agent, so annotators
and verifiers read prompt files instead of posts, and you read neither.
Spawn one `post-annotator` per batch of at most 8 prompt files, all at once (at most 20 concurrent). The delegation
prompt is `prompt_file:` / `output_path:` pairs and nothing else: no ratings, no other cards, no evals, nothing
about what you expect the card to say. Each annotator replies with one line per card, `post_id | archetype |
thesis`, plus any prompt file it could not complete; keep those lines, Stage 5 uses them.
`uv run tools/card_lint.py --post <id> --json` on every new or changed card before a verifier sees it: lint is
mechanical (citations resolve, ids exist, heldout quote cap) and cheap, and annotators have no shell. Problems go
back once to a fresh `post-annotator` with the same pair and the `problems` rows pasted under it; lint runs again.

### 4c. Verification (`card-verifier`, 100% of new or changed cards, fresh context)
`uv run tools/card_prompts.py build --all-uncarded --kind verify --json` writes `<post_id>.verify.md` for every
card that has no current review: the post text, the card inline, the round, and the review output path
`corpus/cards/_reviews/<id>.md` or `corpus/heldout/cards/_reviews/<id>.md`; `--post <id>` rebuilds one after a
rewrite. One `card-verifier` per batch of at most 8 prompt files, in parallel, with `prompt_file:` / `output_path:`
pairs only. The verifier checks that every citation resolves and supports its claim, that every device, archetype,
angle and hook-type id is right at the cited lines, and that the thesis is a fair reading (sarcasm not taken
literally). It returns objections, never rewrites. A card with objections goes back once: `uv run
tools/card_prompts.py build --post <id> --kind annotate --json` again (the new prompt file inlines the review's
objections; annotators cannot open reviews), a fresh `post-annotator` rewrites the card, lint runs, then `--kind
verify --post <id>` and a fresh verifier. Still objected: the card keeps `verified: false`, profile-builders ignore
it, and the report lists it under unverified with the objection.
The review file is the record of verification. Mirror its `verified` value onto the card's front matter with a
one-line edit where you can read the card (train, self); heldout cards keep the review as their record. The value
always comes from the review, never from your own reading of the card.

### 4d. Envelopes
`uv run tools/profile_stats.py --write --json`: per-scope envelopes, function-word centroids and base rates into
`style/profile.json` with a new `profile_version`; the previous version is kept as `style/profile.p<N>.json`.
The swap is direct, so the deterministic health run in 4f is the check on it.

### 4e. Profiles (`profile-builder`)
Wave 1, in parallel: one builder per author touched by this ingest whose post count in the manifest is at least
`corpus.author_profile_min_posts` (config; 6), owning `style/authors/<slug>.md`; plus one owning `style/self.md`
when self posts changed. Wave 2, after wave 1 returns: one builder owning `style/common.md`, `style/moves.md`,
`style/media_habits.md`, `style/exemplars.md`, the `do_not_reuse` block of `style/lexicon.yaml` and the
`style/CHANGELOG.md` entry. Two waves because the common bar and the moves are derived from the author profiles,
and one writer for CHANGELOG and lexicon.yaml avoids two agents clobbering the same file.
Each prompt names the files the builder owns, the post ids in scope, the spec path, and for wave 2 the changelog
lines wave 1 returned. Builders quote train and self posts only; heldout reaches them only as numbers through
`profile_stats.py`, enforced by hook. Authors below the threshold get no profile and feed common and moves only.
Then `uv run tools/moves_lint.py --json`; problems go back once to the wave-2 builder.

### 4f. Leak check and health
`uv run tools/quote_leak_check.py --json`: any heldout 6-gram in a writer-visible file is a stop; the file and phrase
go back to the builder that owns the file, and nothing is reported as done until it is clean.
`uv run tools/health_run.py --scope deterministic --write --json`: the rubric's deterministic checks against the new
profile and lexicon. Report green or the failing section by name. New heldout posts need their oracle control and
lineup control (judge scope) before they join the filler pool; that is `/eval health`, so print the reminder with
the ids when any heldout post is new.

## Stage 5: confirm with Deep (a misread card would propagate into moves and profiles)
From the annotator replies, show one line per new post: `post_id | archetype | thesis`. Then one question for the
batch, not one per post: which ids are wrong, with a one-line correction each, or "all good". A "no" sends the
card back to a fresh `post-annotator`: `uv run tools/card_prompts.py build --post <id> --kind annotate --json`
again, then the pair with Deep's correction verbatim under it; the rewritten card is linted and verified again.
Never rewrite a card yourself; the correction must be applied by an agent that re-reads the post.

When the last card is settled, archive the learn prompt files: `uv run tools/card_prompts.py archive --json` moves
`drafts/learn_<date>/prompts/*` to `drafts/learn_<date>/archive/`, so no later agent can find heldout text there
(`quote_leak_check.py` ignores `drafts/learn_*` by design; the archive is what keeps that safe).

## Report
A table with: rows read, ingested, skipped, variants, crossposts; train, heldout, self counts per platform; media
prepared and unavailable; transcripts available; non-English posts (English-only features are null for them);
authors with fewer than 4 posts, flagged low confidence; cards written, verified, unverified (with objections);
profiles rebuilt; moves added, merged, still-uncited seeds; profile version; lexicon version; leak check; health;
warnings (unmapped columns, refused URLs, prompt files an agent could not complete). Then one line:
`Added N posts (a LinkedIn, b X). Profile pK. Health green. Want to rate them now? /rate corpus`
Counts come from tool JSON and agent replies, not from memory.

## Boundaries
- Never scrape or fetch a LinkedIn or X page; the corpus is what Deep supplies.
- Never edit text under `corpus/`, never move files there by hand (the tools own the manifest and inbox), never
  create a post file yourself.
- Never read `corpus/heldout/**`, `corpus/ratings.jsonl` or `evals/calibration.jsonl`; the scripts read them for
  you and settings deny them to you. Never open a file under `drafts/learn_*/prompts/` or `drafts/learn_*/archive/`
  either: those carry heldout text inline for the annotators and verifiers, and only they may read them.
- Never annotate, verify or build a profile yourself, even for one post: the card must come from a context that
  saw only the post, the check from one that saw only the post and the card, and the profile from one that saw
  only verified cards. If an agent reports a prompt file it could not complete, report it; do not do its work in
  this thread.
- A card is verified only if its review file says so; health is green only if `health_run.py` says so; a leak check
  is clean only if `quote_leak_check.py` says so. Do not summarize a result you did not compute.
