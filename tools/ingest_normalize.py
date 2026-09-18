#!/usr/bin/env python3
"""ingest_normalize.py: map a CSV / JSON / Markdown source onto one row shape (contracts section 17).

    uv run tools/ingest_normalize.py <source> [--kind csv|json|md|auto] [--author X] [--platform linkedin|x]
                                     [--self] [--mapping '{"text": "Post Body"}'] [--root R] [--json]

Writes `corpus/inbox/normalized_<sha>.jsonl` (sha = sha256 of the source bytes, first 16 hex chars), one row
per post:

    {author_name, author_slug, author_handle, platform, text, posted_at, url, context,
     engagement: {likes, comments, reposts, views}, media: [{path_or_url, description}], transcript,
     source_ref, source_kind, source_file, lang}

and prints `{"ok", "rows", "unmapped_columns", "needs", "file", ...}`. `needs` lists what the tool could
not decide on its own ("text", "author", "platform"); the file is written anyway so the caller can inspect
it, and `ingest_commit.py` refuses rows that are still incomplete. Re-run with `--author`, `--platform` or
`--mapping`.

Sources:
- CSV: UTF-8 or UTF-8 with BOM, delimiter sniffed (`,` `;` tab), header on row 1, multi-line cells quoted.
- JSON: an array of objects, an object holding such an array under `posts|rows|items|data`, or JSON Lines.
- Markdown: one post per file (YAML front matter + text) or several posts separated by a line holding only
  `---`, each block starting with `key: value` header lines, a blank line, then the text. A front-matter file
  whose body also carries `---` separators is read as front-matter post + header-line blocks.

Header synonyms (case-insensitive; spaces, underscores and hyphens are equivalent) are in SYNONYMS.
`--mapping` is a JSON object `{canonical: source column}` that overrides the synonym table for that source.

Platform: an explicit column wins, then the url domain (linkedin.com -> linkedin, x.com / twitter.com -> x),
then `--platform`, then inference (at most 280 characters and no line break -> x); otherwise the row needs a
platform. `--self` routes every row to author slug `self` (the name column is kept when present). Language is
`common.detect_lang`. Media cells hold local paths (relative to the source file, the project root,
`corpus/inbox/` or `corpus/inbox/media/`), absolute paths or URLs, several separated by `;`; nothing is
fetched here.

API: normalize(source, kind="auto", author=None, platform=None, self_=False, mapping=None) -> dict
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# --------------------------------------------------------------------------- header mapping

CANONICAL: tuple[str, ...] = ("author", "handle", "text", "platform", "media", "media_description", "transcript",
                              "posted_at", "url", "likes", "comments", "reposts", "views", "engagement", "lang",
                              "context")

# Synonyms in priority order, the exact canonical name first. Normalised: lower case, single spaces.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "author": ("author", "name", "poster", "creator", "author name", "full name", "display name", "writer", "by"),
    "handle": ("handle", "username", "user name", "user", "author handle", "x handle", "twitter handle", "screen name"),
    "text": ("text", "content", "post", "body", "caption", "post text", "post body", "message", "post content"),
    "platform": ("platform", "network", "channel", "source platform", "site"),
    "media": ("media", "image", "picture", "video", "attachment", "file", "images", "attachments", "photo", "media url",
              "url media", "image url", "video url", "media path", "files"),
    "media_description": ("media description", "description", "alt", "media notes", "alt text", "image description",
                          "media note"),
    "transcript": ("transcript", "video transcript", "speech"),
    "posted_at": ("posted at", "date", "posted", "published", "published at", "timestamp", "created at", "created",
                  "post date", "time"),
    "url": ("url", "link", "permalink", "post url", "post link", "href"),
    "likes": ("likes", "reactions", "like count", "favorites", "favourites", "hearts"),
    "comments": ("comments", "replies", "comment count", "reply count"),
    "reposts": ("reposts", "shares", "retweets", "repost count", "share count", "reshares"),
    "views": ("views", "impressions", "view count", "plays"),
    "engagement": ("engagement", "metrics", "stats"),
    "lang": ("lang", "language"),
    "context": ("context", "quoted post", "quoted text", "post context", "surrounding context", "thread context"),
}
ENGAGEMENT_KEYS: dict[str, str] = {}
for _canon in ("likes", "comments", "reposts", "views"):
    for _syn in SYNONYMS[_canon]:
        ENGAGEMENT_KEYS[_syn] = _canon

PLATFORM_ALIASES: dict[str, str] = {
    "linkedin": "linkedin", "li": "linkedin", "linked in": "linkedin", "linkedin.com": "linkedin",
    "x": "x", "twitter": "x", "tw": "x", "x twitter": "x", "twitter x": "x", "x.com": "x", "twitter.com": "x",
    "x (twitter)": "x", "twitter (x)": "x",
}
X_INFER_MAX_CHARS = 280
URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.I)
MD_SEP_RE = re.compile(r"(?m)^---[ \t]*$\n?")
MD_HEADER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_ \-]{0,40}?)[ \t]*:[ \t]?(.*)$")
INT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([kKmMbB])?$")
KIND_BY_SUFFIX = {".csv": "csv", ".tsv": "csv", ".json": "json", ".jsonl": "json", ".ndjson": "json", ".md": "md",
                  ".markdown": "md", ".txt": "md"}
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%Y", "%B %d, %Y", "%b %d, %Y",
                "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%Y-%m", "%Y")


def norm_header(h: Any) -> str:
    s = str(h if h is not None else "").replace("﻿", "").strip().lower()
    return re.sub(r"[\s_\-]+", " ", s)


def _known_key(h: Any) -> bool:
    n = norm_header(h)
    return any(n in syns for syns in SYNONYMS.values())


def build_mapping(headers: list[str], override: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    """Return (canonical -> source header, unmapped headers). `override` maps canonical names to columns.

    Raises ValueError for an unknown canonical name or a column that does not exist.
    """
    headers = [h for h in headers if h is not None]
    norm = {h: norm_header(h) for h in headers}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for canon, src in (override or {}).items():
        if canon not in CANONICAL:
            raise ValueError(f"mapping: unknown field {canon!r}; fields are {', '.join(CANONICAL)}")
        hit = next((h for h in headers if h == src), None) or next((h for h in headers if norm[h] == norm_header(src)), None)
        if hit is None:
            raise ValueError(f"mapping: column {src!r} not found; columns are {headers}")
        mapping[canon] = hit
        used.add(hit)
    for canon in CANONICAL:
        if canon in mapping:
            continue
        for syn in SYNONYMS[canon]:
            hit = next((h for h in headers if h not in used and norm[h] == syn), None)
            if hit is not None:
                mapping[canon] = hit
                used.add(hit)
                break
    unmapped = [h for h in headers if h not in used]
    return mapping, unmapped


# --------------------------------------------------------------------------- value parsing

def slugify(name: str) -> str:
    """ASCII slug matching [a-z][a-z0-9-]* (the post-id grammar); '@handle' loses the @."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower().strip()
    s = s.lstrip("@")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        return "unknown"
    if not s[0].isalpha():
        s = "author-" + s
    return s


def parse_int(v: Any) -> int | None:
    """'1.2k' -> 1200, '3,400' -> 3400, 12 -> 12, '' / 'n/a' -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    m = INT_RE.match(s)
    if not m:
        return None
    mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get((m.group(2) or "").lower(), 1)
    return round(float(m.group(1)) * mult)


def parse_date(v: Any) -> str | None:
    """ISO date (YYYY-MM-DD) from the common spreadsheet date shapes; None when unparseable."""
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date().isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    s = str(v).strip()
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    head = re.split(r"[T ]", s, maxsplit=1)[0] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else s
    for fmt in DATE_FORMATS:
        try:
            return _dt.datetime.strptime(head, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_platform(v: Any) -> str | None:
    if v is None:
        return None
    s = norm_header(v)
    return PLATFORM_ALIASES.get(s)


def platform_from_url(url: Any) -> str | None:
    if not url or not isinstance(url, str):
        return None
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
    except ValueError:
        return None
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "linkedin"
    if host in ("x.com", "twitter.com") or host.endswith((".x.com", ".twitter.com")):
        return "x"
    return None


def infer_platform(text: str) -> str | None:
    """At most 280 characters and no line break -> x; otherwise undecidable."""
    if len(text) <= X_INFER_MAX_CHARS and "\n" not in text:
        return "x"
    return None


def is_url(s: str) -> bool:
    return bool(URL_SCHEME_RE.match(s.strip()))


def resolve_media_ref(ref: str, source_dir: Path) -> str:
    """URL unchanged; a local path is looked up next to the source, under the root, corpus/inbox and
    corpus/inbox/media, and stored project-relative (absolute when outside the project). An unresolvable
    path is kept verbatim."""
    ref = ref.strip()
    if is_url(ref):
        return ref
    p = Path(ref).expanduser()
    root = common.ROOT
    candidates = [p] if p.is_absolute() else [source_dir / p, root / p, root / "corpus" / "inbox" / p,
                                              root / "corpus" / "inbox" / "media" / p]
    for c in candidates:
        if c.exists():
            return common.rel(c)
    return ref


def media_entries(raw: Any, description: Any, source_dir: Path) -> list[dict]:
    items: list[tuple[str, Any]] = []
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [(s, None) for s in re.split(r"[;\n]", raw) if s.strip()]
    elif isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, str) and it.strip():
                items.append((it, None))
            elif isinstance(it, dict):
                ref = it.get("path_or_url") or it.get("path") or it.get("url") or it.get("file") or it.get("src")
                if ref:
                    items.append((str(ref), it.get("description") or it.get("alt")))
    desc_default = str(description).strip() if description not in (None, "") else None
    return [{"path_or_url": resolve_media_ref(ref, source_dir), "description": (d or desc_default)} for ref, d in items]


def engagement_of(row: dict, mapping: dict[str, str]) -> dict:
    eng: dict[str, int | None] = {"likes": None, "comments": None, "reposts": None, "views": None}
    raw = _get(row, mapping, "engagement")
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if isinstance(raw, dict):
        for k, v in raw.items():
            canon = ENGAGEMENT_KEYS.get(norm_header(k))
            if canon:
                eng[canon] = parse_int(v)
    for canon in ("likes", "comments", "reposts", "views"):
        v = _get(row, mapping, canon)
        if v not in (None, ""):
            eng[canon] = parse_int(v)
    return eng


def clean_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).replace("\r\n", "\n").replace("\r", "\n")
    return s.strip("\n").rstrip()


def _get(row: dict, mapping: dict[str, str], canon: str) -> Any:
    h = mapping.get(canon)
    if h is None:
        return None
    v = row.get(h)
    if isinstance(v, str):
        v = v.strip() if canon != "text" else v
        return v if v != "" else None
    return v


# --------------------------------------------------------------------------- readers

def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    raw = path.read_text(encoding="utf-8-sig")
    sample = raw[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    reader = csv.DictReader(io.StringIO(raw, newline=""), delimiter=delimiter)
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    rows: list[dict] = []
    for rec in reader:
        rec = {k: v for k, v in rec.items() if k is not None}
        if all((v is None or str(v).strip() == "") for v in rec.values()):
            continue
        rows.append(rec)
    return headers, rows


def read_json(path: Path) -> tuple[list[str], list[dict]]:
    raw = path.read_text(encoding="utf-8-sig")
    data: Any
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = []
        for i, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"not JSON and not JSON Lines (line {i}: {e.msg})") from None
    if isinstance(data, dict):
        inner = next((data[k] for k in ("posts", "rows", "items", "data") if isinstance(data.get(k), list)), None)
        data = inner if inner is not None else [data]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError("JSON must be an array of objects (or JSON Lines)")
    headers: list[str] = []
    for r in data:
        for k in r:
            if k not in headers:
                headers.append(k)
    return headers, data


def _parse_md_block(block: str) -> dict:
    """Header lines (`key: value`), a blank line, then the text. Returns the row dict with a `text` key."""
    lines = block.split("\n")
    para_end = next((i for i, ln in enumerate(lines) if not ln.strip()), len(lines))
    first_para = lines[:para_end]

    def header_line(ln: str, strict: bool) -> bool:
        m = MD_HEADER_RE.match(ln)
        if not m:
            return False
        key = m.group(1)
        if strict:
            return _known_key(key)
        return _known_key(key) or re.fullmatch(r"[a-z_][a-z0-9_]{0,30}", key) is not None

    if first_para and all(header_line(ln, strict=False) for ln in first_para) \
            and any(_known_key(MD_HEADER_RE.match(ln).group(1)) for ln in first_para):
        n_head = len(first_para)
        body_start = para_end + 1
    else:
        n_head = 0
        while n_head < len(first_para) and header_line(first_para[n_head], strict=True):
            n_head += 1
        body_start = n_head
    header_text = "\n".join(lines[:n_head])
    meta: dict = {}
    if header_text.strip():
        try:
            parsed = common.load_yaml_str(header_text)
            meta = parsed if isinstance(parsed, dict) else {}
        except Exception:  # noqa: BLE001 - fall back to plain key: value
            meta = {}
        if not meta:
            for ln in lines[:n_head]:
                m = MD_HEADER_RE.match(ln)
                if m:
                    meta[m.group(1).strip()] = m.group(2).strip()
    body = "\n".join(lines[body_start:])
    row = {str(k): v for k, v in meta.items()}
    if body.strip():
        row["text"] = body
    return row


def read_md(path: Path) -> tuple[list[str], list[dict]]:
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    rows: list[dict] = []
    meta, body = common.split_front_matter(raw)
    if isinstance(meta, dict) and meta:
        parts = MD_SEP_RE.split(body)
        first = {str(k): v for k, v in meta.items()}
        if parts[0].strip():
            first["text"] = parts[0]
        rows.append(first)
        blocks = parts[1:]
    else:
        blocks = MD_SEP_RE.split(raw)
    for blk in blocks:
        blk = blk.strip("\n")
        if not blk.strip():
            continue
        rows.append(_parse_md_block(blk))
    headers: list[str] = []
    for r in rows:
        for k in r:
            if k not in headers:
                headers.append(k)
    return headers, rows


READERS = {"csv": read_csv, "json": read_json, "md": read_md}


def detect_kind(path: Path, kind: str = "auto") -> str:
    if kind and kind != "auto":
        return kind
    k = KIND_BY_SUFFIX.get(path.suffix.lower())
    if k is None:
        raise ValueError(f"cannot tell the kind of {path.name!r}; pass --kind csv|json|md")
    return k


def resolve_source(source: str) -> Path:
    p = Path(source).expanduser()
    if p.is_absolute():
        return p
    if (Path.cwd() / p).exists():
        return (Path.cwd() / p).resolve()
    return (common.ROOT / p).resolve()


# --------------------------------------------------------------------------- normalize

def normalize(source: str, kind: str = "auto", author: str | None = None, platform: str | None = None,
              self_: bool = False, mapping: dict[str, str] | None = None) -> dict:
    """Read `source`, write corpus/inbox/normalized_<sha>.jsonl and return the report dict. User errors never
    raise: they come back as {"ok": False, "error": ...}."""
    try:
        path = resolve_source(source)
        if not path.is_file():
            return {"ok": False, "error": f"source not found: {source}"}
        if path.name.startswith("normalized_") and path.suffix == ".jsonl":
            return {"ok": False, "error": f"{path.name} is an ingest_normalize output; pass it to ingest_commit.py"}
        kind = detect_kind(path, kind)
        if kind not in READERS:
            return {"ok": False, "error": f"unknown kind {kind!r}; use csv, json, md or auto"}
        if platform is not None:
            platform = normalize_platform(platform)
            if platform is None:
                return {"ok": False, "error": "--platform must be linkedin or x"}
        headers, raw_rows = READERS[kind](path)
        col_map, unmapped = build_mapping(headers, mapping)
    except (ValueError, UnicodeDecodeError, OSError) as e:
        return {"ok": False, "error": str(e)}

    source_dir = path.parent
    source_kind = "gsheet" if (kind == "csv" and path.name.startswith("gsheet_")) else kind
    source_file = common.rel(path)
    warnings: list[str] = []
    skipped: list[dict] = []
    rows: list[dict] = []
    needs_rows: dict[str, list[str]] = {"text": [], "author": [], "platform": []}
    platforms: dict[str, int] = {"linkedin": 0, "x": 0, "unknown": 0}
    non_english: list[str] = []
    authors: dict[str, int] = {}
    if "text" not in col_map:
        needs_rows["text"].append("*")

    for i, raw in enumerate(raw_rows, 1):
        ref = f"{path.name}#{i}"
        text = clean_text(_get(raw, col_map, "text"))
        if not text:
            skipped.append({"source_ref": ref, "reason": "empty text" if "text" in col_map else "text column not mapped"})
            continue
        name = _get(raw, col_map, "author")
        handle = _get(raw, col_map, "handle")
        name = str(name).strip() if name not in (None, "") else None
        handle = str(handle).strip() if handle not in (None, "") else None
        if name and name.startswith("@") and not handle:
            handle, name = name, name.lstrip("@")
        if not name and handle:
            name = handle.lstrip("@")
        if not name and author:
            name = author.strip()
        if handle and not handle.startswith("@"):
            handle = "@" + handle
        if self_:
            slug = "self"
            name = name or "self"
        else:
            slug = slugify(name) if name else None
            if not name:
                needs_rows["author"].append(ref)
        url = _get(raw, col_map, "url")
        url = str(url).strip() if url not in (None, "") else None
        plat_raw = _get(raw, col_map, "platform")
        plat = normalize_platform(plat_raw)
        if plat_raw not in (None, "") and plat is None:
            warnings.append(f"{ref}: unrecognised platform {plat_raw!r}")
        plat = plat or platform_from_url(url) or platform or infer_platform(text)
        if plat is None:
            needs_rows["platform"].append(ref)
        platforms[plat or "unknown"] = platforms.get(plat or "unknown", 0) + 1
        posted_raw = _get(raw, col_map, "posted_at")
        posted_at = parse_date(posted_raw)
        if posted_raw not in (None, "") and posted_at is None:
            warnings.append(f"{ref}: unparseable date {str(posted_raw)!r}")
        lang_raw = _get(raw, col_map, "lang")
        lang = str(lang_raw).strip().lower() if lang_raw not in (None, "") else common.detect_lang(text)
        if lang != "en":
            non_english.append(ref)
        transcript = _get(raw, col_map, "transcript")
        if transcript not in (None, ""):
            transcript = str(transcript)
            tp = Path(transcript).expanduser()
            for cand in ([tp] if tp.is_absolute() else [source_dir / tp, common.ROOT / tp]):
                if len(transcript) < 512 and cand.is_file() and cand.suffix.lower() in (".txt", ".srt", ".vtt", ".md"):
                    transcript = cand.read_text(encoding="utf-8", errors="replace")
                    break
            transcript = clean_text(transcript) or None
        else:
            transcript = None
        media = media_entries(_get(raw, col_map, "media"), _get(raw, col_map, "media_description"), source_dir)
        context = _get(raw, col_map, "context")
        context = clean_text(context) or None if context not in (None, "") else None
        row = {
            "author_name": name, "author_slug": slug, "author_handle": handle, "platform": plat, "text": text,
            "posted_at": posted_at, "url": url, "engagement": engagement_of(raw, col_map), "media": media,
            "transcript": transcript, "source_ref": ref, "source_kind": source_kind, "source_file": source_file,
            "lang": lang, "context": context,
        }
        rows.append(row)
        if slug:
            authors[slug] = authors.get(slug, 0) + 1

    needs = [k for k in ("text", "author", "platform") if needs_rows[k]]
    sha = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    out = common.ROOT / "corpus" / "inbox" / f"normalized_{sha}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    return {
        "ok": True, "rows": len(rows), "unmapped_columns": unmapped, "needs": needs, "file": common.rel(out),
        "needs_rows": {k: v for k, v in needs_rows.items() if v}, "kind": kind, "source": source_file,
        "mapping": col_map, "platforms": platforms, "authors": authors, "non_english": non_english,
        "skipped": skipped, "warnings": warnings,
    }


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize a CSV / JSON / Markdown source of reference posts into "
                                             "corpus/inbox/normalized_<sha>.jsonl (contracts section 17).")
    ap.add_argument("source", help="CSV, JSON/JSONL or Markdown file (relative to the cwd or the project root)")
    ap.add_argument("--kind", default="auto", choices=["csv", "json", "md", "auto"], help="source kind (default: by extension)")
    ap.add_argument("--author", default=None, help="author name for rows without one")
    ap.add_argument("--platform", default=None, help="linkedin or x for rows without an explicit platform")
    ap.add_argument("--self", dest="self_", action="store_true", help="route every row to author slug 'self'")
    ap.add_argument("--mapping", default=None, help='JSON object {canonical: "source column"} overriding the synonyms')
    ap.add_argument("--root", default=None, help="project root (default: $POSTSMITH_ROOT or this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    mapping = None
    if args.mapping:
        try:
            mapping = json.loads(args.mapping)
        except json.JSONDecodeError as e:
            common.emit({"ok": False, "error": f"--mapping is not valid JSON: {e.msg}"})
            return 0
        if not isinstance(mapping, dict) or not all(isinstance(v, str) for v in mapping.values()):
            common.emit({"ok": False, "error": "--mapping must be a JSON object of {canonical: column}"})
            return 0
    try:
        with common.use_root(args.root):
            doc = normalize(args.source, args.kind, args.author, args.platform, args.self_, mapping)
    except FileNotFoundError as e:
        doc = {"ok": False, "error": str(e)}
    common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
