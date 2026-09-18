---
name: posted
description: Marks a draft variant as posted by hand, stores the exact live text (as-is or pasted final) and the diff against the draft, and later logs engagement metrics in plain words. Use when Deep says "I posted it", "/posted", "log the LinkedIn one", "it got 12k views", or pastes a post URL after a run.
argument-hint: "<draft-id> <li|x> [url] | <draft-id> <li|x> 12k views 40 comments"
disable-model-invocation: true
allowed-tools: Read Write Edit AskUserQuestion Bash(uv run *)
metadata:
  skill_version: "1.0"
---

# /posted

Request: $ARGUMENTS

!`uv run tools/status.py --brief || true`

## What this is for
The system never posts; Deep pastes by hand, and this is where the loop closes. Two records come out of it: the live text under `memory/published/` (so `O5_published` stops a later run from repeating him, and so ratings and performance attach to what actually went out) and `memory/performance.jsonl` snapshots. The most valuable part is the diff. Deep edits before pasting, and every edit is a preference he did not have to explain: a cut line, a changed ending, a removed em dash. `posted_record.py` stores those as `edit_ops`; three similar edits propose a lesson or a user tell through `/rate`. A record made from the draft text when the live text differs poisons all of that, which is why the first question is always asked.

## How it runs
Resolve `<draft-id> <li|x>` with `uv run tools/draft_id.py <draft-id> <li|x> --json` (returns `{run, cid, platform, path}`); when it returns `ok: false` with `candidates`, ask which one and rerun.

Posting record (`[url]` form, or no url yet): ask one question, "posted as-is? (y / paste final)". On `y`: `uv run tools/posted_record.py <run> <cid> --url <url> --json`. On a paste: write the pasted text exactly as given (line breaks intact, no cleanup) to `drafts/<run>/final/<cid>.live.txt` and run `uv run tools/posted_record.py <run> <cid> --url <url> --text-file drafts/<run>/final/<cid>.live.txt --json`. Without a url, omit `--url`; Deep can add it later with the same command. Then `uv run tools/topics.py add <run> --outcome posted --json` sets the run's row in `memory/topics.md` (the same command `/post` used to add it; never edit the row by hand, so the two skills keep one format).

Metrics (`12k views 40 comments 3 reposts` form; any token like views, likes, comments, reposts, saves, follows marks it): `uv run tools/posted_record.py <run> <cid> --metrics "<the words as typed>" --json`; the tool parses plain words and appends a snapshot with its own timestamp. Metrics can be logged any number of times; 24 hours and 7 days are the useful pair.

Print what the tool wrote: published path, `edited: true|false`, the `edit_ops` in one line each, and the follow-ups: `/rate blind <run>` if the run is still unrated, and `/posted <draft-id> <li|x> <views> views <comments> comments` in a day.

## Boundaries
Never post, never open the URL, never fetch metrics from LinkedIn or X; Deep reads the numbers off the screen and types them. Never tidy the pasted text, and never write it into the candidate file: the draft stays what the judges saw, the live text is a separate record. Never mark a variant posted without Deep saying it was.
