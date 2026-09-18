#!/usr/bin/env python3
"""ingest_commit.py: normalized rows -> corpus post files, media copies, manifest rows (contracts §1, §17).

    uv run tools/ingest_commit.py <normalized.jsonl> [--self] [--consent-media] [--root R] [--json]

For every row of the JSONL that `ingest_normalize.py` wrote:
- A row still missing text, an author or a platform refuses the whole file and nothing is written; re-run
  normalize with --author / --platform / --mapping.
- Dedupe key = `common.content_sha(text)` + author slug, against `corpus/manifest.jsonl` and the rows already
  planned in this batch. Same key on the same platform is skipped as a duplicate. Same key on the other
  platform is ingested with `crosspost_of` the earlier post. A post by the same author whose word 8-gram
  Jaccard with an existing post reaches `overlap.near_duplicate_jaccard` is ingested with `variant_of` it.
- Split (sticky, written once): `self` for `--self`; otherwise every row goes to train while
  `common.small_corpus_mode` says the corpus is small. When it is not,
  `common.is_heldout_by_hash(sha, corpus.heldout_modulo)` picks heldout, then the new train rows of each
  platform are flipped to heldout in sorted-hash order until that platform holds
  `corpus.heldout_min_per_platform` heldout posts. A `corpus.primary_authors` slug is never held out: they
  are the style target, so every post of theirs has to be able to teach. A variant or crosspost inherits the
  split of the post it links to. Existing posts never move.
- Post ids `<author_slug>_<nnn>` (`self_<nnn>`), sequential per author, three digits minimum.
- Media: local files are copied to `corpus/media/<id>/<N>.<ext>` with sha256 and dims (pillow; HEIC/HEIF
  converted with `sips -s format jpeg` on macOS, otherwise `kind: unavailable`); videos are probed with
  ffprobe when present; PDFs become `kind: carousel`. Remote URLs are listed under `remote_media` and stored
  as `kind: unavailable` with `source_url` unless `--consent-media`, which fetches direct file URLs with
  urllib (200 MB cap, html refused). linkedin.com, x.com and twitter.com page URLs are refused whatever the
  flag; Google Drive links are listed for the Drive connector. With `--consent-media` a duplicate row can
  still back-fill the media of its existing post.
- A row transcript is written to `corpus/media/<id>/transcript.txt` and linked from the first video entry,
  else from the first entry.
- The source file and the normalized JSONL move to `corpus/inbox/done/` when they live directly under
  `corpus/inbox/`; a source elsewhere is copied there, so `source.file` always resolves. Local media
  referenced from directly under `corpus/inbox/` move to done/ too once copied.

Prints `{"ok", "ingested", "skipped", "variants", "crossposts", "remote_media", "refused_urls", "media",
"small_corpus_mode", "split_applied", "heldout_counts", "counts", "non_english", "moved", "warnings"}`.

API: commit(normalized_path, self_=False, consent_media=False) -> dict
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform as _platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import media_prepare  # noqa: E402

SPLIT_DIRS = {"train": "corpus/posts", "heldout": "corpus/heldout", "self": "corpus/self"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
HEIC_EXT = {".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
PDF_EXT = {".pdf"}
REFUSED_HOSTS = ("linkedin.com", "lnkd.in", "x.com", "twitter.com", "t.co")
DRIVE_HOSTS = ("drive.google.com", "docs.google.com")
MAX_REMOTE_BYTES = 200 * 1024 * 1024
FETCH_TIMEOUT_S = 60
CONTENT_TYPE_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                    "image/webp": ".webp", "image/heic": ".heic", "image/heif": ".heif", "video/mp4": ".mp4",
                    "video/quicktime": ".mov", "video/webm": ".webm", "application/pdf": ".pdf"}
NGRAM_N = 8
ID_RE = re.compile(r"^(?P<slug>[a-z][a-z0-9\-]*)_(?P<n>\d{3,})$")
_PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![s/])")


# --------------------------------------------------------------------------- rows

def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path.name} line {i}: not JSON ({e.msg})") from None
        if not isinstance(obj, dict):
            raise ValueError(f"{path.name} line {i}: not an object")
        rows.append(obj)
    return rows


def row_problems(rows: list[dict], self_: bool) -> list[str]:
    problems: list[str] = []
    for i, r in enumerate(rows, 1):
        ref = r.get("source_ref") or f"row {i}"
        text = r.get("text")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{ref}: no text")
        if not self_ and not r.get("author_slug"):
            problems.append(f"{ref}: no author (re-run ingest_normalize with --author)")
        if r.get("platform") not in ("linkedin", "x"):
            problems.append(f"{ref}: no platform (re-run ingest_normalize with --platform)")
    return problems


# --------------------------------------------------------------------------- corpus index

class CorpusIndex:
    """What the corpus already holds: manifest rows plus the post files (platform, text tokens, split)."""

    def __init__(self) -> None:
        self.posts: dict[str, dict] = {}      # post_id -> {slug, platform, split, sha, ngrams, path}
        self.by_key: dict[tuple[str, str], list[str]] = {}   # (sha, slug) -> [post_id]
        self.by_author: dict[str, list[str]] = {}
        self.max_n: dict[str, int] = {}
        self.manifest_rows = common.read_jsonl(common.ROOT / "corpus" / "manifest.jsonl")
        for row in self.manifest_rows:
            pid = str(row.get("post_id") or "")
            split = str(row.get("split") or "train")
            if not pid or pid in self.posts:
                continue
            path = common.ROOT / SPLIT_DIRS.get(split, "corpus/posts") / f"{pid}.md"
            self._add_from_file(pid, path, split, row.get("author_slug"), row.get("content_sha256"))
        for split, rel in SPLIT_DIRS.items():
            d = common.ROOT / rel
            if not d.is_dir():
                continue
            for p in sorted(d.glob("*.md")):
                if p.stem not in self.posts:
                    self._add_from_file(p.stem, p, split, None, None)

    def _add_from_file(self, pid: str, path: Path, split: str, slug: Any, sha: Any) -> None:
        platform = None
        text = ""
        if path.is_file():
            try:
                meta, body = common.split_front_matter(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - a malformed post still counts for ids and dedupe
                meta, body = {}, ""
            if isinstance(meta, dict):
                platform = meta.get("platform")
                author = meta.get("author")
                if not slug and isinstance(author, dict):
                    slug = author.get("slug")
                if not sha:
                    sha = meta.get("content_sha256")
                if not slug and pid.startswith("self_"):
                    slug = "self"
            text = body.rstrip("\n")
            if not sha and text:
                sha = common.content_sha(text)
        slug = str(slug or "unknown")
        sha = str(sha or "")
        self.add(pid, slug, platform, split, sha, text, path)

    def add(self, pid: str, slug: str, platform: Any, split: str, sha: str, text: str, path: Path | None) -> None:
        toks = common.word_tokens_normalized(text) if text else []
        self.posts[pid] = {"slug": slug, "platform": platform, "split": split, "sha": sha,
                           "ngrams": common.word_ngrams(toks, NGRAM_N), "path": path}
        self.by_key.setdefault((sha, slug), []).append(pid)
        self.by_author.setdefault(slug, []).append(pid)
        m = ID_RE.match(pid)
        if m and m.group("slug") == slug:
            self.max_n[slug] = max(self.max_n.get(slug, 0), int(m.group("n")))

    def next_id(self, slug: str) -> str:
        n = self.max_n.get(slug, 0) + 1
        self.max_n[slug] = n
        return f"{slug}_{n:03d}"

    def exact(self, sha: str, slug: str) -> list[str]:
        return list(self.by_key.get((sha, slug), []))

    def nearest_variant(self, slug: str, sha: str, ngrams: set, threshold: float) -> tuple[str, float] | None:
        best: tuple[str, float] | None = None
        if not ngrams:
            return None
        for pid in self.by_author.get(slug, []):
            e = self.posts[pid]
            if e["sha"] == sha:
                continue
            j = common.jaccard(ngrams, e["ngrams"])
            if j >= threshold and (best is None or j > best[1] or (j == best[1] and pid < best[0])):
                best = (pid, j)
        return best

    def heldout_counts(self) -> dict[str, int]:
        out = {"linkedin": 0, "x": 0}
        for e in self.posts.values():
            if e["split"] == "heldout":
                plat = str(e.get("platform") or "unknown")
                out[plat] = out.get(plat, 0) + 1
        return out

    def counts(self) -> dict:
        per: dict[str, dict[str, int]] = {s: {"linkedin": 0, "x": 0} for s in SPLIT_DIRS}
        for e in self.posts.values():
            split = e["split"] if e["split"] in per else "train"
            plat = str(e.get("platform") or "unknown")
            per[split][plat] = per[split].get(plat, 0) + 1
        return {s: {"total": sum(v.values()), **v} for s, v in per.items()}


# --------------------------------------------------------------------------- media

def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _host_in(host: str, names: tuple[str, ...]) -> bool:
    return any(host == n or host.endswith("." + n) for n in names)


def is_url(s: Any) -> bool:
    return isinstance(s, str) and bool(re.match(r"^https?://", s.strip(), re.I))


def media_entry(kind: str = "unavailable", **kw: Any) -> dict:
    base = {"kind": kind, "path": None, "preview": None, "sha256": None, "width": None, "height": None,
            "duration_s": None, "frames_dir": None, "transcript": None, "provided_description": None}
    base.update({k: v for k, v in kw.items() if v is not None or k in base})
    return base


def resolve_local(ref: str, source_dir: Path | None) -> Path | None:
    p = Path(ref).expanduser()
    root = common.ROOT
    cands = [p] if p.is_absolute() else [root / p, root / "corpus" / "inbox" / p, root / "corpus" / "inbox" / "media" / p,
                                         root / "corpus" / "inbox" / "done" / p]
    if source_dir is not None and not p.is_absolute():
        cands.insert(0, source_dir / p)
    for c in cands:
        if c.is_file():
            return c.resolve()
    return None


def _pdf_pages(data: bytes) -> int:
    if not data.startswith(b"%PDF"):
        return 0
    return len(_PDF_PAGE_RE.findall(data))


def place_media(post_id: str, index: int, src: Path, description: str | None, warnings: list[str],
                original_name: str | None = None) -> dict:
    """Copy `src` to corpus/media/<post_id>/<index>.<ext> (HEIC -> jpg via sips) and build the entry."""
    name = original_name or src.name
    ext = Path(name).suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    dest_dir = common.ROOT / "corpus" / "media" / post_id
    if ext in HEIC_EXT:
        sips = shutil.which("sips") if _platform.system() == "Darwin" else None
        if not sips:
            warnings.append(f"{post_id}: {name} is HEIC/HEIF and sips (macOS) is not available")
            return media_entry(note="heic needs macOS sips", provided_description=description)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{index}.jpg"
        res = subprocess.run([sips, "-s", "format", "jpeg", str(src), "--out", str(dest)], capture_output=True,
                             text=True, check=False)
        if res.returncode != 0 or not dest.is_file():
            warnings.append(f"{post_id}: sips could not convert {name}")
            return media_entry(note="heic conversion failed", provided_description=description)
        ext = ".jpg"
    else:
        if ext not in IMAGE_EXT | VIDEO_EXT | PDF_EXT:
            warnings.append(f"{post_id}: unsupported media type {name}")
            return media_entry(note=f"unsupported media type {ext or '(none)'}", provided_description=description)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{index}{ext}"
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
    data_sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    rel = common.rel(dest)
    if ext in IMAGE_EXT:
        dims = media_prepare.image_dims(dest)
        if dims is None:
            warnings.append(f"{post_id}: {name} is not a decodable image")
            return media_entry(path=rel, sha256=data_sha, note="image not decodable", provided_description=description)
        return media_entry("image", path=rel, sha256=data_sha, width=dims[0], height=dims[1],
                           provided_description=description)
    if ext in VIDEO_EXT:
        if not media_prepare.have("ffprobe"):
            warnings.append(f"{post_id}: ffprobe not installed; {name} copied without probing")
            return media_entry("video", path=rel, sha256=data_sha, provided_description=description)
        info = media_prepare.video_info(media_prepare.ffprobe_json(dest))
        if not info["has_video"]:
            warnings.append(f"{post_id}: {name} is not a probeable video")
            return media_entry(path=rel, sha256=data_sha, note="video not probeable", provided_description=description)
        return media_entry("video", path=rel, sha256=data_sha, width=info["width"], height=info["height"],
                           duration_s=info["duration_s"], provided_description=description)
    pages = _pdf_pages(dest.read_bytes())
    if pages <= 0:
        warnings.append(f"{post_id}: {name} is not a PDF with pages")
        return media_entry(path=rel, sha256=data_sha, note="pdf has no pages", provided_description=description)
    return media_entry("carousel", path=rel, sha256=data_sha, provided_description=description, pages=pages)


def fetch_url(url: str, cap: int = MAX_REMOTE_BYTES, timeout: int = FETCH_TIMEOUT_S) -> tuple[bytes | None, str, str]:
    """(bytes, extension, error). Direct file URLs only: html answers and bodies above `cap` are refused."""
    req = urllib.request.Request(url, headers={"User-Agent": "postsmith-ingest/1 (+local)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # user-consented direct file URL
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            length = resp.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > cap:
                return None, "", f"too large ({int(length)} bytes > {cap})"
            if ctype.startswith("text/html"):
                return None, "", "not a file (html page)"
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > cap:
                    return None, "", f"too large (> {cap} bytes)"
                chunks.append(chunk)
    except urllib.error.HTTPError as e:
        return None, "", f"http {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, "", f"fetch failed: {getattr(e, 'reason', e)}"
    ext = CONTENT_TYPE_EXT.get(ctype) or Path(urlparse(url).path).suffix.lower() or ""
    return b"".join(chunks), ext, ""


def build_media(post_id: str, row: dict, consent: bool, report: dict, source_dir: Path | None) -> list[dict]:
    entries: list[dict] = []
    warnings: list[str] = report["warnings"]
    for i, m in enumerate(row.get("media") or [], 1):
        if isinstance(m, str):
            m = {"path_or_url": m, "description": None}
        if not isinstance(m, dict):
            continue
        ref = str(m.get("path_or_url") or "").strip()
        desc = m.get("description") or None
        if not ref:
            continue
        if is_url(ref):
            host = _host(ref)
            if _host_in(host, REFUSED_HOSTS):
                report["refused_urls"].append({"post_id": post_id, "url": ref,
                                               "reason": "page URL on linkedin.com / x.com / twitter.com; save the media locally"})
                entries.append(media_entry(note="refused page url", source_url=ref, provided_description=desc))
                continue
            if _host_in(host, DRIVE_HOSTS):
                report["remote_media"].append({"post_id": post_id, "url": ref, "description": desc, "kind": "drive",
                                               "note": "download via the Drive connector into corpus/inbox/media/"})
                entries.append(media_entry(note="drive link not fetched", source_url=ref, provided_description=desc))
                continue
            if not consent:
                report["remote_media"].append({"post_id": post_id, "url": ref, "description": desc, "kind": "direct"})
                entries.append(media_entry(note="remote url not fetched", source_url=ref, provided_description=desc))
                continue
            data, ext, err = fetch_url(ref)
            if data is None:
                warnings.append(f"{post_id}: {ref}: {err}")
                report["media"]["unavailable"].append({"post_id": post_id, "ref": ref, "reason": err})
                entries.append(media_entry(note=err, source_url=ref, provided_description=desc))
                continue
            tmp = common.ROOT / "corpus" / "media" / post_id / f".fetch_{i}{ext}"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
            try:
                entry = place_media(post_id, i, tmp, desc, warnings, original_name=f"remote_{i}{ext}")
            finally:
                tmp.unlink(missing_ok=True)
            entry["source_url"] = ref
        else:
            src = resolve_local(ref, source_dir)
            if src is None:
                warnings.append(f"{post_id}: media file not found: {ref}")
                report["media"]["unavailable"].append({"post_id": post_id, "ref": ref, "reason": "file not found"})
                entries.append(media_entry(note="file not found", source_ref=ref, provided_description=desc))
                continue
            entry = place_media(post_id, i, src, desc, warnings)
            report["media"]["sources"].add(src)
        if entry["kind"] == "unavailable":
            report["media"]["unavailable"].append({"post_id": post_id, "ref": ref, "reason": entry.get("note")})
        else:
            report["media"]["copied"] += 1
        entries.append(entry)
    return entries


def attach_transcript(post_id: str, transcript: Any, entries: list[dict], warnings: list[str]) -> None:
    if not isinstance(transcript, str) or not transcript.strip():
        return
    if not entries:
        warnings.append(f"{post_id}: transcript supplied but the row has no media; dropped")
        return
    dest = common.ROOT / "corpus" / "media" / post_id / "transcript.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(transcript.rstrip("\n") + "\n", encoding="utf-8")
    target = next((e for e in entries if e.get("kind") == "video"), entries[0])
    target["transcript"] = common.rel(dest)


# --------------------------------------------------------------------------- post files

def text_stats(text: str) -> dict:
    ls = common.lines(text)
    return {"chars": len(text), "words": len(common.words(text)), "lines": len(ls),
            "blank_lines": sum(1 for ln in ls if not ln.strip())}


def build_meta(post_id: str, row: dict, slug: str, split: str, sha: str, source_file_rel: str, ingested_at: str,
               crosspost_of: str | None, variant_of: str | None, media: list[dict], text: str) -> dict:
    eng = row.get("engagement") if isinstance(row.get("engagement"), dict) else {}
    return {
        "schema": "postsmith.post/1",
        "post_id": post_id,
        "author": {"name": row.get("author_name") or slug, "slug": slug, "handle": row.get("author_handle")},
        "platform": row["platform"],
        "posted_at": row.get("posted_at"),
        "url": row.get("url"),
        "lang": row.get("lang") or common.detect_lang(text),
        "source": {"kind": row.get("source_kind") or "csv", "ref": row.get("source_ref"), "file": source_file_rel,
                   "ingested_at": ingested_at},
        "content_sha256": sha,
        "split": split,
        "crosspost_of": crosspost_of,
        "variant_of": variant_of,
        "context": row.get("context") or None,
        "engagement": {k: eng.get(k) for k in ("likes", "comments", "reposts", "views")},
        "media": media,
        "text_stats": text_stats(text),
    }


def _done_path(src: Path) -> Path:
    """Destination under corpus/inbox/done/ for a source file, suffixed when another file holds that name."""
    done = common.ROOT / "corpus" / "inbox" / "done"
    dest = done / src.name
    if dest.exists() and dest.resolve() != src.resolve() and dest.read_bytes() != src.read_bytes():
        dest = done / f"{src.stem}_{hashlib.sha256(src.read_bytes()).hexdigest()[:8]}{src.suffix}"
    return dest


def _move_to_done(src: Path, moved: list[dict], copy_only: bool) -> Path:
    dest = _done_path(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() == src.resolve():
        return dest
    if dest.exists():
        if not copy_only:
            src.unlink()
            moved.append({"from": common.rel(src), "to": common.rel(dest), "note": "identical file already in done/"})
        return dest
    if copy_only:
        shutil.copyfile(src, dest)
        moved.append({"from": common.rel(src), "to": common.rel(dest), "note": "copied (source outside corpus/inbox)"})
    else:
        shutil.move(str(src), str(dest))
        moved.append({"from": common.rel(src), "to": common.rel(dest)})
    return dest


def _directly_in_inbox(p: Path) -> bool:
    try:
        return p.resolve().parent == (common.ROOT / "corpus" / "inbox").resolve()
    except OSError:
        return False


def _in_done(p: Path) -> bool:
    try:
        return p.resolve().parent == (common.ROOT / "corpus" / "inbox" / "done").resolve()
    except OSError:
        return False


# --------------------------------------------------------------------------- split

def small_corpus_after_load(cfg: dict) -> bool:
    return common.small_corpus_mode(cfg, common.ROOT)


def small_corpus_for_counts(cfg: dict, train: dict) -> bool:
    """`common.small_corpus_mode`'s rule applied to a train count dict (`CorpusIndex.counts()["train"]`).

    The split is decided against the corpus as it will be *after* the batch, not before it. A first ingest of a full
    reference set judged against the empty corpus would make `small` true, send every row to train and, because
    splits are sticky, leave the heldout split empty for ever. That silently disables the oracle, the quote-leak
    check and every lineup that draws heldout fillers.
    """
    ccfg = (cfg.get("corpus") or {}) if isinstance(cfg, dict) else {}
    max_posts = int(ccfg.get("small_corpus_max_posts", 24))
    min_per_platform = int(ccfg.get("small_corpus_min_per_platform", 6))
    if int(train.get("total") or 0) < max_posts:
        return True
    # A platform with no references at all is not a small corpus, it is an unanchored platform, and it must
    # not hold the platform that does have references in small-corpus mode (common.small_corpus_mode reads it
    # the same way). tier0 asks per platform, so an X candidate is still judged small-corpus.
    return any(0 < int(train.get(plat) or 0) < min_per_platform for plat in ("linkedin", "x"))


def assign_splits(new_posts: list[dict], index: CorpusIndex, cfg: dict, small: bool) -> None:
    """Set `split` on each new post dict ({sha, platform, slug, self, link}) in place."""
    ccfg = cfg.get("corpus") or {}
    modulo = int(ccfg.get("heldout_modulo", 4))
    min_per = int(ccfg.get("heldout_min_per_platform", 4))
    # A primary author is the style target, so every post of theirs has to be able to teach: their cards,
    # their quoted examples and their envelope all come from the train split, and a quarter of a nine-post
    # sample is too much to spend on filler duty. Fillers, the oracle and pairwise references come from the
    # other authors.
    never_heldout = {str(x).strip().lower() for x in (ccfg.get("primary_authors") or []) if str(x).strip()}
    for p in new_posts:
        if p["self"]:
            p["split"] = "self"
        elif small or str(p.get("slug") or "").lower() in never_heldout:
            p["split"] = "train"
        else:
            p["split"] = "heldout" if common.is_heldout_by_hash(p["sha"], modulo) else "train"
    by_id = {p["post_id"]: p for p in new_posts}
    for p in new_posts:
        link = p.get("link")
        if link and not p["self"]:
            if link in by_id:
                p["split"] = by_id[link]["split"]
            elif link in index.posts:
                p["split"] = index.posts[link]["split"]
    if small:
        return
    counts = index.heldout_counts()
    for p in new_posts:
        if p["split"] == "heldout":
            counts[p["platform"]] = counts.get(p["platform"], 0) + 1
    for plat in ("linkedin", "x"):
        need = min_per - counts.get(plat, 0)
        if need <= 0:
            continue
        cands = sorted((p for p in new_posts if p["split"] == "train" and p["platform"] == plat and not p.get("link")
                        and not p["self"] and str(p.get("slug") or "").lower() not in never_heldout),
                       key=lambda p: p["sha"])
        for p in cands[:need]:
            p["split"] = "heldout"
            counts[plat] = counts.get(plat, 0) + 1


# --------------------------------------------------------------------------- backfill media on duplicates

def backfill_media(existing_id: str, row: dict, report: dict) -> bool:
    """With --consent-media, fetch remote media an existing duplicate post still lists as unavailable."""
    path = media_prepare.find_post(existing_id)
    if path is None:
        return False
    meta, body = common.read_front_matter_file(path)
    entries = meta.get("media") or []
    urls = [str(m.get("path_or_url") or "") for m in (row.get("media") or []) if isinstance(m, dict)]
    changed = False
    for i, e in enumerate(entries, 1):
        if not isinstance(e, dict) or e.get("kind") != "unavailable" or not e.get("source_url"):
            continue
        url = str(e["source_url"])
        if url not in urls or _host_in(_host(url), REFUSED_HOSTS + DRIVE_HOSTS):
            continue
        data, ext, err = fetch_url(url)
        if data is None:
            report["warnings"].append(f"{existing_id}: {url}: {err}")
            continue
        tmp = common.ROOT / "corpus" / "media" / existing_id / f".fetch_{i}{ext}"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        try:
            new = place_media(existing_id, i, tmp, e.get("provided_description"), report["warnings"],
                              original_name=f"remote_{i}{ext}")
        finally:
            tmp.unlink(missing_ok=True)
        new["source_url"] = url
        if new["kind"] != "unavailable":
            entries[i - 1] = new
            report["media"]["copied"] += 1
            changed = True
    if changed:
        meta["media"] = entries
        common.write_front_matter_file(path, meta, body)
        report["media"]["backfilled"].append(existing_id)
    return changed


# --------------------------------------------------------------------------- commit

def commit(normalized: str, self_: bool = False, consent_media: bool = False) -> dict:
    """Ingest one normalized JSONL into the corpus under common.ROOT. Returns the report dict."""
    p = Path(normalized).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p) if (Path.cwd() / p).is_file() else common.ROOT / p
    if not p.is_file():
        return {"ok": False, "error": f"normalized file not found: {normalized}"}
    try:
        rows = load_rows(p)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    problems = row_problems(rows, self_)
    if problems:
        return {"ok": False, "error": "incomplete rows: " + "; ".join(problems[:8]) + (" ..." if len(problems) > 8 else ""),
                "problems": problems}
    cfg = common.load_config()
    threshold = float((cfg.get("overlap") or {}).get("near_duplicate_jaccard", 0.8))
    index = CorpusIndex()
    small_before = small_corpus_after_load(cfg)
    ingested_at = common.now_iso()
    report: dict[str, Any] = {
        "ok": True, "ingested": [], "skipped": [], "variants": [], "crossposts": [], "remote_media": [],
        "refused_urls": [], "media": {"copied": 0, "unavailable": [], "backfilled": [], "sources": set()},
        "small_corpus_mode": small_before, "small_corpus_mode_before": small_before,
        "small_corpus_mode_after": small_before, "split_applied": False, "heldout_counts": {}, "counts": {},
        "non_english": [], "moved": [], "warnings": [],
    }

    # pass 1: dedupe, ids, links
    planned: list[dict] = []
    for row in rows:
        text = str(row["text"]).replace("\r\n", "\n").strip("\n").rstrip()
        slug = "self" if self_ else str(row["author_slug"])
        sha = common.content_sha(text)
        platform = row["platform"]
        same = index.exact(sha, slug)
        dup = next((pid for pid in same if index.posts[pid]["platform"] == platform), None)
        if dup:
            entry = {"source_ref": row.get("source_ref"), "reason": "duplicate", "post_id": dup}
            if consent_media and backfill_media(dup, row, report):
                entry["media_backfilled"] = True
            report["skipped"].append(entry)
            continue
        crosspost_of = same[0] if same else None
        variant_of = None
        jacc = None
        toks = common.word_tokens_normalized(text)
        ngrams = common.word_ngrams(toks, NGRAM_N)
        if crosspost_of is None:
            near = index.nearest_variant(slug, sha, ngrams, threshold)
            if near:
                variant_of, jacc = near
        post_id = index.next_id(slug)
        planned.append({"post_id": post_id, "row": row, "text": text, "slug": slug, "sha": sha, "platform": platform,
                        "self": self_ or slug == "self", "crosspost_of": crosspost_of, "variant_of": variant_of,
                        "jaccard": jacc, "link": crosspost_of or variant_of})
        index.add(post_id, slug, platform, "train", sha, text, None)

    # every planned row is in the index as train by now, so counts()["train"] is the post-batch train corpus
    small_after = small_corpus_for_counts(cfg, index.counts()["train"])
    assign_splits(planned, index, cfg, small_after)
    report["small_corpus_mode"] = small_after      # the value the split decision used
    report["small_corpus_mode_after"] = small_after
    report["split_applied"] = any(p["split"] == "heldout" for p in planned)

    # pass 2: write
    source_dir = Path(str(rows[0].get("source_file") or "")).parent if rows else None
    if source_dir is not None and not source_dir.is_absolute():
        source_dir = common.ROOT / source_dir
    src_files: dict[str, Path] = {}
    for p_ in planned:
        row = p_["row"]
        src_rel = str(row.get("source_file") or "")
        src_path = Path(src_rel)
        if not src_path.is_absolute():
            src_path = common.ROOT / src_path
        src_files.setdefault(str(src_path), src_path)
        done_rel = common.rel(_done_path(src_path)) if src_path.is_file() else src_rel
        media = build_media(p_["post_id"], row, consent_media, report, src_path.parent if src_path.is_file() else source_dir)
        attach_transcript(p_["post_id"], row.get("transcript"), media, report["warnings"])
        meta = build_meta(p_["post_id"], row, p_["slug"], p_["split"], p_["sha"], done_rel, ingested_at,
                          p_["crosspost_of"], p_["variant_of"], media, p_["text"])
        out = common.ROOT / SPLIT_DIRS[p_["split"]] / f"{p_['post_id']}.md"
        common.write_front_matter_file(out, meta, p_["text"])
        index.posts[p_["post_id"]]["split"] = p_["split"]
        index.posts[p_["post_id"]]["path"] = out
        common.append_jsonl(common.ROOT / "corpus" / "manifest.jsonl", {
            "content_sha256": p_["sha"], "author_slug": p_["slug"], "post_id": p_["post_id"], "split": p_["split"],
            "source": meta["source"], "ingested_at": ingested_at, "crosspost_of": p_["crosspost_of"],
            "variant_of": p_["variant_of"],
        })
        report["ingested"].append(p_["post_id"])
        if p_["crosspost_of"]:
            report["crossposts"].append({"post_id": p_["post_id"], "crosspost_of": p_["crosspost_of"]})
        if p_["variant_of"]:
            report["variants"].append({"post_id": p_["post_id"], "variant_of": p_["variant_of"],
                                       "jaccard": round(float(p_["jaccard"] or 0), 3)})
        if meta["lang"] != "en":
            report["non_english"].append(p_["post_id"])

    # move sources, media originals and the normalized file into done/
    for src_path in src_files.values():
        if src_path.is_file() and not _in_done(src_path):
            _move_to_done(src_path, report["moved"], copy_only=not _directly_in_inbox(src_path))
    for m in sorted(report["media"]["sources"], key=str):
        if m.is_file() and _directly_in_inbox(m):
            _move_to_done(m, report["moved"], copy_only=False)
    if not _in_done(p):
        _move_to_done(p, report["moved"], copy_only=not _directly_in_inbox(p))

    report["media"]["sources"] = len(report["media"]["sources"])
    report["heldout_counts"] = index.heldout_counts()
    report["counts"] = index.counts()
    report["rows"] = len(rows)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Commit a normalized JSONL into the corpus: dedupe, sticky split, post "
                                             "files, media copies, manifest rows (contracts sections 1 and 17).")
    ap.add_argument("normalized", help="corpus/inbox/normalized_<sha>.jsonl from ingest_normalize.py")
    ap.add_argument("--self", dest="self_", action="store_true", help="route every row to corpus/self (slug self)")
    ap.add_argument("--consent-media", action="store_true", help="fetch direct-file media URLs (200 MB cap)")
    ap.add_argument("--root", default=None, help="project root (default: $POSTSMITH_ROOT or this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        with common.use_root(args.root):
            doc = commit(args.normalized, args.self_, args.consent_media)
    except FileNotFoundError as e:
        doc = {"ok": False, "error": str(e)}
    common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
