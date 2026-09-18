# Style learning and post judging: method notes (researched 2026-09-17)

Why the corpus is annotated the way it is, where the taxonomies came from, and which numbers in
`config/postsmith.yaml` have a source behind them rather than a guess. The live artifacts are
`.claude/skills/learn/references/card_spec.md` (the card), `style/taxonomies/` (A3-A5 below),
`evals/rubric/v1/` (the judge anchors) and `docs/design/contracts.md` (every schema). When this file and one of
those disagree, they win and this file is out of date.

Tags: **[verified]** the source was fetched and the claim is on the page · **[reported]** third-party summary or
search snippet · **[practitioner heuristic]** widely used by ghostwriters, measured nowhere · **[design choice]** ours,
tuned by calibration data.

Everything here assumes Claude Code running skills with subagents plus small Python helpers. No external LLM APIs.

---

## Part A. Learning a style from a small corpus

### A1. Why annotation rather than examples

"Here are 20 posts, write like this" fails twice over: the model copies surface phrasing, which is both a plagiarism
risk and a pastiche, and it averages several voices into mush. So the corpus becomes *mechanisms* (what a post does and
why that works) plus a *measured fingerprint* (how it reads at the level of lines, sentences and punctuation), and the
writer borrows mechanisms inside the user's own persona. Ghostwriters work the same way: Welsh turns his top posts into
templates of structure, not sentences [reported: https://autoposting.ai/blog/justin-welsh]; Cole's "Tequila Test" is
about listing the obvious angles and refusing them [verified: https://www.ship30for30.com/post/how-to-start-writing-online-the-ship-30-for-30-ultimate-guide].

### A2. The post card

One card per reference post, written after reading the text and looking at the attached media (Read on images,
`ffmpeg` keyframes at 0/25/50/75/100% for video, then Read on the frames). The schema and the field-by-field notes are
`.claude/skills/learn/references/card_spec.md`.

A card with media records what the media *is* (`literal`, verbatim on-media text, style notes), what it *adds*
(`role`: proof, punchline, contrast, context, aesthetic or none), whether the caption survives without it
(`caption_dependency`) and whether a prompt could reproduce it. Those four fields exist so that a later media brief
can imitate the role and never the picture, which is also why `style/taxonomies/media_roles.md` points here.

Two constraints on the card that are easy to lose and expensive to lose:

- Every claim cites the post's line numbers, and a fresh-context subagent re-reads post and card and checks each
  citation and each device claim. Verification is 100%, not sampled: the corpus is small and the cards are what
  everything downstream is built on. The discipline is the one in Anthropic's evals guidance, grade what was produced
  and require transcripts [reported: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents].
- The card exists so that a different model instance, one that has never seen the post, could reconstruct *why it
  works* without being able to reconstruct *its sentences*. One precise device beats three vague ones. If the post is
  not funny, the card says so instead of inventing a humor mechanism.

### A3. Hook taxonomy

Synthesized from Welsh, Acosta, Alić, Cole/Bush and the StrategyKiln analysis. A card tags at most two types.
The live list with overuse flags is `style/taxonomies/hooks.md`.

| id | Hook type | Shape | Source |
|---|---|---|---|
| relatable_enemy | Name a thing the audience resents, take a stance | "The 9-to-5 is getting pummeled." | Welsh [reported: https://www.strategykiln.com/mastering-linkedin-hooks-b2b-thought-leaders] |
| contradiction | State the opposite of expectation | "The best business advice I got: stop taking business advice" | Welsh [reported: autoposting.ai] |
| direct_mirror | Describe the reader's own behavior | "You like. You save. You lurk." | Welsh [reported: autoposting.ai] |
| numbered_promise | N things / lessons / mistakes | "7 things I wish I knew before I left my $400K job" | Welsh, Acosta [reported] |
| negative_qualifier | Promise plus a parenthetical "(that don't involve X)" | | Welsh [reported: StrategyKiln] |
| number_result | "How I got [number] in [time]" | | Acosta [reported: https://buldrr.com/lara-acosta-linkedin-templates-hooks-examples/] |
| stop_start | "Stop X. Do Y instead." | | Acosta, Nat Berman [reported] |
| secret | "Nobody talks about X. But it changed Y." | | Acosta [reported] |
| bold_claim | "[Popular belief] is wrong." | | Acosta [reported] |
| curiosity_gap | Reveal what and who, promise the answer, withhold it | | Cole [verified: Ship 30 guide] |
| rude_awakening | "I once [did X] and [unexpected result]" | | Alić [reported: StrategyKiln] |
| outcome_first | Lead with the result, then how | | Jake Ward [reported: StrategyKiln] |
| specificity | Open with a number, name, date or artifact | "In 2025 I interviewed 100 CFOs..." | [reported: StrategyKiln] |
| cliffhanger | Ends above the fold on ":" or "..." | | [reported: StrategyKiln] |
| question | A provocative question the reader wants answered | | [reported] |
| story_in_medias_res | Drop into the middle of a scene | | [reported] |
| emotional | High-arousal: awe, anger, humor | Berger's "when we care we share" | [reported] |
| deadpan_announcement | Big news said flatly, or small news said hugely | X-native | [practitioner heuristic] |
| one_liner | The whole post is the hook: an observation or an aphorism | X-native | [practitioner heuristic] |
| screenshot_dunk | "look at this" plus a one-line angle; the media carries the proof | X-native | [practitioner heuristic] |
| fake_precision | An absurdly specific number or time, for comedy | "I have 4 minutes and 11 seconds of patience for this" | [practitioner heuristic] |
| meme_template | A recognizable format: "nobody:", "me:", "POV:", fake dialogue | X-native | [practitioner heuristic] |

Practitioner principles worth giving an annotator as context, not as rules: the first line breaks the scroll, the
second builds tension, and the last line above the fold promises a payoff [reported: Welsh via autoposting.ai]; hooks
are one-liners; the rehook "slams the door" so the reader cannot leave [reported: Alić via
https://garden.quintsmart.com/linkedin-writing-tips-from-jasmin-alic]; Acosta treats every line as a hook, so her posts
read like a stack of headlines [reported: https://buldrr.com/the-acosta-linkedin-model/].

### A4. Structure archetypes

The live list is `style/taxonomies/structures.md`. A card records one archetype.

| id | Spine | Notes |
|---|---|---|
| hook_reframe_proof_punch | Hook, reframe, proof, punchline, no CTA | The shape this account wants. Dropping the CTA is deliberate: a CTA is the single strongest LinkedIn-creator tell [practitioner heuristic] |
| story_arc | Scene, complication, turn, lesson (SLAY: Story, Lesson, Actionable, You) | Acosta [reported: buldrr] |
| rude_awakening_story | "I once…", what happened, what it taught | Alić |
| listicle | Numbered promise, N items in parallel form, close | Welsh, Cole "Proven Approach" [verified: Ship 30] |
| contrarian_take | Consensus, "wrong", why, what instead | Acosta bold_claim, Welsh contradiction |
| screenshot_commentary | Media is the evidence, the caption is the angle | X-native; media_caption_dependency = media_dependent |
| one_liner | A single observation, at most 2 lines | X-native. Best-engagement tweet lengths are reported around 71-100 chars [reported: https://wildandfreetools.com/blog/how-long-should-a-tweet-be-2026/] |
| escalation_ladder | 3+ items, each escalating, the last breaking the pattern | The comic triple: establish, reinforce, surprise (Tony Allen) [reported: https://www.writersdigest.com/there-are-no-rules/comedy-writing-secrets-triples] |
| confession | Self-deprecating admission, then the real point | |
| announcement_with_twist | News plus a deadpan or self-undercutting line | Founder and launch posts |
| trailer_meat_cta | Welsh's standard LinkedIn structure [reported: autoposting.ai] | Annotate it, but in generation it is the default to avoid unless the corpus uses it |
| thread | Multi-post, each post standalone-hooky | X |
| meme_format | Caption plus an image that carries the joke | X |

Rhythm notation (Ship 30): `1/3/1`, `1/5/1`, `1/2/5/2/1` describe sentence-per-paragraph crescendo patterns
[verified: Ship 30 guide]. The card records the pattern, the profile records the distribution.

### A5. Device taxonomy

The live list is `style/taxonomies/devices.md`. Humor theory base: incongruity-resolution (the dominant paradigm),
benign violation (a norm is violated *and* the violation is safe), superiority (punching at a target, so for a personal
brand punch up or at yourself), relief [reported: https://arxiv.org/pdf/2509.21175,
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6593112/]. The annotator tags the *structural* device, because that is
what a writer can reuse.

- `misdirection`: the setup builds one expectation and the last words redirect; the pivot lands as late in the
  sentence as possible [reported: https://comedipedia.com/blog/7-joke-structures]
- `rule_of_three_escalation`: two items set a pattern, the third breaks it
- `callback`: an earlier detail returns in a new context, so the post remembers itself
- `reversal`: flip a known saying or belief
- `analogy`: two unrelated things sharing an absurd property
- `exaggeration`
- `understatement` / `deadpan`: a dramatic thing said mildly
- `specificity`: "a 94-pound Rhodesian Ridgeback with a vendetta against ottomans" beats "a large dog"
  [reported: Comedipedia]
- `self_deprecation`: the author is the target, which is benign violation with the safest target
- `fake_precision`
- `anti_climax`: big buildup, tiny payoff
- `incongruous_register`: corporate language for trivial things, casual language for enormous ones
- `meta`: the post comments on its own format or platform
- `absurdism`

Voice and rhetorical devices: `fragment`, `one_word_line`, `anaphora`, `parenthetical_aside`, `rhetorical_question`,
`false_start` ("Wait."), `direct_address`, `lowercase_everything`, `ironic_formality`, `list_as_argument`,
`quote_then_undercut`.

Name a device only when you can point at the line and say what expectation it sets up and how that breaks.
"Witty tone" is not a device.

### A6. Computed stylometrics

`tools/stylometry.py` computes the features and owns the list; it runs on every post in seconds. The features are the
classic authorship-attribution set (sentence length mean and SD, function-word profile, punctuation frequencies, word
length, vocabulary richness), which separates authors with >90% accuracy in small-author settings
[reported: https://ceur-ws.org/Vol-1384/paper6.pdf; function words as the strongest single indicator:
https://maxintel.org/stylometry.html]. Two findings shape which features carry weight: human writing has higher
burstiness, meaning sentence-length variance, than LLM output
[reported: https://gptzero.me/news/perplexity-and-burstiness-what-is-it/], and human texts cluster more loosely than
LLM texts under Burrows' Delta [reported: https://www.nature.com/articles/s41599-025-05986-3 via
https://techxplore.com/news/2025-12-reveals-ai-fully-human.html]. Em-dash density is a known AI marker
[reported: https://theconversation.com/too-many-em-dashes-weird-words-like-delves-spotting-text-written-by-chatgpt-is-still-more-art-than-science-259629].

Report type-token ratio with the word count beside it, because TTR is length-sensitive. Mark the tense ratio as
approximate: it is a regex heuristic on `-ed` and auxiliaries.

`tools/profile_stats.py` turns the features into the **envelope**: median and IQR (25th to 75th) per feature, plus min
and max. With 5-15 posts per author the IQR is noisy, so the profile records `n` and the eval widens the tolerance.

### A7. The learning pass

Normalize the ingested rows, run stylometry, annotate, verify, build profiles, then split. Three parts of that order
are load-bearing:

- Annotate in parallel, one subagent per author (or per 8-10 posts). Independent context per author is what stops the
  annotator blending voices, and it processes the whole corpus in one wall-clock pass.
- A profile builder cites at least 2 post IDs for anything it calls a habit. Single instances go under "seen once", so
  a one-off is never mistaken for a pattern.
- The split holds out at least 4 posts per platform as oracle and lineup fillers that no writer ever sees, and names
  5-8 exemplars that judges anchor on. The user rates corpus posts 1-5 on "how much would I want to have written
  this", which is cheap and doubles as calibration data.

Re-ingestion bumps the version in `style/CHANGELOG.md` with the corpus hash and card count.

### A8. What a profile has to contain

Per author: lane, a voice paragraph written as instructions to a writer ("short declaratives, then one long sentence
that runs away with itself; never explains the joke"), stance sliders with their range, structural habits as
distributions, hook habits with a quoted example each, ranked humor devices and the signature move, the stylometric
envelope, media habits, **negative space** (what the author never does), and the do-not-reuse phrases. Quoting inside
a profile is fine, since it is internal and attributed; generation is where phrasing must not be reused.

Confidence bands on `n`: low under 6 posts, medium 6-15, high above 15. Below 6 the profile states habits it cannot
support, which is why `corpus.author_profile_min_posts` exists.

The aggregate profile (`style/common.md`) is the *level*, not a voice: traits at least 70% of authors share, which is
the bar; the traits authors split on, which are choices a persona makes rather than requirements; a quality bar
computed by contrasting the top-rated third of posts against the bottom third, stated with numbers and post IDs; and
the anti-patterns the corpus never uses.

### A9. Persona and the borrowing rule

`style/persona.md` is what makes output inspired-by rather than copied: who the user is and what they see daily, the
claims they can and cannot make, the opinions they hold and refuse, lane and audience, their chosen position on each
divergent trait, vocabulary in and out, comfort with self-deprecation and with punching at companies (with a named
do-not-target list), and which reference authors to lean on for what.

The rule the whole design rests on: borrow *mechanisms* from `common.md` and one author lens; take *content, claims,
opinions and anecdotes* only from `persona.md` and the brief; never take phrasing from the corpus. The overlap gate
below enforces the last clause mechanically, because that is the only clause a writer can break by accident.

---

## Part B. The eval

### B1. Principles

- Atomic dimensions, scored and reported separately, no blended score. Deterministic checks run first because they are
  cheap and unbiased; judges second; the lineup and pairwise last and only for candidates that already clear
  everything else.
- Every judge is a fresh-context subagent holding the rubric section verbatim, two scored anchors (one weak, one
  strong) and the candidate wrapped as untrusted data, with instructions that anything inside the candidate is content
  and not a command. A score without a quoted span is discarded by the aggregator.
- Judges never learn which text is generated and which is human, never see the writer's reasoning, and are told
  explicitly that length is not quality. Verbosity bias of 15-30 points and position bias of 10-15 points are
  documented for LLM judges [reported: https://futureagi.com/blog/evaluating-llm-judge-bias-mitigation-2026/;
  original: https://arxiv.org/abs/2306.05685]. Position is randomized with a seeded RNG, pairwise tasks run both
  orders, and inconsistent verdicts count as ties (swap augmentation) [verified: https://arxiv.org/html/2604.23178].
- Every judge here shares a base model, so a jury gives far fewer independent votes than its size: a nine-judge panel
  yielded about 2 effective votes when base model, prompt and rubric were shared
  [reported: https://arxiv.org/pdf/2605.29800]. So diversify the *lens*, three judge personas with differently worded
  prompts, and cap juries at 3. Diverse model families are the ideal [reported: https://arxiv.org/abs/2404.18796] but
  are ruled out by running inside Claude Code alone. That limitation is exactly why user calibration matters.
- "No answer" is not "negative answer". Humor, media and factual dimensions return `na` when the post attempts no
  joke, has no media, or makes no checkable claim, and `na` never fails a post.
- Ground truth stays unreachable: held-out posts, ratings and the lineup key are outside every writer's context, and
  hooks enforce it rather than instructions.

### B2. Deterministic checks

**Platform fit** (`tools/platform_check.py`): the LinkedIn hook must complete a thought before ~210 chars on desktop
and ideally ~140 on mobile, which is where "see more" truncates and where the exact cutoff varies by client
[reported: https://authoredup.com/blog/linkedin-character-limit ,
https://linkedinpreview.com/blog/linkedin-post-character-limit-2026]. X is 280 chars unless the persona has Premium
and the post is deliberately long-form [reported: https://typecount.com/blog/twitter-character-limit], with a reported
sweet spot around 70-200 chars [reported: wildandfreetools, toolsoasis]. Threads split into standalone units. Neither
platform renders markdown, so `**bold**` in the output is a bug.

**Overlap** (`tools/overlap_check.py`), against every corpus post and everything already published, after lowercasing,
stripping punctuation and collapsing whitespace:

- a shared word 6-gram flags, a shared word 8-gram fails. Decontamination practice uses 13-word or 8-gram / 50-char
  overlaps for *long documents* [reported: https://arxiv.org/pdf/2405.15523]; social posts run 20-400 words, so the
  thresholds have to be tighter, and 6/8 is our choice.
- longest common substring of 40 chars or more fails, which is what catches paraphrase-with-tweaks.
- any do-not-reuse phrase, fuzzy to an edit distance of 2, fails.
- same archetype + same hook type + same ending + word 3-gram Jaccard at or above 0.15 flags "too close to
  `<post_id>`", and the pairwise judge is then asked whether these are the same post rewritten. This is the guard
  against copying a skeleton and swapping the nouns.
- candidates also run against each other, so a run cannot deliver two variants of one post.

**AI tells** (`tools/ai_tells.py`, patterns in `evals/rubric/v1/patterns.yaml`): banned words and phrases as a hard
zero-hit gate, structural regexes ("not just X but Y", "isn't about X. It's about Y.", inspirational triplets of
abstract nouns), and density checks compared against the corpus envelope (em dashes per 1,000 chars, rule-of-three
lists, present-participle tails, copula avoidance, vague attribution). Wikipedia's list is the canonical source for
the categories [verified: https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing], the specific words come from
`docs/design/research-ai-tells.md`, and the user's own flagged tells are appended over time. That append path is the
main reason the list stays current, since specific words rotate between model generations
[reported: The Conversation].

**Envelope** (`tools/envelope_check.py`): count how many of the candidate's features fall inside
[Q1 − 0.5·IQR, Q3 + 0.5·IQR] for the chosen lens, widened because `n` is small, weighted toward line-length
distribution, sentence-length CV, POV mix, punctuation profile, mean word length, contraction rate, specificity
density, hook length and function-word cosine distance to the author centroid. A weighted 0.70 in-envelope passes.
The value of this check is the failure list, not the score: "your median line is 19 words; this author's is 7
(IQR 5-10)" is rewrite feedback a writer can act on.

### B3. Judges

Each LLM dimension is judged one candidate at a time on an absolute scale against two scored anchors, with integer
scores and quoted evidence. The anchors define 1, 3 and 5 and judges interpolate; the anchor text ships in
`evals/rubric/v1/rubric.md` and this file does not duplicate it.

Three findings that shaped the anchors:

- Expert detectors key on AI vocabulary, formality, originality and clarity, which is what the not-AI anchors are
  written against [verified: https://arxiv.org/abs/2501.15654].
- First person, contractions, lowercase and personal topics are *not* evidence of humanity. People rely on those
  heuristics and they are exploitable [reported: https://arxiv.org/abs/2206.07271], so the rubric tells judges to
  ignore them.
- Uniqueness is Cole's Tequila Test made operational [verified: Ship 30 guide]: the judge first lists the five most
  obvious posts anyone would write on this topic, then scores whether the candidate is on that list.

`suggested_fix` in a judge's JSON must be surgical ("move the number into line 1; cut line 4") because the refine loop
passes it to the rewriter verbatim. A jury of three lenses (comedy writer, skeptical engineer reader,
ghostwriter/editor) runs for any soft dimension within one point of its threshold, any hard-gate dimension scored 3,
and every lineup and pairwise task. Aggregate by median and record the disagreements, which are calibration data.

### B4. The Turing lineup

A direct test of "does not sound like AI" that is harder to game than a rubric score.

Three fillers come from the held-out pool: same platform, length within ±30% of the candidate, same archetype where
possible, different authors where possible. Length matching matters because length is the easiest tell. Strip author
names, URLs and @mentions from all four, keep emoji, casing and line breaks since those are voice, shuffle with a
seeded RNG and store the seed and the mapping. Three fresh judges, three lenses, three orders, asked: exactly one of
these four posts was produced by an AI system, pick it, rate confidence 1-5, name the single strongest tell. The prompt
takes the expert-detector lens, because frequent LLM users detect AI text far better than lay readers or detectors
[verified: arXiv 2501.15654] while lay heuristics fail [reported: PNAS 2023].

**Fail** when 2 of 3 judges pick the candidate at confidence 4 or more, or all 3 pick it at any confidence. Everything
else passes: chance is 25% per judge, so a single low-confidence pick is noise. Every pick feeds its tell into the
feedback packet even on a pass.

The lineup is itself tested whenever the filler pool or the rubric changes. Oracle control: put a real held-out post in
the candidate slot and judges should pick it about 25% of the time across 10 lineups; a filler picked as "the AI" in
more than 50% of controls is an outlier and leaves the pool. Negative control: a known slop post must be picked by 2 of
3 judges at confidence 4 or more in at least 80% of runs. If either control fails, the lineup is not trusted and the
run says so.

### B5. Pairwise against the nearest reference

The nearest reference is the held-out post with the same platform and archetype that maximizes word 3-gram Jaccard
with the candidate, tie-broken by hook type; failing that, same platform, and the report says so. Both texts are
anonymized, and two questions are asked separately: which is the better post, and which sounds more like the voice in
these exemplars. Each judge sees both orders and an inconsistent answer is a tie
[verified: arXiv 2604.23178].

The candidate passes by winning or tying with at least 1 of 3 judges on "better post" and fails only on a consistent
0/3 loss. The bar is deliberately "not clearly worse than a real post", because the corpus is top-tier and losing
narrowly to it is fine. When the structural-proximity flag fired for this reference, the judge is also asked whether
the two are the same post rewritten, and a yes is a plagiarism fail.

### B6. Grader health

Known negatives, each with the dimension it must fail on: empty text (platform fit, clarity); a generic "Here are 5
ways AI is changing work" written with no profile (uniqueness, not-AI, lineup); a corporate "Thrilled to announce"
(AI-tell lexicon, style match); an exact copy of a corpus post (8-gram and phrase list); a corpus post with 15% of its
words synonym-swapped (LCS or 6-gram, or structural proximity plus "same post rewritten"); a 2,900-char LinkedIn post
whose first 210 chars are preamble (platform fit, hook); a correct-voice post carrying a fabricated statistic (factual
sanity); a post that borrows a reference author's biography, "when I left my $400K job" (persona fit).

Oracle: at least 5 held-out real posts per platform pass every dimension except persona fit, which is an expected fail
because they are not the user. An oracle post failing not-AI, style match or uniqueness means the rubric is too strict
or mis-anchored, and that gets fixed before the rubric is used on anything.

A rubric version is promoted only when the health report is green, and the report is committed next to the rubric.

---

## Part C. Calibration and the refine loop

### C1. What gets rated

The user rates corpus posts once during ingestion and every generated post they see, including rejected ones, 1-5 on
"how much I'd want to have written this", with optional tags. The tag vocabulary is fixed in `docs/design/contracts.md`
§13; a tag with a cited phrase is worth more than a score, because the phrase goes straight into the lexicon.

### C2. Agreement

Run the analysis every ~20 new ratings. Overall: Spearman ρ between the user's score and the count of dimensions above
threshold, plus pass/fail agreement as Cohen's κ, treating a user score of 4 or more as a pass. **Auto-pass is not
trusted until κ ≥ 0.4 on n ≥ 30**, and until then every verdict is advisory and shown with its full table. For
reference, strong LLM judges reach about 80% agreement with humans on preference tasks, which is also the
human-to-human level [verified: https://arxiv.org/abs/2306.05685], so 80% is the ceiling, not a disappointment.

Per dimension, compute the false-negative rate behind each tag: the user said `sounds_ai` and the not-AI judge scored
4 or more. Fix in this order, cheapest and most deterministic first: add the cited tell to the lexicon; add the rated
post as a scored anchor for that dimension; move the threshold by one point; rewrite the anchor text. Every change
bumps the rubric version and re-runs the health tests.

Drift check: re-judge the same 10 fixed candidates on every rubric version and log the deltas, so a change that
silently shifts everything is visible instead of mysterious.

### C3. The refine loop

Round 0 spawns parallel writers, each assigned a different (archetype, primary device, author lens) combination, so
diversity is structural rather than a request for "three different versions". Gating runs cheapest first:
deterministic, then single judges, then juries for near-threshold scores, then lineup and pairwise only when
everything else has passed.

The feedback packet goes back to the *same* writer subagent, since it holds the reasoning, and contains only the
failing dimensions with quoted evidence, the `suggested_fix` for each, and the out-of-envelope features. The
instruction is "fix these, keep everything that passed", never "make it better". The rewrite is judged by *new* fresh
judges: self-critique is weaker than fresh-context verification, and same-instance judges show self-preference
[reported: https://arxiv.org/pdf/2410.21819].

Stop conditions, in the order they are checked:

- a pass, which outputs;
- 3 rounds without a pass, which outputs the best candidate with its table, marked as not passed;
- oscillation, where a dimension fails in round k and k+2 with contradictory feedback ("too long", then "hook lacks
  setup"), which stops and asks the user which side to favor, and records the conflict as calibration data;
- regression, where a fix breaks a previously passing hard gate twice, which stops and reports;
- an overlap flag that survives 2 rewrites, which discards the variant, because at its core it is a paraphrase of a
  reference.

---

## Sources

Verified by direct fetch:
- Ship 30 for 30 ultimate guide (4A paths, Curiosity Gap, Tequila Test, 1/3/1 rhythms): https://www.ship30for30.com/post/how-to-start-writing-online-the-ship-30-for-30-ultimate-guide
- Wikipedia, Signs of AI writing: https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
- Judging the Judges (bias mitigation, swap augmentation): https://arxiv.org/html/2604.23178
- Zheng et al., Judging LLM-as-a-judge (MT-Bench; position, verbosity and self-enhancement bias; ~80% human agreement): https://arxiv.org/abs/2306.05685
- Frequent ChatGPT users as expert detectors (cues: AI vocabulary, formality, originality, clarity): https://arxiv.org/abs/2501.15654
- Comedipedia, 7 joke structures: https://comedipedia.com/blog/7-joke-structures

Reported, not independently verified:
- StrategyKiln hook taxonomy and creator attributions: https://www.strategykiln.com/mastering-linkedin-hooks-b2b-thought-leaders
- Justin Welsh templates and trailer/meat/CTA: https://autoposting.ai/blog/justin-welsh
- Lara Acosta hooks, SLAY, hook/re-hook/lead/body/power-ending: https://buldrr.com/lara-acosta-linkedin-templates-hooks-examples/ , https://buldrr.com/the-acosta-linkedin-model/
- Jasmin Alić hook/rehook/P.S.: https://garden.quintsmart.com/linkedin-writing-tips-from-jasmin-alic
- Nicolas Cole on curiosity gap and specificity: https://writewithai.substack.com/p/why-specificity-is-the-secret-to
- Stylometry feature sets and function words: https://ceur-ws.org/Vol-1384/paper6.pdf , https://maxintel.org/stylometry.html
- Human against AI stylometric clustering (Burrows' Delta): https://www.nature.com/articles/s41599-025-05986-3 (summary via https://techxplore.com/news/2025-12-reveals-ai-fully-human.html)
- Burstiness and perplexity: https://gptzero.me/news/perplexity-and-burstiness-what-is-it/
- Jakesch, Hancock, Naaman on flawed human heuristics for AI text: https://arxiv.org/abs/2206.07271
- Nine judges, two effective votes (correlated judge errors): https://arxiv.org/pdf/2605.29800
- Panel of LLM evaluators (PoLL): https://arxiv.org/abs/2404.18796
- Self-preference bias in LLM judges: https://arxiv.org/pdf/2410.21819
- Bias magnitudes summary: https://futureagi.com/blog/evaluating-llm-judge-bias-mitigation-2026/
- Humor theories (incongruity, benign violation, superiority, relief): https://arxiv.org/pdf/2509.21175 , https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6593112/
- Rule of three and the comic triple: https://www.writersdigest.com/there-are-no-rules/comedy-writing-secrets-triples
- AI vocabulary and em dashes: https://theconversation.com/too-many-em-dashes-weird-words-like-delves-spotting-text-written-by-chatgpt-is-still-more-art-than-science-259629
- N-gram decontamination thresholds (8-gram / 13-word / 50-char): https://arxiv.org/pdf/2405.15523
- LinkedIn limits and truncation: https://authoredup.com/blog/linkedin-character-limit , https://linkedinpreview.com/blog/linkedin-post-character-limit-2026
- X limits and length data: https://typecount.com/blog/twitter-character-limit , https://wildandfreetools.com/blog/how-long-should-a-tweet-be-2026/
- LinkedIn ranking signals (dwell, comments): https://blog.hootsuite.com/linkedin-algorithm/ , https://meet-lea.com/en/blog/linkedin-algorithm-explained
- X open-sourced ranking weights as reported: https://www.socialpilot.co/blog/twitter-algorithm , https://dev.to/codedbytan/i-read-xs-open-sourced-ranking-algorithm-heres-what-actually-decides-who-sees-your-posts-2411
- Anthropic, Demystifying evals for AI agents: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
