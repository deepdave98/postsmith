#!/usr/bin/env python3
"""Build `style/profile.json` (contracts.md section 3) from the per-post feature files.

Scopes: `corpus` (train + self), `self`, `platform:linkedin`, `platform:x` and `author:<slug>` (train posts
of an author with n >= config `corpus.author_profile_min_posts`). Heldout posts never contribute. Each scope
holds, per dotted numeric feature path, `{median, q1, q3, min, max, n}`, the function-word centroid (mean
vector over English posts), `max_intra_distance` (largest cosine distance of a member post to that centroid)
and `media_rate` (fraction of posts with usable media).

`base_rates` = fraction of corpus posts failing P8_opener, P10_contrast_flip, P12_closer and P17_lists (via
`ai_tells.run_checks`), P6_emoji (via `platform_check.run_checks`), P16_broetry
(pct_single_sentence_paras > 0.80) and P14_dashes (any em/en dash). Both check modules are hard imports; one
that raises propagates. `base_rates_note` says why the rates are empty. A post with no features file is
computed on the fly and listed in `notes`.

Versioning: on `--write`, when the scopes or base_rates differ from the current `style/profile.json`, that
file is kept as `style/profile.p<N>.json` and `profile_version` becomes N+1; an unchanged profile keeps its
version. `corpus_hash` = sha256 over the sorted content hashes of the member posts.

CLI: `profile_stats.py [--write] [--root R] [--json]` prints the profile (dry run unless --write).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_tells  # noqa: E402
import common  # noqa: E402
import platform_check  # noqa: E402
import stylometry  # noqa: E402
from common import emit, median, now_iso, quantile, sha256_text  # noqa: E402
from stylometry import apply_root, cosine_distance, flatten_numeric, get_path  # noqa: E402

BASE_RATE_IDS = ["P8_opener", "P10_contrast_flip", "P12_closer", "P17_lists", "P16_broetry", "P14_dashes", "P6_emoji"]
AI_TELLS_IDS = ("P8_opener", "P10_contrast_flip", "P12_closer", "P17_lists")
PLATFORM_IDS = ("P6_emoji",)
PROFILE_PATH = Path("style") / "profile.json"


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


# --------------------------------------------------------------------------- collection


def collect_posts(splits: tuple[str, ...] = ("train", "self"), lexicon: dict | None = None,
                  patterns: dict | None = None) -> tuple[list[dict], list[str]]:
    """Rows of {post_id, split, platform, lang, author_slug, meta, text, features, content_sha} plus notes."""
    rows: list[dict] = []
    notes: list[str] = []
    for split in splits:
        for meta, text, path in common.iter_posts((split,)):
            post_id = str(meta.get("post_id") or path.stem)
            platform = str(meta.get("platform") or "linkedin")
            lang = str(meta.get("lang") or common.detect_lang(text))
            feat = common.read_json(stylometry.features_dir_for(split) / f"{post_id}.json", None)
            if not isinstance(feat, dict):
                feat = stylometry.features(text, platform, lang, lexicon, patterns, post_id=post_id)
                notes.append(f"{post_id}: no features file, computed on the fly")
            author = meta.get("author") if isinstance(meta.get("author"), dict) else {}
            rows.append({
                "post_id": post_id, "split": split, "platform": platform, "lang": lang,
                "author_slug": str(author.get("slug") or "") or None, "meta": meta, "text": text, "features": feat,
                "content_sha": str(meta.get("content_sha256") or common.content_sha(text)),
            })
    return rows, notes


def corpus_hash(rows: list[dict]) -> str:
    return sha256_text("\n".join(sorted(r["content_sha"] for r in rows)))


# --------------------------------------------------------------------------- scope statistics


def _has_media(meta: dict) -> bool:
    media = meta.get("media") or []
    return any(isinstance(m, dict) and m.get("kind") not in (None, "unavailable") for m in media)


def scope_stats(rows: list[dict]) -> dict:
    """`{n, features, function_word_centroid, max_intra_distance, media_rate}` for one scope."""
    flat = [flatten_numeric(r["features"]) for r in rows]
    paths = sorted({p for f in flat for p in f})
    feats: dict[str, dict] = {}
    for p in paths:
        vals = [f[p] for f in flat if p in f]
        if not vals:
            continue
        feats[p] = {"median": _r(median(vals)), "q1": _r(quantile(vals, 0.25)), "q3": _r(quantile(vals, 0.75)),
                    "min": _r(min(vals)), "max": _r(max(vals)), "n": len(vals)}
    vectors = [r["features"].get("function_words") for r in rows if isinstance(r["features"].get("function_words"), dict)]
    centroid: dict[str, float] = {}
    max_d: float | None = None
    if vectors:
        keys = sorted({k for v in vectors for k in v})
        centroid = {k: _r(sum(float(v.get(k) or 0.0) for v in vectors) / len(vectors), 5) for k in keys}
        dists = [d for d in (cosine_distance(v, centroid) for v in vectors) if d is not None]
        max_d = _r(max(dists), 6) if dists else None
    return {
        "n": len(rows),
        "features": feats,
        "function_word_centroid": centroid,
        "max_intra_distance": max_d,
        "media_rate": _r(sum(1 for r in rows if _has_media(r["meta"])) / len(rows)) if rows else None,
    }


def build_scopes(rows: list[dict], cfg: dict) -> dict:
    min_author = int((cfg.get("corpus") or {}).get("author_profile_min_posts", 6))
    scopes = {
        "corpus": scope_stats(rows),
        "self": scope_stats([r for r in rows if r["split"] == "self"]),
        "platform:linkedin": scope_stats([r for r in rows if r["platform"] == "linkedin"]),
        "platform:x": scope_stats([r for r in rows if r["platform"] == "x"]),
    }
    by_author: dict[str, list[dict]] = {}
    for r in rows:
        if r["split"] != "self" and r["author_slug"]:
            by_author.setdefault(r["author_slug"], []).append(r)
    for slug in sorted(by_author):
        if len(by_author[slug]) >= min_author:
            scopes[f"author:{slug}"] = scope_stats(by_author[slug])
    return scopes


# --------------------------------------------------------------------------- base rates


def compute_base_rates(rows: list[dict], cfg: dict, lexicon: dict | None, patterns: dict | None) -> tuple[dict, str | None]:
    """Fraction of rows failing each BASE_RATE_IDS check. No base rates are passed in, so the raw rate is
    measured. Returns ({}, note) only when there are no rows; a check module that raises propagates."""
    if not rows:
        return {}, "no corpus posts"
    hits = {cid: 0 for cid in BASE_RATE_IDS}
    for r in rows:
        meta = {"platform": r["platform"], "post_id": r["post_id"], "author": r["meta"].get("author")}
        checks = ai_tells.run_checks(r["text"], r["platform"], meta, cfg, lexicon or {}, patterns or {}, None)["checks"]
        for cid in AI_TELLS_IDS:
            if isinstance(checks.get(cid), dict) and checks[cid].get("pass") is False:
                hits[cid] += 1
        checks = platform_check.run_checks(r["text"], r["platform"], meta, cfg)["checks"]
        for cid in PLATFORM_IDS:
            if isinstance(checks.get(cid), dict) and checks[cid].get("pass") is False:
                hits[cid] += 1
        feat = r["features"]
        if (feat.get("pct_single_sentence_paras") or 0) > 0.80:
            hits["P16_broetry"] += 1
        if (get_path(feat, "punct_per_1k.em_dash") or 0) + (get_path(feat, "punct_per_1k.en_dash") or 0) > 0:
            hits["P14_dashes"] += 1
    rates = {cid: _r(hits[cid] / len(rows)) for cid in BASE_RATE_IDS}
    return rates, None


# --------------------------------------------------------------------------- build & write


def build_profile(cfg: dict | None = None, lexicon: dict | None = None, patterns: dict | None = None) -> dict:
    cfg = cfg or common.load_config()
    rows, notes = collect_posts(lexicon=lexicon, patterns=patterns)
    base_rates, br_note = compute_base_rates(rows, cfg, lexicon, patterns)
    profile = {
        "profile_version": None,
        "corpus_hash": corpus_hash(rows),
        "generated_at": now_iso(),
        "n_posts": len(rows),
        "scopes": build_scopes(rows, cfg),
        "base_rates": base_rates,
    }
    if br_note:
        profile["base_rates_note"] = br_note
    if notes:
        profile["notes"] = notes
    return profile


def _same_profile(a: dict | None, b: dict) -> bool:
    if not a:
        return False
    key = lambda p: json.dumps({"scopes": p.get("scopes"), "base_rates": p.get("base_rates")}, sort_keys=True)  # noqa: E731
    return key(a) == key(b)


def next_version(profile: dict, previous: dict | None) -> int:
    if not previous:
        return 1
    prev_v = int(previous.get("profile_version") or 0)
    return prev_v if _same_profile(previous, profile) else prev_v + 1


def write_profile(profile: dict) -> dict:
    """Write style/profile.json, keeping the previous version as style/profile.p<N>.json when it changed."""
    previous = common.load_profile()
    version = next_version(profile, previous)
    backup = None
    if previous and version != int(previous.get("profile_version") or 0):
        backup = Path("style") / f"profile.p{int(previous.get('profile_version') or 0)}.json"
        common.write_json(backup, previous)
    profile = dict(profile, profile_version=version)
    common.write_json(PROFILE_PATH, profile)
    return {"written": True, "path": str(PROFILE_PATH), "previous": str(backup) if backup else None, **profile}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build style/profile.json envelopes from corpus feature files.")
    ap.add_argument("--write", action="store_true", help="write style/profile.json (default: dry run)")
    ap.add_argument("--root", help="project root (default: env POSTSMITH_ROOT / auto-detected)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        apply_root(args.root)
        cfg = common.load_config()
    except FileNotFoundError as exc:
        common.error(str(exc))
        return 0
    lexicon, patterns = stylometry.load_optional_lexicon_patterns()
    profile = build_profile(cfg, lexicon, patterns)
    if profile["n_posts"] == 0:
        common.error("no corpus posts found under corpus/posts or corpus/self")
        return 0
    if args.write:
        emit({"ok": True, **write_profile(profile)})
    else:
        profile["profile_version"] = next_version(profile, common.load_profile())
        emit({"ok": True, "written": False, "path": str(PROFILE_PATH), "previous": None, **profile})
    return 0


if __name__ == "__main__":
    sys.exit(main())
