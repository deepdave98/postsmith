# Fixture corpus (`tools/tests/fixtures/corpus/`)

A miniature reference corpus in the exact `postsmith.post/1` (contracts section 1) and `postsmith.card/1` (section 2)
formats, for tests of `overlap_check`, `stylometry`, `profile_stats`, `lineup`, `pairwise`, `card_lint` and the golden
health run. Twelve posts, three fictional authors, both platforms; nothing here is a real person's writing.

| author (slug, handle) | posts | platforms |
|---|---|---|
| Mira Okonkwo (`mira-okonkwo`, `@miraokonkwo`), data-enrichment founder | okonkwo_001-004 | 3 LinkedIn, 1 X |
| Tomas Vieira (`tomas-vieira`, `@tvieira_dev`), backend engineer | vieira_001-004 | 1 LinkedIn, 3 X |
| Dana Kessler (`dana-kessler`, `@danakessler`), RevOps operator | kessler_001-004 | 2 LinkedIn, 2 X |

Layout (mirrors `corpus/`):

```
posts/<post_id>.md            8 train posts
heldout/<post_id>.md          4 heldout posts (okonkwo_003, kessler_003 on LinkedIn; vieira_003, kessler_004 on X)
cards/<post_id>.md            cards for the train posts
heldout/cards/<post_id>.md    cards for the heldout posts (no quoted field longer than 6 words)
manifest.jsonl                one row per post: {content_sha256, author_slug, post_id, split, source, ingested_at, crosspost_of, variant_of}
```

Facts tests can rely on:

- `content_sha256` is `common.content_sha(text)` (sha256 of `common.normalize_text`); `text_stats` uses `common.words`
  and `common.lines`. Splits are hand-assigned (split is sticky), not derived from the sha modulo rule, so that both
  platforms have two heldout posts.
- `vieira_004` is the only post with media: `kind: unavailable` with a `provided_description`, and its card carries a
  `media_analysis` block. Every other post has `media: []` and no `media_analysis` key.
- Every card cites line numbers that exist in its post (1-indexed over the body including blank lines); `hook.text` is
  the verbatim first line for train posts and its first six words for heldout posts.
- Card `moves` use these fixture slugs: `receipt_as_proof`, `deadpan_number_ending`, `self_undercut_close`,
  `escalating_triple_breaks`, `flat_literal_description`, `two_numbers_same_unit`. A `moves_lint` that checks slugs
  against `style/moves.md` should be pointed at a stub containing these six.
- `distinctive_phrases` in the train cards are what the lexicon's `do_not_reuse` list is built from. The golden
  negatives `corpus_copy.md`, `synonym_swap.md` and `clean_paraphrase.md` are derived from `okonkwo_001`:
  the copy is byte-identical to that post's body, the swap keeps at least one shared 8-gram, and the paraphrase
  shares zero word trigrams with every post here.

Using it as a project root: `common.project_root()` needs `pyproject.toml` and `config/postsmith.yaml`, so copy this
folder to `<tmp>/corpus/`, copy `config/postsmith.yaml` next to a stub `pyproject.toml`, and set `POSTSMITH_ROOT=<tmp>`
(or pass the folder to a tool that accepts a corpus root). Do not edit the post texts: the golden set depends on them.
