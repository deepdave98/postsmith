# Media genres and roles (v1, 2026-09-17)

Source: docs/design/research-media-prompts.md §4-5, docs/design/research-style-method.md A2. Cards record
`media_analysis: {genre, role, caption_dependency, reproducibility, ...}` for every corpus post with media; media briefs
record `genre`; the media-director cites rules M1-M7 and the media-judge scores against them.

## Genres (`media_analysis.genre`, `brief.genre`)

| id | definition | example | when it works | generation |
|---|---|---|---|---|
| meme | recognizable format where the image carries the joke | two-panel "expectation / reality" with the post's specific | X; the format is current in the scene | promptable; on-image text ≤ 12 words |
| fake_document | an obviously fictional document as the punchline | laminated "AGENT INCIDENT REPORT" on a fridge | LinkedIn; the root-cause line is the joke | promptable (GPT Image or Nano Banana Pro for exact text) |
| parody_ui | a fictional product's interface as the joke | a settings screen with a "be helpful (dangerous)" toggle | the product name is fictional and no real logo appears | promptable; must name a fictional product (M6) |
| whiteboard_explainer | hand-drawn diagram that explains the post's mechanism | three boxes and an arrow that the caption does not draw | LinkedIn; the drawing adds a step the text only implies | promptable; ≤ 5 text elements |
| diagram_chart | a chart or diagram asserting numbers | a two-bar chart of cost before/after | every number is in `factual_claims_in_visual` | promptable; factual sub-result is hard |
| photoreal_scene | a staged photographic scene | a phone photo of a sticky note on a monitor | the scene reads as "taken 30 seconds ago" | promptable; no real faces or logos |
| product_mock | a mock of Deep's own product or artifact | a fictional dashboard of Deep's own tool | the brand is Deep's own | promptable; brand check exempts only the author's brand |
| comic_panels | 2-4 panels with dialogue | an agent and a CFO in three panels | the last panel is the punch; ≤ 8 words per panel | promptable |
| user_photo_direction | a real photo of the author, with shot direction | "Deep at the desk, laptop open on the error, phone photo" | LinkedIn; faces beat polished brand shots | needs_real_face; the brief gives direction only |
| real_capture_direction | a real screenshot with exact capture instructions | "open Claude Code, run X, crop to the last 12 lines, redact the key" | proof of a real product's output (M6: never faked) | needs_real_screenshot; capture_direction sub-result |
| photo_of_artifact | a real photo of a real object or page (corpus analysis) | a whiteboard with "???" in the third box | annotating the corpus; in generation becomes user_photo_direction or photoreal_scene | needs_real_photo |
| screenshot | a real screenshot in a corpus post (corpus analysis) | a pricing page, a terminal | annotating the corpus; in generation this is always real_capture_direction | needs_real_screenshot |

Never: generic illustration, 3D robots, brains, gradients, handshakes, stock imagery (slop_screen, hard). `fake_screenshot` of a
real product is rejected outright by `media_check.py` (M6). Carousel/PDF outranks everything on LinkedIn but is out of scope:
`carousel_suggested: true` with a 5-slide outline.

## Roles (`media_analysis.role`; the delete test M1 decides `none`)

| id | the media... | example |
|---|---|---|
| proof | is the receipt the caption points at | the invoice, the terminal output, the chart |
| punchline | lands the joke the caption sets up | the "???" box; the root-cause line on the form |
| contrast | says the opposite of the caption or of itself | "no price increase" email next to the new pricing page |
| context | shows the scene the caption assumes | the whiteboard the meeting happened at |
| aesthetic | decorates; adds no information | a gradient header (fails the delete test; `none` in generation) |
| none | there is no media, or it should be removed | X default |

## Caption dependency (`media_analysis.caption_dependency`)

| value | meaning |
|---|---|
| standalone | the caption makes sense without the media; the media adds proof, context or a second beat |
| media_dependent | the caption does not make sense without the media (screenshot_commentary, meme_format); alt text must carry the point |

## Reproducibility (`media_analysis.reproducibility`)

| value | meaning | generation path |
|---|---|---|
| promptable | a prompt to a named tool can produce it | image brief with `tool.primary` |
| needs_real_photo | a real photo of a real object or place | user_photo_direction or none |
| needs_real_screenshot | real product output | real_capture_direction with what to open, show, crop, redact |
| needs_real_face | the author's or another real person's face | user_photo_direction; never generated |

Decision rules (media-director cites one in `decision_reason`): M1 delete test first; M2 X image only when it is the joke or the
proof; M3 LinkedIn image default in the listed genres only; M4 text-only wins when the rhythm is the hook, the visual would
restate the caption, on-image text would exceed ~12 words, or a real face or logo is needed; M5 corpus prior (lens author > 60%
media → justify `none`; < 20% → justify `image`); M6 real product output is never faked; M7 carousel suggestion.
