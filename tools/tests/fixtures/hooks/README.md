# hooks fixtures

Used by `tools/tests/test_hooks.py` to exercise `.claude/hooks/guard_paths.py` and `guard_writes.py`.

- `payloads/*.json`: PreToolUse stdin documents as Claude Code sends them (`tool_name`, `tool_input`, plus the
  `session_id`/`cwd` envelope). `{PROJECT}` is replaced with the temporary project directory by the tests.
- `agent_args/*.txt`: the hook argument strings exactly as the agent frontmatter files carry them
  (`.claude/agents/judge-reader.md`, `judge-lineup.md`, `judge-pairwise.md`, `judge-persona.md`, `post-writer.md`,
  `angle-scout.md`, `profile-builder.md`, `post-annotator.md`, `card-verifier.md`), one per file; `test_agent_args_match_agent_files`
  fails when an agent file and its fixture drift apart, so the policy tests always exercise the real policies.
