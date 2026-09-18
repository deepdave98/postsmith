#!/usr/bin/env python3
"""rate_record.py: record Deep's 1-5 rating for a variant or a corpus post (contracts §13, §17, §18).

    --kind generated --ref <run>:<key>   blind key A|B|C via drafts/<run>/final/blind.key.json; pass --blind
    --kind generated --ref <run>/<cid>   a variant by cid
    --kind corpus    --ref <post_id>     a train / self corpus post (heldout is never rated)
    --score 1-5 [--tags a,b] [--note "..."] [--blind] [--json]
    --list-rated --kind corpus|generated   -> {"ok", "kind", "ids": [...]}
    --proposals                            -> what is due: tag clusters (>= 3 ratings sharing a tag),
                                              user-tell candidates, and the calibrate.py result once
                                              config calibration.every_n_ratings new ratings have accrued
                                              since the last evals/health/reports/calibration_*.md

A generated rating appends one evals/calibration.jsonl row joined with the candidate's merged scores (judge
medians = jury median when a jury sat, else the judge score; tier0 soft flags; lineup pass; verdict; rubric
and profile versions; the assignment's move and lens). A candidate that never reached a merged file (Tier 0
hard fail) gets verdict "fail" from its tier0 JSON. A corpus rating appends corpus/ratings.jsonl
`{post_id, user_score, tags, ts}` and mirrors it into calibration.jsonl with kind corpus, blind by
construction. Tags outside the contract vocabulary are a user error. The row fields beyond §13 (run, cid,
blind_key, tier0_hard_fails, paraphrase, media_pass) are what calibrate.py needs to evaluate the copycat and
media tags.

CLI: uv run tools/rate_record.py --kind generated --ref 2026-09-17_agents:A --score 4 --blind
API: record(kind, ref, score, tags=(), note=None, blind=False, root=None) -> dict
     resolve_ref(kind, ref, root=None) -> {run, cid, platform, blind_key} | {post_id, platform, path}
     join_candidate(run, cid, root=None) -> the judge/tier0 join used in the row
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate  # noqa: E402
import common  # noqa: E402
import topics  # noqa: E402

TAGS: tuple[str, ...] = calibrate.TAGS
KINDS = ("generated", "corpus")
CALIBRATION_PATH = Path("evals") / "calibration.jsonl"
RATINGS_PATH = Path("corpus") / "ratings.jsonl"
_POST_ID_RE = re.compile(r"^[a-z][a-z0-9\-]*_\d{3,}$")
_KEY_RE = re.compile(r"^[A-Za-z]$")


# --------------------------------------------------------------------------- validation

def parse_tags(raw: str | list[str] | tuple[str, ...] | None) -> tuple[list[str], list[str]]:
    """(valid tags in input order, unknown tags). Accepts 'a,b' or a list."""
    if raw is None:
        return [], []
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    tags: list[str] = []
    unknown: list[str] = []
    for t in items:
        t = str(t).strip().lower().replace("-", "_").replace(" ", "_")
        if not t:
            continue
        if t in TAGS:
            if t not in tags:
                tags.append(t)
        else:
            unknown.append(t)
    return tags, unknown


def parse_score(score: int | str | None) -> int | None:
    try:
        s = int(str(score).strip())
    except (TypeError, ValueError):
        return None
    return s if 1 <= s <= 5 else None


# --------------------------------------------------------------------------- reference resolution

def _norm(text: str) -> str:
    return common.normalize_text(text or "")


def _blind_items(rd: Path) -> list[dict]:
    """The blind set, each item joined to its cid.

    `final/blind.json` carries `{key, platform, text}` only (contracts §18): a cid would name the round a
    text came from, and a round-2 cid is a rewrite of a candidate that failed. The mapping lives beside it
    in `final/blind.key.json`, which the deny globs keep out of every session. Older runs that still inline
    `cid` keep working, and so does the text-matching fallback in `_cid_for_blind_item`.
    """
    doc = common.read_json(rd / "final" / "blind.json", default=None)
    if not isinstance(doc, dict):
        return []
    items = [i for i in (doc.get("items") or doc.get("variants") or []) if isinstance(i, dict)]
    keydoc = common.read_json(rd / "final" / "blind.key.json", default=None)
    by_key: dict[str, dict] = {}
    if isinstance(keydoc, dict):
        for k in keydoc.get("items") or []:
            if isinstance(k, dict) and k.get("key"):
                by_key[str(k["key"]).upper()] = k
    out: list[dict] = []
    for i in items:
        mapped = by_key.get(str(i.get("key") or i.get("letter") or "").upper()) or {}
        merged = dict(i)
        for field in ("cid", "text_path"):
            if not merged.get(field) and mapped.get(field):
                merged[field] = mapped[field]
        out.append(merged)
    return out


def _cid_for_blind_item(rd: Path, item: dict, lineage: dict | None) -> str | None:
    """cid of a blind item: its own `cid`, else the candidate whose text or text_path matches."""
    cid = item.get("cid")
    if isinstance(cid, str) and cid:
        return cid
    text = item.get("text")
    tp = item.get("text_path")
    if isinstance(tp, str):
        stem = Path(tp).stem
        if known_cid(rd, stem, lineage):
            return stem
        p = Path(tp)
        p = p if p.is_absolute() else common.ROOT / p
        if not isinstance(text, str) and p.exists():
            text = p.read_text(encoding="utf-8")
    if not isinstance(text, str):
        return None
    want = _norm(text)
    seen: list[str] = []
    for r in reversed(topics.rounds(rd)):
        for p in sorted((r / "candidates").glob("*.txt")) if (r / "candidates").is_dir() else []:
            if p.stem in seen:
                continue
            seen.append(p.stem)
            if _norm(p.read_text(encoding="utf-8")) == want:
                return p.stem
    for v in (lineage or {}).get("variants", []):
        t = topics.candidate_text(rd, v["cid"], lineage)
        if t is not None and _norm(t) == want:
            return v["cid"]
    return None


def lineage_or_none(run: str) -> dict | None:
    try:
        return topics.lineage_info(run)
    except (FileNotFoundError, OSError, ValueError):
        return None


def known_cid(rd: Path, cid: str, lineage: dict | None) -> bool:
    if lineage and cid in lineage.get("_by_cid", {}):
        return True
    return any((r / "candidates" / f"{cid}.md").exists() or (r / "candidates" / f"{cid}.txt").exists()
               for r in topics.rounds(rd))


def resolve_ref(kind: str, ref: str, root: Path | None = None) -> dict:
    """Resolve a --ref. Generated: {ok, run, cid, platform, blind_key}. Corpus: {ok, post_id, platform,
    path, author}."""
    with common.use_root(root):
        ref = (ref or "").strip()
        if not ref:
            return {"ok": False, "error": "empty --ref"}
        if kind == "corpus":
            if not _POST_ID_RE.match(ref):
                return {"ok": False, "error": f"corpus ref must be a post id like acosta_017, got {ref!r}"}
            for split, d in (("train", "posts"), ("self", "self")):
                p = common.ROOT / "corpus" / d / f"{ref}.md"
                if p.exists():
                    meta, _ = common.split_front_matter(p.read_text(encoding="utf-8"))
                    meta = meta if isinstance(meta, dict) else {}
                    author = meta.get("author") if isinstance(meta.get("author"), dict) else {}
                    return {"ok": True, "post_id": ref, "platform": meta.get("platform"), "path": common.rel(p),
                            "split": split, "author": author.get("slug")}
            if (common.ROOT / "corpus" / "heldout" / f"{ref}.md").exists():
                return {"ok": False, "error": f"{ref} is a heldout post: heldout posts are never rated"}
            return {"ok": False, "error": f"no corpus post {ref} under corpus/posts or corpus/self"}
        # generated
        ref = ref.removeprefix("drafts/")
        blind_key: str | None = None
        if "/" in ref:
            run, cid = ref.split("/", 1)
        elif ":" in ref:
            run, key = ref.rsplit(":", 1)
            if not _KEY_RE.match(key):
                return {"ok": False, "error": f"blind key must be one letter, got {key!r} (use <run>:<A|B|C>)"}
            blind_key, cid = key.upper(), ""
        else:
            return {"ok": False, "error": "generated ref must be <run>/<cid> or <run>:<blind key>"}
        run = run.strip()
        rd = common.run_dir(run)
        if not rd.is_dir():
            return {"ok": False, "error": f"no run directory drafts/{run}"}
        lineage = lineage_or_none(run)
        if blind_key:
            items = _blind_items(rd)
            if not items:
                return {"ok": False, "error": f"drafts/{run}/final/blind.json is missing or empty; rate by <run>/<cid> instead"}
            item = next((i for i in items if str(i.get("key") or i.get("letter") or "").upper() == blind_key), None)
            if item is None:
                keys = [str(i.get("key") or i.get("letter") or "?") for i in items]
                return {"ok": False, "error": f"blind key {blind_key} not in final/blind.json (keys: {', '.join(keys)})"}
            cid = _cid_for_blind_item(rd, item, lineage) or ""
            if not cid:
                return {"ok": False, "error": f"blind key {blind_key} could not be mapped to a candidate of {run}"}
            platform = item.get("platform")
        else:
            cid = cid.strip()
            if not known_cid(rd, cid, lineage):
                return {"ok": False, "error": f"no candidate {cid} in run {run}"}
            platform = None
        v = (lineage or {}).get("_by_cid", {}).get(cid, {}) if lineage else {}
        meta = topics.candidate_meta(rd, cid)
        platform = platform or v.get("platform") or meta.get("platform") or topics.platform_from_cid(cid)
        return {"ok": True, "run": rd.name, "cid": cid, "platform": platform, "blind_key": blind_key}


# --------------------------------------------------------------------------- join with scores

def _merged_path(rd: Path, cid: str, lineage: dict | None) -> Path | None:
    v = (lineage or {}).get("_by_cid", {}).get(cid, {}) if lineage else {}
    sp = v.get("scores_path")
    if isinstance(sp, str) and sp:
        p = Path(sp)
        p = p if p.is_absolute() else common.ROOT / p
        if p.exists():
            return p
    for r in reversed(topics.rounds(rd)):
        p = r / "scores" / f"{cid}.merged.json"
        if p.exists():
            return p
    return None


def _tier0_path(rd: Path, cid: str) -> Path | None:
    for r in reversed(topics.rounds(rd)):
        p = r / "scores" / f"{cid}.tier0.json"
        if p.exists():
            return p
    return None


def judge_medians(merged: dict) -> dict[str, float]:
    """dimension -> the jury median when a jury sat, else the judge score. na and unscored dimensions are
    omitted."""
    out: dict[str, float] = {}
    for dim, row in (merged.get("tier1") or {}).items():
        if not isinstance(row, dict) or row.get("na"):
            continue
        jury = row.get("jury")
        val = None
        if isinstance(jury, dict) and isinstance(jury.get("median"), (int, float)):
            val = jury["median"]
        elif isinstance(row.get("score"), (int, float)):
            val = row["score"]
        if val is not None:
            out[dim] = int(val) if float(val).is_integer() else float(val)
    return out


def tier0_split(checks: dict) -> tuple[list[str], list[str]]:
    """(soft flags, hard fails): check ids that need action (common.check_needs_action), split by class.
    Advisory results never appear."""
    soft: list[str] = []
    hard: list[str] = []
    for check_id, res in sorted((checks or {}).items()):
        if not common.check_needs_action(res):
            continue
        cls = res.get("class")
        if cls == "hard":
            hard.append(check_id)
        elif cls in ("soft", "flag"):
            soft.append(check_id)
    return soft, hard


def join_candidate(run: str, cid: str, root: Path | None = None) -> dict:
    """Judge medians, tier0 flags, lineup / paraphrase / media results, verdict, versions, move and lens
    for one cid."""
    with common.use_root(root):
        rd = common.run_dir(run)
        lineage = lineage_or_none(run)
        meta = topics.candidate_meta(rd, cid)
        assignment = meta.get("assignment") if isinstance(meta.get("assignment"), dict) else {}
        if not assignment and lineage:
            assignment = (lineage.get("_by_cid", {}).get(cid) or {}).get("assignment") or {}
        out: dict = {"platform": meta.get("platform") or topics.platform_from_cid(cid), "judge_scores": {},
                     "tier0_soft_flags": [], "tier0_hard_fails": [], "lineup_pass": None, "paraphrase": None,
                     "media_pass": None, "verdict": None, "rubric_version": None, "profile_version": None,
                     "lexicon_version": None, "moves": [assignment["move"]] if assignment.get("move") else [],
                     "lens": assignment.get("lens") or None, "scores_path": None, "joined": False}
        mp = _merged_path(rd, cid, lineage)
        if mp is not None:
            merged = common.read_json(mp, default={}) or {}
            out["judge_scores"] = judge_medians(merged)
            out["tier0_soft_flags"], out["tier0_hard_fails"] = tier0_split(merged.get("tier0") or {})
            t2 = merged.get("tier2") or {}
            lu = t2.get("lineup") if isinstance(t2, dict) else None
            out["lineup_pass"] = bool(lu.get("pass")) if isinstance(lu, dict) and "pass" in lu else None
            para = t2.get("paraphrase") if isinstance(t2, dict) else None
            out["paraphrase"] = bool(para) if isinstance(para, bool) else (bool(para.get("paraphrase")) if isinstance(para, dict) and "paraphrase" in para else None)
            media = t2.get("media") if isinstance(t2, dict) else None
            out["media_pass"] = bool(media.get("pass")) if isinstance(media, dict) and "pass" in media else None
            out["verdict"] = (merged.get("verdict") or {}).get("status") if isinstance(merged.get("verdict"), dict) else merged.get("verdict")
            out["rubric_version"] = merged.get("rubric_version")
            out["profile_version"] = merged.get("profile_version")
            out["lexicon_version"] = merged.get("lexicon_version")
            out["platform"] = merged.get("platform") or out["platform"]
            out["scores_path"] = common.rel(mp)
            out["joined"] = True
        else:
            tp = _tier0_path(rd, cid)
            if tp is not None:
                t0 = common.read_json(tp, default={}) or {}
                out["tier0_soft_flags"], out["tier0_hard_fails"] = tier0_split(t0.get("checks") or {})
                out["verdict"] = "fail" if out["tier0_hard_fails"] else None
                out["profile_version"] = t0.get("profile_version")
                out["platform"] = t0.get("platform") or out["platform"]
                out["scores_path"] = common.rel(tp)
        if out["rubric_version"] is None:
            try:
                out["rubric_version"] = common.rubric_version()
            except (FileNotFoundError, OSError):
                out["rubric_version"] = None
        if out["profile_version"] is None:
            prof = common.load_profile()
            out["profile_version"] = prof.get("profile_version") if isinstance(prof, dict) else None
        return out


# --------------------------------------------------------------------------- recording

def _row_base(post_ref: str, kind: str, platform: str | None, score: int, tags: list[str], note: str | None,
              blind: bool) -> dict:
    return {"ts": common.now_iso(), "post_ref": post_ref, "kind": kind, "platform": platform, "user_score": score,
            "tags": tags, "note": note or None, "blind": bool(blind)}


def previous_ratings(post_ref: str, kind: str, root: Path | None = None) -> int:
    with common.use_root(root):
        rows = common.read_jsonl(common.ROOT / CALIBRATION_PATH)
    return sum(1 for r in rows if r.get("post_ref") == post_ref and r.get("kind", "generated") == kind
               and isinstance(r.get("user_score"), (int, float)))


def record(kind: str, ref: str, score: int | str, tags: str | list[str] | None = None, note: str | None = None,
           blind: bool = False, root: Path | None = None) -> dict:
    """Append the rating. Returns {ok, row, calibration_path[, ratings_path], previous_ratings}."""
    with common.use_root(root):
        if kind not in KINDS:
            return {"ok": False, "error": f"--kind must be one of {', '.join(KINDS)}"}
        s = parse_score(score)
        if s is None:
            return {"ok": False, "error": f"--score must be an integer 1-5, got {score!r}"}
        tag_list, unknown = parse_tags(tags)
        if unknown:
            return {"ok": False, "error": f"unknown tag(s) {', '.join(unknown)}; vocabulary: {', '.join(TAGS)}"}
        res = resolve_ref(kind, ref)
        if not res.get("ok"):
            return res
        if kind == "corpus":
            post_ref = res["post_id"]
            ratings_row = {"post_id": post_ref, "user_score": s, "tags": tag_list, "ts": common.now_iso()}
            if note:
                ratings_row["note"] = note
            common.append_jsonl(common.ROOT / RATINGS_PATH, ratings_row)
            row = _row_base(post_ref, "corpus", res.get("platform"), s, tag_list, note, True)
            row.update({"judge_scores": {}, "tier0_soft_flags": [], "lineup_pass": None, "verdict": None,
                        "rubric_version": _rubric_or_none(), "profile_version": _profile_or_none(), "moves": [],
                        "lens": res.get("author"), "edit_ops": [], "split": res.get("split")})
            prev = previous_ratings(post_ref, "corpus")
            common.append_jsonl(common.ROOT / CALIBRATION_PATH, row)
            return {"ok": True, "kind": "corpus", "row": row, "ratings_row": ratings_row,
                    "ratings_path": common.rel(common.ROOT / RATINGS_PATH),
                    "calibration_path": common.rel(common.ROOT / CALIBRATION_PATH), "previous_ratings": prev}
        run, cid = res["run"], res["cid"]
        post_ref = f"{run}/{cid}"
        joined = join_candidate(run, cid)
        row = _row_base(post_ref, "generated", res.get("platform") or joined["platform"], s, tag_list, note, blind)
        row.update({"judge_scores": joined["judge_scores"], "tier0_soft_flags": joined["tier0_soft_flags"],
                    "lineup_pass": joined["lineup_pass"], "verdict": joined["verdict"],
                    "rubric_version": joined["rubric_version"], "profile_version": joined["profile_version"],
                    "moves": joined["moves"], "lens": joined["lens"], "edit_ops": [],
                    "run": run, "cid": cid, "blind_key": res.get("blind_key"),
                    "tier0_hard_fails": joined["tier0_hard_fails"], "paraphrase": joined["paraphrase"],
                    "media_pass": joined["media_pass"]})
        prev = previous_ratings(post_ref, "generated")
        common.append_jsonl(common.ROOT / CALIBRATION_PATH, row)
        warnings = [] if joined["joined"] else ["no merged scores for this candidate; judge fields are empty"]
        return {"ok": True, "kind": "generated", "row": row, "calibration_path": common.rel(common.ROOT / CALIBRATION_PATH),
                "previous_ratings": prev, "scores_path": joined["scores_path"], "warnings": warnings}


def _rubric_or_none() -> str | None:
    try:
        return common.rubric_version()
    except (FileNotFoundError, OSError):
        return None


def _profile_or_none() -> int | None:
    prof = common.load_profile()
    return prof.get("profile_version") if isinstance(prof, dict) else None


# --------------------------------------------------------------------------- list / proposals

def list_rated(kind: str, root: Path | None = None) -> dict:
    with common.use_root(root):
        if kind not in KINDS:
            return {"ok": False, "error": f"--kind must be one of {', '.join(KINDS)}"}
        if kind == "corpus":
            ids = {str(r.get("post_id")) for r in common.read_jsonl(common.ROOT / RATINGS_PATH) if r.get("post_id")}
            ids |= {str(r.get("post_ref")) for r in common.read_jsonl(common.ROOT / CALIBRATION_PATH)
                    if r.get("kind") == "corpus" and r.get("post_ref")}
        else:
            ids = {str(r.get("post_ref")) for r in common.read_jsonl(common.ROOT / CALIBRATION_PATH)
                   if r.get("kind", "generated") == "generated" and r.get("post_ref")
                   and isinstance(r.get("user_score"), (int, float))}
        return {"ok": True, "kind": kind, "ids": sorted(ids)}


def tag_clusters(rows: list[dict], min_n: int = 3) -> list[dict]:
    """Tags shared by >= min_n rated rows, with refs and notes. This is the input to a lesson."""
    out: list[dict] = []
    for tag in TAGS:
        hits = [r for r in rows if tag in (r.get("tags") or []) and isinstance(r.get("user_score"), (int, float))]
        if len(hits) >= min_n:
            out.append({"tag": tag, "n": len(hits), "refs": [str(r.get("post_ref")) for r in hits],
                        "notes": [str(r["note"]) for r in hits if r.get("note")],
                        "runs": sorted({str(r.get("run") or str(r.get("post_ref")).split("/")[0]) for r in hits})})
    return out


def proposals(root: Path | None = None) -> dict:
    with common.use_root(root):
        rt = common.ROOT
        cfg = common.load_config() if (rt / "config" / "postsmith.yaml").exists() else {}
        every_n = int((cfg.get("calibration") or {}).get("every_n_ratings", 20))
        rows = [r for r in common.read_jsonl(rt / CALIBRATION_PATH) if isinstance(r.get("user_score"), (int, float))]
        gen = [r for r in rows if r.get("kind", "generated") == "generated"]
        last = calibrate.last_report_total()
        since = len(rows) - (last or 0)
        due = every_n > 0 and since >= every_n
        known = calibrate.lexicon_user_tells(rt)
        tells = [{"tag": t, "phrase": str(r["note"]), "post_ref": str(r.get("post_ref")), "source": f"rate:{calibrate.cid_of(r)}"}
                 for r in gen for t in calibrate.USER_TELL_TAGS
                 if t in (r.get("tags") or []) and r.get("note") and str(r["note"]).strip().lower() not in known]
        res = {"ok": True, "ratings_total": len(rows), "since_last_calibration": since,
               "last_calibration_total": last, "every_n": every_n, "due": due,
               "tag_clusters": tag_clusters(gen), "user_tell_candidates": tells, "calibration": None,
               "next_step": None}
        if due:
            cal = calibrate.compute()
            cal.pop("thresholds", None)
            res["calibration"] = cal
            res["next_step"] = "run `uv run tools/calibrate.py --json` to write the report and reset the counter"
        return res


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record a 1-5 rating (generated variant or corpus post) into the label stores.")
    ap.add_argument("--kind", choices=KINDS, default=None, help="generated | corpus")
    ap.add_argument("--ref", default=None, help="<run>/<cid> | <run>:<blind key> | <post_id>")
    ap.add_argument("--score", default=None, help="1-5")
    ap.add_argument("--tags", default=None, help="comma-separated tags from the contract vocabulary")
    ap.add_argument("--note", default=None, help="free text (a cited phrase for sounds_ai / not_me)")
    ap.add_argument("--blind", action="store_true", help="the rating was taken before any verdict was shown")
    ap.add_argument("--list-rated", action="store_true", help="print the rated ids for --kind")
    ap.add_argument("--proposals", action="store_true", help="print what is due: tag clusters, user tells, calibration")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        if args.list_rated:
            if not args.kind:
                common.error("--list-rated needs --kind corpus|generated")
                return 0
            common.emit(list_rated(args.kind, args.root))
            return 0
        if args.proposals:
            common.emit(proposals(args.root))
            return 0
        if not args.kind or not args.ref or args.score is None:
            common.error("--kind, --ref and --score are required (or use --list-rated / --proposals)")
            return 0
        common.emit(record(args.kind, args.ref, args.score, tags=args.tags, note=args.note, blind=args.blind,
                           root=args.root))
    except FileNotFoundError as e:
        common.error(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
