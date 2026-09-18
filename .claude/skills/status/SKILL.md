---
name: status
description: Shows the postsmith dashboard (versions, corpus and self-sample counts, health state, pending ratings) and the nags that need Deep's action, each with the command that clears it. Use when Deep asks "what's pending", "status", "anything to rate", "is health green", or /status.
allowed-tools: Bash(uv run *)
metadata:
  skill_version: "1.0"
---

# /status

!`uv run tools/status.py --brief || true`

Present the brief above as it is (counts, versions, health state, pending ratings), then the nags as one line each ending in the command that clears it. Change nothing; this skill is read-only. If the injection failed or printed nothing, run `uv run tools/status.py --brief` yourself and say what failed.

Nags and why each exists (thresholds in `config/postsmith.yaml` `status_nags` and `calibration`):
- Unrated run older than 2 days: `/rate blind <run>`. A verdict Deep never rated teaches the system nothing; a rating taken later is taken after he has seen the report, so it is worth less.
- Posted variant without metrics after 3 days: `/posted <draft-id> <li|x> 12k views 40 comments`. Performance is only comparable across posts when snapshots exist at similar ages.
- Calibration due (20 unprocessed ratings): it runs on the next `/rate`; `uv run tools/calibrate.py` runs it now. Until kappa >= 0.4 on n >= 30 every report says "eval advisory", and it cannot get there without ratings of failed candidates.
- Health stale for the current rubric, lexicon or profile hash: `/eval health`. Judgments under an unchecked rubric are unverified; `/post` says "health stale" in its header but does not block, so this nag is the only pressure.
- Self samples below 8 (or words below 1,500): `/persona --samples <path>`. Below 5 samples `register_match_self` is N/A and the voice gate is off; below 8 it is low confidence.
- Lexicon tiers older than 6 months: refresh `style/lexicon.yaml` from a fresh survey of model tells (the last one is `docs/design/research-ai-tells.md`, dated), bump `lexicon_version`, then `/eval health`. Tells drift as models change; a stale lexicon lets the newest tics through and keeps flagging ones nobody uses.
- Unresolved judge disagreements: the count only; they are the rubric revision queue for the next `/eval health`.

Keep it to the screen: brief, nags, done. No advice beyond the clearing command.
