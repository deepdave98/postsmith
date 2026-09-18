#!/usr/bin/env python3
"""media_prepare.py: previews, frames, contact sheets, audio and transcript hookup for corpus media (contracts §17).

    uv run tools/media_prepare.py --post <id> [--force] [--root R] [--json]
    uv run tools/media_prepare.py --all   [--force] [--root R] [--json]

Per media entry of a post (`media[]` in the post front matter, kinds image | video | carousel; `unavailable` is
left alone):
- image: `corpus/media/<id>/preview_<N>.jpg`, long edge at most 1568 px (pillow); `width` / `height` of the original.
- video: `ffprobe` JSON for dims, duration and streams; keyframes at 0/25/50/75/100 % (`kf_00.jpg` ..
  `kf_100.jpg`) plus up to 8 ffmpeg scene-change frames (`scene_01.jpg` ..) at 640 px wide; a 3x3 contact
  sheet `contact.jpg` over the first nine frames; `audio.wav` (16 kHz mono) only when an audio stream
  exists; `frames.json` with timestamps. All of it lands in `frames_dir` = `corpus/frames/<id>`
  (`corpus/frames/<id>_<N>` for a second video of the same post). The contact sheet is copied to
  `corpus/media/<id>/preview_<N>.jpg` as well, so readers of `preview_*.jpg` see video posts too.
- carousel (PDF): `pdftoppm -r 80 -png` pages into `frames_dir`, preview from page 1, contact sheet from the pages.
  Without pdftoppm the entry keeps its kind and the result says why nothing was prepared.
- transcript: a transcript supplied at ingest lives at `corpus/media/<id>/transcript.txt`; an entry without one is
  pointed at that file when it exists. No speech-to-text is run.

The post file is rewritten only when an entry changed (`preview`, `frames_dir`, `width`, `height`, `duration_s`,
`transcript`, or `kind: unavailable` with a `note` when the file cannot be decoded / probed). Entries already
prepared are reported `unchanged` unless `--force`. Nothing under `corpus/` other than `media/`, `frames/` and the
post's `media` list is touched.

Output: `{"ok", "posts": {"<id>": {"path", "media": [{index, kind, status, preview, frames_dir, frames, audio,
transcript, error}]}}, "prepared", "unchanged", "unavailable", "skipped", "tools": {ffmpeg, ffprobe, pdftoppm}}`.

API: prepare_post(path, force=False) -> dict ; ffprobe_json(path) ; image_dims(path) ; have(tool)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

PREVIEW_MAX_EDGE = 1568
FRAME_WIDTH = 640
SCENE_THRESHOLD = 0.35
MAX_SCENE_FRAMES = 8
KEYFRAME_PCTS = (0, 25, 50, 75, 100)
CONTACT_TILE = "3x3"
CONTACT_CELL = 640
SPLIT_DIRS = {"train": "corpus/posts", "heldout": "corpus/heldout", "self": "corpus/self"}
MEDIA_KEYS = ("kind", "path", "preview", "sha256", "width", "height", "duration_s", "frames_dir", "transcript",
              "provided_description")
_PTS_RE = re.compile(r"pts_time:\s*([0-9.]+)")


# --------------------------------------------------------------------------- external tools

def have(tool: str) -> str | None:
    """Absolute path of `tool` on PATH, or None."""
    return shutil.which(tool)


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def ffprobe_json(path: Path | str) -> dict | None:
    """ffprobe JSON (-show_format -show_streams); None when ffprobe is absent or the file will not probe."""
    exe = have("ffprobe")
    if not exe:
        return None
    try:
        res = _run([exe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        doc = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None
    return doc if isinstance(doc, dict) and doc.get("streams") else None


def video_info(probe: dict | None) -> dict:
    """{width, height, duration_s, has_audio, has_video} from an ffprobe document; None/False when absent."""
    info: dict[str, Any] = {"width": None, "height": None, "duration_s": None, "has_audio": False, "has_video": False}
    if not probe:
        return info
    for st in probe.get("streams") or []:
        ctype = st.get("codec_type")
        if ctype == "video" and not info["has_video"]:
            info["has_video"] = True
            info["width"] = int(st["width"]) if st.get("width") else None
            info["height"] = int(st["height"]) if st.get("height") else None
            if st.get("duration"):
                try:
                    info["duration_s"] = round(float(st["duration"]), 2)
                except ValueError:
                    pass
        elif ctype == "audio":
            info["has_audio"] = True
    fmt = probe.get("format") or {}
    if info["duration_s"] is None and fmt.get("duration"):
        try:
            info["duration_s"] = round(float(fmt["duration"]), 2)
        except ValueError:
            pass
    return info


# --------------------------------------------------------------------------- images

def _pil():
    from PIL import Image  # optional at import time, required at call time
    return Image


def image_dims(path: Path | str) -> tuple[int, int] | None:
    """(width, height) via pillow; None when the file is not a decodable image."""
    try:
        Image = _pil()
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:  # noqa: BLE001 - any decode failure means "not an image"
        return None


def make_preview(src: Path, dst: Path, max_edge: int = PREVIEW_MAX_EDGE) -> tuple[int, int] | None:
    """Write a JPEG preview of `src` with its long edge at most `max_edge`; returns the ORIGINAL dims or None."""
    try:
        Image = _pil()
        with Image.open(src) as im:
            orig = (int(im.size[0]), int(im.size[1]))
            if getattr(im, "n_frames", 1) > 1:
                im.seek(0)
            rgb = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
            if rgb.mode == "RGBA":
                bg = Image.new("RGB", rgb.size, (255, 255, 255))
                bg.paste(rgb, mask=rgb.split()[-1])
                rgb = bg
            rgb.thumbnail((max_edge, max_edge))
            dst.parent.mkdir(parents=True, exist_ok=True)
            rgb.save(dst, "JPEG", quality=85, optimize=True)
            return orig
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- video

def extract_keyframes(src: Path, out_dir: Path, duration: float | None) -> list[dict]:
    exe = have("ffmpeg")
    frames: list[dict] = []
    if not exe:
        return frames
    d = float(duration or 0.0)
    for pct in KEYFRAME_PCTS:
        t = max(0.0, d * pct / 100.0)
        if pct == 100 and d > 0:
            t = max(0.0, d - min(0.1, d / 10))
        out = out_dir / f"kf_{pct:03d}.jpg" if pct == 100 else out_dir / f"kf_{pct:02d}.jpg"
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
               "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "3", str(out)]
        try:
            res = _run(cmd)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if res.returncode == 0 and out.exists() and out.stat().st_size > 0:
            frames.append({"file": out.name, "t_s": round(t, 3), "source": "keyframe", "pct": pct})
        elif out.exists():
            out.unlink()
    return frames


def extract_scene_frames(src: Path, out_dir: Path, threshold: float = SCENE_THRESHOLD,
                         limit: int = MAX_SCENE_FRAMES) -> list[dict]:
    exe = have("ffmpeg")
    if not exe:
        return []
    for old in out_dir.glob("scene_*.jpg"):
        old.unlink()
    pattern = out_dir / "scene_%02d.jpg"
    vf = f"select='gt(scene,{threshold})',showinfo,scale={FRAME_WIDTH}:-2"
    cmd = [exe, "-hide_banner", "-loglevel", "info", "-nostats", "-y", "-i", str(src), "-vf", vf, "-fps_mode", "vfr",
           "-frames:v", str(limit), "-q:v", "3", str(pattern)]
    try:
        res = _run(cmd)
    except (subprocess.TimeoutExpired, OSError):
        return []
    times = [float(m) for m in _PTS_RE.findall(res.stderr or "")]
    files = sorted(out_dir.glob("scene_*.jpg"))
    frames = []
    for i, f in enumerate(files):
        frames.append({"file": f.name, "t_s": round(times[i], 3) if i < len(times) else None, "source": "scene"})
    return frames


def contact_sheet(images: list[Path], dst: Path) -> bool:
    """3x3 contact sheet of up to nine images via ffmpeg `tile` (cells padded to CONTACT_CELL squares)."""
    exe = have("ffmpeg")
    images = [p for p in images if p.exists()][:9]
    if not exe or not images:
        return False
    tmp = dst.parent / ".sheet"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        Image = _pil()
        for i, p in enumerate(images, 1):
            with Image.open(p) as im:
                im.convert("RGB").save(tmp / f"s_{i:02d}.jpg", "JPEG", quality=90)
        vf = (f"scale={CONTACT_CELL}:{CONTACT_CELL}:force_original_aspect_ratio=decrease,"
              f"pad={CONTACT_CELL}:{CONTACT_CELL}:(ow-iw)/2:(oh-ih)/2:color=black,"
              f"tile={CONTACT_TILE}:padding=4:margin=4:color=black")
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-framerate", "1", "-start_number", "1",
               "-i", str(tmp / "s_%02d.jpg"), "-vf", vf, "-frames:v", "1", "-q:v", "4", str(dst)]
        res = _run(cmd)
        return res.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception:  # noqa: BLE001
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract_audio(src: Path, dst: Path) -> bool:
    exe = have("ffmpeg")
    if not exe:
        return False
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
           "-c:a", "pcm_s16le", str(dst)]
    try:
        res = _run(cmd)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return res.returncode == 0 and dst.exists() and dst.stat().st_size > 0


# --------------------------------------------------------------------------- pdf

def _natural_key(p: Path) -> tuple:
    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name))


def pdf_pages(src: Path, out_dir: Path, dpi: int = 80) -> list[Path]:
    exe = have("pdftoppm")
    if not exe:
        return []
    for old in out_dir.glob("page-*.png"):
        old.unlink()
    try:
        res = _run([exe, "-r", str(dpi), "-png", str(src), str(out_dir / "page")], timeout=600)
    except (subprocess.TimeoutExpired, OSError):
        return []
    if res.returncode != 0:
        return []
    return sorted(out_dir.glob("page-*.png"), key=_natural_key)


# --------------------------------------------------------------------------- post files

def find_post(post_id: str) -> Path | None:
    for rel in SPLIT_DIRS.values():
        p = common.ROOT / rel / f"{post_id}.md"
        if p.is_file():
            return p
    return None


def all_posts() -> list[Path]:
    out: list[Path] = []
    for rel in SPLIT_DIRS.values():
        d = common.ROOT / rel
        if d.is_dir():
            out.extend(sorted(d.glob("*.md")))
    return out


def _abs(rel_path: Any) -> Path | None:
    if not rel_path or not isinstance(rel_path, str):
        return None
    p = Path(rel_path)
    return p if p.is_absolute() else common.ROOT / p


def _ordered(entry: dict) -> dict:
    out = {k: entry.get(k) for k in MEDIA_KEYS}
    for k, v in entry.items():
        if k not in out:
            out[k] = v
    return out


def frames_dir_for(post_id: str, index: int, first_frames_index: int) -> Path:
    name = post_id if index == first_frames_index else f"{post_id}_{index}"
    return common.ROOT / "corpus" / "frames" / name


def _write_frames_json(frames_dir: Path, frames: list[dict], extra: dict | None = None) -> None:
    doc = {"frames": frames}
    if extra:
        doc.update(extra)
    common.write_json(frames_dir / "frames.json", doc)


def _transcript_hookup(post_id: str, entry: dict) -> str | None:
    cur = entry.get("transcript")
    if isinstance(cur, str) and cur.strip():
        p = _abs(cur)
        if p is not None and p.is_file():
            return common.rel(p)
        return cur  # inline text or an unknown path: leave as supplied
    default = common.ROOT / "corpus" / "media" / post_id / "transcript.txt"
    return common.rel(default) if default.is_file() else None


def _prepare_image(post_id: str, index: int, entry: dict, src: Path, force: bool) -> tuple[dict, dict]:
    preview = common.ROOT / "corpus" / "media" / post_id / f"preview_{index}.jpg"
    res: dict[str, Any] = {"index": index, "kind": "image", "status": "prepared", "preview": None, "frames_dir": None,
                           "frames": 0, "audio": False, "transcript": None, "error": None}
    if preview.is_file() and entry.get("preview") and not force and entry.get("width"):
        res["status"] = "unchanged"
        res["preview"] = entry.get("preview")
        return entry, res
    dims = make_preview(src, preview)
    if dims is None:
        entry = dict(entry, kind="unavailable", note="image not decodable")
        res.update(status="unavailable", kind="unavailable", error="image not decodable")
        return entry, res
    entry = dict(entry, preview=common.rel(preview), width=dims[0], height=dims[1])
    res["preview"] = entry["preview"]
    return entry, res


def _prepare_video(post_id: str, index: int, entry: dict, src: Path, frames_dir: Path, force: bool) -> tuple[dict, dict]:
    preview = common.ROOT / "corpus" / "media" / post_id / f"preview_{index}.jpg"
    contact = frames_dir / "contact.jpg"
    res: dict[str, Any] = {"index": index, "kind": "video", "status": "prepared", "preview": None,
                           "frames_dir": common.rel(frames_dir), "frames": 0, "audio": False, "transcript": None,
                           "error": None}
    if contact.is_file() and entry.get("frames_dir") and not force:
        res["status"] = "unchanged"
        res["preview"] = entry.get("preview")
        res["frames"] = len(list(frames_dir.glob("*.jpg"))) - 1
        res["audio"] = (frames_dir / "audio.wav").is_file()
        return entry, res
    if not have("ffprobe") or not have("ffmpeg"):
        res.update(status="skipped", error="ffmpeg/ffprobe not installed", frames_dir=None)
        return entry, res
    probe = ffprobe_json(src)
    info = video_info(probe)
    if probe is None or not info["has_video"]:
        entry = dict(entry, kind="unavailable", note="video not probeable")
        res.update(status="unavailable", kind="unavailable", error="video not probeable", frames_dir=None)
        return entry, res
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames = extract_keyframes(src, frames_dir, info["duration_s"])
    frames += extract_scene_frames(src, frames_dir)
    _write_frames_json(frames_dir, frames, {"duration_s": info["duration_s"], "width": info["width"],
                                            "height": info["height"], "has_audio": info["has_audio"]})
    sheet_ok = contact_sheet([frames_dir / f["file"] for f in frames], contact)
    audio_ok = False
    wav = frames_dir / "audio.wav"
    if info["has_audio"]:
        audio_ok = extract_audio(src, wav)
    elif wav.exists():
        wav.unlink()
    if sheet_ok:
        preview.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(contact, preview)
    entry = dict(entry, preview=common.rel(preview) if sheet_ok else entry.get("preview"),
                 width=info["width"], height=info["height"], duration_s=info["duration_s"],
                 frames_dir=common.rel(frames_dir))
    res.update(preview=entry["preview"], frames=len(frames), audio=audio_ok)
    if not frames:
        res["error"] = "no frames extracted"
    return entry, res


def _prepare_pdf(post_id: str, index: int, entry: dict, src: Path, frames_dir: Path, force: bool) -> tuple[dict, dict]:
    preview = common.ROOT / "corpus" / "media" / post_id / f"preview_{index}.jpg"
    res: dict[str, Any] = {"index": index, "kind": "carousel", "status": "prepared", "preview": None,
                           "frames_dir": common.rel(frames_dir), "frames": 0, "audio": False, "transcript": None,
                           "error": None}
    existing = sorted(frames_dir.glob("page-*.png"), key=_natural_key) if frames_dir.is_dir() else []
    if existing and entry.get("frames_dir") and preview.is_file() and not force:
        res.update(status="unchanged", preview=entry.get("preview"), frames=len(existing))
        return entry, res
    if not have("pdftoppm"):
        res.update(status="skipped", error="pdftoppm not installed", frames_dir=None)
        return entry, res
    frames_dir.mkdir(parents=True, exist_ok=True)
    pages = pdf_pages(src, frames_dir)
    if not pages:
        entry = dict(entry, kind="unavailable", note="pdf has no renderable pages")
        res.update(status="unavailable", kind="unavailable", error="pdf has no renderable pages", frames_dir=None)
        return entry, res
    dims = make_preview(pages[0], preview)
    _write_frames_json(frames_dir, [{"file": p.name, "t_s": None, "source": "page", "page": i}
                                    for i, p in enumerate(pages, 1)], {"pages": len(pages)})
    contact_sheet(pages, frames_dir / "contact.jpg")
    entry = dict(entry, preview=common.rel(preview) if dims else None, width=dims[0] if dims else None,
                 height=dims[1] if dims else None, frames_dir=common.rel(frames_dir), pages=len(pages))
    res.update(preview=entry["preview"], frames=len(pages))
    return entry, res


def prepare_post(path: Path | str, force: bool = False) -> dict:
    """Prepare every media entry of one post file, rewriting the file when an entry changed."""
    p = Path(path)
    if not p.is_absolute():
        p = common.ROOT / p
    meta, body = common.read_front_matter_file(p)
    post_id = str(meta.get("post_id") or p.stem)
    entries = meta.get("media") or []
    if not isinstance(entries, list):
        entries = []
    first_frames_index = next((i for i, e in enumerate(entries, 1)
                               if isinstance(e, dict) and e.get("kind") in ("video", "carousel")), None)
    results: list[dict] = []
    new_entries: list[dict] = []
    changed = False
    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            new_entries.append(entry)
            continue
        kind = entry.get("kind")
        src = _abs(entry.get("path"))
        res: dict[str, Any]
        if kind == "unavailable" or src is None:
            res = {"index": i, "kind": kind, "status": "skipped", "preview": None, "frames_dir": None, "frames": 0,
                   "audio": False, "transcript": None, "error": "unavailable at ingest" if kind == "unavailable" else "no path"}
            new_entries.append(entry)
            results.append(res)
            continue
        if not src.is_file():
            new = dict(entry, kind="unavailable", note="media file missing")
            res = {"index": i, "kind": "unavailable", "status": "unavailable", "preview": None, "frames_dir": None,
                   "frames": 0, "audio": False, "transcript": None, "error": f"media file missing: {entry.get('path')}"}
            new_entries.append(_ordered(new))
            results.append(res)
            changed = True
            continue
        if kind == "video":
            new, res = _prepare_video(post_id, i, entry, src, frames_dir_for(post_id, i, first_frames_index or i), force)
        elif kind == "carousel":
            new, res = _prepare_pdf(post_id, i, entry, src, frames_dir_for(post_id, i, first_frames_index or i), force)
        elif kind in ("image", "screenshot"):
            new, res = _prepare_image(post_id, i, entry, src, force)
        else:
            new, res = entry, {"index": i, "kind": kind, "status": "skipped", "preview": None, "frames_dir": None,
                               "frames": 0, "audio": False, "transcript": None, "error": f"unknown kind {kind!r}"}
        transcript = _transcript_hookup(post_id, new)
        if transcript != new.get("transcript"):
            new = dict(new, transcript=transcript)
        res["transcript"] = new.get("transcript")
        new = _ordered(new)
        if new != _ordered(entry):
            changed = True
        new_entries.append(new)
        results.append(res)
    if changed:
        meta["media"] = new_entries
        common.write_front_matter_file(p, meta, body)
    return {"post_id": post_id, "path": common.rel(p), "media": results, "changed": changed}


def run(post: str | None = None, all_: bool = False, force: bool = False) -> dict:
    tools = {"ffmpeg": bool(have("ffmpeg")), "ffprobe": bool(have("ffprobe")), "pdftoppm": bool(have("pdftoppm"))}
    if post:
        p = find_post(post)
        if p is None:
            return {"ok": False, "error": f"post not found: {post}"}
        paths = [p]
    elif all_:
        paths = all_posts()
    else:
        return {"ok": False, "error": "pass --post <id> or --all"}
    posts: dict[str, dict] = {}
    counts = {"prepared": 0, "unchanged": 0, "unavailable": 0, "skipped": 0}
    for p in paths:
        try:
            doc = prepare_post(p, force=force)
        except Exception as e:  # noqa: BLE001 - one bad post must not stop --all
            posts[p.stem] = {"post_id": p.stem, "path": common.rel(p), "media": [], "changed": False,
                             "error": f"{type(e).__name__}: {e}"}
            continue
        posts[doc["post_id"]] = doc
        for r in doc["media"]:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"ok": True, "posts": posts, **counts, "tools": tools}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Previews, frames, contact sheets, audio and transcript hookup for corpus "
                                             "media; updates the post file's media entries (contracts section 17).")
    ap.add_argument("--post", default=None, help="post id (corpus/posts, corpus/heldout or corpus/self)")
    ap.add_argument("--all", dest="all_", action="store_true", help="every post with media")
    ap.add_argument("--force", action="store_true", help="rebuild entries that are already prepared")
    ap.add_argument("--root", default=None, help="project root (default: $POSTSMITH_ROOT or this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        with common.use_root(args.root):
            doc = run(args.post, args.all_, args.force)
    except FileNotFoundError as e:
        doc = {"ok": False, "error": str(e)}
    common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
