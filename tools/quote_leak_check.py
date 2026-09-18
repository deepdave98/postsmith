#!/usr/bin/env python3
"""Heldout quote-leak check: no writer-visible file may share a word 6-gram with any heldout post.

Scanned by default: style/**/*.md, drafts/*/brief.md, memory/lessons.md, memory/topics.md, plus any
candidate or final files passed as positional arguments. Whole files are scanned, front matter included, so
a quote leaked into a metadata field is caught too. Files under corpus/heldout/ are never scanned: they are
the reference.

Output: {"ok": bool, "leaks": [{"file", "heldout_id", "span", "n"}], "scanned": [...], "heldout_posts": int}
Exit code is always 0; `ok` is false when leaks exist or on a user error.

CLI:  uv run tools/quote_leak_check.py [files...] [--root R] [--json]
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import split_front_matter, word_ngrams  # noqa: E402
from overlap_check import (  # noqa: E402
    UserError,
    _entry,
    _relpath,
    load_cfg,
    overlap_cfg,
    prepare,
    resolve_root,
    shared_runs,
    span_of,
)

DEFAULT_GLOBS = ("style/**/*.md", "drafts/*/brief.md", "memory/lessons.md", "memory/topics.md")


def default_files(root: Path) -> list[Path]:
    """Writer-visible files that exist under root, sorted, deduplicated."""
    seen: set[Path] = set()
    out: list[Path] = []
    for pattern in DEFAULT_GLOBS:
        for p in sorted(root.glob(pattern)):
            if p.is_file():
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(rp)
    return out


def build_heldout_index(root: Path, n: int) -> dict:
    """{"posts": {post_id: entry}, "ngrams": {gram: [post_id, ...]}} over corpus/heldout/*.md, built once."""
    posts: dict[str, dict] = {}
    d = root / "corpus" / "heldout"
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            meta, body = split_front_matter(p.read_text(encoding="utf-8"))
            pid = str((meta or {}).get("post_id") or p.stem)
            posts[pid] = _entry(pid, body.rstrip("\n"), path=_relpath(p, root))
    inv: dict[tuple[str, ...], list[str]] = {}
    for pid, e in posts.items():
        for g in word_ngrams(e["tokens"], n):
            inv.setdefault(g, []).append(pid)
    return {"posts": posts, "ngrams": inv, "n": n}


def scan_text(raw: str, index: dict) -> list[dict]:
    """Maximal shared word runs (>= n) between a text and every heldout post: [{heldout_id, span, n}]."""
    n = index["n"]
    prep = prepare(raw)
    refs: set[str] = set()
    for g in word_ngrams(prep.tokens, n):
        ids = index["ngrams"].get(g)
        if ids:
            refs.update(ids)
    leaks: list[dict] = []
    for pid in sorted(refs):
        for i, _j, length in shared_runs(prep.tokens, index["posts"][pid]["tokens"], n):
            leaks.append({"heldout_id": pid, "span": span_of(prep, i, i + length), "n": length})
    return leaks


def _is_under(p: Path, d: Path) -> bool:
    try:
        p.resolve().relative_to(d.resolve())
        return True
    except ValueError:
        return False


def scan(root: str | Path | None = None, files: Iterable[str | Path] | None = None, n: int | None = None) -> dict:
    """Scan the default writer-visible files plus `files` for heldout 6-grams. UserError on bad input."""
    root = resolve_root(root)
    if not root.is_dir():
        raise UserError(f"root is not a directory: {root}")
    n = int(n or overlap_cfg(load_cfg(root))["ngram_flag"])
    index = build_heldout_index(root, n)
    targets = default_files(root)
    skipped: list[str] = []
    for f in files or []:
        p = Path(f).expanduser()
        if not p.is_absolute():
            p = p.resolve() if p.exists() else (root / p).resolve()
        if not p.is_file():
            raise UserError(f"file not found: {f}")
        if _is_under(p, root / "corpus" / "heldout"):
            skipped.append(_relpath(p, root))
            continue
        if p not in targets:
            targets.append(p)
    leaks: list[dict] = []
    for p in targets:
        raw = p.read_text(encoding="utf-8", errors="replace")
        for hit in scan_text(raw, index):
            leaks.append({"file": _relpath(p, root), **hit})
    leaks.sort(key=lambda h: (h["file"], h["heldout_id"], -h["n"], h["span"]))
    return {
        "ok": not leaks,
        "leaks": leaks,
        "n": n,
        "heldout_posts": len(index["posts"]),
        "scanned": [_relpath(p, root) for p in targets],
        "skipped_heldout_inputs": skipped,
    }


def _human(out: dict) -> str:
    if out["ok"]:
        return f"quote leak: clean ({len(out['scanned'])} files vs {out['heldout_posts']} heldout posts)"
    lines = [f"quote leak: {len(out['leaks'])} leak(s) found"]
    for h in out["leaks"]:
        lines.append(f"  {h['file']} <- {h['heldout_id']} ({h['n']} words): {h['span'][:90]!r}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fail when any writer-visible file shares a word 6-gram with a heldout post")
    ap.add_argument("files", nargs="*", help="extra files to scan (candidates, finals)")
    ap.add_argument("--root", help="project root (default: $POSTSMITH_ROOT or the repo containing tools/)")
    ap.add_argument("--n", type=int, help="n-gram size (default: config overlap.ngram_flag = 6)")
    ap.add_argument("--json", action="store_true", help="JSON output (the default)")
    ap.add_argument("--human", action="store_true", help="short human summary instead of JSON")
    args = ap.parse_args(argv)
    try:
        out = scan(args.root, args.files, args.n)
    except UserError as e:
        common.error(str(e), as_json=True)
        return 0
    except (OSError, UnicodeDecodeError) as e:
        common.error(f"{type(e).__name__}: {e}", as_json=True)
        return 0
    except Exception as e:  # noqa: BLE001 - programmer error: contract says exit 2
        if common.yaml is not None and isinstance(e, common.yaml.YAMLError):
            common.error(f"invalid YAML: {e}", as_json=True)
            return 0
        common.emit({"ok": False, "error": f"internal error: {type(e).__name__}: {e}"})
        return 2
    common.emit(out, as_json=not args.human or args.json, human=_human(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
