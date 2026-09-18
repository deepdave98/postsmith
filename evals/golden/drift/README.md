# Drift set (`evals/golden/drift/`)

Frozen candidates, re-judged on every rubric, lexicon or threshold change, so per-dimension score movement can be
measured between versions.

## State

Empty at project start, on purpose. The set is filled by the first 12 *generated* candidates that Deep rates with
`/rate` (any score). Once a candidate is frozen here it is never edited, replaced or removed; a new rubric version
that wants a different drift set creates a new folder (`drift_v2/`) and updates `expected.json#drift`.

## File convention (proposed; `health_run.py` owns the final shape)

- `<yyyy-mm-dd>_<cid>.md`: front matter `{platform, cid, run, rated, user_score, frozen_at, rubric_version_at_freeze,
  note}` followed by the candidate text exactly as judged (the `.txt` content, never the candidate front matter).
- `<yyyy-mm-dd>_<cid>.baseline.json`: the merged Tier 1 medians at freeze time,
  `{"rubric_version": "v1", "dimensions": {"clarity": 4, "substance": 5, ...}, "tier0_flags": [...]}`.
- `baselines.json`: one row per file, appended by `health_run.py` after each green run so deltas are computed against
  the last promoted version, not the first.

## How health uses it

1. Re-judge every frozen candidate with the current rubric (fresh-context judges, same protocol as `/post`).
2. Print, per dimension, the median delta against the previous version's baseline.
3. Any median moving by >= 1 point across the set must be explained in `evals/rubric/vN/CHANGELOG.md` before
   `--promote` moves the `current` symlink.

Nothing in this folder is a label store for writers or judges: hooks deny it to both.
