#!/usr/bin/env python3
"""Merge Tier 0 / Tier 1 / jury / Tier 2 results into <cid>.merged.json and write feedback packets
(contracts §7, §16).

Rules implemented here (thresholds come from evals/rubric/<v>/thresholds.yaml, never hard-coded):
  * pass = all hard gates pass and all soft dimensions >= threshold after any jury and no unaddressed flags
    (unless waived) and (Tier 2 ran -> lineup pass, paraphrase false, no wrong claim, media pass);
  * jury triggers: soft score == threshold-1; hard judged score == hard_trigger_score; any hold; a failing
    known-false-positive Tier 0 check; an O3 flag. Jury size is capped by thresholds.jury.size;
  * rerun / na / hold bookkeeping from judge_io validation results supplied by the caller: a rejected
    dimension is rerun once with the alternate lens; a second rejection makes a soft dimension na
    (counted as na_by_rejection) and a hard dimension hold; a hard-gate na is rerun once, then hold;
    hold -> jury of fresh judges -> no valid vote -> unscored -> needs_your_call;
  * base-rate downgrades are applied by ai_tells; this module only reads the recorded class;
  * flags must be addressed (rewrite, jury, pairwise answer) or waived with --waive; a check that passed its
    gate but raised a flag (platform_check's P2_fold: pass true, flag true) is a flag like any other;
  * a judge-declared na on a dimension without an na_when / na_allowed rule counts toward the same cap as
    na-by-rejection (config judges.max_na_by_rejection_before_needs_call) -> needs_your_call;
  * judge files are bound to their names (lens from the filename, requested output paths from state.json);
  * stop conditions across consecutive rounds: oscillation (same dimension fails in k and k+1 with
    contradictory suggested_fix, or a hard gate that passed in k fails in k+1), regression (a hard gate
    passed-then-failed twice across rounds -> drop), overlap_persistent (O1/O5 flag surviving two rewrites).

CLI:
  aggregate.py merge <run> <cid> --round k [--waive P2_fold ...] [--tier2 path] [--previous path] [--no-write]
  aggregate.py feedback <run> <cid> --round k [--no-write]
  aggregate.py rank <run> --round k
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import judge_io  # noqa: E402

SCHEMA = "postsmith.scores/2"
FEEDBACK_SCHEMA = "postsmith.feedback/1"
JUDGED_LENSES = ("reader", "voice", "comedy", "persona")
INSTRUCTION = ("Fix these, keep everything that passed; do not change the move or the claims unless "
               "uniqueness or persona_fit failed.")
WHOLE = judge_io.WHOLE_FILE

# light stemming for the opposite-direction keyword pairs in thresholds.stop.oscillation.conflict_keywords
_KEYWORD_RE: dict[str, str] = {
    "shorter": r"\bshort(?:er|en|ened|ening)?\b|\btighten\b|\btrim\b",
    "longer": r"\blong(?:er)?\b|\blengthen\b|\bexpand\b|\bextend\b",
    "cut": r"\bcut(?:s|ting)?\b|\bdelete\b|\bdrop\b",
    "add": r"\badd(?:s|ed|ing)?\b|\binsert\b",
    "remove": r"\bremov(?:e|es|ed|ing)\b|\bstrip\b",
    "keep": r"\bkeep(?:s|ing)?\b|\bretain\b|\bleave\b",
    "more": r"\bmore\b",
    "less": r"\bless\b|\bfewer\b",
}


# --------------------------------------------------------------------------- small helpers

def _entry(e: Any) -> dict:
    """Normalize a judge/jury file entry to {"path", "lens", "data", "validation"}."""
    if isinstance(e, dict) and "data" in e:
        out = dict(e)
    elif isinstance(e, dict) and "dimensions" in e:
        out = {"data": e}
    else:
        out = {"data": e if isinstance(e, dict) else {}}
    out.setdefault("path", None)
    data = out.get("data") or {}
    out.setdefault("lens", data.get("lens"))
    out.setdefault("validation", None)
    out["scoring_lens"] = data.get("rerun_for") or out.get("lens")
    out["is_rerun"] = bool(data.get("rerun_for")) or bool(out.get("rerun"))
    return out


def _rejected_dims(val: dict | None) -> tuple[bool, dict[str, str]]:
    """(whole_file_rejected, {dimension: reason})."""
    if not val:
        return False, {}
    whole = False
    dims: dict[str, str] = {}
    for r in val.get("rejected") or []:
        d = r.get("dimension")
        if d in (None, WHOLE):
            whole = True
        else:
            dims[d] = r.get("reason", "rejected")
    return whole, dims


def _dims_of(e: dict) -> dict:
    """Accepted (normalized) dimensions when validation ran, else the raw ones."""
    val = e.get("validation")
    if val and isinstance(val.get("normalized"), dict) and isinstance(val["normalized"].get("dimensions"), dict):
        return val["normalized"]["dimensions"]
    return (e.get("data") or {}).get("dimensions") or {}


def _raw_dims(e: dict) -> dict:
    return (e.get("data") or {}).get("dimensions") or {}


def _median_int(votes: list[int]) -> float | None:
    return common.median([float(v) for v in votes])


def _rubric_sha() -> str | None:
    try:
        d = common.rubric_dir()
    except FileNotFoundError:
        return None
    h = hashlib.sha256()
    found = False
    for name in ("rubric.md", "thresholds.yaml", "patterns.yaml"):
        p = d / name
        if p.exists():
            h.update(name.encode()); h.update(p.read_bytes()); found = True
    return h.hexdigest() if found else None


def fixes_conflict(fix_a: str | None, fix_b: str | None, pairs: list[list[str]] | None = None) -> bool:
    """True when two suggested_fix strings pull in opposite directions (shorter/longer, cut/add, ...)."""
    if not fix_a or not fix_b:
        return False
    pairs = pairs or [["shorter", "longer"], ["cut", "add"], ["remove", "keep"], ["more", "less"]]
    a, b = fix_a.lower(), fix_b.lower()

    def has(word: str, s: str) -> bool:
        return re.search(_KEYWORD_RE.get(word, rf"\b{re.escape(word)}\b"), s) is not None

    for x, y in pairs:
        if (has(x, a) and has(y, b) and not has(x, b)) or (has(y, a) and has(x, b) and not has(y, b)):
            return True
    return False


# --------------------------------------------------------------------------- jury bookkeeping

def _jury_votes(dim: str, jury_entries: list[dict], cap: int) -> dict:
    """Collect jury votes on `dim` from jury files (accepted, non-na scores only)."""
    files_with_dim: list[dict] = []
    votes: list[int] = []
    lenses: list[str] = []
    files: list[str | None] = []
    rejected = 0
    for e in jury_entries:
        if dim not in _raw_dims(e):
            continue
        files_with_dim.append(e)
        whole, rej = _rejected_dims(e.get("validation"))
        if whole or dim in rej:
            rejected += 1
            continue
        d = _dims_of(e).get(dim) or {}
        if d.get("na") or not isinstance(d.get("score"), int):
            rejected += 1
            continue
        if len(votes) >= cap:
            continue
        votes.append(int(d["score"]))
        lenses.append(str(e.get("lens")))
        files.append(e.get("path"))
    return {"n_files": len(files_with_dim), "votes": votes, "lenses": lenses, "files": files, "rejected": rejected}


def _jury_block(original: int | None, jv: dict, threshold: float) -> dict:
    votes = ([original] if original is not None else []) + jv["votes"]
    lenses = (["original"] if original is not None else []) + jv["lenses"]
    med = _median_int(votes) if votes else None
    split = (max(votes) - min(votes)) if votes else 0
    return {"votes": votes, "median": med, "lenses": lenses, "files": jv["files"], "rejected_votes": jv["rejected"],
            "split": split, "pass": (med is not None and med >= threshold)}


# --------------------------------------------------------------------------- merge

def merge(run: str, cid: str, round_k: int, tier0: dict, judge_files: list[dict], jury_files: list[dict],
          tier2: dict | None, previous_merged: dict | None, thresholds: dict, cfg: dict, profile: dict | None,
          waived: set[str] | None = None) -> dict:
    """Build the §7 merged document. Pure: reads nothing from disk."""
    waived = set(waived or set())
    dim_specs: dict[str, dict] = thresholds.get("dimensions") or {}
    lens_map: dict[str, list[str]] = dict(thresholds.get("lenses") or {})
    if not lens_map:  # derive the lens -> dimensions map from dimensions[*].lens
        for dim, spec in dim_specs.items():
            ln = (spec or {}).get("lens") if isinstance(spec, dict) else None
            if ln:
                lens_map.setdefault(str(ln), []).append(dim)
    if not any(lens_map.get(ln) for ln in JUDGED_LENSES):
        raise ValueError("thresholds.yaml defines no judged dimensions (no `lenses` map and no dimensions[*].lens); "
                         "refusing to merge into a verdict that could only pass")
    check_specs: dict[str, dict] = thresholds.get("checks") or {}
    jcfg: dict = thresholds.get("jury") or {}
    rcfg: dict = thresholds.get("rerun") or {}
    scfg: dict = thresholds.get("stop") or {}
    jury_size = int(jcfg.get("size", 3))
    hard_trigger = int(jcfg.get("hard_trigger_score", 3))
    kfp_checks = set(jcfg.get("known_false_positive_checks") or [])
    override_thr = float(jcfg.get("override_threshold", 4))
    rotation: dict[str, list[str]] = jcfg.get("rotation") or {}
    max_rej = int(rcfg.get("max_rejections_before_na", 2))
    max_na_rej = int((cfg.get("judges") or {}).get("max_na_by_rejection_before_needs_call",
                                                    rcfg.get("max_na_by_rejection_before_needs_call", 2)))
    expected_na = set(tier0.get("expected_na") or []) | {w for w in waived if w in dim_specs}
    lens_free = ("lens" in tier0) and tier0.get("lens") is None
    platform = tier0.get("platform")

    judge_entries = [_entry(e) for e in (judge_files or [])]
    jury_entries = [_entry(e) for e in (jury_files or [])]
    jury_requests: list[dict] = []
    rejected_log: list[dict] = []
    na_by_rejection: list[str] = []
    holds: list[str] = []
    disagreements: list[dict] = []

    # the Tier 2 "same post rewritten?" answer (from paraphrase or any pairwise judge) clears or confirms an O3 flag
    same_post: bool | None = None
    if tier2:
        for key in ("paraphrase", "pairwise"):
            blk = tier2.get(key)
            if isinstance(blk, dict) and blk.get("same_post_rewritten") is not None:
                same_post = bool(blk["same_post_rewritten"]) if same_post is not True else True

    # ---------------------------------------------------------------- Tier 0
    t0_in: dict[str, dict] = tier0.get("checks") or {}
    t0_out: dict[str, dict] = {}
    t0_hard: list[str] = []
    t0_soft: list[str] = []
    t0_flags: list[str] = []
    t0_adv: list[str] = []
    waived_applied: list[str] = []
    for chk, res in t0_in.items():
        r = dict(res) if isinstance(res, dict) else {"class": "advisory", "pass": True}
        cls = r.get("class", "advisory")
        if not common.check_needs_action(r):
            t0_out[chk] = r
            continue
        # platform_check's P2_fold shape: the hard gate passed but a flag was raised (must be addressed or waived)
        raised_flag = bool(r.get("pass", True)) and bool(r.get("flag"))
        # Tier 0 juries: a known-false-positive hit only when the module says a jury may override it (a lexicon-only
        # or heuristic-only P8/P12 hit goes to the feedback packet instead), and an O3 skeleton flag
        allowed = r.get("jury_override_allowed")
        if allowed is None:
            allowed = chk in kfp_checks
        needs_jury = (bool(allowed) and chk in kfp_checks and cls in ("hard", "soft", "flag") and not raised_flag) or \
                     (chk == "O3_skeleton" and cls == "flag" and bool(jcfg.get("o3_flag_triggers_jury", True)))
        if chk == "O3_skeleton" and same_post is not None:
            needs_jury = False
            if same_post is False:
                r["cleared_by"] = "pairwise:same_post_rewritten=false"
                r["addressed"] = True
        if needs_jury:
            jv = _jury_votes(chk, jury_entries, jury_size)
            req = {"dimension": chk, "check": chk, "reason": "known_false_positive" if chk in kfp_checks else "o3_flag",
                   "lenses": ["voice", "reader", "comedy"][:jury_size], "size": jury_size, "needs": jury_size,
                   "question": ("Is this regex hit a genuine tell (1) or a false positive the writer meant (5)?"
                                if chk in kfp_checks else "Is this the same post rewritten (1) or its own post (5)?"),
                   "met": jv["n_files"] >= jury_size}
            if jv["n_files"] >= jury_size:
                if jv["votes"]:
                    blk = _jury_block(None, jv, override_thr)
                    r["jury"] = blk
                    if blk["split"] >= int(jcfg.get("split_logged_at", 2)):
                        disagreements.append({"kind": "jury_split", "dimension_or_check": chk, "detail": blk})
                    if blk["pass"]:
                        r["pass"] = True
                        r["jury_override"] = True
                        r["addressed"] = True
                    else:
                        r["jury_confirmed"] = True
                else:
                    r["jury"] = {"votes": [], "note": "all jury votes rejected or na; check stands"}
            jury_requests.append(req)
        if chk in waived and cls in ("flag", "soft"):
            r["waived"] = True
            waived_applied.append(chk)
        t0_out[chk] = r
        if r.get("addressed") or r.get("waived") or (r.get("pass") and not raised_flag):
            continue
        if cls == "hard":
            t0_hard.append(chk)
        elif cls == "soft":
            t0_soft.append(chk)
        elif cls == "flag":
            t0_flags.append(chk)
        else:
            t0_adv.append(chk)

    # ---------------------------------------------------------------- Tier 1
    by_lens: dict[str, list[dict]] = {}
    for e in judge_entries:
        by_lens.setdefault(str(e.get("scoring_lens")), []).append(e)
    for ln, lst in by_lens.items():
        canonical = f"{cid}.{ln}.json"
        lst.sort(key=lambda e: (e["is_rerun"], str(e.get("path") or "").split("/")[-1] != canonical, str(e.get("path") or "")))
    for e in judge_entries:  # file-level rejections are logged once per file
        whole, rej = _rejected_dims(e.get("validation"))
        plan = judge_io.rerun_plan((e.get("validation") or {}).get("rejected") or [], str(e.get("scoring_lens")), thresholds)
        if whole:
            rejected_log.append({"file": e.get("path"), "dimension": WHOLE, "kind": "validation",
                                 "reason": "; ".join(r.get("reason", "") for r in (e["validation"].get("rejected") or [])),
                                 "rerun_lens": plan["rerun_lens"], "rerun_dimensions": plan["dimensions"]})
        for d, reason in rej.items():
            rejected_log.append({"file": e.get("path"), "dimension": d, "kind": "validation", "reason": reason,
                                 "rerun_lens": plan["rerun_lens"]})

    tier1: dict[str, dict] = {}
    claims_rows: list[dict] | None = None
    t1_hard: list[str] = []
    t1_soft: list[str] = []
    advisory_scores: dict[str, Any] = {}
    pending: list[str] = []
    unscored: list[str] = []
    na_declared: list[str] = []
    needs_confirmation: list[dict] = []

    def legit_na(spec: dict) -> bool:
        return bool(spec.get("na_when")) or bool(spec.get("na_allowed"))

    # A hard Tier 0 fail is terminal: run_next spawns judges only for a candidate that passed the hard
    # checks (contracts section 8), so a hard fail with no judge file means Tier 1 was never asked for.
    # Those dimensions are "not run", not "pending" (pending would stall the candidate here for ever).
    # The feedback packet comes from the Tier 0 spans instead.
    judges_skipped = bool(t0_hard) and not judge_entries and not jury_entries

    for lens in (JUDGED_LENSES if not judges_skipped else []):
        entries = by_lens.get(lens, [])
        for dim in lens_map.get(lens, []):
            spec = dim_specs.get(dim) or {}
            cls = spec.get("class", "soft")
            thr = float(spec.get("threshold", 4))
            accepted: tuple[dict, dict] | None = None
            n_rej = 0
            n_na_hard = 0
            for e in entries:
                present = dim in _raw_dims(e)
                whole, rej = _rejected_dims(e.get("validation"))
                if not present and dim not in rej and not whole and not e["is_rerun"]:
                    continue
                if not present and not whole and dim not in rej:
                    # a rerun file that dropped the dimension it was asked for counts as a second rejection
                    n_rej += 1
                    rejected_log.append({"file": e.get("path"), "dimension": dim, "kind": "validation",
                                         "reason": "dimension missing from rerun output", "rerun_lens": None})
                    continue
                if whole or dim in rej:
                    n_rej += 1
                    continue
                d = _dims_of(e).get(dim)
                if d is None:
                    n_rej += 1
                    continue
                if cls == "hard" and d.get("na") and dim not in expected_na:
                    n_na_hard += 1
                    n_rej += 1
                    plan = judge_io.rerun_plan([{"dimension": dim, "reason": "hard-gate na"}], lens, thresholds)
                    rejected_log.append({"file": e.get("path"), "dimension": dim, "kind": "na",
                                         "reason": "hard-gate na (needs a scored judgement)", "rerun_lens": plan["rerun_lens"]})
                    continue
                accepted = (e, d)
                break

            row: dict[str, Any] = {"judge": f"judge-{lens}", "class": cls, "threshold": spec.get("threshold"),
                                   "score": None, "na": False, "evidence": [], "suggested_fix": None, "jury": None,
                                   "result": "unscored", "needs_confirmation": [], "rejections": n_rej}
            if dim == "claims":
                row["class"] = "special"
                if accepted is None:
                    row["result"] = "na" if (n_rej == 0 and dim in expected_na) else ("unscored" if n_rej == 0 else "na")
                    if n_rej == 0 and not entries:
                        row["note"] = "no judgement"
                else:
                    _e, d = accepted
                    row["na"] = bool(d.get("na"))
                    rows = list(d.get("claims") or [])
                    row["claims"] = rows
                    claims_rows = rows
                    row["result"] = "na" if row["na"] else ("fail" if any(c.get("status") == "wrong" for c in rows) else "pass")
                    if row["na"] and dim not in expected_na:
                        row["na_declared"] = True
                        na_declared.append(dim)
                tier1[dim] = row
                continue

            if accepted is None:
                if lens_free and (spec.get("na_when") or {}).get("lens_free_writer") and n_rej == 0:
                    row.update({"na": True, "result": "na", "note": "lens-free writer"})
                elif n_rej == 0:
                    row["result"] = "unscored"
                    row["note"] = "no judgement"
                    if cls in ("hard", "soft"):
                        pending.append(f"judge-{lens}:{dim}")
                elif n_rej >= max_rej:
                    if cls == "hard":
                        row["result"] = "hold"
                        row["note"] = "hard gate: rejected/na twice -> hold -> jury"
                        holds.append(dim)
                    else:
                        row.update({"na": True, "result": "na", "note": "na by rejection"})
                        na_by_rejection.append(dim)
                else:
                    row["result"] = "unscored"
                    row["note"] = "rejected once; rerun with the alternate lens pending"
                    if cls in ("hard", "soft"):
                        pending.append(f"rerun:{dim}")
            else:
                e, d = accepted
                row["judge"] = f"judge-{e.get('lens') or lens}"
                row["evidence"] = d.get("evidence") or []
                row["suggested_fix"] = d.get("suggested_fix")
                row["pre_step"] = d.get("pre_step")
                row["violations"] = d.get("violations") or []
                row["needs_confirmation"] = d.get("needs_confirmation") or []
                if d.get("contradicts") is not None:
                    row["contradicts"] = d.get("contradicts")
                if d.get("na"):
                    row.update({"na": True, "result": "na"})
                    if dim not in expected_na and not legit_na(spec):
                        row["na_declared"] = True
                        na_declared.append(dim)
                elif lens_free and (spec.get("na_when") or {}).get("lens_free_writer"):
                    row.update({"na": True, "result": "na", "note": "lens-free writer: dimension not applicable",
                                "score_ignored": d.get("score")})
                else:
                    score = int(d["score"])
                    row["score"] = score
                    if cls == "advisory":
                        row["result"] = "pass" if score >= thr else "fail"
                        advisory_scores[dim] = score
                    elif cls == "hard":
                        row["result"] = "pass" if score >= thr else "fail"
                        if score == hard_trigger:
                            row["jury_reason"] = f"hard_score_{hard_trigger}"
                    else:
                        row["result"] = "pass" if score >= thr else "fail"
                        if score == thr - 1:
                            row["jury_reason"] = "threshold-1"

            # hold -> jury of fresh judges
            if row["result"] == "hold":
                row["jury_reason"] = "hold"

            if row.get("jury_reason"):
                fresh = jury_size if row["result"] == "hold" else jury_size - 1
                lenses = list(rotation.get(lens, [x for x in JUDGED_LENSES[:3] if x != lens]))
                if row["result"] == "hold":
                    lenses = ([lens] + lenses)[:jury_size]
                jv = _jury_votes(dim, jury_entries, fresh)
                met = jv["n_files"] >= fresh
                jury_requests.append({"dimension": dim, "reason": row["jury_reason"], "lenses": lenses[:fresh],
                                      "size": jury_size, "needs": fresh, "score": row["score"], "threshold": thr, "met": met})
                if met:
                    if jv["votes"]:
                        blk = _jury_block(row["score"] if row["result"] != "hold" else None, jv, thr)
                        row["jury"] = blk
                        row["result"] = "pass" if blk["pass"] else "fail"
                        if blk["split"] >= int(jcfg.get("split_logged_at", 2)):
                            disagreements.append({"kind": "jury_split", "dimension_or_check": dim, "detail": blk})
                    elif row["result"] == "hold":
                        row["jury"] = {"votes": [], "note": "hold survived the jury without evidence"}
                        row["result"] = "unscored"
                        unscored.append(dim)
                    else:
                        row["jury"] = {"votes": [row["score"]], "median": row["score"], "lenses": ["original"],
                                       "note": "jury votes rejected or na; original judgement stands"}
                else:
                    pending.append(f"jury:{dim}")
                    if row["result"] != "hold":
                        row["jury_pending"] = True

            if row["result"] == "fail":
                (t1_hard if cls == "hard" else t1_soft if cls == "soft" else []).append(dim)
            if row["needs_confirmation"]:
                needs_confirmation.extend({"claim": x.get("claim"), "source": x.get("source"), "from": dim}
                                          for x in row["needs_confirmation"] if isinstance(x, dict))
            tier1[dim] = row

    # ---------------------------------------------------------------- Tier 2
    t2_hard: list[str] = []
    t2_block: dict[str, Any] = {"ran": bool(tier2), "lineup": None, "paraphrase": None, "pairwise": None,
                                "claims": None, "media": None}
    if tier2:
        lu = tier2.get("lineup")
        if isinstance(lu, dict):
            lu = dict(lu)
            if "pass" not in lu:
                picks = lu.get("picks") or []
                pick_hi = sum(1 for p in picks if p.get("picked_candidate") and int(p.get("confidence", 0)) >=
                              int((thresholds.get("lineup") or {}).get("fail_if_picks_at_confidence", {}).get("confidence", 4)))
                all_pick = bool(picks) and all(p.get("picked_candidate") for p in picks)
                lu["pass"] = not (pick_hi >= int((thresholds.get("lineup") or {}).get("fail_if_picks_at_confidence", {}).get("picks", 2))
                                  or all_pick)
            t2_block["lineup"] = lu
            if lu.get("pass") is False and not lu.get("advisory"):
                t2_hard.append("lineup")
        pw = tier2.get("pairwise")
        pp = tier2.get("paraphrase")
        para = dict(pp) if isinstance(pp, dict) else {}
        if isinstance(pw, dict):
            pw = dict(pw)
            for key in ("same_post_rewritten", "same_skeleton_or_joke"):
                if pw.get(key) is True:
                    para[key] = True
                elif key not in para and pw.get(key) is not None:
                    para[key] = pw.get(key)
            if "pass" not in pw:
                better = pw.get("better") or {}
                pw["pass"] = not (int(better.get("wins", 0)) == 0 and int(better.get("ties", 0)) == 0 and better)
            t2_block["pairwise"] = pw
            mode = pw.get("mode", "reference")
            if pw.get("pass") is False and mode == "exemplars":
                t2_hard.append("pairwise")
        if para or pp is not None:
            para["pass"] = not (para.get("same_post_rewritten") is True or para.get("same_skeleton_or_joke") is True)
            t2_block["paraphrase"] = para
            if not para["pass"]:
                t2_hard.append("paraphrase")
        if isinstance(tier2.get("claims"), list):
            claims_rows = list(tier2["claims"])
        md = tier2.get("media")
        if isinstance(md, dict):
            md = dict(md)
            fails = [k for k in ("media_check", "media_judge") if md.get(k) == "fail"]
            md["pass"] = not fails
            t2_block["media"] = md
            if fails:
                t2_hard.append("media")
    if claims_rows is not None:
        t2_block["claims"] = claims_rows
        if any(c.get("status") == "wrong" for c in claims_rows):
            t2_hard.append("claims")
        nc_status = (dim_specs.get("claims") or {}).get("needs_confirmation_status", "unverifiable")
        needs_confirmation.extend({"claim": c.get("text"), "source": c.get("source"), "from": "claims"}
                                  for c in claims_rows if c.get("status") == nc_status)

    # ---------------------------------------------------------------- verdict
    non_solo = {k for k, v in check_specs.items() if v.get("solo_fail") is False}
    all_gating = set(t0_hard) | set(t0_soft) | set(t0_flags) | set(t1_hard) | set(t1_soft) | set(t2_hard)
    if all_gating and all_gating <= non_solo:
        for chk in list(all_gating):
            t0_out[chk]["solo_fail_demoted"] = True
            t0_adv.append(chk)
            for lst in (t0_hard, t0_soft, t0_flags):
                if chk in lst:
                    lst.remove(chk)

    hard_fails = t0_hard + t1_hard + t2_hard
    soft_fails = t0_soft + t1_soft
    flags = list(t0_flags)
    unmet = [r for r in jury_requests if not r.get("met")]
    persona_only = (set(hard_fails) | set(soft_fails) | set(flags)) <= {"persona_fit"} and bool(needs_confirmation) \
        and ("persona_fit" in hard_fails)
    if unmet or pending:
        status = "hold"
    elif unscored or len(na_by_rejection) + len(na_declared) >= max_na_rej:
        status = "needs_your_call"
    elif not hard_fails and not soft_fails and not flags:
        status = "pass"
    elif persona_only:
        status = "needs_your_call"
    else:
        status = "fail"
    verdict = {"status": status, "hard_fails": hard_fails, "soft_fails": soft_fails, "flags": flags,
               "unscored": unscored, "advisory": {**advisory_scores, "tier0": t0_adv},
               "waived": waived_applied, "needs_confirmation": needs_confirmation,
               "waiting_on": sorted(set(pending) | {f"jury:{r['dimension']}" for r in unmet}),
               "tier2_tested": bool(tier2), "na_by_rejection": na_by_rejection, "na_declared": na_declared}

    # ---------------------------------------------------------------- stop conditions (consecutive rounds)
    prev = previous_merged or {}
    counters = json.loads(json.dumps(prev.get("counters") or {}))
    reg_events: list[dict] = list(counters.get("regression_events") or [])
    streak: dict[str, int] = dict(counters.get("overlap_streak") or {})
    stops: list[dict] = []
    ocfg = scfg.get("oscillation") or {}
    pairs = ocfg.get("conflict_keywords") or None
    reg_limit = int((scfg.get("regression") or {}).get("hard_gate_pass_then_fail_events", 2))
    ov = scfg.get("overlap_persistent") or {}
    ov_checks = ov.get("checks") or ["O1_ngram", "O5_published"]
    ov_needed = int(ov.get("rewrites", 2)) + 1

    # a hard gate whose jury has not voted yet is not a fail yet, and a previous pass granted by a jury override
    # (the jury cleared the very line the writer was told to keep) is not a pass the rewrite can regress from
    unmet_dims = {str(r.get("dimension")) for r in jury_requests if not r.get("met")}
    hard_now = (set(t0_hard) | set(t1_hard)) - unmet_dims
    if prev:
        prev_t0 = prev.get("tier0") or {}
        prev_t1 = prev.get("tier1") or {}
        prev_pass_hard = {k for k, v in prev_t0.items() if isinstance(v, dict) and v.get("class") == "hard"
                          and v.get("pass") and not v.get("jury_override")}
        prev_pass_hard |= {k for k, v in prev_t1.items() if isinstance(v, dict) and v.get("class") == "hard" and v.get("result") == "pass"}
        flips = sorted(hard_now & prev_pass_hard)
        for g in flips:
            reg_events.append({"round": round_k, "gate": g, "previous_round": prev.get("round")})
        if len(reg_events) >= reg_limit:
            stops.append({"reason": "regression", "detail": f"hard gates passed then failed {len(reg_events)} times: "
                          + ", ".join(f"{x['gate']}@r{x['round']}" for x in reg_events)})
        elif flips and ocfg.get("hard_gate_pass_then_fail", True):
            stops.append({"reason": "oscillation", "detail": f"hard gate {', '.join(flips)} passed in round "
                          f"{prev.get('round')} and fails in round {round_k}"})
        for dim, row in tier1.items():
            if row.get("result") != "fail" or row.get("jury_pending"):
                continue
            prow = prev_t1.get(dim) or {}
            if prow.get("result") != "fail":
                continue
            explicit = row.get("contradicts")
            if explicit or fixes_conflict(prow.get("suggested_fix"), row.get("suggested_fix"), pairs):
                stops.append({"reason": "oscillation", "detail": f"{dim} failed in rounds {prev.get('round')} and {round_k} "
                              f"with contradictory fixes: {prow.get('suggested_fix')!r} vs {row.get('suggested_fix')!r}"})
    for chk in ov_checks:
        flagged = chk in t0_out and common.check_needs_action(t0_out[chk]) and not t0_out[chk].get("waived") \
            and not t0_out[chk].get("addressed")
        streak[chk] = (int(streak.get(chk, 0)) + 1) if flagged else 0
        if streak[chk] >= ov_needed:
            stops.append({"reason": "overlap_persistent", "detail": f"{chk} flag survived {streak[chk] - 1} rewrites"})
    counters = {"regression_events": reg_events, "overlap_streak": streak}
    stop: dict | None = None
    if stops:
        order = {"regression": 0, "overlap_persistent": 1, "oscillation": 2}
        stops.sort(key=lambda s: order.get(s["reason"], 9))
        stop = {"reason": stops[0]["reason"], "detail": stops[0]["detail"],
                "drop": stops[0]["reason"] in ("regression", "overlap_persistent"), "all": stops}
        disagreements.append({"kind": stop["reason"], "dimension_or_check": None, "detail": stop["detail"]})

    lexicon = _safe(common.load_lexicon) or {}
    return {
        "schema": SCHEMA, "run": run, "cid": cid, "round": round_k, "platform": platform,
        "rubric_version": common.rubric_version(), "rubric_sha": _rubric_sha(),
        "profile_version": (profile or {}).get("profile_version") if profile else None,
        "lexicon_version": lexicon.get("lexicon_version"),
        "candidate_sha": tier0.get("candidate_sha"),
        "text_path": tier0.get("text_path"),
        "tier0": t0_out,
        "tier0_envelope": tier0.get("envelope"),
        "tier0_advisory": tier0.get("advisory"),
        "tier1": tier1,
        "tier2": t2_block,
        "judge_io": {"rejected": rejected_log, "na_by_rejection": na_by_rejection, "na_declared": na_declared, "holds": holds},
        "verdict": verdict,
        "jury_requests": jury_requests,
        "stop": stop,
        "counters": counters,
        "disagreements": disagreements,
        "generated_at": common.now_iso(),
    }


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- ranking

def rank_key(merged: dict) -> tuple:
    """Sort key only (never a verdict): (hard fails, soft fails + flags, -reply_worthiness, -sum of Tier 1 scores)."""
    v = merged.get("verdict") or {}
    t1 = merged.get("tier1") or {}
    rw_row = t1.get("reply_worthiness") or {}
    rw = _effective_score(rw_row)
    total = sum(_effective_score(r) or 0 for r in t1.values() if isinstance(r, dict))
    return (len(v.get("hard_fails") or []), len(v.get("soft_fails") or []) + len(v.get("flags") or []),
            -(rw or 0), -total)


def _effective_score(row: dict) -> float | None:
    if not isinstance(row, dict) or row.get("na"):
        return None
    j = row.get("jury")
    if isinstance(j, dict) and j.get("median") is not None:
        return float(j["median"])
    s = row.get("score")
    return float(s) if isinstance(s, (int, float)) else None


def rank(merged_list: list[dict]) -> list[dict]:
    """Order merged documents by rank_key (stable; cid breaks ties)."""
    return sorted(merged_list, key=lambda m: (rank_key(m), str(m.get("cid"))))


# --------------------------------------------------------------------------- feedback packet

def feedback(merged: dict, candidate_meta: dict | None = None) -> tuple[str, dict]:
    """Feedback packet with only failing/flagged checks: (markdown, json)."""
    meta = candidate_meta or {}
    v = merged.get("verdict") or {}
    cid = merged.get("cid")
    t0 = merged.get("tier0") or {}
    t1 = merged.get("tier1") or {}
    t2 = merged.get("tier2") or {}
    env = merged.get("tier0_envelope") or {}
    assignment = meta.get("assignment") if isinstance(meta.get("assignment"), dict) else {}

    tier0_items: list[dict] = []
    for chk, r in t0.items():
        if not common.check_needs_action(r) or r.get("waived") or r.get("addressed") or r.get("class") == "advisory":
            continue
        item = {"check": chk, "class": r.get("class"), "evidence": r.get("evidence") or [], "hits": r.get("hits"),
                "value": r.get("value"), "limit": r.get("limit"), "note": r.get("note") or r.get("why")}
        if chk == "E1_envelope":
            item["score"] = r.get("score", env.get("score"))
            item["out"] = r.get("out") or env.get("out") or []
            item["scope"] = r.get("scope") or env.get("scope")
        if r.get("jury_confirmed"):
            item["jury_confirmed"] = True
        tier0_items.append(item)
    envelope_out = [o for o in (env.get("out") or []) if isinstance(o, dict)]

    tier1_items: list[dict] = []
    for dim, row in t1.items():
        if row.get("result") not in ("fail", "hold", "unscored"):
            continue
        if row.get("result") == "unscored" and row.get("note") in ("no judgement",):
            continue
        item = {"dimension": dim, "class": row.get("class"), "result": row.get("result"), "score": row.get("score"),
                "threshold": row.get("threshold"), "judge": row.get("judge"),
                "jury_median": (row.get("jury") or {}).get("median") if isinstance(row.get("jury"), dict) else None,
                "evidence": row.get("evidence") or [], "suggested_fix": row.get("suggested_fix"),
                "violations": row.get("violations") or [], "needs_confirmation": row.get("needs_confirmation") or []}
        if dim == "claims":
            item["claims"] = [c for c in (row.get("claims") or []) if c.get("status") == "wrong"]
        tier1_items.append(item)

    lineup_tells: list[dict] = []
    lu = t2.get("lineup") if isinstance(t2, dict) else None
    if isinstance(lu, dict):
        for p in lu.get("picks") or []:
            if p.get("picked_candidate"):
                lineup_tells.append({"judge": p.get("judge") or p.get("lens"), "confidence": p.get("confidence"),
                                     "tell": p.get("tell"), "quote": p.get("quote")})
    tier2_items: dict[str, Any] = {}
    if isinstance(lu, dict) and lu.get("pass") is False:
        tier2_items["lineup"] = {"pass": False, "rule": lu.get("rule")}
    para = t2.get("paraphrase") if isinstance(t2, dict) else None
    if isinstance(para, dict) and para.get("pass") is False:
        tier2_items["paraphrase"] = {k: para.get(k) for k in ("same_post_rewritten", "same_skeleton_or_joke", "evidence", "ref")}
    pw = t2.get("pairwise") if isinstance(t2, dict) else None
    if isinstance(pw, dict) and pw.get("pass") is False:
        tier2_items["pairwise"] = {"pass": False, "better": pw.get("better"), "mode": pw.get("mode")}
    claims = t2.get("claims") if isinstance(t2, dict) else None
    if isinstance(claims, list):
        bad = [c for c in claims if c.get("status") in ("wrong", "unverifiable")]
        if bad:
            tier2_items["claims"] = bad
    md_ = t2.get("media") if isinstance(t2, dict) else None
    if isinstance(md_, dict) and md_.get("pass") is False:
        tier2_items["media"] = md_

    packet = {
        "schema": FEEDBACK_SCHEMA, "cid": cid, "round": merged.get("round"), "platform": merged.get("platform"),
        "verdict": v.get("status"), "stop": merged.get("stop"),
        "move": assignment.get("move"), "lens": assignment.get("lens"),
        "tier0": tier0_items, "envelope_out": envelope_out, "tier1": tier1_items, "tier2": tier2_items,
        "lineup_tells": lineup_tells, "unscored": v.get("unscored") or [], "flags": v.get("flags") or [],
        "instruction": INSTRUCTION,
    }

    lines: list[str] = [f"# Feedback for {cid} (round {merged.get('round')}, {merged.get('platform')}) - verdict: {v.get('status')}", ""]
    if merged.get("stop"):
        s = merged["stop"]
        lines += [f"STOP: {s.get('reason')} - {s.get('detail')}", ""]
    if assignment.get("move") or assignment.get("lens"):
        lines += [f"Assignment: move={assignment.get('move')} lens={assignment.get('lens')} (keep both)", ""]
    if tier0_items:
        lines.append("## Tier 0 (deterministic)")
        for it in tier0_items:
            head = f"- {it['check']} ({it['class']})"
            if it["check"] == "E1_envelope":
                thr = _envelope_threshold()
                head += f": score {it.get('score')} < {thr} for scope {it.get('scope')}"
                lines.append(head)
                for o in it.get("out") or []:
                    lines.append(f"  - {_fmt_out(o, it.get('scope'))}")
                continue
            if it.get("value") is not None and it.get("limit") is not None:
                head += f": {it['value']} vs limit {it['limit']}"
            if it.get("note"):
                head += f" - {it['note']}"
            lines.append(head)
            for ev in it["evidence"]:
                if isinstance(ev, dict):
                    lines.append(f"  - \"{ev.get('span', '')}\" - {ev.get('why', '')}")
            for h in (it.get("hits") or [])[:5]:
                if isinstance(h, dict):
                    lines.append(f"  - overlap with {h.get('ref')}: \"{h.get('span', '')}\" ({h.get('n', '')}-gram)")
        lines.append("")
    if envelope_out and not any(i["check"] == "E1_envelope" for i in tier0_items):
        lines.append("## Out-of-envelope features (advisory)")
        for o in envelope_out:
            lines.append(f"- {_fmt_out(o, env.get('scope'))}")
        lines.append("")
    if tier1_items:
        lines.append("## Judged dimensions")
        for it in tier1_items:
            head = f"- {it['dimension']} ({it['class']}, {it['result']}"
            if it.get("score") is not None:
                head += f", score {it['score']}/{it.get('threshold')}"
            if it.get("jury_median") is not None:
                head += f", jury median {it['jury_median']}"
            head += ")"
            lines.append(head)
            for ev in it["evidence"]:
                if isinstance(ev, dict):
                    lines.append(f"  - \"{ev.get('quote', '')}\" - {ev.get('why', '')}")
            if it.get("suggested_fix"):
                lines.append(f"  - suggested fix: {it['suggested_fix']}")
            if it.get("violations"):
                lines.append(f"  - violations: {', '.join(it['violations'])}")
            for nc in it.get("needs_confirmation") or []:
                lines.append(f"  - needs confirmation: {nc.get('claim')} ({nc.get('source')})")
            for c in it.get("claims") or []:
                lines.append(f"  - wrong claim: {c.get('text')} ({c.get('source')})")
        lines.append("")
    if tier2_items or lineup_tells:
        lines.append("## Tier 2")
        for t in lineup_tells:
            lines.append(f"- lineup tell ({t.get('judge')}, confidence {t.get('confidence')}): {t.get('tell')}"
                         + (f" - \"{t.get('quote')}\"" if t.get("quote") else ""))
        if "paraphrase" in tier2_items:
            p = tier2_items["paraphrase"]
            lines.append(f"- paraphrase: same_post_rewritten={p.get('same_post_rewritten')} same_skeleton_or_joke={p.get('same_skeleton_or_joke')}"
                         + (f" - \"{p.get('evidence')}\"" if p.get("evidence") else ""))
        if "pairwise" in tier2_items:
            lines.append(f"- pairwise ({tier2_items['pairwise'].get('mode')}): lost every comparison")
        for c in tier2_items.get("claims") or []:
            lines.append(f"- claim {c.get('status')}: {c.get('text')} ({c.get('source')})")
        if "media" in tier2_items:
            m = tier2_items["media"]
            lines.append(f"- media: media_check={m.get('media_check')} media_judge={m.get('media_judge')}")
        lines.append("")
    if not tier0_items and not tier1_items and not tier2_items and not lineup_tells:
        lines += ["Nothing failed or flagged.", ""]
    lines += ["## Instruction", INSTRUCTION, ""]
    return "\n".join(lines), packet


def _envelope_threshold() -> Any:
    try:
        return (common.load_thresholds().get("checks") or {}).get("E1_envelope", {}).get("threshold", 0.70)
    except Exception:  # noqa: BLE001
        return 0.70


def _fmt_out(o: dict, scope: Any) -> str:
    env = o.get("envelope") or [None, None]
    lo, hi = (env + [None, None])[:2]
    return f"{o.get('feature')} {o.get('value')}; {scope or 'scope'} envelope {lo}-{hi}"


# --------------------------------------------------------------------------- CLI plumbing

def _round_dir(run: str, k: int) -> Path:
    return common.run_dir(run) / f"round{k}"


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _candidate_text(round_dir: Path, cid: str, tier0: dict) -> str | None:
    cands = [tier0.get("text_path"), f"drafts/{round_dir.parent.name}/{round_dir.name}/candidates/{cid}.txt"]
    for c in cands:
        if not c:
            continue
        p = Path(c) if Path(c).is_absolute() else common.ROOT / c
        if p.exists():
            return p.read_text(encoding="utf-8").rstrip("\n")
    p = round_dir / "candidates" / f"{cid}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").rstrip("\n")
    p = round_dir / "candidates" / f"{cid}.md"
    if p.exists():
        return common.split_front_matter(p.read_text(encoding="utf-8"))[1].rstrip("\n")
    return None


def lens_from_filename(name: str, cid: str) -> tuple[str | None, bool]:
    """(lens, is_jury) as the file name declares it: <cid>.<lens>.json, <cid>.<lens>.rerun-<orig>.json,
    <cid>.jury.<lens>.<dim>.json. The name is authoritative; a body whose `lens` disagrees is rejected whole."""
    rest = name[len(cid) + 1:] if name.startswith(cid + ".") else name
    parts = rest[:-len(".json")].split(".") if rest.endswith(".json") else rest.split(".")
    if parts and parts[0] == "jury":
        return (parts[1] if len(parts) > 1 else None), True
    return (parts[0] if parts and parts[0] else None), False


def _collect_judge_files(scores: Path, cid: str, text: str | None, thresholds: dict, cfg: dict,
                         requested: set[str] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """(judge entries, jury entries, contamination rows). With `requested` (project-relative output paths run_next
    asked for, from state.json) a judge or jury file nobody requested is ignored and logged, never merged."""
    judges: list[dict] = []
    juries: list[dict] = []
    contamination: list[dict] = []
    prefix = cid + "."
    for p in sorted(scores.glob(f"{cid}.*.json")):
        rest = p.name[len(prefix):]
        if rest in ("tier0.json", "merged.json"):
            continue
        relp = common.rel(p)
        if requested is not None and relp not in requested:
            contamination.append({"file": relp, "reason": "no run_next action requested this output path; ignored"})
            continue
        file_lens, is_jury = lens_from_filename(p.name, cid)
        try:
            data = _load_json(p)
        except json.JSONDecodeError as exc:
            entry = {"path": relp, "lens": file_lens, "data": {},
                     "validation": {"ok": False, "rejected": [{"dimension": WHOLE, "reason": f"invalid JSON: {exc}"}], "normalized": {}}}
            (juries if is_jury else judges).append(entry)
            continue
        if not isinstance(data, dict):
            data = {}
        if is_jury:
            data.setdefault("jury", True)
        body_lens = data.get("lens")
        validation = judge_io.validate(data, text, thresholds, cfg)
        if file_lens and body_lens and str(body_lens) != file_lens:
            validation = {"ok": False, "normalized": {},
                          "rejected": [{"dimension": WHOLE, "reason": f"file is named for lens {file_lens!r} but carries lens {body_lens!r}"}]
                          + list(validation.get("rejected") or [])}
        elif not is_jury and data.get("rerun_for") and ".rerun-" not in rest:
            validation = {"ok": False, "normalized": {},
                          "rejected": [{"dimension": WHOLE, "reason": f"body declares rerun_for {data.get('rerun_for')!r} but the file is not a rerun file"}]}
        entry = {"path": relp, "lens": file_lens or body_lens, "data": data, "validation": validation}
        (juries if is_jury else judges).append(entry)
    return judges, juries, contamination


def requested_outputs(run: str) -> set[str] | None:
    """Output paths run_next recorded in drafts/<run>/state.json (None when the run has no such record)."""
    state = common.read_json(common.run_dir(run) / "state.json", default=None)
    if not isinstance(state, dict) or not isinstance(state.get("requested_outputs"), dict):
        return None
    return set(state["requested_outputs"].keys())


def _discover_tier2(run: str, cid: str, explicit: str | None) -> dict | None:
    if explicit:
        p = Path(explicit) if Path(explicit).is_absolute() else common.ROOT / explicit
        if not p.exists():
            raise FileNotFoundError(f"tier2 file not found: {common.rel(p)}")
        return _load_json(p)
    t2 = common.run_dir(run) / "tier2"
    combined = t2 / f"{cid}.tier2.json"
    if combined.exists():
        return _load_json(combined)
    out: dict[str, Any] = {}
    for key, names in {"lineup": [f"lineup_{cid}.result.json", f"lineup_{cid}.score.json"],
                       "pairwise": [f"pairwise_{cid}.result.json", f"pairwise_{cid}.score.json"],
                       "claims": [f"claims_{cid}.json"], "media": [f"media_{cid}.json"]}.items():
        for n in names:
            p = t2 / n
            if p.exists():
                out[key] = _load_json(p)
                break
    return out or None


def _discover_previous(run: str, cid: str, k: int, explicit: str | None) -> dict | None:
    if explicit:
        p = Path(explicit) if Path(explicit).is_absolute() else common.ROOT / explicit
        if not p.exists():
            raise FileNotFoundError(f"previous merged file not found: {common.rel(p)}")
        return _load_json(p)
    if k <= 1:
        return None
    prev_dir = _round_dir(run, k - 1) / "scores"
    cand = _round_dir(run, k) / "candidates" / f"{cid}.md"
    names: list[str] = []
    if cand.exists():
        meta, _ = common.split_front_matter(cand.read_text(encoding="utf-8"))
        lineage = meta.get("lineage") if isinstance(meta, dict) else None
        if isinstance(lineage, dict) and lineage.get("rewrite_of"):
            names.append(str(lineage["rewrite_of"]))
    names.append(re.sub(r"^r\d+-", f"r{k - 1}-", cid))
    names.append(cid)
    for n in names:
        p = prev_dir / f"{n}.merged.json"
        if p.exists():
            return _load_json(p)
    return None


def cmd_merge(args: argparse.Namespace) -> dict:
    rd = _round_dir(args.run, args.round)
    scores = rd / "scores"
    t0p = scores / f"{args.cid}.tier0.json"
    if not t0p.exists():
        raise FileNotFoundError(f"tier0 file not found: {common.rel(t0p)} (run tier0.py first)")
    tier0 = _load_json(t0p)
    thresholds = common.load_thresholds()
    cfg = common.load_config()
    text = _candidate_text(rd, args.cid, tier0)
    judges, juries, contamination = _collect_judge_files(scores, args.cid, text, thresholds, cfg,
                                                         requested_outputs(args.run))
    tier2 = _discover_tier2(args.run, args.cid, args.tier2)
    previous = _discover_previous(args.run, args.cid, args.round, args.previous)
    merged = merge(args.run, args.cid, args.round, tier0, judges, juries, tier2, previous, thresholds, cfg,
                   common.load_profile(), set(args.waive or []))
    merged["judge_io"]["contamination"] = contamination
    if not args.no_write:
        common.write_json(scores / f"{args.cid}.merged.json", merged)
        merged["written"] = common.rel(scores / f"{args.cid}.merged.json")
    return merged


def cmd_feedback(args: argparse.Namespace) -> dict:
    rd = _round_dir(args.run, args.round)
    mp = rd / "scores" / f"{args.cid}.merged.json"
    if not mp.exists():
        raise FileNotFoundError(f"merged file not found: {common.rel(mp)} (run aggregate.py merge first)")
    merged = _load_json(mp)
    meta: dict = {}
    cand = rd / "candidates" / f"{args.cid}.md"
    if cand.exists():
        meta, _ = common.split_front_matter(cand.read_text(encoding="utf-8"))
    md, packet = feedback(merged, meta if isinstance(meta, dict) else {})
    out = {"ok": True, "cid": args.cid, "round": args.round, "verdict": merged.get("verdict", {}).get("status"),
           "stop": merged.get("stop"), "packet": packet}
    if not args.no_write:
        fdir = rd / "feedback"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / f"{args.cid}.md").write_text(md, encoding="utf-8")
        common.write_json(fdir / f"{args.cid}.json", packet)
        out["md"] = common.rel(fdir / f"{args.cid}.md")
        out["json"] = common.rel(fdir / f"{args.cid}.json")
    else:
        out["markdown"] = md
    return out


def cmd_rank(args: argparse.Namespace) -> dict:
    scores = _round_dir(args.run, args.round) / "scores"
    if not scores.exists():
        raise FileNotFoundError(f"no scores directory: {common.rel(scores)}")
    docs = [_load_json(p) for p in sorted(scores.glob("*.merged.json"))]
    ordered = rank(docs)
    return {"ok": True, "run": args.run, "round": args.round,
            "ranked": [{"cid": m.get("cid"), "platform": m.get("platform"), "status": (m.get("verdict") or {}).get("status"),
                        "key": list(rank_key(m)), "stop": (m.get("stop") or {}).get("reason") if m.get("stop") else None}
                       for m in ordered]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Merge scores into <cid>.merged.json, write feedback packets, rank candidates.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge", help="merge tier0 + judge + jury (+ tier2) files for one candidate")
    m.add_argument("run"); m.add_argument("cid")
    m.add_argument("--round", type=int, required=True)
    m.add_argument("--waive", action="append", help="waive a flag/soft Tier 0 check id (repeatable) or accept na on a dimension")
    m.add_argument("--tier2", help="explicit tier2 JSON (default: discovered under drafts/<run>/tier2/)")
    m.add_argument("--previous", help="explicit previous-round merged JSON (default: discovered via lineage.rewrite_of)")
    m.add_argument("--no-write", action="store_true")
    m.add_argument("--json", action="store_true")
    f = sub.add_parser("feedback", help="write round<k>/feedback/<cid>.md and .json")
    f.add_argument("run"); f.add_argument("cid")
    f.add_argument("--round", type=int, required=True)
    f.add_argument("--no-write", action="store_true")
    f.add_argument("--json", action="store_true")
    r = sub.add_parser("rank", help="order the round's merged documents by the sort key")
    r.add_argument("run")
    r.add_argument("--round", type=int, required=True)
    r.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "merge":
            common.emit(cmd_merge(args))
        elif args.cmd == "feedback":
            common.emit(cmd_feedback(args))
        else:
            common.emit(cmd_rank(args))
        return 0
    except (FileNotFoundError, ValueError, json.JSONDecodeError, KeyError) as exc:
        common.error(str(exc))
        return 0


if __name__ == "__main__":
    sys.exit(main())
