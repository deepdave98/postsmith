# AI-tells catalog for short-form social copy (researched 2026-09-17)

The source behind `style/lexicon.yaml` (sections 1A-1M, 3, 4), `evals/rubric/v1/patterns.yaml` (2.1-2.37, 6.1, 7) and
the golden set (7.1, 7.2). These are tells that make a *reader* say "a model wrote this", ordered for use as a reject
rubric, not signals a detector could score.

Built from Wikipedia's "Signs of AI writing" (WikiProject AI Cleanup), GPTZero / Originality.ai / Pangram write-ups,
the Russell et al. expert-detector study, the blader/humanizer Claude Code skill, the Velitchkov "22 Claude Clichés"
catalog (Claude is the generator here), LinkedIn's 2026-07-30 "Seems like AI slop" option, X's 2026 enforcement, and
creator and editor lists. **[unverified]** marks a single low-authority source or our own observation. **[weak]** marks
something documented but unreliable on its own.

Word lists decay in about 12 months (see P5). When they go stale the whole catalog reads confident and wrong.

## 0. Principles the rubric respects

| # | Principle | Source |
|---|---|---|
| P1 | **Cluster rule.** One tell is noise. Three or more in one short post is a strong signal. | kitha.co; Wikipedia ("one or two coincidental; many appearing together is the strongest indicator") |
| P2 | **Experts key on exact recurring phrases**, not on fancy words, perfect grammar or neutral tone. Non-experts using those surface cues scored at chance; trained annotators hit >90% TPR on specific overused phrases. Humans produce *more* ungrammatical text than models do. | Russell et al. via pangram.com/blog/russell; Wikipedia "Ineffective indicators" (2025 study: general readers ≈ random, heavy LLM users ≈ 90%) |
| P3 | **Fake imperfection earns nothing.** Injecting typos or lowercase cargo-cults the cues P2 shows are unreliable. Score specificity, opinion and rhythm. | Russell; Pangram |
| P4 | **Perception is not performance, but on LinkedIn perception is reach.** A 1,000-page content study found em dashes slightly *positive* for engagement and "Conclusion" headers the strongest negative. Since 2026-07-30 readers can flag "Seems like AI slop" and flagged posts lose distribution, so reader perception now costs reach directly. | Search Engine Land (Gnuse, 2026-02-25) via seoteric.com; getvyral.io; TechRadar |
| P5 | **Vocabulary drifts by model generation, so version the list.** "delve" dropped sharply in 2025; GPT-5.1 suppresses em dashes; Wikipedia tracks three eras (GPT-4 / GPT-4o / GPT-5) plus Grok-specific words. | Wikipedia; GPTZero |
| P6 | **Humans imitate LLM style now.** A tell that is common in the user's own high-performing corpus must be down-weighted against corpus base rates, or the oracle set fails. | Wikipedia ("human speech and writing are increasingly influenced by LLMs"); arXiv 2502.09606 "Human-LLM Coevolution" |
| P7 | **The generator is Claude**, so Claude-era tics (1K, 2.15-2.19) matter more than GPT-4-era "tapestry" words, which Claude rarely emits. | Velitchkov; Jerod Santo; PCWorld |
| P8 | **Genre is itself a tell.** Originality.ai (Jan 2026, 3,368 posts): human posts beat "likely AI" posts by 25-80% in trust-driven sectors and 73% in marketing, but AI beat humans by 75% in *motivational leadership*. Generic inspo is the one genre where slop wins, and it is not the genre this account is in. | originality.ai/blog/linkedin-ai-study-engagement |

## 1. Lexical tells (~200 items)

Tier weights feed section 6. **T1** near-diagnostic in social copy · **T2** strong in clusters · **T3** weak alone,
counts toward a cluster.

### 1A. AI verbs (T1 unless noted)
delve / delve into · dive into / deep dive / let's dive in · unpack · navigate (the landscape/complexities) · leverage · harness (the power of) · elevate · unlock · unleash · foster · cultivate · empower · showcase (20x AI vs human, GPTZero) · underscore · highlight / highlighting · emphasize / emphasizing · enhance · bolster / bolstered · garner · streamline · supercharge · embrace · revolutionize · transform · demystify · illuminate · "aims to explore" (50x+) · "aligns / aligns with" (16x) · "remarked" (18x) · "surpassing" (12x) · "impacting" (11x) · "paving the way" · "resonate with" · reimagine · redefine · "double down" (T3) · "lean in" (T3)
Sources: Wikipedia (GPT-4/4o/5 era lists); GPTZero top-10; isitslop.io; oliviacal.com blacklist; Pangram; COLING 2025 "Why does ChatGPT delve so much" (21 focal words incl. delve, showcase, underscore, intricate, realm, groundbreaking, advancements, aligns); Kobak et al. Science Advances (delve 28x rise in PubMed abstracts).

### 1B. Abstraction nouns (T1)
tapestry · landscape (the X landscape) · realm · testament · journey · game-changer / game changer · paradigm shift · synergy · roadmap · beacon · symphony · interplay · intricacies · nuance / nuances (Claude-heavy) · insights ("valuable / actionable / key insights") · advancements · endeavors · ecosystem (T2) · north star · secret sauce · superpower · mindset (T2) · "the art of X" · "the power of X" · "a masterclass in" · "a testament to" · "a reminder that" · "the future of X" · "cornerstone" · "catalyst" · "blueprint" · "playbook" (T3)

### 1C. Adjectives and adverbs (T2)
crucial · pivotal · vital · key (as adj) · significant · groundbreaking · transformative · revolutionary · cutting-edge · robust · seamless / seamlessly · scalable · holistic · comprehensive · multifaceted · myriad · plethora · intricate · meticulous / meticulously · vibrant · profound · unwavering · unparalleled · ever-evolving · fast-paced · authentic (T3) · truly · "tragically" (11x) · notably · effortlessly · "remarkable" · "invaluable" · "essential" (T3) · "powerful" (T3)

### 1D. Transitions and connectives (T2; T1 when sentence-initial in a post under 100 words)
Additionally · Moreover · Furthermore · However (sentence-initial) · Conversely · Notably · Ultimately · Subsequently · Thereby · Overall · In conclusion · In summary · Finally · That said · In other words / Put differently (Claude "Restatement Gloss") · To be clear · "In essence" · "At the end of the day" (T3) · "Firstly/Secondly/Lastly"
Sources: isitslop; Wikipedia; magicpost.in ("essay connectors like Moreover and Furthermore"); Velitchkov [RG].

### 1E. Throat-clearing and staged run-up (T1)
"It's important to note" · "It's worth noting" · "Here's the thing" · "The thing is" · "Let's dive in" · "Here's what you need to know" · "Honestly?" · "Real talk" · "Let's be honest" · "Let me explain" · "Here's why" · "Here's the kicker" · "But here's the twist" · "Plot twist:" · "The result?" · "The catch?" · "The truth is" · "The honest answer is" (Claude [CDF]) · "The real question is" · "At its core" · "What really matters" · "Spoiler:" · "Simply put" · "Bottom line:" [unverified as model-specific] · "Short version:" [unverified] · "TL;DR" as closer (T3)
Sources: humanizer skill (pattern 4); oliviacal #12; Velitchkov; magicpost ("The result?" −4.8% reach).

### 1F. Inflated significance and borrowed authority (T1)
"stands as a testament" · "serves as a reminder" · "plays a pivotal / crucial / significant role in shaping" (182x, GPTZero #1) · "marks a turning point" / "key turning point" · "sets the stage for" · "the ever-evolving landscape" · "the future looks bright" · "leaves a lasting impact" · "indelible mark" · "reflects a broader shift" · "underscores the importance of" · "a game-changer for" · "the future is here" · "we're just getting started" · "this changes everything" · "experts say / studies show / industry reports / observers have cited / some critics argue" · "it is believed that" · "deeply rooted" · "enduring legacy"
Sources: Wikipedia (Undue emphasis; Vague attributions); GPTZero; tweeks.io; humanizer 13/17.

### 1G. Global openers and blog clichés (T1 as first line)
"In today's fast-paced world" (107x) · "In today's digital age" · "In an era of" · "Imagine a world where" · "Picture this:" · "Have you ever wondered" · "It goes without saying" · "Everyone wants to" · "As we navigate" · "When it comes to" · "In the world of X" · "As a [role], I…" (T2) · "Ever since I was" [unverified] · "Let me tell you a story" [unverified]
Sources: GPTZero; Kernan #13; oliviacal #9/#10; Pangram ("as we [verb] the topic", "when it comes to").

### 1H. LinkedIn business buzzwords (T2; T1 for the announcement trio)
"thrilled / humbled / excited / honored to announce (share)" (T1) · "I had the pleasure of" · "we are proud to support" · results-driven · solutions-led · customer delight · differentiation · "amazing" · "unleash" · "harnessing the power of AI" · "committed to best practices" · thought leader · value-add · disrupt / reshape / shift · 10x · level up · move the needle · at scale · growth mindset · "storytelling" (T3) · "grateful for the journey" · "couldn't have done it without" · "learnings" · "circle back" · "impactful"
Sources: Forbes Coaches Council (2025-01-06); hiration.com; Trung Phan.

### 1I. Chatbot residue, placeholders, markup leaks (T1, hard fail)
"I hope this helps" · "Certainly!" · "Absolutely!" · "Great question!" · "Of course!" · "Let me know if" · "Feel free to" · "Would you like me to…?" · "Want me to…?" / "If you want, I can…" (GPT-5 trailing offer; tech.yahoo.com) · "As an AI language model" · "as of my last update / training data" · "Sure! Here's a LinkedIn post…" · "Here's a version that…" · "Option 1 / Option 2" · "[Your Name]", "[Company]", "[insert…]" · "**Hook:**", "(≈280 chars)", "Caption:" labels · literal `**bold**` asterisks or `#` headers leaking into plain text · curly quotes when the corpus uses straight ones (T3) · "Word count:" · citation artifacts (turn0search0, oaicite, [cite: 1])
Sources: Wikipedia (Collaborative communication; Markup); Originality.ai obvious sayings ("Absolutely", "Certainly" as paragraph openers); tweeks.io; humanizer 22/23.

### 1J. Hedge stack (T2 alone; T1 at three or more in one post)
typically · might · may · could potentially · arguably · "in some cases" · "generally speaking" · "it could be argued" · "some argue… on the other hand" · "to be fair" · tends to · roughly · largely · almost · "actually" (PCWorld: 15x in 11.7k words) · "rather" · "in many ways" · "often" as blanket softener · "can help to"
Sources: Kernan #11; oliviacal #6/#8; kitha #5; PCWorld; Velitchkov [RH]; humanizer 9.

### 1K. Claude-specific tics (T1 here, because the generator is Claude)
genuinely · structurally · nuanced · "the honest answer" · "in other words / put differently" · "has a name" · "the cleanest…" · "and no more" / "and nothing finer" · "This matters because" · "The deepest point" · "Better posed:" · "It would be wrong, though, to…" · "falls out of" / "follows directly" · "is correct, and it can be made precise" · "not decoration but…" · "quietly" [unverified] · "does a lot of heavy lifting" / "load-bearing" [unverified] · "the real X is Y" [unverified] · "That's the whole point" [unverified] · "worth" as in "worth sitting with" [unverified] · "the spectrum isn't widening. It's collapsing." shape · "jump scared me" style self-aware melodrama
Sources: Velitchkov "22 Claude Clichés" (linkandth.ink); Jerod Santo (2026-06); PCWorld; the-ai-corner ("loves the word nuanced, ends paragraphs with a summary sentence").

### 1L. X hook templates and engagement bait (T1)
"Unpopular opinion:" · "Hot take:" · "Confession:" · "True story:" · "Is it just me or" · "I've noticed that" · "Here's the thing:" · "Nobody is talking about this" · "Here's what nobody tells you" (−4.3% reach, magicpost) · "Stop X, start Y" (−6.7%) · "Let that sink in" · "Read that again" · "Bookmark this" / "Save this" · "Most people don't know / will ignore this" · "This is your sign" · "🧵 A thread" / "Thread below 👇" / "1/" · "Steal this" · "Reply 'YES'" / "Comment GUIDE and I'll DM you" · "Like if you agree" · "Follow for more" · "I'll follow everyone who replies" (X: 3 strikes → revenue-share removal, 2026-07-16) · "Who else…?" · "Tag someone who" · "Stop scrolling" · "PSA:" / "Friendly reminder:" / "Gentle reminder" · "Take notes" · "That's a wrap" · "Agree?" · "Thoughts?" · "What do you think? Let me know in the comments" · "Repost if this resonates" / "♻️ Repost to help someone"
Sources: voicemoat.com; tweeks.io; humanizer 2; socialmediatoday.com (X policy); newslit.org (vote/react/share/tag/comment baiting); getvyral.io.

### 1M. Model-era vocabulary (the versioning axis, from Wikipedia)
- GPT-4 era (2023 to mid-2024): Additionally, boasts, bolstered, crucial, delve, emphasizing, enduring, garner, intricate/intricacies, interplay, key, landscape, meticulous(ly), pivotal, underscore, tapestry, testament, valuable, vibrant
- GPT-4o era (mid-2024 to mid-2025): align with, bolstered, crucial, emphasizing, enhance, enduring, fostering, highlighting, pivotal, showcasing, underscore, vibrant
- GPT-5 era (mid-2025 on): emphasizing, enhance, highlighting, showcasing
- Grok (2026): causal, empirical, correlate, underscore
- Originality.ai top ChatGPT tokens (10M-word set): unique, additionally, finally, conclusion, journey, difference, certainly

## 2. Structural and rhetorical tells

| # | Tell | Detectable how | Sources |
|---|---|---|---|
| 2.1 | **Negative parallelism / contrast-flip**: "It's not X, it's Y" · "not just X, but Y" · "not only X but also Y" · "Y rather than X" · "Not X. Not Y. Just Z." · "I'm not saying X. I'm saying Y." | regex; LinkedIn flags it; −4.9% reach | Wikipedia; getvyral; magicpost; SEL; humanizer 1; Gorrie (antithesis via explicit negation is "the least subtle form") |
| 2.2 | **Tricolon / rule of three**, especially *ascending* (two short items then a longer third), forced adjective triads, three identically templated lines | count of 3-item lists; ≥2 per post | Wikipedia; Gorrie; Air Mail (200 admissions essays); getvyral; humanizer 6 |
| 2.3 | **Perfectly parallel bullet list** / "**Term:** description" bullets / emoji bullets (🚀 ✅ 💡 🔥 👉 ✨) / numbered "5 key insights" crammed into a post | list detection | Wikipedia; blakestockton #10; getvyral; oliviacal #13; kitha #3; hiration |
| 2.4 | **Hypophora / reveal bridge**: a rhetorical question answered immediately. "The result?" "Why? Because…" "The catch?" "Plot twist:" | regex `\?\s*(Because|It|The|Simple)` | getvyral ("reveal bridges"); magicpost (−4.8%) |
| 2.5 | **Em-dash as universal connector**, and spaced en-dash asides (Claude) | count per 100 words. LinkedIn posts with an em dash: 1.2% (2021) → 15.6% (2025) → 10.4% (2026, magicpost, methodology undisclosed) | Wikipedia; WaPo 2025-04-09; PCWorld (1 per 150 words flagged); humanizer 8. **[weak]**: SEL found slight positive engagement and GPT-5.1 suppresses them, so treat as a cluster member, never a solo fail |
| 2.6 | **Uniform sentence length / low burstiness** (18-24 or ~27 words each, no 2-word sentence) | coefficient of variation of sentence length < ~0.4 [threshold unverified] | kitha ("biggest 2026 tell"); Kernan #9; Pangram |
| 2.7 | **One-line-paragraph cadence throughout** (broetry), clipped lines building to a lesson | ≥80% of paragraphs are 1 sentence | getvyral; hiration; fenwick.media |
| 2.8 | **Summarizing / moralizing closer**: "In conclusion", "Ultimately…", "The lesson?", "Takeaway:", "And that's when it hit me", aphoristic ender ("a stance, not its absence"), paragraph-final summary sentence | last 2 lines restate or generalize | Wikipedia; oliviacal #11; Velitchkov [AE]; SEL ("Conclusion" strongest negative); the-ai-corner |
| 2.9 | **Hedged neutrality / both-sides / no stance** | hedge count; judge "could anyone disagree?" | kitha #5; Kernan #11; oliviacal #8; Pangram ("avoids criticizing particular viewpoints") |
| 2.10 | **Generic CTA / engagement bait** (1L) | regex | getvyral; Trung Phan; X policy |
| 2.11 | **Absence of specifics**: no proper nouns, numbers, dates, prices, product names, places; "a client", "a founder I know", "a recent study"; names default to Emily/Sarah (60-70% of AI-generated names, Pangram) | count of capitalized non-initial tokens, digits, $, %, dates | Pangram; getvyral ("generic abstraction"); Wikipedia vague attribution |
| 2.12 | **No risk taken**: nothing a reader could disagree with; uniformly positive; "balanced" | judge | Pangram; hiration ("one honest opinion a reader could disagree with") |
| 2.13 | **No first-person concrete anecdote**, or a fake "imagine you're a…" scenario, or "I once had a client" | judge | oliviacal #14; Pangram ("very bad at relating to personal experience"); Kernan #5 |
| 2.14 | **Staged run-up before the point** (1E) | regex on first 15 words | humanizer 4 |
| 2.15 | **Arguing with no one**: "I'm not saying…", "To be clear", "Don't get me wrong", "A tempting approach would be…", "It would be wrong, though, to…" | regex | humanizer 5; Velitchkov [ARR][CP] |
| 2.16 | **Sayings that sound deep**: "X is the Y of Z", "the real question is", "X becomes a trap", contrastive binary "not a style but an attractor" | judge + regex | humanizer 3; Velitchkov [CB][AE] |
| 2.17 | **Colon-reveal / suspense hook**: "has a name:", "the cleanest idea is this:", setup-colon-payload | regex `:\s*$` line ends, "has a name" | Velitchkov [CR][SH] |
| 2.18 | **Meta-signposting / self-ranking**: "The most important part:", "Here's the key insight", "This matters because", "Four caveats first" | regex | Velitchkov [MS][SRC][SS] |
| 2.19 | **Mirrored-clause symmetry / chiasmus by default**: "High X runs high Y; low X runs low Y" | judge | Velitchkov [MCS]; Gorrie |
| 2.20 | **Repeated sentence openings (anaphora by reflex)** | ≥3 consecutive sentences same first word | humanizer 7 |
| 2.21 | **Stacked qualifiers and hyphenated compounds** ("data-driven, end-to-end, high-quality, cross-functional") | count | humanizer 9/10 |
| 2.22 | **Copula avoidance**: "serves as / stands as / functions as / boasts / features / represents" in place of "is/has" | regex | Wikipedia; humanizer 18 |
| 2.23 | **Shallow -ing riders**: "…, highlighting the importance of / ensuring / reflecting / fostering…" | regex `, (highlighting|underscoring|ensuring|reflecting|fostering|showcasing|emphasizing)` | Wikipedia; humanizer 15; makeuseof ("tailing clauses") |
| 2.24 | **False range**: "from X to Y" across a non-spectrum ("from intimate gatherings to global movements") | regex + judge | Wikipedia via beutlerink |
| 2.25 | **Elegant variation** (synonym cycling to avoid repeating a noun) | judge | **[unverified in fetched excerpt]**, attributed to the Wikipedia page TOC |
| 2.26 | **Over-polish**: zero typos, no fragments, no sentence-initial And/But, no contractions, Oxford commas, American spelling, curly quotes | contraction ratio; straight against curly quotes | Pangram; kitha #2; Kernan #8. **[weak]** per P2/P3: never fix this by injecting typos |
| 2.27 | **Formatting decoration**: bold as decoration, Title Case Headings, emoji headers, arrows →, horizontal rules, hashtag pile | count | Wikipedia; humanizer 19/20; hiration; fenwick |
| 2.28 | **Person lock**: all 2nd person or all 3rd person, never switching to "I" | judge | Kernan #3 |
| 2.29 | **Colon in title/hook**: "X: Why Y Matters" | regex | Kernan #12 |
| 2.30 | **Curiosity-gap opener**: "Here's what nobody tells you", "Stop X. Start Y." | regex | magicpost |
| 2.31 | **Forced parable**: a mundane event (tree, marathon, Uber ride, kid's question) carrying an oversized business lesson | judge | hiration; Trung Phan |
| 2.32 | **Symmetric paragraph blocks**, every paragraph the same length, "perfect rectangles" | paragraph-length CV | oliviacal #3; Pangram |
| 2.33 | **Length inflation**, long technically-correct sentences (>35 words) | count | PCWorld #3 |
| 2.34 | **Passive voice with a missing actor** | judge | humanizer 11 |
| 2.35 | **Validate-then-promise**: "That's right, and it can be made precise" | regex | Velitchkov [VP] |
| 2.36 | **Deflating tail clause**: "…and no more." "…and nothing else." | regex | Velitchkov [DT] |
| 2.37 | **Would-fit-under-any-post**: swap the topic noun and the post still reads fine. The single most useful holistic check. | judge | tweeks.io ("replies that would fit unchanged under any post were probably generated"); Pangram ("could fit a wide variety of possible prompts") |

## 3. LinkedIn-specific clichés

| Cliché | Shape | Source |
|---|---|---|
| **Broetry** | one sentence per line · clickbait first line before "…see more" · hero's-journey anecdote · cliché lesson · hashtag pile (coined by Bloomberg's Lorcan Roche Kelly; popularized by Josh Fechter, 2017; LinkedIn later banned him) | fenwick.media; Trung Phan |
| "I'm humbled / thrilled / excited / honored to announce" | fake humility announcement | Forbes; hiration; Trung Phan |
| "Agree?" / "Thoughts?" / "Repost if this resonates" / "Comment YES" | comment-bait closer | Trung Phan; getvyral |
| Fake vulnerability | "I failed first, but then…" · "I got rejected 47 times" · "this taught me humility" · vulnerability with no actual cost | Trung Phan; Kernan; hiration |
| Forced parable | "My 6-year-old / my Uber driver / a tree in a storm taught me about leadership" | Trung Phan; hiration. "Uber driver" specifically: [unverified as documented, folk-known] |
| "I asked ChatGPT to…" + screenshot | AI-about-AI filler | [unverified as documented; user-supplied] |
| Curiosity gap | "Here's what nobody tells you about…" (−4.3%), "Stop X. Start Y." (−6.7%), "The result?" (−4.8%), "It's not X, it's Y" (−4.9%) | magicpost (methodology undisclosed) |
| Emoji bullets and rocket clusters | 🚀 ✅ ✨ 💡 used uniformly | hiration; getvyral |
| Buzzword density without data | Shift / Reshape / Disrupt / Synergy | hiration |
| "3 lessons / 5 things I learned / 7 mistakes" listicle | numbered insights | kitha; oliviacal |
| "Normalize X" / "This is your reminder that" / "Be the person who" | motivational imperative | [unverified as documented; widely mocked] |
| Gratitude paragraph | "couldn't have done it without this amazing team, grateful for the journey" | Forbes; Trung |
| "P.S." engagement line, "♻️ repost to help someone in your network" | closer bait | getvyral |
| Hashtag pile | #leadership #growth #mindset #ai | fenwick |
| "X months at Company" with lessons | hero arc | Trung |
| "Unpopular opinion:" followed by a universally popular opinion | fake edge | voicemoat; folk |

LinkedIn's own line (CPO, July 2026): "AI and slop are not the same thing". The target is low-effort generic output,
and reader flags cut reach (getvyral). Originality.ai, July 2026: 81.2% of 5,000 public 100+-word posts "Likely AI".

## 4. X-specific tells

1. **Reply-bot register**: "Great point!", "This is so true", "Couldn't agree more", "Well said", "Fascinating!", "Spot on" · restates the OP · references nothing specific in the post · customer-service tone · ends with a question ("What's your take?") · would fit under any post. X removed 42,000 AI-reply accounts and 1.7M bots in 2026; detection is timing regularity plus phrasing similarity plus velocity. (tweeks.io; fireply.ai; startupfortune.com)
2. **Hook templates** (1L): "Unpopular opinion:", "Hot take:", "Confession:", "Nobody is talking about this", "Here's the thing:". Voicemoat: these "were sharp two years ago and now read as noise."
3. **Engagement-bait solicitation**: "Like if you agree", "Reply YES", "Bookmark this", "Read that again", "Let that sink in", "Follow for more", "I'll follow everyone who replies". X policy 2026-07-16: 3 solicitations means creator-revenue removal plus a suspension referral. (socialmediatoday)
4. **Thread formula**: "🧵", "A thread 👇", "1/", "10 lessons from…", "Steal my prompt", "That's a wrap", TL;DR closer.
5. **Essay formatting in a tweet**: numbered list with bold headers, Title Case headings, "In conclusion", exactly-three-item lists, curly quotes. (tweeks.io)
6. **Uniform cadence**: 18-24-word sentences, zero fragments, zero lowercase, no slang (ngl, tbh, lol, imo, rn), perfect punctuation. (kitha; Pangram)
7. **Suspicious timing**: replies within seconds, around the clock, flawless paragraphs across dozens of threads. (kitha #6)
8. **Emoji clusters** 🚀🔥💯 and pointing 👇; **hashtag stuffing**, since tech-X humans rarely hashtag [second half unverified].
9. **Slang register mismatch**: "It's giving…", "lowkey", "cope", "ratio" used slightly wrong or over-explained [unverified, observational].
10. **Over-complete grammar** in a 40-word post: full subject-verb-object every sentence, no ellipsis, no trailing "…", no "anyway" [unverified].
11. **Hedged neutrality** where X rewards a take: "some argue… others…". (kitha #5)
12. **"Not X. Not Y. Just Z."** three-fragment punch, rule-of-three and negation at once, so it is doubly flagged. (oliviacal #4)

## 5. What high-performing human posts do instead

| # | Behavior | Evidence |
|---|---|---|
| H1 | **Specificity you can verify**: real names, numbers, dates, dollar amounts, product and version names, file paths, error messages, screenshots. AI "tries extremely hard to avoid proper nouns." | Pangram; Ship 30 for 30 ("specificity is clarity"); hiration ("one real datapoint, one honest opinion, one scar") |
| H2 | **A stance someone could disagree with**, and a willingness to criticize a named thing | hiration; Pangram; kitha |
| H3 | **Burstiness**: a 3-word sentence next to a 40-word one; fragments used with intent | kitha; Pangram; proofreaderpro |
| H4 | **Write like you talk**: would I say this to a friend; read it aloud | Paul Graham "Write like you talk" (paulgraham.com/talk.html) |
| H5 | **A concrete first-person anecdote with a cost**, a scar from doing the work, not a parable | hiration; Pangram; Trung Phan (contrast) |
| H6 | **End on the last concrete fact**, not a moral | humanizer 13 |
| H7 | **Register mixing**: slang next to technical terms; sentence-initial And/But; contractions | realtext.org; Pangram (AI rarely uses contractions) |
| H8 | **Person switching mid-post** (you → I → we) | Kernan #3 |
| H9 | **Consistent, recognizable mannerisms across posts**, a character | Kernan #10 |
| H10 | **Unexpected concrete comparisons** from another domain, not "X is the Y of Z" | humanizer 3 (contrast); [craft guidance, unverified] |
| H11 | **Mid-sentence tonal shift / bathos**: a serious setup deflated by a petty specific | [craft guidance, unverified]; Jerod Santo notes Claude fakes "self-aware melodrama", so a judge has to check the deflation lands on a *specific* |
| H12 | **Inside references** to scene lore: named people, drama, tools, prices | [craft guidance, unverified]; consistent with kitha #4 |
| H13 | **Imperfection that is real, not decorative**: mixed feelings, odd asides, dated references | humanizer boundaries list |
| H14 | **Corpus-relative**: whatever the ingested high-performers do often is allowed, per P6 | Wikipedia; coevolution paper |

## 6. Scoring

Atomic checks, each reported with its quoted evidence, and a gate derived from them rather than a blended score.
Deterministic first (no LLM), then judges. The deduction weights live in `evals/rubric/v1/thresholds.yaml` and the
judge protocol in `.claude/skills/post/references/judge_protocol.md`.

### 6.1 Hard fails (any one rejects, with the quoted span returned to the generator)

| ID | Check | Detection |
|---|---|---|
| HF-1 | Chatbot residue / placeholders / markup leak (1I) | regex |
| HF-2 | Contrast-flip: "it's not X, it's Y" / "not just X, but Y" / "Not X. Not Y. Just Z." | regex |
| HF-3 | Engagement-bait CTA or solicitation (1L, 2.10), including "Agree?", "Thoughts?", "Let that sink in", "Read that again", "Follow for more", "Comment YES" | regex |
| HF-4 | Global-opener cliché or stale hook on line 1 (1G, "Unpopular opinion:", "Hot take:", "Here's what nobody tells you") | regex on line 1 |
| HF-5 | Zero specifics: a post over 40 words with no proper noun, number, date, price or product name | token counter |
| HF-6 | Moralizing or summarizing closer in the last 2 lines ("In conclusion", "Ultimately", "The lesson", aphoristic ender, "And that's when it hit me") | regex + judge |
| HF-7 | Lexical cluster: ≥3 T1 hits, or ≥5 hits across tiers, or ≥2 Claude-specific (1K) hits | regex with tiers |
| HF-8 | ≥2 tricolons, or any "**Term:** description" or emoji-bullet list, or a numbered "N key insights" | regex |
| HF-9 | Forced parable or fake-vulnerability arc (2.31, section 3) | judge |
| HF-10 | "humbled/thrilled/excited/honored to announce" unless an announcement post was asked for | regex |
| HF-11 | Would-fit-under-any-post: the judge swaps the topic noun and the post still reads as complete | judge |

### 6.2 Corpus-relative downgrade

Before scoring, compute each check's base rate on the ingested corpus. Any check whose corpus base rate is above 25%
drops one level: a hard fail becomes a deduction, a deduction is halved. Log every downgrade. This is P6 made
mechanical, and it is why the golden set carries two posts (P2, P4) that trip a hard regex and still have to pass.

Refresh the word tiers about every 6 months (P5): drop words whose corpus-to-AI ratio has collapsed, such as "delve",
and add the tics of whatever model generation is current.

## 7. Test posts for the judge

### 7.1 Five "AI slop" posts (expected: REJECT; expected hard fails listed)

**S1 (LinkedIn)**
> In today's fast-paced world, AI isn't just a tool—it's a mindset. 🚀
> Here's what nobody tells you about building with LLMs:
> ✅ It's not about the model, it's about the workflow.
> ✅ It's not about speed, it's about clarity.
> ✅ It's not about replacing people, it's about empowering them.
> The result? Teams that move faster, think deeper, and build better.
> Agree? Let me know in the comments. 👇 #AI #Leadership #Innovation
Expected: HF-2, HF-3, HF-4, HF-5, HF-6, HF-7, HF-8.

**S2 (X)**
> Unpopular opinion: most founders don't have a product problem, they have a focus problem.
> Not more features. Not more funding. Just relentless prioritization.
> Read that again.
Expected: HF-2 ("Not X. Not Y. Just Z."), HF-3, HF-4, HF-5.

**S3 (LinkedIn, Claude-flavored)**
> The honest answer is that most "AI strategies" aren't strategies at all. They're a stance, not its absence.
> Structurally, what companies call adoption is closer to ornamentation—a genuinely nuanced distinction, and one worth sitting with.
> This matters because it shapes everything that follows. Put differently: the real question isn't whether to use AI. It's what you're willing to stop doing.
Expected: HF-2, HF-5, HF-6, HF-7 (≥2 Claude tics: honest answer, structurally, genuinely, nuanced, put differently, this matters because), plus the em-dash density deduction (2.5).

**S4 (X, reply-bot)**
> Great point! This is so true. AI is truly transforming how we work, and it's important to note that the human element remains crucial. Thanks for sharing your insights—what's your take on where this goes next?
Expected: HF-1 ("thanks for sharing", residue register), HF-5, HF-7 (truly, transforming, it's important to note, crucial, insights), HF-11.

**S5 (LinkedIn, fake vulnerability)**
> Three years ago I got rejected from 47 jobs.
> I was humbled. I was broken. I was lost.
> Then a mentor said something that changed everything: "Your network is your net worth."
> Today, I'm thrilled to announce I've joined an amazing team as Head of Growth.
> The lesson? Rejection is redirection.
> Grateful for the journey. ♻️ Repost if this resonates.
Expected: HF-3, HF-6, HF-8 (tricolon), HF-9, HF-10.

### 7.2 Five "human" posts (expected: PASS)

Synthetic, written to the section 5 rubric. The real oracle set is the ingested corpus; these are smoke tests.

**P1 (X)**
> spent 4 hours yesterday getting ffmpeg to output VP9 with alpha for a TV loop. the flag is `-pix_fmt yuva420p`. that's it. that's the post. four hours.
Passes: specifics (ffmpeg, VP9, flag, 4 hours), burstiness, fragment with intent, no CTA, ends on a fact. One-line paragraphs but under 40 words.

**P2 (LinkedIn)**
> We paid $1,140 last month for an "AI SDR" that booked 2 meetings. Both were with people who already had a call scheduled with us. I asked the vendor for the prompt it uses and they said it was proprietary. It was 11 lines. I know because it leaked in an error message. Anyway we now run it in a Claude Code skill for $0 and it booked 5 in two weeks, one of which was actually new. Not a success story. Just cheaper.
Passes: numbers, prices, a named tool, a disagreeable claim about a category, a scar, register mixing ("Anyway"), ends on a deflating specific. The closing "Not X. Just Y." trips HF-2's regex: this is the calibration case where the contrast corrects a belief the reader actually holds (humanizer exception), so the jury should override and the hit is logged as a known regex false positive.

**P3 (X)**
> every "we're building the Cursor for X" pitch this week: X = lawyers (3), X = accountants (2), X = Cursor (1, unironically)
Passes: specific counts, inside joke, no hedging, no CTA, unexpected turn on a specific.

**P4 (LinkedIn)**
> Hot take nobody asked for: the reason your RAG demo works and your RAG product doesn't is that your demo has 40 documents and your customer has 40,000, and 39,000 of them are the same PDF re-uploaded by 6 people in 2019. Dedup before you touch an embedding model. I learned this after we shipped to a bank and their "AI" confidently cited a 2014 policy that had been rescinded 4 times.
Passes: numbers, date, a concrete failure, actionable and disagreeable. The opener "Hot take" trips HF-4's regex. Second known false-positive calibration case: the phrase is subverted ("nobody asked for"), so the jury decides, and if the corpus base rate for "hot take" is above 25% HF-4 auto-downgrades. Swapping the opener makes it pass cleanly.

**P5 (X)**
> Claude Code wrote a 900-line migration, ran the tests, they passed, and then it wrote "Note: I have not verified these tests exercise the new code path." Reader, they did not. Best coworker I've ever had. Would not let it near prod alone.
Passes: named product, concrete number, real quote, mid-post tonal shift landing on a specific, an opinion, no closer moral, no CTA.

## 8. Known unreliable indicators (never score these alone)

From Wikipedia "Ineffective indicators" and Russell: fancy or low-frequency vocabulary by itself · perfect grammar ·
formal or neutral tone · a single em dash · a single "delve" (regional-English bias, since Nigerian English uses it
natively; the Paul Graham incident, April 2024) · length · Oxford comma or American spelling · bullet lists in a post
whose corpus uses them · one tricolon.

## Sources

- Wikipedia, "Signs of AI writing" (WikiProject AI Cleanup): https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
- Secondary summaries of the Wikipedia guide: https://www.beutlerink.com/blog/how-to-spot-ai-writing · https://www.makeuseof.com/wikipedia-best-ai-writing-detection-guide/ · https://www.blakestockton.com/p/takeaways-from-wikipedias-signs-of-ai-writing-2 · https://humanizeai.com/blog/wikipedias-signs-of-ai-writing-list-plus-a-prompt-you-can-turn-into-a-skill/
- blader/humanizer Claude Code skill (25 patterns, boundaries): https://github.com/blader/humanizer (raw SKILL.md fetched)
- GPTZero AI vocabulary (3.3M texts; top-10 multipliers): https://gptzero.me/ai-vocabulary · https://gptzero.me/news/most-common-ai-vocabulary/
- Originality.ai obvious ChatGPT sayings (10M words): https://originality.ai/blog/obvious-chatgpt-sayings
- Originality.ai LinkedIn studies: https://originality.ai/blog/linkedin-ai-study-engagement (Jan 2026, 53.7%, engagement by sector) · https://originality.ai/blog/ai-content-published-linkedin (Jul 2026, 81.2%)
- Pangram: https://www.pangram.com/blog/comprehensive-guide-to-spotting-ai-writing-patterns · https://www.pangram.com/blog/russell (expert against non-expert detection)
- Search Engine Land, "The AI writing tics that hurt engagement" (Gnuse, 2026-02-25): https://searchengineland.com/ai-writing-tics-engagement-study-470051 (403 on fetch; summarized via https://www.seoteric.com/which-ai-writing-tics-actually-hurt-engagement-and-what-marketers-should-do-about-it/)
- LinkedIn "Seems like AI slop" (2026-07-30): https://www.getvyral.io/blog/linkedin-ai-slop-button-2026 · https://www.techradar.com/pro/linkedin-is-finally-set-to-crack-down-on-ai-slop-and-my-sanity-might-be-saved · https://www.engadget.com/2174163/linkedin-doesnt-want-your-ai-slop-anymore/
- LinkedIn em-dash data and reach-damaging templates (methodology undisclosed): https://magicpost.in/blog/em-dash-ai-sign-linkedin
- LinkedIn AI-slop backlash: https://www.hiration.com/blog/ai-slop-linkedin/
- Broetry: https://fenwick.media/rewild/magazine/dead-broets-society-behind-the-strange-story · https://www.readtrung.com/p/why-is-linkedin-so-cringe
- LinkedIn clichés: https://www.forbes.com/councils/forbescoachescouncil/2025/01/06/stop-using-these-cringey-clichs-in-your-linkedin-posts/
- X detection: https://www.kitha.co/blog/how-to-detect-ai-generated-tweets · https://www.tweeks.io/blog/what-is-ai-slop · https://fireply.ai/blog/x-reply-bots-2026 · https://startupfortune.com/x-removes-42000-ai-reply-bot-accounts-and-the-warning-to-growth-marketers-is-impossible-to-ignore/
- X engagement-bait policy (2026-07-16): https://www.socialmediatoday.com/news/x-updates-its-engagement-bait-detection/825495/ · https://newslit.org/news-and-research/what-is-engagement-bait/
- X hook templates going stale: https://voicemoat.com/blog/best-chatgpt-prompts-for-twitter
- Rhetorical devices (antithesis, tricolon): https://www.deadlanguagesociety.com/p/rhetorical-analysis-ai · https://airmail.news/issues/2025-12-6/in-defense-of-the-em-dash · https://www.washingtonpost.com/technology/2025/04/09/ai-em-dash-writing-punctuation-chatgpt/
- Claude-specific: https://www.linkandth.ink/p/catalog-of-claude-cliches · https://jerodsanto.net/2026/06/claudes-writing-style-has-me-on-edge/ · https://www.pcworld.com/article/3179916/claude-ranked-my-sounds-like-ai-writing-habits.html · https://www.the-ai-corner.com/p/claude-best-practices-power-user-guide-2026
- GPT-5 trailing offers: https://tech.yahoo.com/ai/articles/fixed-most-annoying-thing-chatgpt-221143236.html
- Writer lists: https://seanjkernan.substack.com/p/13-signs-you-used-chatgpt-to-write · https://www.oliviacal.com/post/ai-writing-tells · https://isitslop.io/ai-words-and-phrases/
- Academic vocabulary studies: https://aclanthology.org/2025.coling-main.426/ (COLING 2025, 21 focal words) · https://www.science.org/doi/10.1126/sciadv.adt3813 (Kobak et al., delve 28x) · https://arxiv.org/html/2502.09606v2 (human-LLM coevolution)
- Paul Graham: https://paulgraham.com/talk.html · delve incident: https://x.com/paulg/status/1777035484826349575
- Ship 30 for 30 specificity: https://www.ship30for30.com/the-22-laws-of-digital-writing
- Human against AI writing features (H3 burstiness, H7 register mixing): https://realtext.org/en/blog/ai-vs-human-writing.html · https://proofreaderpro.ai/blog/what-is-burstiness-ai-writing
