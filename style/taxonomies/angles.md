# Angle taxonomy (v1, 2026-09-17)

Source: docs/design/content-quality-bar.md §1. An angle is the thesis a reader could restate in one sentence. Writers pick
one before drafting (the `angle_sheet` in the candidate front matter records the candidates, their scores, the pick and the
runner-up); cards record the angle of every corpus post (`angle:` slug). Ids are stable slugs; `family` ids are
`reveal | receipt | reframe | ridicule | rule` and appear as `assignment.angle_family`.

Pick an angle by asking: (a) what does the reader already half-believe that I can make explicit (revelatory beats contrarian);
(b) what emotion is this for; (c) what do I specifically know or have done that nobody else in the feed does; (d) why now.
Contrarian-for-its-own-sake creates opposition rather than "aha".

## Angles (example topic: "OpenAI ships a new model")

| id | family | definition | works when | example |
|---|---|---|---|---|
| revelatory_reversal | reveal | State the thing people half-suspect, with the mechanism | you can supply the mechanism | "The benchmark jump is real. The reason it won't show up in your product for 9 months is eval debt." |
| name_the_unnamed | reveal | Coin a two-word label for a pattern people feel | the pattern is common and the label sticks | "Call it 'launch lag': the 6-week gap between a model's demo and the day it's usable in production." |
| obvious_unsaid | reveal | Say the plain fact everyone tiptoes around (FINALLY) | true but socially unsaid | "Nobody in our customer base has asked which model we use. Not once. In 18 months." |
| distinction | reveal | Define two things people conflate | the distinction changes a decision | "'Smarter model' and 'better product' are different claims. Only one of them ships." |
| specific_number | receipt | One precise non-round figure carries the post | the number is yours or reproducible | "We reran 1,214 extraction jobs on it. 31 got better. 4 got worse. Here are the 4." |
| personal_receipt | receipt | "I did X, here is what happened," with cost | you did it and can show the artifact | "Switched our pipeline Tuesday. Wednesday's bill: 2.3x. Wednesday's accuracy: same." |
| confession | receipt | An unflattering truth about yourself or your company | true, survivable, you pay | "We told customers our enrichment was 'AI'. For the first 4 months it was me and a spreadsheet." |
| build_log | receipt | Chronological "here's what I did in N hours" with caveats | you built something today | "Ported our classifier at 9am. Green by 11. The two things it broke: ..." |
| field_notes | receipt | Aggregate what you heard from N real conversations | N ≥ 10 | "Talked to 14 data teams this week. Zero have switched. Every one is 'evaluating'." |
| artifact | receipt | Post the artifact (memo, screenshot, dashboard), not its summary | you have the artifact | posting the actual memo, not a paragraph about it |
| second_order | reframe | Skip the obvious consequence; state the consequence of the consequence | you can trace two steps | "Cheaper tokens don't cut our costs. They raise our customers' expectations of what 'done' means." |
| for_narrow_x | reframe | Translate a broad event for one job or company type | you know X intimately | "If you sell data enrichment to RevOps teams, this launch matters for exactly one reason: ..." |
| unexpected_comparison | reframe | Map the event onto a distant domain with a precise structural match | ≥ 2 aligned points | "New model releases are airline seat sales. The headline price is real; nobody flies at that price." |
| historical_rhyme | reframe | "This happened before; here's the one difference" | you can cite the earlier case with a date | "In 2007 every startup 'added maps'. In 2025 every startup 'adds the new model'. Same three outcomes." |
| reframe_the_metric | reframe | The headline number measures the wrong thing; name the right one | you can propose a better metric | "Stop reading the benchmark. Read the refusal rate on your own 50 hardest prompts." |
| pattern_across_events | reframe | Three recent events, one rule | the rule survives the third example | "Three launches, one pattern: the demo uses tools the API doesn't expose for 6 weeks." |
| deflation | ridicule | Describe the hyped thing in flat literal terms | the description is accurate | "A new model shipped. It's the old model, but it argues with you less." |
| escalation_absurd | ridicule | Extend the trend to its logical, ridiculous conclusion | honest about the trend | "At this cadence, by Q3 the changelog will be longer than the model card." |
| who_this_hurts | rule | Name the loser the announcement omits | specific, not cruel | "Great for anyone with a 1,000-GPU eval harness. A tax on everyone else." |
| uncomfortable_tradeoff | rule | Name the trade nobody says out loud, and who pays | you own the trade | "We'll take a 2% accuracy hit for a 40% cost cut. Every customer says no. Every customer's CFO says yes." |
| falsifiable_prediction | rule | A number and a date | you will post the result | "By March, 95% of our tokens will go to tasks no human here ever did. Screenshot this." |
| the_razor | rule | A one-line rule of thumb for deciding | memorable and usable tomorrow | "If a launch demo doesn't show the failure case, assume the failure case is the product." |

## Scoring axes (1-5 each; keys of `angle_sheet.candidates[].scores`)

| axis | question |
|---|---|
| surprise | Would a follower of this topic have predicted it? |
| truth | Is it defensible from a source or the persona fact bank? |
| specificity | Does it carry a number, name, date or artifact? |
| personal_fit | Could only this author say it? |
| timeliness | Why now, in one sentence? |
| disagreeability | Could a smart person argue the other side? |

## Hard kills (values of `angle_sheet.candidates[].killed_by`; null when the angle survived)

| killed_by | rule |
|---|---|
| truth_below_4 | truth < 4 |
| fit_without_receipt | personal_fit ≤ 2 and no receipt (number, artifact, first-hand detail) backs it |
| on_obvious_list | the angle is on the scout's obvious-takes list |
| needs_missing_fact | the angle needs a fact the author does not have (and `--quick` forbids asking) |

## Emotion targets (Puri; `angle_sheet.emotion`, one per post)
LOL, OHHH (now I get it), WOW, WTF, AWW, YAY, NSFW (that's crazy), FINALLY (someone said it). Choose one before writing;
the comedy judge scores `emotion` against this list.

## Procedure (writers run this before drafting)
1. Inputs: topic; persona fact bank and story bank; the emotion list; the assigned family; the scout's obvious-takes list.
2. Generate 8-10 candidate angles inside the assigned family, one sentence each.
3. Score each on the six axes. 4. Apply the hard kills. 5. Pick the top one, record the runner-up, choose the emotion and the
hook family (hooks.md). 6. After drafting, the thesis must still be recoverable from the post in one sentence (rubric clarity).
