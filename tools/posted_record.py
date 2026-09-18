#!/usr/bin/env python3
"""posted_record.py: close the loop after a variant is pasted by hand (contracts §13, §17).

    posted_record.py <run> <cid> [--url U] [--text-file F] [--metrics "12k views 40 comments"] [--after 24h|7d]
                     [--posted-at YYYY-MM-DD] [--root R] [--json]

Writes memory/published/<date>_<slug>_<platform>.md (front matter draft_id, cid, platform, posted_at, url,
sha256, edited; body is the live text: the pasted --text-file, else the draft text the judges saw), diffs
draft against live into `edit_ops` (difflib line opcodes tagged cut_line, added_line, changed_line,
changed_first_line, changed_ending, removed_em_dash, shortened, lengthened), stores those tags on the run's
evals/calibration.jsonl row for this cid (appending a kind "published" row when none exists), upserts the
memory/performance.jsonl row for (draft_id, cid), appends a metrics snapshot parsed by metrics_parse.parse
when --metrics is given, and calls topics.add(run, outcome="posted"). Re-running is safe: --metrics alone
appends a snapshot, --url alone fills the url in. The draft text is never modified.

API: record(run, cid, url=None, text_file=None, metrics=None, after=None, posted_at=None, root=None) -> dict
     edit_ops(draft, live) -> [{"op", "line"|"detail"}]  (pure; op tags listed above)
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import metrics_parse  # noqa: E402
import rate_record  # noqa: E402
import topics  # noqa: E402

PUBLISHED_DIR = Path("memory") / "published"
PERFORMANCE_PATH = Path("memory") / "performance.jsonl"
SNAPSHOT_KEYS = ("views", "likes", "comments", "reposts", "saves", "follows")
EDIT_OPS = ("cut_line", "added_line", "changed_line", "changed_first_line", "changed_ending", "removed_em_dash",
            "shortened", "lengthened")
LENGTH_CHANGE_RATIO = 0.10
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- diff

def _lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]


def _short(s: str, n: int = 80) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


PAIR_RATIO = 0.5


def _pair_lines(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    """Greedy best-ratio pairing of draft lines to live lines inside a replace block: [(ia, ib)], each side used once."""
    cands: list[tuple[float, int, int]] = []
    for i, la in enumerate(a):
        for j, lb in enumerate(b):
            r = difflib.SequenceMatcher(None, la, lb, autojunk=False).ratio()
            if r >= PAIR_RATIO:
                cands.append((r, i, j))
    cands.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_a: set[int] = set()
    used_b: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _r, i, j in cands:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((i, j))
    return sorted(pairs)


def edit_ops(draft: str, live: str) -> list[dict]:
    """Human-readable edit tags between the draft and the live text (pure function).

    Line ops come from difflib on non-blank lines (a replace pairs lines up; the first/last line of the draft get
    changed_first_line / changed_ending instead of changed_line). removed_em_dash fires when the live text has
    fewer em dashes; shortened / lengthened when the word count moved by >= LENGTH_CHANGE_RATIO.
    """
    a, b = _lines(draft), _lines(live)
    ops: list[dict] = []
    touched_a: set[int] = set()   # draft lines covered by a delete/replace opcode (an insert covers none)
    if a == b:
        pass
    else:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            touched_a.update(range(i1, i2))
            if tag == "delete":
                for i in range(i1, i2):
                    ops.append({"op": "cut_line", "line": _short(a[i]), "index": i})
            elif tag == "insert":
                for j in range(j1, j2):
                    ops.append({"op": "added_line", "line": _short(b[j]), "index": j})
            else:  # replace: pair each draft line with its closest live line; the rest are cut / added
                pairs = _pair_lines(a[i1:i2], b[j1:j2])
                matched_b = {pj for _pi, pj in pairs}
                paired = dict(pairs)
                # a rewritten opener or ending is still a changed first/last line, however different the words
                if i1 == 0 and j1 == 0 and 0 not in paired and 0 not in matched_b:
                    paired[0] = 0
                    matched_b.add(0)
                la, lb = i2 - i1 - 1, j2 - j1 - 1
                if i2 == len(a) and j2 == len(b) and la not in paired and lb not in matched_b and la >= 0 and lb >= 0:
                    paired[la] = lb
                    matched_b.add(lb)
                for i in range(i1, i2):
                    if (i - i1) in paired:
                        j = j1 + paired[i - i1]
                        op = "changed_first_line" if i == 0 else "changed_ending" if i == len(a) - 1 else "changed_line"
                        ops.append({"op": op, "line": _short(a[i]), "to": _short(b[j]), "index": i})
                    else:
                        ops.append({"op": "cut_line", "line": _short(a[i]), "index": i})
                for j in range(j1, j2):
                    if (j - j1) not in matched_b:
                        ops.append({"op": "added_line", "line": _short(b[j]), "index": j})
        # These fallbacks catch a boundary line the opcode walk could not pair with anything close enough. The
        # touched_a and handled guards keep them off a boundary the walk already handled and off one it never
        # touched: deleting the first line moves a[1] into b[0] and appending one moves b[-1] past a[-1], and
        # neither of those is a rewrite of that line.
        handled = {o["index"] for o in ops
                   if o["op"] in ("cut_line", "changed_line", "changed_first_line", "changed_ending")}
        last = len(a) - 1
        if a and b and a[-1] != b[-1] and last in touched_a and last not in handled:
            ops.append({"op": "changed_ending", "line": _short(a[-1]), "to": _short(b[-1]), "index": last})
        if a and b and a[0] != b[0] and 0 in touched_a and 0 not in handled:
            ops.append({"op": "changed_first_line", "line": _short(a[0]), "to": _short(b[0]), "index": 0})
    dash_a, dash_b = draft.count("—"), live.count("—")
    if dash_b < dash_a:
        ops.append({"op": "removed_em_dash", "detail": f"{dash_a} -> {dash_b}"})
    wa, wb = len(common.words(draft)), len(common.words(live))
    if wa and abs(wb - wa) / wa >= LENGTH_CHANGE_RATIO:
        ops.append({"op": "shortened" if wb < wa else "lengthened", "detail": f"{wa} -> {wb} words"})
    return ops


def _same_text(a: str, b: str) -> bool:
    norm = lambda t: "\n".join(ln.rstrip() for ln in t.replace("\r\n", "\n").strip("\n").split("\n"))  # noqa: E731
    return norm(a) == norm(b)


# --------------------------------------------------------------------------- stores

def _published_meta(p: Path) -> dict:
    """Front matter of a memory/published file; {} when the file is malformed (never fatal)."""
    try:
        meta, _ = common.split_front_matter(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return meta if isinstance(meta, dict) else {}


def _published_for(root: Path, run: str, cid: str) -> Path | None:
    d = root / PUBLISHED_DIR
    if not d.is_dir():
        return None
    for p in sorted(d.glob("*.md")):
        meta = _published_meta(p)
        if meta.get("draft_id") == run and meta.get("cid") == cid:
            return p
    return None


def _published_path(root: Path, run: str, cid: str, platform: str, posted_at: str) -> Path:
    existing = _published_for(root, run, cid)
    if existing is not None:
        return existing
    d = root / PUBLISHED_DIR
    base = f"{posted_at}_{topics.run_slug(run)}_{platform}"
    p = d / f"{base}.md"
    return p if not p.exists() else d / f"{base}_{cid}.md"


def _rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def update_calibration_edit_ops(root: Path, run: str, cid: str, platform: str | None, ops: list[str],
                                edited: bool) -> dict:
    """Set edit_ops on the newest generated calibration row for run/cid, else append a kind=published row."""
    path = root / rate_record.CALIBRATION_PATH
    rows = common.read_jsonl(path)
    post_ref = f"{run}/{cid}"
    idx = None
    for i, r in enumerate(rows):
        if r.get("post_ref") == post_ref and r.get("kind", "generated") in ("generated", "published"):
            idx = i
    if idx is not None:
        rows[idx]["edit_ops"] = ops
        rows[idx]["edited"] = edited
        _rewrite_jsonl(path, rows)
        return {"action": "updated", "row": rows[idx]}
    joined = rate_record.join_candidate(run, cid, root)
    row = {"ts": common.now_iso(), "post_ref": post_ref, "kind": "published", "platform": platform or joined["platform"],
           "user_score": None, "tags": [], "note": None, "blind": False, "judge_scores": joined["judge_scores"],
           "tier0_soft_flags": joined["tier0_soft_flags"], "lineup_pass": joined["lineup_pass"],
           "verdict": joined["verdict"], "rubric_version": joined["rubric_version"],
           "profile_version": joined["profile_version"], "moves": joined["moves"], "lens": joined["lens"],
           "edit_ops": ops, "edited": edited, "run": run, "cid": cid,
           "tier0_hard_fails": joined["tier0_hard_fails"], "paraphrase": joined["paraphrase"],
           "media_pass": joined["media_pass"]}
    common.append_jsonl(path, row)
    return {"action": "appended", "row": row}


def _snapshot(parsed: dict, after_hours: int | None) -> dict:
    snap: dict = {"at": common.now_iso(), "after_hours": after_hours}
    for k in SNAPSHOT_KEYS:
        snap[k] = parsed["metrics"].get(k)
    for k, v in parsed["metrics"].items():
        if k not in snap:
            snap[k] = v
    return snap


def upsert_performance(root: Path, run: str, cid: str, platform: str | None, url: str | None, published_path: str,
                       posted_at: str, snapshot: dict | None) -> dict:
    path = root / PERFORMANCE_PATH
    rows = common.read_jsonl(path)
    row = next((r for r in rows if r.get("draft_id") == run and r.get("cid") == cid), None)
    created = row is None
    if row is None:
        row = {"ts": common.now_iso(), "draft_id": run, "cid": cid, "platform": platform, "url": url,
               "published_path": published_path, "posted_at": posted_at, "snapshots": []}
        rows.append(row)
    else:
        if url:
            row["url"] = url
        row["published_path"] = published_path
        row.setdefault("posted_at", posted_at)
        row.setdefault("snapshots", [])
        row["platform"] = row.get("platform") or platform
    if snapshot is not None:
        row["snapshots"].append(snapshot)
    _rewrite_jsonl(path, rows)
    return {"row": row, "created": created, "path": common.rel(path)}


# --------------------------------------------------------------------------- record

def record(run: str, cid: str, url: str | None = None, text_file: str | None = None, metrics: str | None = None,
           after: str | None = None, posted_at: str | None = None, root: Path | None = None) -> dict:
    with common.use_root(root):
        rt = common.ROOT
        rd = common.run_dir(run)
        if not rd.is_dir():
            return {"ok": False, "error": f"no run directory drafts/{run}"}
        run = rd.name
        if posted_at and not _DATE_RE.match(posted_at):
            return {"ok": False, "error": "--posted-at must be YYYY-MM-DD"}
        lineage = rate_record.lineage_or_none(run)
        if not rate_record.known_cid(rd, cid, lineage):
            return {"ok": False, "error": f"no candidate {cid} in run {run}"}
        draft = topics.candidate_text(rd, cid, lineage)
        if draft is None:
            return {"ok": False, "error": f"no draft text for {cid} in run {run} (round<k>/candidates or final/)"}
        v = (lineage or {}).get("_by_cid", {}).get(cid, {}) if lineage else {}
        platform = v.get("platform") or topics.candidate_meta(rd, cid).get("platform") or topics.platform_from_cid(cid) or "unknown"
        warnings: list[str] = []

        live = draft
        if text_file:
            tp = Path(text_file)
            tp = tp if tp.is_absolute() else rt / tp
            if not tp.exists():
                return {"ok": False, "error": f"--text-file not found: {text_file}"}
            live = tp.read_text(encoding="utf-8")
            if not live.strip():
                return {"ok": False, "error": f"--text-file is empty: {text_file}"}

        parsed = None
        after_hours = None
        if metrics is not None:
            parsed = metrics_parse.parse(metrics + (f" after {after}" if after else ""))
            if not parsed.get("ok"):
                return {"ok": False, "error": parsed.get("error") or "metrics not recognised", "unparsed": parsed.get("unparsed")}
            after_hours = parsed.get("after_hours")
            warnings += [f"metrics: {w}" for w in parsed.get("warnings") or []]
            if parsed.get("unparsed"):
                warnings.append("metrics: ignored " + ", ".join(parsed["unparsed"]))
        elif after:
            warnings.append("--after ignored without --metrics")

        existing = _published_for(rt, run, cid)
        existing_meta: dict = {}
        if existing is not None:
            try:
                existing_meta, existing_body = common.split_front_matter(existing.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                existing_meta, existing_body = {}, ""
            if not text_file and existing_body.strip():
                live = existing_body  # metrics-only or url-only rerun keeps the recorded live text
        date = posted_at or (existing_meta.get("posted_at") if isinstance(existing_meta, dict) else None) or common.today()
        date = str(date)[:10]
        edited = not _same_text(draft, live)
        ops = edit_ops(draft, live) if edited else []
        op_tags = [o["op"] for o in ops]

        pub = _published_path(rt, run, cid, platform, date)
        meta = {"draft_id": run, "cid": cid, "platform": platform, "posted_at": date,
                "url": url or (existing_meta.get("url") if isinstance(existing_meta, dict) else None),
                "sha256": common.content_sha(live), "edited": edited}
        common.write_front_matter_file(pub, meta, live)
        cal = update_calibration_edit_ops(rt, run, cid, platform, op_tags, edited)
        snapshot = _snapshot(parsed, after_hours) if parsed else None
        perf = upsert_performance(rt, run, cid, platform, meta["url"], common.rel(pub), date, snapshot)
        topic_res = topics.add(run, outcome="posted")
        if not topic_res.get("ok"):
            warnings.append(f"topics.md not updated: {topic_res.get('error')}")
        return {"ok": True, "run": run, "cid": cid, "platform": platform, "published_path": common.rel(pub),
                "edited": edited, "edit_ops": op_tags, "edit_ops_detail": ops, "url": meta["url"], "posted_at": date,
                "calibration": cal["action"], "performance": perf["row"], "performance_created": perf["created"],
                "snapshot": snapshot, "topics_row": topic_res.get("row"), "warnings": warnings}


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record a hand-posted variant: live text, edit_ops diff, performance snapshots.")
    ap.add_argument("run", help="run directory name, e.g. 2026-09-17_agents")
    ap.add_argument("cid", help="variant cid, e.g. r1-w2-li")
    ap.add_argument("--url", default=None, help="the live post URL")
    ap.add_argument("--text-file", default=None, help="file holding the text exactly as posted (pasted final)")
    ap.add_argument("--metrics", default=None, help="plain words: '12k views 40 comments 3 reposts'")
    ap.add_argument("--after", default=None, help="how long after posting the metrics were read: 24h | 7d")
    ap.add_argument("--posted-at", default=None, help="YYYY-MM-DD (default: today, or the recorded date)")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        res = record(args.run, args.cid, url=args.url, text_file=args.text_file, metrics=args.metrics, after=args.after,
                     posted_at=args.posted_at, root=args.root)
    except FileNotFoundError as e:
        common.error(str(e))
        return 0
    common.emit(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
