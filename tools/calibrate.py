#!/usr/bin/env python3
"""How well the judges track Deep's ratings (contracts §17).

Reads evals/calibration.jsonl (generated rows joined with judge medians by rate_record.py) and reports:

- Cohen's kappa on pass/fail: user pass = user_score >= 4, system pass = verdict == "pass". Withheld (value null,
  status "withheld") until config calibration.min_system_fails_for_kappa rated system-fails exist AND
  n >= min_ratings_for_kappa; `mode` stays "advisory" until kappa >= kappa_advisory_threshold on that n.
- Spearman rho between user_score and the number of judged dimensions at or above their threshold
  (thresholds.yaml `dimensions`; na / missing dimensions are skipped). Average ranks for ties; pure Python.
- Per-tag false-negative rates using the contract tag -> dimension map (TAG_DIMENSIONS): a complaint tag whose
  mapped dimensions all passed is a false negative. Positive tags (media_great) report how often the system
  flagged what Deep praised instead.
- Proposals in the fix order 1 user tell -> 2 anchor -> 3 threshold -> 4 anchor text, as structured JSON.
- Drift of judge medians across rubric versions.
- Performance PREFER/AVOID proposals by angle family / move / lens once >= calibration.performance_min_posts
  (default 20) posted variants carry metrics.

Writes evals/health/reports/calibration_<date>.md (unless --no-write) with a `ratings_total: N` line that
rate_record.py --proposals reads to know when the next calibration is due.

CLI: uv run tools/calibrate.py [--no-write] [--date YYYY-MM-DD] [--root R] [--json]
API: compute(root=None, today=None) -> dict ; run(root=None, write=True, today=None) -> dict (adds report_path)
     cohen_kappa(a, b, c, d) ; spearman(xs, ys) ; rank_average(xs)
"""
from __future__ import annotations

import argparse
import itertools
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import topics  # noqa: E402

TAGS = ("too_safe", "not_funny", "sounds_ai", "not_me", "too_long", "too_short", "hook_weak", "copycat", "wrong_facts",
        "too_mean", "great_hook", "great_ending", "media_miss", "media_great")
POSITIVE_TAGS = frozenset({"great_hook", "great_ending", "media_great"})
# contracts §17: which system signal each tag should have caught
TAG_DIMENSIONS: dict[str, list[str]] = {
    "sounds_ai": ["not_ai", "lineup"],
    "not_me": ["persona_fit", "register_match_self"],
    "not_funny": ["humor"],
    "copycat": ["overlap", "paraphrase"],
    "hook_weak": ["hook"],
    "too_long": ["E1_envelope"],
    "too_mean": ["regret_risk"],
    "media_miss": ["media"],
    "media_great": ["media"],
}
USER_TELL_TAGS = ("sounds_ai", "not_me")
FIX_ORDER = ("user_tell", "anchor", "threshold", "anchor_text")
REPORTS_DIR = Path("evals") / "health" / "reports"
_RATINGS_LINE_RE = re.compile(r"^ratings_total:\s*(\d+)\s*$", re.MULTILINE)
OVERLAP_CHECKS = ("O1_ngram", "O2_phrases", "O3_skeleton", "O4_sibling", "O5_published")


# --------------------------------------------------------------------------- statistics (pure Python)

def cohen_kappa(a: int, b: int, c: int, d: int) -> float | None:
    """kappa for the 2x2 table [[a, b], [c, d]]:
    [[both pass, user pass/system fail], [user fail/system pass, both fail]]."""
    n = a + b + c + d
    if n == 0:
        return None
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / (n * n)
    if math.isclose(pe, 1.0):
        return 1.0 if math.isclose(po, 1.0) else 0.0
    return (po - pe) / (1 - pe)


def rank_average(xs: list[float]) -> list[float]:
    """Ranks starting at 1 with ties given their average rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman's rho = Pearson correlation of the average ranks. None below 3 pairs or with zero variance."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = rank_average(xs), rank_average(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


# --------------------------------------------------------------------------- row inspection

def _thresholds_map(root: Path) -> dict[str, int]:
    """dimension -> threshold from the current rubric (empty when no rubric exists)."""
    try:
        with common.use_root(root):
            th = common.load_thresholds()
    except (FileNotFoundError, OSError, RuntimeError):
        return {}
    dims = th.get("dimensions") if isinstance(th, dict) else {}
    out: dict[str, int] = {}
    for d, spec in (dims or {}).items():
        if isinstance(spec, dict) and isinstance(spec.get("threshold"), (int, float)):
            out[d] = int(spec["threshold"])
    return out


def dims_at_threshold(row: dict, thresholds: dict[str, int]) -> int | None:
    """Count of judged dimensions with median >= threshold; None when the row carries no judge scores."""
    scores = row.get("judge_scores") or {}
    n = 0
    seen = False
    for dim, val in scores.items():
        if not isinstance(val, (int, float)):
            continue
        seen = True
        if val >= thresholds.get(dim, 4):
            n += 1
    return n if seen else None


def system_flagged(row: dict, signal: str, thresholds: dict[str, int]) -> bool | None:
    """Did the system flag `signal` on this row? True / False / None (not evaluated for this row)."""
    scores = row.get("judge_scores") or {}
    soft = list(row.get("tier0_soft_flags") or [])
    hard = list(row.get("tier0_hard_fails") or [])
    if signal == "lineup":
        lp = row.get("lineup_pass")
        return (not lp) if isinstance(lp, bool) else None
    if signal == "paraphrase":
        p = row.get("paraphrase")
        return bool(p) if isinstance(p, bool) else None
    if signal == "overlap":
        if not soft and not hard and row.get("verdict") is None:
            return None
        return any(c in OVERLAP_CHECKS for c in soft + hard)
    if signal == "media":
        mp = row.get("media_pass")
        return (not mp) if isinstance(mp, bool) else None
    if signal.startswith(("E1", "P")):
        if not soft and not hard and row.get("verdict") is None:
            return None
        return signal in soft or signal in hard
    val = scores.get(signal)
    if not isinstance(val, (int, float)):
        return None
    return val < thresholds.get(signal, 4)


def _system_pass(row: dict) -> bool | None:
    v = row.get("verdict")
    if v is None:
        return None
    return v == "pass"


def _user_pass(row: dict) -> bool | None:
    s = row.get("user_score")
    return (s >= 4) if isinstance(s, (int, float)) else None


def _ref(row: dict) -> str:
    return str(row.get("post_ref") or "")


def cid_of(row: dict) -> str:
    ref = _ref(row)
    return ref.split("/", 1)[1] if "/" in ref else ref


# --------------------------------------------------------------------------- sections

def kappa_section(rows: list[dict], cfg: dict) -> dict:
    ccfg = cfg.get("calibration") or {}
    min_fails = int(ccfg.get("min_system_fails_for_kappa", 8))
    min_n = int(ccfg.get("min_ratings_for_kappa", 30))
    adv = float(ccfg.get("kappa_advisory_threshold", 0.4))
    a = b = c = d = 0
    for r in rows:
        up, sp = _user_pass(r), _system_pass(r)
        if up is None or sp is None:
            continue
        if up and sp:
            a += 1
        elif up and not sp:
            b += 1
        elif not up and sp:
            c += 1
        else:
            d += 1
    n = a + b + c + d
    system_fails = b + d
    table = {"user_pass_system_pass": a, "user_pass_system_fail": b, "user_fail_system_pass": c,
             "user_fail_system_fail": d}
    reasons = []
    if system_fails < min_fails:
        reasons.append(f"{system_fails} rated system-fail(s) < {min_fails}")
    if n < min_n:
        reasons.append(f"n={n} < {min_n}")
    if reasons:
        return {"value": None, "status": "withheld", "reason": "; ".join(reasons), "n": n,
                "system_fails": system_fails, "table": table, "advisory_threshold": adv, "mode": "advisory"}
    k = cohen_kappa(a, b, c, d)
    k = round(k, 4) if k is not None else None   # rounded before the comparison: 0.39999999 is 0.4
    mode = "calibrated" if k is not None and k >= adv else "advisory"
    return {"value": k, "status": "reported", "reason": None, "n": n,
            "system_fails": system_fails, "table": table, "advisory_threshold": adv, "mode": mode}


def rho_section(rows: list[dict], thresholds: dict[str, int]) -> dict:
    xs: list[float] = []
    ys: list[float] = []
    for r in rows:
        s = r.get("user_score")
        k = dims_at_threshold(r, thresholds)
        if isinstance(s, (int, float)) and k is not None:
            xs.append(float(s))
            ys.append(float(k))
    rho = spearman(xs, ys)
    return {"value": round(rho, 4) if rho is not None else None, "n": len(xs),
            "note": "user_score vs number of judged dimensions at or above threshold"}


def per_tag_section(rows: list[dict], thresholds: dict[str, int]) -> dict:
    out: dict[str, dict] = {}
    for tag in TAGS:
        tagged = [r for r in rows if tag in (r.get("tags") or [])]
        dims = TAG_DIMENSIONS.get(tag, [])
        misses: list[str] = []
        evaluable = 0
        for r in tagged:
            flags = [system_flagged(r, d, thresholds) for d in dims]
            known = [f for f in flags if f is not None]
            if not known:
                continue
            evaluable += 1
            caught = any(known)
            if tag in POSITIVE_TAGS:
                if caught:
                    misses.append(_ref(r))
            elif not caught:
                misses.append(_ref(r))
        key = "system_flagged" if tag in POSITIVE_TAGS else "false_negatives"
        out[tag] = {"n": len(tagged), "dimensions": dims, "evaluable": evaluable, key: len(misses),
                    "rate": round(len(misses) / evaluable, 3) if evaluable else None, "refs": misses}
    return out


def lexicon_user_tells(root: Path) -> set[str]:
    with common.use_root(root):
        try:
            lex = common.load_lexicon()
        except (FileNotFoundError, OSError, RuntimeError):
            return set()
    return {str(t.get("phrase", "")).strip().lower() for t in (lex.get("user_tells") or []) if isinstance(t, dict)}


def _failing_dims(row: dict, thresholds: dict[str, int]) -> list[str]:
    fails = [d for d, v in (row.get("judge_scores") or {}).items()
             if isinstance(v, (int, float)) and v < thresholds.get(d, 4)]
    fails += [c for c in (row.get("tier0_hard_fails") or []) + (row.get("tier0_soft_flags") or [])]
    if row.get("lineup_pass") is False:
        fails.append("lineup")
    if row.get("paraphrase") is True:
        fails.append("paraphrase")
    return fails


def proposals_section(rows: list[dict], thresholds: dict[str, int], root: Path) -> list[dict]:
    props: list[dict] = []
    known_tells = lexicon_user_tells(root)
    # 1. user tells: sounds_ai / not_me with a cited phrase (the note)
    for r in rows:
        tags = r.get("tags") or []
        note = str(r.get("note") or "").strip()
        for tag in USER_TELL_TAGS:
            if tag in tags and note and note.lower() not in known_tells:
                props.append({"order": 1, "kind": "user_tell", "tag": tag, "phrase": note, "post_ref": _ref(r),
                              "source": f"rate:{cid_of(r)}",
                              "why": f"tag {tag} with a cited phrase; add to style/lexicon.yaml user_tells"})
    # 2. anchors from disagreements
    raise_votes: dict[str, list[str]] = {}
    lower_votes: dict[str, list[str]] = {}
    for r in rows:
        up, sp = _user_pass(r), _system_pass(r)
        if up is None or sp is None or up == sp:
            continue
        if up and not sp:
            for d in _failing_dims(r, thresholds) or ["unspecified"]:
                lower_votes.setdefault(d, []).append(_ref(r))
            dims = _failing_dims(r, thresholds)
            props.append({"order": 2, "kind": "anchor", "strength": "strong", "post_ref": _ref(r),
                          "dimension": dims[0] if dims else None, "dimensions": dims,
                          "why": f"Deep {r.get('user_score')}/5 on a system {r.get('verdict')}; make it a strong anchor"})
        else:
            dims = [d for t in (r.get("tags") or []) for d in TAG_DIMENSIONS.get(t, [])]
            for d in dims or ["unspecified"]:
                raise_votes.setdefault(d, []).append(_ref(r))
            props.append({"order": 2, "kind": "anchor", "strength": "weak", "post_ref": _ref(r),
                          "dimension": dims[0] if dims else None, "dimensions": dims,
                          "why": f"Deep {r.get('user_score')}/5 on a system pass; make it a weak anchor"})
    # 3. thresholds: >= 3 complaint tags the mapped dimension passed -> raise; >= 3 user-pass on a dim fail -> lower
    for tag, dims in TAG_DIMENSIONS.items():
        if tag in POSITIVE_TAGS:
            continue
        for d in dims:
            if d not in thresholds:
                continue
            refs = [_ref(r) for r in rows if tag in (r.get("tags") or []) and system_flagged(r, d, thresholds) is False]
            if len(refs) >= 3:
                raise_votes.setdefault(d, []).extend(x for x in refs if x not in raise_votes.get(d, []))
    for d, refs in sorted(raise_votes.items()):
        if d in thresholds and len(refs) >= 3:
            props.append({"order": 3, "kind": "threshold", "dimension": d, "direction": "+1",
                          "current": thresholds[d], "n": len(refs), "refs": refs,
                          "why": "the dimension passed on posts Deep tagged; the bar is too low"})
    for d, refs in sorted(lower_votes.items()):
        if d in thresholds and len(refs) >= 3:
            props.append({"order": 3, "kind": "threshold", "dimension": d, "direction": "-1",
                          "current": thresholds[d], "n": len(refs), "refs": refs,
                          "why": "the dimension failed posts Deep rated >= 4; the bar is too high"})
    # 4. anchor text: a dimension pulled both ways
    for d in sorted(set(raise_votes) & set(lower_votes)):
        if d in thresholds and len(raise_votes[d]) >= 2 and len(lower_votes[d]) >= 2:
            props.append({"order": 4, "kind": "anchor_text", "dimension": d,
                          "refs": sorted(set(raise_votes[d] + lower_votes[d])),
                          "why": "disagreements in both directions: the anchor text, not the threshold, is the problem"})
    props.sort(key=lambda p: (p["order"], str(p.get("dimension") or ""), str(p.get("post_ref") or "")))
    return props


def _version_key(v: str) -> tuple[int, str]:
    m = re.match(r"^v(\d+)", str(v))
    return (int(m.group(1)) if m else 10**9, str(v))


def drift_section(rows: list[dict]) -> dict:
    by_ver: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        ver = str(r.get("rubric_version") or "unknown")
        for d, v in (r.get("judge_scores") or {}).items():
            if isinstance(v, (int, float)):
                by_ver.setdefault(ver, {}).setdefault(d, []).append(float(v))
    versions = sorted(by_ver, key=_version_key)
    per_dim: dict[str, dict] = {}
    for ver in versions:
        for d, vals in by_ver[ver].items():
            per_dim.setdefault(d, {})[ver] = {"median": common.median(vals), "n": len(vals)}
    for d, vers in per_dim.items():
        seq = [v for v in versions if v in vers]
        for prev, cur in itertools.pairwise(seq):
            a, b = vers[prev]["median"], vers[cur]["median"]
            vers[cur]["delta_from"] = prev
            vers[cur]["delta"] = round(b - a, 3) if a is not None and b is not None else None
    return {"versions": versions, "per_dimension": per_dim}


def performance_section(root: Path, cfg: dict) -> dict:
    min_posts = int((cfg.get("calibration") or {}).get("performance_min_posts", 20))
    items = topics.posted_variants(root)
    with_metrics = [i for i in items if i["has_metrics"]]
    res: dict = {"n_posted": len(items), "n_with_metrics": len(with_metrics), "min_posts": min_posts, "proposals": []}
    if len(with_metrics) < min_posts:
        res["note"] = f"PREFER/AVOID by angle family, move and lens after {min_posts} posted variants with metrics"
        return res
    views = [i["views"] for i in with_metrics if isinstance(i.get("views"), (int, float))]
    overall = (sum(views) / len(views)) if views else None
    for key in ("angle_family", "move", "lens"):
        for g in topics.aggregate_by(with_metrics, key):
            vm = g.get("views_mean")
            if overall is None or vm is None:
                continue
            if vm >= 1.5 * overall:
                res["proposals"].append({"section": "PREFER", key: g[key], "n": g["n"], "views_mean": vm,
                                         "overall_views_mean": round(overall, 1)})
            elif vm <= 0.5 * overall:
                res["proposals"].append({"section": "AVOID", key: g[key], "n": g["n"], "views_mean": vm,
                                         "overall_views_mean": round(overall, 1)})
    return res


# --------------------------------------------------------------------------- compute / report

def compute(root: Path | None = None, today: str | None = None) -> dict:
    with common.use_root(root):
        rt = common.ROOT
        cfg = common.load_config() if (rt / "config" / "postsmith.yaml").exists() else {}
        all_rows = common.read_jsonl(rt / "evals" / "calibration.jsonl")
        rated = [r for r in all_rows if isinstance(r.get("user_score"), (int, float))]
        gen = [r for r in rated if r.get("kind", "generated") == "generated"]
        corpus = [r for r in rated if r.get("kind") == "corpus"]
        thresholds = _thresholds_map(rt)
        kappa = kappa_section(gen, cfg)
        return {
            "ok": True, "date": today or common.today(), "ratings_total": len(rated), "n_generated": len(gen),
            "n_corpus": len(corpus), "n_system_fails": kappa["system_fails"], "mode": kappa["mode"],
            "kappa": kappa, "rho": rho_section(gen, thresholds), "per_tag": per_tag_section(gen, thresholds),
            "proposals": proposals_section(gen, thresholds, rt), "drift": drift_section(gen),
            "performance": performance_section(rt, cfg), "thresholds": thresholds,
            "rubric_version": (sorted({str(r.get("rubric_version")) for r in gen if r.get("rubric_version")},
                                      key=_version_key) or [None])[-1],
        }


def render_report(res: dict) -> str:
    k, rho = res["kappa"], res["rho"]
    lines = [f"# Calibration report {res['date']}", "",
             f"ratings_total: {res['ratings_total']}",
             f"generated: {res['n_generated']} · corpus: {res['n_corpus']} · system_fails: {res['n_system_fails']}",
             f"mode: {res['mode']}",
             (f"kappa: {k['value']} (n={k['n']})" if k["status"] == "reported" else f"kappa: withheld ({k['reason']})"),
             f"rho: {rho['value']} (n={rho['n']})", ""]
    t = k["table"]
    lines += ["## Pass/fail table", "", "| | system pass | system fail |", "|---|---|---|",
              f"| user >= 4 | {t['user_pass_system_pass']} | {t['user_pass_system_fail']} |",
              f"| user <= 3 | {t['user_fail_system_pass']} | {t['user_fail_system_fail']} |", ""]
    lines += ["## Per-tag false negatives", "", "| tag | n | evaluable | misses | rate | dimensions |", "|---|---|---|---|---|---|"]
    for tag, row in res["per_tag"].items():
        misses = row.get("false_negatives", row.get("system_flagged", 0))
        rate = "" if row["rate"] is None else f"{row['rate']:.2f}"
        lines.append(f"| {tag} | {row['n']} | {row['evaluable']} | {misses} | {rate} | {', '.join(row['dimensions'])} |")
    lines += ["", "## Proposals (fix order: user tell -> anchor -> threshold -> anchor text)", ""]
    if not res["proposals"]:
        lines.append("none")
    for p in res["proposals"]:
        detail = {kk: vv for kk, vv in p.items() if kk not in ("order", "kind", "why", "refs", "dimensions")}
        lines.append(f"{p['order']}. {p['kind']}: " + ", ".join(f"{kk}={vv}" for kk, vv in detail.items()) + f" — {p['why']}")
    lines += ["", "## Drift of judge medians across rubric versions", ""]
    d = res["drift"]
    if not d["versions"]:
        lines.append("no judged rows")
    else:
        lines.append("| dimension | " + " | ".join(d["versions"]) + " |")
        lines.append("|---|" + "|".join("---" for _ in d["versions"]) + "|")
        for dim, vers in sorted(d["per_dimension"].items()):
            cells = []
            for v in d["versions"]:
                cell = vers.get(v)
                if not cell:
                    cells.append("")
                else:
                    s = f"{cell['median']} (n={cell['n']})"
                    if cell.get("delta") is not None:
                        s += f" Δ{cell['delta']:+}"
                    cells.append(s)
            lines.append(f"| {dim} | " + " | ".join(cells) + " |")
    perf = res["performance"]
    lines += ["", "## Performance", "",
              f"posted: {perf['n_posted']} · with metrics: {perf['n_with_metrics']} · proposals after {perf['min_posts']}"]
    for p in perf["proposals"]:
        key = next(kk for kk in ("angle_family", "move", "lens") if kk in p)
        lines.append(f"- {p['section']} {key}={p[key]} (n={p['n']}, views_mean={p['views_mean']} vs {p['overall_views_mean']})")
    return "\n".join(lines) + "\n"


def last_report_total(root: Path | None = None) -> int | None:
    """ratings_total recorded by the newest calibration report, None when no report exists."""
    with common.use_root(root):
        d = common.ROOT / REPORTS_DIR
    files = sorted(d.glob("calibration_*.md")) if d.exists() else []
    for f in reversed(files):
        m = _RATINGS_LINE_RE.search(f.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    return None


def run(root: Path | None = None, write: bool = True, today: str | None = None) -> dict:
    res = compute(root, today=today)
    with common.use_root(root):
        if write:
            p = common.ROOT / REPORTS_DIR / f"calibration_{res['date']}.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(render_report(res), encoding="utf-8")
            res["report_path"] = common.rel(p)
        else:
            res["report_path"] = None
    res.pop("thresholds", None)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kappa, rho, per-tag false negatives and fix proposals from evals/calibration.jsonl.")
    ap.add_argument("--no-write", action="store_true", help="do not write evals/health/reports/calibration_<date>.md")
    ap.add_argument("--date", default=None, help="report date (default: today)")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    if args.date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        common.error("--date must be YYYY-MM-DD")
        return 0
    try:
        res = run(args.root, write=not args.no_write, today=args.date)
    except FileNotFoundError as e:
        common.error(str(e))
        return 0
    common.emit(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
