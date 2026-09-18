# X (Twitter) mechanics (researched 2026-09-17)

Provenance for the `platforms.x` limits in `config/postsmith.yaml` and the X ops notes in the README. The ranking
weights below are a snapshot of a file that changes weekly, so re-read it before relying on a number. The rules
themselves live in `evals/rubric/v1/`.

Tags: **[P]** primary source fetched (X code, legal page, peer-reviewed paper) · **[S]** reputable secondary
(Buffer/Hootsuite data, TechCrunch/SMT reporting) · **[U]** unverified blog claim or an X post seen only as a search snippet.

## 1. Hard limits (2026)

| Item | Value | Source |
|---|---|---|
| Post, free | 280 chars | [S] https://support.typefully.com/en/articles/8717699-twitter-x-posting-limitations |
| Long post, any Premium tier (Basic/Premium/Premium+) | 25,000 chars; timeline shows first ~280 + "Show more" | [S] Typefully (above); https://fmax.io/blog/twitter-character-limit-2026 |
| Articles (rich formatting) | 100,000 chars; opened to all Premium tiers 2026-01-07 (was Premium+ only) | [S] https://ppc.land/x-opens-articles-to-all-premium-users-ending-exclusive-pricing-tier/ ; https://techcrunch.com/2024/03/08/x-allows-premium-users-and-organizations-to-publish-articles/ |
| Thread length | up to 50 posts | [S] Typefully |
| Media per post | 4 images OR 1 video OR 1 GIF; alt text 1,000 chars | [S] fmax.io; https://publishq.com/twitter-limits |
| Video | free 2:20 / 512 MB; Premium up to 4 h / 8 GB | [S] https://www.nemovideo.com/blog/twitter-video-specs-guide-2026 (not cross-checked against help.x.com, which is Cloudflare-blocked) |
| Polls | 2–4 options, 25 chars each | [S] publishq |
| Daily caps, non-Premium | 50 original posts + 200 replies/day (May 2026), down from 2,400 | [U] https://piunikaweb.com/2026/05/17/cant-post-on-x-there-are-new-rules-for-non-premium-users/ (cites X Help Center; not fetched directly) |
| Counting rules | URLs count 23; most emoji count 2 | [U] X developer docs, not re-fetched; `tools/xcount.py` applies these |

X's own help pages returned 403 or a Cloudflare challenge to both WebFetch and curl, so the tier feature lists above
rest on secondary sources.

## 2. Ranking mechanics (primary source)

Repo: https://github.com/xai-org/x-algorithm (Apache 2.0, first released 2026-01-19/20; runnable end-to-end stack
added 2026-05-15). `Final Score = Σ (weight_i × P(action_i))`, where P comes from the Grok-based Phoenix transformer,
so the weights multiply *predicted probabilities*, not raw counts. Cron jobs sync production defaults into
`home-mixer/params/param.rs`, and that file took ~20 commits between 2026-08-13 and 2026-09-17. [P]

Snapshot 2026-09-17 of https://raw.githubusercontent.com/xai-org/x-algorithm/main/home-mixer/params/param.rs :

| Signal | Weight | Signal | Weight |
|---|---|---|---|
| ShareViaCopyLink | 20.0 | Click (open post / "Show more") | 0.4 |
| BidirectionalFollowReplyWeightBoost (reply from a mutual) | 15.0 | OpenLink | 0.2 |
| Reply | 5.0 | VideoOpen | 0.07 |
| Quote | 5.0 | Dwell | 0.05 |
| ShareViaDm | 5.0 | PhotoExpand | 0.05 |
| FollowAuthor | 4.0 | ContDwellTime | 0.004 |
| Share | 2.0 | ProfileClick | 0.0 |
| Retweet | 1.0 | Vqv (video quality view) | 0.0 |
| Favorite | 0.5 | NotDwelled | −0.02 |
| NotInterested | −43.2 | Block | −31.2 |
| Mute | −58.8 | Report | −234.0 |

Other constants: `AuthorDiversityDecay 0.5`, `AuthorDiversityFloor 0.25` (your 2nd post in a viewer's feed batch
scores ×0.5, the 3rd and later ×0.25); `OonWeightFactor 0.75` (non-followers' feeds discount you by 25%);
`MinVideoDurationMs 10_000`; a separate dwell-regret gate running from −10,000 (not interested) to −60,000 (report);
cold-start prior Beta(0.75, 49.25) with `ColdStartMaxPostAgeSecs 172800`, so posts can surface for 48 h. No parameter
mentions bookmark, Premium, verified, thread or URL. [P]

What follows from the constants, as inference rather than measurement:

- The ordering is unambiguous even though the probabilities are not equal: the objective is conversation and
  sending-to-a-friend, not likes.
- Dwell and click weights are ~100x smaller than reply and share weights, so "write long posts for dwell time" is
  weakly supported. Length pays only when the extra text earns replies or shares.
- Any measurable rise in P(mute/not-interested/report) wipes out a post. Rage-bait math flipped after 2023.
- "Bookmark this" targets a signal with zero weight.
- The 2023 weights still circulating in 2026 blogs (reply 13.5, retweet 20, bookmark 10, author-reply-back 75/150) are
  obsolete; reposts went from 20 to 1. Those figures come from the 2023 release:
  https://www.techtimes.com/articles/316791/20260518/xais-may-15-update-makes-xs-phoenix-ranking-engine-fully-runnable-one-reply-outweighs-150-likes.htm [S]

Product statements that corroborate the file: 2026-07-13, X boosted posts and replies from mutuals, which matches the
15.0 boost: https://techcrunch.com/2026/07/13/x-just-tweaked-its-algorithm-to-make-it-more-friendly-less-battleground/ [S].
Bier's claim that the reply predictor was "the largest contributor of seeing ragebait" and got a 15x friend boost
appears only in a search snippet of https://x.com/nikitabier/status/2089763962330230803 [U]. Reply downvotes
(Premium-only; the reasons include "AI generated", "Spam", "Incorrect or misleading") feed reply ranking:
https://www.socialmediatoday.com/news/x-formerly-twitter-adds-comment-downvotes-train-algorithm-tanking/815272/ (2026-03-19) [S].

## 3. Format and account-tier data

Buffer, State of Social Media Engagement 2026 (18.8M X posts, 2025 data): median ER text 3.56% > image 3.40% >
video 2.96% > link 2.25%. X is the only major platform where text beats video, by ~20% (the "30%" figure other blogs
repeat is wrong). Free-account median ER hit 0% in the most recent months. Top-10% accounts post far more than the
median, and silent weeks underperform. https://buffer.com/resources/state-of-social-media-engagement-2026/ ,
https://buffer.com/resources/data-best-content-format-social-media/ [S]

Buffer X Premium review (18.8M posts, 71k accounts, Aug 2024–Aug 2025): median impressions free <100, Premium ~600,
Premium+ ~1,550, a ~10x gap; median ER free 0%, Premium Basic ~0.55%, Premium ~0.49%, Premium+ ~0.53%; free-account
text ~0.25% and link 0% after March 2025. Premium is a precondition, not a tactic.
https://buffer.com/resources/x-premium-review/ , https://buffer.com/resources/links-on-x/ [S]. The two Buffer reports
define ER differently, so use each only for relative comparisons.

Buffer 1.7M-post cross-platform study (early 2025): X median 4 engagements/post with SD 5,159. Expect most posts to
flop and a few to break out. https://buffer.com/resources/x-threads-bluesky-data/ [S]

Long post against thread against single: no credible 2025–26 dataset exists. Hootsuite's experiment (2024-01-31, n=6
posts, 370-follower account) had long posts at 11,846 and threads at 10,783 impressions, concluding content matters
more than format. https://blog.hootsuite.com/experiment-x-threads-vs-longform-posts/ [S]. Buffer's 2024 test (n=10)
had threads beating link-tweets. https://buffer.com/resources/twitter-thread-experiment/ [S]. "Threads get 3x"
(opentweet, socialpilot) cites nothing [U]. The structural facts: only the first post of a thread is ranked and the
mixer collapses branches of one conversation [P], so if the starter flops the rest is never distributed
(https://typefully.com/blog/x-algorithm-open-source [S]). Articles reportedly get less feed reach and paywalled ones
are "severely deboosted" (creator reports in ppc.land) [U].

Video: text still wins on median ER, but Bier (2026-04-12) calls talking-head video an "easy way to get millions of
impressions with basically no followers", and reposted third-party media gets up to −90% impressions.
https://piunikaweb.com/2026/04/13/x-twitter-original-talking-videos-nikita-bier/ [U, X post via secondary]. Videos
under 10 s do not clear `MinVideoDurationMs` [P]. "Video gets 2–4x reach" is unsourced [U].

Screenshots (DMs, charts, receipts, AI-chat) are a widely used format (https://postory.io/blog/viral-tweets [U]).
Text-as-image bypasses 280 but is unsearchable, unreadable to screen readers, and compressed harder on free accounts.
https://postory.io/blog/social-media-character-image-limits-2026 [U]

## 4. Hooks and voice on tech X

What the data supports: specificity (real numbers, real screenshots) beats generic claims, the first line decides, and
the posts that win are the ones peers reply to and send to each other, which is what the weights say. Marc Lou and
levelsio-style build-in-public works through verifiable numbers, ~15 posts/week, most under 100 reactions with rare
breakouts. https://streakr.co/playbook/marc-lou , https://captureflow.ai/playbooks/marc-louvion [U]. Levels' post on
fake MRR screenshots did 518k+ views (Indie Hackers) [U].

What is weakly supported: every hook-formula list found (postory, autotweet, metadatareactor, xholic) uses invented
examples and recycles 2021–23 thread-bro templates ("Most people think X…", "$X in Y months. Here's how:", "Unpopular
opinion:", colon-cliffhangers). Those are now the recognizable creator and AI tells, and the reply-downvote menu has
an "AI generated" button. Only 26% of consumers prefer AI-generated creator content, down from 60% in 2023, and the
reporting sums it up as "we crave imperfection". Source:
https://digiday.com/media/after-an-oversaturation-of-ai-generated-content-creators-authenticity-and-messiness-are-in-high-demand/
(2026-01-14) [S]. Recognized ChatGPT tells: "it's not X, it's Y", "in today's digital age", "dive deep", "leverage",
"it's crucial to": https://textpulse.ai/blog/ai-writing-patterns [U]. Lowercase reads as off-the-cuff and
peer-to-peer in 2025–26 https://cornflowercommunications.co.uk/2025/03/05/lowercase/ [U].

Humor mechanics: setup then punchline, punchline last, short distance between them; observation beats pun; formatting
(caps, punctuation) does the timing. https://tweethunter.io/blog/funny-tweets [U]. Contrarian takes "work for reach
but create the most volatility" (autotweet) [U], and against −43/−59/−234 negative weights they are riskier than the
blogs assume.

Hashtags: Musk, 2024-12-17: "Please stop using hashtags. The system doesn't need them anymore and they look ugly."
https://x.com/elonmusk/status/1869070358210572306 [S via multiple outlets]

## 5. Cadence and timing

- Buffer (8.7M X posts, published 2026-03-25): best Tue 9 a.m.; weekdays 8–11 a.m. audience-local; Wednesday best day;
  Saturday quietest. https://buffer.com/resources/best-time-to-post-social-media/ [S]. Sprout's 2026 data says
  12–6 p.m., which conflicts [U].
- Hootsuite: 2–3 posts/day baseline, up to 5–10 for teams, spaced 2–3 h.
  https://blog.hootsuite.com/how-often-to-post-on-social-media/ [S]
- Author-diversity decay (0.5, floor 0.25) means a viewer's feed discounts your 2nd and 3rd post in the same batch, so
  spacing matters more than volume [P]. Bier's deleted Jan 2026 thread described a finite daily reach allocation
  depleted by low-value replies ("GM" spam), preserved only in screenshots [U].
  https://dannykpolitics.substack.com/p/part-two-the-pattern-nikita-biers
- Replying to your own replies: Buffer finds ~+8% and calls it their least certain result [S]; the 2023 code weighted
  author-reply-back 75 [S, obsolete].
- "10 engagements in 15 minutes" velocity thresholds are unsourced [U].
- Auto-translate went worldwide 2026-04-07, so English posts compete against every language, and wordplay that depends
  on English spelling may not survive translation. (Bier post via snippet; Arnaud Bertrand's analysis) [U]

## 6. Risk surface (2026)

- Original Content Rewards Program replaced Creator Revenue Sharing (enrollment closed 2026-08-07, retired 2026-09-07,
  applications 2026-09-08). It excludes engagement bait ("repeatedly instructing users to engage… like, reply,
  bookmark, follow, repost"), recycled or copied content, and posts that receive a helpful Community Note. Eligibility
  is Premium + 500 verified followers + 500k verified Home Timeline impressions per 90 days.
  https://www.complex.com/pop-culture/a/markelibert/x-original-content-rewards-program-creator-payouts ; terms at
  https://legal.x.com/en/original-content-rewards-terms.html (returned 402 to fetch; wording via search snippet) [S/U]
- Engagement solicitation 3+ times means removal from the program and a possible suspension, and Grok detects it
  (2026-07-16). https://techcrunch.com/2026/07/16/x-cracks-down-on-creators-who-steal-content/ ;
  https://www.socialmediatoday.com/news/x-updates-its-engagement-bait-detection/825495/ [S]
- Habitual "BREAKING" and sensational language brings permanent payout reductions; aggregators were cut to 60% then a
  further 20% (2026-04-12). https://techweez.com/2026/04/13/x-crackdown-clickbait-creator-payouts/ [S]
- Community Notes: once a note displays, reposts fall 61.2% and the author is 94.3% more likely to delete; median
  time-to-note 18.1 h, mean 62.9 h (Nature Communications, 2026-05-05, 237,180 cascades).
  https://pmc.ncbi.nlm.nih.gov/articles/PMC13144318/ [P]. For a personal brand the cost is credibility, not reach.
- Whether engagement bait reduces *distribution* beyond monetization is undocumented. It is plausible through the
  not-interested and dwell-regret machinery, but [U].

## 7. Adapting a LinkedIn post into an X post

X rewards "punchy and informal" and LinkedIn rewards "context and a professional frame"; "wording that feels sharp on
X can feel flippant on LinkedIn"; keep the idea, change the register, never paste verbatim
(https://socialk.it/en/cross-post/x-to-linkedin [U]; https://blog.brandghost.ai/posts/repurpose-linkedin-posts-twitter-threads/ [U]).
LinkedIn broetry (one sentence per line, like-bait first line, moral at the end) is the exact thing X culture mocks
(https://www.readtrung.com/p/why-is-linkedin-so-cringe [U]).

The translation, which is our reading of the above plus the weights:

- Cut: the preamble ("I've been thinking…", "In my experience…"), credentials, the lesson paragraph, the CTA question,
  hashtags, emoji bullets, line-per-sentence formatting, any link.
- Keep: the single sharpest observation, one concrete number or the screenshot that proves it, the one specific detail
  that makes it yours.
- Shift: earnest to deadpan; "here's what I learned" to "here's the thing that happened, stated flatly, funny part
  last"; addressing an audience to talking to peers; lesson to observation. On LinkedIn the joke is the hook for a
  lesson; on X the joke is the whole post.
- Shape: one LinkedIn post becomes a one-liner (≤140), a single post (≤280), an optional screenshot post, and a long
  post only when there is real substance past the first 280 chars.

## 8. Claims to keep out of the rubric

- "Bookmark = 10x", "reply = 13.5x", "author reply-back = 150x", "Premium = 4x in-network / 2x OON" are 2023 constants
  and are not in the 2026 params.
- "url_click is omitted from Phoenix" (ppc.land) is contradicted by the README, which lists a link-click prediction,
  and by `OpenLinkWeight 0.2`. The link penalty is empirical (Buffer), not an explicit constant.
- "Threads get 3x", "video gets 2–4x", "Premium+ 25x", "hashtags penalized 40%", "10 engagements in 15 min",
  "reach halves every 6 h": unsourced blog claims.
- X help center pages, legal.x.com terms and Bier's X posts could not be fetched directly (403/402/JS). Those claims
  rest on secondary reporting.

## Sources

- https://github.com/xai-org/x-algorithm ; https://raw.githubusercontent.com/xai-org/x-algorithm/main/README.md ; https://raw.githubusercontent.com/xai-org/x-algorithm/main/home-mixer/params/param.rs ; https://raw.githubusercontent.com/xai-org/x-algorithm/main/phoenix/README.md
- https://buffer.com/resources/state-of-social-media-engagement-2026/ ; https://buffer.com/resources/data-best-content-format-social-media/ ; https://buffer.com/resources/x-premium-review/ ; https://buffer.com/resources/links-on-x/ ; https://buffer.com/resources/x-threads-bluesky-data/ ; https://buffer.com/resources/best-time-to-post-social-media/ ; https://buffer.com/resources/twitter-thread-experiment/
- https://blog.hootsuite.com/experiment-x-threads-vs-longform-posts/ ; https://blog.hootsuite.com/how-often-to-post-on-social-media/
- https://techcrunch.com/2026/07/13/x-just-tweaked-its-algorithm-to-make-it-more-friendly-less-battleground/ ; https://techcrunch.com/2026/07/16/x-cracks-down-on-creators-who-steal-content/ ; https://techcrunch.com/2024/03/08/x-allows-premium-users-and-organizations-to-publish-articles/
- https://www.socialmediatoday.com/news/x-updates-its-engagement-bait-detection/825495/ ; https://www.socialmediatoday.com/news/x-formerly-twitter-adds-comment-downvotes-train-algorithm-tanking/815272/
- https://techweez.com/2026/04/13/x-crackdown-clickbait-creator-payouts/ ; https://www.complex.com/pop-culture/a/markelibert/x-original-content-rewards-program-creator-payouts ; https://legal.x.com/en/original-content-rewards-terms.html
- https://pmc.ncbi.nlm.nih.gov/articles/PMC13144318/ (Nature Communications 2026, Community Notes)
- https://ppc.land/x-opens-articles-to-all-premium-users-ending-exclusive-pricing-tier/ ; https://ppc.land/x-exposes-algorithm-secrets/ ; https://www.techtimes.com/articles/316791/20260518/xais-may-15-update-makes-xs-phoenix-ranking-engine-fully-runnable-one-reply-outweighs-150-likes.htm ; https://typefully.com/blog/x-algorithm-open-source ; https://helloai.substack.com/p/x-just-open-sourced-its-algorithm
- https://support.typefully.com/en/articles/8717699-twitter-x-posting-limitations ; https://fmax.io/blog/twitter-character-limit-2026 ; https://publishq.com/twitter-limits ; https://www.nemovideo.com/blog/twitter-video-specs-guide-2026 ; https://piunikaweb.com/2026/05/17/cant-post-on-x-there-are-new-rules-for-non-premium-users/ ; https://piunikaweb.com/2026/04/13/x-twitter-original-talking-videos-nikita-bier/
- https://x.com/elonmusk/status/1869070358210572306 ; https://x.com/nikitabier/status/2089763962330230803 ; https://dannykpolitics.substack.com/p/part-two-the-pattern-nikita-biers
- https://digiday.com/media/after-an-oversaturation-of-ai-generated-content-creators-authenticity-and-messiness-are-in-high-demand/ ; https://textpulse.ai/blog/ai-writing-patterns ; https://cornflowercommunications.co.uk/2025/03/05/lowercase/ ; https://www.readtrung.com/p/why-is-linkedin-so-cringe ; https://socialk.it/en/cross-post/x-to-linkedin ; https://blog.brandghost.ai/posts/repurpose-linkedin-posts-twitter-threads/
- https://streakr.co/playbook/marc-lou ; https://captureflow.ai/playbooks/marc-louvion ; https://www.indiehackers.com/post/what-you-can-learn-from-marc-lou-c825413443 ; https://tweethunter.io/blog/funny-tweets ; https://postory.io/blog/viral-tweets ; https://www.autotweet.io/examples/viral-tweet-examples ; https://metadatareactor.com/blog/how-to-go-viral-on-x-twitter-2026/ ; https://www.socialpilot.co/blog/twitter-algorithm
