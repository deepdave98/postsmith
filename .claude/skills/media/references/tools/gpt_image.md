# GPT Image (ChatGPT Images 2.5): prompt template

verified_on: 2026-09-17 · config: `media.gpt_image` (on_image_text_max_words 12; prompt_words 80-200)
sources: https://developers.openai.com/api/docs/guides/image-prompting ;
https://developers.openai.com/api/docs/guides/image-generation ;
https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide ;
https://openai.com/index/introducing-chatgpt-images-2-5/ ;
https://developers.openai.com/api/reference/resources/images/methods/generate
prompt file: `drafts/<run>/media/<cid>.prompts/gpt_image.md` (the paste text only; settings live in the brief)

## What it is, when to pick it
ChatGPT Images 2.5 shipped 2026-09-08 (API default `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst` for
precision; `gpt-image-2` and `1.5` are legacy, DALL-E is irrelevant). Pick it for photoreal documents and objects,
a parody UI of a fictional product described as a shipped app inside a device frame, logos for a fictional brand,
and structured diagrams; it reasons about the scene before drawing and infers period detail from a place and a
date. It is the fallback when a Nano Banana concept needs a photographic finish. Weak spots the docs name:
element placement in dense layouts, the same character across separate generations, small type (use quality
high), and up to two minutes on complex prompts.

## Settings Deep sets in the app
Image mode. Vertical for 4:5 (then crop to 1080x1350; whether typing "4:5" yields an exact 4:5 file is
unverified), Square for 1:1. Quality `high` whenever the image carries text; `xhigh` or `max` only when high
fails. API: `size` as custom WxH (multiples of 16, ratio at most 3:1), `quality=high`, up to 32,000 characters.

## Template (keep this order; drop empty slots)
```
Use: {genre} for a {platform} post, {aspect_ratio} portrait/square/landscape ({target_pixels}), {resolution_tier}.
Scene: {setting}. {style.medium}, {style.palette}, {style.era_or_reference}, {style.finish}.
Subject: {subject}. {composition.framing}, {composition.angle}; focal point {composition.focal_point}; {composition.negative_space}.
Details: {must_show, comma-separated}. {keep_out_as_positive}.
Text (EXACT, verbatim, each appears once, nothing else written anywhere): "{line 1}" as {typography_intent} at {placement}; "{line 2}" ...
Constraints: photorealistic / illustrated as stated; no watermark, no logos, no extra text; keep the composition uncluttered.
If editing: change only {X}; keep {identity, framing, lighting, layout, existing text} unchanged.
```

## Rules, each with its reason
- Order Use → Scene → Subject → Details → Text → Constraints → If-editing: the guide's own scene → subject →
  details → constraints order, with the intended use first so the model picks the right polish.
- Say "photorealistic" or "real photograph" for photo genres; camera words are look cues, not physics.
- Parody UI: describe the app as a shipped product of a fictional brand (layout, hierarchy, real UI elements) in
  a device frame. The fictional name is what separates a parody from a faked screenshot (M6).
- Aspect ratio in words and numbers ("4:5 portrait, 1080x1350") because the UI toggle is coarse.
- On-image text in quotes, once, with placement and typography by look, and "nothing else written anywhere";
  spell odd or brand-like words letter by letter; at most 12 words in total and 8 per line (config), because the
  docs still warn that text placement and clarity can struggle.
- 80-200 words (config). This tool tolerates "no watermark" in Constraints, but every other exclusion is better
  as its positive replacement, and the same brief must also render in Nano Banana, where negation fails.
- Regenerating: one change per follow-up, restating what must not change (the guide's edit rule); drift comes
  from unstated invariants.
- References by role and index ("Image 1: subject, Image 2: style"); the 16-reference figure is third-party.
- Never a real person's likeness, never a real logo, never a real product's output.

## Rendered example
Brief: LinkedIn, `fake_document`, a laminated incident-report form on a startup fridge, on-image text
"AGENT INCIDENT REPORT" and "Root cause: it was being helpful", 4:5, 2K.
```
Use: fake-document photo for a LinkedIn post, 4:5 portrait (1080x1350), 2K.
Scene: a scuffed office fridge door in a small startup kitchen, late-afternoon window light from the left, a bowl of fruit blurred in the foreground. Photorealistic iPhone-style photo, natural colours, slight grain.
Subject: a laminated A4 form pinned by one magnet, printed in plain corporate black type, filled in with blue ballpoint handwriting. Medium close-up, straight-on, form fills 80% of the frame with the fridge edge visible.
Details: a coffee ring on the corner, a "REPORTED BY: the intern" handwritten line, a checked box reading "will happen again".
Text (EXACT, verbatim, each appears once, nothing else legible): "AGENT INCIDENT REPORT" as a bold sans-serif printed header centred at the top; "Root cause: it was being helpful" in blue handwriting on the second line of the form.
Constraints: no logos, no watermark, no extra words on the form beyond the two lines plus short generic field labels.
```
(The example's Details line adds two short handwritten items; when the brief's `on_image_text` budget is already
at 12 words, leave such extras out or count them.)

## Self-check before returning (mirrors `media_check.py`)
Every `on_image_text.lines` entry appears verbatim in quotes · total on-image words ≤ 12, each line ≤ 8 · prompt
80-200 words · aspect ratio matches the brief and the platform · no real person's name, no brand other than
Deep's own · parody UI names a fictional product · the still, if it feeds Runway, is described clean and
artifact-free.
