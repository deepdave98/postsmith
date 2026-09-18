# Device taxonomy: humor and voice (v1, 2026-09-17)

Source: docs/design/research-style-method.md A5; humor theory base: incongruity-resolution, benign violation (a norm is
violated and the violation is safe), superiority (punch up or at yourself), relief. Cards list `devices: [{device, lines, note}]`;
candidates name one (`assignment.device`); the comedy judge names the device(s) and the expectation before scoring `humor`.

Rule for annotators and judges: name a device only if you can point to the line and state the expectation it sets up and how
it is broken. "Witty tone" is not a device. Every joke is a plain opinion passed through a filter; if you cannot state the
opinion, there is no joke.

## Humor devices

| id | definition | sets up | breaks it with | example |
|---|---|---|---|---|
| misdirection | setup builds one expectation, the last words redirect | a reading the first clause makes obvious | a pivot as late in the sentence as possible | "Best coworker I've ever had. Would not let it near prod alone." |
| rule_of_three_escalation | two items set a pattern, the third breaks it | a parallel series | a third item that degrades, escalates or changes category | "see stuff, say stuff, run stuff, and copy-paste stuff" |
| callback | an earlier detail returns in a new context | the detail was incidental | it turns out to be load-bearing (the post "remembers itself") | the $14 line item from line 3 closes the post |
| reversal | flip a known saying or belief | the reader completes the familiar phrase | the completion is the opposite | "stop taking business advice" |
| analogy | compare unrelated things that share an absurd property | a serious domain | a mundane one with two aligned points | "New model releases are airline seat sales." |
| exaggeration | inflate one true detail past plausibility | a proportionate claim | a scale the reader knows is impossible but directionally right | "by Q3 the changelog will be longer than the model card" |
| understatement | a dramatic thing said mildly | alarm | a flat reaction | "this seems…not good." |
| deadpan | no signal that a joke is happening | earnest register | the content is absurd while the tone never moves | "We killed our AI strategy last week." |
| specificity | the odd, precise detail is the joke | a generic category | a detail nobody would invent | "a 94-pound Rhodesian Ridgeback with a vendetta against ottomans" |
| self_deprecation | the author is the target | competence on display | an admission at the author's own expense (safest benign violation) | "posted my way to the top" |
| fake_precision | absurdly exact number or time | a rough estimate | decimal-point precision about something unmeasurable | "4 minutes and 11 seconds of patience" |
| anti_climax | big buildup, tiny payoff | a revelation | a trivial or literal one | "It was 11 lines." |
| incongruous_register | corporate language for trivial things, or casual language for enormous things | register matched to stakes | register mismatched to stakes | "AGENT INCIDENT REPORT. Root cause: it was being helpful" |
| meta | the post comments on its own format or platform | the post as content | the post as an object the author can see | "that's it. that's the post." |
| absurdism | a premise that cannot be true, followed with full seriousness | a plausible scene | its logical consequences taken literally | an agent nostalgic for being blackmailed by humans |

## Voice and rhetorical devices

| id | definition | sets up | breaks it with | example |
|---|---|---|---|---|
| fragment | a sentence without a verb or subject, used with intent | grammatical completeness | a clipped fragment carrying the weight | "Four hours." |
| one_word_line | a single word as its own line or paragraph | paragraph-length prose | one word given the space of a paragraph | "Anyway." |
| anaphora | repeated openers across consecutive lines | variety | deliberate repetition that builds (three-plus by reflex is a tell, 2.20) | "Not more features. Not more funding." (the slop form) |
| parenthetical_aside | a side comment in brackets or after a dash | the main line | a private remark to the reader | "(1, unironically)" |
| rhetorical_question | a question the author answers or leaves hanging | an answer | none needed, or an answer that undercuts (hypophora "The result?" is a tell, 2.4) | "What does it do at 3am?" |
| false_start | a stop and restart mid-thought | a finished sentence | "Wait." and a correction | "Wait. It did run the tests." |
| direct_address | speaking to the reader as "you" | third-person description | a second-person accusation or instruction | "Reader, they did not." |
| lowercase_everything | no capitals anywhere | published register | typed-fast register (proves nothing about humanity on its own) | "spent 4 hours yesterday getting ffmpeg to..." |
| ironic_formality | formal diction about an informal thing | plain speech | bureaucratic or legal phrasing | "I regret to inform the team that the agent has purchased a domain." |
| list_as_argument | the list itself is the claim | a paragraph of reasoning | items whose accumulation makes the point | "X = lawyers (3), accountants (2), Cursor (1)" |
| quote_then_undercut | quote something, then one line that deflates it | the quote as authority | a flat, specific reply | "'Your network is your net worth.' It was a Slack workspace with 4 people." |
