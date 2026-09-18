# Veo 3.1 (Gemini app, Flow, AI Studio): prompt template

verified_on: 2026-09-17 · config: `media.veo` (max_prompt_words 700; durations 4/6/8; dialogue_words_per_second 2.5; aspects 16:9, 9:16)
sources: https://ai.google.dev/gemini-api/docs/veo ; https://ai.google.dev/gemini-api/docs/models/veo-3.1-generate-preview ;
https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1 ;
https://deepmind.google/models/veo/prompt-guide/ ; https://support.google.com/flow/answer/16352836 ;
https://blog.google/innovation-and-ai/products/flow-video-tips/
prompt file: `drafts/<run>/media/<cid>.prompts/veo.md` (the paste text only; settings live in the brief's `video` block)

## What it is, when to pick it
Veo 3.1 (with Fast and Lite variants; there is no Veo 4) is the primary video tool because it generates native,
synchronised audio: a spoken line, sound effects and an ambient bed in one 8-second clip. Pick it when the post
needs motion with speech or sound; pick Runway when a locked still must move silently. Limits that shape every
prompt: 1,024 tokens; 4, 6 or 8 s (8 s required for 1080p and for reference images); 16:9 or 9:16 only; up to 3
reference images ("ingredients") to lock a character, object or setting; first-and-last-frame interpolation;
extension by 7 s at 720p. No negative-prompt field exists in the Gemini API, and real-person faces are restricted.
On-screen text is not a documented capability and community reports show garbled captions (unverified), so
captions are burned in an editor afterwards.

## Settings Deep sets in the app
Model Veo 3.1 (Fast for drafts, Lite only to extend); 9:16 for LinkedIn and X vertical; 8 s; 1080p. "Using the
provided image for the {form, character, setting}, ..." at the start of the prompt when a generated still is
the first frame. For first-and-last-frame mode, describe only the transition and the audio.

## Template
```
{Composition + one camera move}, {subject with physical detail} {action} in {setting}. {Style: film genre or animation style}, {ambiance: light and colour}.
[00:00-00:0N] {beat 1}. [00:0N-00:0M] {beat 2}. [00:0M-00:08] {beat 3}.
{Speaker description} says, "{line}".
SFX: {one or two concrete sounds}. Ambient noise: {bed}.
{Positive replacements for exclusions.}
```

## Rules, each with its reason
- One camera move for the clip: the guides list moves (dolly, tracking, crane, POV, aerial) and every extra move
  divides eight seconds into nothing.
- At most three timestamped beats that together cover the clip: `[00:00-00:03]` syntax is the documented way to
  direct a multi-beat sequence in one generation; a fourth beat does not fit.
- One quoted line, at most 15 words, attributed to a described speaker ("an unseen man, tired and deadpan"),
  because speech must fit inside the clip (about 2.5 spoken words per second; `media_check.py` enforces
  dialogue words ≤ 2.5 × duration) and lines given to minor characters misfire.
- `SFX:` and `Ambient noise:` lines, in that syntax, for effects and bed; audio is the reason to use this tool.
- No on-screen text requests, and none of the words `caption`, `subtitle`, `title card`, `text on screen`,
  `on-screen text` anywhere in the prompt in any sense: the model does not render type reliably, and
  `media_check.py` reads any of those words as a request for it; `captions_plan: burn_in_in_editor` covers the
  need.
- Positive phrasing only: there is no negative prompt, and `media_check.py` fails any Veo prompt containing
  `no `, `don't`, `do not`, `without`, `avoid` or `never`. Rewrite each exclusion as what is there instead.
- Under about 150 words (hard cap 700 in config, well under 1,024 tokens): clarity over length.
- 9:16 for both platforms (16:9 is not in either platform's `video_aspects`), 8 s, 1080p.
- No real people, no lookalikes of Deep's colleagues or of named founders; detailed descriptions of an invented
  person (age, hair, clothing) improve adherence.

## Rendered example
Brief: the incident-form concept as a video; still generated first with the Nano Banana template; one line of
dialogue; 9:16, 8 s, 1080p.
```
Static medium close-up on a laminated incident form pinned to a scuffed white startup fridge, late-afternoon window light from the left, phone-camera realism, natural colour.
[00:00-00:03] A hand in a grey hoodie sleeve enters from the right holding a blue ballpoint and pauses over the "Root cause" line. [00:03-00:06] The hand writes slowly, the pen scratching, then underlines the words twice. [00:06-00:08] The hand retreats and a second magnet is slapped onto the form for emphasis.
An unseen man, tired and deadpan, says, "It bought four hundred domains. To be safe."
SFX: ballpoint scratching on laminate, a magnet clacking on metal. Ambient noise: fridge compressor hum, distant office keyboard.
The form's printed header is a generic bold block of black type; the only visible writing is handwritten blue ink.
```
(The quoted "Root cause" in the first beat names a line already on the still; it asks for nothing new to be
rendered.)

## Self-check before returning (mirrors `media_check.py`)
Under 700 words (aim under 150) · `video.duration_s` in {4, 6, 8} · dialogue words ≤ 2.5 × duration and one
line ≤ 15 words · no negation words · none of the on-screen-text words listed above · aspect 9:16 (or 16:9 only
where a platform allows it) · no real person's name, no brand other than Deep's own · at most three beats, one
camera move.
