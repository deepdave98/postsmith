# Persona interview: question bank

How to use this file: one section per batch of one to three `AskUserQuestion` calls. Ask the goal, not the list; the questions below are angles on the goal, and the "why" tells you when an answer is good enough to move on. Every example under "good answer looks like" is an invented shape to show the level of specificity wanted; never copy an example into the persona.

Contents: 1 Who I am · 2 Fact bank · 3 Story bank · 4 Can / cannot claim · 5 Opinions · 6 Lane and audience · 7 Voice choices · 8 Vocabulary · 9 Comfort levels and targets · 10 Lens preferences · 11 Platform choices · 12 Media · 13 Self-writing samples · 14 The rewrite exercise

## 1. Who I am and what I see daily
Why it matters: the angle taxonomy's strongest family is Receipt, and receipts come from what someone actually sees every day. A writer who knows Deep runs data-enrichment pipelines for RevOps teams can find a `for_narrow_x` angle on any launch; a writer who knows "founder, AI" cannot.
- What do you do, in one sentence a peer would say about you (not a bio line)?
- What do you look at most days: which dashboards, logs, customer calls, tools, error queues?
- What do you know the inside of that most people in your feed only know the outside of?
- What did you do before this that still shapes how you read the news?
Good answer looks like: "I run the enrichment pipeline at a 9-person data startup; most mornings I read the failed-jobs queue and two customer Slack channels; I know what a 'verified email' actually costs to produce."

## 2. Fact bank
Why it matters: G3 of the quality bar (a detail only this author could supply) and G4 (every fact sourced) are gates. Non-round numbers with dates beat round ones; the number is the punchline in half the good posts in the corpus. Each entry must be usable inside one sentence without a follow-up question.
- Numbers you know by heart: volumes, costs, error rates, latencies, headcount, revenue-ish figures you can publish, dates things shipped or broke.
- Customers or customer types you may name, and what they actually asked for.
- Tools you pay for, what they cost, which you dropped and why.
- Incidents: the outage, the bad bill, the model that regressed, the migration that took three weekends.
- Benchmarks you ran yourself, with the sample size.
Follow-ups: "what is the exact number?", "what month?", "can that appear in public under your name?".
Good answer looks like: "F3 (2026-08): we rerun about 1,214 extraction jobs a week; on the last model swap 31 improved and 4 got worse | source: prod job logs | public: yes".
Reject: "we process a lot of data", "our accuracy is high", any number Deep is estimating on the spot without saying so (mark estimates as `approx` or leave them out).

## 3. Story bank
Why it matters: story openers are the best-performing hook family in the data, and a story is only usable if it is true, first-hand and dated. `used_in:` keeps a story from repeating inside 60 days. Three good stories are worth more than twelve vague ones.
- Something that happened at work in the last 90 days that made you change your mind.
- A customer conversation you still think about.
- A time you were wrong in public or in front of the team.
- The most expensive mistake you made with a tool or a model.
- Something absurd that happened because of a process, a vendor or a model.
For each: when (date), who was there (named only if publishable), what happened, what it cost or changed. Two to four sentences, no moral.
Good answer looks like: "S2 (2026-07-14): a customer asked if we'd switched models because their weekly report looked 'more confident'. We hadn't. The prompt had been edited by an intern on the 11th. Took two days to find | used_in: []".

## 4. Can claim / cannot claim
Why it matters: `judge-persona` applies these two lists verbatim; a candidate whose claim maps to nothing here scores 3 (needs confirmation) and one that contradicts `cannot_claim` scores 1 (hard fail). The lists let writers be bold where Deep is entitled to be and stop them where he is not.
- What can you say you have done or measured, in first person, without hedging?
- What have you *not* done that people in your position often claim (raised a round, scaled to N users, run models at scale, hired a big team)?
- Which companies, people or products must never be described from the inside?
- Which numbers are confidential even if you know them?
Good entries: can_claim "I've run the same extraction batch through four model versions since March"; cannot_claim "that we have enterprise customers (we have SMBs)", "anything about a specific customer's revenue".

## 5. Opinions held / refused
Why it matters: G2 (a claim a smart reader could disagree with) is a gate, and `judge-persona` checks every opinion against these lists; an opinion Deep refuses is a hard fail. Held opinions give writers their stance; refused opinions stop them from borrowing a reference author's.
- Three things you believe about your field that a smart peer would argue with.
- Which popular takes in your feed do you think are wrong, and why in one sentence?
- Which takes are you often *expected* to hold but do not (state them as refusals)?
- What would you never say even if it would do numbers?
Good answer looks like: held "benchmark gains do not reach a product for months because of eval debt, and I can show ours"; refused "that AI will replace SDRs", "hustle-culture takes about hours worked".

## 6. Lane and audience
Why it matters: `/trending` searches inside the lane; writers pick `for_narrow_x` angles from the audience; a post outside the lane is regret risk for the followers Deep wants.
- Who do you want reading and replying: their job, company size, what they are deciding this quarter?
- Which topics are inside your lane, which are adjacent (comment on, never lead with), which are out?
- Who are the five people whose posts your target reader already follows?
Good answer looks like: "audience: RevOps and data leads at 20-200 person B2B companies deciding what to build vs buy for enrichment; lane: data quality, model swaps in production, pricing of AI tooling; adjacent: agents, hiring; out: politics, crypto, productivity hacks".

## 7. Voice choices
Why it matters: `style/common.md` lists the traits on which the reference authors split (divergent traits). These are choices, and a candidate is judged on Deep's choice, not the lens author's. Ask one row at a time with options; each answer goes into the `## Voice choices` table with a one-line reason or example.
Default trait list when `common.md` does not exist yet: casing (lowercase / cased); sentence length (short and clipped / mixed / long); paragraphing (one line per paragraph / mixed); contractions (always / sometimes); profanity (none / mild / free); em dashes (never / rare / freely); emoji (never / one at most / freely); questions to the reader (never / rare); exclamation marks (never / rare); first person vs second person; story-led vs take-led; humor register (deadpan / warm / none); how he addresses the reader (peer / student / nobody).
Good answer looks like: "cased, short sentences, no em dashes (I never type them), no emoji, one joke at most and it has to be deadpan, I talk to peers not juniors".

## 8. Vocabulary
Why it matters: `not_ai` and `register_match_self` both read word choice; `style/lexicon.yaml` already bans model tells, so this section captures Deep's own words and his personal bans (which `/rate` grows as `user_tells`).
- Words and phrases you actually use in Slack that a model would not (slang, in-jokes, shorthand, Hinglish if any).
- Words you would never use in public even though your industry does ("synergy", "leverage", "journey", "excited to announce").
- How you name your own product and company in text (exact spelling, capitalization).
Good answer looks like: use "ship it", "the queue", "fine, it's fine"; never "delve", "game-changer", "thrilled", "learnings".

## 9. Comfort levels and targets
Why it matters: humor that punches down fails the joke tests; `do_not_target` is applied by `judge-persona` as a hard rule; `too_mean` is a rating tag that maps to `regret_risk`.
- How far can a post laugh at you? Give an example of a self-deprecating line you would post and one you would not.
- Profanity: none, mild, anything?
- Companies you are happy to needle (big platforms, vendors) and ones you must not (partners, customers, investors, former employers).
- People or groups never to target (juniors, job seekers, named individuals, competitors' employees, specific communities).
Good answer looks like: "self-deprecation yes if the post also shows I know what I'm doing; mild profanity ok on X, none on LinkedIn; needle OpenAI/Google/LinkedIn itself; never partners, never named people, never job seekers".

## 10. Lens preferences
Why it matters: the matrix assigns author lenses to writers 2 and 3; a lens Deep finds grating produces posts he will never paste, which wastes a run.
- Of the reference authors in `style/authors/`, whose mechanics do you want borrowed most, whose least, and any you want only for X or only for LinkedIn?
- Any author whose *topics* you must avoid even if their moves are good (a competitor, a friend)?
Good answer looks like: "acosta for LinkedIn structure; puri for X deadpan; never welsh's carousels; skip anyone who posts about hiring".

## 11. Platform choices
Why it matters: `platform_check.py` reads `platform_choices` (hashtags, emoji, long posts) as hard gates; X long posts are only allowed on Premium and only when the first 280 characters end at a sentence boundary; a CTA is bait unless the persona opts in.
- X: Premium or not (free accounts get a median of under 100 impressions; the research says Premium is a precondition)? Long posts ever? One-liners as a variant?
- LinkedIn: hashtags (default 0), emoji (default 0), long posts, closing questions ever?
- Cadence you will actually keep (posts per week per platform), and what time of day you can reply for the first hour.
Good answer looks like: "X Premium yes; no long posts; one-liners yes; LinkedIn 0 hashtags, 0 emoji, no closing questions; 2 LinkedIn + 5 X per week; I can reply 9-11am IST".

## 12. Media
Why it matters: the media-director needs to know whether `real_capture_direction` (a real screenshot) and `user_photo_direction` (a phone photo of Deep) are options; they beat generated images on LinkedIn and can never be faked for a real product.
- Will you take a phone photo of your desk, whiteboard, team, screen when a post calls for it?
- Will you appear on camera or in a photo?
- May posts include real screenshots of your own product and dashboards (with what redacted)?
- Which of your brands may appear in a generated visual (`brands`), and which other spellings of your name (`aliases`)?
Good answer looks like: "photos yes, camera no, screenshots of our dashboard yes with customer names blurred; brands: [Floqer]".

## 13. Self-writing samples
Why it matters: `register_match_self` is the voice gate and is N/A below 5 samples; the envelope check uses the `self` scope only once it exists; until then every run is optimized toward the reference authors. Words count, not posts: 1,500 words of Slack messages carry more register than two polished posts. Excluded: anything a model wrote or rewrote, because it would teach the system a model's register as Deep's.
Ask for: 10-30 Slack or WhatsApp messages longer than two lines; 3-5 emails or memos he wrote without help; any past posts (with dates and platform); a Claude chat where *his* side was typed at length (his turns only).
Before pasting: strip names of private people, customer names under NDA, credentials, and anything he would not want quoted in `style/self.md`.

## 14. The rewrite exercise (20 minutes)
Why it matters: paired register data. The original and Deep's rewrite share a subject and a shape, so every difference is register: sentence length, casing, how he addresses the reader, what he cuts, where he puts the number. `style/self.md` gets a section per pair.
Pick three train posts (`corpus/posts/`): different authors, at least one X post, none longer than ~1,200 characters, none that require facts Deep does not have. Show each and ask: "say this the way you would say it to a peer; keep the subject, use your own words, and if it needs a number you do not have, write [n]". No time to polish; five to seven minutes each. Label each block `rewrite_of: <post_id>`. Nothing in a rewrite is a receipt; it never enters the fact bank.
