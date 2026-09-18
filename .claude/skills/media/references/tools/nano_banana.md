# Nano Banana (Gemini image: Nano Banana 2 / Nano Banana Pro): prompt template

verified_on: 2026-09-17 · config: `media.nano_banana` (on_image_text_max_elements 5; min_resolution_with_text 2K)
sources: https://ai.google.dev/gemini-api/docs/image-generation ;
https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana ;
https://blog.google/products-and-platforms/products/gemini/prompting-tips-nano-banana-pro/ ;
https://blog.google/innovation-and-ai/technology/ai/nano-banana-2/ ; https://deepmind.google/models/gemini-image/pro/
prompt file: `drafts/<run>/media/<cid>.prompts/nano_banana.md` (the paste text only; settings live in the brief)

## What it is, when to pick it
Three models: Nano Banana 2 (`gemini-3.1-flash-image`, default in the Gemini app), Nano Banana 2 Lite, and Nano
Banana Pro (`gemini-3-pro-image`, paid plans, best typography and factual accuracy). Pick this family for dense
or exact text, infographics, whiteboard explainers, diagrams, multi-panel comics, semantic edits ("change only
the sofa") and anything that must be grounded in a current fact (Pro and NB2 can call Google Search while
drawing, unique among the four tools). Weak spots the docs name: small faces, spelling in fine text, factual
errors in data-driven infographics without grounding, artifacts after heavy edits, no character consistency
guarantee, knowledge cutoff January 2025 without grounding.

## Model selection rule (name the pick in `tool.reason`)
**Pro** when `on_image_text` has more than one line, when the genre is `whiteboard_explainer` or `diagram_chart`,
or when a fact must be grounded. **Nano Banana 2** for everything else: it is faster and the default in the app.
Never Lite for a post image.

## Settings Deep sets in the app
Gemini app: switch the model to Pro when the rule says so; state the ratio and resolution in the prompt itself
("4:5 portrait, 2K"), which is Google's own tip, because the app has no ratio control; download at 2K (paid
plan). AI Studio when an explicit aspect ratio and resolution control matters. 2K minimum whenever the image
carries text (config).

## Template
```
Create a {genre} for a {platform} post. Output {aspect_ratio} ({target_pixels}) at {resolution_tier}.
{One-paragraph narrative: the subject with materials and texture, doing the action, in the setting, lit by the light source, seen from the framing and angle with the lens; medium, palette, era.}
{Purpose sentence: "This should read as ... so that a tech audience ..."}
Render the text exactly as written, each once: "{line 1}" in {typography_intent} {placement}; "{line 2}" ... Keep the type large and every letter crisp.
{Positive replacements for anything to keep out.}
{If references: "Use image 1 for the subject's appearance, image 2 for the colour palette."}
{If grounded: "Search for {fact} and make the labels accurate."}
```

## Rules, each with its reason
- Narrative sentences that start with a verb (Create, Render, Transform), never keyword lists: the model is
  trained on descriptions, and a list reads as tags.
- Materials, textures, light source, lens ("navy tweed", "85mm, f/1.8, window light from the left"): the guide's
  hyper-specific rule; adjectives like "professional" carry no picture.
- A purpose sentence: the model chooses polish and hierarchy from the intended use.
- Exact text in quotes, each once, fonts described by look (bold condensed sans, brush script), at most five
  text elements, 2K minimum; draft the copy in a prior chat turn and reference it when the app is used
  conversationally. Pro for precise typography.
- Positive framing only ("empty street", not "no cars"): there is no negative prompt, and `media_check.py` fails
  any Nano Banana prompt containing `no `, `don't`, `do not`, `without`, `avoid` or `never`.
- References by role ("image 1 for pose, image 2 for style"); NB2 accepts up to 10 object and 5 character
  references, Pro 6 object and 3 style.
- Iterate one edit at a time ("Using the provided image, change only ..., keep everything else identical"); if a
  character drifts after many edits, restart with the full description.
- Never a real person's likeness, never a real logo, never a real product's output. A grounded infographic still
  lists every number it asserts in `factual_claims_in_visual`.

## Rendered example
Brief: LinkedIn, `fake_document`, laminated incident-report form on a startup fridge, two exact text lines,
4:5, 2K, Nano Banana Pro (two lines of exact text).
```
Create a photorealistic fake-document image for a LinkedIn post. Output 4:5 (1080x1350) at 2K.
A laminated A4 incident form, printed in plain black corporate type and filled in with blue ballpoint handwriting, is pinned by a single round magnet to a scuffed white office fridge in a small startup kitchen. Soft late-afternoon window light comes from the left; a coffee ring stains one corner. Straight-on medium close-up shot on a phone camera, the form filling most of the frame, natural colour, faint grain.
This should read as a real bureaucratic artefact so the deadpan header lands for an engineering audience.
Render the text exactly as written, each once: "AGENT INCIDENT REPORT" as a bold, wide sans-serif header centred at the top of the form; "Root cause: it was being helpful" as blue handwriting on the second line. Keep the type large and every letter crisp; the remaining field labels are short generic words like Date and Severity.
Keep the fridge clean of any brand marks; the only legible words are the ones above.
```

## Self-check before returning (mirrors `media_check.py`)
Every `on_image_text.lines` entry appears verbatim in quotes · at most five text elements · `resolution_tier`
2K or 4K when text is present · the prompt contains none of the negation words · aspect ratio matches the brief
and the platform · no real person's name, no brand other than Deep's own · `tool.reason` names Pro or 2.
