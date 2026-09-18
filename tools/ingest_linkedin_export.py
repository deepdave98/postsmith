#!/usr/bin/env python3
"""Convert a packaged LinkedIn creator export into the ingest JSON that `ingest_normalize.py` reads.

The export is the bundle shipped as `linkedin-style-corpus.json` beside an `assets/` tree: creator groups,
one record per scraped post, every text block carrying `eligible_for_feed_creator_style`. Only eligible
blocks become corpus posts, so a third-party repost sitting in a creator's feed never teaches that creator's
voice. A quote post contributes the creator's own commentary, with the quoted original carried in `context`
(the comment is unreadable without it) and the quoted post's media attached, because that media is what the
comment points at.

Every row is tagged `lang: en` by default. These exports are English-language feeds, and the stopword
detector reads a three-word caption like "Apple Feet ID" as another language, which would drop the post out
of the envelope statistics. Pass `--lang auto` for a genuinely multilingual export.

Assets are staged next to the output file (`assets/<ref>/<name>`) so the JSON stays portable and
`ingest_normalize.py` resolves the relative paths. Derived files (storyboards, rendered PDF pages, video
thumbnails) are dropped: `media_prepare.py` builds its own previews, frames and contact sheets from the
originals, and a poster frame handed over as a second image would show up in the card as media the post did
not have.

Re-running is safe: same export in, same rows out, and `ingest_commit.py` dedupes on content hash, so a
later bundle that repeats posts adds only what is new.

CLI: uv run tools/ingest_linkedin_export.py <export dir | export.json> [--out PATH] [--only slug,slug]
     [--no-assets] [--json]
Prints `{"ok", "rows", "creators": {name: n}, "classifications": {...}, "assets_staged", "out",
"skipped": [...], "warnings": [...]}`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import ingest_normalize  # noqa: E402
import stylometry  # noqa: E402

# The roles that are part of how the post appeared. video_thumbnail and *_storyboard are LinkedIn's or the
# packager's derivations of the video; document_rendered_page and document_cover_page derive from the PDF.
SOURCE_ROLES = ("primary_image", "primary_video", "document_pdf", "article_preview")


def load_export(source: Path) -> tuple[dict, Path]:
    """(export dict, directory the local_paths are relative to)."""
    path = source
    if path.is_dir():
        candidates = sorted(path.glob("*.json"))
        named = [p for p in candidates if "corpus" in p.stem]
        if not candidates:
            raise ValueError(f"no .json file in {common.rel(path)}")
        path = named[0] if named else candidates[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "creator_groups" not in data:
        raise ValueError(f"{common.rel(path)} is not a packaged creator export (no creator_groups)")
    return data, path.parent


def _assets_by_id(post: dict) -> dict[str, dict]:
    return {str(a.get("asset_id")): a for a in (post.get("assets") or []) if isinstance(a, dict)}


def _quoted_block(post: dict) -> dict | None:
    for tb in post.get("text_blocks") or []:
        if isinstance(tb, dict) and tb.get("role") == "quoted_original":
            return tb
    return None


def _describe(asset: dict, quoted: bool) -> str:
    """A factual note only: what the file is and how big. The annotator looks at the file; it is never told
    what the media means."""
    bits = [str(asset.get("role") or asset.get("kind") or "media").replace("_", " ")]
    if quoted:
        bits.append("belongs to the quoted post, not to the comment")
    w, h = asset.get("width"), asset.get("height")
    if w and h:
        bits.append(f"{w}x{h}")
    dur = asset.get("duration_seconds")
    if dur and str(asset.get("kind")) == "video":
        bits.append(f"{float(dur):.0f}s")
    if asset.get("page_number"):
        bits.append(f"page {asset['page_number']}")
    return ", ".join(bits)


def block_assets(post: dict, block: dict) -> list[tuple[dict, bool]]:
    """[(asset, from_the_quoted_post)] for one text block, originals only, in export order."""
    by_id = _assets_by_id(post)
    ids = [str(i) for i in (block.get("asset_ids") or [])]
    quoted = False
    if not ids:
        qb = _quoted_block(post)
        if qb is not None and block.get("role") == "creator_commentary":
            ids = [str(i) for i in (qb.get("asset_ids") or [])]
            quoted = True
    out = []
    for aid in ids:
        a = by_id.get(aid)
        if not a or a.get("generated") or str(a.get("role")) not in SOURCE_ROLES:
            continue
        if str(a.get("download_status") or "") != "downloaded_and_verified" or not a.get("local_path"):
            continue
        out.append((a, quoted))
    return out


def context_for(post: dict, block: dict) -> str | None:
    """What a reader saw but this text does not say: the quoted original, or a creator's own re-share."""
    if str(post.get("classification")) == "quote" and block.get("role") == "creator_commentary":
        qb = _quoted_block(post)
        if qb is None:
            return "This is a comment on a quoted post; the quoted post was not captured."
        author = ((qb.get("author") or {}).get("name") or "someone else") if isinstance(qb.get("author"), dict) else "someone else"
        text = str(qb.get("exact_text") or "").strip()
        return (f"This post is a comment on someone else's post, shown above it in the feed. "
                f"The quoted post, by {author}, reads:\n{text}")
    if post.get("is_self_repost"):
        return "The creator re-shared this post of their own; the text is theirs."
    return None


def build_rows(export: dict, base: Path, only: set[str] | None = None,
               lang: str | None = "en") -> tuple[list[dict], dict]:
    rows: list[dict] = []
    report: dict[str, Any] = {"creators": {}, "classifications": {}, "skipped": [], "warnings": []}
    for group in export.get("creator_groups") or []:
        creator = (group.get("creator") or {})
        key = str(creator.get("creator_key") or "")
        name = str(creator.get("display_name") or key)
        if only and key not in only and ingest_normalize.slugify(name) not in only:
            continue
        for post in group.get("posts") or []:
            ref = str(post.get("ref") or "?")
            cls = str(post.get("classification") or "original")
            for block in post.get("text_blocks") or []:
                if not isinstance(block, dict) or not block.get("eligible_for_feed_creator_style"):
                    continue
                text = str(block.get("exact_text") or "")
                if not text.strip():
                    report["skipped"].append({"ref": ref, "reason": "empty text"})
                    continue
                pub = block.get("published_at") or (post.get("chronology") or {}).get("timestamp") or {}
                eng = post.get("engagement") or {}
                media = []
                for asset, quoted in block_assets(post, block):
                    media.append({"asset": asset, "quoted": quoted, "ref": ref})
                rows.append({
                    "author": name,
                    "platform": "linkedin",
                    "lang": lang,
                    "text": text,
                    "posted_at": (pub or {}).get("date"),
                    "url": block.get("source_url") or (post.get("source_links") or {}).get("post_url"),
                    "likes": eng.get("total_reactions"),
                    "comments": eng.get("comments"),
                    "reposts": eng.get("shares"),
                    "context": context_for(post, block),
                    "_media": media,
                })
                report["creators"][name] = report["creators"].get(name, 0) + 1
                report["classifications"][cls] = report["classifications"].get(cls, 0) + 1
    for r in rows:
        for m in r["_media"]:
            if not (base / str(m["asset"].get("local_path"))).is_file():
                report["warnings"].append(f"{m['ref']}: missing asset file {m['asset'].get('local_path')}")
    return rows, report


def stage_assets(rows: list[dict], base: Path, out_dir: Path, copy: bool) -> int:
    """Copy each row's originals to <out_dir>/assets/<ref>/<filename> and rewrite media to relative paths."""
    staged = 0
    for row in rows:
        media = []
        for m in row.pop("_media"):
            asset, ref = m["asset"], m["ref"]
            src = base / str(asset.get("local_path"))
            rel = f"assets/{ref}/{Path(str(asset.get('local_path'))).name}"
            dest = out_dir / rel
            if copy and src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
                    shutil.copy2(src, dest)
                staged += 1
            elif not src.is_file():
                continue
            media.append({"path_or_url": rel, "description": _describe(asset, m["quoted"])})
        row["media"] = media
    return staged


def convert(source: Path | str, out: Path | str | None = None, only: set[str] | None = None,
            copy_assets: bool = True, lang: str | None = "en") -> dict:
    src = Path(source).expanduser()
    if not src.exists():
        return {"ok": False, "error": f"no such export: {src}"}
    try:
        export, base = load_export(src)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)}
    rows, report = build_rows(export, base, only, lang)
    if not rows:
        return {"ok": False, "error": "no eligible text blocks in this export", **report}
    corpus_id = str(export.get("corpus_id") or "linkedin-export")
    out_path = Path(out).expanduser() if out else common.ROOT / "corpus" / "inbox" / f"{corpus_id}.json"
    if not out_path.is_absolute():
        out_path = common.ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    staged = stage_assets(rows, base, out_path.parent, copy_assets)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"ok": True, "rows": len(rows), "creators": report["creators"],
            "classifications": report["classifications"], "assets_staged": staged,
            "out": common.rel(out_path), "skipped": report["skipped"], "warnings": report["warnings"],
            "source": str(base)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert a packaged LinkedIn creator export into the canonical "
                                             "ingest JSON (feeds ingest_normalize.py).")
    ap.add_argument("export", help="the export directory or its .json file")
    ap.add_argument("--out", default=None, help="output JSON (default corpus/inbox/<corpus_id>.json)")
    ap.add_argument("--only", default=None, help="comma-separated creator keys or slugs to include")
    ap.add_argument("--no-assets", action="store_true", help="do not copy media files next to the output")
    ap.add_argument("--lang", default="en", help="language tag for every row, or 'auto' to let the stopword "
                                                "detector decide (it reads a three-word caption as 'other')")
    ap.add_argument("--root", default=None, help="project root")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    if args.root:
        stylometry.apply_root(args.root)
    only = {s.strip() for s in args.only.split(",") if s.strip()} if args.only else None
    res = convert(args.export, args.out, only, not args.no_assets,
                  None if args.lang == "auto" else args.lang)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
