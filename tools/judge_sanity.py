#!/usr/bin/env python3
"""Judge-sanity check over a hook log (contracts §14, §17; the health_run "judge-sanity" item).

The judge agents run with ``POSTSMITH_HOOK_LOG=<file>``, so ``guard_paths.py`` / ``guard_writes.py`` append
one JSON line per decision. This tool groups those lines per judge call and asserts what fresh-context
judging needs:

* every judge call read exactly one prompt file (``drafts/**/prompts/*.md``, ``tier2/lineup_*.prompt.md``,
  ``tier2/pairwise_*.prompt.md``, ``tier2/claims_*.prompt.md`` or ``media/*.judge.prompt.md``);
* every other read was the rubric (``evals/rubric/**``);
* zero blocked decisions: a blocked attempt is contamination, the judge reaching outside its handed paths.

A judge call is one ``agent_id``, falling back to ``session_id``; rows with neither are grouped as
``"unattributed"``. ``--agents`` keeps only the listed ``agent_type`` values (default: every row whose
``agent_type`` starts with ``judge-`` or is ``media-judge``, and every row that carries no ``agent_type``).

CLI: ``judge_sanity.py <hook.log> [--agents judge-reader,judge-voice] [--json]`` ->
``{"ok", "green", "calls": n, "problems": [{"call", "problem", "rows": [...]}], "per_call": {...}}``.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

PROMPT_RE = re.compile(
    r"(?:^|/)(?:prompts/[^/]+\.md|tier2/(?:lineup|pairwise|claims)_[^/]+\.prompt\.md|media/[^/]+\.judge\.prompt\.md)$")
RUBRIC_RE = re.compile(r"(?:^|/)evals/rubric/")
READ_TOOLS = {"Read", "Grep", "Glob", "Bash"}


def _is_judge_row(row: dict, keep: set[str] | None) -> bool:
    at = row.get("agent_type")
    if keep is not None:
        return at in keep
    if at is None:
        return True
    return str(at).startswith("judge-") or str(at) == "media-judge"


def check(rows: list[dict], keep: set[str] | None = None) -> dict:
    """Group hook-log rows per judge call and evaluate the three assertions. Pure."""
    calls: dict[str, list[dict]] = {}
    for r in rows:
        if not isinstance(r, dict) or not _is_judge_row(r, keep):
            continue
        key = str(r.get("agent_id") or r.get("session_id") or "unattributed")
        calls.setdefault(key, []).append(r)
    problems: list[dict] = []
    per_call: dict[str, dict] = {}
    for call, crs in calls.items():
        blocked = [r for r in crs if r.get("decision") == "block"]
        reads = [r for r in crs if r.get("tool") in READ_TOOLS and r.get("decision") == "allow"]
        prompt_reads = [r for r in reads if any(PROMPT_RE.search(str(t)) for t in r.get("targets") or [])]
        other = [r for r in reads if r not in prompt_reads
                 and not all(RUBRIC_RE.search(str(t)) for t in (r.get("targets") or ["?"]))]
        per_call[call] = {"rows": len(crs), "blocked": len(blocked), "prompt_reads": len(prompt_reads),
                          "other_reads": len(other), "agent_type": next((r.get("agent_type") for r in crs if r.get("agent_type")), None)}
        if blocked:
            problems.append({"call": call, "problem": "blocked read attempt (contamination)",
                             "rows": [{"tool": r.get("tool"), "targets": r.get("targets"), "reason": r.get("reason")} for r in blocked]})
        if len(prompt_reads) != 1:
            problems.append({"call": call, "problem": f"expected exactly one prompt read, saw {len(prompt_reads)}",
                             "rows": [{"tool": r.get("tool"), "targets": r.get("targets")} for r in prompt_reads]})
        if other:
            problems.append({"call": call, "problem": "read outside the prompt file and the rubric",
                             "rows": [{"tool": r.get("tool"), "targets": r.get("targets")} for r in other]})
    return {"ok": True, "green": not problems and bool(calls), "calls": len(calls), "problems": problems, "per_call": per_call}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assert judge isolation from a POSTSMITH_HOOK_LOG file: one prompt read per "
                                             "judge call, only the rubric otherwise, zero blocked attempts.")
    ap.add_argument("log", help="hook log (JSON lines written by guard_paths.py / guard_writes.py)")
    ap.add_argument("--agents", default=None, help="comma-separated agent_type values to keep (default: judge-* and media-judge)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    p = Path(args.log)
    if not p.is_absolute():
        p = (Path.cwd() / p) if (Path.cwd() / p).exists() else common.ROOT / p
    if not p.exists():
        common.error(f"hook log not found: {args.log}")
        return 0
    rows = common.read_jsonl(p)
    keep = {a.strip() for a in args.agents.split(",") if a.strip()} if args.agents else None
    out: dict[str, Any] = check(rows, keep)
    out["log"] = common.rel(p)
    common.emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
