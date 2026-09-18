# Fixtures for the card tools (`card_prompts.py`, `card_lint.py`, `moves_lint.py`)

`tools/tests/test_cards.py` builds a scratch project root per test: `tools/tests/fixtures/corpus/` copied to
`<tmp>/corpus/`, the real `config/postsmith.yaml` and `style/taxonomies/`, a stub `pyproject.toml`, plus these files:

| file | copied to | what it exercises |
|---|---|---|
| `moves.md` | `style/moves.md` | a clean catalogue: 4 canonical moves (`receipt_as_proof`, `deadpan_number_ending`, `flat_literal_description`, `escalating_triple_breaks`), both list syntaxes for `seen_in` (bracket and YAML list), bulleted and bare `key: value` lines, an inline alias (`two_numbers_same_unit` -> `receipt_as_proof`) and a `merged_into` stub (`self_undercut_close` -> `deadpan_number_ending`). Together the six slugs the fixture corpus cards use all resolve. |
| `moves_bad.md` | `style/moves.md` (bad-catalogue tests) | duplicate id, non-slug id, an alias equal to a real id, one alias claimed by two moves, an unknown platform, one citation only, malformed / reversed / unknown-post citations, missing required keys, an alias cycle, a stub pointing at no move. |
| `topics.md` | `memory/topics.md` | a moves scoreboard whose keys resolve only through the aliases (`self_undercut_close`, `two_numbers_same_unit`); tests append an unresolvable key to see the problem. |

Nothing here is a real person's writing; post ids are the fixture corpus ids (see `../corpus/README.md`).
