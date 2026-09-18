#!/usr/bin/env python3
"""status.py: project dashboard and nags. Read-only, and it never crashes: every input file is optional.

    uv run tools/status.py --brief   compact summary; the `!` injection at the top of each skill uses it
    uv run tools/status.py --json    the full dict
    uv run tools/status.py --root R  another project root (tests)

Reports: corpus counts per split / platform / author, profile_version, rubric version and health state (read
off the latest evals/health/reports/<date>_<rubric-hash>_<profile>.md name), lexicon_version, pending blind
ratings (runs with final/ but no calibration rows), unrated drafts older than N days, posted items without
metrics after N days, small-corpus mode, self sample count against target, unresolved disagreements.
API: collect(root=None) -> dict ; brief(doc) -> str
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from run_next import load_config_at, rubric_dir_at  # noqa: E402

SPLIT_DIRS = {"train": "corpus/posts", "heldout": "corpus/heldout", "self": "corpus/self"}
RUBRIC_HASH_FILES = ("rubric.md", "patterns.yaml", "thresholds.yaml")


def _safe(fn, default: Any = None) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001 - status must never crash
        return default


def _iso_date(s: Any) -> _dt.date | None:
    if not s:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(s))
    if not m:
        return None
    try:
        return _dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def rubric_sha(root: Path) -> str | None:
    """sha256 over rubric.md, patterns.yaml and thresholds.yaml in the current rubric dir, plus
    style/lexicon.yaml. None without a rubric dir holding at least one of those three."""
    rd = rubric_dir_at(root)
    if rd is None:
        return None
    h = hashlib.sha256()
    found = False
    for name in RUBRIC_HASH_FILES:
        p = rd / name
        if p.exists():
            found = True
            h.update(name.encode("utf-8"))
            h.update(p.read_bytes())
    lex = root / "style" / "lexicon.yaml"
    if lex.exists():
        h.update(b"lexicon.yaml")
        h.update(lex.read_bytes())
    return h.hexdigest() if found else None


def corpus_counts(root: Path) -> dict:
    per_split: dict[str, int] = {}
    per_platform: Counter = Counter()
    per_author: Counter = Counter()
    per_split_platform: dict[str, Counter] = {}
    for split, rel in SPLIT_DIRS.items():
        d = root / rel
        n = 0
        c = Counter()
        if d.exists():
            for p in sorted(d.glob("*.md")):
                n += 1
                meta = _safe(lambda p=p: common.split_front_matter(p.read_text(encoding="utf-8"))[0], {}) or {}
                if not isinstance(meta, dict):
                    meta = {}
                plat = str(meta.get("platform") or "unknown").lower()
                c[plat] += 1
                per_platform[plat] += 1
                author = meta.get("author")
                slug = author.get("slug") if isinstance(author, dict) else author
                per_author[str(slug or ("self" if split == "self" else "unknown"))] += 1
        per_split[split] = n
        per_split_platform[split] = c
    return {
        "total": sum(per_split.values()),
        "per_split": per_split,
        "per_platform": dict(per_platform),
        "per_split_platform": {k: dict(v) for k, v in per_split_platform.items()},
        "per_author": dict(sorted(per_author.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def health_state(root: Path, profile_version: int | None) -> dict:
    reports = root / "evals" / "health" / "reports"
    files = sorted(reports.glob("*.md")) if reports.exists() else []
    sha = rubric_sha(root)
    if not files:
        return {"state": "none", "latest_report": None, "rubric_sha": sha, "reason": "no health report yet"}
    latest = files[-1]
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_([0-9a-fA-F]+)_p?(\d+)", latest.name)
    rep_hash = m.group(2).lower() if m else None
    rep_profile = int(m.group(3)) if m else None
    text = _safe(lambda: latest.read_text(encoding="utf-8")[:4000], "") or ""
    verdict = None
    vm = re.search(r"(?im)^\s*(?:health|state|result|status)\s*[:=]\s*\**\s*(green|red|stale|amber)", text)
    if vm:
        verdict = vm.group(1).lower()
    reasons: list[str] = []
    if sha is None:
        reasons.append("no rubric files to hash")
    elif rep_hash and not sha.startswith(rep_hash):
        reasons.append(f"rubric/lexicon changed since report (sha {sha[:8]} vs {rep_hash[:8]})")
    if profile_version is not None and rep_profile is not None and rep_profile != profile_version:
        reasons.append(f"profile p{profile_version} newer than report p{rep_profile}")
    if verdict == "red":
        state = "red"
    elif reasons:
        state = "stale"
    else:
        state = verdict or "green"
    return {"state": state, "latest_report": str(latest.relative_to(root)), "report_date": m.group(1) if m else None,
            "rubric_sha": sha, "report_rubric_hash": rep_hash, "report_profile": rep_profile,
            "reason": "; ".join(reasons) or None}


def _run_date(run: str) -> _dt.date | None:
    return _iso_date(run)


def drafts_status(root: Path, cfg: dict, today: _dt.date) -> dict:
    drafts = root / "drafts"
    unrated_days = int((cfg.get("status_nags") or {}).get("unrated_days", 2))
    cal_rows = common.read_jsonl(root / "evals" / "calibration.jsonl")
    rated_refs = " ".join(str(r.get("post_ref") or "") for r in cal_rows)
    finished: list[dict] = []
    in_progress: list[str] = []
    if drafts.exists():
        for rd in sorted(drafts.iterdir()):
            if not rd.is_dir() or rd.name == "trending" or rd.name.startswith("."):
                continue
            final = rd / "final"
            if final.is_dir() and (final / "report.md").exists():
                rated = rd.name in rated_refs
                date = _run_date(rd.name)
                age = (today - date).days if date else None
                finished.append({"run": rd.name, "rated": rated, "age_days": age})
            elif (rd / "state.json").exists() or any(rd.glob("round*")):
                in_progress.append(rd.name)
    pending_blind = [f["run"] for f in finished if not f["rated"]]
    unrated_old = [f["run"] for f in finished if not f["rated"] and f["age_days"] is not None and f["age_days"] > unrated_days]
    return {"finished": len(finished), "in_progress": in_progress, "pending_blind_ratings": pending_blind,
            "unrated_older_than_days": {"days": unrated_days, "runs": unrated_old}, "calibration_rows": len(cal_rows)}


def posted_status(root: Path, cfg: dict, today: _dt.date) -> dict:
    days = int((cfg.get("status_nags") or {}).get("metrics_missing_days", 3))
    rows = common.read_jsonl(root / "memory" / "performance.jsonl")
    missing: list[str] = []
    for r in rows:
        snaps = r.get("snapshots") or []
        has_metrics = any(isinstance(s, dict) and any(v is not None for k, v in s.items() if k != "at") for s in snaps)
        date = _iso_date(r.get("posted_at") or r.get("ts"))
        if not has_metrics and date and (today - date).days > days:
            missing.append(f"{r.get('draft_id') or r.get('cid') or '?'} ({r.get('platform', '?')})")
    return {"posted": len(rows), "without_metrics_after_days": {"days": days, "items": missing}}


def collect(root: Path | None = None, today: _dt.date | None = None) -> dict:
    """Full status dict. Every section degrades to zeros/None when its files are missing."""
    root = Path(root) if root else common.ROOT
    today = today or _dt.date.today()
    cfg = _safe(lambda: load_config_at(root), {}) or {}
    corpus_cfg = cfg.get("corpus") or {}
    nags_cfg = cfg.get("status_nags") or {}

    corpus = _safe(lambda: corpus_counts(root), {"total": 0, "per_split": {}, "per_platform": {}, "per_author": {},
                                                  "per_split_platform": {}}) or {}
    profile = _safe(lambda: common.read_json(root / "style" / "profile.json", default=None), None)
    profile_version = profile.get("profile_version") if isinstance(profile, dict) else None
    lexicon = _safe(lambda: common.load_yaml(root / "style" / "lexicon.yaml") if (root / "style" / "lexicon.yaml").exists() else None, None)
    lexicon_version = lexicon.get("lexicon_version") if isinstance(lexicon, dict) else None
    lexicon_updated = _iso_date(lexicon.get("updated")) if isinstance(lexicon, dict) else None
    lexicon_stale_months = int(nags_cfg.get("lexicon_refresh_months", 6))
    lexicon_stale = bool(lexicon_updated and (today - lexicon_updated).days > lexicon_stale_months * 30)
    rd = _safe(lambda: rubric_dir_at(root), None)
    rubric_version = rd.name if rd else None
    health = _safe(lambda: health_state(root, profile_version), {"state": "unknown", "latest_report": None}) or {}

    # one small-corpus rule (train split only), shared with tier0.py via common.small_corpus_mode
    small_corpus = common.small_corpus_mode(cfg, root)
    self_n = int((corpus.get("per_split") or {}).get("self", 0))
    self_target = int(nags_cfg.get("self_target_samples", 8))
    self_min = int(corpus_cfg.get("self_min_samples", 5))

    drafts = _safe(lambda: drafts_status(root, cfg, today), {"finished": 0, "in_progress": [], "pending_blind_ratings": [],
                                                              "unrated_older_than_days": {"days": 2, "runs": []},
                                                              "calibration_rows": 0}) or {}
    posted = _safe(lambda: posted_status(root, cfg, today), {"posted": 0, "without_metrics_after_days": {"days": 3, "items": []}}) or {}
    dis_rows = _safe(lambda: common.read_jsonl(root / "evals" / "disagreements.jsonl"), []) or []
    unresolved = [r for r in dis_rows if not r.get("resolved")]
    ratings = _safe(lambda: common.read_jsonl(root / "corpus" / "ratings.jsonl"), []) or []
    every_n = int((cfg.get("calibration") or {}).get("every_n_ratings", 20))
    total_ratings = len(ratings) + int(drafts.get("calibration_rows", 0))
    calibration_due = total_ratings > 0 and every_n > 0 and total_ratings % every_n == 0

    nags: list[str] = []
    ur = drafts.get("unrated_older_than_days", {})
    if ur.get("runs"):
        nags.append(f"{len(ur['runs'])} draft(s) unrated >{ur['days']}d: " + ", ".join(ur["runs"][:3]))
    pm = posted.get("without_metrics_after_days", {})
    if pm.get("items"):
        nags.append(f"{len(pm['items'])} posted without metrics >{pm['days']}d: " + ", ".join(pm["items"][:3]))
    if drafts.get("pending_blind_ratings"):
        nags.append(f"{len(drafts['pending_blind_ratings'])} run(s) awaiting a blind rating")
    if unresolved:
        nags.append(f"{len(unresolved)} unresolved disagreement(s)")
    if health.get("state") in ("stale", "red", "none"):
        nags.append(f"health {health.get('state')}" + (f" ({health.get('reason')})" if health.get("reason") else ""))
    if self_n < self_min:
        nags.append(f"corpus/self has {self_n} sample(s) (<{self_min}): register_match_self is N/A")
    elif self_n < self_target:
        nags.append(f"corpus/self has {self_n}/{self_target} samples")
    if small_corpus:
        nags.append("small-corpus mode (widened envelopes, lineup may be advisory)")
    if lexicon_stale:
        nags.append(f"lexicon tiers older than {lexicon_stale_months} months")
    if calibration_due:
        nags.append(f"calibration due ({total_ratings} ratings)")
    if not (root / "style" / "persona.md").exists():
        nags.append("style/persona.md missing (/persona first)")

    return {
        "ok": True,
        "root": str(root),
        "today": today.isoformat(),
        "corpus": corpus,
        "profile_version": profile_version,
        "rubric_version": rubric_version,
        "rubric_sha": health.get("rubric_sha"),
        "health": health,
        "lexicon_version": lexicon_version,
        "lexicon_updated": lexicon_updated.isoformat() if lexicon_updated else None,
        "small_corpus_mode": small_corpus,
        "self_samples": {"count": self_n, "min": self_min, "target": self_target},
        "persona_present": (root / "style" / "persona.md").exists(),
        "drafts": drafts,
        "posted": posted,
        "disagreements_unresolved": len(unresolved),
        "ratings_total": total_ratings,
        "calibration_due": calibration_due,
        "nags": nags,
    }


def brief(doc: dict) -> str:
    c = doc.get("corpus") or {}
    ps = c.get("per_split") or {}
    pp = c.get("per_platform") or {}
    authors = ", ".join(f"{a} {n}" for a, n in list((c.get("per_author") or {}).items())[:6]) or "none"
    h = doc.get("health") or {}
    profile = f"p{doc['profile_version']}" if doc.get("profile_version") is not None else "none"
    lexicon = doc.get("lexicon_version") if doc.get("lexicon_version") is not None else "none"
    ss = doc.get("self_samples") or {}
    dr = doc.get("drafts") or {}
    lines = [
        (f"postsmith · rubric {doc.get('rubric_version') or 'none'} (health: {h.get('state', 'unknown')}) · profile {profile}"
         f" · lexicon v{lexicon} · small-corpus: {'on' if doc.get('small_corpus_mode') else 'off'}"),
        (f"corpus: {c.get('total', 0)} posts (train {ps.get('train', 0)} / heldout {ps.get('heldout', 0)} / self {ps.get('self', 0)})"
         f" · linkedin {pp.get('linkedin', 0)} · x {pp.get('x', 0)} · authors: {authors}"),
        f"self samples: {ss.get('count', 0)}/{ss.get('target', 0)} (min {ss.get('min', 0)} for register_match_self)",
        (f"drafts: {dr.get('finished', 0)} finished · {len(dr.get('in_progress', []))} in progress"
         f" · {(doc.get('posted') or {}).get('posted', 0)} posted · {doc.get('disagreements_unresolved', 0)} disagreements open"),
    ]
    nags = doc.get("nags") or []
    lines.append("nags: " + (" · ".join(nags) if nags else "none"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="postsmith status dashboard and nags (read-only).")
    ap.add_argument("--brief", action="store_true", help="compact multi-line summary")
    ap.add_argument("--json", action="store_true", help="full JSON dict (default when --brief is absent)")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    try:
        doc = collect(root)
    except Exception as e:  # noqa: BLE001 - never crash
        doc = {"ok": False, "error": f"status failed: {e}", "nags": [], "corpus": {}, "drafts": {}, "posted": {}}
    if args.brief and not args.json:
        print(brief(doc))
    else:
        common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
