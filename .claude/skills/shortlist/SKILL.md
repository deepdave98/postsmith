---
name: shortlist
description: Every morning, three stories from the last 24 hours in Deep's lane, each with its one-line joke and its image concept, written to memory/shortlist/<date>.md so he can pick one and send it to /draft. Use when Deep says "shortlist", "what's today", "tomorrow's three", "what should I post today", or /shortlist.
argument-hint: "[--hours 24] [area]"
disable-model-invocation: true
allowed-tools: Read Write WebSearch WebFetch Bash(uv run *)
effort: high
metadata:
  skill_version: "1.0"
---

# /shortlist

Request: $ARGUMENTS

## Why this exists
Deep asked for it on 2026-10-06 after two weeks in which no draft went live as written. The post that did go
up (Muse, 2026-10-05) was made the way posts that travel get made: a story hours old, a screenshot that
carries the joke, five words on top, and many fast rounds of punchlines with him picking. This skill is the
first step of that loop. It does not write posts. It finds three stories worth a joke, writes the joke in one
line, says what the image would be, and stops. He picks. `/draft` takes the pick.

## Read first
- `memory/published/*.md`: every live post. The three must share no subject, no opener shape and no
  argumentative beat with the last three. Yesterday's beat is the one most likely to repeat.
- `memory/shortlist/` from the last 7 days: a story offered and not picked comes back only with a new
  development.
- `memory/topics.md`: subjects already run.
- `style/persona.md`: Lane and audience define the search; `do_not_target` and Opinions refused remove
  stories he will not touch; politics is out unless the story is the industry's own behaviour.
- `memory/lessons.md` when it exists: PREFER and AVOID.

## Finding the three
WebSearch from the main thread, `extended` mode, several queries across the lane (AI labs and their
products, agents misbehaving, dev tools, GTM and sales software, startups and funding, the big platforms),
restricted to the window (default 24 hours, `--hours` widens it). Prefer primary sources and reputable
reporting over aggregators; every story carries a URL and a date inside the window, and when the date is
unclear, WebFetch the page rather than guess. Never search or fetch LinkedIn or X to see what is trending;
that is scraping, and the topics come from events, not from other people's posts about them.

## The bar for a story
A story makes the three when all of these hold:
- **It has an artifact or can wear one.** A screenshot that exists, a product's own copy, a form, a dialog, a
  chat. Or it supports an obviously fictional parody of one (a chat with the agent, a notice, a listing). The
  image carries the joke; the caption is five words. A story with no artifact needs a text ladder, which is the
  weaker format for him, and is listed only when it is clearly the funniest thing that happened.
- **The joke is on an institution, a format or a system.** Never a customer, an investor, a job seeker, a
  junior engineer or a named private person (`do_not_target`). A company or a product is fair.
- **A non-technical reader gets it in one read.** His audience is mostly non-technical. Jargon only where
  there is no plain word.
- **It is checkable.** The premise is a real event with a source; only the execution is absurd.
- **It is not yesterday.** Different subject, different beat, different closer than the last three live posts.

## Per story, write exactly this
- **Source**: URL, date, outlet.
- **What happened**: two plain sentences, the facts a reader needs and nothing else.
- **The joke**: one line, the punch in the last words, nothing after it. Mechanisms that work for him: comply
  with the thing literally one rung past where the reader stopped; relabel the complaint as the request; let
  the institution speak in its own vocabulary; the format's last slot filled with the conclusion it entails.
  No explaining, no "imagine if", no question to the reader.
- **The image**: what the artifact is and where it comes from (a real capture he can take, a public
  screenshot, or an obviously fictional parody and of what). One sentence. Never a render, never a mock-up;
  `/draft` writes the generator prompt and he makes the picture.
- **Format**: `image + caption` or `text ladder`.
- **Why it moves**: the one thing the reader recognises from their own life. One sentence.

Three stories, best first, where best means the joke is sharpest and the artifact is strongest, not the
source is biggest. Then a `skipped` list: each candidate that was considered and why it lost (repeats
yesterday, no artifact, punches down, political, not in lane, not funny).

## Output
Write `memory/shortlist/<YYYY-MM-DD>.md` with a header (window, generated at), the three blocks, and the
skipped list. Print the three blocks in the terminal, numbered, nothing else, then one line:
`pick one: /draft #1 | #2 | #3`.

## Boundaries
Never draft the post here; the joke line and the image sentence are the limit. Never invent a source, a date
or a quote. Never render, crop or mock up an image. Never read `corpus/heldout/`, ratings or `evals/`. Never
post, schedule or open LinkedIn or X.
