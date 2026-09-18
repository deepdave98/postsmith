#!/usr/bin/env python3
"""Validate judge output files (contracts §6, §16) and plan reruns.

validate(judge_json, candidate_text, thresholds, cfg) checks:
  * schema, rubric_version == common.rubric_version(), a known lens, dimension ids valid for that lens (a
    file with ``jury: true`` may score any dimension, a known-false-positive Tier 0 check id, or
    O3_skeleton; a file with ``rerun_for: <lens>`` is validated against that lens's dimension list);
  * integer scores 1-5 unless ``na: true``, which needs a non-empty ``pre_step`` reason;
  * a full judgement (not a jury or rerun file) carries every dimension of its lens; a missing one is
    rejected per dimension so the alternate-lens rerun ladder engages;
  * every scored non-na dimension has >= 1 evidence quote that matches the candidate after normalization
    (NFKC, quotes/dashes/ellipsis folded by common.fold_punct, collapsed whitespace, casefold), either as a
    substring or with difflib ratio >= cfg.judges.evidence_fuzzy_ratio against the best-aligned window;
  * the lineup, pairwise, claims and media shapes.
Returns {"ok", "rejected": [{"dimension", "reason"}], "normalized": {...}}, where `normalized` holds only the
accepted dimensions, with integer scores and each evidence quote annotated with its match kind.

CLI: judge_io.py validate <judge.json> --candidate <cid>.txt [--json]
     judge_io.py rerun-plan <judge.json> --rejected <validation.json> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

SCHEMA = "postsmith.judge/1"
LENSES = ("reader", "voice", "comedy", "persona", "media", "lineup", "pairwise")
SCORED_LENSES = ("reader", "voice", "comedy", "persona", "media")
WHOLE_FILE = "*"
CLAIM_STATUSES = {"user_provided", "brief", "opinion", "joke", "needs_check", "verified", "plausible", "unverifiable", "wrong"}
MEDIA_SUB_RESULTS = {"alt_text_alone", "does_work", "slop_screen", "executable", "factual", "capture_direction"}
DEFAULT_RERUN_ROTATION = {"reader": "voice", "voice": "comedy", "comedy": "reader", "persona": "voice",
                          "media": "media", "lineup": "lineup", "pairwise": "pairwise"}


# --------------------------------------------------------------------------- normalization & matching

def normalize_for_match(s: str) -> str:
    """NFKC + folded quotes/dashes/ellipsis + collapsed whitespace + casefold (both sides of every match)."""
    return common.collapse_ws(common.fold_punct(str(s))).casefold()


def best_window_ratio(quote: str, candidate: str) -> tuple[float, str]:
    """difflib ratio of `quote` against the best-aligned window of the same length in `candidate`.

    Windows start at the matching blocks between the two strings, so a quote with a typo or a dropped word
    still lines up with the span it came from. Both inputs must already be normalized.
    """
    if not quote or not candidate:
        return 0.0, ""
    n = len(quote)
    if n >= len(candidate):
        return SequenceMatcher(None, quote, candidate, autojunk=False).ratio(), candidate
    sm = SequenceMatcher(None, candidate, quote, autojunk=False)
    starts: set[int] = set()
    for block in sm.get_matching_blocks():
        if block.size == 0:
            continue
        start = block.a - block.b
        for delta in (-2, -1, 0, 1, 2):
            s = start + delta
            if 0 <= s <= len(candidate) - n:
                starts.add(s)
    if not starts:
        starts = {0}
    best, best_win = 0.0, ""
    for s in sorted(starts):
        win = candidate[s:s + n]
        r = SequenceMatcher(None, quote, win, autojunk=False).ratio()
        if r > best:
            best, best_win = r, win
    return best, best_win


def match_quote(quote: str, candidate_text: str, fuzzy_ratio: float) -> dict:
    """Return {"match": "exact"|"fuzzy"|"none", "ratio": float}."""
    q = normalize_for_match(quote)
    c = normalize_for_match(candidate_text)
    if not q:
        return {"match": "none", "ratio": 0.0, "reason": "empty quote"}
    if q in c:
        return {"match": "exact", "ratio": 1.0}
    ratio, _win = best_window_ratio(q, c)
    if ratio >= fuzzy_ratio:
        return {"match": "fuzzy", "ratio": round(ratio, 4)}
    return {"match": "none", "ratio": round(ratio, 4)}


# --------------------------------------------------------------------------- validation

def _is_int_score(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return 1 <= v <= 5
    if isinstance(v, float) and v.is_integer():
        return 1 <= int(v) <= 5
    return False


def _lens_dims(thresholds: dict, lens: str) -> list[str]:
    """Dimensions of a lens: thresholds.lenses[lens], else from dimensions[*].lens, as aggregate does."""
    lenses = thresholds.get("lenses") or {}
    if lenses:
        return list(lenses.get(lens) or [])
    return [d for d, spec in (thresholds.get("dimensions") or {}).items()
            if isinstance(spec, dict) and str(spec.get("lens")) == lens]


def _all_dims(thresholds: dict) -> set[str]:
    return set((thresholds.get("dimensions") or {}).keys())


def _kfp_checks(thresholds: dict) -> set[str]:
    return set((thresholds.get("jury") or {}).get("known_false_positive_checks") or [])


def _validate_evidence(ev: Any, candidate_text: str, fuzzy: float) -> tuple[list[dict], bool]:
    out: list[dict] = []
    any_match = False
    if not isinstance(ev, list):
        return out, False
    for item in ev:
        if isinstance(item, str):
            item = {"quote": item, "why": ""}
        if not isinstance(item, dict):
            continue
        quote = item.get("quote")
        if not isinstance(quote, str):
            continue
        m = match_quote(quote, candidate_text, fuzzy) if candidate_text is not None else {"match": "unchecked", "ratio": None}
        row = {"quote": quote, "why": item.get("why", ""), **m}
        if m["match"] in ("exact", "fuzzy", "unchecked"):
            any_match = True
        out.append(row)
    return out, any_match


def _validate_scored_dim(dim: str, d: Any, candidate_text: str, fuzzy: float, is_claims: bool, is_media: bool) -> tuple[dict | None, str | None]:
    """Return (normalized_dim, rejection_reason)."""
    if not isinstance(d, dict):
        return None, "dimension value is not an object"
    nd: dict[str, Any] = dict(d)
    na = bool(d.get("na", False))
    nd["na"] = na
    if na and not (isinstance(d.get("pre_step"), str) and d["pre_step"].strip()):
        return None, "na requires a non-empty pre_step reason"
    if is_claims:
        if na:
            nd["claims"] = []
            return nd, None
        claims = d.get("claims")
        if not isinstance(claims, list):
            return None, "claims must be a list of {text, status, source}"
        norm_claims = []
        for c in claims:
            if not isinstance(c, dict) or not isinstance(c.get("text"), str):
                return None, "each claim needs a text"
            status = c.get("status")
            if status not in CLAIM_STATUSES:
                return None, f"claim status {status!r} not in {sorted(CLAIM_STATUSES)}"
            norm_claims.append({"text": c["text"], "status": status, "source": c.get("source")})
        nd["claims"] = norm_claims
        ev, _ = _validate_evidence(d.get("evidence", []), candidate_text, fuzzy)
        nd["evidence"] = ev
        return nd, None
    if is_media:
        if na:
            return nd, None
        sub = d.get("sub_results") or d.get("results") or {}
        if not isinstance(sub, dict):
            return None, "media needs sub_results"
        unknown = sorted(set(sub) - MEDIA_SUB_RESULTS)
        if unknown:
            return None, f"unknown media sub-results: {unknown}"
        nd["sub_results"] = sub
        if "pass" in d and not isinstance(d["pass"], bool):
            return None, "media.pass must be boolean"
        return nd, None
    if na:
        nd["score"] = None
        ev, _ = _validate_evidence(d.get("evidence", []), candidate_text, fuzzy)
        nd["evidence"] = ev
        return nd, None
    score = d.get("score")
    if not _is_int_score(score):
        return None, f"score must be an integer 1-5 (got {score!r}) unless na is true"
    nd["score"] = int(score)
    ev, ok = _validate_evidence(d.get("evidence", []), candidate_text, fuzzy)
    nd["evidence"] = ev
    if not ok:
        if not ev:
            return None, "no evidence quote"
        return None, "no evidence quote matches the candidate verbatim (after normalization / fuzzy window)"
    nc = d.get("needs_confirmation")
    if nc is not None:
        if not isinstance(nc, list) or any(not isinstance(x, dict) for x in nc):
            return None, "needs_confirmation must be a list of {claim, source}"
    else:
        nd["needs_confirmation"] = []
    sf = d.get("suggested_fix")
    nd["suggested_fix"] = sf if isinstance(sf, str) and sf.strip() else None
    v = d.get("violations")
    nd["violations"] = [str(x) for x in v] if isinstance(v, list) else []
    return nd, None


def validate(judge_json: Any, candidate_text: str | None, thresholds: dict, cfg: dict) -> dict:
    """Validate one judge output. See module docstring. Never raises on bad judge content."""
    rejected: list[dict] = []
    fuzzy = float((cfg.get("judges") or {}).get("evidence_fuzzy_ratio", 0.9))
    warnings: list[str] = []

    if not isinstance(judge_json, dict):
        return {"ok": False, "rejected": [{"dimension": WHOLE_FILE, "reason": "judge output is not a JSON object"}],
                "normalized": {}}
    schema = judge_json.get("schema")
    if schema not in (None, SCHEMA):
        rejected.append({"dimension": WHOLE_FILE, "reason": f"schema {schema!r} != {SCHEMA}"})
    rv = judge_json.get("rubric_version")
    expected_rv = common.rubric_version()
    if rv != expected_rv:
        rejected.append({"dimension": WHOLE_FILE, "reason": f"rubric_version {rv!r} != current {expected_rv!r}"})
    lens = judge_json.get("lens")
    if lens not in LENSES:
        rejected.append({"dimension": WHOLE_FILE, "reason": f"unknown lens {lens!r}"})
    if rejected:
        return {"ok": False, "rejected": rejected, "normalized": {}, "warnings": warnings}

    normalized: dict[str, Any] = {
        "schema": SCHEMA, "rubric_version": rv, "lens": lens,
        "candidate_sha": judge_json.get("candidate_sha"),
    }
    for key in ("jury", "rerun_for", "agent", "model", "cid"):
        if key in judge_json:
            normalized[key] = judge_json[key]
    if candidate_text is not None and judge_json.get("candidate_sha"):
        actual = common.content_sha(candidate_text)
        if judge_json["candidate_sha"] != actual:
            warnings.append(f"candidate_sha {judge_json['candidate_sha']!r} does not match the candidate text ({actual})")

    if lens == "lineup":
        _validate_lineup(judge_json, normalized, rejected)
        return {"ok": not rejected, "rejected": rejected, "normalized": normalized, "warnings": warnings}
    if lens == "pairwise":
        _validate_pairwise(judge_json, normalized, rejected)
        return {"ok": not rejected, "rejected": rejected, "normalized": normalized, "warnings": warnings}

    dims = judge_json.get("dimensions")
    if not isinstance(dims, dict) or not dims:
        rejected.append({"dimension": WHOLE_FILE, "reason": "dimensions missing or empty"})
        return {"ok": False, "rejected": rejected, "normalized": normalized, "warnings": warnings}

    scoring_lens = judge_json.get("rerun_for") or lens
    if bool(judge_json.get("jury")):
        allowed = _all_dims(thresholds) | _kfp_checks(thresholds) | {"O3_skeleton"}
    else:
        allowed = set(_lens_dims(thresholds, scoring_lens))
        if not allowed:
            allowed = _all_dims(thresholds)
    norm_dims: dict[str, Any] = {}
    for dim, d in dims.items():
        if dim not in allowed:
            rejected.append({"dimension": dim, "reason": f"dimension {dim!r} is not valid for lens {scoring_lens!r}"})
            continue
        nd, reason = _validate_scored_dim(dim, d, candidate_text, fuzzy, is_claims=(dim == "claims"), is_media=(dim == "media"))
        if reason:
            rejected.append({"dimension": dim, "reason": reason})
            continue
        spec = (thresholds.get("dimensions") or {}).get(dim) or {}
        if "threshold" in spec and "threshold" not in nd:
            nd["threshold"] = spec["threshold"]
        norm_dims[dim] = nd
    normalized["dimensions"] = norm_dims
    expected = set(_lens_dims(thresholds, scoring_lens))
    missing = sorted(expected - set(dims))
    if missing:
        normalized["missing"] = missing
        # Rejecting the missing dimension one by one starts the rerun ladder (alternate lens, then na / hold)
        # instead of leaving the merge to wait for ever. A jury file scores one dimension and a rerun file
        # only the dimensions it was asked for, so both are exempt.
        if not judge_json.get("jury") and not judge_json.get("rerun_for"):
            for d in missing:
                rejected.append({"dimension": d, "reason": "dimension missing from judge output"})
    return {"ok": not rejected, "rejected": rejected, "normalized": normalized, "warnings": warnings}


def _validate_lineup(j: dict, normalized: dict, rejected: list[dict]) -> None:
    pick = j.get("pick")
    conf = j.get("confidence")
    if pick not in ("A", "B", "C", "D"):
        rejected.append({"dimension": "lineup", "reason": f"pick must be A|B|C|D (got {pick!r})"})
    if not _is_int_score(conf):
        rejected.append({"dimension": "lineup", "reason": f"confidence must be an integer 1-5 (got {conf!r})"})
    if not isinstance(j.get("tell"), str) or not j.get("tell", "").strip():
        rejected.append({"dimension": "lineup", "reason": "tell missing"})
    if not rejected:
        normalized.update({"pick": pick, "confidence": int(conf), "tell": j["tell"], "quote": j.get("quote", "")})


def _validate_pairwise(j: dict, normalized: dict, rejected: list[dict]) -> None:
    for key in ("better", "voice"):
        if j.get(key) not in (1, 2):
            rejected.append({"dimension": "pairwise", "reason": f"{key} must be 1 or 2 (got {j.get(key)!r})"})
        ev = j.get(f"{key}_evidence")
        if not isinstance(ev, str) or not ev.strip():
            rejected.append({"dimension": "pairwise", "reason": f"{key}_evidence missing"})
    for key in ("same_post_rewritten", "same_skeleton_or_joke"):
        if j.get(key) not in (None, True, False):
            rejected.append({"dimension": "pairwise", "reason": f"{key} must be null|true|false"})
    if not rejected:
        normalized.update({k: j.get(k) for k in ("better", "better_evidence", "voice", "voice_evidence",
                                                  "same_post_rewritten", "same_skeleton_or_joke", "evidence")})


# --------------------------------------------------------------------------- rerun planning

def rerun_plan(rejected: list[dict], lens: str, thresholds: dict | None = None) -> dict:
    """The alternate-lens rerun for rejected dimensions: reader->voice->comedy->reader; persona->voice.

    Returns {"original_lens", "rerun_lens", "dimensions": [...], "whole_file": bool, "reasons": [...]}.
    A whole-file rejection reruns every dimension of the lens (dimensions == []).
    """
    rotation = dict(DEFAULT_RERUN_ROTATION)
    if thresholds:
        rotation.update((thresholds.get("rerun") or {}).get("rotation") or {})
    whole = any(r.get("dimension") in (None, WHOLE_FILE) for r in rejected)
    dims = sorted({r["dimension"] for r in rejected if r.get("dimension") not in (None, WHOLE_FILE)})
    if whole and thresholds:
        dims = list(_lens_dims(thresholds, lens))
    return {
        "original_lens": lens,
        "rerun_lens": rotation.get(lens, lens),
        "dimensions": dims,
        "whole_file": whole,
        "reasons": [r.get("reason") for r in rejected],
    }


# --------------------------------------------------------------------------- CLI

def _read_json_file(path: str) -> Any:
    p = Path(path)
    if not p.is_absolute():
        p = common.ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"file not found: {common.rel(p)}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{common.rel(p)} is not valid JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate judge output files and plan reruns.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate <judge.json> against the candidate text")
    v.add_argument("judge_json")
    v.add_argument("--candidate", required=True, help="<cid>.txt (post text only) or the candidate .md")
    v.add_argument("--json", action="store_true")
    r = sub.add_parser("rerun-plan", help="plan the alternate-lens rerun for a rejected judge file")
    r.add_argument("judge_json")
    r.add_argument("--rejected", help="a validation result JSON (default: validate now, requires --candidate)")
    r.add_argument("--candidate")
    r.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        judge = _read_json_file(args.judge_json)
        thresholds = common.load_thresholds()
        cfg = common.load_config()
        if args.cmd == "validate":
            text = _read_candidate_text(args.candidate)
            common.emit(validate(judge, text, thresholds, cfg))
            return 0
        if args.rejected:
            rejected = _read_json_file(args.rejected).get("rejected", [])
        else:
            if not args.candidate:
                common.error("--rejected or --candidate is required")
                return 0
            rejected = validate(judge, _read_candidate_text(args.candidate), thresholds, cfg)["rejected"]
        common.emit(rerun_plan(rejected, str(judge.get("lens")), thresholds))
        return 0
    except (FileNotFoundError, ValueError) as exc:
        common.error(str(exc))
        return 0


def _read_candidate_text(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = common.ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"candidate text not found: {common.rel(p)}")
    raw = p.read_text(encoding="utf-8")
    if p.suffix == ".md":
        _, body = common.split_front_matter(raw)
        return body.rstrip("\n")
    return raw.rstrip("\n")


if __name__ == "__main__":
    sys.exit(main())
