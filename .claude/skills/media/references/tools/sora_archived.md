# Sora 2: archived (discontinued)

status: **discontinued**. The Sora app and web product shut on 2026-04-26; the API shuts on 2026-09-24.
verified_on: 2026-09-17 · sources: https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation ;
https://developers.openai.com/cookbook/examples/sora/sora2_prompting_guide ;
https://developers.openai.com/api/docs/guides/video-generation

Do not pick `sora` as a tool: it is not a `tool.primary` id, `config/postsmith.yaml` has no budget for it, and
`media_check.py` has no checks for it. This file keeps the transferable rules from the archived guide as a
**generic prose-plus-dialogue fallback** for the day a successor tool appears. When one does, copy the template
into a new `references/tools/<tool>.md` with its own `verified_on`, sources and config budget; do not use this
file directly.

## Generic prose + dialogue template (archived shape)
```
{Scene prose: setting, time of day, wardrobe, materials, light.}
{Cinematography line: shot size, lens, camera move, mood.}
{Beat 1.} {Beat 2.} {Beat 3, optional.}
Dialogue:
- {Speaker A}: "{line}"
- {Speaker B}: "{line}"
Sound: {diegetic cues that anchor rhythm, not a score}.
```

## Rules that transfer to any prose-first video model
- One camera move and one subject action per shot; short clips follow instructions better.
- 4 s fits one or two exchanges of dialogue, 8 s fits three or four; speech must fit the clip.
- Describe diegetic sound as rhythm anchors (a pen scratching, a door), not as a score.
- Edit by naming a single change ("same shot, 85mm"), keeping everything else stated as unchanged.
- The postsmith rules still apply on top: no on-screen text, no real people, no real product output (M6),
  positive phrasing, alt text that carries the point alone.
