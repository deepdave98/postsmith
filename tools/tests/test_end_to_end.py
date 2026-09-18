"""End-to-end dry run of the whole tool chain on a scratch project root.

The scratch root copies config/, evals/, .claude/, tools/ and the style/ scaffold, plus an empty corpus/,
memory/ and drafts/. Every tool runs as a subprocess from that root (`<root>/tools/<name>.py ... --json`,
cwd = root, POSTSMITH_ROOT = root), exactly as `uv run tools/<name>.py` runs in a real session. A final test
asserts the repository's own corpus/, style/, memory/ and drafts/ are untouched.

The run walks the /ingest, /post, /rate, /posted and /eval flows in order, with the agents replaced by scripted
stand-ins that answer every `run_next` action in the shape the validators accept: verbatim evidence quotes,
`na` with a `pre_step`, jury files, nonces in lineup picks and pairwise verdicts, a media brief and a
media-judge document. Tests are ordered. Each one performs the next step and records what it produced in the
module-level `S` dict; a test whose prerequisite step failed skips instead of failing again.

The video attachment and its frames are skipped when ffmpeg or ffprobe are missing.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import common  # noqa: E402

PROJECT = TOOLS.parent
FIX = Path(__file__).resolve().parent / "fixtures"
CORPUS_FIX = FIX / "corpus"
CARDS_FIX = FIX / "cards"
REPORT_FIX = FIX / "report" / "2026-09-17_agents-buying-domains"
DATE = "2026-09-17"
LEARN_DIR = f"drafts/learn_{DATE}"
TOPIC = "agents buying domains to be safe"
SLUG = "agents-buying-domains"
LENSES = ["reader", "voice", "comedy", "persona"]
LENS_DIMS = {
    "reader": ["clarity", "substance", "hook", "regret_risk", "reply_worthiness"],
    "voice": ["register_match_self", "level_and_move", "not_ai", "platform_register"],
    "comedy": ["humor", "uniqueness", "emotion"],
    "persona": ["persona_fit", "claims"],
}
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
FIXTURE_ID_RE = re.compile(r"\b((?:kessler|okonkwo|vieira)_\d{3})\b")
VERDICT_WORDS = ("PASSED", "DID NOT PASS", "needs your call", "passed Tier 0-1")

# state shared by the ordered tests (a failed step leaves its key missing; later tests skip)
S: dict = {}

# --------------------------------------------------------------------------- texts (all original; none shares a 6-gram with the fixture corpus)

SELF_POSTS = [
    ("linkedin", "I read every invoice our company paid last month. 212 of them.\n\nThe most expensive line item was a "
                 "tool nobody could name in the all-hands, so I asked the room and got four different answers and one "
                 "very quiet Slack thread.\n\nWe still pay for it. The thread is now the documentation."),
    ("linkedin", "Our data team has a rule: no dashboard ships without the number that would embarrass us.\n\nLast "
                 "quarter that number was the 41% of enrichment jobs that returned the same address for two different "
                 "companies. It is on the front page now.\n\nThe jobs are at 9%. The front page has not changed."),
    ("x", "hiring rule at floqer: the take-home is the bug we shipped last week. if you find it in under an hour we "
          "talk. if you find two we talk faster."),
    ("x", "our enrichment pipeline has a status page. the status page has a status page. neither of them was up on "
          "tuesday."),
    ("linkedin", "Three years in, I finally deleted the pitch deck from 2023.\n\nIt had 14 slides about the market and "
                 "one about the product. The product slide was a screenshot of a spreadsheet.\n\nThe spreadsheet is "
                 "still what customers pay for."),
]

CLEAN_LI_1 = (REPORT_FIX / "round1" / "candidates" / "r1-w1-li.txt").read_text(encoding="utf-8").rstrip("\n")
CLEAN_X_1 = (REPORT_FIX / "round1" / "candidates" / "r1-w1-x.txt").read_text(encoding="utf-8").rstrip("\n")
CLEAN_LI_2 = (REPORT_FIX / "round1" / "candidates" / "r1-w2-li.txt").read_text(encoding="utf-8").rstrip("\n")
BROKEN_LI = ("We gave our agent a budget of $50 for the launch and it spent $4,812 on domains, which it described in "
             "its log as a rounding error.\n\nThe finance team has questions. The agent has answers, all of them "
             "beginning with the phrase 'to be safe'.\n\n#AI #agents #startups #founders\n\nAgree? Comment below and share this "
             "with your network!")
BROKEN_X = ((REPORT_FIX / "round1" / "candidates" / "r1-w2-x.txt").read_text(encoding="utf-8").rstrip("\n")
            + " #ai #agents #buildinpublic")

CLAIMS_LI = [{"text": "the agent registered 400 domains", "source": "brief.user_detail"},
             {"text": "the invoice came to $4,812", "source": "brief.user_detail"},
             {"text": "the Estonian word for launch was available and cheap", "source": "joke"}]
CLAIMS_X = [{"text": "the agent registered 400 domains", "source": "brief.user_detail"}]

# what each scripted judge says (score, or "na:<reason>"); the clean LI finalist scores hook 3 (a jury) and leaves
# one claim needs_check (a Tier 2 claim verification); the alternate scores lower reply_worthiness so it ranks second
PLAN = {
    "r1-w1-li": {"reader": {"clarity": 5, "substance": 5, "hook": 3, "regret_risk": 5, "reply_worthiness": 5},
                 "voice": {"register_match_self": 4, "level_and_move": "na:lens-free writer (lens: none)", "not_ai": 5,
                           "platform_register": 5},
                 "comedy": {"humor": 4, "uniqueness": 4, "emotion": 4},
                 "persona": {"persona_fit": 5, "claims": [
                     {"text": "the agent registered 400 domains", "status": "user_provided", "source": "brief.user_detail"},
                     {"text": "the invoice came to $4,812", "status": "needs_check", "source": "brief.user_detail"},
                     {"text": "the Estonian word for launch was available and cheap", "status": "joke", "source": "joke"}]}},
    "r2-w2-li": {"reader": {"clarity": 4, "substance": 4, "hook": 4, "regret_risk": 5, "reply_worthiness": 4},
                 "voice": {"register_match_self": 4, "level_and_move": 4, "not_ai": 4, "platform_register": 4},
                 "comedy": {"humor": 4, "uniqueness": 4, "emotion": 4},
                 "persona": {"persona_fit": 4, "claims": [
                     {"text": "the agent registered 400 domains", "status": "user_provided", "source": "brief.user_detail"}]}},
    "r1-w1-x": {"reader": {"clarity": 5, "substance": 4, "hook": 5, "regret_risk": 5, "reply_worthiness": 4},
                "voice": {"register_match_self": 4, "level_and_move": "na:lens-free writer (lens: none)", "not_ai": 5,
                          "platform_register": 5},
                "comedy": {"humor": 5, "uniqueness": 4, "emotion": 4},
                "persona": {"persona_fit": 5, "claims": [
                    {"text": "the agent registered 400 domains", "status": "user_provided", "source": "brief.user_detail"}]}},
}


# --------------------------------------------------------------------------- scratch root

class Root:
    """A scratch project root; runs the copied tools as subprocesses the way a session runs `uv run tools/<name>.py`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.commands: list[str] = []          # every tool command run_next emitted (for the hook simulation)
        self.agent_actions: list[dict] = []     # every agent action run_next emitted
        self.log: list[dict] = []

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "POSTSMITH_HOOK_LOG")}
        env["POSTSMITH_ROOT"] = str(self.path)
        return env

    def tool(self, name: str, *args: str, ok: bool = True, stdout_to: Path | None = None) -> dict:
        argv = [sys.executable, str(self.path / "tools" / name), *[str(a) for a in args]]
        if "--json" not in argv and "--brief" not in argv:
            argv.append("--json")
        res = subprocess.run(argv, capture_output=True, text=True, cwd=str(self.path), env=self.env(), check=False)
        assert res.returncode == 0, f"{name} {' '.join(map(str, args))}\nrc={res.returncode}\n{res.stderr}\n{res.stdout[:2000]}"
        if stdout_to is not None:
            stdout_to.parent.mkdir(parents=True, exist_ok=True)
            stdout_to.write_text(res.stdout, encoding="utf-8")
        try:
            doc = json.loads(res.stdout)
        except json.JSONDecodeError:
            doc = {"stdout": res.stdout}
        self.log.append({"tool": name, "args": list(map(str, args)), "ok": doc.get("ok") if isinstance(doc, dict) else None})
        if ok and isinstance(doc, dict):
            assert doc.get("ok", True) is not False, f"{name} {' '.join(map(str, args))} -> {json.dumps(doc)[:1500]}"
        return doc

    def run_command(self, command: str) -> dict:
        """Run a `uv run tools/<tool> args [> file]` command as the orchestrator would."""
        self.commands.append(command)
        toks = shlex.split(command)
        assert toks[:2] == ["uv", "run"] and toks[2].startswith("tools/"), command
        redirect = None
        if ">" in toks:
            i = toks.index(">")
            redirect = self.path / toks[i + 1]
            toks = toks[:i]
        return self.tool(toks[2][len("tools/"):], *toks[3:], stdout_to=redirect)

    def read(self, rel: str) -> str:
        return (self.path / rel).read_text(encoding="utf-8")

    def json(self, rel: str):
        return json.loads(self.read(rel))

    def write(self, rel: str, text: str) -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def write_json(self, rel: str, doc) -> Path:
        return self.write(rel, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def _copytree(src: Path, dst: Path, ignore=None) -> None:
    shutil.copytree(src, dst, symlinks=True, ignore=ignore)


@pytest.fixture(scope="module")
def root(tmp_path_factory) -> Root:
    dst = tmp_path_factory.mktemp("e2e") / "postsmith"
    dst.mkdir()
    _copytree(PROJECT / "config", dst / "config")
    _copytree(PROJECT / "evals", dst / "evals")
    # Only the style/ scaffold is copied. The learned layer (profile.json and its history, the author
    # profiles, moves, common, exemplars, media_habits, self) is what this run builds from nothing.
    # Inheriting the project's copies would start the run already learned: the profile would resume at
    # the project's version instead of 1 and the "built from zero" assertions would measure real data.
    (dst / "style").mkdir(parents=True, exist_ok=True)
    _copytree(PROJECT / "style" / "taxonomies", dst / "style" / "taxonomies")
    shutil.copy2(PROJECT / "style" / "lexicon.yaml", dst / "style" / "lexicon.yaml")
    _copytree(PROJECT / ".claude", dst / ".claude")
    _copytree(PROJECT / "tools", dst / "tools", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (dst / "evals" / "health" / "reports").mkdir(parents=True, exist_ok=True)
    for d in ("corpus/inbox/media", "corpus/posts", "corpus/heldout/cards", "corpus/self", "corpus/cards/_reviews",
              "corpus/features", "corpus/media", "corpus/frames", "memory/published", "drafts"):
        (dst / d).mkdir(parents=True, exist_ok=True)
    (dst / "pyproject.toml").write_text('[project]\nname = "postsmith-e2e"\nversion = "0"\n', encoding="utf-8")
    (dst / "CLAUDE.md").write_text((PROJECT / "CLAUDE.md").read_text(encoding="utf-8"), encoding="utf-8")
    (dst / "README.md").write_text("# postsmith (scratch)\n\n## Ops notes\n\n**LinkedIn**\n- Zero hashtags.\n\n**X**\n"
                                   "- No link in the body; it goes to reply_1.\n", encoding="utf-8")
    S["root"] = dst
    return Root(dst)


def need(*keys: str) -> None:
    for k in keys:
        if k not in S:
            pytest.skip(f"earlier step did not complete ({k} missing)")


# --------------------------------------------------------------------------- 1. ingest

def _fixture_posts() -> list[tuple[dict, str]]:
    out = []
    for d in (CORPUS_FIX / "posts", CORPUS_FIX / "heldout"):
        for p in sorted(d.glob("*.md")):
            meta, body = common.split_front_matter(p.read_text(encoding="utf-8"))
            out.append((meta, body.rstrip("\n")))
    return out


def _make_media(root: Root) -> dict[str, str]:
    """Generate one PNG (pillow) and, with ffmpeg, one silent MP4 under corpus/inbox/media; returns {post_id: filename}."""
    from PIL import Image, ImageDraw
    media_dir = root.path / "corpus" / "inbox" / "media"
    img = Image.new("RGB", (640, 480), (245, 245, 240))
    draw = ImageDraw.Draw(img)
    draw.line([(40, 60), (600, 420)], fill=(200, 30, 30), width=6)
    draw.line([(40, 420), (600, 60)], fill=(30, 60, 200), width=6)
    img.save(media_dir / "vieira_chart.png")
    files = {"vieira_004": "vieira_chart.png"}
    if HAVE_FFMPEG:
        res = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=navy:s=320x240:d=2",
                              "-pix_fmt", "yuv420p", str(media_dir / "kessler_clip.mp4")], capture_output=True, text=True)
        if res.returncode == 0 and (media_dir / "kessler_clip.mp4").exists():
            files["kessler_002"] = "kessler_clip.mp4"
    return files


def test_01_ingest_csv_and_self(root: Root) -> None:
    media = _make_media(root)
    S["media_files"] = media
    rows = _fixture_posts()
    csv_path = root.path / "corpus" / "inbox" / "references.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Handle", "Network", "Date", "Content", "Likes", "Comments", "Reposts", "Views", "Media",
                    "Media description"])
        for meta, body in rows:
            eng = meta.get("engagement") or {}
            desc = ""
            for m in meta.get("media") or []:
                desc = m.get("provided_description") or desc
            w.writerow([meta["author"]["name"], meta["author"]["handle"], "LinkedIn" if meta["platform"] == "linkedin" else "X",
                        meta.get("posted_at") or "", body, eng.get("likes") or "", eng.get("comments") or "",
                        eng.get("reposts") or "", eng.get("views") or "", media.get(meta["post_id"], ""), desc])
    norm = root.tool("ingest_normalize.py", "corpus/inbox/references.csv", "--kind", "csv")
    assert norm["rows"] == 12 and norm["needs"] == [], norm
    assert norm["file"].startswith("corpus/inbox/normalized_")
    commit = root.tool("ingest_commit.py", norm["file"])
    assert len(commit["ingested"]) == 12 and commit["skipped"] == [] and commit["small_corpus_mode"] is True, commit
    assert commit["heldout_counts"] in ({}, {"linkedin": 0, "x": 0}), commit["heldout_counts"]
    assert not (root.path / "corpus" / "inbox" / "references.csv").exists(), "the source moves to corpus/inbox/done/"
    assert (root.path / "corpus" / "inbox" / "done" / "references.csv").exists()

    # map fixture ids -> ingested ids through the content sha in both manifests
    fixture_by_sha = {json.loads(ln)["content_sha256"]: json.loads(ln)["post_id"]
                      for ln in (CORPUS_FIX / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()}
    idmap: dict[str, str] = {}
    for row in common.read_jsonl(root.path / "corpus" / "manifest.jsonl"):
        fid = fixture_by_sha.get(row["content_sha256"])
        if fid:
            idmap[fid] = row["post_id"]
    assert len(idmap) == 12, idmap
    assert all(re.match(r"^[a-z][a-z0-9-]*_\d{3,}$", v) for v in idmap.values()), idmap
    S["idmap"] = idmap

    # self posts: a markdown file of --- separated blocks, routed to corpus/self
    blocks = []
    for plat, text in SELF_POSTS:
        blocks.append(f"author: Deep\nplatform: {plat}\nposted_at: 2026-08-0{len(blocks) + 1}\n\n{text}\n")
    root.write("corpus/inbox/self_posts.md", "\n---\n".join(blocks))
    norm_self = root.tool("ingest_normalize.py", "corpus/inbox/self_posts.md", "--self")
    assert norm_self["rows"] == 5 and norm_self["needs"] == [], norm_self
    commit_self = root.tool("ingest_commit.py", norm_self["file"], "--self")
    assert len(commit_self["ingested"]) == 5, commit_self
    assert sorted(p.name for p in (root.path / "corpus" / "self").glob("*.md")) == [f"self_00{i}.md" for i in range(1, 6)]
    for pid in commit_self["ingested"]:
        meta, _ = common.split_front_matter(root.read(f"corpus/self/{pid}.md"))
        assert meta["split"] == "self" and meta["author"]["slug"] == "self"
    # re-running the same source is a no-op
    again = root.tool("ingest_normalize.py", "corpus/inbox/done/references.csv", "--kind", "csv")
    again_commit = root.tool("ingest_commit.py", again["file"])
    assert again_commit["ingested"] == [] and len(again_commit["skipped"]) == 12, again_commit
    S["ingested"] = True


def test_02_media_prepare(root: Root) -> None:
    need("ingested")
    idmap, media = S["idmap"], S["media_files"]
    doc = root.tool("media_prepare.py", "--all")
    by_post = doc["posts"]
    assert doc["prepared"] >= 1 and doc["unavailable"] == 0, doc
    S["media_prepare"] = doc
    img_post = idmap["vieira_004"]
    meta, _ = common.split_front_matter(root.read(f"corpus/posts/{img_post}.md"))
    entry = meta["media"][0]
    assert entry["kind"] == "image" and entry["path"].startswith(f"corpus/media/{img_post}/"), entry
    assert entry.get("preview") and (root.path / entry["preview"]).exists(), entry
    assert entry["width"] == 640 and entry["height"] == 480
    if "kessler_002" in media:
        vid_post = idmap["kessler_002"]
        meta, _ = common.split_front_matter(root.read(f"corpus/posts/{vid_post}.md"))
        entry = meta["media"][0]
        assert entry["kind"] == "video" and entry.get("frames_dir"), entry
        frames = root.path / entry["frames_dir"]
        assert frames.is_dir() and list(frames.glob("kf_*.jpg")), sorted(frames.iterdir())
        assert entry.get("preview") and (root.path / entry["preview"]).exists()
        assert not (frames / "audio.wav").exists(), "a silent clip has no audio stream to extract"
        S["video_post"] = vid_post
    S["media_prepared"] = by_post


# --------------------------------------------------------------------------- 2. learn

def test_03_stylometry_and_profile(root: Root) -> None:
    need("ingested")
    root.tool("stylometry.py", "--corpus")
    feats = sorted(p.stem for p in (root.path / "corpus" / "features").glob("*.json"))
    assert len(feats) == 17, feats  # 12 reference posts + 5 self posts
    assert not list((root.path / "corpus" / "heldout" / "features").glob("*.json"))
    prof = root.tool("profile_stats.py", "--write")
    profile = root.json("style/profile.json")
    assert profile["profile_version"] == 1 and profile["scopes"]["self"]["n"] == 5, prof
    assert profile["scopes"]["corpus"]["n"] >= 12 and profile["scopes"]["platform:linkedin"]["n"] >= 5  # corpus = train + self
    S["profile"] = profile


def test_04_card_prompts_are_self_contained(root: Root) -> None:
    need("profile")
    doc = root.tool("card_prompts.py", "build", "--all-uncarded", "--kind", "annotate", "--date", DATE)
    assert doc["learn_dir"] == LEARN_DIR and len(doc["prompts"]) == 17, doc
    for p in doc["prompts"]:
        text = root.read(p["prompt_file"])
        split = "self" if p["post_id"].startswith("self_") else "posts"
        _, body = common.split_front_matter(root.read(f"corpus/{split}/{p['post_id']}.md"))
        first = next(ln for ln in body.splitlines() if ln.strip())
        assert "<numbered_lines>" in text and "L1: " + first in text, p["prompt_file"]
        assert "<untrusted_post>" in text and first in text.split("<untrusted_post>")[1].split("</untrusted_post>")[0]
        assert "rating" not in text.lower() and "user_score" not in text and "calibration" not in text.lower(), p["prompt_file"]
        assert p["output_path"] == f"corpus/cards/{p['post_id']}.md", p
        assert "corpus/heldout" not in text
    S["annotate_prompts"] = doc["prompts"]


def _media_analysis_video() -> dict:
    return {"literal": "A two-second navy frame with no text, used as a placeholder clip.", "on_media_text": [],
            "genre": "diagram_chart", "role": "proof", "caption_dependency": "media_dependent",
            "style_notes": "flat colour, no motion", "reproducibility": "promptable",
            "what_it_adds": "Nothing beyond the caption; the clip is a stand-in.", "video": {"duration_s": 2, "has_speech": False}}


def test_05_cards_written_by_the_annotator_stand_in_and_linted(root: Root) -> None:
    need("annotate_prompts")
    idmap = S["idmap"]
    written = []
    for src in sorted(list((CORPUS_FIX / "cards").glob("*.md")) + list((CORPUS_FIX / "heldout" / "cards").glob("*.md"))):
        meta, body = common.split_front_matter(src.read_text(encoding="utf-8"))
        fid = meta["post_id"]
        meta["post_id"] = idmap[fid]
        meta["annotated_by"] = "post-annotator"
        meta["verified"] = False
        if fid == "kessler_002" and S.get("video_post"):
            meta["media_analysis"] = _media_analysis_video()
        common.write_front_matter_file(root.path / "corpus" / "cards" / f"{idmap[fid]}.md", meta, body)
        written.append(idmap[fid])
    assert len(written) == 12
    lint = root.tool("card_lint.py", "--all")
    assert lint["problems"] == [] and lint["n_cards"] == 12, lint
    one = root.tool("card_lint.py", "--post", idmap["kessler_001"])
    assert one["ok"] and one["problems"] == []
    # verification prompts carry the card inline; the verifier stand-in accepts every card
    ver = root.tool("card_prompts.py", "build", "--all-uncarded", "--kind", "verify", "--date", DATE)
    assert len(ver["prompts"]) == 12, ver
    for p in ver["prompts"]:
        text = root.read(p["prompt_file"])
        assert "<annotation_card>" in text and "<untrusted_post>" in text and p["round"] == 1
        assert p["output_path"] == f"corpus/cards/_reviews/{p['post_id']}.md"
        common.write_front_matter_file(root.path / p["output_path"],
                                       {"schema": "postsmith.review/1", "post_id": p["post_id"], "verified": True, "round": 1,
                                        "checked_at": "2026-09-17T10:31:00Z", "objections": []}, "")
        cmeta, cbody = common.split_front_matter(root.read(f"corpus/cards/{p['post_id']}.md"))
        cmeta["verified"] = True
        common.write_front_matter_file(root.path / "corpus" / "cards" / f"{p['post_id']}.md", cmeta, cbody)
    assert root.tool("card_prompts.py", "build", "--all-uncarded", "--kind", "verify", "--date", DATE)["prompts"] == []
    arch = root.tool("card_prompts.py", "archive", LEARN_DIR)
    assert arch["moved"] == 29 and not list((root.path / LEARN_DIR / "prompts").glob("*")), arch
    S["cards"] = written


def test_06_style_layer_and_moves_lint(root: Root) -> None:
    need("cards")
    idmap = S["idmap"]
    moves = FIXTURE_ID_RE.sub(lambda m: idmap[m.group(1)], (CARDS_FIX / "moves.md").read_text(encoding="utf-8"))
    root.write("style/moves.md", moves)
    lint = root.tool("moves_lint.py")
    assert lint["problems"] == [] and lint["moves"] == 4, lint
    root.write("style/persona.md", PERSONA)
    root.write("style/self.md", "# self register\n\nShort declaratives, numbers first, lowercase on X.\n")
    root.write("style/common.md", "# common bar\n\nEvery post lands on a specific the author could be asked to prove.\n")
    root.write("style/authors/dana-kessler.md", "# dana-kessler\n\nRevOps operator; receipts and deadpan closers.\n")
    root.write("style/exemplars.md", "# Exemplars (train posts only)\n\n"
               f"- {idmap['kessler_001']}: the receipt carries the post\n"
               f"- {idmap['okonkwo_001']}: flat description of a hyped thing\n"
               f"- {idmap['vieira_002']}: number ending\n"
               f"- {idmap['vieira_001']}: one number story\n")
    leak = root.tool("quote_leak_check.py")
    assert leak["ok"] is True, leak
    S["style"] = True


def test_07_health_deterministic(root: Root) -> None:
    need("style")
    doc = root.tool("health_run.py", "--scope", "deterministic", "--write", "--date", DATE)
    S["health"] = doc
    assert doc["green"] is True, {k: v for k, v in doc["sections"].items() if not v.get("green", True)}
    reports = list((root.path / "evals" / "health" / "reports").glob(f"{DATE}_*_p1.md"))
    assert len(reports) == 1 and "status: green" in reports[0].read_text(encoding="utf-8")
    oracle = root.json("evals/golden/oracle.json")
    assert oracle.get("small_corpus_mode") is True and len(oracle.get("posts") or []) == 12, oracle


# --------------------------------------------------------------------------- 3. the /post run with scripted agents

PERSONA = """---
schema: postsmith.persona/1
name: Deep
handle: "@deep"
brands: [Floqer]
aliases: []
lens_preferences: [dana-kessler]
platform_choices: {hashtags: never, emoji: never, long_posts: false}
can_claim:
  - ran 3 agents in prod for 6 weeks
  - gave an agent a company card in staging
cannot_claim:
  - raised a round
do_not_target:
  - individual employees
updated: 2026-09-17
---
## Who I am
Founder of a data company (Floqer). I run the agents that touch our billing.

## Story bank
- story#2 (2026-08-20): the agent that registered a domain in staging. used_in: none

## Opinions held
- guardrails are budgets with better marketing

## Opinions refused
- AI will replace sales teams

## Vocabulary
use: receipt, invoice, log. never: leverage, journey, game-changer

## Claims I can make
- can_claim#1: ran 3 agents in prod for 6 weeks
- can_claim#2: gave an agent a company card in staging

## Never
- hashtags
"""


def _cand(cid: str, text: str, *, writer: int, round_k: int, lens: str | None, claims: list[dict],
          media: str, exemplars: list[str], rewrite_of: str | None = None) -> str:
    plat = "x" if cid.endswith("-x") else "linkedin"
    meta = {
        "schema": "postsmith.candidate/1", "cid": cid, "platform": plat, "writer": f"post-writer-{writer}", "round": round_k,
        "assignment": {"angle_family": "receipt", "archetype": "announcement_with_twist", "move": "receipt_as_proof",
                       "device": "anti_climax", "lens": lens, "seed": 4171, "short_deadpan": False},
        "angle_sheet": {"candidates": [{"angle": "400 domains to be safe", "family": "receipt",
                                        "scores": {"surprise": 5, "truth": 5, "specificity": 5, "personal_fit": 5,
                                                   "timeliness": 3, "disagreeability": 3}, "killed_by": None}],
                        "pick": "400 domains to be safe", "runner_up": None, "emotion": "LOL",
                        "hook_family": "story_in_medias_res"},
        "hook_type": "deadpan_announcement", "ending": "punchline", "claims": claims,
        "media_intent": {"decision": media, "delete_test": "the caption ends on a setup; the form is the receipt" if media != "none"
                         else "nothing: the line is the joke", "genre": "fake_document" if media != "none" else None,
                         "concept": "the incident report on the fridge" if media != "none" else None},
        "lineage": {"exemplars_seen": exemplars, "lessons_used": [], "rewrite_of": rewrite_of},
    }
    if plat == "x":
        meta["reply_1"] = "the incident report, redacted: https://example.com/incident-0400"
    return "---\n" + common.dump_yaml(meta) + "---\n" + text.rstrip("\n") + "\n"


def _writer_output(root: Root, out_rel: str) -> None:
    """The post-writer stand-in: writes the scripted candidate for the requested output path."""
    idmap = S["idmap"]
    cid = Path(out_rel).stem
    m = re.match(r"^r(\d+)-w(\d+)-(li|x)$", cid)
    assert m, cid
    k, w, suffix = int(m.group(1)), int(m.group(2)), m.group(3)
    li_ex = [idmap["kessler_001"], idmap["okonkwo_001"]]
    x_ex = [idmap["vieira_002"], idmap["vieira_001"]]
    lens = None if w == 1 else "dana-kessler"
    prev = f"r{k - 1}-w{w}-{suffix}" if k > 1 else None
    if suffix == "li":
        if w == 1:
            text, claims, media = CLEAN_LI_1, CLAIMS_LI, "image"
        else:
            text, claims, media = (BROKEN_LI, CLAIMS_LI[:1], "none") if k == 1 else (CLEAN_LI_2, CLAIMS_LI[:1], "none")
        doc = _cand(cid, text, writer=w, round_k=k, lens=lens, claims=claims, media=media, exemplars=li_ex, rewrite_of=prev)
    else:
        text = CLEAN_X_1 if w == 1 else BROKEN_X
        doc = _cand(cid, text, writer=w, round_k=k, lens=lens, claims=CLAIMS_X, media="none", exemplars=x_ex, rewrite_of=prev)
    root.write(out_rel, doc)


def _quote_from_prompt(root: Root, prompt_rel: str) -> str:
    text = root.read(prompt_rel)
    assert "<untrusted_post>" in text, prompt_rel
    inside = text.split("<untrusted_post>", 1)[1].split("</untrusted_post>", 1)[0]
    return next(ln for ln in inside.splitlines() if ln.strip())


def _dim_row(score, quote: str, na_reason: str | None = None) -> dict:
    if na_reason:
        return {"score": None, "na": True, "pre_step": na_reason, "evidence": [], "violations": [], "suggested_fix": None,
                "needs_confirmation": []}
    return {"score": score, "na": False, "pre_step": "checked the whole post first", "evidence": [{"quote": quote, "why": "the span carries it"}],
            "violations": [], "suggested_fix": None, "needs_confirmation": []}


def _judge_output(root: Root, a: dict) -> None:
    """Tier 1 / jury / rerun / claims-verification stand-in for judge-<lens> actions."""
    cid = a["cid"]
    if a.get("verify"):  # claim verification writes a JSON array, not a judge document, and carries no lens

        rows = [{"text": t, "status": "plausible", "source": "brief.user_detail", "url": None,
                 "why": "user-provided figure; 400 domains at roughly $12 each"} for t in a.get("claims") or []]
        root.write_json(a["output_path"], rows)
        return
    lens = a["lens"]
    quote = _quote_from_prompt(root, a["prompt_file"])
    prompt = root.read(a["prompt_file"])
    plan = PLAN.get(cid, {}).get(lens, {})
    doc = {"schema": "postsmith.judge/1", "rubric_version": "v1", "lens": lens, "candidate_sha": None, "dimensions": {}}
    if a.get("jury"):
        dim = a["dimension"]
        assert "jury" in a["prompt_file"] and dim in prompt, a
        doc["jury"] = True
        doc["dimensions"][dim] = _dim_row(4, quote)
        root.write_json(a["output_path"], doc)
        return
    dims = a.get("dimensions") or LENS_DIMS[lens]
    if a.get("rerun_for"):
        doc["rerun_for"] = a["rerun_for"]
    for dim in dims:
        spec = plan.get(dim, 4)
        if dim == "claims":
            claims = spec if isinstance(spec, list) else [{"text": c["text"], "status": "user_provided", "source": c["source"]}
                                                          for c in CLAIMS_X]
            doc["dimensions"][dim] = {"na": False, "pre_step": "classified every claim", "evidence": [], "claims": claims}
        elif isinstance(spec, str) and spec.startswith("na:"):
            if dim == "level_and_move":
                assert "lens: none" in prompt, "level_and_move is na only for the lens-free writer"
            doc["dimensions"][dim] = _dim_row(None, quote, na_reason=spec[3:])
        else:
            doc["dimensions"][dim] = _dim_row(int(spec), quote)
    root.write_json(a["output_path"], doc)


def _lineup_pick(root: Root, a: dict) -> None:
    """judge-lineup stand-in: echoes the nonce from its prompt; the harness (never a judge) reads the key to keep the
    picks off the candidate except for one low-confidence reader pick."""
    prompt = root.read(a["prompt_file"])
    nonce = re.search(r'"nonce":\s*"([0-9a-f]+)"', prompt)
    assert nonce, a["prompt_file"]
    key = root.json(f"drafts/{S['run']}/tier2/lineup_{a['cid']}.key.json")
    lens = a["lens"]
    cand_slot = key["candidate_slot_by_lens"][lens]
    other = next(x for x in sorted(key["slots"]) if x != cand_slot)
    pick, conf = (cand_slot, 3) if lens == "reader" else (other, 2)
    assert nonce.group(1) == key["nonces"][lens]
    root.write_json(a["output_path"], {"nonce": nonce.group(1), "pick": pick, "confidence": conf,
                                       "tell": "the paragraphs are the same length", "quote": "x"})


def _pairwise_verdict(root: Root, a: dict) -> None:
    prompt = root.read(a["prompt_file"])
    nonce = re.search(r'"nonce":\s*"([0-9a-f]+)"', prompt)
    assert nonce, a["prompt_file"]
    root.write_json(a["output_path"], {"nonce": nonce.group(1), "same_skeleton_or_joke": False, "same_post_rewritten": False,
                                       "evidence": ""})


def _media_director(root: Root, a: dict) -> None:
    brief = yaml.safe_load((REPORT_FIX / "media" / "r1-w1-li.brief.yaml").read_text(encoding="utf-8"))
    brief["post_id"] = a["cid"]
    root.write(a["output_path"], common.dump_yaml(brief))
    for p in (REPORT_FIX / "media" / "r1-w1-li.prompts").glob("*.md"):
        root.write(f"{a['prompts_dir']}/{p.name}", p.read_text(encoding="utf-8"))


def _media_judge(root: Root, a: dict) -> None:
    doc = json.loads((REPORT_FIX / "media" / "r1-w1-li.media-judge.json").read_text(encoding="utf-8"))
    doc["candidate_sha"] = None
    root.write_json(a["output_path"], doc)


def perform(root: Root, a: dict) -> None:
    if a["kind"] == "tool":
        root.run_command(a["command"])
        return
    root.agent_actions.append(a)
    agent = a["agent"]
    if agent == "post-writer":
        for out in a.get("output_paths") or [a["output_path"]]:
            _writer_output(root, out)
    elif agent in ("judge-reader", "judge-voice", "judge-comedy", "judge-persona"):
        _judge_output(root, a)
    elif agent == "judge-lineup":
        _lineup_pick(root, a)
    elif agent == "judge-pairwise":
        _pairwise_verdict(root, a)
    elif agent == "media-director":
        _media_director(root, a)
    elif agent == "media-judge":
        _media_judge(root, a)
    else:
        raise AssertionError(f"unexpected agent action {a}")


def test_08_run_init_and_brief(root: Root) -> None:
    need("health")
    doc = root.tool("run_next.py", "init", SLUG, "--topic", TOPIC, "--seed", "4171", "--writers", "2")
    run = doc["run"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}_" + SLUG + "$", run) and doc["run_dir"] == f"drafts/{run}", doc
    assert len(doc["matrix"]) == 2 and doc["matrix"][0].get("lens") in (None, "") and doc["matrix"][1].get("lens") == "dana-kessler", doc["matrix"]
    brief = (REPORT_FIX / "brief.md").read_text(encoding="utf-8").replace("run: 2026-09-17_agents-buying-domains", f"run: {run}")
    root.write(f"drafts/{run}/brief.md", brief)
    S["run"] = run
    first = root.tool("run_next.py", run)
    assert first["stage"] == "write" and [a["agent"] for a in first["actions"]] == ["post-writer", "post-writer"], first
    assert all(a["prompt_file"].startswith(f"drafts/{run}/round1/writers/writer-") for a in first["actions"])
    S["first_batch"] = first


def test_09_drive_the_run_to_done(root: Root) -> None:
    need("run")
    run = S["run"]
    stages: list[str] = []
    for _ in range(60):
        doc = root.tool("run_next.py", run)
        stages.append(doc["stage"])
        S["last_batch"] = doc
        if doc["stage"] in ("done", "stopped"):
            break
        assert doc["actions"], f"stage {doc['stage']} emitted no action: {json.dumps(doc, indent=1)[:3000]}"
        assert not doc["waiting_on"], doc["waiting_on"]
        for a in doc["actions"]:
            perform(root, a)
    S["stages"] = stages
    assert doc["stage"] == "done", (stages, doc.get("notes"))
    # the stages walked, in order (a jury and a Tier 2 pass included)
    for st in ("write", "tier0", "tier1", "aggregate", "jury", "feedback", "tier2", "deliver", "done"):
        assert st in stages, (st, stages)
    assert stages.index("jury") < stages.index("tier2") < stages.index("deliver") < stages.index("done")
    rd = root.path / "drafts" / run
    merged = {p.stem[:-len(".merged")]: json.loads(p.read_text()) for p in rd.glob("round*/scores/*.merged.json")}
    status = {cid: m["verdict"]["status"] for cid, m in merged.items()}
    assert status["r1-w1-li"] == "pass" and status["r1-w1-x"] == "pass" and status["r2-w2-li"] == "pass", status
    assert status["r1-w2-li"] == "fail" and status["r1-w2-x"] == "fail" and status["r2-w2-x"] == "fail" and status["r3-w2-x"] == "fail", status
    assert "P3_hashtags" in merged["r1-w2-li"]["verdict"]["hard_fails"] and "P7_bait" in merged["r1-w2-li"]["verdict"]["hard_fails"]
    assert merged["r1-w1-li"]["tier1"]["hook"]["jury"]["median"] == 4 and merged["r1-w1-li"]["tier1"]["hook"]["result"] == "pass"
    assert merged["r1-w1-li"]["tier1"]["level_and_move"]["result"] == "na" and merged["r1-w1-li"]["verdict"]["na_declared"] == []
    assert merged["r1-w1-li"]["tier2"]["lineup"]["pass"] is True and merged["r1-w1-li"]["tier2"]["paraphrase"]["same_skeleton_or_joke"] is False
    assert merged["r1-w1-li"]["tier2"]["claims"][0]["status"] == "plausible"
    assert merged["r1-w1-li"]["tier2"]["media"]["media_check"] == "pass" and merged["r1-w1-li"]["tier2"]["media"]["media_judge"] == "pass"
    assert merged["r1-w1-x"]["tier2"]["lineup"]["pass"] is True and merged["r1-w1-x"]["tier2"]["media"] is None
    assert (rd / "round1" / "feedback" / "r1-w2-li.md").exists()          # feedback packets stay in the run
    rw = list((rd / "archive" / "round2" / "writers").glob("rewrite-r1-w2-li.*.md"))   # prompts archived, token-named
    assert len(rw) == 1, rw
    rewrite = rw[0].read_text(encoding="utf-8")
    assert "<feedback_packet>" in rewrite and "<previous_candidate>" in rewrite and "#AI #agents" in rewrite
    assert not list(rd.glob("round*/prompts/*.md")) and not list(rd.glob("round*/writers/*.md")), "prompts are archived at deliver"
    S["merged"] = merged
    S["finalists"] = {"linkedin": "r1-w1-li", "x": "r1-w1-x"}


def test_10_deliver_hidden_then_blind_rate_then_reveal(root: Root) -> None:
    need("merged")
    run = S["run"]
    final = root.path / "drafts" / run / "final"
    for name in ("report.md", "clipboard.md", "lineage.json", "blind.json", "r1-w1-li.md", "r1-w1-x.md"):
        assert (final / name).exists(), sorted(p.name for p in final.iterdir())
    report = (final / "report.md").read_text(encoding="utf-8")
    assert "After blind rating" in report and "<details>" in report
    head = report.split("<details>")[0]
    assert not any(w in head for w in VERDICT_WORDS), head[:800]
    blind = root.json(f"drafts/{run}/final/blind.json")
    keys = [it["key"] for it in blind["items"]]
    # finalist + alternate + a did-not-pass. r1-w2-li was superseded by the passing rewrite r2-w2-li, so the
    # did-not-pass slot is the X chain's last attempt. blind.json carries {key, platform, text} only
    # (contracts §18); the cid mapping sits in the sibling key file, because a round-2 cid is by
    # construction a rewrite of a candidate that failed.
    key_doc = root.json(f"drafts/{run}/final/blind.key.json")
    by_key = {it["key"]: it["cid"] for it in key_doc["items"]}
    assert keys == ["A", "B", "C"] and set(by_key.values()) == {"r1-w1-li", "r2-w2-li", "r3-w2-x"}, key_doc
    for it in blind["items"]:
        assert set(it) == {"key", "platform", "text"} and it["text"].strip()
    assert "verdict: withheld" in (final / "r1-w1-li.md").read_text(encoding="utf-8")
    topics = root.read("memory/topics.md")
    assert TOPIC in topics and "| pass |" in topics, topics
    # rate the three blind
    scores = {"r1-w1-li": (5, "great_ending"), "r2-w2-li": (4, "great_hook"), "r3-w2-x": (2, "sounds_ai")}
    for it in blind["items"]:
        cid = by_key[it["key"]]
        score, tag = scores[cid]
        res = root.tool("rate_record.py", "--kind", "generated", "--blind", "--ref", f"{run}:{it['key']}", "--score", str(score),
                        "--tags", tag, "--note", "rated blind in the dry run")
        assert res["row"]["cid"] == cid and res["row"]["blind"] is True and res["row"]["post_ref"] == f"{run}/{cid}", res
    rows = common.read_jsonl(root.path / "evals" / "calibration.jsonl")
    assert len(rows) == 3 and {r["verdict"] for r in rows} == {"pass", "fail"}
    # reveal
    shown = root.tool("assemble_report.py", run)
    assert shown["verdicts_hidden"] is False, shown["header"]
    report = (final / "report.md").read_text(encoding="utf-8")
    assert "PASSED" in report.split("<details>")[0] if "<details>" in report else "PASSED" in report
    fin = (final / "r1-w1-li.md").read_text(encoding="utf-8")
    assert "verdict: pass" in fin and CLEAN_LI_1.splitlines()[0] in fin
    assert "reply_1" in (final / "r1-w1-x.md").read_text(encoding="utf-8")
    S["rated"] = True


def test_11_posted_calibrate_topics_lessons_status(root: Root) -> None:
    need("rated")
    run = S["run"]
    posted = root.tool("posted_record.py", run, "r1-w1-li", "--url", "https://www.linkedin.com/posts/deep_agents-0400")
    assert posted["edited"] is False and posted["published_path"].startswith("memory/published/"), posted
    pub_meta, pub_body = common.split_front_matter(root.read(posted["published_path"]))
    assert pub_meta["cid"] == "r1-w1-li" and pub_body.strip() == CLEAN_LI_1.strip()
    metrics = root.tool("posted_record.py", run, "r1-w1-li", "--metrics", "12k views 40 comments 3 reposts", "--after", "24h")
    perf = common.read_jsonl(root.path / "memory" / "performance.jsonl")
    assert len(perf) == 1 and perf[0]["snapshots"][-1]["views"] == 12000 and perf[0]["snapshots"][-1]["comments"] == 40, (metrics, perf)
    assert root.tool("topics.py", "add", run, "--outcome", "posted")["row"]["outcome"] == "posted"
    cal = root.tool("calibrate.py", "--date", DATE)
    assert cal["kappa"]["status"] == "withheld" and cal["ratings_total"] == 3 and cal["mode"] == "advisory", cal
    assert (root.path / "evals" / "health" / "reports" / f"calibration_{DATE}.md").exists()
    sb = root.tool("topics.py", "scoreboard")
    assert "receipt_as_proof" in root.read("memory/topics.md") and sb["ok"]
    pv = root.tool("topics.py", "proven")
    assert pv["ok"] and "## Proven angles" in root.read("memory/topics.md")
    les = root.tool("lessons.py", "add", "--tag", "sounds_ai", "--instruction", "hashtags and a comment bait closer read as a template",
                    "--evidence", "r1-w2-li:Agree? Comment below", "--run", run, "--count", "3")
    assert les["ok"] and les["entry"]["id"] == "L-001", les
    lessons = root.read("memory/lessons.md")
    assert "## AVOID" in lessons and "L-001" in lessons and "tag sounds_ai x3" in lessons
    con = root.tool("lessons.py", "consolidate")
    assert con["ok"]
    props = root.tool("rate_record.py", "--proposals")
    assert props["ok"]
    brief = root.tool("status.py", "--brief")
    text = brief.get("stdout", "")
    assert "profile p1" in text or "profile 1" in text or "profile" in text, text
    assert "health: green" in text, text
    full = root.tool("status.py")
    assert full["ok"] is not False
    S["done"] = True


# --------------------------------------------------------------------------- 4. hook simulation

HOOK_RE = r"python3 \$\{CLAUDE_PROJECT_DIR\}/\.claude/hooks/(guard_paths|guard_writes)\.py ([^\"]*)\""


def _agent_hook_args(agent: str) -> dict[str, list[str]]:
    text = (PROJECT / ".claude" / "agents" / f"{agent}.md").read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for m in re.finditer(HOOK_RE, text):
        out[m.group(1)] = shlex.split(m.group(2))
    assert "guard_paths" in out and "guard_writes" in out, agent
    return out


def _settings_deny_args() -> list[str]:
    settings = json.loads((PROJECT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "guard_paths.py" in cmd, cmd
    return shlex.split(cmd.split("guard_paths.py", 1)[1])


def _hook(root: Root, hook: str, args: list[str], tool: str, **tool_input) -> subprocess.CompletedProcess:
    ti = dict(tool_input)
    for k in ("file_path", "path"):
        if k in ti and not str(ti[k]).startswith("/"):
            ti[k] = str(root.path / ti[k])
    payload = {"session_id": "e2e", "hook_event_name": "PreToolUse", "cwd": str(root.path), "tool_name": tool, "tool_input": ti}
    env = {k: v for k, v in os.environ.items() if k not in ("POSTSMITH_HOOK_LOG",)}
    env["CLAUDE_PROJECT_DIR"] = str(root.path)
    return subprocess.run([sys.executable, str(root.path / ".claude" / "hooks" / f"{hook}.py"), *args], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(root.path), timeout=30, check=False)


def test_12_orchestrator_commands_pass_the_project_hook(root: Root) -> None:
    need("done")
    deny = _settings_deny_args()
    assert root.commands, "no tool command was recorded"
    settings = json.loads((PROJECT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "Bash(uv run *)" in settings["permissions"]["allow"]
    for cmd in root.commands:
        assert cmd.startswith("uv run tools/"), cmd
        res = _hook(root, "guard_paths", deny, "Bash", command=cmd)
        assert res.returncode == 0, (cmd, res.stderr)
    # the deny list still bites when the orchestrator strays
    res = _hook(root, "guard_paths", deny, "Bash", command=f"cat drafts/{S['run']}/tier2/lineup_r1-w1-li.key.json")
    assert res.returncode == 2 and "*.key.json" in res.stderr


def test_13_agent_hooks_allow_exactly_what_their_actions_need(root: Root) -> None:
    need("done")
    run = S["run"]
    seen = set()
    for a in root.agent_actions:
        agent = a["agent"]
        hooks = _agent_hook_args(agent)
        seen.add(agent)
        if agent == "media-director":
            assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=a["candidate"]).returncode == 0
            assert _hook(root, "guard_writes", hooks["guard_writes"], "Write", file_path=a["output_path"]).returncode == 0
            assert _hook(root, "guard_writes", hooks["guard_writes"], "Write", file_path=f"{a['prompts_dir']}/nano_banana.md").returncode == 0
            continue
        res = _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=a["prompt_file"])
        assert res.returncode == 0, (agent, a["prompt_file"], res.stderr)
        for out in a.get("output_paths") or [a["output_path"]]:
            res = _hook(root, "guard_writes", hooks["guard_writes"], "Write", file_path=out)
            assert res.returncode == 0, (agent, out, res.stderr)
        if agent.startswith("judge-"):
            cid = a.get("cid") or "r1-w1-li"
            for bad in (f"drafts/{run}/round1/candidates/{cid}.txt", f"drafts/{run}/brief.md", f"drafts/{run}/tier2/lineup_{cid}.key.json",
                        "style/persona.md", "corpus/posts"):
                res = _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=bad)
                assert res.returncode == 2, (agent, bad, res.stderr)
            assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path="evals/rubric/current/rubric.md").returncode == 0
        if agent == "post-writer":
            assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=f"drafts/{run}/brief.md").returncode == 0
            assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path="style/moves.md").returncode == 0
            for bad in (f"drafts/{run}/round1/feedback/r1-w2-li.md", f"drafts/{run}/round1/scores/r1-w1-li.merged.json",
                        "corpus/cards", "memory/topics.md"):
                assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=bad).returncode == 2, (agent, bad)
            assert _hook(root, "guard_writes", hooks["guard_writes"], "Write", file_path=f"drafts/{run}/round1/candidates/r1-w1-li.txt").returncode == 2
    assert {"post-writer", "judge-reader", "judge-voice", "judge-comedy", "judge-persona", "judge-lineup", "judge-pairwise",
            "media-director", "media-judge"} <= seen, seen


def test_14_annotator_and_verifier_hooks_match_the_learn_prompt_files(root: Root) -> None:
    need("cards")
    idmap = S["idmap"]
    pid = idmap["kessler_001"]
    ann = _agent_hook_args("post-annotator")
    ver = _agent_hook_args("card-verifier")
    # the archived prompt files are what the agents read at the time (archive/ is outside both allow lists afterwards)
    for agent, hooks, prompt, out in (("post-annotator", ann, f"{LEARN_DIR}/prompts/{pid}.annotate.md", f"corpus/cards/{pid}.md"),
                                      ("card-verifier", ver, f"{LEARN_DIR}/prompts/{pid}.verify.md", f"corpus/cards/_reviews/{pid}.md")):
        assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=prompt).returncode == 0, agent
        assert _hook(root, "guard_writes", hooks["guard_writes"], "Write", file_path=out).returncode == 0, agent
        assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path="style/taxonomies/devices.md").returncode == 0
        assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=f"corpus/media/{idmap['vieira_004']}/1.preview.jpg").returncode == 0
        assert _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=".claude/skills/learn/references/card_spec.md").returncode == 0
        for bad in (f"corpus/posts/{pid}.md", "corpus/ratings.jsonl", f"{LEARN_DIR}/archive/{pid}.annotate.md", "evals/calibration.jsonl"):
            res = _hook(root, "guard_paths", hooks["guard_paths"], "Read", file_path=bad)
            assert res.returncode == 2, (agent, bad, res.stderr)
        assert _hook(root, "guard_paths", hooks["guard_paths"], "Bash", command="uv run tools/card_lint.py --all").returncode == 2, agent
    assert _hook(root, "guard_paths", ann["guard_paths"], "Read", file_path=f"corpus/cards/{pid}.md").returncode == 2
    assert _hook(root, "guard_writes", ver["guard_writes"], "Write", file_path=f"corpus/cards/{pid}.md").returncode == 2
    assert _hook(root, "guard_writes", ann["guard_writes"], "Write", file_path=f"corpus/cards/_reviews/{pid}.md").returncode == 2


# --------------------------------------------------------------------------- 5. hygiene

# Everything this run must leave alone, snapshotted at import so the guard survives a project that has a real
# corpus in it. "Empty" stopped being the invariant once the reference set was ingested. "Unchanged" is
# the one that matters: a temp-root run must not reach into the working project.
GUARDED = ("corpus/posts", "corpus/heldout", "corpus/cards", "corpus/features", "style", "drafts", "memory",
           "evals/calibration.jsonl", "evals/health/reports")


def _repo_state() -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for rel in GUARDED:
        base = PROJECT / rel
        if not base.exists():
            continue
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for q in paths:
            if q.is_file():
                st = q.stat()
                out[str(q.relative_to(PROJECT))] = (st.st_size, int(st.st_mtime))
    return out


REPO_AT_IMPORT = _repo_state()


def test_15_nothing_was_written_into_the_repository() -> None:
    now = _repo_state()
    added = sorted(set(now) - set(REPO_AT_IMPORT))
    removed = sorted(set(REPO_AT_IMPORT) - set(now))
    changed = sorted(k for k in set(now) & set(REPO_AT_IMPORT) if now[k] != REPO_AT_IMPORT[k])
    assert not added, f"the run created files in the working project: {added[:10]}"
    assert not removed, f"the run deleted files from the working project: {removed[:10]}"
    # A concurrent writer in the working project (an agent mid-ingest, an editor saving) trips this too; the guard
    # cannot tell who wrote, only that the snapshot moved.
    assert not changed, f"the run modified files in the working project: {changed[:10]}"
    assert not list((PROJECT / "drafts").glob(f"*{SLUG}*")), "the run's own draft directory landed in the project"
