# LinkedIn post mechanics (researched Sept 2026)

Provenance for the `platforms.linkedin` limits in `config/postsmith.yaml`, the fold arithmetic in
`tools/platform_check.py`, and the ops notes in the README. Every number here goes stale: re-check the
dated sources before trusting one. Nothing here is a rule. The rules live in `evals/rubric/v1/`.

Tags: **[LI]** LinkedIn's own statement or paper · **[D]** third-party dataset with a stated sample ·
**[C]** creator or consultant claim, no public method · **[UNVERIFIED]** widely repeated, no traceable primary source.

## 1. Hook budget: the "…see more" fold

- **Desktop ~210 characters / ~3 lines. Mobile ~140 characters / ~3 lines.** Whichever runs out first cuts the post.
  A blank line spends one of the 3 lines. Emoji consume more than one character unit, which is why `platform_check.py`
  counts them as 2 on the fold. LinkedIn has never documented any of this and it drifts, so treat the numbers as
  approximate. [C, re-measured by several tool vendors]: https://postformatter.com/blog/linkedin-see-more-cutoff/ ,
  https://authoredup.com/blog/linkedin-character-limit , https://linkedgrow.ai/free-tools/linkedin-character-counter
- ~72% of usage is mobile (AuthoredUp, citing platform stats), so **140 is the budget that matters**.
  https://authoredup.com/blog/linkedin-algorithm
- LinkedIn's own hook guidance (Laura Lorenzetti, LinkedIn News exec editor): most interesting part at the top,
  "hook the people, tell them the payoff." [LI]: https://buffer.com/resources/linkedin-algorithm/

## 2. Length

- **Hard cap 3,000 characters**, counting spaces, line breaks and emoji. [LI]: https://www.linkedin.com/help/linkedin/answer/a528176
- AuthoredUp, 372,126 personal posts, Sep 2025–Feb 2026: **1,301–2,500 chars best** (ER 2.61–2.67%, ~1,100–1,170
  impressions, 5–6 comments) against **<400 chars at 2.10% ER, 575 impressions, 1 comment**. Performance declines
  above 2,500. [D]: https://authoredup.com/blog/linkedin-character-limit
- AuthoredUp 3M-post format study, Mar 2025–Feb 2026: text-only peaks at **1,000+ chars (1.18x reach)**, under 300
  chars 0.88x; document captions do best **short (0–100 chars = 1.28x reach)**; image captions 800–900 chars. [D]:
  https://authoredup.com/blog/best-performing-content-on-linkedin
- Van der Blom Algorithm Insights 2026, 1.3M posts: 1,250–3,000 chars "perform 228% better", yet **34% of top posts
  are under 600 chars**. Read it as bimodal: long and substantive, or short and sharp, with mid-length mush losing.
  [C, paid report, method not public]:
  https://www.linkedin.com/posts/richardvanderblom_rvdbcarousel-algorithm-insights-report-2026-activity-7455148601749729280-AwsY
- Readability: 10th-grade-plus reading level gets **~35% less reach**; aim 4th–6th grade. [D/C]:
  https://authoredup.com/blog/linkedin-algorithm

## 3. Formats

Two metrics are in play and they disagree: **reach multiplier** (impressions against your own median) and **engagement rate**.

| Format | AuthoredUp 3M posts, personal profiles, Mar 2025–Feb 2026 (reach x / engagement x) [D] | Buffer 4.8M LinkedIn posts, Mar 2026 (median ER as % of reach) [D] |
|---|---|---|
| Document/PDF carousel | **1.39x / 1.30x** ("best overall"; drives saves at 2.6x its share) | **21.77%** |
| Image (single) | 1.20x / **1.33x** (portrait 1080×1350 beats landscape by 32%) | 6.52% |
| Text-only | 1.07x / 0.78x | 3.18% |
| Native video | 0.86x / 0.93x (reach down 36% YoY; 3-min+ videos 1.21x against <30s 0.96x) | 7.35% |
| Poll | **1.78x / 0.37x** (a reach trap: votes, no comments) | n/a |
| Link post | n/a | 3.81% |
| Article | 0.69x / 0.44x | n/a |
| Reshare | 0.29x / 0.22x | n/a |

Sources: https://authoredup.com/blog/best-performing-content-on-linkedin , https://buffer.com/resources/data-best-content-format-social-media/

- Van der Blom 2025, 1.8M posts: document 6.60% ER, video 5.60%, image+text 3.2%, text 2.0%. 2026 edition:
  **infographics are 29% of the top-1% posts**; whiteboard-style and 3D-rendered carousel covers perform best. [C]:
  https://www.dataslayer.ai/blog/linkedin-algorithm-february-2026-whats-working-now , vdB 2026 post above
- Video is what LinkedIn is pushing: views +36% YoY Q1 2025, double-digit upload growth through Q1 2026, an immersive
  vertical feed. [LI]: https://www.linkedin.com/pulse/up-36-over-last-year-video-linkedin-booming-time-now-somasundaram-yqbzc ,
  https://techcrunch.com/2025/02/04/linkedin-amps-up-vertical-video-tools-as-uploads-jump-36 .
  Per-post reach for creators is not better, though: AuthoredUp and van der Blom (Feb 2025) both measure video reach
  dropping sharply. His 2026 podcast says text-only works for the top ~5% of copywriters and "99% of creators need
  visuals." [C]: https://podcast.creatorscience.com/richard-van-der-blom-2/
- Polls: LinkedIn said in 2022 it would show fewer polls and less engagement bait [LI]:
  https://searchengineland.com/linkedin-feed-less-polls-engagement-bait-384986 . The "0.07% poll ER after a March 2026
  Authenticity Update" figure is **[UNVERIFIED]** and the "Authenticity Update" name is community-coined with no
  LinkedIn source (https://sociallyin.com/blog/linkedin-algorithm-authenticity-update/ cites nothing official).
- Newsletters are the strongest 2026 channel for reach and conversion (vdB). [C]: podcast above
- Baseline: creator reach is down ~60% over two years (vdB, 1.3M posts / 50K creators); his 2025 report has views
  −50%, engagement −25%, follower growth −59% YoY. The feed is interest-graph driven and ~9–10% of it is "suggested"
  out-of-network posts. [C]: podcast above,
  https://melaniegoodmanlinkedinconsultant.substack.com/p/linkedin-algorithm-2026-reach-topic-authority ,
  https://www.linkedin.com/posts/richardvanderblom_chapter-1-algorithm-insights-report-2025-activity-7322514599126130688-Q895

## 4. Hashtags and external links

- **Hashtags have no positive effect.** vdB 2026: zero hashtags **outperform by 5–10%**; more than 3 cost 71%.
  AuthoredUp: 3–5 slightly reduce visibility, 6+ hurt. LinkedIn (Lorenzetti): "a nice to have, not a need to have."
  [C/D/LI]: vdB 2026 post, https://authoredup.com/blog/linkedin-algorithm , https://buffer.com/resources/linkedin-algorithm/
- **The "60% link penalty" has no traceable source [UNVERIFIED]** (https://fast-growth.fr/linkedin-algorithm-2026-proven-invented/).
  Best available data: vdB 2026 has **one link in the body cutting median reach ~18.8%** while 3+ links get 441%;
  AuthoredUp has 4+ links at 3–5x the median reach of single-link posts; Saywhat Q1 2026 (~400K posts) has multi-link
  beating no-link. vdB declares "link in first comment" obsolete. Dan Roth (LinkedIn EIC) calls the link penalty
  "a total misunderstanding" and LinkedIn's line is that the post's own value is what gets ranked. [C/D/LI]:
  Melanie Goodman substack above, https://thebreakoutinsights.substack.com/p/does-linkedin-penalize-external-links ,
  https://buffer.com/resources/linkedin-algorithm/
- So: a single naked link in a thin post is the worst case, and a link is fine when the post stands alone without it.

## 5. Ranking signals

- **Dwell time is an official ranking input since 2020.** LinkedIn measures on-feed dwell (the clock starts when ≥50%
  of the post is visible) and after-click dwell, with a skip threshold (T_skip) that is the same across text, image and
  video. [LI]: https://www.linkedin.com/blog/engineering/feed/understanding-feed-dwell-time (May 2020, follow-up Oct 2024).
  The widely quoted "30-second dwell threshold" is **[UNVERIFIED]**.
- **Feb 2026 LinkedIn paper**, "An Industrial-Scale Sequential Recommender for LinkedIn Feed Ranking" (arXiv:2602.12354):
  a transformer over ~1,000 recently viewed posts predicts click, scroll-past, **Long Dwell**, reactions, comments and
  shares; the optimization targets are Long Dwell and "Contribution" (reactions + comments + shares); the A/B gave
  +2.10% time spent and +3.52% like/comment/reshare. Saves are not a target. [LI]: https://arxiv.org/abs/2602.12354 ,
  https://fast-growth.fr/linkedin-algorithm-2026-proven-invented/
- Comment weighting: "comments = 15x likes" comes from vdB's 2024 report and is disputed; AuthoredUp (621K posts)
  estimates ~2x. Only the direction is agreed: substantive comments beat likes. [C/D]:
  https://linkhub.gg/en/blog/commentaires-vs-likes-linkedin . vdB Feb 2025: 2nd-degree comments have 2.6x the impact of
  connection comments; **comments arriving after 90 minutes have 1.8x more impact** (which is the anti-pod signal);
  AI-written comments "can kill the growth of a post"; 80% of comments in the first 5 minutes are AI-written; LinkedIn
  detects pods with ~97% accuracy. [C]:
  https://www.linkedin.com/posts/richardvanderblom_8-new-findings-about-linkedin-algorithm-activity-7297521619319570432-ZbYC , podcast above
- Saves: ~5x the reach effect of a like, ~2x a comment (AuthoredUp 3M, cited by Hootsuite). [D]:
  https://blog.hootsuite.com/linkedin-algorithm/
- "Golden hour" (first 60–90 min decides 70% of reach): everywhere in creator content, **absent from LinkedIn
  publications [UNVERIFIED]**. Posts keep surfacing for days (relevance over recency; vdB measures a 5-day lifespan).
  [LI via Hootsuite, C]
- Engagement bait ("Comment YES", "Agree?", "Thoughts?") gets reduced distribution, stated by LinkedIn in 2022 and
  repeated in 2026 guides. [LI]: Search Engine Land and Hootsuite links above
- Tagging: more than 5 tagged people is a spam signal, and there is a penalty when ≥50% of tagged people do not
  engage (vdB 2026). [C]

## 6. Cadence and timing

- LinkedIn: posting weekly is worth roughly 2x engagement. [LI via Hootsuite]
- Buffer, 2M+ posts / 94K accounts (Aug 2025), within-account regression: **more posts per week means more impressions
  per post, with no ceiling found** (2–5/wk +1,182 impressions/post; 6–10/wk +5,001; 11+/wk ~+17,000). [D]:
  https://buffer.com/resources/how-often-to-post-on-linkedin/
- Van der Blom 2026 contradicts himself across outlets: the podcast says optimal dropped from 5–6/wk to **2–4/wk**,
  his report post says 6x/week gets 3x views per post and twice-weekly is "insufficient for growth". [C, conflicting]
  Practical read: **3–5/week sustained**, and not twice within a few hours (the "8h/24h spacing" rules are [UNVERIFIED]).
- Times: Sprout Social, 2B engagements, Nov 2025–Feb 2026: **Tue 11am–5pm strongest, Wed 11–4, Thu 11am and 1–5pm,
  weekends worst.** [D]: https://sproutsocial.com/insights/best-times-to-post-on-linkedin/

## 7. Hooks: what the first-line data says

- AuthoredUp, 309,614 personal posts, Dec 2025–May 2026, median ER by opener style: **Story 2.60% > Contrarian 2.31% >
  Statement 2.27% > Results/number 2.19% > Question 2.16%** (question is last). Hook length: **0–40 chars 2.61%**,
  41–80 2.39%, 81–120 2.23%, 121–200 2.15%, 200+ 2.08%. A closing question adds 0.07pp (2.33 against 2.26). [D]:
  https://authoredup.com/blog/linkedin-hook-examples
- MagicPost, 1,179,958 posts in the 12 months to June 2026, medians: **question opener −34% likes (19 against 29)**
  and fewer comments, across every follower band; **a number in the first line 35 against 26 likes**; **1–5-word first
  lines best at 30 likes**, 11–15 words worst at 25. [D]: https://magicpost.in/blog/linkedin-hooks
- Emoji (AuthoredUp, 847K posts, Mar 2025–Feb 2026): going 0 to 1 lifts ER 2.30 to 2.47% and median reach 798 to 970,
  then it is flat from 1 to 15. One is fine, more buys nothing. [D]:
  https://authoredup.com/blog/how-to-add-emojis-on-linkedin-posts
- Concrete specifics (company names, exact metrics, timeframes) beat generic claims, repeatedly, in AuthoredUp and
  Buffer write-ups of LinkedIn's own guidance (original POV, expertise, knowledge and advice). [LI]

## 8. Broetry (one sentence per line)

- Origin and definition: https://contentin.io/glossary/broetry/ , https://blog.hootsuite.com/social-media-definitions/broetry/ ,
  https://contentin.io/glossary/line-break-formatting/
- **No public dataset isolates one-line-per-sentence against normal paragraphs.** What exists: vdB Feb 2025 has
  "formatted posts perform 2.1x better" (line breaks against a wall of text) [C]; AuthoredUp has text posts needing
  20+ sentences for 1.14x reach [D]; the fold mechanics mean a blank line burns 1 of 3 visible lines [C].
- The reputational shift is the part that matters. A uniform single-sentence-with-blank-line rhythm now reads as a
  template and an AI tell (SocialNexis claims 91% of AI posts use it, sample undisclosed, [UNVERIFIED]), and
  LinkedIn's own slop definition targets "polished, no substance". White space still helps readability; the metronome
  cadence and the cliffhanger padding ("Read that again.") signal low effort. Sources:
  https://socialnexis.com/guides/ai-post-edit-tells-linkedin ,
  https://www.sophieflow.com/article/the-end-of-linkedin-broetry-why-value-driven-ai-storytelling-is-winning-in-2026

## 9. AI-looking posts get down-ranked, officially

- **2026-07-30:** LinkedIn added a "Seems like AI slop" option to every post's ⋯ menu. New classifiers reduce such
  content in out-of-network suggestions, "hundreds of thousands" of automated comments are blocked daily, the "Enhance
  your post" rewriter was replaced by a voice-preserving proofreader, and creators who collect many flags get private
  notices. Hari Srinivasan (CPO): "AI slop is a top priority for all of us." [LI]:
  https://techcrunch.com/2026/07/30/linkedin-adds-a-button-to-report-ai-generated-slop/
- **2026-08-20 (Srinivasan):** 1M+ members used the flag in two weeks and members "now experiencing **40% less views**
  on what we classify as AI slop." A single report affects only that reporter's feed; distribution drops when many
  members flag the same content. The definition (Sam Corrao Clannon, Creator Product Lead) is content "sophisticated
  or polished in its presentation, but lacks substance… no particular experience, perspective, or insight." Using AI
  to polish language is explicitly fine. [LI]:
  https://www.socialmediatoday.com/news/linkedin-says-1m-people-have-reported-ai-slop/828465/ ,
  https://gcn.com/linkedin-slop-flag-used-million-members/21090/
- Saturation: Originality.ai found **81.2% of 5,000 long-form (100+ word) public posts in July 2026 "likely AI"**, up
  from ~50% late 2024 and 53.7% in 2025. Pangram calls LinkedIn the most AI-saturated platform. [D]:
  https://originality.ai/blog/ai-content-published-linkedin ,
  https://www.fastcompany.com/91571983/linkedin-is-the-most-ai-saturated-platform-new-study-suggests
- Tells readers call out in public: em dashes (the "Blade Runners of LinkedIn" hunt them):
  https://www.techradar.com/computing/artificial-intelligence/blade-runners-of-linkedin-are-hunting-for-replicants-one-em-dash-at-a-time ,
  https://knowyourmeme.com/memes/chatgpt-em-dash ; filler openers ("Here's the thing", "Let that sink in", "Read that
  again", "It's worth noting"); "It's not X. It's Y."; "Most people think X. They're wrong."; humble-brag confessions
  ("I did X. Here's what nobody tells you"); triads; takeaway lists closing on a comment prompt. [C]: SocialNexis link above

## 10. Clichés readers scroll past

Profile and brand buzzwords (LinkedIn's own historical lists plus 2026 updates): passionate, strategic, results-driven,
expert, creative, motivated, detail-oriented, team player, innovative, leadership, seasoned, dedicated. Sources:
https://careerenlightenment.com/overused-linkedin-buzzwords-2026

Post clichés: "I'm excited/thrilled/humbled to announce", "I had the pleasure of meeting", "we are proud to support",
"amazing", "unleash", "harnessing the power of AI", "game-changer", "in today's fast-paced world", "let's connect",
"Agree?", "Thoughts?", "Comment YES". Sources:
https://www.forbes.com/councils/forbescoachescouncil/2025/01/06/stop-using-these-cringey-clichs-in-your-linkedin-posts/ ,
https://www.liseller.com/linkedin-growth-blog/how-to-avoid-overused-phrases-in-linkedin-posts

Structural clichés: fake-vulnerability story into generic lesson into "What's your take?"; "I got rejected by X, now I
run Y"; numbered-lesson listicles with rocket emoji; unicode-bold headline fonts, which carry no algorithmic penalty
but break screen readers and search. Source: https://ligosocial.com/blog/10-linkedin-text-formatting-tricks-to-make-your-posts-stand-out

Secondary summary consulted, not cited above: https://meet-lea.com/en/blog/linkedin-algorithm-explained
