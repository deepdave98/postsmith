# Writer brief: what a `post-writer` receives, what it never receives, and what it must return

This is the contract between `/post` and every `post-writer-<n>`. The orchestrator hands a writer five lines
(prompt file path, platform, its assignment line, output path, `verify: false`); the prompt file is
`drafts/<run>/round<k>/writers/writer-<n>.<token>.md` in round 1 and `writers/rewrite-<cid>.<token>.md` on a
rewrite, and it names the items below. Everything else the writer needs is on disk at the paths listed. The reason
for each item is stated because the writer is expected to use it for that reason and no other.

## 1. What a writer receives and why

| Item | Path | Why it is there |
|---|---|---|
| The brief | `drafts/<run>/brief.md` | Topic, flags, the obvious takes under "Do not write these" (the angle must not be one of them), numbered facts `brief.fact#N` with URLs, the story match by persona id, `brief.user_detail`, moves and topics used in the last 3 runs. Every number in a post traces to this file or to `persona.md`. |
| The assignment | inlined as JSON in the writer's own prompt file under `round<k>/writers/` (`run_next.py` copies it from `drafts/<run>/matrix.json`, which the writer does not open; also on the delegation prompt's third line) | `{angle_family, archetype, move, device, lens, seed, short_deadpan}`. Diversity across writers is by assignment, not by asking one writer for "three versions". |
| Persona | `style/persona.md` | The only source of first-hand claims: fact bank, story bank (with `used_in:`), opinions held and refused, `can_claim` / `cannot_claim`, `do_not_target`, vocabulary use/never, platform choices, media willingness. |
| Deep's register | `style/self.md` | Sentence shape, casing, punctuation, contractions, how he addresses the reader. `register_match_self` is the voice gate; reference authors never override this. |
| The bar | `style/common.md` | Shared traits of the corpus, divergent traits the persona decides, anti-patterns, the corpus envelope. |
| Moves | `style/moves.md` | Mechanisms with `execute_without_copying` notes; the assigned move is executed from here. |
| Lens profile | `style/authors/<lens>.md` (absent for the lens-free writer) | How that author executes moves, rhythm, endings, negative space, do-not-reuse phrases. It informs *how*, never *what*. |
| Exemplars | `style/exemplars.md` | Lettered train-split posts, the only raw reference text a writer sees. Skeletons and devices may be borrowed; wording, claims, anecdotes, coinages and jokes may not, and the candidate's `lineage.exemplars_seen` lists them so Tier 2 can check paraphrase against exactly these. |
| Lexicon | `style/lexicon.yaml` | Tiers of off-limits phrases, stale openers, closers, bait, residue, hedges, `do_not_reuse` per author, `user_tells`. `tier0.py` fails on hits; the writer avoids them at the source. |
| Lessons | `memory/lessons.md`, the last 40 non-RETIRED entries (the prompt names the file) | Distilled from Deep's blind ratings: PREFER / AVOID / FACTS-I-CAN-USE. Tags and cids only, never scores. |
| Taxonomies | `style/taxonomies/{angles,hooks,structures,devices}.md` | Slugs for `angle_sheet.candidates[].family`, `hook_type`, `archetype`, `ending`, `device`. Every slug must exist there (judges and cards use them); `tier0.py` P0 checks only that the required keys are present. |
| Output contract | `.claude/skills/post/references/output_contract.md` and section 4 below | The front matter and file layout the tools parse. |
| Rewrite packet (round ≥ 2) | inlined in the writer's own `round<k>/writers/rewrite-<cid>.<token>.md` inside `<feedback_packet>` (the packet exactly as `aggregate.py feedback` wrote it to `round<k-1>/feedback/<cid>.md`, which the writer does not open) with the previous candidate inside `<previous_candidate>`; only the writer's own | Only failing or flagged checks, each with the judge's quoted span and one-sentence surgical fix, out-of-envelope features with numbers, lineup tells. Instruction: fix these, keep everything that passed; do not change the move or the claims unless `uniqueness` or `persona_fit` failed. |

## 2. What a writer never receives, and why
- `corpus/heldout/**`, `corpus/cards/**`, `corpus/features/**`, `corpus/ratings.jsonl`, `evals/**`,
  `memory/performance.jsonl`, `memory/published/**`: label stores and the answer key. A writer who has seen the
  rubric writes to the rubric; a writer who has seen heldout posts copies them; a writer who has seen published
  text repeats Deep.
- `drafts/*/round*/scores`, `drafts/*/tier2`, `drafts/*/media`, `drafts/*/final`, `brief_inputs.json`,
  `matrix.json`, `run.log`, `state.json`, `memory/topics.md`: verdicts, key files, other runs' passed posts, the
  scout's notes, the rating-derived scoreboard. The only judge output a writer sees is its own packet.
- Other writers' candidates and packets, the obvious-takes list's provenance, which exemplar was "best", any rating.
The `post-writer` hooks enforce this: `.claude/hooks/guard_paths.py` with an allow list of `drafts/*/brief.md`,
`drafts/*/round*/writers/*.md`, `style/**`, `memory/lessons.md`,
the bar, `docs/design/contracts.md` and this references directory, and a deny list that names the label stores,
`memory/topics.md`, `brief_inputs.json`, `matrix.json`, `run.log`, `state.json` and every `round*/candidates`,
`round*/feedback`, `round*/prompts`, `round*/scores`, `tier2`, `media`, `final` and `archive` directory;
`guard_writes.py` allowing only `drafts/*/round*/candidates/r*-w*-*.md` and never a `.txt`. Because the rewrite
prompt inlines the packet and the previous candidate, a writer reads no `candidates/` or `feedback/` file at all,
its own included. A writer also does not open files its prompt did not name, because a Read outside the list is
treated as a leak even when it succeeds; the `writers/` prompt files of other writers in the same run are fenced
by that rule and the hook log rather than by the hook itself (globs cannot tell writers of one run apart). A
delivered run's prompt files are archived under `drafts/<run>/archive/`, outside every allow list.

## 3. Angle discovery (run before drafting)
The procedure is `docs/design/content-quality-bar.md` §1 ("Angle-discovery procedure"), the canonical bar; the
angle ids and families are `style/taxonomies/angles.md`. What the front matter needs from it: 8–10 candidates
inside the assigned `angle_family`, each with `scores` keyed `surprise`, `truth`, `specificity`, `personal_fit`,
`timeliness`, `disagreeability` (1–5) and `killed_by` (null, or the kill rule that removed it: `truth`,
`personal_fit`, `obvious_take`, `missing_fact`); the `pick`, the `runner_up`, one `emotion` (LOL, OHHH, WOW, WTF,
AWW, YAY, NSFW, FINALLY) and one `hook_family` from `style/taxonomies/hooks.md`. Anything failing a quality-bar
gate is regenerated from the angle step, never patched at the sentence level.

## 4. Candidate front matter (contracts §4; `tier0.py` P0 rejects anything missing)
File: `drafts/<run>/round<k>/candidates/<cid>.md`, `cid = r<k>-w<n>-<li|x|x1>` (`x1` is the optional X one-liner).
Front matter, then the post text exactly as it would be pasted, one trailing newline.
```yaml
schema: postsmith.candidate/1
cid: r1-w2-li
platform: linkedin                       # linkedin | x
writer: post-writer-2
round: 1
assignment: {angle_family: receipt, archetype: announcement_with_twist, move: corporate_register_for_trivial_event, device: anti_climax, lens: lara-acosta, seed: 4171, short_deadpan: false}
angle_sheet:
  candidates:                            # 8–10 entries, all inside the assigned family
    - {angle: "...", family: receipt, scores: {surprise: 4, truth: 5, specificity: 4, personal_fit: 5, timeliness: 3, disagreeability: 4}, killed_by: null}
  pick: "..."
  runner_up: "..."
  emotion: OHHH
  hook_family: story_in_medias_res
hook_type: deadpan_announcement          # style/taxonomies/hooks.md
ending: punchline                        # style/taxonomies/structures.md
claims:                                  # every checkable claim: numbers, names, product facts, events
  - {text: "...", source: "persona.can_claim#4"}     # persona.<section>#<n> | brief.fact#N | brief.user_detail | opinion | joke
media_intent: {decision: none, delete_test: "...", genre: null, concept: null}   # decision: none|image|video|real_capture_direction
lineage: {exemplars_seen: [acosta_003], lessons_used: [L-023], rewrite_of: null}  # rewrite_of: previous cid on round ≥ 2
reply_1: null                            # X only: the link or line that goes in the first reply, never in the body
```
- `claims[].source` is the whole claims audit: `judge-persona` classifies each one every round and verifies
  `needs_check` at Tier 2; a claim you cannot source is made unmistakably a joke or cut.
- `media_intent.delete_test` states what the post loses without the visual; "nothing" means `decision: none`.
  A real product (Claude Code, Cursor, a dashboard) is never faked: `real_capture_direction` with what to open,
  type, crop and redact.
- `lineage.exemplars_seen` lists every exemplar letter's post id you read; Tier 2 checks paraphrase against the two
  closest, so omitting one is how a paraphrase slips through and how your variant gets dropped later.
- `reply_1` is optional; P0 checks the required keys only. `assemble_report.py` copies it into the X variant file
  and the clipboard.

## 5. Platform shape
- **X**: the sharpest single idea; the observation or joke is the whole post; ends on the last concrete thing.
  ≤ 280 as X counts (URL = 23, emoji = 2, CJK = 2; `common.x_count`); no hashtags; no link in the body (it goes in
  `reply_1`); the punch word last. Optional `x1` one-liner ≤ 140. A long X post only if the persona opts in and
  the first 280 characters end at a sentence boundary.
- **LinkedIn**: room to set up, never to pad. First line ≤ ~40 characters / ≤ 8 words, one line, could not be
  attached to any other topic; a complete clause ends within 140 characters (mobile fold; 210 desktop); ≤ 3,000
  characters; hashtags and emoji only as `persona.md` allows; no lesson paragraph, no CTA, no "see more" bait.
- **Never the same text.** X is not LinkedIn with the line breaks removed, and LinkedIn is not a tweet padded out;
  `platform_register` scores exactly that.

## 6. The diversity table
`matrix.py` (seeded by the run) gives each writer a row that differs from every other row on at least one axis:

| Slot | angle_family | archetype | move | device | lens | short_deadpan |
|---|---|---|---|---|---|---|
| writer 1 | assigned | assigned | assigned | assigned | none (persona + self + common) | one slot is always `true` |
| writer 2 | assigned | assigned | assigned | assigned | best-fit author, or `--lens` | |
| writer 3 (…5 with `--wide`) | assigned | assigned | assigned | assigned | second best-fit author, or `--lens` | |

- Writer 1 is always lens-free so the pure-Deep voice competes.
- The `short_deadpan: true` slot writes the short, flat option (plain case, no intensifiers, punch last); Deep's
  best posts so far are the short ones.
- Moves used in the last 3 runs and moves with scoreboard mean ≤ 2.5 (n ≥ 3) are excluded; mean ≥ 4 preferred.
  When the catalogue is small the fallback ladder relaxes recency to 1 run → allows a repeat with a different
  device → persona-only assignment; the `rung` is recorded in `matrix.json` and in the report header.
- A writer executes its row. It does not swap the move for one it likes better; the point of the row is that no
  other writer has it.

## 7. Writer boundaries
- No claim, number, customer, incident, or story that is not in `persona.md` or the brief. No borrowed biography.
- No phrase from `style/lexicon.yaml`; no do-not-reuse phrase of any author; no 6+ consecutive words shared with
  any exemplar (`O1_ngram` fails at 8, flags at 6).
- No CTA or engagement bait unless the persona opts in; no moral, summary or restated thesis at the end; no
  explaining the joke; no triad of abstract nouns; no "not X but Y"; no em dashes unless the lens and `self.md`
  both use them; no hashtags on X; no link in an X body; no fake screenshot of a real product.
- One joke beat per ~5 lines on LinkedIn, one per post on X; target self, the system, an abstraction or a powerful
  institution, never juniors, customers or a named person.
- Write only under `drafts/<run>/round<k>/candidates/`, as `r<k>-w<n>-<li|x|x1>.md`; `tier0.py` writes the
  `.txt`, never the writer. Never post, never scrape, never touch LinkedIn or X.

## 8. Reply format
The writer's final message is the candidate paths and one line naming the angle, nothing else:
```
drafts/<run>/round1/candidates/r1-w2-li.md
drafts/<run>/round1/candidates/r1-w2-x.md
angle: <one line>
```
No post text in the reply. The orchestrator must not have the text in its context, because an orchestrator that
can see the text is tempted to fix it, and the hooks cannot stop a fix that happens in a delegation prompt.
