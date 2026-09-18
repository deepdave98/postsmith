postsmith drafts LinkedIn and X posts in Deep's voice and scores them against a reference corpus. Deep pastes posts by hand; nothing here logs into, posts to or scrapes LinkedIn or X.

Layout: corpus/ (reference posts, cards, features), style/ (persona, learned profiles, moves, lexicon, exemplars, taxonomies), drafts/ (runs), memory/ (lessons, topics, performance, published), evals/ (rubric, golden, health, calibration), tools/ (deterministic scripts), docs/design/ (contracts.md, content-quality-bar.md).

Conventions:
- Run helpers as `uv run tools/<name>.py ...` from the project root. Every tool has --help and --json.
- docs/design/contracts.md is authoritative for every schema, path and CLI. Code that disagrees with it is the bug.
- corpus/heldout/, corpus/ratings.jsonl, evals/calibration.jsonl, evals/golden/, evals/disagreements.jsonl and memory/performance.jsonl are label stores: read them only when the skill you are running says to. Opening one early makes you a second, contaminated grader.
- Never edit text under corpus/. Never write or edit candidate post text as the orchestrator; writers do that.
- A post "passes" only if a scores/<id>.merged.json written by tools/aggregate.py says so.
