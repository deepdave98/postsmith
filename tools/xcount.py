#!/usr/bin/env python3
"""Count a post the way X does. CLI wrapper over common.x_count.

Rules (config `platforms.x`): NFC-normalized code points count 1, URLs count `url_weight` (23), emoji
`emoji_weight` (2), CJK `cjk_weight` (2). Prints {"x_len": N, "over": bool, "limit": 280}.

Usage:
    xcount.py <file>                 file with or without front matter; the body is counted
    xcount.py -                      read the text from stdin
    xcount.py --text "..."           count a literal string
    xcount.py <file> --limit 25000   compare against another limit (default: platforms.x.max_chars)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, emit, error, load_config, split_front_matter, x_count


def count(text: str, limit: int | None = None, cfg: dict | None = None) -> dict:
    """Pure helper: {"x_len", "over", "limit"} for `text`. Trailing newlines are ignored."""
    xcfg = (cfg or load_config())["platforms"]["x"]
    limit = int(xcfg.get("max_chars", 280)) if limit is None else int(limit)
    n = x_count(text.replace("\r\n", "\n").rstrip("\n"), xcfg)
    return {"x_len": n, "over": n > limit, "limit": limit}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Count characters the way X does (URL=23, emoji=2, CJK=2).")
    ap.add_argument("source", nargs="?", help="file to count (front matter is skipped) or '-' for stdin")
    ap.add_argument("--text", help="count this literal string instead of a file")
    ap.add_argument("--limit", type=int, help="limit to compare against (default: config platforms.x.max_chars)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON; accepted for uniformity)")
    args = ap.parse_args(argv)

    if args.text is not None:
        text = args.text
    elif args.source == "-":
        text = sys.stdin.read()
    elif args.source:
        p = Path(args.source)
        if not p.is_absolute():
            p = (ROOT / p) if (ROOT / p).exists() else p.resolve()
        if not p.exists() or not p.is_file():
            error(f"file not found: {args.source}")
            return 0
        try:
            raw = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            error(f"not a UTF-8 text file: {args.source}")
            return 0
        try:
            _, text = split_front_matter(raw)
        except Exception as exc:  # noqa: BLE001 - malformed YAML front matter
            error(f"bad front matter in {args.source}: {exc}")
            return 0
    else:
        error("nothing to count: pass a file, '-' for stdin, or --text")
        return 0
    if args.limit is not None and args.limit <= 0:
        error("--limit must be a positive integer")
        return 0
    emit(count(text, args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
