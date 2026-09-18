"""Tests for ingest_normalize.py, ingest_commit.py and media_prepare.py.

Text fixtures under tools/tests/fixtures/ingest/ carry the awkward inputs: a BOM, synonym headers,
multi-line cells, `---` separated posts, front matter, and rows missing a platform or an author. Binary media
is generated inside the tests with pillow, ffmpeg and sips, so those tests skip when the tool is absent.

Every test runs against a scratch root under tmp_path through common.use_root, never the repository corpus.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import common  # noqa: E402
import ingest_commit as ic  # noqa: E402
import ingest_normalize as norm  # noqa: E402
import media_prepare as mp  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "ingest"
PROJECT = TOOLS.parent
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
HAVE_PDFTOPPM = bool(shutil.which("pdftoppm"))
HAVE_SIPS = sys.platform == "darwin" and bool(shutil.which("sips"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
needs_pdftoppm = pytest.mark.skipif(not HAVE_PDFTOPPM, reason="pdftoppm not installed")
needs_sips = pytest.mark.skipif(not HAVE_SIPS, reason="sips (macOS) not available")

POST_KEYS = ["schema", "post_id", "author", "platform", "posted_at", "url", "lang", "source", "content_sha256", "split",
             "crosspost_of", "variant_of", "context", "engagement", "media", "text_stats"]
MEDIA_KEYS = ["kind", "path", "preview", "sha256", "width", "height", "duration_s", "frames_dir", "transcript",
              "provided_description"]


# --------------------------------------------------------------------------- helpers

@pytest.fixture(autouse=True)
def _restore_root():
    root, cfg, env = common.ROOT, common._CONFIG, os.environ.get("POSTSMITH_ROOT")
    before = sorted(p.name for p in (PROJECT / "corpus" / "inbox").glob("*")) if (PROJECT / "corpus" / "inbox").exists() else []
    yield
    common.ROOT, common._CONFIG = root, cfg
    if env is None:
        os.environ.pop("POSTSMITH_ROOT", None)
    else:
        os.environ["POSTSMITH_ROOT"] = env
    after = sorted(p.name for p in (PROJECT / "corpus" / "inbox").glob("*")) if (PROJECT / "corpus" / "inbox").exists() else []
    assert before == after, "a test wrote into the repository inbox"


def make_root(tmp_path: Path, name: str = "root") -> Path:
    root = tmp_path / name
    (root / "config").mkdir(parents=True)
    (root / "corpus" / "inbox").mkdir(parents=True)
    shutil.copyfile(PROJECT / "config" / "postsmith.yaml", root / "config" / "postsmith.yaml")
    (root / "pyproject.toml").write_text('[project]\nname = "ingest-root"\nversion = "0"\n', encoding="utf-8")
    return root


def inbox(root: Path) -> Path:
    return root / "corpus" / "inbox"


def stage(root: Path, *names: str) -> Path:
    """Copy fixture files into the scratch inbox; returns the path of the first one."""
    out = None
    for n in names:
        dst = inbox(root) / n
        shutil.copyfile(FIX / n, dst)
        out = out or dst
    assert out is not None
    return out


def run_normalize(root: Path, src: Path | str, **kw) -> dict:
    with common.use_root(root):
        return norm.normalize(str(src), **kw)


def run_commit(root: Path, file: str, **kw) -> dict:
    with common.use_root(root):
        return ic.commit(file, **kw)


def run_prepare(root: Path, post: str | None = None, all_: bool = False, force: bool = False) -> dict:
    with common.use_root(root):
        return mp.run(post, all_, force)


def read_post(root: Path, split: str, post_id: str) -> tuple[dict, str]:
    d = {"train": "posts", "heldout": "heldout", "self": "self"}[split]
    return common.split_front_matter((root / "corpus" / d / f"{post_id}.md").read_text(encoding="utf-8"))


def manifest(root: Path) -> list[dict]:
    return common.read_jsonl(root / "corpus" / "manifest.jsonl")


def write_json_source(root: Path, name: str, rows: list[dict]) -> Path:
    p = inbox(root) / name
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def png(path: Path, size: tuple[int, int] = (400, 300), color: tuple[int, int, int] = (200, 30, 30)) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def pdf(path: Path) -> Path:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(im).rectangle([50, 50, 550, 200], fill=(30, 30, 200))
    im.save(path)
    return path


def video(path: Path, audio: bool = False, seconds: int = 2) -> Path:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000"]
    cmd += ["-t", str(seconds), "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def scene_video(path: Path) -> Path:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for c in ("red", "blue", "green"):
        cmd += ["-f", "lavfi", "-i", f"color={c}:s=320x240:d=1:r=10"]
    cmd += ["-filter_complex", "[0][1][2]concat=n=3:v=1:a=0,format=yuv420p", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def long_post(i: int, author: str) -> str:
    return (f"Deal {i} for {author} closed on day {i * 3} after {i + 7} calls.\n\n"
            f"The CFO asked for {i * 11} percent and got a spreadsheet with {i * 2 + 1} tabs instead.\n\n"
            f"Tab {i + 1} is the one that mattered.")


def short_post(i: int, author: str) -> str:
    return f"deal {i} for {author}: {i + 7} calls, {i * 11} percent asked, one spreadsheet delivered"


# --------------------------------------------------------------------------- ingest_normalize

def test_csv_with_bom_synonyms_and_multiline_cells(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src = stage(root, "posts_synonyms.csv")
    assert src.read_bytes().startswith(b"\xef\xbb\xbf")
    doc = run_normalize(root, src)
    assert doc["ok"] and doc["rows"] == 4 and doc["needs"] == []
    assert doc["unmapped_columns"] == ["Notes"]
    assert doc["mapping"] == {"author": "Name", "text": "Content", "platform": "Network", "media": "Image",
                              "posted_at": "Date", "likes": "Likes", "comments": "Comments"}
    assert doc["file"].startswith("corpus/inbox/normalized_") and doc["file"].endswith(".jsonl")
    rows = common.read_jsonl(root / doc["file"])
    assert [r["source_ref"] for r in rows] == [f"posts_synonyms.csv#{i}" for i in range(1, 5)]
    r1, r2, r3, r4 = rows
    assert r1["author_name"] == "Lara Acosta" and r1["author_slug"] == "lara-acosta"
    assert r1["platform"] == "linkedin" and r1["posted_at"] == "2026-05-01"
    assert r1["text"].count("\n") == 6 and r1["text"].startswith("We cancelled") and r1["text"].endswith("phone number.")
    assert r1["engagement"] == {"likes": 1200, "comments": 340, "reposts": None, "views": None}
    assert r1["media"] == [{"path_or_url": "acosta_sko.png", "description": None}]  # not next to the CSV: kept verbatim
    assert r1["source_kind"] == "csv" and r1["lang"] == "en"
    assert r2["platform"] == "linkedin" and r2["posted_at"] == "2026-05-14"     # "li" alias, US date
    assert r3["platform"] == "x" and r3["engagement"]["likes"] == 800            # inferred: short, one line
    assert r4["platform"] == "x" and r4["engagement"]["likes"] == 2300           # column ("twitter") beats the url
    assert doc["platforms"] == {"linkedin": 2, "x": 2, "unknown": 0}


def test_csv_needs_platform_until_flag(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src = stage(root, "needs_platform.csv")
    doc = run_normalize(root, src)
    assert doc["ok"] and doc["needs"] == ["platform"] and doc["needs_rows"] == {"platform": ["needs_platform.csv#1"]}
    assert common.read_jsonl(root / doc["file"])[0]["platform"] is None
    doc2 = run_normalize(root, src, platform="LinkedIn")
    assert doc2["needs"] == [] and common.read_jsonl(root / doc2["file"])[0]["platform"] == "linkedin"
    bad = run_normalize(root, src, platform="mastodon")
    assert bad["ok"] is False and "linkedin or x" in bad["error"]


def test_csv_needs_author_until_flag(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src = stage(root, "no_author.csv")
    doc = run_normalize(root, src)
    assert doc["needs"] == ["author"] and doc["rows"] == 2
    doc2 = run_normalize(root, src, author="Kai Nakamura")
    rows = common.read_jsonl(root / doc2["file"])
    assert doc2["needs"] == [] and {r["author_slug"] for r in rows} == {"kai-nakamura"}


def test_mapping_override_and_self_routing(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src = stage(root, "posts_synonyms.csv")
    doc = run_normalize(root, src, mapping={"text": "Notes"})
    assert doc["ok"] and doc["mapping"]["text"] == "Notes" and "Content" in doc["unmapped_columns"]
    assert doc["rows"] == 2 and [s["reason"] for s in doc["skipped"]] == ["empty text", "empty text"]
    bad = run_normalize(root, src, mapping={"headline": "Notes"})
    assert bad["ok"] is False and "unknown field" in bad["error"]
    missing = run_normalize(root, src, mapping={"text": "Nope"})
    assert missing["ok"] is False and "not found" in missing["error"]
    selfdoc = run_normalize(root, src, self_=True)
    rows = common.read_jsonl(root / selfdoc["file"])
    assert {r["author_slug"] for r in rows} == {"self"} and rows[0]["author_name"] == "Lara Acosta"


def test_json_array_engagement_media_and_url_platform(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src = stage(root, "posts.json")
    doc = run_normalize(root, src)
    assert doc["ok"] and doc["rows"] == 3 and doc["needs"] == [] and doc["kind"] == "json"
    rows = common.read_jsonl(root / doc["file"])
    assert rows[0]["engagement"] == {"likes": 5400, "comments": 210, "reposts": 90, "views": None}
    assert rows[0]["media"] == [{"path_or_url": "bloom_chart.png", "description": "bar chart, three bars"}]
    assert rows[1]["platform"] == "x" and rows[1]["url"] == "https://x.com/paulg/status/1"
    assert rows[2]["lang"] == "other" and doc["non_english"] == ["posts.json#3"]
    assert rows[2]["media"][0]["path_or_url"] == "https://pbs.example.com/img/1.jpg"
    jsonl = inbox(root) / "rows.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in json.loads(src.read_text())) + "\n", encoding="utf-8")
    assert run_normalize(root, jsonl)["rows"] == 3
    broken = inbox(root) / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert run_normalize(root, broken)["ok"] is False


def test_markdown_blocks_and_front_matter(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    blocks = stage(root, "posts_blocks.md")
    doc = run_normalize(root, blocks)
    assert doc["ok"] and doc["rows"] == 3 and doc["unmapped_columns"] == ["rewrite_of"]
    rows = common.read_jsonl(root / doc["file"])
    assert rows[0]["text"] == "chatgpt is a guy on reddit 8 years ago, but polite" and rows[0]["platform"] == "x"
    assert rows[1]["posted_at"] == "2026-02-11" and rows[1]["engagement"]["likes"] == 1200
    assert rows[1]["media"] == [{"path_or_url": "puri_screenshot.png", "description": None}]
    assert rows[1]["text"].startswith("I sold my company") and rows[1]["text"].endswith("was the exit.")
    assert rows[2]["text"].startswith("Second long one.")
    single = stage(root, "single_post.md")
    doc = run_normalize(root, single)
    assert doc["rows"] == 1
    r = common.read_jsonl(root / doc["file"])[0]
    assert r["media"] == [{"path_or_url": "acosta_whiteboard.jpg", "description": "whiteboard with three boxes"}]
    assert r["url"].startswith("https://www.linkedin.com/") and r["platform"] == "linkedin"
    assert r["text"].startswith("We killed our AI strategy") and r["engagement"]["comments"] == 340
    mixed = inbox(root) / "mixed.md"
    mixed.write_text(single.read_text() + "---\nauthor: Lara Acosta\nplatform: x\n\nthe slide was the strategy\n",
                     encoding="utf-8")
    doc = run_normalize(root, mixed)
    assert doc["rows"] == 2 and [r["platform"] for r in common.read_jsonl(root / doc["file"])] == ["linkedin", "x"]


def test_normalize_user_errors(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    assert run_normalize(root, "corpus/inbox/nope.csv")["ok"] is False
    odd = inbox(root) / "posts.xyz"
    odd.write_text("a,b\n1,2\n", encoding="utf-8")
    assert "kind" in run_normalize(root, odd)["error"]
    assert run_normalize(root, odd, kind="csv")["ok"] is True
    fake = inbox(root) / "normalized_deadbeef.jsonl"
    fake.write_text("{}\n", encoding="utf-8")
    assert "ingest_commit" in run_normalize(root, fake)["error"]


def test_value_parsers() -> None:
    assert norm.parse_int("1.2k") == 1200 and norm.parse_int("3,400") == 3400 and norm.parse_int("1.5M") == 1500000
    assert norm.parse_int("") is None and norm.parse_int("n/a") is None and norm.parse_int(12) == 12
    assert norm.parse_date("2026-05-01") == "2026-05-01" and norm.parse_date("2026-05-01T10:00:00Z") == "2026-05-01"
    assert norm.parse_date("05/14/2026") == "2026-05-14" and norm.parse_date("March 2, 2026") == "2026-03-02"
    assert norm.parse_date("yesterday") is None and norm.parse_date("") is None
    assert norm.slugify("Lara Acosta") == "lara-acosta" and norm.slugify("@laraacosta") == "laraacosta"
    assert norm.slugify("Jasmin Alić") == "jasmin-alic" and norm.slugify("42 Labs") == "author-42-labs"
    assert norm.slugify("") == "unknown"
    assert norm.infer_platform("a" * 280) == "x" and norm.infer_platform("a" * 281) is None
    assert norm.infer_platform("one\ntwo") is None
    assert norm.platform_from_url("https://www.linkedin.com/posts/x") == "linkedin"
    assert norm.platform_from_url("https://twitter.com/a/status/1") == "x" and norm.platform_from_url("https://example.com") is None
    assert norm.normalize_platform("Twitter") == "x" and norm.normalize_platform("Linked In") == "linkedin"
    assert norm.normalize_platform("mastodon") is None
    mapping, unmapped = norm.build_mapping(["Name", "Handle", "Post Body", "Reactions", "Notes"])
    assert mapping == {"author": "Name", "handle": "Handle", "text": "Post Body", "likes": "Reactions"}
    assert unmapped == ["Notes"]


# --------------------------------------------------------------------------- ingest_commit

def test_commit_writes_posts_manifest_media_and_moves_sources(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src = stage(root, "posts_synonyms.csv")
    png(inbox(root) / "acosta_sko.png", size=(640, 480))
    ndoc = run_normalize(root, src)
    rows = common.read_jsonl(root / ndoc["file"])
    assert rows[0]["media"][0]["path_or_url"] == "corpus/inbox/acosta_sko.png"
    doc = run_commit(root, ndoc["file"])
    assert doc["ok"], doc
    assert doc["ingested"] == ["lara-acosta_001", "lara-acosta_002", "jasmin-alic_001", "jasmin-alic_002"]
    assert doc["skipped"] == [] and doc["variants"] == [] and doc["crossposts"] == [] and doc["remote_media"] == []
    assert doc["small_corpus_mode"] is True and doc["split_applied"] is False
    assert doc["heldout_counts"] == {"linkedin": 0, "x": 0}
    assert doc["counts"]["train"] == {"total": 4, "linkedin": 2, "x": 2}
    assert [r["url"] for r in doc["refused_urls"]] == ["https://www.linkedin.com/posts/jasmin-alic_pricing-activity-1234"]

    meta, body = read_post(root, "train", "lara-acosta_001")
    assert list(meta.keys()) == POST_KEYS
    assert meta["schema"] == "postsmith.post/1" and meta["split"] == "train"
    assert meta["author"] == {"name": "Lara Acosta", "slug": "lara-acosta", "handle": None}
    assert meta["platform"] == "linkedin" and meta["posted_at"] == "2026-05-01" and meta["url"] is None
    assert meta["source"]["kind"] == "csv" and meta["source"]["ref"] == "posts_synonyms.csv#1"
    assert meta["source"]["file"] == "corpus/inbox/done/posts_synonyms.csv" and (root / meta["source"]["file"]).is_file()
    assert meta["source"]["ingested_at"].endswith("Z")
    assert body == rows[0]["text"] + "\n"                       # verbatim, one trailing newline
    assert meta["content_sha256"] == common.content_sha(rows[0]["text"])
    assert meta["text_stats"] == {"chars": len(rows[0]["text"]), "words": len(common.words(rows[0]["text"])),
                                  "lines": 7, "blank_lines": 3}
    assert meta["engagement"] == {"likes": 1200, "comments": 340, "reposts": None, "views": None}
    m = meta["media"][0]
    assert list(m.keys()) == MEDIA_KEYS
    assert m["kind"] == "image" and m["path"] == "corpus/media/lara-acosta_001/1.png"
    assert m["width"] == 640 and m["height"] == 480 and m["preview"] is None
    assert m["sha256"] == hashlib.sha256((root / m["path"]).read_bytes()).hexdigest()
    meta4, _ = read_post(root, "train", "jasmin-alic_002")
    assert meta4["media"][0]["kind"] == "unavailable" and meta4["media"][0]["source_url"].startswith("https://www.linkedin.com/")

    rows_m = manifest(root)
    assert [r["post_id"] for r in rows_m] == doc["ingested"]
    assert set(rows_m[0].keys()) == {"content_sha256", "author_slug", "post_id", "split", "source", "ingested_at",
                                     "crosspost_of", "variant_of"}
    assert rows_m[0]["source"] == meta["source"]
    moved_from = {m["from"] for m in doc["moved"]}
    assert moved_from == {"corpus/inbox/posts_synonyms.csv", "corpus/inbox/acosta_sko.png", ndoc["file"]}
    assert sorted(p.name for p in inbox(root).iterdir()) == ["done"]
    assert (inbox(root) / "done" / "acosta_sko.png").is_file()


def test_commit_refuses_incomplete_rows_and_missing_file(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    ndoc = run_normalize(root, stage(root, "needs_platform.csv"))
    doc = run_commit(root, ndoc["file"])
    assert doc["ok"] is False and "no platform" in doc["error"]
    assert not (root / "corpus" / "manifest.jsonl").exists() and not (root / "corpus" / "posts").exists()
    assert (root / ndoc["file"]).is_file()  # nothing moved
    assert run_commit(root, "corpus/inbox/normalized_missing.jsonl")["ok"] is False
    bad = inbox(root) / "normalized_bad.jsonl"
    bad.write_text("{\n", encoding="utf-8")
    assert run_commit(root, "corpus/inbox/normalized_bad.jsonl")["ok"] is False


def test_commit_dedupe_crosspost_and_variant(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    base = long_post(1, "kessler")
    variant = base.replace("Tab 2 is the one that mattered.", "Tab 2 is the one that mattered, obviously.")
    rows = [
        {"author": "Dana Kessler", "platform": "linkedin", "text": base},
        {"author": "Dana Kessler", "platform": "linkedin", "text": base + "\n"},            # exact duplicate
        {"author": "Dana Kessler", "platform": "x", "text": base},                          # crosspost
        {"author": "Dana Kessler", "platform": "linkedin", "text": variant},                # near duplicate
        {"author": "Mira Okonkwo", "platform": "linkedin", "text": base},                   # other author: new post
        {"author": "Dana Kessler", "platform": "linkedin", "text": long_post(9, "kessler")},
    ]
    ndoc = run_normalize(root, write_json_source(root, "dupes.json", rows))
    doc = run_commit(root, ndoc["file"])
    assert doc["ok"], doc
    assert doc["ingested"] == ["dana-kessler_001", "dana-kessler_002", "dana-kessler_003", "mira-okonkwo_001", "dana-kessler_004"]
    assert doc["skipped"] == [{"source_ref": "dupes.json#2", "reason": "duplicate", "post_id": "dana-kessler_001"}]
    assert doc["crossposts"] == [{"post_id": "dana-kessler_002", "crosspost_of": "dana-kessler_001"}]
    assert len(doc["variants"]) == 1 and doc["variants"][0]["post_id"] == "dana-kessler_003"
    assert doc["variants"][0]["variant_of"] == "dana-kessler_001" and doc["variants"][0]["jaccard"] >= 0.8
    m2, _ = read_post(root, "train", "dana-kessler_002")
    m3, _ = read_post(root, "train", "dana-kessler_003")
    m4, _ = read_post(root, "train", "dana-kessler_004")
    mo, _ = read_post(root, "train", "mira-okonkwo_001")
    assert m2["crosspost_of"] == "dana-kessler_001" and m2["variant_of"] is None and m2["platform"] == "x"
    assert m3["variant_of"] == "dana-kessler_001" and m3["crosspost_of"] is None
    assert m4["variant_of"] is None and mo["crosspost_of"] is None and mo["variant_of"] is None
    rows_m = manifest(root)
    assert [r["post_id"] for r in rows_m] == doc["ingested"]
    assert rows_m[1]["crosspost_of"] == "dana-kessler_001" and rows_m[2]["variant_of"] == "dana-kessler_001"


def test_rerun_of_the_same_source_is_idempotent(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    ndoc = run_normalize(root, stage(root, "posts_blocks.md"))
    first = run_commit(root, ndoc["file"])
    assert first["ingested"] == ["shaan-puri_001", "shaan-puri_002", "shaan-puri_003"]
    before = (root / "corpus" / "manifest.jsonl").read_bytes()
    ndoc2 = run_normalize(root, "corpus/inbox/done/posts_blocks.md")
    second = run_commit(root, ndoc2["file"])
    assert second["ok"] and second["ingested"] == [] and len(second["skipped"]) == 3
    assert all(s["reason"] == "duplicate" for s in second["skipped"])
    assert (root / "corpus" / "manifest.jsonl").read_bytes() == before
    assert sorted(p.name for p in inbox(root).iterdir()) == ["done"]
    # a further post by the same author continues the sequence
    ndoc3 = run_normalize(root, write_json_source(root, "more.json", [{"author": "Shaan Puri", "platform": "x",
                                                                       "text": "the label maker was the exit"}]))
    assert run_commit(root, ndoc3["file"])["ingested"] == ["shaan-puri_004"]


def test_self_posts_go_to_corpus_self_and_are_never_held_out(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    ndoc = run_normalize(root, stage(root, "posts_synonyms.csv"), self_=True)
    doc = run_commit(root, ndoc["file"], self_=True)
    assert doc["ingested"] == ["self_001", "self_002", "self_003", "self_004"]
    meta, _ = read_post(root, "self", "self_001")
    assert meta["split"] == "self" and meta["author"]["slug"] == "self" and meta["author"]["name"] == "Lara Acosta"
    assert doc["counts"]["self"]["total"] == 4 and doc["heldout_counts"] == {"linkedin": 0, "x": 0}
    assert all(r["split"] == "self" and r["author_slug"] == "self" for r in manifest(root))
    # --self on commit alone also routes rows that were normalized with an author
    ndoc2 = run_normalize(root, write_json_source(root, "me.json", [{"author": "Deep", "platform": "x", "text": "shipped"}]))
    doc2 = run_commit(root, ndoc2["file"], self_=True)
    assert doc2["ingested"] == ["self_005"] and (root / "corpus" / "self" / "self_005.md").is_file()


def test_one_batch_that_crosses_the_bar_gets_a_heldout_split(tmp_path: Path) -> None:
    """The split is decided against the corpus as it will be after the batch, not before it.

    A first `/ingest` drops the whole reference set in at once. Judged against the empty corpus that batch
    looks small, so everything goes to train, and because splits are sticky the heldout split then stays empty
    for ever. An empty heldout split silently disables the oracle, the quote-leak check and every lineup.
    """
    root = make_root(tmp_path)
    cfg = common.load_yaml(root / "config" / "postsmith.yaml")
    min_per = cfg["corpus"]["heldout_min_per_platform"]
    authors = ["Dana Kessler", "Mira Okonkwo", "Tomas Vieira"]
    batch = []
    for i in range(40):
        a = authors[i % 3]
        plat = "linkedin" if i % 2 == 0 else "x"
        batch.append({"author": a, "platform": plat, "text": long_post(i, a) if plat == "linkedin" else short_post(i, a)})
    doc = run_commit(root, run_normalize(root, write_json_source(root, "one.json", batch))["file"])
    assert doc["ok"] and len(doc["ingested"]) == 40
    assert doc["small_corpus_mode"] is False and doc["small_corpus_mode_before"] is True
    assert doc["split_applied"] is True
    assert doc["heldout_counts"]["linkedin"] >= min_per and doc["heldout_counts"]["x"] >= min_per
    for r in manifest(root):
        d = "heldout" if r["split"] == "heldout" else "posts"
        assert (root / "corpus" / d / f"{r['post_id']}.md").is_file()


def test_split_is_all_train_while_small_then_sticky_hash_split_with_top_up(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    cfg = common.load_yaml(root / "config" / "postsmith.yaml")
    modulo = cfg["corpus"]["heldout_modulo"]
    min_per = cfg["corpus"]["heldout_min_per_platform"]
    authors = ["Dana Kessler", "Mira Okonkwo", "Tomas Vieira"]
    batch1 = []
    for i in range(12):                                 # 12 posts, 6 per platform: still under the bar
        a = authors[i % 3]
        plat = "linkedin" if i % 2 == 0 else "x"
        batch1.append({"author": a, "platform": plat, "text": long_post(i, a) if plat == "linkedin" else short_post(i, a)})
    doc1 = run_commit(root, run_normalize(root, write_json_source(root, "batch1.json", batch1))["file"])
    assert doc1["ok"] and len(doc1["ingested"]) == 12 and doc1["variants"] == []
    assert doc1["split_applied"] is False and doc1["heldout_counts"] == {"linkedin": 0, "x": 0}
    assert doc1["small_corpus_mode"] is True            # 12 train posts: small-corpus mode, everything to train
    assert all(r["split"] == "train" for r in manifest(root))
    with common.use_root(root):
        assert common.small_corpus_mode(cfg, root) is True
    manifest_before = manifest(root)

    batch2 = []
    for i in range(100, 116):
        a = authors[i % 3]
        plat = "linkedin" if i % 2 == 0 else "x"
        batch2.append({"author": a, "platform": plat, "text": long_post(i, a) if plat == "linkedin" else short_post(i, a)})
    batch2.append({"author": "Dana Kessler", "platform": "x", "text": batch1[0]["text"]})   # crosspost of a train post
    doc2 = run_commit(root, run_normalize(root, write_json_source(root, "batch2.json", batch2))["file"])
    assert doc2["ok"] and len(doc2["ingested"]) == 17 and doc2["split_applied"] is True
    assert doc2["heldout_counts"]["linkedin"] >= min_per and doc2["heldout_counts"]["x"] >= min_per
    rows_m = manifest(root)
    assert rows_m[:12] == manifest_before                                       # existing rows never rewritten
    new_rows = rows_m[12:]
    assert len(new_rows) == 17
    by_id = {r["post_id"]: r for r in new_rows}
    plat_of = {}
    for r in new_rows:
        meta, _ = read_post(root, r["split"], r["post_id"])
        plat_of[r["post_id"]] = meta["platform"]
        assert meta["split"] == r["split"]
    # every hash-selected post is heldout; the crosspost inherits train from its original
    cross = doc2["crossposts"][0]
    assert by_id[cross["post_id"]]["split"] == "train"
    for r in new_rows:
        if r["post_id"] == cross["post_id"]:
            continue
        if common.is_heldout_by_hash(r["content_sha256"], modulo):
            assert r["split"] == "heldout", r
    # top-up: per platform the heldout set is the hash picks plus the lowest shas among the rest
    for plat in ("linkedin", "x"):
        pool = [r for r in new_rows if plat_of[r["post_id"]] == plat and r["post_id"] != cross["post_id"]]
        hashed = {r["post_id"] for r in pool if common.is_heldout_by_hash(r["content_sha256"], modulo)}
        rest = sorted((r for r in pool if r["post_id"] not in hashed), key=lambda r: r["content_sha256"])
        need = max(0, min_per - len(hashed))
        expected = hashed | {r["post_id"] for r in rest[:need]}
        assert {r["post_id"] for r in pool if r["split"] == "heldout"} == expected
    for r in new_rows:
        d = "heldout" if r["split"] == "heldout" else "posts"
        assert (root / "corpus" / d / f"{r['post_id']}.md").is_file()
    # a third batch never moves anything already split
    snapshot = {r["post_id"]: r["split"] for r in manifest(root)}
    doc3 = run_commit(root, run_normalize(root, write_json_source(root, "batch3.json", [
        {"author": "Tomas Vieira", "platform": "linkedin", "text": long_post(500, "vieira")}]))["file"])
    assert doc3["ok"] and len(doc3["ingested"]) == 1
    assert all(snapshot[r["post_id"]] == r["split"] for r in manifest(root) if r["post_id"] in snapshot)


class _MediaHandler(http.server.BaseHTTPRequestHandler):
    payload = b""

    def log_message(self, *a) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/img.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(self.payload)))
            self.end_headers()
            self.wfile.write(self.payload)
        elif self.path == "/page":
            body = b"<html><body>not a file</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/big.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(300 * 1024 * 1024))
            self.end_headers()
            self.wfile.write(b"\0" * 1024)
        else:
            self.send_error(404)


@pytest.fixture
def media_server(tmp_path: Path):
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (120, 80), (10, 10, 200)).save(buf, "PNG")
    _MediaHandler.payload = buf.getvalue()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MediaHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def test_remote_media_listed_then_fetched_with_consent(tmp_path: Path, media_server: str) -> None:
    root = make_root(tmp_path)
    rows = [
        {"author": "Dana Kessler", "platform": "linkedin", "text": long_post(1, "kessler"),
         "media": [f"{media_server}/img.png", "https://www.linkedin.com/posts/x-activity-1",
                   "https://drive.google.com/file/d/abc/view", "https://x.com/dana/status/1/photo/1"]},
        {"author": "Dana Kessler", "platform": "linkedin", "text": long_post(2, "kessler"),
         "media": [f"{media_server}/page", f"{media_server}/big.mp4", f"{media_server}/missing.png"]},
    ]
    src = write_json_source(root, "remote.json", rows)
    doc = run_commit(root, run_normalize(root, src)["file"])
    assert doc["ok"] and doc["ingested"] == ["dana-kessler_001", "dana-kessler_002"]
    assert [m["url"] for m in doc["remote_media"] if m["kind"] == "direct"] == [f"{media_server}/img.png", f"{media_server}/page",
                                                                               f"{media_server}/big.mp4", f"{media_server}/missing.png"]
    assert [m["url"] for m in doc["remote_media"] if m["kind"] == "drive"] == ["https://drive.google.com/file/d/abc/view"]
    assert sorted(r["url"] for r in doc["refused_urls"]) == ["https://www.linkedin.com/posts/x-activity-1",
                                                             "https://x.com/dana/status/1/photo/1"]
    meta, _ = read_post(root, "train", "dana-kessler_001")
    assert [m["kind"] for m in meta["media"]] == ["unavailable"] * 4
    assert meta["media"][0]["source_url"] == f"{media_server}/img.png" and doc["media"]["copied"] == 0
    assert not (root / "corpus" / "media").exists()

    # consent: the duplicate rows back-fill the media of the existing posts
    doc2 = run_commit(root, run_normalize(root, "corpus/inbox/done/remote.json")["file"], consent_media=True)
    assert doc2["ok"] and doc2["ingested"] == []
    assert doc2["skipped"][0]["media_backfilled"] is True and doc2["media"]["backfilled"] == ["dana-kessler_001"]
    meta, _ = read_post(root, "train", "dana-kessler_001")
    m = meta["media"][0]
    assert m["kind"] == "image" and m["path"] == "corpus/media/dana-kessler_001/1.png" and (m["width"], m["height"]) == (120, 80)
    assert m["sha256"] == hashlib.sha256(_MediaHandler.payload).hexdigest() and m["source_url"] == f"{media_server}/img.png"
    assert [x["kind"] for x in meta["media"][1:]] == ["unavailable"] * 3   # refused / drive stay as they were
    assert any("not a file" in w for w in doc2["warnings"]) and any("too large" in w for w in doc2["warnings"])
    assert any("http 404" in w for w in doc2["warnings"])
    meta2, _ = read_post(root, "train", "dana-kessler_002")
    assert [x["kind"] for x in meta2["media"]] == ["unavailable"] * 3

    # consent on a fresh ingest fetches straight away and refuses the html page and the oversize body
    rows3 = [{"author": "Mira Okonkwo", "platform": "x", "text": "one chart, no caption",
              "media": [f"{media_server}/img.png", f"{media_server}/page", f"{media_server}/big.mp4"]}]
    doc3 = run_commit(root, run_normalize(root, write_json_source(root, "fresh.json", rows3))["file"], consent_media=True)
    meta3, _ = read_post(root, "train", "mira-okonkwo_001")
    assert [x["kind"] for x in meta3["media"]] == ["image", "unavailable", "unavailable"]
    assert meta3["media"][1]["note"] == "not a file (html page)" and meta3["media"][2]["note"].startswith("too large")
    assert doc3["remote_media"] == [] and doc3["media"]["copied"] == 1


def test_missing_and_undecodable_local_media_are_unavailable(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (inbox(root) / "broken.png").write_bytes(b"not really a png")
    (inbox(root) / "notes.docx").write_bytes(b"PK\x03\x04")
    rows = [{"author": "Dana Kessler", "platform": "x", "text": "receipts attached",
             "media": ["gone.jpg", "broken.png", "notes.docx"]}]
    doc = run_commit(root, run_normalize(root, write_json_source(root, "m.json", rows))["file"])
    assert doc["ok"]
    meta, _ = read_post(root, "train", "dana-kessler_001")
    assert [m["kind"] for m in meta["media"]] == ["unavailable"] * 3
    assert meta["media"][0]["note"] == "file not found" and meta["media"][1]["note"] == "image not decodable"
    assert meta["media"][2]["note"].startswith("unsupported media type")
    assert [u["reason"] for u in doc["media"]["unavailable"]] == ["file not found", "image not decodable",
                                                                   "unsupported media type .docx"]
    assert (inbox(root) / "done" / "broken.png").is_file()      # referenced files leave the inbox once handled


@needs_sips
def test_heic_is_converted_with_sips(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src_png = png(tmp_path / "photo.png", size=(300, 200))
    res = subprocess.run(["sips", "-s", "format", "heic", str(src_png), "--out", str(inbox(root) / "photo.heic")],
                         capture_output=True, text=True, check=False)
    if res.returncode != 0:
        pytest.skip("sips cannot write HEIC here")
    rows = [{"author": "Dana Kessler", "platform": "x", "text": "phone photo of the whiteboard", "media": ["photo.heic"]}]
    doc = run_commit(root, run_normalize(root, write_json_source(root, "heic.json", rows))["file"])
    assert doc["ok"] and doc["media"]["copied"] == 1
    meta, _ = read_post(root, "train", "dana-kessler_001")
    m = meta["media"][0]
    assert m["kind"] == "image" and m["path"] == "corpus/media/dana-kessler_001/1.jpg" and (m["width"], m["height"]) == (300, 200)
    assert mp.image_dims(root / m["path"]) == (300, 200)


def test_heic_without_sips_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_root(tmp_path)
    (inbox(root) / "photo.heic").write_bytes(b"\0\0\0\x18ftypheic")
    monkeypatch.setattr(ic._platform, "system", lambda: "Linux")
    rows = [{"author": "Dana Kessler", "platform": "x", "text": "phone photo", "media": ["photo.heic"]}]
    doc = run_commit(root, run_normalize(root, write_json_source(root, "heic.json", rows))["file"])
    meta, _ = read_post(root, "train", "dana-kessler_001")
    assert meta["media"][0]["kind"] == "unavailable" and "sips" in meta["media"][0]["note"]
    assert any("HEIC" in w for w in doc["warnings"])


def test_transcript_is_written_and_linked(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    png(inbox(root) / "still.png")
    rows = [{"author": "Dana Kessler", "platform": "x", "text": "me, on camera, about the close date",
             "media": ["still.png"], "transcript": "forecast accuracy went to ninety four percent"},
            {"author": "Dana Kessler", "platform": "x", "text": "no media but a transcript", "transcript": "hello"}]
    doc = run_commit(root, run_normalize(root, write_json_source(root, "t.json", rows))["file"])
    meta, _ = read_post(root, "train", "dana-kessler_001")
    assert meta["media"][0]["transcript"] == "corpus/media/dana-kessler_001/transcript.txt"
    assert (root / meta["media"][0]["transcript"]).read_text(encoding="utf-8") == "forecast accuracy went to ninety four percent\n"
    assert any("transcript supplied but the row has no media" in w for w in doc["warnings"])


def test_commit_flags_non_english_posts(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    doc = run_commit(root, run_normalize(root, stage(root, "posts.json"))["file"])
    assert doc["non_english"] == ["paul-graham_002"]
    meta, _ = read_post(root, "train", "paul-graham_002")
    assert meta["lang"] == "other"


# --------------------------------------------------------------------------- media_prepare

def _ingest_with_media(root: Path, media: list[str], text: str = "receipts attached", platform: str = "x") -> str:
    rows = [{"author": "Dana Kessler", "platform": platform, "text": text, "media": media}]
    doc = run_commit(root, run_normalize(root, write_json_source(root, "media.json", rows))["file"])
    assert doc["ok"], doc
    return doc["ingested"][0]


def test_prepare_image_preview_downscales_and_is_idempotent(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    png(inbox(root) / "wide.png", size=(2000, 1000))
    png(inbox(root) / "small.png", size=(300, 200), color=(0, 120, 0))
    pid = _ingest_with_media(root, ["wide.png", "small.png"])
    before_body = read_post(root, "train", pid)[1]
    doc = run_prepare(root, post=pid)
    assert doc["ok"] and doc["prepared"] == 2 and doc["tools"]["ffmpeg"] == HAVE_FFMPEG
    res = doc["posts"][pid]["media"]
    assert [r["status"] for r in res] == ["prepared", "prepared"]
    meta, body = read_post(root, "train", pid)
    assert body == before_body
    m1, m2 = meta["media"]
    assert m1["preview"] == f"corpus/media/{pid}/preview_1.jpg" and m2["preview"] == f"corpus/media/{pid}/preview_2.jpg"
    assert mp.image_dims(root / m1["preview"]) == (1568, 784) and (m1["width"], m1["height"]) == (2000, 1000)
    assert mp.image_dims(root / m2["preview"]) == (300, 200)
    assert list(m1.keys()) == MEDIA_KEYS
    again = run_prepare(root, post=pid)
    assert again["prepared"] == 0 and again["unchanged"] == 2 and again["posts"][pid]["changed"] is False
    forced = run_prepare(root, post=pid, force=True)
    assert forced["prepared"] == 2
    assert run_prepare(root, all_=True)["unchanged"] == 2


@needs_ffmpeg
def test_prepare_video_frames_contact_sheet_and_audio_only_when_present(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    video(inbox(root) / "silent.mp4", audio=False)
    video(inbox(root) / "talky.mp4", audio=True)
    rows = [{"author": "Dana Kessler", "platform": "linkedin", "text": long_post(1, "kessler"), "media": ["silent.mp4"]},
            {"author": "Dana Kessler", "platform": "x", "text": "talking to camera", "media": [{"path_or_url": "talky.mp4",
             "description": "me talking"}], "transcript": "ninety four percent"}]
    doc = run_commit(root, run_normalize(root, write_json_source(root, "v.json", rows))["file"])
    assert doc["ok"] and doc["media"]["copied"] == 2
    meta_c, _ = read_post(root, "train", "dana-kessler_002")
    assert meta_c["media"][0]["kind"] == "video" and meta_c["media"][0]["duration_s"] == pytest.approx(2.0, abs=0.2)
    assert (meta_c["media"][0]["width"], meta_c["media"][0]["height"]) == (320, 240)

    doc = run_prepare(root, all_=True)
    assert doc["ok"] and doc["prepared"] == 2, doc
    r1 = doc["posts"]["dana-kessler_001"]["media"][0]
    r2 = doc["posts"]["dana-kessler_002"]["media"][0]
    assert r1["frames"] == 5 and r1["audio"] is False and r1["frames_dir"] == "corpus/frames/dana-kessler_001"
    assert r2["frames"] == 5 and r2["audio"] is True and r2["transcript"] == "corpus/media/dana-kessler_002/transcript.txt"
    f1 = root / "corpus" / "frames" / "dana-kessler_001"
    f2 = root / "corpus" / "frames" / "dana-kessler_002"
    assert sorted(p.name for p in f1.iterdir()) == ["contact.jpg", "frames.json", "kf_00.jpg", "kf_100.jpg", "kf_25.jpg",
                                                     "kf_50.jpg", "kf_75.jpg"]
    assert (f2 / "audio.wav").is_file() and (f2 / "audio.wav").stat().st_size > 16000 * 2  # > 1 s of 16 kHz mono
    assert not (f1 / "audio.wav").exists()
    frames = common.read_json(f2 / "frames.json")
    assert [f["t_s"] for f in frames["frames"]] == [0.0, 0.5, 1.0, 1.5, 1.9] and frames["has_audio"] is True
    assert mp.image_dims(f2 / "kf_50.jpg") == (640, 480)
    assert mp.image_dims(f2 / "contact.jpg") is not None
    meta, _ = read_post(root, "train", "dana-kessler_002")
    m = meta["media"][0]
    assert m["frames_dir"] == "corpus/frames/dana-kessler_002" and m["preview"] == "corpus/media/dana-kessler_002/preview_1.jpg"
    assert (root / m["preview"]).read_bytes() == (f2 / "contact.jpg").read_bytes()
    assert m["duration_s"] == pytest.approx(2.0, abs=0.2) and m["provided_description"] == "me talking"
    again = run_prepare(root, all_=True)
    assert again["prepared"] == 0 and again["unchanged"] == 2


@needs_ffmpeg
def test_prepare_scene_change_frames(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    scene_video(inbox(root) / "scenes.mp4")
    pid = _ingest_with_media(root, ["scenes.mp4"], text="three colours")
    doc = run_prepare(root, post=pid)
    r = doc["posts"][pid]["media"][0]
    assert r["status"] == "prepared" and r["frames"] == 7           # 5 keyframes + 2 scene changes
    frames = common.read_json(root / "corpus" / "frames" / pid / "frames.json")["frames"]
    scenes = [f for f in frames if f["source"] == "scene"]
    assert [f["file"] for f in scenes] == ["scene_01.jpg", "scene_02.jpg"]
    assert [f["t_s"] for f in scenes] == pytest.approx([1.0, 2.0], abs=0.15)
    assert (root / "corpus" / "frames" / pid / "contact.jpg").is_file()


@needs_ffmpeg
def test_prepare_two_videos_get_two_frames_dirs(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    video(inbox(root) / "a.mp4")
    video(inbox(root) / "b.mp4")
    pid = _ingest_with_media(root, ["a.mp4", "b.mp4"], text="two clips")
    doc = run_prepare(root, post=pid)
    dirs = [r["frames_dir"] for r in doc["posts"][pid]["media"]]
    assert dirs == [f"corpus/frames/{pid}", f"corpus/frames/{pid}_2"]
    assert all((root / d / "contact.jpg").is_file() for d in dirs)


@needs_pdftoppm
def test_prepare_pdf_pages(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    pdf(inbox(root) / "deck.pdf")
    pid = _ingest_with_media(root, ["deck.pdf"], text=long_post(3, "kessler"), platform="linkedin")
    meta, _ = read_post(root, "train", pid)
    assert meta["media"][0]["kind"] == "carousel" and meta["media"][0]["pages"] == 1
    doc = run_prepare(root, post=pid)
    r = doc["posts"][pid]["media"][0]
    assert r["status"] == "prepared" and r["frames"] == 1 and r["frames_dir"] == f"corpus/frames/{pid}"
    fdir = root / "corpus" / "frames" / pid
    assert (fdir / "page-1.png").is_file() and (fdir / "frames.json").is_file()
    meta, _ = read_post(root, "train", pid)
    m = meta["media"][0]
    assert m["preview"] == f"corpus/media/{pid}/preview_1.jpg" and mp.image_dims(root / m["preview"]) is not None
    assert m["frames_dir"] == f"corpus/frames/{pid}" and m["kind"] == "carousel"
    if HAVE_FFMPEG:
        assert (fdir / "contact.jpg").is_file()
    assert run_prepare(root, post=pid)["unchanged"] == 1


def test_prepare_skips_unavailable_and_marks_missing_files(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    png(inbox(root) / "gone_later.png")
    rows = [{"author": "Dana Kessler", "platform": "x", "text": "two media", "media": ["gone_later.png", "https://www.linkedin.com/posts/a"]},
            {"author": "Dana Kessler", "platform": "x", "text": "no media at all"}]
    doc = run_commit(root, run_normalize(root, write_json_source(root, "m.json", rows))["file"])
    pid = doc["ingested"][0]
    (root / "corpus" / "media" / pid / "1.png").unlink()
    res = run_prepare(root, all_=True)
    r = res["posts"][pid]["media"]
    assert r[0]["status"] == "unavailable" and "missing" in r[0]["error"]
    assert r[1]["status"] == "skipped" and r[1]["error"] == "unavailable at ingest"
    assert res["posts"]["dana-kessler_002"]["media"] == [] and res["unavailable"] == 1 and res["skipped"] == 1
    meta, _ = read_post(root, "train", pid)
    assert meta["media"][0]["kind"] == "unavailable" and meta["media"][0]["note"] == "media file missing"
    assert run_prepare(root)["ok"] is False and run_prepare(root, post="nobody_001")["ok"] is False


def test_prepare_video_without_ffmpeg_is_skipped_not_broken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_root(tmp_path)
    (inbox(root) / "clip.mp4").write_bytes(b"\0" * 64)
    monkeypatch.setattr(mp.shutil, "which", lambda name: None)
    pid = _ingest_with_media(root, ["clip.mp4"], text="a clip")
    meta, _ = read_post(root, "train", pid)
    assert meta["media"][0]["kind"] == "video" and meta["media"][0]["width"] is None
    doc = run_prepare(root, post=pid)
    r = doc["posts"][pid]["media"][0]
    assert r["status"] == "skipped" and "ffmpeg" in r["error"] and doc["tools"] == {"ffmpeg": False, "ffprobe": False, "pdftoppm": False}
    assert read_post(root, "train", pid)[0]["media"][0]["kind"] == "video"


# --------------------------------------------------------------------------- CLIs

def run_cli(tool: str, *args: str, env: dict | None = None) -> tuple[int, dict]:
    e = {k: v for k, v in os.environ.items() if k not in ("POSTSMITH_ROOT", "CLAUDE_PROJECT_DIR")}
    if env:
        e.update(env)
    proc = subprocess.run([sys.executable, str(TOOLS / tool), *args], capture_output=True, text=True, cwd=str(PROJECT),
                          env=e, check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


@pytest.mark.parametrize("tool", ["ingest_normalize.py", "ingest_commit.py", "media_prepare.py"])
def test_cli_help(tool: str) -> None:
    proc = subprocess.run([sys.executable, str(TOOLS / tool), "--help"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0 and "--json" in proc.stdout and "--root" in proc.stdout


def test_cli_round_trip_with_root_flag_and_env(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    src = stage(root, "posts_blocks.md")
    png(inbox(root) / "puri_screenshot.png", size=(900, 600))
    _, ndoc = run_cli("ingest_normalize.py", str(src), "--kind", "auto", "--root", str(root), "--json")
    assert ndoc["ok"] and ndoc["rows"] == 3 and (root / ndoc["file"]).is_file()
    _, cdoc = run_cli("ingest_commit.py", ndoc["file"], "--json", env={"POSTSMITH_ROOT": str(root)})
    assert cdoc["ok"] and cdoc["ingested"] == ["shaan-puri_001", "shaan-puri_002", "shaan-puri_003"]
    assert cdoc["small_corpus_mode"] is True and cdoc["media"]["copied"] == 1
    _, pdoc = run_cli("media_prepare.py", "--post", "shaan-puri_002", "--root", str(root), "--json")
    assert pdoc["ok"] and pdoc["prepared"] == 1
    assert (root / "corpus" / "media" / "shaan-puri_002" / "preview_1.jpg").is_file()
    _, adoc = run_cli("media_prepare.py", "--all", "--json", env={"POSTSMITH_ROOT": str(root)})
    assert adoc["unchanged"] == 1
    assert not list((PROJECT / "corpus" / "posts").glob("shaan-puri_*.md"))


def test_cli_user_errors_exit_zero_with_json(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    _, doc = run_cli("ingest_normalize.py", "corpus/inbox/nope.csv", "--root", str(root), "--json")
    assert doc == {"ok": False, "error": "source not found: corpus/inbox/nope.csv"}
    _, doc = run_cli("ingest_normalize.py", "x.csv", "--mapping", "{not json", "--root", str(root))
    assert doc["ok"] is False and "mapping" in doc["error"]
    _, doc = run_cli("ingest_commit.py", "corpus/inbox/normalized_none.jsonl", "--root", str(root), "--json")
    assert doc["ok"] is False and "not found" in doc["error"]
    _, doc = run_cli("media_prepare.py", "--root", str(root), "--json")
    assert doc["ok"] is False and "--post" in doc["error"]
    _, doc = run_cli("media_prepare.py", "--post", "x_001", "--root", str(tmp_path / "missing"), "--json")
    assert doc["ok"] is False and "root" in doc["error"]
