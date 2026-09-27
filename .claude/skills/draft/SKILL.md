---
name: draft
description: Writes one paste-ready post fast, in a chosen mode (funny or insightful), from the learned style files, then runs one pass of checks and hands over the text plus a meme prompt. Use when Deep says "give me a post on X", "funny post about X", "insightful post like this one", "restructure this post", "hawkins style", or pastes a post and asks for his version. Minutes, not hours. /post stays for the full tournament.
argument-hint: "<topic | pasted post> [funny|insightful] [li|x|both]"
allowed-tools: Read Write Agent WebFetch WebSearch Bash(uv run *)
metadata:
  skill_version: "1.0"
---

# /draft

Request: $ARGUMENTS

## What this is
One post, one pass, about five minutes. You write it yourself, with the learned files open on the desk. Deep
asked for this on 2026-09-20 after two full `/post` runs produced nothing he could publish: the tournament
optimised for rejection and a from-memory draft missed the lens author's signature move. This is the middle.
Ingestion decides how the post is built. A short list of checks decides whether it ships. Nothing loops.

## Mode picks the lens
- `funny`: `style/authors/james-hawkins.md`. He is the primary target. Pick one archetype he actually uses
  (escalation_ladder, screenshot_commentary, one_liner) and say which.
- `insightful`: `style/modes/insightful.md` when it exists. Until it does, the structural reference is the
  example Deep pasted (skeleton only, never wording) plus `style/common.md`, and the output says
  "insightful lens: thin" so he knows the draft leaned on one example.
- No mode given: infer it from the topic, say which you chose, carry on.
- No topic given, insightful mode: `memory/insightful_topic_bank.md` holds scouted topics with scores, the other
  side's best argument and facts already opened at source. Pick one not marked used, re-open each URL you quote
  (facts go stale), mark it used. When the bank is older than about 30 days, scout again before drafting.

## New examples keep the lenses honest
When Deep pastes a post he likes and calls it funny or insightful, file it: a Markdown block in `corpus/inbox/`
with `mode:` set, then the `/ingest` stages (normalize, commit, card, verify, mode profile rebuild). A mode profile
states a habit only when two posts share it, so one odd example cannot bend the lens; it waits under "Seen once"
until a second post agrees. That is what keeps quality steady as the pile grows.

## Before writing, read
`style/persona.md` (voice choices, the never list, `cannot_claim`, `do_not_target`), the lens file,
`style/moves.md` (pick one move, name it), and the lens author's `do_not_reuse` block in `style/lexicon.yaml`.
No default personal angle: a personal line goes in only when Deep asked for one. Invention nobody would bank on
is allowed and stays deadpan. Invention pinned on a real named third party is not.

## Write
LinkedIn and X unless told otherwise. X is its own post, not LinkedIn with the breaks removed. Line 1 must
leave a question open; a specification is not a hook. Restructuring a pasted post: keep its skeleton, replace
every sentence.

## Then check, once, in this order
1. **Lens conformance.** Walk the lens file's checkable rules against the draft and fix misses before anything
   else runs. For Hawkins that means: line 1 leads with the object, not with "i"; the absurd thing is said in
   the vocabulary of the institution it belongs to; none of the six marks he never uses; the pivot is the last
   words; nothing follows the punch.
2. **Tier 0.** Write the draft to `drafts/draft_<date>_<slug>/round1/candidates/e1-li.md` (and `e1-x.md`) with
   golden-style front matter, then `uv run tools/tier0.py <file> --as-golden --lens author:<slug> --json`.
   A hard fail is fixed and rerun. Seconds.
3. **One batch of fresh judges.** `uv run tools/run_next.py draft_<date>_<slug> --json`, spawn the first batch
   in parallel with the five-line delegation `/eval` uses, and stop there. No juries, no rewrite rounds. Reader
   always (the hook gap test, clarity, substance). Comedy when the mode is funny (the eight joke tests).
4. **Claims.** Every number and dated fact is opened at its source with WebFetch before delivery. A false
   figure survived twelve judge passes on 2026-09-20 and was caught only by looking.

## Checks repair, they never cancel
The product is a post. Every note from step 1 to 4 ends one of two ways: it becomes an edit, or it is declined
with a one-line reason (a register check built on seven Slack messages objecting to a flat comic ladder is
declined; a reader who cannot resolve a line is never declined). A claim that cannot be confirmed is cut or
corrected, and the post survives without it. An overlap rewrites its span. A hook with no gap rewrites line 1.
When an edit rewrote line 1 or the line the post turns on, send the new text to the reader judge once more,
one call, because a fix can break what it touched. Two judge batches is the ceiling. Then hand over, always.

## Hand over
Paste-ready LinkedIn. Paste-ready X. One meme prompt or capture direction: most of the corpus attaches
media, and the lens author's habit is a tight crop of a real screen or an obviously fictional parody chart or
UI, never a faked capture of a real product. Then a short list: what the checks changed, what was declined
and why, and anything left open as Deep's call. No score table, no pass or fail label, and never a run that
ends without text he can paste.

## Boundaries
Never open `corpus/heldout/`, `corpus/ratings.jsonl`, `evals/calibration.jsonl` or a `*.key.json`. Judge
output here is advice, not a verdict: `/draft` never says "passed". Only `/post` and `/eval` do, and only
from a `merged.json`.
