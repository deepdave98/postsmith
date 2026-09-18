# Runway Gen-4.5: prompt template

verified_on: 2026-09-17 · config: `media.runway` (max_prompt_chars 1000; duration_range 2-10; t2v_aspects 16:9; i2v_aspects 9:16, 1:1, 3:4, 16:9)
sources: https://help.runwayml.com/hc/en-us/articles/46974685288467-Creating-with-Gen-4-5 ;
https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide ;
https://help.runwayml.com/hc/en-us/articles/47313737321107-Text-to-Video-Prompting-Guide ;
https://help.runwayml.com/hc/en-us/articles/46749315925395-Camera-Terms-Prompts-Examples ;
https://runway.com/research/introducing-runway-gen-4.5
prompt file: `drafts/<run>/media/<cid>.prompts/runway.md` (the paste text only; settings live in the brief's `video` block)

## What it is, when to pick it
Gen-4.5 (2025-12-01; Gen-4 is legacy) is the second video tool, used for **image-to-video from a still** produced
with the GPT Image or Nano Banana template. Pick it when a specific look must hold exactly (a document, a parody
UI, a comic panel coming to life) and no speech is needed. Its strengths are motion quality, prompt adherence,
precise camera choreography and physics; its own research page lists causal reasoning, object permanence and
success bias as weaknesses. Audio is conflicting between the help-center spec (none) and press (native audio
added December 2025): treat the output as silent and plan voiceover in an editor. Web only; 720p; 24/25 fps;
2-10 s; text-to-video is 16:9 only, so it never fits a LinkedIn or X vertical video; use image-to-video.

## Settings Deep sets in the app
Gen-4.5, image-to-video, upload the clean still (no artifacts, no visible text errors), 9:16 or 1:1 to match the
still, duration 5-8 s, 24 fps. Text-to-video only when consistency does not matter, and then 16:9 (which no
platform video list in config allows: it is a last resort for a landscape asset Deep will crop himself).

## Image-to-video template (the default)
```
The camera {single move from Runway's camera vocabulary} as {the subject / the object on the left} {action}. {Environmental motion}. {Motion style and speed}.
[00:00 through 00:0N] {beat}. [00:0N through 00:0M] {beat}. [00:0M through 00:08] {beat}.
```
## Text-to-video template (only when consistency does not matter)
```
{Camera term} shot of {subject with detail} {action} in {environment}. {Lighting}, {style}, {palette}. {Environmental motion}. {Motion timing}.
```

## Rules, each with its reason
- Motion only in image-to-video: the still already supplies composition, lighting, subject and style, and
  re-describing them creates conflicting instructions (Runway's own warning).
- Generic subject references ("the subject", "the hand on the right"): the model maps them to the still.
- One camera move, from Runway's camera vocabulary (dolly in, whip pan, rack focus, crane, handheld, locked
  static); the camera library has worked examples per term.
- Timestamps as `[00:00 through 00:02]` paired with the natural-language line, at most three beats.
- Positive phrasing only ("sharp focus", not "not blurry"); `media_check.py` fails any Runway prompt containing
  `no `, `don't`, `do not`, `without`, `avoid` or `never`.
- No dialogue, no on-screen text: neither is a documented capability, and `media_check.py` fails a prompt
  containing any of the words `caption`, `subtitle`, `title card`, `text on screen`, `on-screen text` in any sense.
- Under 1,000 characters (a third-party cap kept as the config limit); start simple and add one element per
  iteration; JSON prompting is a placebo per Runway; prompt order does not matter.
- Abstract words (beautiful, professional, cinematic) carry no motion; say what moves, how fast, and how the
  camera behaves.
- If the motion misfires, strip the prompt to the core move and re-add one element.

## Rendered example (image-to-video, using the Nano Banana still)
Brief: the incident-form still moves; a hand writes the root-cause line; 9:16, 8 s, silent.
```
The camera holds a locked static frame as a hand in a grey hoodie sleeve enters from the right holding a blue ballpoint and writes on the second line of the form, then underlines the words twice and pulls back out of frame. The magnet wobbles slightly when the hand brushes the form. Slow, deliberate motion, handheld-steady, documentary realism.
[00:00 through 00:02] hand enters and pauses. [00:02 through 00:06] writing and double underline. [00:06 through 00:08] hand exits, magnet settles.
```

## Self-check before returning (mirrors `media_check.py`)
Under 1,000 characters · `video.duration_s` between 2 and 10 (aim 5-8) · image-to-video with a `references`
entry `{role: first_frame, source: generated_still}` and the still's own prompt written under the image tool's
file · aspect 9:16 or 1:1 for image-to-video; text-to-video only at 16:9 · no negation words · no dialogue, no
text and none of the on-screen-text words · one camera move, at most three beats · `video.dialogue: []` and
`captions_plan` set.
