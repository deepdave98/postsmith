# Card spec (postsmith.card/1)

A card is the mechanism-level record of one reference post: what it argues, how the hook works, what each beat
does, what each turn set up and broke, which devices carry it, what the media adds, and why it works. Writers never
read cards; profile-builders read cards and turn them into habits, moves and the bar. So a card that paraphrases the
post is worthless (nothing downstream may reuse wording) and a card that names the mechanism precisely is the whole
value of the corpus.

Contents: 1 bar · 2 where cards live · 3 line numbers · 4 front matter field by field · 5 the expectation ledger ·
6 taxonomies · 7 heldout rules · 8 the review file · 9 lint.

## 1. The annotator bar
- A stranger with the card and without the post can explain why the post works and what it does, and cannot
  reconstruct its sentences.
- One precise device beats three vague ones. Name a device only when you can point at the line and say what
  expectation it set up and how it broke it. "Witty tone", "engaging", "punchy" are not devices.
- If it is not funny, say so: `humor_attempted: false`, no humor devices, no expectation-ledger entry dressed up
  as a joke. Most good LinkedIn posts are earnest; an invented joke becomes a fake move in the catalogue.
- Media is looked at, not inferred. Open the preview or contact sheet; describe what is literally there; read the
  text on it. `provided_description` is the row author's hint, not evidence.
- Cite line numbers for everything: beats, ledger entries, devices, hook. A claim you cannot cite does not go on
  the card.
- The thesis is what the post argues, as the author meant it. Sarcasm, irony and deadpan are read as intended; a
  joke is not recorded as a claim and a claim is not recorded as a joke. The verifier rejects literal readings.
- Heldout posts: no quoted field longer than 6 words and never 6+ consecutive words of the post anywhere on the
  card (section 7).

## 2. Where cards live, and how the post reaches the annotator
- Train and self posts: `corpus/cards/<post_id>.md`. Heldout posts: `corpus/heldout/cards/<post_id>.md`.
- Verifier reviews: `corpus/cards/_reviews/<post_id>.md` and `corpus/heldout/cards/_reviews/<post_id>.md`.
- The post itself lives at `corpus/posts/`, `corpus/self/` or `corpus/heldout/` as `<post_id>.md`, and neither the
  annotator nor the verifier ever opens it. `uv run tools/card_prompts.py build [--post id | --all-uncarded]
  --kind annotate|verify --json` writes one self-contained prompt file per post under
  `drafts/learn_<date>/prompts/`: `<post_id>.annotate.md` (the post text inside `<untrusted_post>` tags, the post
  id, platform, author, split and engagement, the `profile_version` to record, the media entries with their preview
  and contact-sheet paths, the spec pointer and the card output path) and `<post_id>.verify.md` (the same post text,
  the card text inline in its own tagged block, the round, and the review output path). The agents receive the
  prompt file path and the output path, nothing else.
- Media previews: `corpus/media/<post_id>/` (previews) and `corpus/frames/<post_id>/` (`contact.jpg` and numbered
  frames), plus a transcript path when one exists. These, the learn prompt files, `style/taxonomies/` and this
  references directory are the only paths on the annotator's and verifier's allow list; `corpus/posts/`,
  `corpus/heldout/`, `corpus/self/`, `corpus/cards/`, `corpus/features/`, ratings, evals, memory and every run's
  round directories are denied to both.
- The orchestrating skill never opens a learn prompt file either (heldout text is inline there); when `/ingest` or
  `/learn` finishes, the prompt files are archived under `drafts/learn_<date>/archive/`, and
  `quote_leak_check.py` ignores `drafts/learn_*`.

## 3. Line numbers
Post line 1 is the first line inside the `<untrusted_post>` tags of the prompt file (the closing tag is not a
line); this is the same sequence as the first line after the closing `---` of the post file's front matter, which is
what `card_lint.py` counts. Blank lines count. When the prompt file prints line numbers beside the post, cite them
as printed. A citation is a single line `"7"` or an inclusive range `"5-9"`; use separate entries for separate
ranges. `card_lint.py` rejects any citation outside `1..last line`.

## 4. Front matter, field by field
```yaml
---
schema: postsmith.card/1
post_id: acosta_017
annotated_by: post-annotator
verified: false                 # the review file is the record; the annotator never writes true
profile_version_at_annotation: 3   # as the prompt file gives it (style/profile.json when the prompt was built; 0 if none)
thesis: "Most 'AI strategies' are a slide, not a decision, and the tell is that nobody stopped doing anything."
subtext: "The author has sat in these rooms and is allowed to be bored by them."
archetype: contrarian_take      # style/taxonomies/structures.md
angle: obvious_unsaid           # style/taxonomies/angles.md
emotion: FINALLY                # LOL | OHHH | WOW | WTF | AWW | YAY | NSFW | FINALLY | none
hook: {text: "We killed our AI strategy last week.", types: [deadpan_announcement, specificity], above_fold_chars: 38, standalone: true}
rehook: "Nobody noticed."       # the line after the hook that closes the exit; null if none
beats:
  - {lines: "1", beat: hook}
  - {lines: "3", beat: rehook}
  - {lines: "5-9", beat: setup}
  - {lines: "11", beat: turn}
  - {lines: "13-17", beat: proof}
  - {lines: "19", beat: punchline}
expectation_ledger:
  - {lines: "11", sets_up: "a lesson about strategy", breaks_with: "a $14 line item nobody could explain"}
  - {lines: "19", sets_up: "a recommendation", breaks_with: "an admission the author also has no strategy"}
rhythm: "1/1/5/1/5/1"
devices:
  - {device: deadpan, lines: "1", note: "big news said flatly"}
  - {device: specificity, lines: "13", note: "$14 line item, not 'a small cost'"}
  - {device: anti_climax, lines: "19", note: "buildup to advice, payoff is a shrug"}
moves: []                       # always [] from the annotator; the profile-builder fills it from style/moves.md
stance: {earnest_ironic: 0.7, humble_brash: 0.5, warm_cold: 0.4, dense_airy: 0.7, abstract_specific: 0.9}
pov: first_singular             # first_singular | second | first_plural | third | mixed
tense: past                     # past | present | mixed
address: none                   # direct_you | none
ending: punchline               # punchline | callback | question | cta | ps | lesson | summary | trail_off | none
media_analysis:                 # omit the whole block when the post has no media
  literal: "Phone photo of a whiteboard; three boxes labelled Strategy, AI, Q3 with arrows; a coffee cup in the corner."
  on_media_text: ["Strategy", "AI", "Q3", "???"]
  genre: photo_of_artifact      # style/taxonomies/media_roles.md
  role: punchline               # proof | punchline | contrast | context | aesthetic | none
  caption_dependency: media_dependent   # standalone | media_dependent
  style_notes: "Handheld, slightly tilted, fluorescent light; reads as taken 30 seconds ago."
  reproducibility: needs_real_photo     # promptable | needs_real_photo | needs_real_screenshot | needs_real_face
  what_it_adds: "The ??? box is the joke; the caption never mentions it."
  video: null                   # {duration_s, shots: [{t, what}], has_speech, transcript_source, burned_captions, pacing}
why_it_works: >
  Announcement shape used for a non-event, so the reader expects a lesson and gets a receipt. The proof beat is one
  number, which makes the sarcasm earned rather than performed. Ending on the author's own failure removes the
  superiority reading.
what_would_break_it: "Add 'Agree?' at the end, or explain that the $14 was symbolic."
distinctive_phrases: ["killed our AI strategy", "nobody noticed", "a $14 line item"]
generic_risk: low               # low | medium | high: would the median creator write this?
humor_attempted: true
engagement: {likes: 1200, comments: 340, reposts: 40}   # copied from the prompt file's engagement line; null values allowed
---
Optional prose notes: a loose taxonomy fit, what you could not decide, what the verifier should look at.
```

Guidance per field:
- `thesis`: one sentence a reader could restate; the argument, not the topic. "Posts about AI strategy" is a topic;
  "AI strategies are slides, not decisions" is a thesis. For a pure joke, the thesis is the opinion under the joke.
- `subtext`: what the reader concludes about the author (credible, bored, generous, dangerous). One sentence.
- `archetype`: the spine of the post from `structures.md`; when two fit, the one the ending confirms.
- `angle`: the closest of the 22 angles in `angles.md`; if the fit is loose, say so in the notes rather than
  inventing an id (lint checks ids, not fit).
- `emotion`: the one emotion the post is for; `none` only when you honestly cannot name it.
- `hook.text`: the exact first line(s) above the fold, verbatim for train and self posts; `types`: at most two ids
  from `hooks.md`; `above_fold_chars`: characters before the first blank line, capped by the platform fold (LinkedIn
  ~140 mobile, ~210 desktop; X: the whole post); `standalone`: would line 1 work as its own post.
- `rehook`: the line right after the hook that makes leaving impossible; null when the post has none.
- `beats`: the spine, in order, covering every non-blank line at least once. Labels: hook, rehook, setup,
  complication, turn, proof, escalation, list, aside, punchline, callback, lesson, cta, close, ps.
- `rhythm`: sentences per paragraph block, in order, `/`-separated (Ship 30 notation); a one-word line is 1.
- `devices`: ids from `devices.md`, each with lines and a one-clause note of the expectation and the break.
  Humor devices only when `humor_attempted` is true.
- `moves`: `[]` from the annotator, always; `style/moves.md` is not on its allow list, and the profile-builder
  grows the catalogue, records `seen_in` there and fills this field from the cards it verified.
- `stance`: 0..1 sliders, left pole at 0: earnest→ironic, humble→brash, warm→cold, dense→airy, abstract→specific.
- `ending`: what the last beat is; `lesson` and `summary` are the LinkedIn-default endings and worth recording as
  such, because the corpus mostly avoids them.
- `media_analysis.literal`: what is in the image or frames, plainly, so a media brief can later imitate the role
  and never the picture. `on_media_text`: every legible text element, verbatim (heldout: ≤ 6 words each).
  `genre` from `media_roles.md`; `role` is what the media adds to the post, `none` when it adds nothing;
  `caption_dependency`: does the text make sense without the media; `reproducibility`: could a prompt make this,
  or does it need a real photo, screenshot or face. `video`: duration, up to 5 shots with timestamps, speech yes/no,
  `transcript_source` (`column` | `burned_captions` | `none`), burned captions yes/no, pacing in one clause.
  When `kind: unavailable`, write `literal: "media unavailable; not analysed"` and `what_it_adds: unknown`.
- `why_it_works`: 2 to 4 sentences of mechanism, no adjectives of praise; each sentence should be traceable to a
  beat, a ledger entry or a device.
- `what_would_break_it`: the smallest change that turns it into a median post.
- `distinctive_phrases`: 2 to 6 phrases that are this author's (coinages, framings, the joke's words); they go to
  the do-not-reuse lexicon. Heldout: ≤ 6 words each.
- `generic_risk`: the Tequila test; high means the median creator could have written it.
- `engagement`: copied from the prompt file's engagement line (the post's front matter values), never edited.

## 5. The expectation ledger
Every turn, reveal and punchline is a broken expectation. The ledger records, per cited line, what the reader was
set up to expect (`sets_up`) and what the post delivers instead (`breaks_with`). This is the reusable part of a
joke or a turn: a writer can build a new post on the same expectation shape ("reader expects a lesson, gets a
receipt") with different content, and the overlap check will find nothing to object to. Record one entry per
break, at the line where the break lands, in plain language; do not paraphrase the punchline itself for heldout
posts. Earnest posts have ledgers too (a stated consensus broken by a number); a post with no break has an empty
ledger and probably `generic_risk: high`.

## 6. Taxonomies
Ids must come from these files, which are the source of truth (`card_lint.py` checks them):
- `style/taxonomies/angles.md`: the 22 angles in five families (Reveal, Receipt, Reframe, Ridicule, Rule).
- `style/taxonomies/hooks.md`: hook types (relatable_enemy, contradiction, direct_mirror, numbered_promise,
  specificity, story_in_medias_res, deadpan_announcement, one_liner, screenshot_dunk, fake_precision, ...).
- `style/taxonomies/structures.md`: archetypes (hook_reframe_proof_punch, story_arc, contrarian_take, listicle,
  screenshot_commentary, one_liner, escalation_ladder, confession, announcement_with_twist, ...).
- `style/taxonomies/devices.md`: humor devices (misdirection, rule_of_three_escalation, callback, reversal,
  understatement, deadpan, specificity, self_deprecation, fake_precision, anti_climax, incongruous_register, ...)
  and voice devices (fragment, one_word_line, anaphora, parenthetical_aside, false_start, ...).
- `style/taxonomies/media_roles.md`: media genres and roles.
Read the files rather than trusting this list; they may have grown.

## 7. Heldout rules
Heldout cards live inside the denied path, but they are still parsed by tooling and could be read by a future
agent. So: `hook.text`, `rehook`, every `distinctive_phrases[]` item and every `on_media_text[]` item is at most 6
words (write the first words, no ellipsis), and no field anywhere (thesis, ledger, notes, `why_it_works`) contains
6 or more consecutive words of the post. Describe; do not quote. `card_lint.py` enforces the field cap;
`quote_leak_check.py` enforces the rest wherever heldout text could surface (it ignores `drafts/learn_*`, where the
prompt files carry the heldout text on purpose; those files are archived when the skill finishes and are on no
writer's or judge's allow list). The prompt file says which split the post is in.

## 8. The review file (postsmith.review/1)
Written only by `card-verifier`, at `corpus/cards/_reviews/<post_id>.md` (heldout: under `corpus/heldout/cards/`),
from the `<post_id>.verify.md` prompt file, which inlines the post and the card.
```yaml
---
schema: postsmith.review/1
post_id: acosta_017
verified: false                 # true only with zero objections
round: 1                        # 1 first check, 2 after the annotator's one rewrite
checked_at: 2026-09-17T10:31:00Z
objections:
  - {field: "devices[1]", lines: "13", objection: "line 13 has no number; the $14 is on line 15", severity: citation}
  - {field: "thesis", lines: "1-19", objection: "reads the sarcasm literally: the post mocks strategy decks, it does not recommend killing strategy", severity: meaning}
---
Optional notes for the annotator.
```
Severity: `citation` (a line does not support the claim), `id` (wrong taxonomy id), `meaning` (thesis, subtext or
ledger misread), `leak` (heldout quote rule). Objections say what is wrong and where; they never supply replacement
text, so the annotator must re-derive it from the post. The annotator cannot open a review; a rebuilt annotate
prompt inlines the objections. The review is the record of verification; the card's `verified` field is a mirror
of it, set by the orchestrating skill, never by the annotator or the verifier.

## 9. Lint
`uv run tools/card_lint.py --post <id> --json` checks YAML validity, that every `lines` citation exists in the post,
that device, archetype, hook-type and angle ids exist in the taxonomy files, and the heldout 6-word cap on quoted
fields. It does not check meaning; the verifier does. The orchestrating skill runs it on every new or changed card
before a verifier sees it (annotators have no shell) and hands the `problems` rows back to a fresh annotator with
the same prompt file; the annotator checks citations and ids itself before replying so lint has nothing to report.
