#!/usr/bin/env python3
"""metrics_parse.py: natural-language engagement metrics -> dict (used by /posted).

    '12k views 40 comments 3 reposts 2 saves 5 follows 1.2M impressions' ->
    {"views": 1200000, "comments": 40, "reposts": 3, "saves": 2, "follows": 5}

Rules: k = x1e3, m = x1e6, b = x1e9 (case-insensitive), commas allowed ('1,234'); the number may precede or
follow its key ('views 12k', 'views: 12k', '12k views'); synonyms fold to canonical keys (views/impressions
-> views, likes/reactions -> likes, comments/replies -> comments, reposts/reshares/retweets/shares ->
reposts, saves/bookmarks -> saves, follows/followers -> follows). A repeated key keeps the last value and
adds a warning. '--after 24h|7d' durations come back as after_hours. Unrecognised tokens are listed.

CLI: uv run tools/metrics_parse.py "12k views 40 comments" [--json]
API: parse(text) -> {"ok": bool, "metrics": {...}, "after_hours": int|None, "unparsed": [...], "warnings": [...]}
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SYNONYMS = {
    "view": "views", "views": "views", "impression": "views", "impressions": "views", "imp": "views",
    "like": "likes", "likes": "likes", "reaction": "likes", "reactions": "likes", "hearts": "likes", "heart": "likes",
    "comment": "comments", "comments": "comments", "reply": "comments", "replies": "comments",
    "repost": "reposts", "reposts": "reposts", "reshare": "reposts", "reshares": "reposts",
    "retweet": "reposts", "retweets": "reposts", "rt": "reposts", "rts": "reposts", "share": "reposts", "shares": "reposts",
    "save": "saves", "saves": "saves", "bookmark": "saves", "bookmarks": "saves",
    "follow": "follows", "follows": "follows", "follower": "follows", "followers": "follows", "newfollowers": "follows",
    "click": "clicks", "clicks": "clicks", "profileviews": "profile_views", "profile_views": "profile_views",
}
CANONICAL = ["views", "likes", "comments", "reposts", "saves", "follows", "clicks", "profile_views"]
MULT = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}

_NUM_RE = re.compile(r"^(\d[\d,]*(?:\.\d+)?|\.\d+)([kKmMbB])?$")
_AFTER_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|d|day|days|w|wk|week|weeks)$", re.IGNORECASE)
# words (with '--after'), numbers with a glued suffix ('12k', '1,234', '24h', '12kviews'), single symbols
_TOKEN_RE = re.compile(r"-{0,2}[A-Za-z_]+|\d[\d,]*(?:\.\d+)?[A-Za-z]*|\.\d+[A-Za-z]*|[^\sA-Za-z0-9]")


def parse_number(tok: str) -> int | None:
    """'12k' -> 12000, '1.2M' -> 1200000, '1,234' -> 1234. None when not a number."""
    m = _NUM_RE.match(tok.strip())
    if not m:
        return None
    body, suffix = m.group(1), m.group(2)
    try:
        val = float(body.replace(",", ""))
    except ValueError:
        return None
    if suffix:
        val *= MULT[suffix.lower()]
    return round(val)


def _canon_key(word: str) -> str | None:
    w = word.lower().strip("_")
    if w in SYNONYMS:
        return SYNONYMS[w]
    if w.startswith("new") and w[3:] in SYNONYMS:
        return SYNONYMS[w[3:]]
    return None


def _duration_hours(tok: str) -> int | None:
    m = _AFTER_RE.match(tok)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        return round(val)
    if unit.startswith("d"):
        return round(val * 24)
    return round(val * 24 * 7)


def parse(text: str) -> dict:
    """Parse free-text metrics. Never raises on user text."""
    metrics: dict[str, int] = {}
    unparsed: list[str] = []
    warnings: list[str] = []
    after_hours: int | None = None
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "empty metrics text", "metrics": {}, "after_hours": None,
                "unparsed": [], "warnings": []}
    toks = [t for t in _TOKEN_RE.findall(text) if t.strip() and t not in (":", "=", ",", ";", "·", "-", "—")]
    i = 0
    pending_number: int | None = None
    pending_number_tok: str | None = None
    while i < len(toks):
        tok = toks[i]
        low = tok.lower()
        if low in ("--after", "after", "at", "@"):
            # duration follows: '24h' or '7 d'
            j = i + 1
            if j < len(toks):
                dur = _duration_hours(toks[j])
                if dur is None and j + 1 < len(toks):
                    dur = _duration_hours(toks[j] + toks[j + 1])
                    if dur is not None:
                        j += 1
                if dur is not None:
                    after_hours = dur
                    i = j + 1
                    continue
            if low in ("--after", "after"):
                unparsed.append(tok)
            i += 1
            continue
        dur = _duration_hours(tok)
        if dur is not None and pending_number is None:
            after_hours = dur
            i += 1
            continue
        num = parse_number(tok)
        if num is not None:
            if pending_number is not None:
                unparsed.append(pending_number_tok or str(pending_number))
            pending_number, pending_number_tok = num, tok
            i += 1
            continue
        key = _canon_key(tok)
        if key is not None:
            if pending_number is not None:
                _set(metrics, key, pending_number, warnings)
                pending_number, pending_number_tok = None, None
            elif i + 1 < len(toks) and parse_number(toks[i + 1]) is not None:
                _set(metrics, key, parse_number(toks[i + 1]), warnings)  # type: ignore[arg-type]
                i += 1
            else:
                unparsed.append(tok)
            i += 1
            continue
        # '12kviews' is rare but happens: split the number off the unit
        gm = re.match(r"^(\d[\d,]*(?:\.\d+)?[kKmMbB]?)([A-Za-z_]+)$", tok)
        if gm and _canon_key(gm.group(2)) and parse_number(gm.group(1)) is not None:
            _set(metrics, _canon_key(gm.group(2)), parse_number(gm.group(1)), warnings)  # type: ignore[arg-type]
            i += 1
            continue
        if low not in ("and", "with", "of", "the", "a"):
            unparsed.append(tok)
        i += 1
    if pending_number is not None:
        unparsed.append(pending_number_tok or str(pending_number))
    ok = bool(metrics)
    doc = {"ok": ok, "metrics": {k: metrics[k] for k in CANONICAL if k in metrics},
           "after_hours": after_hours, "unparsed": unparsed, "warnings": warnings}
    if not ok:
        doc["error"] = "no metrics recognised (expected e.g. '12k views 40 comments 3 reposts')"
    return doc


def _set(metrics: dict, key: str, value: int, warnings: list[str]) -> None:
    if key in metrics and metrics[key] != value:
        warnings.append(f"{key} given twice; keeping {value}")
    metrics[key] = value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse '12k views 40 comments 3 reposts' into a metrics dict.")
    ap.add_argument("text", nargs="*", help="metrics text (all positional words are joined)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    text = " ".join(args.text)
    common.emit(parse(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
