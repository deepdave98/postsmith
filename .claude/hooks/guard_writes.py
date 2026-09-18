#!/usr/bin/env python3
"""PreToolUse hook: allow Write/Edit/MultiEdit/NotebookEdit only under the given globs.

Usage in an agent's frontmatter (see docs/design/contracts.md section 15):

    python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/guard_writes.py --allow 'drafts/*/round*/scores/*' 'evals/health/reports/*'

Reads the PreToolUse JSON on stdin, takes the write target (`file_path`, or `notebook_path` for
NotebookEdit), resolves it against CLAUDE_PROJECT_DIR (fallback: cwd, `..` and symlinks folded) and exits 2
with a one-line reason on stderr unless it matches an --allow glob. --deny wins over --allow. Other tools
pass through (exit 0). With no --allow globs every write is blocked: an agent writes only where it is
explicitly allowed to.

Glob semantics, project-dir resolution and the POSTSMITH_HOOK_LOG JSON-lines log come from guard_paths.py in
the same directory. Stdlib only; runs under the system python3, outside uv.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import guard_paths as gp
except ImportError as exc:  # pragma: no cover - only when the sibling file is missing
    print(f"guard_writes: cannot import guard_paths.py ({exc}); blocking the write", file=sys.stderr)
    sys.exit(2)

HOOK_NAME = "guard_writes"
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="guard_writes.py",
        description="PreToolUse hook: exit 2 when a Write/Edit/MultiEdit/NotebookEdit target is outside the "
                    "--allow globs (or matches a --deny glob). Reads the hook JSON on stdin.")
    ap.add_argument("--allow", nargs="*", default=[], metavar="GLOB",
                    help="globs a write target must match (project-relative; '**' supported)")
    ap.add_argument("--deny", nargs="*", default=[], metavar="GLOB",
                    help="globs that block a write even when allowed (deny wins)")
    ap.add_argument("--project-dir", default=None, metavar="DIR",
                    help="project root (default: $CLAUDE_PROJECT_DIR, then the current directory)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = gp.read_payload()
    if payload is None:
        print(f"{HOOK_NAME}: no hook JSON on stdin; nothing to check", file=sys.stderr)
        return 0
    tool, tool_input = gp.tool_and_input(payload)
    if tool not in WRITE_TOOLS:
        return 0
    project = gp.Project(args.project_dir)
    cwd, _outside = gp.payload_cwd(payload, project)
    targets = gp.collect_targets(tool, tool_input, project, cwd)
    allow, deny = list(args.allow), list(args.deny)
    if targets and not allow:
        decision, reason = "block", f"{tool} {targets[0].display}: no --allow globs configured for this agent"
    else:
        decision, reason = gp.decide(tool, targets, allow, deny, project.ignore_case)
    gp.log_decision(project, HOOK_NAME, tool, targets, decision, reason, payload)
    if decision == "block":
        print(f"{HOOK_NAME}: blocked {reason}", file=sys.stderr)
        return gp.BLOCK_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main())
