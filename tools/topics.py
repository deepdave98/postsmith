#!/usr/bin/env python3
"""topics.py: maintain memory/topics.md (contracts §13, §18).

    add <run> [--outcome pass|posted|skipped]
        upsert the run's row `| date | topic | angle | moves | lens | outcome |`
    scoreboard   rewrite `## Moves scoreboard` from evals/calibration.jsonl
    proven       rewrite `## Proven angles` from memory/performance.jsonl and the runs' lineage

The runs table keeps the newest 30 rows. `add` reads drafts/<run>/final/lineage.json (topic, variants) and,
when a variant carries no `assignment`, round<k>/candidates/<cid>.md. The row's angle is the finalist's
`assignment.angle_family`, moves are every variant's `assignment.move` (finalists first, deduplicated), lens
is the finalist's `assignment.lens`.

The scoreboard is `| move | mean_rating | n | last_used |` over generated calibration rows carrying `moves[]`
and a `user_score`. matrix.py parses exactly that header, so it may not be renamed. Proven angles are mean
views and comments per angle family and per move, latest snapshot per posted variant, n >= 3.

CLI: uv run tools/topics.py add <run> [--outcome posted] [--root R] [--json]
API: add(run, outcome=None, root=None) / scoreboard(root=None) / proven(root=None) -> dict
     lineage_info(run, root=None) -> {run, topic, date, variants: [...]}   (rate_record and calibrate use it)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

TOPICS_PATH = Path("memory") / "topics.md"
RUNS_HEADER = ["date", "topic", "angle", "moves", "lens", "outcome"]
SCOREBOARD_HEADER = ["move", "mean_rating", "n", "last_used"]
FAMILY_HEADER = ["angle_family", "n", "views_mean", "comments_mean", "best", "last_posted"]
MOVE_HEADER = ["move_used", "n", "views_mean", "comments_mean", "last_posted"]
RUNS_KEEP = 30
PROVEN_MIN_N = 3
OUTCOMES = ("pass", "posted", "skipped")
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_ROUND_RE = re.compile(r"^round(\d+)$")

TEMPLATE_HEAD = "# Topics used\n\n"
SCOREBOARD_NOTE = ("Mean of Deep's 1-5 ratings per assigned move (evals/calibration.jsonl, generated rows). "
                   "matrix.py excludes moves with mean <= 2.5 at n >= 3 and prefers mean >= 4.\n\n")
PROVEN_NOTE = ("Engagement by angle family and by move: memory/performance.jsonl joined with each run's "
               f"final/lineage.json, latest snapshot per posted variant, n >= {PROVEN_MIN_N}. "
               "Performance never changes a judge score; it informs the matrix and /trending only.\n\n")


# --------------------------------------------------------------------------- markdown tables

def _cell(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, (list, tuple)):
        return ", ".join(_cell(x) for x in v)
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v).replace("|", "/").replace("\n", " ").strip()


def render_table(header: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return "\n".join(out) + "\n"


def parse_table(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """First markdown table in `lines` -> (header, rows) with stripped cells. None when there is none."""
    header: list[str] | None = None
    rows: list[list[str]] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("|"):
            if header is not None:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = [c.lower().strip("`* ") for c in cells]
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and any(cells):
            continue
        rows.append(cells)
    return (header, rows) if header is not None else None


def split_sections(text: str) -> list[tuple[str | None, list[str]]]:
    """Split a markdown file into (heading_line | None, body_lines) at every `#` or `##` heading."""
    sections: list[tuple[str | None, list[str]]] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if re.match(r"^#{1,2}\s+\S", line):
            sections.append((heading, body))
            heading, body = line.rstrip(), []
        else:
            body.append(line)
    sections.append((heading, body))
    return sections


def _find_section(sections: list[tuple[str | None, list[str]]], title: str) -> int | None:
    for i, (h, _b) in enumerate(sections):
        if h and h.lstrip("#").strip().lower() == title.lower():
            return i
    return None


def _read_topics(root: Path) -> list[tuple[str | None, list[str]]]:
    p = root / TOPICS_PATH
    if not p.exists():
        return split_sections(TEMPLATE_HEAD.rstrip("\n"))
    return split_sections(p.read_text(encoding="utf-8"))


def _write_topics(root: Path, sections: list[tuple[str | None, list[str]]]) -> Path:
    parts: list[str] = []
    for h, body in sections:
        chunk = ("\n".join(body)).strip("\n")
        if h is not None:
            parts.append(h + ("\n\n" + chunk if chunk else "") + "\n")
        elif chunk:
            parts.append(chunk + "\n")
    text = "\n".join(parts)
    if not text.startswith("#"):
        text = TEMPLATE_HEAD + text
    p = root / TOPICS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    return p


def _replace_section(sections: list[tuple[str | None, list[str]]], title: str, body: str,
                     level: int = 2) -> list[tuple[str | None, list[str]]]:
    idx = _find_section(sections, title)
    new = ("#" * level + " " + title, body.rstrip("\n").split("\n"))
    if idx is None:
        return sections + [new]
    return sections[:idx] + [new] + sections[idx + 1:]


# --------------------------------------------------------------------------- lineage / candidates

def run_date(run: str) -> str | None:
    m = _DATE_RE.match(Path(run).name)
    return m.group(1) if m else None


def run_slug(run: str) -> str:
    name = Path(run).name
    m = re.match(r"^\d{4}-\d{2}-\d{2}[_-]?(.*)$", name)
    slug = (m.group(1) if m else name) or name
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower()
    return slug or "post"


def platform_from_cid(cid: str | None) -> str | None:
    if not cid:
        return None
    if cid.endswith(("-x", "-x1")):
        return "x"
    if cid.endswith("-li"):
        return "linkedin"
    return None


def rounds(rd: Path) -> list[Path]:
    """drafts/<run>/round<k> directories in round order."""
    dirs = [p for p in rd.iterdir() if p.is_dir() and _ROUND_RE.match(p.name)] if rd.is_dir() else []
    return sorted(dirs, key=lambda p: int(_ROUND_RE.match(p.name).group(1)))  # type: ignore[union-attr]


def candidate_meta(rd: Path, cid: str) -> dict:
    """Front matter of the newest round<k>/candidates/<cid>.md. Empty when there is none."""
    for r in reversed(rounds(rd)):
        p = r / "candidates" / f"{cid}.md"
        if p.exists():
            try:
                meta, _ = common.split_front_matter(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - malformed candidate front matter is not this tool's error
                return {}
            return meta if isinstance(meta, dict) else {}
    return {}


def _fenced(body: str) -> str | None:
    m = re.search(r"```[a-zA-Z]*\n(.*?)\n?```", body, re.DOTALL)
    return m.group(1) if m else None


def candidate_text(rd: Path, cid: str, lineage: dict | None = None) -> str | None:
    """Post text as the judges saw it: the newest round<k>/candidates/<cid>.txt, else the fenced block in
    the run's final/ file."""
    for r in reversed(rounds(rd)):
        p = r / "candidates" / f"{cid}.txt"
        if p.exists():
            return p.read_text(encoding="utf-8")
        p = r / "candidates" / f"{cid}.md"
        if p.exists():
            _m, body = common.split_front_matter(p.read_text(encoding="utf-8"))
            return body
    v = (lineage or {}).get("_by_cid", {}).get(cid) if lineage else None
    fp = (v or {}).get("final_path") or (v or {}).get("path")
    cands = [rd / "final" / Path(str(fp)).name] if fp else []
    cands += sorted((rd / "final").glob("*.md")) if (rd / "final").is_dir() else []
    for p in cands:
        if not p.exists() or p.name in ("report.md", "clipboard.md", "README.md"):
            continue
        meta, body = common.split_front_matter(p.read_text(encoding="utf-8"))
        if isinstance(meta, dict) and (meta.get("cid") == cid or (fp and p.name == Path(str(fp)).name)):
            return _fenced(body) or body.strip("\n")
    return None


def _variants(lineage: dict) -> list[dict]:
    v = lineage.get("variants")
    out: list[dict] = []
    if isinstance(v, dict):
        for cid, row in v.items():
            if isinstance(row, dict):
                out.append({"cid": str(row.get("cid") or cid), **row})
    elif isinstance(v, list):
        for row in v:
            if isinstance(row, dict) and row.get("cid"):
                out.append(dict(row))
    return out


def lineage_info(run: str, root: Path | None = None) -> dict:
    """{run, topic, date, variants: [{cid, platform, verdict, tier2_tested, final_path, scores_path,
    assignment}]}. Raises FileNotFoundError when the run has no final/lineage.json.
    """
    with common.use_root(root):
        rd = common.run_dir(run)
        lp = rd / "final" / "lineage.json"
        if not lp.exists():
            raise FileNotFoundError(f"no final/lineage.json for run {Path(run).name} (deliver it first)")
        lineage = common.read_json(lp, default={}) or {}
        if not isinstance(lineage, dict):
            lineage = {}
        variants: list[dict] = []
        for v in _variants(lineage):
            cid = v["cid"]
            meta = candidate_meta(rd, cid)
            assignment = v.get("assignment") if isinstance(v.get("assignment"), dict) else meta.get("assignment")
            assignment = assignment if isinstance(assignment, dict) else {}
            fmeta: dict = {}
            fp = v.get("final_path") or v.get("path")
            if fp:
                f = rd / "final" / Path(str(fp)).name
                if f.exists():
                    try:
                        fmeta, _ = common.split_front_matter(f.read_text(encoding="utf-8"))
                    except Exception:  # noqa: BLE001
                        fmeta = {}
                    fmeta = fmeta if isinstance(fmeta, dict) else {}
            variants.append({
                "cid": cid,
                "platform": v.get("platform") or fmeta.get("platform") or meta.get("platform") or platform_from_cid(cid),
                "verdict": v.get("verdict") if v.get("verdict") is not None else fmeta.get("verdict"),
                "tier2_tested": bool(v.get("tier2_tested", fmeta.get("tier2_tested", False))),
                "final_path": fp,
                "scores_path": v.get("scores_path") or fmeta.get("scores_path"),
                "assignment": assignment,
                "media_path": v.get("media_path"),
                "lessons_used": v.get("lessons_used") or (meta.get("lineage") or {}).get("lessons_used") or [],
            })
        variants.sort(key=lambda x: (not x["tier2_tested"], x["verdict"] != "pass", x["cid"]))
        return {"run": rd.name, "topic": str(lineage.get("topic") or run_slug(rd.name).replace("-", " ")),
                "date": run_date(rd.name) or common.today(), "variants": variants,
                "_by_cid": {x["cid"]: x for x in variants}, "flags": lineage.get("flags"),
                "versions": lineage.get("versions") or {}}


# --------------------------------------------------------------------------- add

def _row_from_lineage(info: dict, outcome: str | None) -> dict:
    variants = info["variants"]
    finalist = variants[0] if variants else {}
    moves: list[str] = []
    for v in variants:
        mv = (v.get("assignment") or {}).get("move")
        if isinstance(mv, str) and mv and mv not in moves:
            moves.append(mv)
    if outcome is None:
        outcome = "pass" if any(v.get("verdict") == "pass" for v in variants) else "no_pass"
    return {"date": info["date"], "topic": info["topic"],
            "angle": (finalist.get("assignment") or {}).get("angle_family") or None,
            "moves": moves, "lens": (finalist.get("assignment") or {}).get("lens") or None, "outcome": outcome}


def _runs_rows(sections: list[tuple[str | None, list[str]]]) -> tuple[int, list[dict]]:
    """(index of the section holding the runs table, rows as dicts). Creates nothing."""
    for i, (_h, body) in enumerate(sections):
        t = parse_table(body)
        if t and "date" in t[0] and "moves" in t[0]:
            header, rows = t
            idx = {h: j for j, h in enumerate(header)}
            out = []
            for r in rows:
                cell = {k: (r[j].strip() if j < len(r) else "") for k, j in idx.items()}
                if not cell.get("date"):
                    continue
                out.append({"date": cell.get("date", ""), "topic": cell.get("topic", ""), "angle": cell.get("angle", ""),
                            "moves": [m.strip() for m in cell.get("moves", "").split(",") if m.strip()],
                            "lens": cell.get("lens", ""), "outcome": cell.get("outcome", "")})
            return i, out
    return -1, []


def _render_runs(rows: list[dict]) -> str:
    rows = sorted(rows, key=lambda r: r["date"], reverse=True)[:RUNS_KEEP]
    return render_table(RUNS_HEADER, [[r["date"], r["topic"], r["angle"] or "null", r["moves"] or "null",
                                       r["lens"] or "null", r["outcome"]] for r in rows])


def add(run: str, outcome: str | None = None, root: Path | None = None) -> dict:
    """Upsert the run's row, matched on date plus topic. Returns {ok, row, path, created}."""
    with common.use_root(root):
        rt = common.ROOT
        try:
            info = lineage_info(run)
        except FileNotFoundError as e:
            return {"ok": False, "error": str(e)}
        row = _row_from_lineage(info, outcome)
        sections = _read_topics(rt)
        idx, rows = _runs_rows(sections)
        created = True
        for r in rows:
            if r["date"] == row["date"] and r["topic"].strip().lower() == row["topic"].strip().lower():
                r.update({k: v for k, v in row.items() if k != "outcome"})
                r["outcome"] = row["outcome"] if outcome is not None or not r["outcome"] else r["outcome"]
                row = r
                created = False
                break
        if created:
            rows.append(row)
        table = _render_runs(rows)
        if idx < 0:
            # no runs table yet: put it in the first section, the title, ahead of every other section
            h, body = sections[0]
            lead = "\n".join(body).strip("\n")
            sections[0] = (h, ((lead + "\n\n") if lead else "").split("\n") + table.split("\n"))
        else:
            h, body = sections[idx]
            t = parse_table(body)
            start = next(i for i, ln in enumerate(body) if ln.strip().startswith("|"))
            end = start + 2 + len(t[1]) if t else start
            sections[idx] = (h, body[:start] + table.rstrip("\n").split("\n") + body[end:])
        p = _write_topics(rt, sections)
        return {"ok": True, "row": row, "path": common.rel(p), "created": created, "run": info["run"]}


# --------------------------------------------------------------------------- scoreboard

def calibration_rows(root: Path | None = None) -> list[dict]:
    with common.use_root(root):
        return common.read_jsonl(common.ROOT / "evals" / "calibration.jsonl")


def scoreboard_rows(rows: list[dict]) -> list[dict]:
    """[{move, mean_rating, n, last_used}] sorted by mean desc, n desc, move."""
    acc: dict[str, dict] = {}
    for r in rows:
        if r.get("kind", "generated") != "generated":
            continue
        score = r.get("user_score")
        if not isinstance(score, (int, float)):
            continue
        date = str(r.get("ts") or "")[:10]
        for mv in r.get("moves") or []:
            if not isinstance(mv, str) or not mv:
                continue
            a = acc.setdefault(mv, {"sum": 0.0, "n": 0, "last": ""})
            a["sum"] += float(score)
            a["n"] += 1
            a["last"] = max(a["last"], date)
    out = [{"move": m, "mean_rating": round(a["sum"] / a["n"], 2), "n": a["n"], "last_used": a["last"] or None}
           for m, a in acc.items() if a["n"]]
    out.sort(key=lambda x: (-x["mean_rating"], -x["n"], x["move"]))
    return out


def scoreboard(root: Path | None = None) -> dict:
    with common.use_root(root):
        rt = common.ROOT
        rows = scoreboard_rows(calibration_rows())
        body = SCOREBOARD_NOTE + render_table(SCOREBOARD_HEADER, [[r["move"], r["mean_rating"], r["n"],
                                                                   r["last_used"] or ""] for r in rows])
        sections = _replace_section(_read_topics(rt), "Moves scoreboard", body)
        p = _write_topics(rt, sections)
        return {"ok": True, "scoreboard": rows, "path": common.rel(p), "n_rows": len(rows)}


# --------------------------------------------------------------------------- proven angles

def _latest_snapshot(row: dict) -> dict:
    snaps = [s for s in (row.get("snapshots") or []) if isinstance(s, dict)]
    if not snaps:
        return {}
    return max(snaps, key=lambda s: (str(s.get("at") or ""), s.get("after_hours") or 0))


def posted_variants(root: Path | None = None) -> list[dict]:
    """performance.jsonl rows joined with lineage: [{draft_id, cid, platform, posted_at, views, comments,
    likes, angle_family, move, lens, url}], one row per posted variant, latest snapshot."""
    with common.use_root(root):
        rt = common.ROOT
        out: list[dict] = []
        cache: dict[str, dict | None] = {}
        for r in common.read_jsonl(rt / "memory" / "performance.jsonl"):
            run = str(r.get("draft_id") or "")
            cid = str(r.get("cid") or "")
            if run not in cache:
                try:
                    cache[run] = lineage_info(run)
                except (FileNotFoundError, OSError, ValueError):
                    cache[run] = None
            info = cache[run]
            v = (info or {}).get("_by_cid", {}).get(cid, {}) if info else {}
            a = v.get("assignment") or {}
            snap = _latest_snapshot(r)
            out.append({"draft_id": run, "cid": cid, "platform": r.get("platform") or v.get("platform"),
                        "posted_at": str(r.get("posted_at") or r.get("ts") or "")[:10], "url": r.get("url"),
                        "views": snap.get("views"), "comments": snap.get("comments"), "likes": snap.get("likes"),
                        "angle_family": a.get("angle_family"), "move": a.get("move"), "lens": a.get("lens"),
                        "has_metrics": bool(snap)})
        return out


def _mean(xs: list[float]) -> float | None:
    xs = [float(x) for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 1) if xs else None


def aggregate_by(items: list[dict], key: str, min_n: int = PROVEN_MIN_N) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for it in items:
        k = it.get(key)
        if isinstance(k, str) and k and it.get("has_metrics"):
            groups.setdefault(k, []).append(it)
    out = []
    for k, rows in groups.items():
        if len(rows) < min_n:
            continue
        best = max(rows, key=lambda r: (r.get("views") or 0, r.get("comments") or 0))
        out.append({key: k, "n": len(rows), "views_mean": _mean([r["views"] for r in rows if r.get("views") is not None]),
                    "comments_mean": _mean([r["comments"] for r in rows if r.get("comments") is not None]),
                    "best": f"{best['draft_id']}/{best['cid']}", "last_posted": max(r["posted_at"] for r in rows)})
    out.sort(key=lambda x: (-(x["views_mean"] or 0), -(x["comments_mean"] or 0), x[key]))
    return out


def proven(root: Path | None = None) -> dict:
    with common.use_root(root):
        rt = common.ROOT
        items = posted_variants()
        fam = aggregate_by(items, "angle_family")
        mov = aggregate_by(items, "move")
        body = PROVEN_NOTE
        body += render_table(FAMILY_HEADER, [[f["angle_family"], f["n"], f["views_mean"], f["comments_mean"], f["best"],
                                              f["last_posted"]] for f in fam]) + "\n"
        body += render_table(MOVE_HEADER, [[m["move"], m["n"], m["views_mean"], m["comments_mean"], m["last_posted"]]
                                           for m in mov])
        sections = _replace_section(_read_topics(rt), "Proven angles", body)
        p = _write_topics(rt, sections)
        return {"ok": True, "families": fam, "moves": mov, "n_posted": len(items),
                "n_with_metrics": sum(1 for i in items if i["has_metrics"]), "path": common.rel(p)}


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Maintain memory/topics.md: run rows, moves scoreboard, proven angles.")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    common_flags = argparse.ArgumentParser(add_help=False)  # --root / --json accepted after the subcommand too
    common_flags.add_argument("--root", default=argparse.SUPPRESS, help="project root (default: this project)")
    common_flags.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="JSON output")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", parents=[common_flags], help="upsert the run's row from drafts/<run>/final/lineage.json")
    a.add_argument("run")
    a.add_argument("--outcome", choices=OUTCOMES, default=None,
                   help="pass|posted|skipped (default: pass when a variant passed, else no_pass)")
    sub.add_parser("scoreboard", parents=[common_flags], help="rewrite ## Moves scoreboard from evals/calibration.jsonl")
    sub.add_parser("proven", parents=[common_flags], help="rewrite ## Proven angles from memory/performance.jsonl")
    args = ap.parse_args(argv)
    try:
        with common.use_root(args.root):
            if args.cmd == "add":
                res = add(args.run, outcome=args.outcome)
            elif args.cmd == "scoreboard":
                res = scoreboard()
            else:
                res = proven()
    except FileNotFoundError as e:
        common.error(str(e))
        return 0
    common.emit(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
