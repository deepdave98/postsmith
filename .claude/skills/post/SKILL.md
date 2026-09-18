---
name: post
description: Writes LinkedIn and X post variants on a topic in Deep's voice using moves learned from the reference corpus, has fresh-context judges score them, sends the failures back for surgical rewrites, and prints paste-ready posts with an optional image or video prompt. Use when Deep says "write a post about", "post ideas on", "draft something on", "give me variants for", "/post <topic>", or picks a topic after /trending.
argument-hint: "[topic] [--lens slug] [--platform both|linkedin|x] [--quick] [--wide] [--no-media] [--copy]"
disable-model-invocation: true
allowed-tools: Read Write Glob Grep Agent SendMessage WebSearch WebFetch AskUserQuestion Bash(uv run *) Bash(pbcopy *) Bash(mkdir *)
effort: high
metadata:
  skill_version: "1.0"
---

# /post

Request: $ARGUMENTS

Project state right now (versions, health, corpus counts, nags):
!`uv run tools/status.py --brief || true`

## What this is for
Posts Deep would be proud to have typed himself: one specific idea, a punch that lands on a detail only he could
know, built on a move from `style/moves.md`, in his own register (`style/self.md`, `style/persona.md`), at the level
of the corpus (`style/common.md`). Output is text Deep pastes by hand into LinkedIn and X. Nothing here posts,
scrapes, or touches either platform.

## Why the shape of this matters
The brand lives in a feed that punishes sameness: LinkedIn down-ranks what readers flag as AI slop, X pays for
replies and a mute wipes a post out. A post that is merely correct and polished has failed. The eval exists to catch
that before Deep does. Your job is to feed it honest candidates, relay its evidence unchanged, and never grade or
patch a post yourself: by the end of a run you have seen feedback packets and score tables, so an orchestrator that
edits a candidate is a generator that has read the answer key. Every boundary below follows from that.

## What "good" means here
Angle before words: the writers find the thing the reader half-believes and make it explicit, with a receipt.
The hook is a specific thing, not a shape. One thesis per post, restatable in a sentence. A claim a smart reader
could dispute. No lesson paragraph, no CTA, no explaining the joke. X gets the sharpest single idea; LinkedIn gets
room to set it up; they are never the same text with the line breaks changed. Deep's best posts so far are not the
long ones, so one assignment is always the short deadpan option. The full bar is `docs/design/content-quality-bar.md`;
writers and judges carry it, you do not apply it by hand.

## What you have and why it matters
- `style/persona.md`: the only source of first-hand claims, numbers, opinions and stories. Writers may not invent
  experience; a fabricated anecdote fails a hard gate and cannot be rewritten into truth.
- `style/moves.md`, `style/common.md`, `style/authors/*.md`, `style/exemplars.md`: mechanisms and the bar. Writers
  borrow moves, never phrasing; `style/lexicon.yaml` lists what is off limits and `tier0.py` catches reuse anyway.
- `style/self.md`: Deep's register. Reference authors supply moves; Deep supplies the texture. `register_match_self`
  is the voice gate, so when `status --brief` says self samples are below the bar, print "voice anchor: weak
  (self n=<n>)" in the header and keep going.
- `memory/lessons.md` (PREFER / AVOID / FACTS-I-CAN-USE, not RETIRED) and `memory/topics.md` (recent topics, moves
  used in the last 3 runs, scoreboard, proven angles): what Deep has already said he likes, what scored, what was
  used recently. Read them before anything else; blind ratings are the only ground truth about his taste.
- `angle-scout`: one agent that returns `drafts/<run>/brief_inputs.json` with the 5–8 obvious takes (writers avoid
  them; judges never see them), persona facts and opinions by line, a story-bank match, 2–4 live specifics with
  URLs when the topic is current, and `needs_user_detail`. It never proposes angles; the writers do that.

## Round 0: the brief
1. `uv run tools/run_next.py init <slug> --topic "<topic>" [--lens slug] [--platform both|linkedin|x] [--quick]
   [--wide] [--no-media] --json` (slug: three or four words of the topic, hyphenated; the tool prefixes the date)
   creates `drafts/<run>/` with the seeded matrix and returns `{"ok", "run", "run_dir", ...}`; `run` is
   `<YYYY-MM-DD>_<slug>` and every later command takes it.
2. Spawn `angle-scout` with: topic, platform, the run id, the output path `drafts/<run>/brief_inputs.json`.
3. If `needs_user_detail` is true and not `--quick`, ask Deep exactly one question with AskUserQuestion: "One true
   detail from your week about this, or 'none'." A second question only if the topic touches a `cannot_claim`.
   Never ask more; never fill the gap yourself.
4. Write `drafts/<run>/brief.md`: topic and flags; obvious takes under "Do not write these"; facts you may use,
   numbered `brief.fact#N` (live specifics keep their URL); the story match by its persona id; the user detail as
   `brief.user_detail` (or "none"); moves and topics from the last 3 runs. Lessons are not copied in: the writer's
   prompt names `memory/lessons.md` directly. The brief is the writers' only window onto this run, which is why it
   carries sources and nothing about judging.

## The loop: `run_next.py` drives it
Repeat until `stage` is `done` or `stopped`:
`uv run tools/run_next.py <run> --json` → `{run, round, stage, actions[], waiting_on[], notes[]}`. Execute every
action in the batch in parallel (Agent calls in one turn, Bash for tool actions, at most 20 concurrent), wait for
all of them, run `run_next` again. The tool derives the stage from what exists on disk, so it is the only memory of
the run: never skip, reorder, add or repeat an action on your own judgment, and never judge a candidate the batch
did not name. A crash costs nothing; rerunning `run_next` resumes where the files stop.

- Agent action → spawn the named agent (`post-writer`, `judge-reader`, `judge-voice`, `judge-comedy`,
  `judge-persona`, `judge-lineup`, `judge-pairwise`, `media-director`, `media-judge`) with a five-line
  delegation prompt and nothing else:
  ```
  prompt_file: <action.prompt_file>
  platform: <linkedin|x>
  lens: <lens id for judges; the assignment line from drafts/<run>/matrix.json for writers>
  output_path: <action.output_path>
  verify: <true only when the action is a claim-verification call; else false>
  ```
  `media-director` is not a judge and its action has no prompt file: it receives the action's `candidate`,
  `inputs`, `output_path` and `prompts_dir` lines instead; every other agent gets the five lines.
  The prompt file path is always the action's: writer prompts are
  `drafts/<run>/round<k>/writers/writer-<n>.<token>.md` (round 1) and `writers/rewrite-<cid>.<token>.md` (rewrites),
  where the token is opaque so one writer cannot name another's file: never reconstruct one, always pass the
  action's `prompt_file` through; Tier 1 and jury prompts are `round<k>/prompts/<cid>.<lens>*.md`; Tier 2 lineup
  and pairwise prompts are token-named under `tier2/` (`lineup_<token>.<lens>.prompt.md`,
  `pairwise_<token>.<slot>.prompt.md`) so their names reveal no cid.
  Name writers `post-writer-<n>` (from the cid) so a rewrite can reach the same writer over SendMessage. Judges get
  no name and no history; each call is a fresh instance, which is what makes the verdict independent.
- Tool action → run the command the action carries, as given. These cover `matrix.py` (assignments, seeded,
  written to `drafts/<run>/matrix.json`), `tier0.py`, `judge_io.py validate`, `aggregate.py`,
  `aggregate.py feedback`, `lineup.py`, `pairwise.py`, `media_check.py`, `quote_leak_check.py`,
  `assemble_report.py`. Their JSON is the evidence; read it, do not restate it.
- Rewrite actions (stage `write` in round ≥ 2): send the five lines to `post-writer-<n>` with SendMessage; if
  resume is unavailable or errors, spawn a fresh `post-writer` with the same five lines and note it in `run.log`.
  The feedback packet reaches the writer only as `aggregate.py feedback` wrote it: `run_next` inlines the packet
  inside `<feedback_packet>` and the previous candidate inside `<previous_candidate>` in
  the rewrite prompt file, so the writer opens no `feedback/` or `candidates/` file and you never
  summarise the packet, soften it, or add "make it better". Rewrites are judged by fresh judges and get a full
  Tier 0 rerun; run_next emits both.
- `waiting_on` non-empty → an action produced no file; re-run that one action once. A second miss is a rejection
  and `run_next` routes it (rerun with another lens, hold, jury) without your help.
- `stopped` → read `notes`. Oscillation (the same dimension failing in consecutive rounds with contradictory fixes,
  or a hard gate that passed then failed after the packet) means the judges disagree with each other: show Deep the
  two suggested fixes verbatim and ask which side to favour, then continue. Any other stop reason goes into the
  report as written.

Stop conditions are encoded in `aggregate.py`, not in you: pass → finalist; three rounds → best attempt marked did
not pass with its table; a fix breaking a passing hard gate twice → dropped; an O1/O5 flag surviving two rewrites →
dropped (that variant is a paraphrase at its core); a candidate failing only on a persona claim → delivered under
"needs your call" with the claim named, never rewritten into a safer claim, because that decision is Deep's.

## Tier 2 and delivery
`run_next` runs Tier 2 on the top finalist per platform (both with `--wide`): the Turing lineup, the exemplar
paraphrase check, claim verification, and unless `--no-media` the media brief and its judge; pairwise ranking is
skipped when the lineup is clean 0/3. The judge-facing Tier 2 files are named by opaque build tokens
(`tier2/lineup_<token>.<lens>.prompt.md` → `lineup_<token>.picks/<lens>.json`;
`tier2/pairwise_<token>.<slot>.prompt.md` → `pairwise_<token>.verdicts/<slot>.json`), each prompt ending with a
nonce the judge must echo; the cid-named `lineup_<cid>.key.json`, `pairwise_<cid>.exemplars.key.json` and
`*.score.json` files are never handed to a judge and never opened by you. Read every path from the action. The
one-judge lineup on every Tier-1-passing candidate is off by default: `run_next` emits it only when config
`run.quick_lineup_on_tier1_pass` is true, and an absent key reads as false; otherwise alternates are reported as
"passed Tier 0-1, not lineup-tested". `.claude/skills/post/references/judge_protocol.md` is the exact protocol.
At `deliver`, `run_next` emits tool actions, in order: `uv run tools/quote_leak_check.py <finalist .txt>` per
finalist (a heldout 6-gram in a finalist is a stop, reported as written), then
`uv run tools/assemble_report.py <run> [--copy]`. Run them as given and print the report's stdout verbatim: it
writes `final/` (per-variant files, `clipboard.md`, `report.md`, `lineage.json`, `blind.json`) and prints the
terminal layout in `references/output_contract.md`. Verdicts are hidden by default: `final/blind.json` holds the
lettered (A/B/C), seed-shuffled, verdict-free texts that `/rate blind` shows, and `report.md` keeps the PASSED /
DID NOT PASS / needs-your-call labels, scores and failing evidence collapsed under "After blind rating" until a
calibration row with `blind: true` exists for the run; while they are hidden you print no verdict, hint at none
and reconstruct none from the files you can read. Then `uv run tools/topics.py add <run> --outcome pass --json`
adds the run's row to `memory/topics.md` (`--outcome skipped` when no variant passed; `/posted` later sets
`--outcome posted` with the same command), mark the used story `used_in:` in `style/persona.md`, and print the
file paths. With `--copy` the top LinkedIn variant is already on the clipboard.

## Header disclosures (never silent)
The first line of the report and of your terminal summary states: rubric and profile versions; `health: green` or
`health: stale for rubric sha …`; `small-corpus mode: lineup uses train posts` when `status --brief` or the
tier0 files say so; `lineup advisory` when the pool could not supply fillers; `voice anchor: weak (self n=…)`;
the matrix fallback rung when `matrix.json` records one; `quick: no lineup, no pairwise` under `--quick`; rounds,
calls and wall time from `run.log`. Each of these changes how much the verdict is worth, so Deep sees them first.

## What judges and writers must never receive
Judges: the brief, `brief_inputs.json`, any candidate's front matter, writer reasoning, feedback history, other
judges' scores, previous rounds, which text in a lineup or pair is human, which candidate is a rewrite, ratings,
memory, key files, the cid of a Tier 2 candidate. Writers: anything under `evals/`, `corpus/heldout/`,
`corpus/cards/`, `corpus/features/`, ratings, scores, any `feedback/` or `candidates/` file (their own packet and
previous text arrive inlined in its own rewrite prompt file), other runs' drafts, `memory/published/`,
`memory/topics.md`. Hooks enforce this; the prompt files are generated by tools so nothing leaks through your
typing. Do not work around either.

## Boundaries for you, the orchestrator
Never write, edit, tighten, reformat or "fix a typo in" candidate text; writers own every character under
`candidates/`. Never paraphrase a judge's evidence when relaying it. Never tell a subagent which text is human,
which candidate is a rewrite, or what a previous round scored. Never open `evals/rubric/`, `corpus/heldout/`,
`corpus/ratings.jsonl`, `evals/calibration.jsonl` or a `*.key.json`; the scripts read them for you. Never hand a
judge anything but the five lines. Never claim a check passed, a lineup was clean or a claim was verified unless
the file under `scores/` or `tier2/` says so.

## Evidence
A candidate passes only if `drafts/<run>/round<k>/scores/<cid>.merged.json` (written by `aggregate.py` alone)
says `verdict.status: pass`. PASSED, DID NOT PASS and "needs your call" labels come from `assemble_report.py`,
never from you. Do not summarise a score you did not compute, and do not round a table into "looks good".

## Output contract (details in `references/output_contract.md`)
`drafts/<run>/final/`: one file per variant with the exact paste text fenced, "why this works" citing moves, the
media block or `real_capture_direction`, `reply_1` for X; `clipboard.md`; `report.md` with every dimension shown
separately and verdicts collapsed under "After blind rating" until `/rate blind <run>` has recorded a blind
calibration row for the run, so Deep's rating does not inherit the judge's; `blind.json`, the lettered verdict-free
texts that rating reads; `lineage.json`. Terminal: finalists first, each fenced exactly as pasted with its
one-line eval header, claims to confirm, and `Rate it: /rate blind <run>` / `Log it: /posted <run> <li|x> <url>`;
then alternates ("passed Tier 0-1, not lineup-tested"), "needs your call", "did not pass" with evidence, paths.
While verdicts are hidden the labels and scores are withheld from the terminal too.

## Flags
`--quick`: two writers, Tier 0 and Tier 1 only, two rounds, no user question, media intent shown but not rendered.
`--wide`: five writers, Tier 2 on both finalists per platform. `--platform`: one platform only. `--lens`: that
author lens for every lens writer (writer 1 stays lens-free). `--no-media`: skip media brief and judge.
`--copy`: pipe the top LinkedIn variant to `pbcopy`.
