# Media brief schema `drafts/<run>/media/<cid>.brief.yaml`

Contents: 1 the full brief · 2 the video block · 3 the capture block · 4 field by field · 5 the delete test ·
6 decision rules M1-M7 with reasons · 7 genres · 8 text budgets per tool · 9 what `media_check.py` fails on

The brief is the contract between the media-director, `tools/media_check.py`, the media-judge and
`assemble_report.py`. It is tool-agnostic: a human designer could build the image from it without a question, and
the tool prompts are rendered from it, never the other way round. Alt text is capped per platform (LinkedIn
120, X 1,000), there is no minimum video duration, tool ids are the config keys, and genre ids come from
`style/taxonomies/media_roles.md`.

## 1. The full brief

```yaml
schema: postsmith.media/1
post_id: r2-w2-li                   # the candidate id (cid) this brief belongs to
platform: linkedin                  # linkedin | x
decision: image                     # none | image | video | real_capture_direction
decision_reason: "M3: fake-document punchline; the caption sets up, the form lands the root-cause line. M5: lens attaches media in 71% of train posts."
delete_test: "Without it the caption ends on a setup with no receipt; the root-cause line exists only on the form."
carousel_suggested: false
carousel_outline: []                # five one-line slides, only when carousel_suggested is true (M7)
genre: fake_document                # id from style/taxonomies/media_roles.md; see §7
genre_note: null                    # optional one line for the judge (why a parody is obviously fictional, why a chart is grounded)
fictional_product: null             # parody_ui and product_mock: the invented product name; media_check.py requires it
humor_or_hook_device: "bureaucratic deadpan"
visual_concept: "A laminated incident-report form pinned to a startup fridge, filled in by hand; the root-cause line is the joke."
subject: "A4 laminated form, plain corporate black type, blue ballpoint handwriting"
setting: "scuffed white office fridge, small startup kitchen, late-afternoon window light from the left"
composition: {framing: "medium close-up", angle: "straight-on", focal_point: "the handwritten root-cause line", negative_space: "fridge edge visible on the right"}
style: {medium: "photorealistic phone photo", palette: "natural, slightly warm", era_or_reference: "taken 30 seconds ago", finish: "faint grain"}
on_image_text:                      # omit the whole block when the image carries no text
  lines: ["AGENT INCIDENT REPORT", "Root cause: it was being helpful"]   # each <= 8 words; <= 12 words total for gpt_image; <= 5 elements for nano_banana
  placement: "header centred top; second line on the form's second row"
  typography_intent: "bold wide sans header; blue handwriting"           # by look, never a font name
must_show: ["one round magnet", "a coffee ring on the corner"]
keep_out_as_positive: ["the fridge is clean of brand marks", "the only legible words are the two lines plus short generic field labels"]
aspect_ratio: "4:5"                 # linkedin image: 4:5 | 1:1 ; x image: 1:1 | 16:9 | 9:16 ; video: 9:16 | 1:1
target_pixels: "1080x1350"
resolution_tier: 2K                 # 1K | 2K | 4K; 2K minimum whenever on_image_text is present
tool: {primary: nano_banana, reason: "two exact text lines -> Nano Banana Pro model, 2K", fallback: gpt_image}   # ids: gpt_image | nano_banana | veo | runway
references: []                      # [{role: subject|style|background|first_frame, source: user_upload|generated_still, note: "..."}]
video: null                         # §2 when decision is video
real_capture_direction: null        # §3 when decision is real_capture_direction
safety_checks: {no_real_person_likeness: true, no_logos_or_trademarks: true, no_copyrighted_characters: true}
alt_text: "Laminated incident report on a fridge; root cause line reads: it was being helpful."   # <= 120 chars on LinkedIn, <= 1000 on X
factual_claims_in_visual: []        # every number or label a chart or infographic asserts, with its source
risk_notes: "text-heavy; expect 2-3 regenerations"
```

`decision: none` still needs `decision_reason` (citing M1 or M4, plus M5 when the corpus prior pushes the other
way) and `delete_test` ("nothing: ..."), and the rest of the fields stay null or empty. A brief with `decision:
none` produces no prompt files.

## 2. The video block

```yaml
video:
  duration_s: 8                     # veo: 4 | 6 | 8 (8 required for 1080p); runway: 2-10, aim for 5-8
  start_frame: generated_still      # generated_still | none; write the still's prompt too when a look must hold
  camera: "static medium close-up"  # one move for the whole clip
  beats:                            # at most 3, timestamped, together covering the whole clip
    - {t: "00:00-00:03", action: "a hand in a grey hoodie sleeve enters from the right and pauses over the root-cause line"}
    - {t: "00:03-00:06", action: "the hand writes, then underlines the words twice"}
    - {t: "00:06-00:08", action: "the hand retreats; a second magnet is slapped onto the form"}
  dialogue:                         # veo: one line, <= 15 words and <= 2.5 words per second; runway: []
    - {speaker_desc: "an unseen man, tired and deadpan", line: "It bought four hundred domains. To be safe."}
  sfx: ["ballpoint scratching on laminate", "a magnet clacking on metal"]
  ambient: "fridge compressor hum, distant office keyboard"
  captions_plan: burn_in_in_editor  # none | burn_in_in_editor; never ask the video model for on-screen text
```

There is no minimum duration on either platform. M2's only timing rule for X is that the hook lands in the first
second, because the timeline autoplays muted and a viewer decides before the second beat.

## 3. The capture block

```yaml
real_capture_direction:
  what_to_open: "Claude Code in the terminal, inside the repo where the agent ran"
  what_to_type: "the exact command or prompt that reproduces the moment, or null"
  what_to_show: "the tool-call list where it registers the 400th domain, with the cost line beneath it"
  crop: "terminal only, from the prompt line to the cost line, then 4:5"
  redact: "API keys, customer names, the org name in the path"
```

Used for `decision: real_capture_direction` with `genre: real_capture_direction` (a real screenshot) or `genre:
user_photo_direction` (a phone photo of Deep or of his desk; `what_to_open` becomes the shot direction). Every
instruction must be executable by Deep in under five minutes without a question, because an ambiguous capture
direction is a media miss the judge scores under `capture_direction`.

## 4. Field by field

| Field | Guidance and reason |
|---|---|
| `decision` | `none` is a full answer, not a failure. `real_capture_direction` covers anything Deep must capture himself. |
| `decision_reason` | One or two sentences, each starting with the rule id it applies (M1-M7); `media_check.py` fails a reason with no rule id. State the fact the rule was applied to (which line of the caption, which media rate). |
| `delete_test` | Name the specific thing the post loses without the media (a receipt, the punchline, the proof). "It adds visual interest" is a fail; see §5. |
| `carousel_suggested`, `carousel_outline` | M7. Flag only; the outline lets Deep build it by hand. |
| `genre` | An id from §7. Drives the tool pick and the judge's slop screen. |
| `genre_note` | Optional, one line, read by the judge as part of the concept. |
| `fictional_product` | Required for `parody_ui` and `product_mock`: the invented name, which must not be a real brand. `media_check.py` fails a parody with no fictional name or with a real one. |
| `humor_or_hook_device` | The mechanism the image executes (literalism, escalation, bureaucratic deadpan, mismatch of scale). If none can be named, the image is decoration. |
| `visual_concept` | Two to four sentences, one idea, concrete nouns. Readable by a designer. |
| `subject`, `setting` | Materials, age, clothing, texture; where, when, light source and colour. Concrete beats adjectival in every vendor guide. |
| `composition`, `style` | Framing, angle, focal point, negative space; medium, palette, era or reference, finish. Camera and lens words are look cues. |
| `on_image_text` | Exact strings, each once, placement, typography by look. Budgets in §8. Omit the block when there is no text; a chart's labels count as text. |
| `must_show` | Positive details that carry the joke or the proof. |
| `keep_out_as_positive` | Every exclusion rewritten as what replaces it. Veo, Runway and Nano Banana have no negative prompt; a "no" in those prompts fails `media_check.py`. |
| `aspect_ratio`, `target_pixels`, `resolution_tier` | Per platform in `references/platform_specs.md`; `media_check.py` validates the ratio against `config/postsmith.yaml`. 2K minimum with text because fine type breaks at 1K. |
| `tool` | `primary` and `fallback` are ids from {gpt_image, nano_banana, veo, runway}: the config keys and the prompt file names. Name the exact model or setting in `reason` (Nano Banana Pro vs 2, GPT Image quality high, Veo 3.1 Fast). |
| `references` | Role by index. `first_frame` with `source: generated_still` is the Runway image-to-video path. |
| `video` | §2. Only when `decision: video`. |
| `real_capture_direction` | §3. Only when `decision: real_capture_direction`. |
| `safety_checks` | All three true or the brief fails: tools refuse real faces and logos, and a lookalike is worse than a refusal. |
| `alt_text` | Carries the point alone (§5). One or two plain sentences; LinkedIn 120 chars, X 1,000 (`platforms.<p>.alt_text_max`). Never the caption restated. |
| `factual_claims_in_visual` | Any number, label or comparison a chart or infographic asserts, each traceable to the caption, the brief facts or persona. The judge fails an unlisted number. |
| `risk_notes` | What may go wrong in rendering and what Deep should check (spelling, a hand, a logo that crept in). |

## 5. The delete test
Remove the media and read the post again. If the post still lands, the decision is `none`, whatever the corpus
prior says. The test has a second half, run on the alt text: a screen-reader user who gets only `alt_text` must
get the joke or the point. If the alt text has to explain the caption to make sense, the visual is restating it
(M4) and the judge's `alt_text_alone` and `does_work` sub-results both fail. Write the alt text before the prompt;
if it cannot be written, there is no image.

## 6. Decision rules M1-M7 with reasons
- **M1 delete test first.** Media is a cost (a second thing to get right, a slop risk, an alt text) and text-only
  is the median-best format on X and a fine one on LinkedIn, so the burden is on the image. X defaults to `none`.
- **M2 X.** Image only when the image is the joke or the proof (meme, chart, fake-document parody, a real
  screenshot direction): X's own data puts text above image above video on median engagement, and a decorative
  image costs the reader a tap. Video only if native with the hook in the first second; there is no minimum
  duration.
- **M3 LinkedIn.** Image is the default lift (about 1.2x reach, 1.33x engagement, portrait over landscape) but
  only in genres a reader stops for: whiteboard or infographic explainer, fake-document or parody-UI punchline,
  meme, comic panels, a real photo of Deep, a real screenshot. Generic illustration, 3D robots, gradients and
  handshakes are the slop LinkedIn says it detects: `none`.
- **M4 text-only wins** when the rhythm is the hook (story, one-liner, hot take), when the visual would restate
  the caption, when on-image text would pass about 12 words (it will render wrong and read as a slide), or when
  the concept needs a real face or a real logo (every tool's policy blocks both).
- **M5 corpus prior.** The lens author's train-post media rate sets the burden of proof: above 60%, `none` must
  be justified; below 20%, `image` must be. Keeps the decision corpus-relative rather than a taste call.
- **M6 real product output is never faked.** Claude Code, Cursor, dashboards, bank screens, chat transcripts:
  `real_capture_direction` with what to open, type, crop and redact. A parody UI names a fictional product and
  carries no real logo. A faked real screenshot is a Community Note, a lost audience and a lie in Deep's name;
  `media_check.py` rejects it outright.
- **M7 carousel.** Documents lead LinkedIn on median engagement (about 21.8%) and saves, but a PDF is out of
  scope; flag `carousel_suggested: true` with a five-slide outline so Deep can decide.

## 7. Genres (`style/taxonomies/media_roles.md`)
`meme` · `fake_document` · `parody_ui` (fictional product named in `fictional_product`, no real logo) · `whiteboard_explainer` ·
`diagram_chart` · `photoreal_scene` · `product_mock` (a fictional product, obviously so) · `comic_panels` ·
`user_photo_direction` (Deep captures it) · `real_capture_direction` (Deep captures it).
`fake_screenshot` is not a brief genre: of a real product it is rejected by `media_check.py` (M6); of a fictional
one it is `parody_ui`.

## 8. Text budgets per tool (`config/postsmith.yaml` → `media`)
| Tool | Budget | Why |
|---|---|---|
| gpt_image | `on_image_text` ≤ 12 words total, each line ≤ 8; prompt 80-200 words | the docs still warn about text placement; short lines render once and legibly |
| nano_banana | ≤ 5 text elements; 2K minimum with text; Pro model for more than one line, for whiteboard or chart genres, or when facts must be grounded | Pro's typography error rate is the lowest of the four tools; NB2 is faster for everything else |
| veo | ≤ 700 words hard cap (aim under 150); duration 4, 6 or 8 s; one quoted line ≤ 15 words and ≤ 2.5 words per second; no on-screen text; no negation words | 1,024-token prompt limit; speech must fit the clip; the model does not render captions reliably |
| runway | ≤ 1,000 chars; 2-10 s (aim 5-8); motion only for image-to-video; no dialogue, no text; no negation words | the still supplies look; long prompts create conflicting instructions |

## 9. What `media_check.py` fails on (contracts §11, as implemented in `tools/media_check.py`)
- Required when `decision != none`: `visual_concept`, `aspect_ratio`, `delete_test`, `decision_reason`,
  `tool.primary` (a warning only for `real_capture_direction`). `decision_reason` must contain an `M1`-`M7` id.
  A `delete_test` of "nothing", "none" or "n/a" fails: the decision must then be `none`.
- Tool and decision agree: an image tool for `image`, a video tool for `video`. Tool ids are matched by family
  substring (`gpt`, `nano`/`banana`, `veo`, `runway`), and prompt files are keyed by file stem and read whole,
  so a prompt file is the paste text and nothing else.
- `real_capture_direction` needs its block with `what_to_open`, `what_to_show`, `crop`, `redact` (empty ones warn).
- `aspect_ratio` must be in the platform's `image_aspects` or `video_aspects` (config).
- `genre: fake_screenshot` fails outright (M6). `parody_ui` fails when a real brand appears in the content fields
  or when no fictional product is named (`fictional_product`, or a quoted name in `visual_concept`/`subject`).
- On-image text: each line ≤ 8 words; ≤ 12 words in total when gpt_image is the primary or has a prompt; ≤ 5
  elements for nano_banana; every line must appear verbatim, in quotes, in every image prompt; 1K with text warns.
- A negation word (`no `, `don't`, `do not`, `without`, `avoid`, `never`) in a Veo, Runway or Nano Banana prompt.
- Video: the block must exist; Veo duration in {4, 6, 8}, aspect in Veo's list, prompt ≤ 700 words, dialogue ≤ 2.5
  words × seconds; Runway ≤ 1,000 chars, 2-10 s, text-to-video 16:9 only unless `video.start_frame:
  generated_still` marks image-to-video, whose aspect must be in the I2V list. Any of the words `caption`, `text
  on screen`, `on-screen text`, `onscreen text`, `title card`, `subtitle` in a Veo or Runway prompt fails as an
  on-screen text request, so none of them may appear in a video prompt in any sense.
- `alt_text` over the platform cap fails; a missing one warns (the judge needs it).
- A known real person's name in the brief content or a prompt fails; a brand other than Deep's own warns in a
  prompt and fails inside a parody; `real_capture_direction` fields are exempt.
Output `{"ok", "fails": [...], "warnings": [...]}`; the director fixes only what is cited.
