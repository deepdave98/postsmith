# Anchors

One directory per scored dimension, each holding `weak.md` (scored 2) and `strong.md` (scored 5). A judge prompt for a
dimension carries both anchors verbatim, as data, so the judge interpolates between real posts rather than adjectives.

`claims` (a classification, no score) and `media` (sub-results) have no anchors; their negatives live in `evals/golden/`.

## The rule
- **Strong anchors come from train-split corpus posts (`corpus/posts/`) only.** Never heldout (label store), never `corpus/self`,
  never synthetic text. A strong anchor shows the judge what the corpus bar looks like; an invented one would teach an invented bar.
- **v1 ships with weak anchors only.** Every `weak.md` is a synthetic slop post from the S-set in docs/design/research-ai-tells.md
  §7.1, scored 2, with a two-line rationale. Every `strong.md` is a front-matter stub:
  ```yaml
  ---
  status: pending
  note: filled by /ingest from a train-split corpus post rated high
  ---
  ```
  `/ingest` fills it from a train-split post rated high for that dimension (user rating first, engagement normalized per author
  second). Filling a pending stub is the one write allowed inside a promoted rubric version. Until it is filled the judge prompt
  carries the weak anchor only and says "no strong anchor yet".
- **No author name, no origin label.** Anchor files never say who wrote the post, whether it is human, synthetic or generated,
  or where it came from. That information lives here and in the CHANGELOG, never in a file a judge reads.
- Replacing a filled anchor creates a new rubric version. `/rate` nominates a replacement when a user rating disagrees with the
  judge median by 2 or more at n ≥ 30.

## File format
```markdown
---
status: filled            # filled | pending
dimension: clarity
score: 2                  # 2 for weak.md, 5 for strong.md
platform: linkedin        # linkedin | x
---
<the complete post text, verbatim, line breaks preserved>

Rationale:
<line 1: what the post does on this dimension>
<line 2: why that puts it at this score>
```
The post text starts on the first line after the front matter and ends at the blank line before `Rationale:`.
