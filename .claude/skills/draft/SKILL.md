---
name: draft
description: Turns one pick (a number from today's shortlist, a pasted story, or the user's own line) into the material for a post in their voice: facts opened at source, ten candidate lines for the one place the post turns, then the dialogue or ladder built around the line they pick, an image concept and generator prompt (never a render), captions under six words, the first comment and two reply seeds. Deterministic checks only, no judges. Use when the user says "draft #2", "do this one", "punchlines for X", "funny post about X", "insightful post on X", "hawkins style", or pastes a story or a line.
argument-hint: "<#n from today's shortlist | topic | pasted line> [funny|insightful]"
allowed-tools: Read Write WebFetch WebSearch Bash(uv run *)
metadata:
  skill_version: "2.0"
---

# /draft

Request: $ARGUMENTS

## What changed on 2026-10-06 and why
Version 1 wrote one polished post per topic, ran four judges on it, and handed it over. In two weeks none of
those posts went live as written. The one that did go up was the user's own rewrite, and the Muse post was made
by fifteen fast rounds of punchlines, their pick, a screenshot carrying the joke, and five words on top. The
judges passed every draft they rejected. So the product is no longer a finished post. It is raw material in their
voice, delivered in two halves with their pick in between: first the facts and ten candidate lines for the one
place the post turns; then, after they pick or write their own, everything built around that line.

## Read first, every time
- `memory/published/*.md`: all of it. The new post shares no subject, no opener shape, no beat and no closer
  with the last three. They said "i dont want shit to sound repetitive at all".
- `corpus/self/*` and `style/self.md`: their register. This outranks every reference author. Where the self
  samples are thin, their live posts in `memory/published/` are the better anchor.
- `style/persona.md`: `do_not_target`, `cannot_claim`, Opinions refused, Never. No personal angle unless they
  asked for one.
- `style/lexicon.yaml` `do_not_reuse`: other people's coinages. Never in a line of their.
- `style/authors/james-hawkins.md` sections 7 and 10 for funny; `style/modes/insightful.md` for insightful.
  These are mechanism catalogs now, not the voice.
- `memory/shortlist/<today>.md` when the request is a number.
- The private company context pack, when `style/persona.md` names one under `## Company context` (it lives
  outside this repo and is never copied in here), whenever the post touches the user's company, its products,
  a competitor or the space: every receipt, every number's verdict, the "never say" list and leadership's
  rules for that half of the feed are in it.
- `memory/lessons.md` when it exists.

## Half one: facts and ten lines
1. **Facts.** Open every number, date, name and quote at its source with WebFetch. Write
   `drafts/<date>_<slug>/claims.md`: claim, status, source. A figure that cannot be confirmed is not used.
   A false figure survived twelve judge passes on 2026-09-20 and was caught only by looking.
2. **The turn.** Decide where the post turns: the last bubble of a chat, the caption under a screenshot, the
   kicker of a ladder. There is one such place. Everything else is setup.
3. **Ten lines for it.** Numbered, each twelve words or fewer, each a different mechanism: literal compliance
   one rung past; the complaint relabelled as the request; the institution's own vocabulary; the scale made
   exact; the format's last slot filled with what it entails; the artifact's own words transcribed; the flat
   confession; the chirpy non-answer; the smaller-than-the-setup payoff; the "you" that makes a claim about
   the reader. Lowercase unless the line is the machine speaking in its own case. No emoji unless it is the
   machine's. Beside each line at most five words naming the mechanism, nothing more. Do not rank them in
   prose; put the one you would ship first.
4. **Stop.** Print the facts in three lines, the ten numbered lines, and nothing else. Wait for their pick.

## Half two: build around their line
When they pick a number or pastes their own line:
- **Their line is the line.** Build the setup to land it. Never swap their words for better ones; sharpen only
  what they ask, and show the change as a one-line diff. If their line has a logic gap (a word that does not
  carry the misreading, as "marketplace" did not carry "stock market" on 2026-10-05), name the gap in one
  sentence and give two words that close it.
- **Shape.** For a chat parody: three or four bubbles, the user typed lowercase, the machine in its own
  case, the punch the last bubble, nothing after. For a ladder: three blocks, events in order, flat register,
  the punch the last words. Read the last sentence of every block in a row; at most one may land.
- **Image.** The default format is image plus caption; a text ladder only when there is no artifact. Write
  the concept in one sentence and the generator prompt (ChatGPT Images unless they name another tool). When they
  gives a reference screenshot, the prompt opens with "use the attached screenshot as the exact UI reference"
  and lists only what changes. Never render, mock up, crop or build the image; they make it. A fake capture of a
  real product is their call, flagged once in one line, never refused twice.
- **Captions.** Three, each six words or fewer, lowercase, no period, no emoji. A caption is a reaction to the
  image, never a description of it, never a correction of it.
- **First comment and two reply seeds.** In their lane (GTM, startups, dev tools). The comment is a joke that
  extends the post into the lane, not a pitch and not an explanation. The reply seeds are two one-liners for
  the first two kinds of reply they will get (the pedant, the fan).
- **Checks, deterministic only.** `uv run tools/tier0.py <candidate> --as-golden --lens author:james-hawkins
  --json` on the caption or ladder text, with `media:` set in the front matter so a caption is scored as a
  caption. Fix a hard fail; read O1, O2, O5 for overlap; ignore E1 on a caption. `uv run
  tools/quote_leak_check.py <candidate> --json`. No judge batch. Judges run only if they type "judge it".
- **Hand over.** The dialogue or ladder, the image prompt, the three captions, the first comment, the reply
  seeds, then a short list of what the checks changed and what is their call. No score table, no verdict word.

## Insightful mode
Same two halves. The turn is the opinion line or the one number that changes what the reader does. Ten
candidate lines for it, their pick, then the plain-sentence post built around it in the register of
the user's own live posts under `memory/published/`: their spoken lines, one idea per paragraph, about
five figures total, no mirrored lines, no fragment runs, no "not X, it's Y", no colon reveal.

## Story posts
Mandatory, by the user's standing order of 2026-10-18: any post or paragraph that narrates something that happened
walks `.claude/skills/story/SKILL.md` (the `/story` skill) before anything else here continues. No story post
exists without it. It carries the framework they pasted, the two halves and the ten-line audit. In short: art, the
moment told from inside it in specific detail with one felt beat, nothing invented about the user's company, its products or a named
person; science, a bridge sentence naming the moment and the count in words, then two or three numbered lessons,
each a plain sentence with a verb, the last one their opinion, nothing after it. In half one the turn is the
sentence where the thing happened; the scene and the lessons are built in half two around their pick. This shape is
exempt from the insightful lens rules 6 to 9 and rule 19's no-takeaway clause.

## Log it
When they say it went up: write the live caption or text exactly as posted to
`drafts/<run>/final_live_caption.txt`, keep the posted image beside it under `drafts/<run>/media/`, and run
`uv run tools/posted_record.py <run> <cid> --text-file <file> --posted-at <date> --json` the same minute.
Forty-eight hours later: `/posted <run> <li|x> <views> views <likes> likes <comments> comments`. After ten
logged posts, read `memory/performance.jsonl` by format (image plus caption, chat parody, text ladder) and
say which one moves for them.

## Boundaries
Never open `corpus/heldout/`, `corpus/ratings.jsonl`, `evals/calibration.jsonl` or a `*.key.json`. Never
render a UI, an image or a screenshot. Never post. Never say "passed"; nothing here passes, it ships when they
says so.
