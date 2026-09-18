#!/usr/bin/env python3
"""Envelope checks (contracts.md section 16): E1_envelope, P14_dashes, P15_burstiness, P16_broetry.

`run_checks(features, scope, profile, cfg, self_profile_scope="self")`:
- E1_envelope (soft): the weighted fraction of FEATURE_WEIGHTS inside [q1 - widen*IQR, q3 + widen*IQR] of
  the lens scope, plus the function-word cosine distance to the lens centroid (inside when <= the scope's
  max_intra_distance). `widen` is config `envelope.iqr_widen`, the pass mark config `envelope.pass_score`.
  Register features (sent_words.*, case.*, punct_per_1k.*, lexicon.contraction_rate) are measured against
  the self scope when it exists with n >= config `corpus.self_min_samples`. A feature whose value is null,
  whose scope has no stats, or sent_words.* on a post with fewer than 3 sentences, is skipped and listed in
  `envelope.skipped`.
- P14_dashes (soft): em+en dashes per 1k chars above the register scope's q3 + widen*IQR (summed over em and
  en) and > 0.
- P15_burstiness (soft): sent_words.cv below the register scope q1, only when the post has >= 4 sentences.
- P16_broetry (soft): pct_single_sentence_paras > 0.80 while the lens scope median is < 0.30.

An unknown or empty scope falls back to `corpus`. Without a profile or a usable scope every check is
`{"class": "advisory", "pass": true, "note": ...}`. Small-corpus mode (`small_corpus=True`, widen from config
`envelope.small_corpus_iqr_widen`, default 1.5) and a lens scope under `envelope.min_scope_n` posts
(default 4) still compute the four checks but report them as advisory, with `class_original` and
`downgrade_reason`. Failing checks carry `evidence` with a `why` and an empty span: this module sees
numbers, never the text.

CLI: `envelope_check.py <features.json|post.md|post.txt> [--scope S] [--profile P] [--root R] [--json]`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import emit  # noqa: E402
import stylometry  # noqa: E402
from stylometry import apply_root, cosine_distance, get_path  # noqa: E402

FEATURE_WEIGHTS: list[tuple[str, float]] = [
    ("line_words.median", 2), ("line_words.pct_le4", 1), ("sent_words.cv", 2), ("sent_words.mean", 1),
    ("hook.line1_chars", 1), ("pov.i_per100", 1), ("pov.you_per100", 1), ("punct_per_1k.em_dash", 1),
    ("punct_per_1k.exclaim", 1), ("punct_per_1k.ellipsis", 0.5), ("lexicon.mean_word_len", 1),
    ("lexicon.contraction_rate", 1), ("lexicon.specificity_per100", 2), ("n_chars", 1),
]
FUNCTION_WORD_WEIGHT = 2.0
REGISTER_PREFIXES = ("sent_words.", "case.", "punct_per_1k.")
REGISTER_EXACT = {"lexicon.contraction_rate"}
CHECK_IDS = ("E1_envelope", "P14_dashes", "P15_burstiness", "P16_broetry")


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


def is_register_feature(path: str) -> bool:
    return path in REGISTER_EXACT or path.startswith(REGISTER_PREFIXES)


def envelope_bounds(stats: dict, widen: float) -> tuple[float, float] | None:
    q1, q3 = stats.get("q1"), stats.get("q3")
    if q1 is None or q3 is None:
        return None
    iqr = float(q3) - float(q1)
    return float(q1) - widen * iqr, float(q3) + widen * iqr


def resolve_scopes(scope: str, profile: dict, cfg: dict, self_profile_scope: str | None) -> tuple[str | None, str | None, list[str]]:
    """(lens scope, register scope or None, notes). Unknown/empty lens falls back to corpus."""
    scopes = profile.get("scopes") or {}
    notes: list[str] = []

    def usable(name: str | None) -> bool:
        return bool(name) and isinstance(scopes.get(name), dict) and int(scopes[name].get("n") or 0) > 0

    lens = scope if usable(scope) else None
    if lens is None:
        if usable("corpus"):
            lens = "corpus"
            notes.append(f"scope {scope!r} not in profile (or empty); using corpus")
        else:
            return None, None, notes + ["profile has no usable scope"]
    min_self = int((cfg.get("corpus") or {}).get("self_min_samples", 5))
    register = None
    if self_profile_scope and self_profile_scope != lens and usable(self_profile_scope) \
            and int(scopes[self_profile_scope].get("n") or 0) >= min_self:
        register = self_profile_scope
    return lens, register, notes


def _advisory(note: str) -> dict:
    return {"checks": {cid: {"class": "advisory", "pass": True, "note": note} for cid in CHECK_IDS},
            "envelope": {"scope": None, "score": None, "out": [], "note": note}}


def _fail(value, why: str, **extra) -> dict:
    return {"class": "soft", "pass": False, "value": value, "evidence": [{"span": "", "why": why}], **extra}


def _pass(value, **extra) -> dict:
    return {"class": "soft", "pass": True, "value": value, "evidence": [], **extra}


def run_checks(features: dict, scope: str, profile: dict | None, cfg: dict,
               self_profile_scope: str | None = "self", small_corpus: bool = False) -> dict:
    """Contracts section 16. `small_corpus` (tier0 passes common.small_corpus_mode) widens every envelope to
    config `envelope.small_corpus_iqr_widen` and downgrades the four checks to advisory, recording
    `class_original`: an envelope drawn from a handful of posts is a guess, not a gate. A lens scope under
    `envelope.min_scope_n` posts is advisory for the same reason: with a single post q1 == q3, so the
    envelope is a point."""
    if not profile or not profile.get("scopes"):
        return _advisory("no profile")
    lens, register, notes = resolve_scopes(scope, profile, cfg, self_profile_scope)
    if lens is None:
        return _advisory(notes[-1] if notes else "no usable scope")
    scopes = profile["scopes"]
    env_cfg = cfg.get("envelope") or {}
    widen = float(env_cfg.get("iqr_widen", 0.5))
    pass_score = float(env_cfg.get("pass_score", 0.70))
    min_scope_n = int(env_cfg.get("min_scope_n", 4))
    lens_n = int((scopes.get(lens) or {}).get("n") or 0)
    advisory_reason: str | None = None
    if small_corpus:
        widen = float(env_cfg.get("small_corpus_iqr_widen", 1.5))
        advisory_reason = f"small-corpus mode: envelopes widened to {widen} IQR and reported as advisory"
    if lens_n < min_scope_n:
        advisory_reason = f"scope {lens} has n={lens_n} < {min_scope_n}: envelope is a point estimate, advisory only"
    n_sent = int(features.get("n_sentences") or 0)

    def scope_for(path: str) -> str:
        return register if (register and is_register_feature(path)) else lens

    def stats_for(sc: str, path: str) -> dict | None:
        st = ((scopes.get(sc) or {}).get("features") or {}).get(path)
        return st if isinstance(st, dict) else None

    total_w = in_w = 0.0
    out: list[dict] = []
    skipped: list[dict] = []
    for path, w in FEATURE_WEIGHTS:
        value = get_path(features, path)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            skipped.append({"feature": path, "reason": "value missing"})
            continue
        if path.startswith("sent_words.") and n_sent < 3:
            skipped.append({"feature": path, "reason": "fewer than 3 sentences"})
            continue
        sc = scope_for(path)
        bounds = envelope_bounds(stats_for(sc, path) or {}, widen)
        if bounds is None:
            skipped.append({"feature": path, "reason": f"no stats in scope {sc}"})
            continue
        lo, hi = bounds
        total_w += w
        if lo <= float(value) <= hi:
            in_w += w
        else:
            out.append({"feature": path, "value": _r(value), "envelope": [_r(lo), _r(hi)], "scope": sc, "weight": w})
    fw = features.get("function_words")
    centroid = (scopes.get(lens) or {}).get("function_word_centroid")
    max_d = (scopes.get(lens) or {}).get("max_intra_distance")
    dist = cosine_distance(fw, centroid) if isinstance(fw, dict) and isinstance(centroid, dict) else None
    if dist is None or max_d is None:
        skipped.append({"feature": "function_words.cosine_distance", "reason": "no vector or centroid"})
    else:
        total_w += FUNCTION_WORD_WEIGHT
        if dist <= float(max_d):
            in_w += FUNCTION_WORD_WEIGHT
        else:
            out.append({"feature": "function_words.cosine_distance", "value": _r(dist, 6),
                        "envelope": [0.0, _r(max_d, 6)], "scope": lens, "weight": FUNCTION_WORD_WEIGHT})
    score = _r(in_w / total_w) if total_w else None
    e1_pass = score is None or score >= pass_score
    e1 = {"class": "soft", "pass": e1_pass, "score": score, "threshold": pass_score, "scope": lens,
          "register_scope": register, "out": out,
          "evidence": [] if e1_pass else [{"span": "", "why": f"{o['feature']}={o['value']} outside "
                                           f"[{o['envelope'][0]}, {o['envelope'][1]}] ({o['scope']})"} for o in out]}
    if score is None:
        e1["note"] = "no comparable features"
    if notes:
        e1["notes"] = notes

    # P14_dashes
    sc14 = scope_for("punct_per_1k.em_dash")
    dashes = (get_path(features, "punct_per_1k.em_dash") or 0) + (get_path(features, "punct_per_1k.en_dash") or 0)
    b_em = envelope_bounds(stats_for(sc14, "punct_per_1k.em_dash") or {}, widen)
    b_en = envelope_bounds(stats_for(sc14, "punct_per_1k.en_dash") or {}, widen)
    if b_em is None and b_en is None:
        p14 = {"class": "advisory", "pass": True, "value": _r(dashes), "note": f"no dash stats in scope {sc14}"}
    else:
        hi = (b_em[1] if b_em else 0.0) + (b_en[1] if b_en else 0.0)
        if dashes > 0 and dashes > hi:
            p14 = _fail(_r(dashes), f"em+en dashes per 1k chars = {_r(dashes)} exceeds scope {sc14} envelope high "
                                    f"{_r(hi)}", limit=_r(hi), scope=sc14)
        else:
            p14 = _pass(_r(dashes), limit=_r(hi), scope=sc14)

    # P15_burstiness
    sc15 = scope_for("sent_words.cv")
    cv = get_path(features, "sent_words.cv")
    st15 = stats_for(sc15, "sent_words.cv") or {}
    if cv is None or st15.get("q1") is None:
        p15 = {"class": "advisory", "pass": True, "value": _r(cv), "note": f"no sent_words.cv stats in scope {sc15}"}
    elif n_sent < 4:
        p15 = _pass(_r(cv), limit=_r(st15["q1"]), scope=sc15, note="fewer than 4 sentences; not judged")
    elif float(cv) < float(st15["q1"]):
        p15 = _fail(_r(cv), f"sentence-length cv = {_r(cv)} below scope {sc15} q1 {_r(st15['q1'])} (low burstiness)",
                    limit=_r(st15["q1"]), scope=sc15)
    else:
        p15 = _pass(_r(cv), limit=_r(st15["q1"]), scope=sc15)

    # P16_broetry
    pct = features.get("pct_single_sentence_paras")
    st16 = stats_for(lens, "pct_single_sentence_paras") or {}
    med = st16.get("median")
    if pct is None or med is None:
        p16 = {"class": "advisory", "pass": True, "value": _r(pct), "note": f"no pct_single_sentence_paras stats in scope {lens}"}
    elif float(pct) > 0.80 and float(med) < 0.30:
        p16 = _fail(_r(pct), f"{round(100 * float(pct))}% of paragraphs are a single sentence; scope {lens} median is "
                             f"{_r(med)} (broetry)", scope_median=_r(med), scope=lens)
    else:
        p16 = _pass(_r(pct), scope_median=_r(med), scope=lens)

    checks = {"E1_envelope": e1, "P14_dashes": p14, "P15_burstiness": p15, "P16_broetry": p16}
    if advisory_reason:
        for c in checks.values():
            if c.get("class") != "advisory":
                c["class_original"] = c["class"]
                c["class"] = "advisory"
                c["downgraded"] = True
                c["downgrade_reason"] = advisory_reason
            c.setdefault("note", advisory_reason)
    return {"checks": checks,
            "envelope": {"scope": lens, "register_scope": register, "score": score, "out": out, "skipped": skipped,
                         "weights_in": _r(in_w), "weights_total": _r(total_w), "widen": widen, "scope_n": lens_n,
                         "small_corpus_mode": bool(small_corpus), "advisory_reason": advisory_reason}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Envelope checks (E1_envelope, P14_dashes, P15_burstiness, P16_broetry).")
    ap.add_argument("input", help="features .json, or a post .md/.txt (features computed on the fly)")
    ap.add_argument("--scope", default="corpus", help="profile scope, e.g. corpus, self, author:<slug>, platform:x")
    ap.add_argument("--profile", help="profile JSON path (default: style/profile.json)")
    ap.add_argument("--self-scope", default="self", help="register scope name ('' to disable)")
    ap.add_argument("--small-corpus", action="store_true", help="apply the small-corpus widening / advisory rule")
    ap.add_argument("--root", help="project root (default: env POSTSMITH_ROOT / auto-detected)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        apply_root(args.root)
        cfg = common.load_config()
    except FileNotFoundError as exc:
        common.error(str(exc))
        return 0
    src = Path(args.input)
    if not src.is_absolute():
        src = (Path.cwd() / src) if (Path.cwd() / src).exists() else common.ROOT / src
    if not src.exists():
        common.error(f"input not found: {args.input}")
        return 0
    try:
        if src.suffix.lower() == ".json":
            features = json.loads(src.read_text(encoding="utf-8"))
        else:
            lexicon, patterns = stylometry.load_optional_lexicon_patterns()
            features = stylometry.features_for_file(src, lexicon=lexicon, patterns=patterns)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        common.error(f"cannot parse input: {exc}")
        return 0
    if not isinstance(features, dict):
        common.error("features file must contain a JSON object")
        return 0
    if args.profile:
        p = Path(args.profile)
        p = p if p.is_absolute() else common.ROOT / p
        if not p.exists():
            common.error(f"profile not found: {args.profile}")
            return 0
        profile = json.loads(p.read_text(encoding="utf-8"))
    else:
        profile = common.load_profile()
    result = run_checks(features, args.scope, profile, cfg, args.self_scope or None, small_corpus=args.small_corpus)
    emit({"ok": True, **result})
    return 0


if __name__ == "__main__":
    sys.exit(main())
