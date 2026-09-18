---
name: media
description: Builds or rebuilds the media brief and paste-ready image or video prompts (GPT Image, Nano Banana, Veo 3.1, Runway Gen-4.5) for one finalist variant of a /post run; decides none, image, video or a real-capture direction by rules M1-M7, checks the result with media_check.py and a fresh-context media-judge, and updates the variant under final/. Use when Deep says "media for", "make an image for", "redo the media on", "give me a Veo prompt for", "try nano banana on", "no media on", or wants a screenshot direction for a draft.
argument-hint: "<draft-id> <li|x> [--tool gpt_image|nano_banana|veo|runway] [--genre <id>] [--none]"
disable-model-invocation: true
allowed-tools: Read Write Agent Bash(uv run *)
effort: high
metadata:
  skill_version: "1.0"
---

# /media

Request: $ARGUMENTS

Project state (versions, health, corpus counts, nags):
!`uv run tools/status.py --brief || true`

## What this is for
One finalist variant gets a media brief at `drafts/<run>/media/<cid>.brief.yaml` and, when the decision is image or
video, a primary and a fallback prompt Deep pastes into the tool himself, at
`drafts/<run>/media/<cid>.prompts/<tool>.md`. Nothing is rendered here and nothing is posted. `/post` runs the same
two agents on its top finalists; `/media` exists to redo one variant after a `media_miss` rating, to force a tool or
a genre, or to switch a variant to text-only.

## Why the shape matters
On LinkedIn a single portrait image lifts reach about 1.2x and engagement about 1.33x, but only when the image is
the joke, the proof or an explainer; generic AI illustration is what readers flag as slop and what LinkedIn says it
detects. On X, text beats every media format on median engagement, so an image has to earn its place as evidence or
punchline. A faked screenshot of a real product is a Community Note waiting to happen and a breach of trust with
Deep's own audience. So `none` is a frequent and legitimate answer, every decision must cite a rule, and the judge
that checks the brief never sees the director's reasoning.

## Resolve the variant
`uv run tools/draft_id.py <draft-id> <li|x> --json` resolves the fuzzy id to `{run, cid, platform, path}`, where
`path` is the variant file under `drafts/<run>/final/`; on `ok: false` with `candidates`, ask Deep which one and
rerun. That variant file's front matter carries `round` and `scores_path`, so the candidate lives at
`drafts/<run>/round<k>/candidates/<cid>.{md,txt}` and its `candidate_sha` is in
`drafts/<run>/round<k>/scores/<cid>.tier0.json`. Collect what the director needs and nothing else:
- the caption: `drafts/<run>/round<k>/candidates/<cid>.txt` (post text only);
- the writer's `media_intent` and `assignment.lens` from `drafts/<run>/round<k>/candidates/<cid>.md`;
- `style/persona.md` (media willingness, `do_not_target`, platform choices), `style/media_habits.md`, and
  `style/authors/<lens>.md` when the variant has a lens;
- three to five preview images of the lens author: rows of `corpus/manifest.jsonl` with that `author_slug` and
  `split: train`, then `corpus/media/<post_id>/preview_*.jpg`, one per post. Train only, because heldout posts stay
  unseen by anything that shapes output. Lens-free variant: one preview each from up to five train authors, so the
  M5 corpus prior is corpus-wide;
- media lines from `memory/lessons.md`, if any (Deep's `media_miss` and `media_great` tags, distilled).

## The loop: `run_next.py --media` drives it
Before the first call, copy the previous brief's `decision`, `decision_reason` and media result (from
`media/<cid>.media-check.json` and `media/<cid>.media-judge.json`, when they exist) into `drafts/<run>/run.log`,
because a rebuild overwrites that cid's brief, prompts, check and judge files.

Then repeat `uv run tools/run_next.py <run> --media <cid> --json` until it emits no action. It re-derives only the
media step for that finalist (a delivered run included), in the same action shape as `/post`, and marks `final/`
stale so the report is rebuilt afterwards. Execute every action it emits, as given:
1. The `media-director` agent action (first on a rebuild). Its action carries `candidate`, `inputs`,
   `output_path` and `prompts_dir`; the delegation prompt is those lines plus the paths collected above (persona,
   media habits, the lens profile, the train preview images, the media lessons), any override (`--tool`,
   `--genre`, `--none`) and the reference files under `.claude/skills/media/references/`. It writes the brief and
   the prompts and replies with paths. Pass no judge output, no ratings and no verdict from an earlier brief: the
   director is tuned by Deep's lessons, not by the judge, for the same reason writers never see the rubric.
2. The `media_check.py` tool action (`uv run tools/media_check.py drafts/<run>/media/<cid>.brief.yaml --prompts
   drafts/<run>/media/<cid>.prompts --json`, its JSON at `drafts/<run>/media/<cid>.media-check.json`). On `fails`,
   hand the list back to the same director once (resume it by name, or give a fresh `media-director` the brief
   path plus the fails), then run the check again. A second failure ends the run with the fails printed. Never
   patch the brief or a prompt yourself: an unjudged edit by the orchestrator is the hole this pipeline exists to
   close.
3. The `media-judge` agent action, emitted only when `decision` is not `none` (the rubric marks media `na`
   otherwise). You never compose its input: the tool writes `drafts/<run>/media/<cid>.judge.prompt.md` from the
   brief, the prompt files and the caption, and you hand the judge the five lines (that prompt file, the platform,
   lens `media`, output path `drafts/<run>/media/<cid>.media-judge.json`, `verify: false`) and nothing else. The
   judge reads the rubric itself.
4. Any merge action it emits (`aggregate.py merge`), so the media result reaches `merged.json` through the only
   writer of merged scores.

When `run_next --media` emits nothing more, `uv run tools/assemble_report.py <run> --json` rewrites `final/` with
the new brief, prompts and media result (its verdict labels stay hidden while the run's blind rating is pending;
that is its call, not yours).

Append one line per agent call to `drafts/<run>/run.log` (timestamp, agent, wall time).

## The judge's prompt file is the tool's
`run_next.py` writes `drafts/<run>/media/<cid>.judge.prompt.md`: rubric section 0 and 2.15 (media) pointers, the
platform, the `media_check` result, the brief verbatim inside `<media_brief>`, each file under `<cid>.prompts/`
inside `<tool_prompt>`, the caption inside `<untrusted_post>`, and the output path. You never write, reorder or
annotate it (`.claude/skills/post/references/judge_protocol.md` §9): a judge whose input the orchestrator composed
is no longer fresh, and its verbatim evidence could not be matched back to the files.

## Decision rules the director cites in `decision_reason`
- M1 delete test first. If the post loses nothing without the media, `none`. X defaults to `none`.
- M2 X: image only when the image is the joke or the proof; video only if native with the hook in the first
  second. No minimum duration.
- M3 LinkedIn: image is the default lift only in these genres: whiteboard or infographic explainer, fake-document
  or parody-UI punchline, meme, comic panels, a real photo of Deep (`user_photo_direction`), a real screenshot
  (`real_capture_direction`). Generic illustration, 3D robots, gradients: `none`.
- M4 text-only wins when the rhythm is the hook, when the visual would restate the caption, when on-image text
  would pass about 12 words, or when the concept needs a real face or a real logo (no tool renders either).
- M5 corpus prior: the lens author attaches media in more than 60% of train posts, so `none` needs a justification;
  under 20%, so `image` needs one.
- M6 real product output is never faked. Claude Code, Cursor, dashboards, bank screens: `real_capture_direction`
  with exact instructions. Parody UIs must be obviously fictional.
- M7 a carousel or PDF outranks everything on LinkedIn but is out of scope: `carousel_suggested: true` with a
  five-slide outline Deep can build by hand.
The rules with their reasons, and the brief field by field, are in `references/brief_schema.md`.

## Flags
`--tool gpt_image|nano_banana|veo|runway` forces the primary tool; `--genre <id>` forces the genre; `--none`
forces `decision: none` (the director still writes the brief, citing M1 plus the override, so `final/` records
why). An override that fights a rule is honored and named in `risk_notes`; the judge's `executable` sub-result
says whether it will work.

## Boundaries
- Never write or edit candidate text, a brief or a prompt. Never fake a real product's output, and never let a
  prompt through that does (M6 is a hard fail in `media_check.py`).
- Never read `evals/rubric/`, `corpus/heldout/`, `corpus/ratings.jsonl` or `evals/calibration.jsonl`; never hand
  the director a preview image of a heldout post.
- "media_check passed" only when its JSON says `ok: true`; a judge sub-result only as written in
  `media/<cid>.media-judge.json`; the PASSED or FAIL label on the variant only as `assemble_report.py` renders it
  (verdicts stay hidden while a blind rating is pending; that is its call, not yours).
- Never post, never scrape, never touch LinkedIn or X.

## Output
In the terminal, in this order:
1. `decision` and `decision_reason` from the brief, then `media_check`'s `ok`, `fails` and `warnings`.
2. Each judge sub-result with its quoted evidence, exactly as `media/<cid>.media-judge.json` has it (or "media:
   na, decision none").
3. The primary prompt in a fenced block headed "paste into <tool>", then the settings Deep sets in the app (from
   the brief: aspect ratio, pixels, resolution tier, duration, model pick named in `tool.reason`), the alt text to
   enter on upload, and the fallback prompt's path. For `real_capture_direction`: the capture steps as a numbered
   list instead of a prompt.
4. `Rate it: /rate <draft-id> <li|x> N media_great|media_miss` and `Log it: /posted <draft-id> <li|x> <url>`,
   then the file paths.

Reference files, read on demand: `references/brief_schema.md` (the brief field by field, the delete test, M1-M7
with reasons), `references/platform_specs.md` (aspect ratios, sizes and alt-text caps with sources and
verified_on), `references/tools/{gpt_image,nano_banana,veo,runway}.md` (template, rules, rendered example per
tool), `references/tools/sora_archived.md` (discontinued; generic fallback only).
