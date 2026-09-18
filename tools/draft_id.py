#!/usr/bin/env python3
"""draft_id.py: resolve a fuzzy draft reference to a final variant file.

    'agents li'                  -> the LinkedIn finalist of the most recent run matching 'agents'
    '2026-09-17_agents li'       -> that run, LinkedIn
    'r2-w2-li'                   -> the variant with that cid (latest run first)
    'drafts/<run>/final/li_1.md' -> itself

Reads drafts/*/final/*.md (front matter: platform, cid or scores_path) and drafts/*/final/lineage.json;
never a label store. Score = token overlap of the query against run name, topic and cid, then recency. A
full-score tie across runs with no date in the query, or a run with several variants and no platform in the
query, is ambiguous: {"ok": false, "candidates": [...]}.

CLI: uv run tools/draft_id.py "agents li" [--root R] [--json]
API: resolve(query, root=None) -> {"ok": true, "run", "cid", "path", "platform", "alternates": [...]}
     or {"ok": false, ...}
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

PLATFORM_WORDS = {
    "li": "linkedin", "linkedin": "linkedin", "linked": "linkedin", "in": "linkedin",
    "x": "x", "tw": "x", "twitter": "x", "tweet": "x",
}
SKIP_FINAL_FILES = {"report.md", "clipboard.md", "README.md"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CID_RE = re.compile(r"^r\d+-w\d+-(li|x|x1)$")
_STOP = {"the", "a", "an", "of", "and", "on", "for", "to", "post", "draft", "run"}


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def _run_date(run: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", run)
    return m.group(1) if m else "0000-00-00"


def _cid_from(meta: dict, path: Path, lineage_variants: dict) -> str | None:
    cid = meta.get("cid")
    if isinstance(cid, str) and cid:
        return cid
    sp = meta.get("scores_path")
    if isinstance(sp, str):
        m = re.search(r"([^/]+)\.merged\.json$", sp)
        if m:
            return m.group(1)
    for vcid, v in lineage_variants.items():
        if isinstance(v, dict) and str(v.get("final_path") or v.get("path") or "").endswith(path.name):
            return vcid
    return None


def _platform_from(meta: dict, cid: str | None, path: Path) -> str | None:
    p = meta.get("platform")
    if isinstance(p, str) and p:
        return PLATFORM_WORDS.get(p.lower(), p.lower())
    if cid and _CID_RE.match(cid):
        return "x" if cid.endswith(("-x", "-x1")) else "linkedin"
    stem = path.stem.lower()
    for w, plat in PLATFORM_WORDS.items():
        if stem == w or stem.startswith((w + "_", w + "-")):
            return plat
    return None


def _lineage_variants(lineage: dict) -> dict:
    v = lineage.get("variants") if isinstance(lineage, dict) else None
    if isinstance(v, dict):
        return v
    if isinstance(v, list):
        return {str(x.get("cid", i)): x for i, x in enumerate(v) if isinstance(x, dict)}
    return {}


def scan(root: Path | None = None) -> list[dict]:
    """All final variants across runs: [{run, cid, platform, path, date, topic, verdict, tier2_tested}]."""
    root = Path(root) if root else common.ROOT
    drafts = root / "drafts"
    entries: list[dict] = []
    if not drafts.exists():
        return entries
    for run_dir in sorted(drafts.iterdir()):
        final = run_dir / "final"
        if not run_dir.is_dir() or not final.is_dir():
            continue
        lineage = common.read_json(final / "lineage.json", default={}) or {}
        if not isinstance(lineage, dict):
            lineage = {}
        variants = _lineage_variants(lineage)
        topic = str(lineage.get("topic") or "")
        for p in sorted(final.glob("*.md")):
            if p.name in SKIP_FINAL_FILES:
                continue
            try:
                meta, _ = common.split_front_matter(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - a malformed final file must not break resolution
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            cid = _cid_from(meta, p, variants)
            entries.append({
                "run": run_dir.name,
                "cid": cid,
                "platform": _platform_from(meta, cid, p),
                "path": str(p.relative_to(root)),
                "date": _run_date(run_dir.name),
                "topic": topic,
                "verdict": meta.get("verdict"),
                "tier2_tested": bool(meta.get("tier2_tested", False)),
                "file": p.name,
            })
    return entries


def _score(entry: dict, q_tokens: list[str], q_date: str | None) -> float:
    if not q_tokens and not q_date:
        return 0.0
    hay_run = _tokens(entry["run"])
    hay_topic = _tokens(entry["topic"])
    hay_cid = _tokens(entry["cid"] or "")
    score = 0.0
    for t in q_tokens:
        if t in hay_run or t in hay_topic:
            score += 1.0
        elif any(h.startswith(t) or t.startswith(h) for h in hay_run + hay_topic if len(h) >= 3 and len(t) >= 3):
            score += 0.6
        elif t in hay_cid:
            score += 0.8
    if q_date:
        score += 2.0 if entry["date"] == q_date else -5.0
    if q_tokens:
        score /= len(q_tokens)
    return score


def resolve(query: str, root: Path | None = None, platform: str | None = None) -> dict:
    """Resolve a fuzzy reference. See module docstring for the result shape."""
    root = Path(root) if root else common.ROOT
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty draft reference"}
    entries = scan(root)
    if not entries:
        return {"ok": False, "error": "no finished drafts under drafts/*/final/", "candidates": []}

    # direct path
    qp = Path(q)
    for e in entries:
        if e["path"] == q or (qp.is_absolute() and str(qp.resolve()) == str((root / e["path"]).resolve())):
            return _ok(e, [x for x in entries if x["run"] == e["run"] and x is not e])

    raw_tokens = [t for t in re.split(r"\s+", q) if t]
    plat = platform.lower() if platform else None
    if plat in PLATFORM_WORDS:
        plat = PLATFORM_WORDS[plat]
    q_date: str | None = None
    words: list[str] = []
    cid_query: str | None = None
    for t in raw_tokens:
        low = t.lower()
        if low in PLATFORM_WORDS and plat is None:
            plat = PLATFORM_WORDS[low]
        elif _CID_RE.match(low):
            cid_query = low
        elif _DATE_RE.match(low):
            q_date = low
        else:
            m = re.match(r"^(\d{4}-\d{2}-\d{2})[_-](.+)$", low)
            if m:
                q_date = m.group(1)
                words.extend(_tokens(m.group(2)))
            else:
                words.extend(_tokens(low))
    q_tokens = [w for w in words if w not in _STOP]

    pool = entries
    if plat:
        pool = [e for e in pool if e["platform"] == plat]
        if not pool:
            return {"ok": False, "error": f"no final variants for platform {plat}", "candidates": []}
    if cid_query:
        pool = [e for e in pool if (e["cid"] or "").lower() == cid_query]
        if not pool:
            return {"ok": False, "error": f"no variant with cid {cid_query}", "candidates": []}

    exact_run = [e for e in pool if e["run"].lower() == q.lower() or e["run"].lower() == "_".join(raw_tokens).lower()]
    scored = []
    for e in pool:
        s = 10.0 if e in exact_run else _score(e, q_tokens, q_date)
        scored.append((s, e))
    if q_tokens or q_date or exact_run:
        scored = [(s, e) for s, e in scored if s > 0]
    if not scored:
        return {"ok": False, "error": f"nothing matches {q!r}", "candidates": []}
    scored.sort(key=lambda se: (se[0], se[1]["date"], se[1]["run"]), reverse=True)
    best_score = scored[0][0]
    top = [e for s, e in scored if abs(s - best_score) < 1e-9]
    top_runs = sorted({e["run"] for e in top}, reverse=True)
    if len(top_runs) > 1:
        # Equal scores across runs: a full match with no date in the query is genuinely ambiguous. Anything
        # weaker is a partial match, so the most recent run wins.
        if best_score >= 1.0 and not q_date:
            return {"ok": False, "error": "ambiguous draft reference", "candidates": [_cand(e) for e in top]}
        top = [e for e in top if e["run"] == top_runs[0]]
    run = top[0]["run"]
    run_entries = [e for e in entries if e["run"] == run]
    if plat is None and cid_query is None and len({e["platform"] for e in run_entries}) > 1:
        return {"ok": False, "error": "ambiguous: specify the platform (li|x)", "run": run,
                "candidates": [_cand(e) for e in run_entries]}
    chosen = min(top, key=lambda e: (not e["tier2_tested"], str(e["verdict"]) != "pass", e["file"]))
    alternates = [e for e in run_entries if e is not chosen and (plat is None or e["platform"] == plat)]
    return _ok(chosen, alternates)


def _cand(e: dict) -> dict:
    return {"run": e["run"], "cid": e["cid"], "platform": e["platform"], "path": e["path"]}


def _ok(e: dict, alternates: list[dict]) -> dict:
    return {"ok": True, "run": e["run"], "cid": e["cid"], "platform": e["platform"], "path": e["path"],
            "verdict": e["verdict"], "tier2_tested": e["tier2_tested"], "alternates": [_cand(a) for a in alternates]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Resolve a fuzzy draft reference ('agents li') to a final variant.")
    ap.add_argument("query", nargs="+", help="reference words, e.g. agents li")
    ap.add_argument("--platform", default=None, help="li|x (overrides a platform word in the query)")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    common.emit(resolve(" ".join(args.query), root=root, platform=args.platform))
    return 0


if __name__ == "__main__":
    sys.exit(main())
