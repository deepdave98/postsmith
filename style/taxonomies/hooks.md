# Hook taxonomy (v1, 2026-09-17)

Source: docs/design/research-style-method.md A3 (Welsh, Acosta, Alić, Cole/Bush, StrategyKiln), overuse flags from
docs/design/content-quality-bar.md §4 and docs/design/research-ai-tells.md §1G/§2.30/§3/§4. A card tags each hook with at
most two ids (`hook.types`); a candidate names one (`hook_type`); the reader judge names the type before scoring `hook`.

`overused` values: `yes` = the research lists the shape itself as stale (judge caps hook at 3 unless visibly subverted;
several also trip Tier 0 P8/P19); `template` = fine as a mechanism, stale in its stock wording; `no` = no evidence of fatigue.
Data behind the flags: story openers 2.60% median ER > contrarian 2.31% > statement 2.27% > results 2.19% > question 2.16%;
0-40-char hooks beat 200+; "Here's what nobody tells you" −4.3% reach, "It's not X, it's Y" −4.9%, "Stop X, start Y" −6.7%,
question hooks 19 vs 29 median likes; a number in line 1 beats none (35 vs 26); hooks longer than one line drop ~20%.

| id | shape | example | when it works | overused |
|---|---|---|---|---|
| relatable_enemy | Name a thing the audience resents, take a stance | "The 9-to-5 is getting pummeled." | the enemy is named, not "people" or "they" | no |
| contradiction | State the opposite of expectation | "The best business advice I got: stop taking business advice" | the flip is earned in the body; never as "It's not X, it's Y" | template |
| direct_mirror | Describe the reader's own behavior | "You like. You save. You lurk." | the behavior is specific enough to sting; watch the tricolon (P17) | no |
| numbered_promise | N things / lessons / mistakes | "7 things I wish I knew before I left my $400K job" | the corpus uses listicles and the items are non-parallel | yes |
| negative_qualifier | Promise plus a parenthetical "(that don't involve X)" | "3 ways to grow (that don't involve posting daily)" | the excluded X is the thing everyone recommends | template |
| number_result | "How I got [number] in [time]" | "How I got 40K followers in 9 months" | the number is yours and non-round; the stock "How I got" frame is stale | template |
| stop_start | "Stop X. Do Y instead." | "Stop posting tips. Start posting receipts." | rarely; banned anywhere in a post by quality-bar G5 | yes |
| secret | "Nobody talks about X. But it changed Y." | "Nobody talks about eval debt." | rarely; "nobody talks about" is a P19/P8 pattern | yes |
| bold_claim | "[Popular belief] is wrong." | "Prompt engineering is a job title for six more months." | the claim is disputable and specific; never prefixed "Unpopular opinion:" or "Hot take:" | template |
| curiosity_gap | Reveal what + who + promise, withhold the answer | "We rewrote one 40-line prompt. Extraction errors fell 31%. The line that mattered was the last one." | subject and stake are stated and only the mechanism is withheld; bait withholds the subject | template |
| rude_awakening | "I once [did X] and [unexpected result]" | "I once shipped a migration on a Friday and learned what 'idempotent' means." | the result is concrete and cost something | no |
| outcome_first | Lead with the result, then how | "Bill went from $1,140 to $0. Here's the 11-line prompt." | the outcome is a non-round number | no |
| specificity | Open with a number, name, date or artifact | "In 2025 I interviewed 100 CFOs..." | the specific is yours; the highest-yield opener in the data | no |
| cliffhanger | Ends above-fold with ":" or "..." | "Then the vendor sent the invoice:" | the payoff sits right after the fold; "has a name:" colon-reveals are a tell (2.17) | template |
| question | Provocative question the reader wants answered | "What does your AI SDR do at 3am?" | the answer is not obvious; question openers score lowest in the data | yes |
| story_in_medias_res | Drop into the middle of a scene | "Tuesday, 11:40pm, the bank's compliance lead is on the call." | the scene is real and dated; the best-performing opener family | no |
| emotional | High-arousal (awe, anger, humor) | "I have never been this angry at a changelog." | the emotion is produced by a specific, not announced; manufactured outrage is a regret_risk trigger | no |
| deadpan_announcement | Big news said flatly, or small news said hugely | "We killed our AI strategy last week." | X-native; the flatness is the joke | no |
| one_liner | The whole post is the hook; observation or aphorism | "every 'Cursor for X' pitch this week: X = lawyers (3), accountants (2), Cursor (1)" | X; ≤ 140 chars; ends on the last concrete thing | no |
| screenshot_dunk | "look at this" + one-line angle; media carries the proof | "the pricing page after the 'no price increase' email:" | the screenshot is real (real_capture_direction); "I asked ChatGPT to" + screenshot is a cliché | no |
| fake_precision | Absurdly specific number or time for comic effect | "I have 4 minutes and 11 seconds of patience for this." | the precision is obviously invented and the target is benign | no |
| meme_template | Recognizable format ("nobody:", "me:", "POV:", fake dialogue) | "nobody: / our agent at 2am: buying a domain" | X; the format is current in the scene and the specific inside it is new | template |

Practitioner context (not rules): the first line breaks the scroll, the second builds tension, the last line above the fold
promises a payoff; hooks are one line; the rehook slams the door so the reader cannot leave; some authors treat every line
as a hook, so posts read like a stack of headlines. Reject any opener whose subject is unnamed.
