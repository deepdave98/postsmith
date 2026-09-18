# Content quality bar

Scope: what separates top-1% tech/AI/startup posts on LinkedIn and X. Sources: Dickie Bush / Nicolas Cole (4A, Tequila test), Justin Welsh (hook formula), Katelyn Bourgoin (contrarian vs revelatory), Shaan Puri (emotion first), Jasmin Alić (specificity, one-line hooks), Lara Acosta (re-hook), George Mack, Greg Isenberg (why now), Sam Parr, Sahil Bloom; 13 deconstructed real posts (Karpathy, Altman, Levie, Bloom, Puri, Bier, Levels, Lütke, Graham, Alić, Bourgoin, Udotong, von Ahn); benign violation theory (McGraw), Dikkers' 11 filters; AuthoredUp (309K posts) and MagicPost (1.18M posts) hook data.

## 1. Angle before words

Top creators pick an angle by asking: (a) what does the reader already half-believe that I can make explicit (revelatory > contrarian); (b) what emotion is this for; (c) what do I specifically know or have done that nobody else in the feed does; (d) why now. Contrarian-for-its-own-sake ranks second to story openers in the data and creates opposition rather than "aha".

Emotion targets (Puri): LOL, OHHH (now I get it), WOW, WTF, AWW, YAY, NSFW (that's crazy), FINALLY (someone said it). Choose one before writing.

### Angle taxonomy (22 angles, 5 families). Example topic: "OpenAI ships a new model."

| Family | Angle | Definition | Works when | Example |
|---|---|---|---|---|
| Reveal | revelatory_reversal | State the thing people half-suspect, with the mechanism | you can supply the mechanism | "The benchmark jump is real. The reason it won't show up in your product for 9 months is eval debt." |
| Reveal | name_the_unnamed | Coin a two-word label for a pattern people feel | the pattern is common and the label sticks | "Call it 'launch lag': the 6-week gap between a model's demo and the day it's usable in production." |
| Reveal | obvious_unsaid | Say the plain fact everyone tiptoes around (FINALLY) | true but socially unsaid | "Nobody in our customer base has asked which model we use. Not once. In 18 months." |
| Reveal | distinction | Define two things people conflate | the distinction changes a decision | "'Smarter model' and 'better product' are different claims. Only one of them ships." |
| Receipt | specific_number | One precise non-round figure carries the post | the number is yours or reproducible | "We reran 1,214 extraction jobs on it. 31 got better. 4 got worse. Here are the 4." |
| Receipt | personal_receipt | "I did X, here is what happened," with cost | you did it and can show the artifact | "Switched our pipeline Tuesday. Wednesday's bill: 2.3x. Wednesday's accuracy: same." |
| Receipt | confession | An unflattering truth about yourself or your company | true, survivable, you pay | "We told customers our enrichment was 'AI'. For the first 4 months it was me and a spreadsheet." |
| Receipt | build_log | Chronological "here's what I did in N hours" with caveats | you built something today | "Ported our classifier at 9am. Green by 11. The two things it broke: ..." |
| Receipt | field_notes | Aggregate what you heard from N real conversations | N ≥ 10 | "Talked to 14 data teams this week. Zero have switched. Every one is 'evaluating'." |
| Reframe | second_order | Skip the obvious consequence; state the consequence of the consequence | you can trace two steps | "Cheaper tokens don't cut our costs. They raise our customers' expectations of what 'done' means." |
| Reframe | for_narrow_x | Translate a broad event for one job or company type | you know X intimately | "If you sell data enrichment to RevOps teams, this launch matters for exactly one reason: ..." |
| Reframe | unexpected_comparison | Map the event onto a distant domain with a precise structural match | ≥ 2 aligned points | "New model releases are airline seat sales. The headline price is real; nobody flies at that price." |
| Reframe | historical_rhyme | "This happened before; here's the one difference" | you can cite the earlier case with a date | "In 2007 every startup 'added maps'. In 2025 every startup 'adds the new model'. Same three outcomes." |
| Reframe | reframe_the_metric | The headline number measures the wrong thing; name the right one | you can propose a better metric | "Stop reading the benchmark. Read the refusal rate on your own 50 hardest prompts." |
| Reframe | pattern_across_events | Three recent events, one rule | the rule survives the third example | "Three launches, one pattern: the demo uses tools the API doesn't expose for 6 weeks." |
| Ridicule | deflation | Describe the hyped thing in flat literal terms | the description is accurate | "A new model shipped. It's the old model, but it argues with you less." |
| Ridicule | escalation_absurd | Extend the trend to its logical, ridiculous conclusion | honest about the trend | "At this cadence, by Q3 the changelog will be longer than the model card." |
| Rule | who_this_hurts | Name the loser the announcement omits | specific, not cruel | "Great for anyone with a 1,000-GPU eval harness. A tax on everyone else." |
| Rule | uncomfortable_tradeoff | Name the trade nobody says out loud, and who pays | you own the trade | "We'll take a 2% accuracy hit for a 40% cost cut. Every customer says no. Every customer's CFO says yes." |
| Rule | falsifiable_prediction | A number and a date | you will post the result | "By March, 95% of our tokens will go to tasks no human at Floqer ever did. Screenshot this." |
| Rule | the_razor | A one-line rule of thumb for deciding | memorable and usable tomorrow | "If a launch demo doesn't show the failure case, assume the failure case is the product." |
| Receipt | artifact | Post the artifact (memo, screenshot, dashboard), not its summary | you have the artifact | (Lütke posting the Shopify memo) |

### Angle-discovery procedure (writers run this before drafting)

1. Inputs: topic; the persona fact bank and story bank; the emotion list; the assigned angle family; the scout's list of obvious takes.
2. Generate 8–10 candidate angles inside the assigned family (one sentence each: the thesis a reader could restate).
3. Score each 1–5 on Surprise (would a follower of this topic have predicted it?), Truth (defensible from a source or the fact bank?), Specificity (number, name, date or artifact?), Personal fit (could only this author say it?), Timeliness (why now, in one sentence), Disagreeability (could a smart person argue the other side?).
4. Hard kills: Truth < 4; Personal fit ≤ 2 without a receipt; the angle is on the obvious-takes list; the angle needs a fact Deep does not have.
5. Pick the top one (record the runner-up), choose the emotion and the hook family before drafting.
6. After drafting, the thesis sentence must still be recoverable from the post in one sentence.

## 2. Sentence-level craft moves (seed for style/moves.md)

1. Coin or adopt a two-word label in the first clause (vibe coding, founder mode, context engineering).
2. Two numbers, same unit, different timeframes; let the reader do the math (1M users in five days vs 1M in the last hour).
3. Non-round numbers beat round ones (1,168 days, 92%, 17 days, $750, 30 enterprises).
4. The receipt sits within one sentence of the claim ("I just met with about 30 enterprises...").
5. Include one caveat that costs you something ("80% yes"; "didn't go 100% smooth").
6. Form demonstrates content (Alić writing the whole post in the first three lines).
7. Line 2 negates the reader's expected answer (re-hook), or flips enemy → hero.
8. Deadpan register: plain case, no exclamation marks, no intensifiers.
9. Describe the hyped thing in flat literal terms ("answers with something a guy wrote on Reddit 8 years ago").
10. Escalate to the logical absurd endpoint, one step past where the reader expected.
11. The self-aware line must also be literally true ("posted my way to the top").
12. Name tools, people, places (Cursor Composer, "Fred", Brian Chesky at a YC event).
13. Rule-of-three with a degraded fourth item ("see stuff, say stuff, run stuff, and copy-paste stuff").
14. Draw a distinction, not an opinion (contrarian/revelatory; founder/manager; prompt/context).
15. Post the artifact, not a description of it.
16. Close the loop with a callback to the hook.
17. Prediction = number + date.
18. First line ≤ ~8 words / ≤ 40 characters and one line long.
19. Delete the first and last 25% of the draft; start at the most interesting moment.
20. One thesis per post, restatable in one sentence.

## 3. Humor that works in tech posts

Theory: benign violation (a norm is violated AND the violation is safe, perceived at once); Dikkers: every joke is a plain opinion passed through a filter (irony, character, shock, hyperbole, wordplay, reference, madcap, parody, analogy, misplaced focus, meta); surprise is the core element; keep a straight face; the specific is funnier than the general.

| Mechanism | How it works | Real example |
|---|---|---|
| deadpan_understatement | alarming fact, flat reaction | "this seems…not good." (Bloom on the Claude blackmail test) |
| deflation | describe the hyped thing exactly as it is | Puri: ChatGPT = "a guy on Reddit 8 years ago" |
| escalation | extend the true trend one step too far | nostalgia for being blackmailed by humans |
| specificity_as_punchline | the odd detail is the joke | "8 years ago"; "SuperWhisper"; "Fred" |
| self_deprecation_with_competence | mock yourself for the thing you are demonstrably good at | Bier: "posted my way to the top" |
| obvious_unsaid | the laugh is recognition | Karpathy admitting expert coding is "vibes" |
| rule_of_three_twist | two parallel items, third breaks the pattern | "...and copy-paste stuff" |
| incongruous_comparison | map tech onto a mundane domain with two aligned points | airline seat sales |
| confession | admit the unglamorous truth with numbers | "two guys surviving on pizza" |

Falls flat: puns without an opinion underneath; laughing at your own joke ("lol", 😂, "haha", "jk"); forced memes; dad jokes; punching down (juniors, job seekers, named individuals, a competitor's employees); more than one joke per beat; preachy satire; self-deprecation without evidence of competence.

Joke tests a judge runs without a human:
1. Subtext: extract the implied opinion as one plain sentence. None → cut.
2. Truth: the observation is verifiable or in the fact bank.
3. Restatement: a fresh reader can (a) identify the funny line, (b) name the mechanism, (c) explain why in one sentence. Fail if "pun" or cannot locate the line.
4. Deletion: remove the funny line; if nothing is lost it was decoration.
5. Target: self, the system, an abstraction, a powerful institution = pass; a named person, juniors, customers = fail.
6. Straight face: no "lol", laughing emoji, "jk", "haha", "(joke)".
7. Surprise: the punch word is the last word of its sentence and not predictable from the setup.
8. Frequency: at most one joke beat per ~5 lines on LinkedIn; one per post on X.

## 4. Head-turning hooks

Data: story openers 2.60% median ER > contrarian 2.31% > statement 2.27% > results 2.19% > question 2.16% (AuthoredUp, 309K posts). Hook length 0–40 chars 2.61% vs 200+ 2.08%. Number in first line: 35 vs 26 median likes; 1–5-word openers best, 11–15 words worst; question hooks 19 vs 29 (MagicPost, 1.18M posts). Hooks longer than one line drop ~20% (Alić). 210 chars visible on desktop, ~140 on mobile before "see more".

LinkedIn first-line patterns that work: in-medias-res story line; specific result with a non-round number; a claim a smart reader could dispute; confession; naming; the enemy line; the demonstration hook. X first lines: label + definition; deflating literalism; number + date prediction; two-number contrast; quote-tweet + deadpan one-liner; live build log with a caveat.

Overused (reject): "Here's what nobody tells you" (−4.3% reach), "It's not X, it's Y" (−4.9%), "The result?" (−4.8%), "Stop X, start Y" (−6.7%), sentence-initial "Moreover/Furthermore", "It's worth noting", question openers, "I'm excited/thrilled/humbled to announce", "harnessing the power of AI", "Unpopular opinion:", "Hot take:", "I was today years old", "Let that sink in", "Read that again", "Nobody talks about this", "This changes everything", "X is dead", "A thread 🧵", "I asked ChatGPT to", "In today's fast-paced world", "game-changer", "Agree?", "Thoughts?", any opener whose subject is unnamed.

Curiosity gap without clickbait: state the subject and the stake concretely; withhold only the mechanism, number or twist; deliver it inside the post; never withhold the subject. Bait: "This one change 10x'd our pipeline." Gap done right: "We rewrote one 40-line prompt. Extraction errors fell 31%. The line that mattered was the last one."

## 5. The quality bar (gates then scores)

| # | Criterion | Type | Pass |
|---|---|---|---|
| G1 | The first line could not be attached to any other topic (a name, number or specific event) | gate | yes |
| G2 | At least one claim a smart reader could disagree with | gate | yes |
| G3 | At least one detail only this author could supply (fact bank, first-hand, a real number) | gate | yes |
| G4 | Every factual claim is in the fact bank, sourced, or explicitly opinion/prediction | gate | yes |
| G5 | No reject-list item in the first two lines; no "It's not X, it's Y" or "Stop X, start Y" anywhere | gate | yes |
| G6 | No generic CTA; any closing question is specific to the post's claim | gate | yes |
| G7 | Any joke passes the subtext + truth + target tests | gate | yes |
| G8 | Not derivative of any reference post (section 6 checklist) | gate | yes |
| S1 | A fresh reader can restate the thesis in one sentence and it matches the intended angle | 1–5 | ≥ 4 |
| S2 | No sentence can be deleted without loss | 1–5 | ≥ 4 |
| S3 | Surprise: a follower of this topic would not have predicted the angle | 1–5 | ≥ 4 |
| S4 | Specificity density: non-round numbers, named tools/people/dates per 100 words | 1–5 | ≥ 3 |
| S5 | Register: deadpan, no intensifiers/exclamation marks/emoji-laughter; sounds like speech | 1–5 | ≥ 4 |
| S6 | Hook mechanics: one line, ≤ ~40 chars (LinkedIn) or the whole point in line one (X); line 2 re-hooks or delivers | 1–5 | ≥ 4 |
| S7 | Payoff: what the hook withheld is delivered; the ending closes the loop or calls back | 1–5 | ≥ 4 |
| S8 | Personal fit: consistent with the persona/voice; a colleague would believe he wrote it | 1–5 | ≥ 4 |
| S9 | Timeliness: passes "why now?" in one sentence | 1–5 | ≥ 3 |
| S10 | Humor quality (if attempted): fresh reader names the mechanism and the true observation it rests on | 1–5 | ≥ 4 or no joke |
| S11 | Emotion target is identifiable and singular | 1–5 | ≥ 4 |

Anything failing a gate is regenerated from the angle step, not patched at the sentence level.

## 6. Using reference posts without copying them

Principle: good theft = study, steal from many, transform, remix; bad theft = steal from one, imitate, rip off (Kleon). "Borrow the skeleton, rewrite the flesh." Copy rhythm and cadence until the divergences reveal your voice (Perell). Steal the device, never the sentence (Cole).

| Extract and reuse | Never reuse |
|---|---|
| Hook family (story / result / contrarian / confession / naming) | The hook's words or its specific claim |
| Line-2 move (re-hook, flip, caveat) | The example, anecdote, or number |
| Paragraph rhythm, sentence length distribution | Distinctive phrases, coinages, metaphors |
| Device placement (where the receipt sits, where the joke sits, how it closes) | The joke itself or its target |
| Humor mechanism (deflation, escalation, understatement) | The topic + thesis pairing |
| Register (deadpan, lowercase, no intensifiers) | Signature sign-offs or catchphrases |
| Length and format (list vs prose, P.S. usage) | Any sentence with 6+ consecutive words in common |

Keeping the author at the center: reference posts inform *how*; the fact bank supplies *what*. If a draft's specific details all came from the model rather than the fact bank, G3 fails.

"Inspired by, not derivative" checklist (G8): topic+thesis pair not shared with any reference; no 6+ consecutive words in common; not the same hook family AND structure AND device order as a single reference (borrow from ≥ 2 or diverge on one axis); every specific detail traces to the fact bank or a cited source; no reference's coinage, metaphor, catchphrase or joke; a reader who has seen the reference would call this "in the same tradition", not "a rewrite"; the voice matches the author's own profile more closely than the reference author's; attribution when a borrowed idea is load-bearing.
