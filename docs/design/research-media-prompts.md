# Image and video tools: limits, prompt rules, media decision (researched 2026-09-17)

Provenance for the `media` block in `config/postsmith.yaml` and for `.claude/skills/media/`. Checked against live
official pages unless marked **[unverified]** or **[third-party]**. Model names and caps here move every few months;
`/eval health` flags any `verified_on` older than `media.facts_stale_after_days`.

The live prompt templates are `.claude/skills/media/references/tools/*.md`. This file is why they say what they say.

## 0. What the current model lineup forces

| Tool | Status on 2026-09-17 | Consequence |
|---|---|---|
| GPT Image / DALL-E | ChatGPT Images 2.5 shipped 2026-09-08 (API `gpt-image-2.5-flare` default, `gpt-image-2.5-sunburst` precision). `gpt-image-2` (2026-04-21) and `gpt-image-1.5` are legacy. DALL-E is irrelevant. https://openai.com/index/introducing-chatgpt-images-2-5/ , https://developers.openai.com/api/reference/resources/images/methods/generate | One template, targeting 2.5 behaviour: reasoning before drawing, reference photos, sketch, comment-on-image edits. |
| Nano Banana (Gemini image) | Nano Banana 2 (`gemini-3.1-flash-image`, 2026-02-26, default in the Gemini app), NB2 Lite, and Nano Banana Pro (`gemini-3-pro-image`, 2025-11-20, paid plans, best typography and factual accuracy). `gemini-2.5-flash-image` is legacy. https://ai.google.dev/gemini-api/docs/image-generation , https://support.google.com/gemini/answer/14286560 | One template with a model-pick rule: text-heavy or infographic goes to Pro, everything else to NB2. |
| Veo 3 / 3.1 | Veo 3.1 (+Fast, +Lite March 2026) is current, there is no Veo 4. GA on Vertex as `veo-3.1-generate-001` (2025-11-17). https://ai.google.dev/gemini-api/docs/veo , https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate | Primary video template, native audio and dialogue. |
| Sora 2 | **Discontinued.** App and web shut 2026-04-26, API shuts 2026-09-24. https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation | No Sora template. A generic prose+dialogue fallback survives in case a successor appears. |
| Runway Gen-4 / 4.5 | Gen-4.5 (2025-12-01) is current, Gen-4 is legacy. https://help.runwayml.com/hc/en-us/articles/46974685288467-Creating-with-Gen-4-5 | Second video template, for image-to-video from a still made by GPT Image or Nano Banana. |

## 1. Per-tool findings

### 1.1 OpenAI GPT Image (ChatGPT Images 2.5 / gpt-image-2.5)

Docs: https://developers.openai.com/api/docs/guides/image-generation , https://developers.openai.com/api/docs/guides/image-prompting ,
cookbook https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide and
https://developers.openai.com/cookbook/examples/multimodal/image-gen-1.5-prompting_guide , system card
https://deploymentsafety.openai.com/chatgpt-images-2-5

- **Prompt order**: background/scene, subject, key details, constraints. Name the intended use (ad, diagram, social
  graphic) so the model picks the right polish. Labelled segments and line breaks are fine for long prompts. JSON and
  tags buy nothing, so use whatever is maintainable. The **80–200 word** target in our template comes from this guide's
  worked examples, not from a stated cap.
- **Max prompt length**: 32,000 characters (API reference, verified live). The ChatGPT chat box has no separate
  documented image-prompt limit.
- **Sizes**: presets 1024x1024, 1536x1024, 1024x1536; 2.5 also takes custom WxH (multiples of 16, ratio at most 3:1,
  edge at most 3840 px, 655,360–8,294,400 total px); 2K/4K presets 2048x2048, 3840x2160. The ChatGPT UI exposes only
  Horizontal / Square / Vertical. Whether typing "4:5" there yields an exact 4:5 file is **[unverified]**
  (third-party claims yes), so the safe path is Vertical then crop to 4:5, or the API.
- **Quality**: `auto/low/medium/high/xhigh/max`. Use `high` for dense text and infographics; keep `xhigh/max` for when
  `high` fails.
- **Text rendering**: put required wording in quotes or ALL CAPS, describe position and typography, spell unusual words
  letter by letter, ask for no extra text, then check the spelling in the output. The docs still warn that text
  placement and clarity can struggle; the 2.5 system card claims better infographic accuracy and layout.
- **Reference images and edits**: give each reference a role by index ("Image 1: subject, Image 2: style"). For edits,
  say "change only X" and list what to keep (identity, geometry, layout, lighting, labels), restating the list every
  turn to stop drift, one change per turn. Up to 16 reference images in 2.5 **[third-party: Unite.AI]**. Transparent
  background via `background=transparent` with PNG or WebP.
- **Strengths**: photorealism when you say "photorealistic" or "real photograph" (camera terms are look cues, not
  physics), UI mockups when you describe the product as if it already shipped, which is the fake-screenshot path;
  logos; structured diagrams; world knowledge (it infers Woodstock from "Bethel NY, Aug 1969").
- **Weaknesses, from the docs**: imprecise element placement in structured layouts, recurring characters drifting
  across separate generations, complex prompts taking ~2 min, small text needing `high`.

### 1.2 Google Nano Banana (2 / 2 Lite / Pro)

Docs: https://ai.google.dev/gemini-api/docs/image-generation , Cloud guide
https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana , app tips
https://blog.google/products-and-platforms/products/gemini/prompting-tips-nano-banana-pro/ ,
https://blog.google/innovation-and-ai/products/nano-banana-pro/ , https://blog.google/innovation-and-ai/technology/ai/nano-banana-2/ ,
https://deepmind.google/models/gemini-image/pro/ , https://developers.googleblog.com/en/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/

- **Prompt shape**: a narrative scene description, never a keyword list. Start with a strong verb (Create, Render,
  Transform). Formula: [Subject] + [Action] + [Location/Context] + [Composition] + [Style]. Be specific about materials
  ("navy tweed", not "jacket"), use camera and lighting language (85mm, f/1.8, three-point softbox, chiaroscuro,
  golden-hour backlight), state the purpose, phrase positively ("empty street", not "no cars"), iterate one edit at a
  time, and restart the chat with a full description when a character drifts.
- **Text in images**: exact text in quotes; describe fonts by look (bold condensed sans, brush script) rather than by
  name; draft the copy in chat first, then ask for the image with that copy (Google's own tip); keep text large,
  **3–5 text elements max**, render at **2K or above** for fine type, and overlay final copy yourself when it has to be
  pixel-perfect. Pro for precise typography.
- **Max prompt length**: no character cap. Context window 131,072 tokens (NB2) and 65,536 (Pro) [Cloud blog].
  Practical guidance is 100–250 words.
- **Sizes**: 512 px (Flash only), 1K default, 2K, 4K (uppercase K). Aspect ratios 1:1, 3:2, 2:3, 3:4, 4:3, **4:5**, 5:4,
  9:16, 16:9, 21:9 (NB2 adds 1:4, 4:1, 1:8, 8:1). The Gemini app downloads 2K on a paid plan and 1K without; AI Studio
  has explicit ratio and resolution controls; in the app you state it in the prompt ("9:16 vertical poster").
- **Reference images** (API docs): NB2 up to 10 object + 5 character; NB2 Lite 14 object + 4 character; Pro 6 object +
  3 style. Marketing pages say "up to 14 images, 5 people". Assign roles ("Image A for pose, B for style, C for
  background").
- **Grounding**: Pro and NB2 can call Google Search for factually grounded infographics (last night's match, current
  weather). No other tool here does this, which matters for trending-topic posts.
- **Strengths**: best legible text (Pro: single-line text error rates mostly under 10% per the DeepMind page),
  infographics, whiteboard explainers, localisation, semantic-mask edits ("change only the sofa"), multi-panel comics.
- **Weaknesses, official**: small faces, spelling in fine text, factual errors in data-driven infographics, grammar in
  multilingual text, artifacts on heavy edits, no guaranteed character consistency, knowledge cutoff Jan 2025 without
  grounding.

### 1.3 Google Veo 3.1 (Gemini app, Flow, AI Studio)

Docs: https://ai.google.dev/gemini-api/docs/veo , model card https://ai.google.dev/gemini-api/docs/models/veo-3.1-generate-preview ,
Cloud guide https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1 , DeepMind guide
https://deepmind.google/models/veo/prompt-guide/ , Flow help https://support.google.com/flow/answer/16352836 , Flow tips
https://blog.google/innovation-and-ai/products/flow-video-tips/ , meta-prompting https://blog.google/products/gemini/meta-prompting-veo-gemini-tips/

- **Prompt elements**: subject, action, style (film-genre keywords), camera position and motion (dolly, tracking,
  crane, POV, aerial), composition (wide, close-up, two-shot), focus and lens (shallow DOF, macro, wide-angle),
  ambiance (colour and light). Cloud-blog formula: [Cinematography] + [Subject] + [Action] + [Context] + [Style &
  Ambiance]. Detailed character descriptions (age, hair, clothing) improve adherence.
- **Audio cues**, syntax from the Cloud guide: dialogue in quotation marks attributed to a described speaker,
  `SFX: ...` for effects, `Ambient noise: ...` for beds. Speech works best when it fits inside the 8 s clip; avoid
  giving lines to minor characters.
- **Timestamp prompting**: `[00:00-00:02] ... [00:02-00:04] ...` directs multi-beat sequences inside one generation.
- **Limits**: prompt 1,024 tokens (model card); durations **4/6/8 s**; 720p default, 1080p, 4K (8 s required for
  1080p/4K and for reference images, no 4K on Lite); aspect **16:9 or 9:16 only**; up to 3 reference images
  ("ingredients") to lock a character, object or setting; first+last frame interpolation; extend by 7 s up to 20 times
  (API, extension is 720p only; in Flow, extending needs Lite and 8 s clips). Dialogue runs about
  **2–2.5 spoken words per second**, which is what caps a line's length.
- **Negative prompts**: the Gemini API has no negative-prompt field (verified). The official advice is to describe what
  you want and never write "no" or "don't", which is why `media.negation_words` is a hard check. Vertex AI's
  `negativePrompt` (string, up to 1,000 chars) **[unverified: search snippet only]**.
- **Strengths**: synchronised native audio and multi-person dialogue, cinematic camera moves, physics; ingredients plus
  first/last frame give a recurring character enough consistency for a brand.
- **Weaknesses**: on-screen text is not a documented capability and community reports show garbled text
  **[unverified]**, so keep text out of Veo prompts and add captions in an editor; real-person faces are restricted
  (`personGeneration`); add/remove-object editing falls back to Veo 2 without audio; API videos are retained 2 days.

### 1.4 Runway Gen-4.5

Docs: https://help.runwayml.com/hc/en-us/articles/46974685288467-Creating-with-Gen-4-5 ,
https://help.runwayml.com/hc/en-us/articles/46182941379347-Introduction-to-Prompting ,
https://help.runwayml.com/hc/en-us/articles/47313737321107-Text-to-Video-Prompting-Guide ,
https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide ,
https://help.runwayml.com/hc/en-us/articles/46749315925395-Camera-Terms-Prompts-Examples ,
https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide ,
https://runway.com/research/introducing-runway-gen-4.5 , https://academy.runwayml.com/guides/prompting-guide

- **Prompt shape**: text-to-video is "[Camera] shot of [subject] [action] in [environment]. [Supporting descriptions]"
  with both a visual and a motion component. Image-to-video is "The camera [motion] as the subject [action]." and
  describes **motion only**, because the still already supplies composition, lighting and style. Refer to subjects
  generically ("the subject", "the woman on the left"). Positive phrasing ("sharp focus", not "not blurry"); no
  abstract words (beautiful, professional); no conflicting instructions; no multi-paragraph prompts. JSON prompting is
  explicitly called a placebo, prompt order does not matter, and there is no ideal length. Start simple and add one
  element per iteration. Timestamps use `[00:00 through 00:02] ...` alongside a natural-language prompt.
- **Limits**: 2–10 s; 720p; 24/25 fps; text-to-video is 16:9 only (1280x720); image-to-video takes 16:9, 9:16, 1:1,
  4:3, 3:4, 21:9; 12 credits/s; web only. The 1,000-character prompt cap is **[third-party, not on the help pages
  read]**.
- **Audio**: the Sept-2026 help-center spec table lists none, while TechCrunch (2025-12-11) reported a native-audio and
  multi-shot update to Gen-4.5. **Conflicting, so treat output as silent** and plan voiceover through Runway Generate
  Speech / Lip Sync or an editor.
- **Strengths**: motion quality and prompt adherence, precise camera choreography, physics, a long camera-term
  vocabulary with worked examples.
- **Weaknesses**, from Runway's own research page: causal reasoning (effects before causes), object permanence, success
  bias. No text-rendering claims and no documented dialogue.

### 1.5 Sora 2 (archive)

https://developers.openai.com/cookbook/examples/sora/sora2_prompting_guide ,
https://developers.openai.com/api/docs/guides/video-generation . Transferable rules, kept for whatever replaces it:
prose scene plus a labelled dialogue block; one camera move and one subject action per shot; short clips follow
instructions better; 4 s fits 1–2 exchanges and 8 s fits 3–4; describe diegetic sound as rhythm anchors, not a score;
edit by naming a single change ("same shot, 85mm").

## 2. What all four vendors agree on

1. Concrete beats adjectival: materials, lens, light direction, palette, era, not "beautiful/professional/modern".
2. State the intended use and audience up front.
3. On-image text goes in quotes, once, with placement and typography; spell odd words; ask for nothing else; verify
   the spelling afterwards.
4. Positive phrasing only. Every "avoid" becomes what should be there instead.
5. Iterate one change at a time and restate the invariants.
6. References get explicit roles by index.
7. For video: one camera move and one action per clip, dialogue short enough for the duration, sound described.
8. Clarity over length. Runway warns that long prompts create conflicts; Veo caps at 1,024 tokens.

## 3. Platform format specs (these drive `aspect_ratio`)

- **LinkedIn images** (official, https://www.linkedin.com/help/lms/answer/a527229): 3:1 to 4:5 accepted, anything
  taller is centre-cropped, a single photo renders at most 4:5, 1080 px wide recommended, 5 MB. So **4:5 (1080x1350)**
  for maximum feed height or **1:1 (1080x1080)**. AuthoredUp: portrait images 32% ahead of landscape on reach
  [third-party]. LinkedIn native video specs are not on any official page found; 1:1 or 9:16 is common practice
  [unverified].
- **X images and video** (official ad specs, https://business.x.com/en/help/campaign-setup/creative-ad-specifications.html):
  4:5 (1440x1800), 1:1 (1080x1080), 1.91:1, 16:9 (1920x1080). X states that 1:1 always renders square on every surface
  and that 1:1 or 9:16 take more real estate than 16:9, and recommends 9:16 for video. Hootsuite (Sept 2026) suggests
  1280x720 or 1080x1080 for single images. So **1:1** by default, **16:9** only for screenshot and chart images,
  **9:16 or 1:1** for video.
- Video defaults: LinkedIn 9:16 or 1:1 (a 9:16 Veo render is crop-safe from the centre), X 9:16 (Veo native) or 1:1
  (Runway I2V native).

## 4. When no media is the better answer

- Buffer, 52M+ posts, 2025 data (https://buffer.com/resources/state-of-social-media-engagement-2026/): LinkedIn median
  engagement rate carousel 21.77%, video 7.35%, image 6.52%, link 3.81%, text 3.18%. X: text 3.56%, image 3.40%,
  video 2.96%, link 2.25%.
- AuthoredUp, 3M+ personal-profile posts, Mar 2025–Feb 2026
  (https://authoredup.com/blog/best-performing-content-on-linkedin): reach multipliers document 1.39x, image 1.20x,
  text 1.07x, video 0.86x; engagement image 1.33x, text 0.78x; long text posts (20+ sentences) 1.14x reach; portrait
  beats landscape by 32%.
- van der Blom Algorithm Insights 2026, 1.3M posts
  (https://www.linkedin.com/posts/richardvanderblom_rvdbcarousel-algorithm-insights-report-2026-activity-7455148601749729280-AwsY)
  [methodology contested in the comments]: infographics are 29% of top-1% posts; photos with the creator's face beat
  polished brand shots; 34% of top posts are under 600 characters; LinkedIn is claimed to detect generic AI imagery.
- X is text-first. Images give a modest lift, video is promoted but X publishes no multiplier, and replies dominate
  ranking (the open-source Phoenix ranker predicts like/reply/repost/click/dwell as multi-label targets:
  https://github.com/xai-org/x-algorithm ; weights from https://opentweet.io/blog/how-twitter-x-algorithm-works-2026
  are third-party).

The decision rules the brief has to cite:

- **Default to text-only on X.** An image only when the image is the joke or the proof (meme, fake screenshot, chart).
  Video only under ~15 s with the hook in the first second.
- **On LinkedIn an image is the default lift** (1.2x reach, 1.33x engagement), but only three genres earn it for this
  brand: whiteboard or infographic explainer, meme or fake-document or screenshot punchline, and a real photo of the
  user, which cannot be generated (the brief says "USER PHOTO" and gives a shot direction). Generic AI illustration,
  3D robots and gradient backgrounds lose to no media at all.
- **Text-only wins** when the post is a story, hot take or list whose rhythm is the hook; when the visual would restate
  the caption; when on-image text would run past ~12 words; or when the concept needs a real face or a real logo, both
  of which every tool's policy blocks.
- **Carousels** outrank everything on LinkedIn (21.77% median) but a PDF is out of scope, so the brief flags
  "would work better as a 5-slide PDF" and leaves the call to the user.

## 5. The media brief

One tool-agnostic YAML brief per post, written by the generator and consumed by the renderers and the evals. The live
schema and field notes are `.claude/skills/media/references/brief_schema.md`; `tools/media_check.py` enforces it.

Genres: `meme`, `fake_screenshot`, `fake_document`, `whiteboard_explainer`, `diagram_chart`, `photoreal_scene`,
`product_mock`, `comic_panels`, `user_photo_direction`.

The fields that carry a limit rather than a preference: `on_image_text.lines` (each ≤ 8 words, total ≤ 12 words for
GPT Image, ≤ 5 elements for Nano Banana), `resolution_tier` (2K minimum whenever `on_image_text` is present),
`alt_text` (≤ 125 chars, and it doubles as the probe for whether the concept survives without the caption),
`keep_out_as_positive` (every exclusion rewritten as what replaces it), `video.duration_s` (Veo 4/6/8, Runway 2–10),
`video.dialogue` (≤ ~2.5 words per second of clip, none for Runway), `video.captions_plan` (never ask a video model
for on-screen text), and `factual_claims_in_visual` (anything a chart asserts, verified before posting).
A renderer fails loudly when `decision != none` and `visual_concept`, `aspect_ratio` or `tool.primary` is missing.

## 6. Worked example behind the templates

The example running through every tool template is an original brief, not from any vendor doc: platform LinkedIn,
genre `fake_document`, a laminated "AGENT INCIDENT REPORT" form pinned to a startup fridge and filled in by hand, the
incident being "agent bought 400 domain names to be safe"; on-image text `AGENT INCIDENT REPORT` and
`Root cause: it was being helpful`; 4:5 at 2K; tool `nano_banana_pro` for the dense text, fallback `gpt_image`. It is
the same brief in all five templates so the difference between the tools is the only thing that varies.

Per-tool rules distilled into those templates:

- **6.1 GPT Image**: say "photorealistic" or "real photograph" for photo genres; for `fake_screenshot` describe the app
  as a shipped product and put it in a device frame; give the aspect ratio in words and numbers ("4:5 portrait,
  1080x1350") because the UI toggle is coarse; spell brand-like words letter by letter; 80–200 words total; regenerate
  with a single-change follow-up. Use `quality=high` when there is text.
- **6.2 Nano Banana**: narrative sentences, never keyword lists; start with a verb; pick Pro when `on_image_text` has
  more than one line or the genre is `whiteboard_explainer` or `diagram_chart`; draft the copy in a prior turn and
  reference it; at most 5 text elements, 2K minimum; describe fonts by look; edits are "change only …, keep everything
  else identical".
- **6.3 Veo 3.1**: one camera move, at most three beats, no on-screen text, no real people, exclusions rewritten
  positively, under ~150 words. Generate the first frame with 6.1 or 6.2 when a specific look has to hold.
- **6.4 Runway Gen-4.5**: image-to-video from a 6.1/6.2 still is the default and text-to-video is for when consistency
  does not matter. Motion only in I2V, never re-describe the still; generic subject references; positive phrasing; no
  dialogue, no text; upload a clean still; when the motion misfires, strip to the core move and re-add one element.
- **6.5 Generic fallback**, for whatever replaces Sora: scene prose, then a cinematography line, then 2–3 action beats,
  then a labelled dialogue block (1–2 exchanges per 4 s), then a diegetic sound cue.

## 7. Eval hooks

Script checks, no LLM: the brief has a `decision_reason` citing a section-4 rule; `delete_test` is non-empty when media
is chosen; `aspect_ratio` is valid for the platform (LinkedIn in {4:5, 1:1}, X in {1:1, 16:9, 9:16}); on-image text is
≤ 12 words total (GPT Image) or ≤ 5 elements (Nano Banana) and every line appears verbatim in quotes inside the
rendered prompt; the rendered prompt contains none of `no `, `don't`, `without`, `avoid`, `never` for
Veo / Runway / Nano Banana; the Veo prompt is ≤ 700 words (safely under 1,024 tokens) with duration in {4, 6, 8} and
dialogue words ≤ 2.5 × duration; the Runway prompt is ≤ 1,000 chars with a 16:9 T2V ratio; no video prompt requests
text; no real people's names and no brand names other than the user's own; `alt_text` ≤ 125 chars.

Fresh-context judge, candidate treated as data, order randomised, length not rewarded: (1) does `alt_text` alone carry
the joke or the point; (2) is the visual doing work the caption does not (restatement fails); (3) the slop screen,
where generic robot, brain, gradient and handshake imagery fails; (4) is the prompt executable by the named tool given
the section-1 limits; (5) is factual content flagged in `factual_claims_in_visual`.

The graders are themselves tested against an empty brief, a "futuristic AI brain with glowing circuits" brief that must
fail the slop screen, and a brief whose `alt_text` is just the caption, which must fail as restatement.

## 8. Open items to confirm by hand

1. Runway Gen-4.5 native audio (help-center spec says none, TechCrunch says added Dec 2025).
2. Runway 1,000-character prompt cap (third-party only).
3. Whether the ChatGPT UI honours "4:5" exactly (it shows only Horizontal/Square/Vertical).
4. Images 2.5 "up to 16 reference images" (Unite.AI).
5. Vertex `negativePrompt` for Veo (search snippet only; the Gemini API definitely lacks it).
6. Veo on-screen text quality (no official statement, community reports are poor).
7. LinkedIn native-video aspect-ratio limits (not on any official page found).
8. van der Blom 2026 figures (self-published, methodology questioned in the comments).

## Sources (official unless noted)

OpenAI: https://developers.openai.com/api/docs/guides/image-generation ; https://developers.openai.com/api/docs/guides/image-prompting ; https://developers.openai.com/api/reference/resources/images/methods/generate ; https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide ; https://developers.openai.com/cookbook/examples/multimodal/image-gen-1.5-prompting_guide ; https://openai.com/index/introducing-chatgpt-images-2-5/ ; https://deploymentsafety.openai.com/chatgpt-images-2-5 ; https://developers.openai.com/api/docs/models/gpt-image-2 ; https://community.openai.com/t/introducing-gpt-image-2-available-today-in-the-api-and-codex/1379479 ; https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation ; https://developers.openai.com/cookbook/examples/sora/sora2_prompting_guide ; https://developers.openai.com/api/docs/guides/video-generation
Google: https://ai.google.dev/gemini-api/docs/image-generation ; https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana ; https://blog.google/products-and-platforms/products/gemini/prompting-tips-nano-banana-pro/ ; https://blog.google/innovation-and-ai/products/nano-banana-pro/ ; https://blog.google/innovation-and-ai/technology/ai/nano-banana-2/ ; https://deepmind.google/models/gemini-image/pro/ ; https://developers.googleblog.com/en/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/ ; https://support.google.com/gemini/answer/14286560 ; https://ai.google.dev/gemini-api/docs/veo ; https://ai.google.dev/gemini-api/docs/models/veo-3.1-generate-preview ; https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1 ; https://deepmind.google/models/veo/prompt-guide/ ; https://deepmind.google/models/veo/ ; https://support.google.com/flow/answer/16352836 ; https://blog.google/innovation-and-ai/products/flow-video-tips/ ; https://blog.google/products/gemini/meta-prompting-veo-gemini-tips/ ; https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate
Runway: https://help.runwayml.com/hc/en-us/articles/46974685288467-Creating-with-Gen-4-5 ; https://help.runwayml.com/hc/en-us/articles/46182941379347-Introduction-to-Prompting ; https://help.runwayml.com/hc/en-us/articles/47313737321107-Text-to-Video-Prompting-Guide ; https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide ; https://help.runwayml.com/hc/en-us/articles/46749315925395-Camera-Terms-Prompts-Examples ; https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide ; https://academy.runwayml.com/guides/prompting-guide ; https://runway.com/research/introducing-runway-gen-4.5 ; (third-party) https://techcrunch.com/2025/12/11/runway-releases-its-first-world-model-adds-native-audio-to-latest-video-model
Platforms and data: https://www.linkedin.com/help/lms/answer/a527229 ; https://business.x.com/en/help/campaign-setup/creative-ad-specifications.html ; https://github.com/xai-org/x-algorithm ; (third-party) https://blog.hootsuite.com/social-media-image-sizes-guide/ ; https://buffer.com/resources/state-of-social-media-engagement-2026/ ; https://buffer.com/resources/data-best-content-format-social-media/ ; https://authoredup.com/blog/best-performing-content-on-linkedin ; https://www.linkedin.com/posts/richardvanderblom_rvdbcarousel-algorithm-insights-report-2026-activity-7455148601749729280-AwsY ; https://opentweet.io/blog/how-twitter-x-algorithm-works-2026 ; https://en.wikipedia.org/wiki/GPT_Image
