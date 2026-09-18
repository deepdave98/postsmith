# postsmith

postsmith writes LinkedIn and X posts in your voice, learned from posts you admire, graded by judges that never see what the writer meant. You paste the result yourself.

## Why

Frequency compounds. Buffer's within-account regression over 2M posts from 94K accounts found that posting more often raises impressions *per post* with no ceiling: 2 to 5 posts a week is worth about +1,182 impressions per post, 6 to 10 about +5,001, 11 or more about +17,000. Volume is the game, and volume is what a language model is for.

Both platforms have priced that shortcut. LinkedIn added a "Seems like AI slop" flag in July 2026; a million members used it within two weeks and flagged content gets about 40% fewer views. Originality.ai read 5,000 long-form public LinkedIn posts that month and called 81.2% likely machine written, up from 53.7% in January. X open-sourced its ranker: a like scores +0.5, a mute -58.8, a report -234.0. One reader who finds you tedious cancels roughly a hundred who did not. Your second post in a viewer's batch is scored at half and everything after at a quarter (`AuthorDiversityDecay 0.5`, `AuthorDiversityFloor 0.25`), so cadence without quality is self-cancelling. Free X accounts sit under 100 median impressions and 0% median engagement (Buffer, 18.8M posts).

Generic model output is not neutral on these feeds. It is negative.

## Why "write me a LinkedIn post about X" fails

Three reasons, all structural.

A model cannot judge its own output. The context that wrote the post knows what it meant and grades the intention. The feed only gets the text.

Style transfer without a fact source produces confident lies. A model told to sound like you needs specifics and will invent yours.

A single grader paired with a single writer converges. The grader learns to pass its own writer and the bar drifts down every round.

postsmith is an evaluation harness that happens to write posts. Generation is the cheap part.

## Architecture

Six stages. Each is separated from the next because each one corrupts the next if it is not.

**Ingest.** Drop CSV, Markdown, JSON or a published Google Sheet into `corpus/inbox/` with local media and run `/ingest`. `ingest_normalize.py` maps synonym headers into one row shape. `ingest_commit.py` dedupes by content hash and assigns a split that is sticky forever: `sha256[:8] % 4 == 0` sends a post to `corpus/heldout/`, the pool the Turing lineup later draws from. `media_prepare.py` runs before anyone reads the post, so an annotator looks at the picture instead of guessing from the caption: `ffprobe` dimensions and duration, keyframes at 0/25/50/75/100%, up to 8 scene-change frames, a 3x3 contact sheet.

**Learn.** `card_prompts.py` writes one self-contained prompt file per post, so the annotator never opens a post file. The annotator returns a *card*: thesis, archetype, hook type, beat function, what each turn set up and broke, devices at line numbers, the role of the media, every claim cited to a line. A verifier in a fresh context that has seen only the post and the card checks each citation at the cited lines and returns objections, never replacement text. A card whose review says `verified: false` is invisible downstream. `stylometry.py` measures every post (sentence-length CV, function-word frequencies, punctuation per 1k chars, specificity per 100 words) and `profile_stats.py` turns those into per-scope envelopes, centroids and base rates. `profile-builder` agents convert verified cards into the style layer: per-author profiles, `style/common.md` (what at least 70% of profiled authors do, which is the bar), `style/moves.md`, six rotating exemplars and the do-not-reuse phrase list. A move is a mechanism plus a trigger plus a shape plus an `execute_without_copying` note, with at least two `seen_in` post ids; `moves_lint.py` enforces the two. Writers read this layer. They never read a card.

**Write.** `/post <topic>` runs `angle-scout`, which returns the 5 to 8 obvious takes, persona facts and opinions cited by line, a story-bank match, and live specifics with URLs. Writers must avoid the obvious takes and judges never see them. `matrix.py` then deals each writer a distinct row of angle family, archetype, move, device and author lens from a seed, so diversity is structural rather than a temperature setting. Writer 1 is lens-free and one slot is always the short deadpan option. Each writer generates 8 to 10 candidate angles inside its family, scores them 1 to 5 on surprise, truth, specificity, personal fit, timeliness and disagreeability, kills anything under truth 4 or on the obvious-takes list, then writes one LinkedIn post and one X post. They are never the same text reflowed. Every checkable claim is declared with its source: a persona section and line, a numbered brief fact, a detail you supplied, `opinion`, or `joke`. Nothing sources to the reference corpus, which teaches only *how*.

**Grade.** Three tiers, in cost order.

Tier 0 is Python and runs in seconds, because most failures are cheap. `tier0.py` composes platform limits and fold behaviour, hashtags, links and emoji (`platform_check.py`, `xcount.py`), the AI-tell lexicon and pattern checks (`ai_tells.py`), dash density, burstiness and broetry against the corpus envelope (`envelope_check.py`), and word-level overlap (`overlap_check.py`). Six words shared consecutively with any corpus post is a flag, eight is a fail, and so is a 40-character common substring. The same test runs against `memory/published/`. Tells are base-rate aware: a pattern the corpus itself uses more than 25% of the time is downgraded, because a rule your references break is not a rule. Hard failures go back to the writer with the offending span quoted.

Tier 1 sends each survivor to four narrow judges: reader (clarity, substance, hook, regret risk, reply worthiness), voice (register match against your own writing, level and move, not-AI, platform register), comedy (humor, uniqueness, emotion), persona (persona fit, claim classification). Each is a fresh subagent that opens one generated prompt file holding the candidate inside `<untrusted_post>` tags, plus the rubric and its anchors, and nothing else. Scores are integers 1 to 5, each carrying a quote copied verbatim from the candidate. `judge_io.py` matches every quote against the text, forgiving case, quote marks, dashes and whitespace and nothing more, and discards the whole dimension when none matches, so an approximate quote costs the judgment rather than a point. A soft score exactly one under its threshold, a hard dimension at its trigger, a hold, a skeleton flag, or a check with a known false-positive history sends that one dimension to a jury of three fresh judges drawn from the other lenses. The median decides.

Tier 2 tests whether the finalist survives contact with a human. `lineup.py` picks three heldout posts near the candidate on platform and length, from three different authors, strips handles, names and domains from all four, shuffles them under an opaque build token, and asks three judges which of A to D is machine written. Two picks at confidence 4 or higher, or a clean sweep, and the finalist dies. Then `pairwise.py` finds the two exemplars this writer actually saw and asks whether the candidate is that skeleton or that joke rewritten. One yes is a hard fail. A move can be borrowed. A skeleton cannot. Unsourced claims are verified against the web here. Only `aggregate.py` writes `merged.json`, so the word `pass` has exactly one author in the system. There is no blended score anywhere: every check is atomic, quoted and reported separately.

**Deliver.** `assemble_report.py` writes `final/`: one file per variant with the exact paste text, a media block when media earns its place, `clipboard.md`, `report.md`, `lineage.json` and `blind.json`.

**Calibrate.** Verdicts stay collapsed until you run `/rate blind`, which shows the lettered, shuffled, verdict-free texts in `blind.json`. A rating taken after you have seen PASSED inherits the judge's opinion and measures nothing. Every 20 ratings, `calibrate.py` reports Cohen's kappa and Spearman rho against the judges, per-tag false-negative rates, and proposals in a fixed order: user tell, then anchor, then threshold, then anchor text. Rubric versions are immutable; a change writes `v<N+1>` and health promotes it. `/posted` stores the text you actually published, diffed against what was delivered, and later the metrics in plain words.

## Isolation

The interesting engineering is what each component cannot reach. Per-agent allow and deny lists in the agent front matter are enforced by `PreToolUse` hooks (`.claude/hooks/guard_paths.py`, `guard_writes.py`).

Writers are denied `corpus/heldout/`, cards, features, ratings, everything under `evals/`, memory and every score file. A writer that can read the lineup pool writes toward the test. Writer prompt files are named `writer-<n>.<token>.md` with an opaque per-writer token, so one writer cannot construct a sibling's path and read the feedback packet written about another candidate.

Judges are allowed their own prompt file and the rubric. Not the brief, not the writer's reasoning, not the previous round, not another judge's file, not a lineup or blind key. The persona judge is denied `style/persona.md` itself and grades against the excerpt the prompt carries. Blocked attempts are logged, and `judge_sanity.py` reads that log, so a judge that reached for the corpus counts as contamination even though the read was blocked.

The orchestrator can spawn, route and report but cannot write a character of candidate text. By mid-run it has seen feedback packets and score tables, and an orchestrator that edits a candidate is a generator that has read the answer key. The one component allowed to touch post text is the one with the least information.

## What it will not do

It never posts and never logs in. There is no write path to either platform.

It never scrapes. The corpus is what you supply, and `/ingest` refuses LinkedIn and X page URLs whatever consent you give.

It never invents a fact. A candidate whose only failure is a claim you alone can confirm is delivered under `needs_your_call` with the claim named, not rewritten into a safer one, because that edit is yours.

There is no API key and no external service. Every model call is a skill or subagent inside Claude Code, so a run costs session tokens and wall time. A default run is 3 writers producing 2 candidates each, 4 judge calls per candidate per round, juries as triggered, up to 3 rounds, then a lineup and a paraphrase gate on the top finalist per platform, at up to 20 concurrent subagents. `--quick` is 2 writers and 2 rounds. `--wide` is 5 writers and 2 Tier 2 finalists per platform. The numbers live in `config/postsmith.yaml`.

## Getting started

Requirements:

- Claude Code. The skills under `.claude/skills/` and the agents under `.claude/agents/` are the runtime; nothing here runs as a server.
- Python 3.12 or later and `uv`. Every tool runs as `uv run tools/<name>.py ... --json`.
- `ffmpeg` and `ffprobe` if your references carry video.
- Optional: `pdftoppm` for PDF carousels, and `sips` (macOS) if any reference image is HEIC or HEIF.

Setup:

1. `uv sync --all-groups`
2. Open Claude Code in this folder.
3. `/persona`. A 10 to 15 minute interview that writes `style/persona.md`: fact bank, story bank, what you can and cannot claim, opinions, platform choices. It is the only source of first-hand claims a post may carry. It also collects samples of your own writing into `corpus/self/`, which are never held out.
4. Drop reference posts into `corpus/inbox/` and run `/ingest`.

Three commands carry the loop:

| Command | What it does |
|---|---|
| `/post <topic> [--lens slug] [--platform both\|linkedin\|x] [--quick] [--wide] [--no-media] [--copy]` | topic to paste-ready LinkedIn and X text, with a media prompt and the full evidence table |
| `/rate blind [run]` | shows the delivered texts unlabelled and records your 1 to 5 and tags before any verdict is revealed |
| `/posted <draft-id> <li\|x> [url]` | stores the text you actually published, diffs it against the draft, and later takes metrics in plain words |

`/ingest` adds references. `/trending [area]` finds topics in your lane. `/status` shows what is unrated, unmeasured or stale. `/eval <file> --platform li|x` scores arbitrary text and `/eval health` self-tests the graders. `/learn` rebuilds the style layer after a taxonomy change. `/media` rebuilds a media brief. Asking in plain chat to tighten or shorten a line you wrote yourself runs the `voice` skill, which is not a command.

| Path | Holds |
|---|---|
| `.claude/` | skills, agents, and the two hooks that fence every read and write |
| `config/postsmith.yaml` | fan-out, jury rules, thresholds and platform limits, each with a source and a `verified_on` date |
| `corpus/` | reference posts, the heldout split, your own samples, cards, features, media, frames |
| `style/` | persona, self, author profiles, `common.md`, the move catalogue, exemplars, lexicon, envelopes |
| `drafts/<date>_<slug>/` | one run: brief, matrix, every prompt file, candidate, score, Tier 2 key and final |
| `memory/` | lessons, topic history, performance, the live text of everything posted |
| `evals/` | rubric versions and anchors, thresholds, golden sets, health reports, calibration |
| `tools/` | the deterministic Python, each script with `--help` and `--json`, tests under `tools/tests/` |
| `docs/design/contracts.md` | authoritative for every CLI, schema and path. Code that disagrees is the bug |

## Limits

A small corpus makes a weak envelope. Under 24 train posts, or under 6 on a platform, small-corpus mode holds: no heldout split, lineup fillers come from the train pool and the lineup is advisory, and the envelope checks widen to 1.5 IQR and report as advisory. Every report header says so, because it changes what the verdict is worth.

The judges are calibrated against you, not against the world. Kappa is withheld until 30 ratings exist with at least 8 rated system failures among them, and verdicts stay advisory until it clears 0.4. Until then, treat a `pass` as a filter that caught the obvious failures, not as a prediction that the post will work.

Authors with fewer than 6 posts get no profile. With fewer than 5 self samples the voice gate has no anchor and every run drifts toward the reference authors, which the header prints as `voice anchor: weak`.

Claim verification depends on a live search tool. Without one, those claims come back `needs_check` and land in your lap.

The platform numbers above are dated. They sit in `config/postsmith.yaml` and `docs/design/research-*.md` with sources and `verified_on` stamps because they will rot, and a ranker constant that changed six months ago is worse than no constant at all.
