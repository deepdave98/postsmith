# Structure archetypes (v1, 2026-09-17)

Source: docs/design/research-style-method.md A4. A card records one `archetype`; a candidate assignment names one
(`assignment.archetype`); `O3_skeleton` compares archetype + hook type + ending between a candidate and corpus cards.

| id | spine | when it works | notes |
|---|---|---|---|
| hook_reframe_proof_punch | Hook → reframe → proof → punchline, no CTA | the proof is one receipt and the punch is the last beat | the default "head-turning" shape; CTA-less close is deliberate: a CTA is the single strongest "LinkedIn-creator" tell |
| story_arc | Scene → complication → turn → lesson (SLAY: Story, Lesson, Actionable, You) | the scene is real, dated and cost something; the "lesson" is one line, not a paragraph | story openers lead the engagement data; the moralizing closer is where it dies (P12) |
| rude_awakening_story | "I once..." → what happened → what it taught | the unexpected result is concrete | Alić; the fake-vulnerability version ("rejected 47 times") is the slop form |
| listicle | Numbered promise → N items with parallel form → close | the corpus uses it and the items are non-parallel or escalate | Welsh/Cole; trips P17 when every item has the same shape |
| contrarian_take | Consensus → "wrong" → why → what instead | the consensus is quoted fairly and the "why" is a mechanism | second to story openers in the data; creates opposition rather than "aha" |
| screenshot_commentary | Media is the evidence; caption is the angle or joke | the capture is real (`real_capture_direction`) | X-native; `caption_dependency: media_dependent` |
| one_liner | Single observation; ≤ 2 lines | X; the observation is the whole post | best-engagement tweet lengths reported at 71-100 chars |
| escalation_ladder | 3+ items, each escalating, the last breaks the pattern | the break lands on a specific | the comic triple: establish, reinforce, surprise (Allen); the P17 known false positive |
| confession | Self-deprecating admission → the real point | the admission is true and costs something; competence is visible elsewhere in the post | self-deprecation without evidence of competence falls flat |
| announcement_with_twist | News + deadpan or self-undercutting line | founder/launch posts where the twist deflates the announcement register | "thrilled to announce" without the twist is P11/P8 territory |
| trailer_meat_cta | Trailer (promise) → meat (the content) → CTA | annotate it in the corpus; **avoid unless corpus uses it** in generation | Welsh's standard LinkedIn structure; the CTA beat is the tell |
| thread | Multi-post, each post standalone-hooky | X; every unit works as its own 280-char post | no "🧵", "A thread 👇" or "1/" openers (P19) |
| meme_format | Caption + image where the image carries the joke | X; the format is current and the specific inside it is new | `caption_dependency: media_dependent`; media genre `meme` |

## Rhythm notation
Sentences per paragraph, slash-joined, in order (Ship 30): `1/3/1`, `1/5/1`, `1/2/5/2/1` describe crescendo patterns.
Paragraphs are blank-line separated; a one-word line is a paragraph of 1; on X (no blank lines) count sentences per line.
Cards record the actual string (`rhythm: "1/1/5/1/5/1"`); author profiles record the distribution; the voice judge compares the
candidate's rhythm to the exemplars' under `level_and_move`.

## Ending habits (`ending:` in cards and candidates)

| id | what the last beat does |
|---|---|
| punchline | the joke lands on the last line; nothing after it |
| callback | an earlier detail returns in a new context |
| last_concrete_fact | ends on the last specific (a number, a quote, an artifact), no comment |
| deflation | a big setup resolved by a small, literal specific |
| open_question | a question specific to the post's claim (never "Agree?"/"Thoughts?", P7) |
| cliffhanger | ends on an unresolved specific the reader will carry |
| cta | asks the reader to do something; corpus-only, never generated (P7) |
| moral | summarizes or generalizes; corpus-only, never generated (P12) |
