---
name: story
description: Mandatory for any post, or any paragraph of a post, that tells something that happened (the user's own, their team's, or one they watched). Every story walks the art-and-science frame the user set on 2026-10-18 - the moment told from inside it in specific detail with one felt beat, then a bridge sentence and a short numbered list of the lessons that resulted - and the ten-line audit at the end. Use when the user says "story post", "tell the story of", "what happened when", "the week we", pastes an anecdote, or when any other skill finds itself narrating a moment. No story post exists without this.
argument-hint: "<the moment, pasted notes, or the draft that contains a story> [funny|insightful]"
allowed-tools: Read Write WebFetch WebSearch Bash(uv run *)
metadata:
  skill_version: "1.0"
---

# /story

Request: $ARGUMENTS

## Standing order
The user, 2026-10-18: "we have to compulsorily, mandatorily, statutorily refer to this when writing storytelling
posts. no questions, asked. any storytelling has to go through this. we will never have a story without this."
This file is not advice. A post that narrates something that happened is not finished until it has walked the
audit in step 4, whichever skill started it: /draft, /post, a writer, a rewrite, a reply. An anecdote inside a
funny or insightful post is a story at its own scale and walks the same audit. Nothing here asks them a question;
what they have not supplied becomes a bracketed slot.

## The framework, as the user pasted it on 2026-10-18
Source text, author not named by them. It teaches the shape. Its words, images and example never appear in a post.

> Founders today absolutely suck at storytelling. I am sorry, but it is true.
>
> For one reason. They forget that it is about art and science. You have to have both.
>
> Art: The art is the story. Tell excessive detail, bring the listener into the story with you. Make them feel.
> "As I entered the Sequoia partnership meeting, the palms of my hands became clammy with sweat; my heart was
> racing. Breathe, I told myself". Make the audience feel. Take them with you.
>
> Then you combine it with the science.
>
> Science: This is a structured framework of lessons that result from that experience. Audiences resonate with
> numbered lists of takeaways. Package your wisdom.
>
> "And it was at that moment, walking into the Sequoia partnership, I learned three things about how to deal
> with high-stress environments".
>
> Try this today and I guarantee you, it will change the nature of your career and business.

Two halves, both required. Art is the story told in excessive detail from inside the moment, so the reader feels
what the teller felt. Science is the structured set of lessons that resulted, packaged as a numbered list and
introduced by a bridge that names the moment and the count in words. A story with no lessons is a diary. Lessons
with no story are the label-definition listicle the voice judge scored 3 on `not_ai` on 2026-09-21 and the user
called slop.

## What counts as a story
A post, or a paragraph, that narrates something that happened in sequence: to the user, to their team, or to someone they
watched. "Last Tuesday", "the week we", "when we started building", "I was sitting in", a pasted anecdote, a
customer call retold, a conference scene. Not a story: a chat parody, a ladder of public facts, a comparison of
two price lists, an opinion with no event in it. When unsure, it is a story.

## Read first
- `style/persona.md`: `cannot_claim`, `do_not_target`, the story bank (the S entries). A story about the user's
  company, its products, a customer or a named person uses only what is there or what the user said in chat.
- `style/self.md` and `memory/published/*.md`: their register. The scene is written in their spoken sentences.
- `style/lexicon.yaml` `do_not_reuse`, including the `storytelling-framework` block.
- The private company context pack named under `## Company context` in `style/persona.md`, when one exists (it
  lives outside this repo and is never copied in here), whenever the story touches the product, a customer or
  the space.

## Step 1: pin the moment
One moment. Write it in one line: who, where, when, what was on the screen or the table, what was said.
Everything the scene needs that the user has not supplied becomes a bracketed slot: `[day]`, `[what the screen
showed]`, `[what X said, in their words]`, `[what you did right then]`. Never fill a slot about the user's company, its products, a
customer or a named person yourself. Invention stays where /draft allows it: an anecdote nobody would bank on,
deadpan, pinned on no real third party.

## Step 2: art, the scene
Write the moment from inside it, not as a summary of it.
- Specific detail: the day, the room, the screen, the words someone actually said. "Excessive" means every
  detail is particular, not that the scene is long. Three sentences usually do it; the YC-founder concision they
  asked for on 2026-10-17 still holds.
- One beat of feeling, shown as what they did or thought right then (sat down, said nothing for a bit, asked for
  it to run again), in plain words. Never named with an adjective pile, never the framework's own images.
- Their register throughout: contractions, a hedge where they would hedge, people credited by name, no mirrored
  lines, no fragment runs, no "not X, it's Y", no colon reveal, no em dashes.

## Step 3: science, the lessons
- A bridge sentence that names the moment and the count in words: "that week I learned three things about X".
- A numbered list, two or three items. The framework says three; two when the third would be padding.
- Each item is a plain sentence with a verb that a reader could act on tomorrow, in their words. Not
  "Label: definition". Not a mirrored pair. Not an aphorism. Not a recap of the scene.
- The last item is their opinion and the post ends on it. No closer, no question, no promise to the reader.

## Step 4: the audit, every line a yes before hand-over
1. Can the reader say where they are, what they can see and what day it is?
2. Does the scene carry words somebody actually said, in their words, or a slot for them?
3. Is the feeling shown as an action or a thought, not named with an adjective?
4. Is every detail about the user's company, its products, a customer or a named person from the user, from `style/persona.md` or a slot?
5. Is there a bridge sentence naming the moment and the count in words?
6. Are the lessons numbered, two or three, each a full sentence with a verb?
7. Could a reader apply each lesson without having been there?
8. Is the last line the last lesson, with nothing after it?
9. Are both halves present, in this order: scene, then lessons?
10. Is the framework's own material absent: no Sequoia, no clammy palms, no racing heart, no "Breathe, I told
    myself", no "I guarantee you"?
A no is an edit, not a note. Make the edit and walk the list again.

## Step 5: checks, deterministic only
`uv run tools/tier0.py <candidate> --as-golden --lens platform:linkedin --json` (or `--lens author:james-hawkins`
inside a funny frame), with golden-style front matter on the file. Fix a hard fail. P17 fails hard only on
"Term: description" and anaphora lists, so plain numbered takeaways pass it; a soft tricolon flag on a lesson is
read and usually left. `uv run tools/quote_leak_check.py <candidate> --json`. No judges unless they type
"judge it".

## Hand over
The post, paste-ready, every slot in brackets. Under it: the slots they fill, one line each; what the audit
changed; what is their call. No score table, no verdict word.

## The lenses
The insightful lens rules 6 to 9 and rule 19's no-takeaway clause were learned from two analysis posts and do
not apply to a story. Inside a funny post the scene stays flat and the lesson may be the deadpan punch, but the
lesson is there and it is numbered when there is more than one.

## Boundaries
Never open `corpus/heldout/`, `corpus/ratings.jsonl`, `evals/calibration.jsonl` or a `*.key.json`. Never render
an image. Never post. Never say "passed". Never ask them to confirm that this skill applies: it applies.
