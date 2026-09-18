---
name: persona
description: Interviews Deep to build or edit style/persona.md (who he is, fact bank, story bank, can/cannot claim, opinions, voice and platform choices) and collects his own first-person writing into corpus/self so the system writes in his register instead of the reference authors'. Use when Deep says "set up my persona", "update my persona", "add a story", "add facts I can use", "add my writing samples", or /persona.
argument-hint: "[edit] [--samples path]"
disable-model-invocation: true
allowed-tools: Read Write Edit Glob AskUserQuestion Agent Bash(uv run *)
effort: high
metadata:
  skill_version: "1.0"
---

# /persona

Request: $ARGUMENTS

Project state (versions, corpus counts, self-sample count, nags):
!`uv run tools/status.py --brief || true`

## What this is for
Two files that the rest of the system cannot work without:
- `style/persona.md`: the only source of first-hand claims, numbers, customers, incidents, stories and opinions a post may carry. Writers may borrow mechanisms from the reference corpus; every *what* comes from here. A fabricated anecdote fails `persona_fit` (a hard gate) and cannot be rewritten into truth, so a thin persona means thin posts, and an inaccurate one means posts Deep cannot stand behind.
- `corpus/self/` plus `style/self.md`: Deep's register. Without self samples `register_match_self` is N/A, the envelope check falls back to the lens author, and every run drifts toward the reference authors, which is the exact failure this project exists to avoid. Register comes from any first-person writing, counted by words (target >= 1500, config `corpus.self_min_words`), not by published posts, because a brand built from scratch has none.

Read `references/interview.md` before the interview: it holds the question bank per section, why each question matters, and what a good answer looks like.

## The interview
Goal-level, not a script. Batches of one to three `AskUserQuestion` calls, each batch covering one section; free text for facts and stories, options for choices. Skip what Deep has already answered, follow up when an answer is generic ("we do AI for sales" is not a fact; "we rerun 1,214 extraction jobs a week" is). Stop a section when it has enough to be useful, not when the question bank is exhausted. Expect 10 to 15 minutes; say so up front.

The bar for an entry: a stranger could use it as a receipt in a sentence without asking a follow-up. Numbers non-round and dated; customers and tools named where Deep is allowed to name them; stories first-hand and dated. Ask "can this appear in public under your name?" for anything about a customer, an employee or a number that might be confidential; a fact Deep cannot publish belongs in `cannot_claim`, not in the fact bank.

Sections and the front matter keys the tools read (`platform_check.py` reads `platform_choices`; `judge-persona` applies `can_claim`, `cannot_claim`, `do_not_target` verbatim; `media_check.py` reads `name`, `aliases` and `brands` to tell Deep's own brand from a third-party one in a visual):

```yaml
---
schema: postsmith.persona/1
name: Deep Dave
updated: 2026-09-17
platform_choices:
  linkedin: {hashtags_max: 0, emoji_max: 0, long_posts: true, cta: false}
  x: {premium: false, long_posts: false, hashtags_max: 0, emoji_max: 0, one_liners: true}
can_claim:            # append-only, 1-indexed; candidates cite "persona.can_claim#4"
  - "..."
cannot_claim:
  - "..."
do_not_target: []     # people, groups, companies posts never punch at
brands: []            # Deep's own brands allowed to appear in generated visuals (media_check.py exempts them)
aliases: []           # other spellings of his name a visual may carry
---
```

Markdown sections, in this order and with these exact headings, because `angle-scout`, writers and `run_next.py` address entries by heading slug and position (`persona.fact_bank#3` is the third fact-bank entry, `persona.story#2` the second story, `persona.opinions_held#2`, `persona.cannot_claim#1`), so every list is append-only and numbered in order:
`## Who I am and what I see daily` · `## Fact bank` (entries `- F1 (YYYY-MM): fact | source: where it comes from | public: yes`) · `## Story bank` (entries `- S1 (YYYY-MM-DD): first-hand story in 2-4 sentences | used_in: []`; `/post` fills `used_in` so nothing repeats within 60 days) · `## Claims` (the rules behind the two front-matter lists) · `## Opinions held` · `## Opinions refused` · `## Lane and audience` · `## Voice choices` (one row per divergent trait in `style/common.md`; when that file does not exist yet use the default trait list in `references/interview.md`) · `## Vocabulary` with `### Words I use` and `### Words I never use` · `## Comfort levels` (self-deprecation, profanity, punching at companies; mirrors `do_not_target`) · `## Lens preferences` · `## Platform choices` (prose behind the front matter, plus cadence) · `## Media` (phone photo, on camera, real screenshots of his own tools) · `## Never` (left empty; `/rate` appends here on a confirmed `not_me` tag).

Proven angles do not live here; they live in `memory/topics.md`, because this file is read by writers and judges and must never carry rating-derived data.

`edit` mode: read the existing file, ask which sections to revisit, and change only those. Every numbered list (`can_claim`, `cannot_claim`, fact bank, story bank, opinions) is append-only because candidates and scores cite entries by number; to retire one, replace its text with `RETIRED: <text>`. The `used_in` lists and `## Never` are machine-maintained and must survive an edit untouched. Bump `updated` so the file's history is legible.

## Self-writing samples
Collect after the interview (or on `--samples <path>` alone). Anything first-person Deep wrote himself counts: Slack and WhatsApp messages, emails, memos, past posts, internal docs. Before pasting, Deep strips names of private individuals and anything under NDA, because the sample is stored in the repo and may be quoted in `style/self.md`. Machine-written or heavily edited-by-a-model text is excluded; it would teach the system a model's register.

Then the 20-minute exercise: pick three train posts from `corpus/posts/` (different authors, at least one X post, none longer than ~1,200 chars) and ask Deep to rewrite each in his own words, as he would say it to a peer. The rewrite is a register sample and a paired diff against the original; its content is never a receipt, so its block carries `rewrite_of: <post_id>` and nothing in it enters the fact bank. Skip the exercise when the corpus is empty and say so.

Storage and ingest: write pasted text to `corpus/inbox/self_<date>.md` as `---`-separated blocks, each with `author: <persona name>`, `platform: linkedin|x` (the platform it would have been posted to; long prose is `linkedin`), `posted_at:` when known, and `rewrite_of:` for exercise blocks. A file path from `--samples` is passed as is. Then `uv run tools/ingest_normalize.py <source> --self --json`; when the result's `needs` is non-empty, ask once and rerun with `--platform`/`--author`/`--mapping`. `rewrite_of` is not a canonical column, so ingest lists it under `unmapped_columns` and ignores it; that is expected, do not remap it. Then `uv run tools/ingest_commit.py <normalized.jsonl> --self --json`. Self posts are never held out and get ids `self_<nnn>`. Sum `text_stats.words` over `corpus/self/*.md` and report the total against 1,500 and the sample count against 5 (`corpus.self_min_samples`) and 8 (the `/status` target); below the bar `/post` prints "voice anchor: weak" and says why.

Features and the self envelope: `uv run tools/stylometry.py --corpus --json` then `uv run tools/profile_stats.py --write --json` (the same calls `/ingest` makes; the previous profile is kept as `style/profile.p<N>.json`).

Then spawn one `profile-builder` agent to write `style/self.md` from `corpus/self/*.md`, `corpus/features/self_*.json`, the `self` scope of `style/profile.json` and `style/common.md` (when present): register fingerprint in the author-profile shape minus moves, "what Deep does that the references do not", "what the references do that Deep never does", and for each `rewrite_of` pair what changed between the original and Deep's version. It quotes self posts only. It receives paths, not pasted text, and nothing under `corpus/heldout/`.

## Finish
Print: sections filled with entry counts (fact bank >= 5 and stories >= 3 is the working minimum), `can_claim`/`cannot_claim` sizes, self samples and words against the bars, and the next command (`/post <topic>` when the bars are met; otherwise what is still missing and how to add it: `/persona --samples <path>` or `/persona edit`).

## Boundaries
Never invent an entry, round a number, or fill a gap with something plausible; an empty section is honest and `/post` asks for a true detail when it needs one. Never read `corpus/heldout/`, `corpus/ratings.jsonl` or `evals/calibration.jsonl`. Never write outside `style/persona.md`, `style/self.md`, `corpus/inbox/`, and what the ingest tools write. Nothing here posts anywhere.
