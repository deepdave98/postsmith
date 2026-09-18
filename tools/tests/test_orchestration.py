"""Tests for run_next.py, matrix.py, draft_id.py, metrics_parse.py and status.py.

Fixtures live under tools/tests/fixtures/orchestration/. `proj/` is a small project root: config, rubric,
style, memory, corpus and three finished runs. `run_parts/` holds the candidate, tier0, judge and merged
documents that RunBuilder below assembles into a live run at any stage.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import common  # noqa: E402
import draft_id  # noqa: E402
import lineup  # noqa: E402
import matrix  # noqa: E402
import metrics_parse  # noqa: E402
import pairwise  # noqa: E402
import run_next  # noqa: E402
import status  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "orchestration"
PARTS = FIX / "run_parts"
LENSES = ["reader", "voice", "comedy", "persona"]
TODAY = dt.date(2026, 9, 17)


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    dst = tmp_path / "proj"
    shutil.copytree(FIX / "proj", dst)
    return dst


def _rj(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _wj(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


class RunBuilder:
    """Assemble drafts/<run>/ from run_parts at any stage."""

    def __init__(self, root: Path, name: str = "2026-09-16_cursor-rules", brief: bool = True) -> None:
        self.root = root
        self.name = name
        self.rd = root / "drafts" / name
        (self.rd / "round1" / "candidates").mkdir(parents=True, exist_ok=True)
        if brief:
            (self.rd / "brief.md").write_text("# brief\n", encoding="utf-8")
        _wj(self.rd / "matrix.json", matrix.build(3, 4171, root=root))

    def rdir(self, k: int) -> Path:
        return self.rd / f"round{k}"

    def cand(self, cid: str, k: int = 1, txt: bool = True) -> "RunBuilder":
        d = self.rdir(k) / "candidates"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(PARTS / "candidates" / f"{cid}.md", d / f"{cid}.md")
        if txt and (PARTS / "candidates" / f"{cid}.txt").exists():
            shutil.copy(PARTS / "candidates" / f"{cid}.txt", d / f"{cid}.txt")
        return self

    def tier0(self, cid: str, k: int = 1, hardfail: bool = False) -> "RunBuilder":
        src = PARTS / "tier0" / (f"{cid}.hardfail.tier0.json" if hardfail else f"{cid}.tier0.json")
        if not src.exists():
            src = PARTS / "tier0" / "r1-w2-li.tier0.json"
        doc = _rj(src)
        doc.update({"run": self.name, "cid": cid, "round": k})
        _wj(self.rdir(k) / "scores" / f"{cid}.tier0.json", doc)
        return self

    def judges(self, cid: str, k: int = 1, lenses=tuple(LENSES), persona: str = "persona_clean") -> "RunBuilder":
        for lens in lenses:
            src = PARTS / "judges" / (f"{persona}.json" if lens == "persona" else f"{lens}.json")
            shutil.copy(src, self.rdir(k) / "scores" / f"{cid}.{lens}.json")
        return self

    def merged(self, cid: str, variant: str, k: int = 1) -> dict:
        doc = _rj(PARTS / "merged" / f"{variant}.json")
        plat = "x" if cid.endswith("-x") else "linkedin"
        doc.update({"run": self.name, "cid": cid, "round": k, "platform": plat})
        for rj in (doc.get("judge_io") or {}).get("rejected") or []:
            rj["file"] = rj["file"].replace("RUN", self.name).replace("CID", cid)
        _wj(self.rdir(k) / "scores" / f"{cid}.merged.json", doc)
        return doc

    def jury(self, cid: str, lens: str, dim: str, k: int = 1) -> "RunBuilder":
        _wj(self.rdir(k) / "scores" / f"{cid}.jury.{lens}.{dim}.json",
            {"schema": "postsmith.judge/1", "lens": lens, "jury": True, "dimensions": {dim: {"score": 4}}})
        return self

    def feedback(self, cid: str, k: int = 1) -> "RunBuilder":
        p = self.rdir(k) / "feedback" / f"{cid}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text((PARTS / "feedback.md").read_text().replace("CID", cid), encoding="utf-8")
        return self

    def full_round1(self, persona_for: dict | None = None) -> "RunBuilder":
        """Four round-1 candidates with tier0 + four judges each (r1-w2-x tier0 passes here)."""
        persona_for = persona_for or {}
        for cid in ("r1-w1-li", "r1-w1-x", "r1-w2-li", "r1-w2-x"):
            self.cand(cid).tier0(cid).judges(cid, persona=persona_for.get(cid, "persona_clean"))
        return self

    def next(self, **flags) -> dict:
        return run_next.derive(self.root, self.name, flags)


def _by(doc: dict, **match) -> list[dict]:
    return [a for a in doc["actions"] if all(a.get(k) == v for k, v in match.items())]


# =========================================================================== matrix

def test_moves_parser_tolerant_and_aliases(proj: Path) -> None:
    moves = matrix.parse_moves_md((proj / "style" / "moves.md").read_text())
    ids = [m["id"] for m in moves]
    assert ids == ["corporate_register_for_trivial_event", "receipt_as_proof", "deadpan_announcement",
                   "escalating_triple_break", "quote_then_deflate", "one_number_story"]
    by = {m["id"]: m for m in moves}
    assert by["corporate_register_for_trivial_event"]["platforms"] == ["linkedin", "x"]
    assert by["corporate_register_for_trivial_event"]["aliases"] == ["incident_report_framing"]
    assert by["receipt_as_proof"]["platforms"] == ["linkedin", "x"]  # unbracketed list
    assert by["escalating_triple_break"]["platforms"] == ["x"]
    assert by["one_number_story"]["mechanism"].startswith("a dated number")


def test_topics_parser_runs_and_scoreboard(proj: Path) -> None:
    runs, board = matrix.parse_topics_md((proj / "memory" / "topics.md").read_text())
    assert [r["date"] for r in runs] == ["2026-09-10", "2026-09-08", "2026-09-05", "2026-08-20"]
    assert runs[1]["moves"] == ["receipt_as_proof", "one_number_story"]
    assert runs[0]["lens"] == "null"
    assert board["corporate_register_for_trivial_event"] == {"mean": 4.3, "n": 4, "last_used": "2026-09-05"}
    assert board["quote_then_deflate"]["n"] == 3


def test_taxonomy_parsers(proj: Path) -> None:
    inputs = matrix.load_inputs(proj)
    tax = inputs["taxonomies"]
    assert tax["angles"] == ["reveal", "receipt", "reframe", "ridicule", "rule"]  # families, deduped, no axes
    assert tax["archetypes"] == ["contrarian_take", "announcement_with_twist", "one_liner", "escalation_ladder"]
    assert "punchline" not in tax["archetypes"]  # the ending-habits table is skipped
    assert tax["devices"][:4] == ["deadpan", "anti_climax", "specificity", "incongruous_register"]
    assert "fragment" in tax["devices"]  # second table merged
    assert inputs["lenses"] == ["justin-welsh", "lara-acosta"]
    assert inputs["persona"]["lens_preferences"] == ["lara-acosta", "justin-welsh"]


def test_taxonomy_fallbacks_when_files_missing(tmp_path: Path) -> None:
    inputs = matrix.load_inputs(tmp_path)
    assert inputs["taxonomies"]["angles"] == matrix.FALLBACK_ANGLES
    assert inputs["taxonomies"]["archetypes"] == matrix.FALLBACK_ARCHETYPES
    assert inputs["moves"] == [] and inputs["lenses"] == [] and inputs["recent_runs"] == []


def test_matrix_deterministic_by_seed(proj: Path) -> None:
    a = matrix.build(3, 4171, root=proj)["assignments"]
    b = matrix.build(3, 4171, root=proj)["assignments"]
    assert a == b
    c = matrix.build(3, 99, root=proj)["assignments"]
    assert c != a


def test_matrix_rules(proj: Path) -> None:
    doc = matrix.build(3, 4171, root=proj)
    asg = doc["assignments"]
    assert [a["writer"] for a in asg] == [1, 2, 3]
    assert asg[0]["lens"] is None  # writer 1 lens-free
    assert asg[1]["lens"] == "lara-acosta" and asg[2]["lens"] == "justin-welsh"  # persona lens preference order
    assert sum(a["short_deadpan"] for a in asg) == 1
    deadpan = next(a for a in asg if a["short_deadpan"])
    assert deadpan["device"] == "deadpan"
    tuples = {(a["angle_family"], a["archetype"], a["move"], a["device"], a["lens"]) for a in asg}
    assert len(tuples) == 3
    assert len({a["device"] for a in asg}) == 3 and len({a["archetype"] for a in asg}) == 3
    assert doc["excluded"]["low_score"] == ["quote_then_deflate"]
    assert set(doc["excluded"]["recent"]) == {"corporate_register_for_trivial_event", "deadpan_announcement",
                                              "one_number_story", "receipt_as_proof"}
    assert "quote_then_deflate" not in {a["move"] for a in asg}
    rung0 = [a for a in asg if a["rung"] == 0]
    assert rung0 and all(a["move"] == "escalating_triple_break" for a in rung0)  # the only move free of the last 3 runs
    for a in asg:
        assert a["seed"] == 4171 and a["name"] == f"post-writer-{a['writer']}"
    assert all(k in a for a in asg for k in ("angle_family", "archetype", "move", "device", "lens", "seed", "short_deadpan", "rung"))


def test_matrix_fallback_ladder(proj: Path) -> None:
    asg = matrix.build(7, 4171, root=proj)["assignments"]
    rungs = [a["rung"] for a in asg]
    assert rungs[0] == 0  # eligible under full rules
    assert rungs[1:4] == [1, 1, 1]  # recency relaxed to the last run only
    assert rungs[4] == 2  # last-run move allowed
    assert rungs[5:] == [2, 2] and all(a["move"] for a in asg[5:])  # repeats inside the matrix, different devices
    for mv in {a["move"] for a in asg[5:]}:
        repeated = [a for a in asg if a["move"] == mv]
        assert len(repeated) == 2 and len({a["device"] for a in repeated}) == 2
    # a tiny pool: two moves feed four slots (rung 0, then one repeat each at rung 2), then persona-only at rung 3
    tax = matrix.load_inputs(proj)["taxonomies"]
    tiny = [{"id": "m1", "platforms": [], "aliases": []}, {"id": "m2", "platforms": [], "aliases": []}]
    asg2 = matrix.assign(6, 5, tiny, {}, [], ["lara-acosta"], {}, tax)
    assert sorted(a["rung"] for a in asg2) == [0, 0, 2, 2, 3, 3]
    assert [a["move"] for a in asg2 if a["rung"] == 3] == [None, None]
    assert all(a["device"] for a in asg2) and len({a["device"] for a in asg2}) == 6
    # no moves at all -> every slot is persona-only at rung 3
    empty = matrix.assign(2, 1, [], {}, [], ["lara-acosta"], {}, tax)
    assert [a["move"] for a in empty] == [None, None] and [a["rung"] for a in empty] == [3, 3]


def test_matrix_lens_and_platform_options(proj: Path) -> None:
    asg = matrix.build(3, 4171, root=proj, lens="justin-welsh")["assignments"]
    assert [a["lens"] for a in asg] == [None, "justin-welsh", "justin-welsh"]
    x_only = matrix.build(3, 4171, root=proj, platform="x")["assignments"]
    assert "quote_then_deflate" not in {a["move"] for a in x_only}  # linkedin-only move filtered (and low score)
    moves = {m["id"]: m for m in matrix.load_inputs(proj)["moves"]}
    for a in x_only:
        if a["move"]:
            assert not moves[a["move"]]["platforms"] or "x" in moves[a["move"]]["platforms"]


def test_matrix_cli(proj: Path) -> None:
    out = subprocess.run([sys.executable, str(TOOLS / "matrix.py"), "--n", "3", "--seed", "4171", "--root", str(proj), "--json"],
                         capture_output=True, text=True, check=True)
    doc = json.loads(out.stdout)
    assert doc["ok"] is True and len(doc["assignments"]) == 3
    bad = subprocess.run([sys.executable, str(TOOLS / "matrix.py"), "--n", "0", "--seed", "1", "--root", str(proj)],
                         capture_output=True, text=True)
    assert bad.returncode == 0 and json.loads(bad.stdout)["ok"] is False


# =========================================================================== metrics_parse

def test_metrics_canonical_example() -> None:
    doc = metrics_parse.parse("12k views 40 comments 3 reposts 2 saves 5 follows")
    assert doc["ok"] and doc["metrics"] == {"views": 12000, "comments": 40, "reposts": 3, "saves": 2, "follows": 5}
    assert doc["unparsed"] == [] and doc["warnings"] == []


@pytest.mark.parametrize("text,expected", [
    ("1.2M impressions 300 reactions 12 replies 4 retweets", {"views": 1200000, "likes": 300, "comments": 12, "reposts": 4}),
    ("views: 12k, likes = 1,234; reshares 2", {"views": 12000, "likes": 1234, "reposts": 2}),
    ("12.5K views 7 bookmarks 3 new followers", {"views": 12500, "saves": 7, "follows": 3}),
    ("12kviews 40comments", {"views": 12000, "comments": 40}),
    ("Views 12K", {"views": 12000}),
    ("2b impressions", {"views": 2000000000}),
])
def test_metrics_variants(text: str, expected: dict) -> None:
    doc = metrics_parse.parse(text)
    assert doc["ok"] is True, doc
    assert doc["metrics"] == expected


def test_metrics_edge_cases() -> None:
    dup = metrics_parse.parse("12k views 40 comments 1.2M impressions")
    assert dup["metrics"]["views"] == 1200000 and dup["warnings"] == ["views given twice; keeping 1200000"]
    after = metrics_parse.parse("12k views 40 comments --after 24h")
    assert after["after_hours"] == 24 and after["metrics"] == {"views": 12000, "comments": 40}
    assert metrics_parse.parse("500 views after 7d")["after_hours"] == 168
    junk = metrics_parse.parse("12k views banana 77")
    assert junk["metrics"] == {"views": 12000} and junk["unparsed"] == ["banana", "77"]
    none = metrics_parse.parse("nothing to see")
    assert none["ok"] is False and none["metrics"] == {} and "error" in none
    empty = metrics_parse.parse("   ")
    assert empty["ok"] is False
    assert metrics_parse.parse_number("1,234.5k") == 1234500
    assert metrics_parse.parse_number("abc") is None


def test_metrics_cli() -> None:
    out = subprocess.run([sys.executable, str(TOOLS / "metrics_parse.py"), "12k", "views", "40", "comments", "--json"],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["metrics"] == {"views": 12000, "comments": 40}


# =========================================================================== draft_id

def test_draft_id_scan(proj: Path) -> None:
    entries = draft_id.scan(proj)
    assert len(entries) == 6
    e = next(x for x in entries if x["run"] == "2026-09-10_agents-buying-domains" and x["file"] == "li_1.md")
    assert e["cid"] == "r1-w1-li" and e["platform"] == "linkedin" and e["tier2_tested"] is True
    assert e["topic"] == "agents buying domains to be safe"


def test_draft_id_resolution(proj: Path) -> None:
    amb = draft_id.resolve("agents li", proj)
    assert amb["ok"] is False and "ambiguous" in amb["error"]
    assert {c["run"] for c in amb["candidates"]} == {"2026-09-10_agents-buying-domains", "2026-09-12_agents-memory-leak"}

    r = draft_id.resolve("agents domains li", proj)
    assert r["ok"] and r["run"] == "2026-09-10_agents-buying-domains" and r["cid"] == "r1-w1-li"
    assert r["path"] == "drafts/2026-09-10_agents-buying-domains/final/li_1.md"
    assert [a["cid"] for a in r["alternates"]] == ["r1-w2-li"]  # the alternate on the same platform

    assert draft_id.resolve("memory li", proj)["run"] == "2026-09-12_agents-memory-leak"
    assert draft_id.resolve("agents x", proj)["cid"] == "r1-w1-x"  # only one run has an X variant
    assert draft_id.resolve("2026-09-12_agents li", proj)["run"] == "2026-09-12_agents-memory-leak"
    assert draft_id.resolve("2026-09-10_agents-buying-domains", proj, platform="li")["cid"] == "r1-w1-li"
    assert draft_id.resolve("agents leak", proj, platform="linkedin")["cid"] == "r1-w2-li"

    no_plat = draft_id.resolve("cursor", proj)
    assert no_plat["ok"] is False and no_plat["run"] == "2026-09-14_cursor-rules" and len(no_plat["candidates"]) == 2
    assert draft_id.resolve("cursor x", proj)["cid"] == "r2-w3-x"
    assert draft_id.resolve("r2-w3-x", proj)["run"] == "2026-09-14_cursor-rules"
    assert draft_id.resolve("drafts/2026-09-14_cursor-rules/final/li_1.md", proj)["cid"] == "r2-w1-li"

    assert draft_id.resolve("", proj)["ok"] is False
    assert draft_id.resolve("zzz li", proj)["ok"] is False
    assert draft_id.resolve("agents li", proj / "nope")["ok"] is False


def test_draft_id_cli(proj: Path) -> None:
    out = subprocess.run([sys.executable, str(TOOLS / "draft_id.py"), "cursor", "x", "--root", str(proj)],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["cid"] == "r2-w3-x"


# =========================================================================== status

def test_status_empty_project(tmp_path: Path) -> None:
    doc = status.collect(tmp_path, today=TODAY)
    assert doc["ok"] and doc["corpus"]["total"] == 0 and doc["profile_version"] is None
    assert doc["rubric_version"] is None and doc["health"]["state"] == "none"
    assert doc["small_corpus_mode"] is True
    assert any("persona.md missing" in n for n in doc["nags"])
    text = status.brief(doc)
    assert "corpus: 0 posts" in text and "nags:" in text


def test_status_fixture_project(proj: Path) -> None:
    doc = status.collect(proj, today=TODAY)
    c = doc["corpus"]
    assert c["per_split"] == {"train": 4, "heldout": 1, "self": 2}
    assert c["per_platform"] == {"linkedin": 4, "x": 3}
    assert c["per_author"] == {"lara-acosta": 3, "justin-welsh": 2, "self": 2}
    assert doc["profile_version"] == 3 and doc["rubric_version"] == "v1" and doc["lexicon_version"] == 2
    assert doc["health"]["state"] == "none"
    assert doc["small_corpus_mode"] is True
    assert doc["self_samples"] == {"count": 2, "min": 5, "target": 8}
    assert set(doc["drafts"]["pending_blind_ratings"]) == {"2026-09-12_agents-memory-leak", "2026-09-14_cursor-rules"}
    assert set(doc["drafts"]["unrated_older_than_days"]["runs"]) == {"2026-09-12_agents-memory-leak", "2026-09-14_cursor-rules"}
    assert doc["posted"]["without_metrics_after_days"]["items"] == ["2026-09-10_agents-buying-domains (linkedin)"]
    assert doc["disagreements_unresolved"] == 1
    assert doc["calibration_due"] is False
    nags = " ".join(doc["nags"])
    assert "2 draft(s) unrated >2d" in nags and "1 posted without metrics >3d" in nags
    assert "2 run(s) awaiting a blind rating" in nags and "1 unresolved disagreement" in nags
    assert "register_match_self is N/A" in nags and "small-corpus" in nags


def test_status_health_from_report_name(proj: Path) -> None:
    sha = status.rubric_sha(proj)
    assert sha and len(sha) == 64
    reports = proj / "evals" / "health" / "reports"
    reports.mkdir(parents=True)
    (reports / f"2026-09-15_{sha[:8]}_p3.md").write_text("# health\nstate: green\n", encoding="utf-8")
    assert status.collect(proj, today=TODAY)["health"]["state"] == "green"
    (reports / "2026-09-16_ffffffff_p3.md").write_text("# health\n", encoding="utf-8")
    h = status.collect(proj, today=TODAY)["health"]
    assert h["state"] == "stale" and "rubric/lexicon changed" in h["reason"]
    (reports / f"2026-09-17_{sha[:8]}_p2.md").write_text("# health\n", encoding="utf-8")
    assert "profile p3 newer" in status.collect(proj, today=TODAY)["health"]["reason"]


def test_status_cli_brief_and_json(proj: Path) -> None:
    out = subprocess.run([sys.executable, str(TOOLS / "status.py"), "--brief", "--root", str(proj)],
                         capture_output=True, text=True, check=True)
    assert out.stdout.startswith("postsmith · rubric v1")
    assert "self samples: 2/8" in out.stdout
    js = subprocess.run([sys.executable, str(TOOLS / "status.py"), "--json", "--root", str(proj)],
                        capture_output=True, text=True, check=True)
    assert json.loads(js.stdout)["ok"] is True
    empty = subprocess.run([sys.executable, str(TOOLS / "status.py"), "--brief", "--root", str(proj / "missing")],
                           capture_output=True, text=True)
    assert empty.returncode == 0 and "corpus: 0 posts" in empty.stdout


# =========================================================================== run_next: init and write

def test_init_creates_skeleton_and_matrix(proj: Path) -> None:
    doc = run_next.init("agents buying domains", "agents that buy domains to be safe", {"quick": True}, root=proj)
    assert doc["ok"] and doc["run"].startswith(dt.date.today().isoformat() + "_agents-buying-domains")
    rd = proj / "drafts" / doc["run"]
    for sub in ("round1/candidates", "round1/scores", "round1/prompts", "tier2", "media"):
        assert (rd / sub).is_dir()
    mx = _rj(rd / "matrix.json")
    assert len(mx["assignments"]) == 2 and mx["topic"] == "agents that buy domains to be safe"
    st = _rj(rd / "state.json")
    assert st["flags"]["quick"] is True and st["stage"] == "write"
    assert (rd / "run.log").read_text().count("init") == 1
    with pytest.raises(FileExistsError):
        run_next.init(doc["run"], "again", {}, root=proj)
    with pytest.raises(ValueError):
        run_next.init("other", "t", {"quick": True, "wide": True}, root=proj)


def test_write_stage_from_matrix(proj: Path) -> None:
    b = RunBuilder(proj, brief=False)
    doc = b.next()
    assert doc["stage"] == "write" and doc["round"] == 1
    assert any("brief.md" in w for w in doc["waiting_on"])
    writers = _by(doc, kind="agent", agent="post-writer")
    assert [a["name"] for a in writers] == ["post-writer-1", "post-writer-2", "post-writer-3"]
    assert writers[0]["output_paths"] == [f"drafts/{b.name}/round1/candidates/r1-w1-li.md",
                                          f"drafts/{b.name}/round1/candidates/r1-w1-x.md"]
    pf = proj / writers[1]["prompt_file"]
    assert pf.exists()
    text = pf.read_text()
    assert "Assignment (JSON)" in text and "style/authors/lara-acosta.md" in text and "brief.md" in text
    # platform restriction and cached state
    li = b.next(platform="linkedin")
    assert li["actions"][0]["output_paths"] == [f"drafts/{b.name}/round1/candidates/r1-w1-li.md"]
    st = _rj(b.rd / "state.json")
    assert st["stage"] == "write" and st["flags"]["platform"] == "linkedin" and st["history"]


def test_write_stage_without_matrix_notes(proj: Path) -> None:
    b = RunBuilder(proj)
    (b.rd / "matrix.json").unlink()
    doc = b.next()
    assert doc["stage"] == "write" and doc["actions"] == [] and any("matrix.json" in n for n in doc["notes"])


# =========================================================================== run_next: stage derivation

def test_stage_tier0(proj: Path) -> None:
    b = RunBuilder(proj)
    for cid in ("r1-w1-li", "r1-w1-x", "r1-w2-li", "r1-w2-x"):
        b.cand(cid, txt=False)
    doc = b.next()
    assert doc["stage"] == "tier0" and doc["round"] == 1
    tools = _by(doc, kind="tool", tool="tier0.py")
    assert [a["cid"] for a in tools] == ["r1-w1-li", "r1-w1-x", "r1-w2-li", "r1-w2-x"]
    assert tools[0]["command"] == (f"uv run tools/tier0.py drafts/{b.name}/round1/candidates/r1-w1-li.md --cid r1-w1-li"
                                   f" --siblings drafts/{b.name}/round1/candidates/r1-w2-li.md")
    assert tools[0]["siblings"] == ["r1-w2-li"] and tools[0]["args"][1:] == ["--cid", "r1-w1-li", "--siblings", f"drafts/{b.name}/round1/candidates/r1-w2-li.md"]
    assert doc["candidates"]["r1-w1-li"]["tier0"] is False
    # the same derivation again with no tier0.json written: the cid waits instead of looping on the same action
    doc2 = b.next()
    assert doc2["stage"] == "tier0" and not _by(doc2, kind="tool", tool="tier0.py")
    assert any(w.startswith("tier0:r1-w1-li:") for w in doc2["waiting_on"])
    # a rewritten candidate file is re-emitted
    md = b.rdir(1) / "candidates" / "r1-w1-li.md"
    future = time.time() + 5
    os.utime(md, (future, future))
    doc3 = b.next()
    assert [a["cid"] for a in _by(doc3, kind="tool", tool="tier0.py")] == ["r1-w1-li"]
    st = _rj(b.rd / "state.json")
    assert f"drafts/{b.name}/round1/scores/r1-w1-li.tier0.json" in st["requested_outputs"]


def test_stage_tier1_and_judge_prompts(proj: Path) -> None:
    b = RunBuilder(proj)
    for cid in ("r1-w1-li", "r1-w1-x", "r1-w2-li", "r1-w2-x"):
        b.cand(cid).tier0(cid, hardfail=(cid == "r1-w2-x"))
    doc = b.next()
    assert doc["stage"] == "tier1"
    acts = _by(doc, kind="agent")
    assert len(acts) == 12 and {a["agent"] for a in acts} == {f"judge-{lens}" for lens in LENSES}
    assert not _by(doc, cid="r1-w2-x")
    assert any("hard Tier 0 fails skip judges: r1-w2-x" in n for n in doc["notes"])
    reader = _by(doc, cid="r1-w1-li", lens="reader")[0]
    assert reader["output_path"] == f"drafts/{b.name}/round1/scores/r1-w1-li.reader.json"
    assert reader["prompt_file"] == f"drafts/{b.name}/round1/prompts/r1-w1-li.reader.md"
    rtxt = (proj / reader["prompt_file"]).read_text()
    assert "Read evals/rubric/current/rubric.md section 0 (protocol)" in rtxt
    assert "evals/rubric/current/anchors/clarity/{weak,strong}.md" in rtxt
    assert "Dimensions to score: clarity, substance, hook, regret_risk, reply_worthiness" in rtxt
    assert "Platform: linkedin" in rtxt and "Length is not quality." in rtxt and "<fold_preview>" in rtxt
    assert rtxt.count("</untrusted_post>") == 1 and "<\\/untrusted_post>" in rtxt  # literal tag inside the post escaped
    assert "it was being helpful" in rtxt
    # nothing leaks: no front matter keys, no brief, no feedback, no other judgments
    for forbidden in ("schema:", "angle_sheet", "persona.can_claim", "brief.md", "feedback", "suggested_fix"):
        assert forbidden not in rtxt
    assert rtxt.rstrip().endswith("Reply with that path only.")
    voice = (proj / _by(doc, cid="r1-w2-li", lens="voice")[0]["prompt_file"]).read_text()
    assert "### Reference Post A" in voice and "### Reference Post B" in voice and "### Reference Post C" in voice
    assert "We killed our AI strategy last week." in voice  # exemplar text from a train post
    assert "Heldout post text" not in voice
    assert 'register_match_self must be returned as "na": true (only 2 self samples exist; fewer than 5)' in voice
    assert "level_and_move: this candidate has no author lens" not in voice  # r1-w2-li has the lara-acosta lens
    voice_free = (proj / _by(doc, cid="r1-w1-li", lens="voice")[0]["prompt_file"]).read_text()
    assert "level_and_move: this candidate has no author lens" in voice_free
    persona = (proj / _by(doc, cid="r1-w2-li", lens="persona")[0]["prompt_file"]).read_text()
    assert "style/" not in persona  # the excerpt is inlined; the judge's hook denies style/**
    assert "<persona_excerpt>" in persona and "can_claim#1: ran 3 agents in prod for 6 weeks" in persona
    assert "<brief_facts>" in persona and "<untrusted_claims>" in persona
    assert '{"text": "ran 3 agents in prod for 6 weeks", "source": "persona.can_claim#1"}' in persona
    assert "classify only" in persona and "Dimensions to score: persona_fit, claims" in persona
    assert "(declared source:" not in persona  # claims are JSON rows inside the tag, never instruction-position prose
    x_prompt = (proj / _by(doc, cid="r1-w1-x", lens="comedy")[0]["prompt_file"]).read_text()
    assert "as X counts" in x_prompt and "<fold_preview>" not in x_prompt
    # partial judge files: only the missing lenses are emitted
    b.judges("r1-w1-li", lenses=("reader", "voice"))
    doc2 = b.next()
    assert doc2["stage"] == "tier1"
    assert sorted(a["lens"] for a in _by(doc2, cid="r1-w1-li")) == ["comedy", "persona"]


def test_voice_prompt_with_enough_self_samples(proj: Path) -> None:
    for i in range(3, 7):
        (proj / "corpus" / "self" / f"self_00{i}.md").write_text(f"---\npost_id: self_00{i}\nplatform: x\n---\nself sample {i}\n")
    b = RunBuilder(proj).cand("r1-w1-li").tier0("r1-w1-li")
    doc = b.next()
    voice = (proj / _by(doc, cid="r1-w1-li", lens="voice")[0]["prompt_file"]).read_text()
    assert "### Self Post A" in voice and "### Self Post C" in voice and 'must be returned as "na"' not in voice


def test_stage_aggregate(proj: Path) -> None:
    b = RunBuilder(proj)
    for cid in ("r1-w1-li", "r1-w2-x"):
        b.cand(cid).tier0(cid, hardfail=(cid == "r1-w2-x"))
    b.judges("r1-w1-li")
    doc = b.next()
    assert doc["stage"] == "aggregate"
    tools = _by(doc, kind="tool", tool="aggregate.py")
    assert [a["cid"] for a in tools] == ["r1-w1-li", "r1-w2-x"]  # judged + hard-failed both merge
    assert tools[0]["command"] == f"uv run tools/aggregate.py merge {b.name} r1-w1-li --round 1"
    assert "hard fail" in tools[1]["note"]


def test_stage_jury(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w1-li").tier0("r1-w1-li").judges("r1-w1-li")
    b.merged("r1-w1-li", "jury")
    doc = b.next()
    assert doc["stage"] == "jury"
    acts = _by(doc, kind="agent", jury=True)
    assert [(a["agent"], a["dimension"]) for a in acts] == [("judge-comedy", "not_ai"), ("judge-reader", "not_ai")]
    assert acts[0]["output_path"] == f"drafts/{b.name}/round1/scores/r1-w1-li.jury.comedy.not_ai.json"
    text = (proj / acts[0]["prompt_file"]).read_text()
    assert "(jury)" in text and "Dimensions to score: not_ai" in text and "Reason: threshold-1" in text
    assert "You are a comedy writer" in text and '"jury": true' in text
    assert "### Reference Post A" in text  # not_ai is a voice dimension: exemplars supplied
    # one jury file present -> only the other lens remains; both present -> re-aggregate
    b.jury("r1-w1-li", "comedy", "not_ai")
    doc2 = b.next()
    assert doc2["stage"] == "jury" and [a["agent"] for a in _by(doc2, kind="agent")] == ["judge-reader"]
    b.jury("r1-w1-li", "reader", "not_ai")
    doc3 = b.next()
    assert doc3["stage"] == "aggregate" and "re-merge" in doc3["actions"][0]["note"]


def test_jury_lenses_from_rotation_and_regex_question(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w1-li").tier0("r1-w1-li").judges("r1-w1-li")
    b.merged("r1-w1-li", "jury_nolenses")
    doc = b.next()
    assert [a["lens"] for a in _by(doc, kind="agent")] == ["reader", "voice"]  # humor -> comedy's rotation
    b.merged("r1-w1-li", "jury_regex")
    doc = b.next()
    acts = _by(doc, kind="agent")
    assert [a["lens"] for a in acts] == ["voice", "reader", "comedy"]
    text = (proj / acts[0]["prompt_file"]).read_text()
    assert "template or the exception" in text and "Dimensions to score: P10_contrast_flip" in text
    assert "anchors/P10_contrast_flip" not in text


def test_stage_rerun_after_rejection(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w1-li").tier0("r1-w1-li").judges("r1-w1-li")
    b.merged("r1-w1-li", "rerun")
    doc = b.next()
    assert doc["stage"] == "tier1"
    act = _by(doc, kind="agent")[0]
    assert act["agent"] == "judge-reader" and act["rerun_for"] == "comedy" and act["dimensions"] == ["humor"]
    assert act["output_path"] == f"drafts/{b.name}/round1/scores/r1-w1-li.reader.rerun-comedy.json"
    text = (proj / act["prompt_file"]).read_text()
    assert "(rerun for comedy)" in text and '"rerun_for": "comedy"' in text and "Dimensions to score: humor" in text
    _wj(proj / act["output_path"], {"lens": "reader", "rerun_for": "comedy", "dimensions": {"humor": {"score": 4}}})
    assert b.next()["stage"] == "aggregate"


def test_stage_feedback_then_write_then_next_round(proj: Path) -> None:
    b = RunBuilder(proj).full_round1()
    for cid in ("r1-w1-li", "r1-w1-x", "r1-w2-x"):
        b.merged(cid, "pass")
    b.merged("r1-w2-li", "fail")
    doc = b.next()
    assert doc["stage"] == "feedback"
    assert doc["actions"] == [{
        "id": "a1", "kind": "tool", "tool": "aggregate.py", "args": ["feedback", b.name, "r1-w2-li", "--round", "1"],
        "command": f"uv run tools/aggregate.py feedback {b.name} r1-w2-li --round 1", "cid": "r1-w2-li",
        "output_path": f"drafts/{b.name}/round1/feedback/r1-w2-li.md", "stage": "feedback", "depends_on": []}]
    b.feedback("r1-w2-li")
    doc = b.next()
    assert doc["stage"] == "write" and doc["round"] == 2
    act = doc["actions"][0]
    assert act["agent"] == "post-writer" and act["name"] == "post-writer-2" and act["cid"] == "r1-w2-li"
    assert act["feedback_file"] == f"drafts/{b.name}/round1/feedback/r1-w2-li.md"
    assert act["output_path"] == f"drafts/{b.name}/round2/candidates/r2-w2-li.md"
    assert act["prompt_file"] == (f"drafts/{b.name}/round2/writers/rewrite-r1-w2-li."
                                  f"{run_next.writer_prompt_token(b.name, 2, 2, 'r1-w2-li')}.md")  # never under prompts/
    text = (proj / act["prompt_file"]).read_text()
    assert "keep everything that passed" in text and "lineage.rewrite_of: r1-w2-li" in text
    assert "<feedback_packet>" in text and "cut the summarising last line" in text  # the packet is pasted in
    assert "<previous_candidate>" in text and "Three agents ran in prod for six weeks." in text and "cid: r1-w2-li" in text
    assert "Feedback packet: drafts/" not in text and "Your candidate: drafts/" not in text
    b.cand("r2-w2-li", k=2)
    doc = b.next()
    assert doc["stage"] == "tier0" and doc["round"] == 2 and doc["actions"][0]["cid"] == "r2-w2-li"
    assert doc["candidates"]["r1-w2-li"]["superseded_by"] == "r2-w2-li"


def test_max_rounds_exhausted_goes_to_deliver(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w2-li").tier0("r1-w2-li").judges("r1-w2-li")
    b.merged("r1-w2-li", "fail", k=1)
    assert b.next(quick=True)["stage"] == "feedback"  # round 1 < 2: still rewritable
    b.feedback("r1-w2-li")
    assert b.next(quick=True)["stage"] == "write"
    b.cand("r2-w2-li", k=2).tier0("r2-w2-li", k=2).judges("r2-w2-li", k=2)
    b.merged("r2-w2-li", "fail", k=2)
    doc = b.next(quick=True)  # quick: max 2 rounds
    assert doc["stage"] == "deliver"
    assert any("did not pass after round 2" in n for n in doc["notes"])
    assert doc["actions"][-1]["tool"] == "assemble_report.py"


def test_stage_tier2_actions(proj: Path) -> None:
    b = RunBuilder(proj).full_round1(persona_for={"r1-w1-li": "persona"})
    b.merged("r1-w1-li", "pass")
    b.merged("r1-w2-li", "pass_low")
    b.merged("r1-w1-x", "pass")
    b.merged("r1-w2-x", "pass")
    doc = b.next()
    assert doc["stage"] == "tier2"
    assert any("r1-w2-li: alternate (linkedin)" in n for n in doc["notes"])
    assert {a["cid"] for a in doc["actions"]} == {"r1-w1-li", "r1-w1-x"}  # top finalist per platform only
    li = _by(doc, cid="r1-w1-li")
    build = li[0]
    assert build["tool"] == "lineup.py" and build["args"][:3] == ["build", b.name, "r1-w1-li"] and "--seed" in build["args"]
    lineup_judges = [a for a in li if a.get("agent") == "judge-lineup"]
    assert [a["lens"] for a in lineup_judges] == ["reader", "voice", "comedy"]
    assert lineup_judges[0]["depends_on"] == [build["id"]]
    tok = lineup.lineup_token(b.name, "r1-w1-li", int(build["args"][build["args"].index("--seed") + 1]))
    assert lineup_judges[1]["prompt_file"] == f"drafts/{b.name}/tier2/lineup_{tok}.voice.prompt.md"
    assert lineup_judges[1]["output_path"] == f"drafts/{b.name}/tier2/lineup_{tok}.picks/voice.json"
    assert "r1-w1-li" not in lineup_judges[1]["prompt_file"]  # the judge-facing names never carry the cid
    pw = [a for a in li if a.get("tool") == "pairwise.py"][0]
    assert pw["args"] == ["build", b.name, "r1-w1-li", "--mode", "exemplars"]
    claims = [a for a in li if a.get("agent") == "judge-persona"]
    assert len(claims) == 1 and claims[0]["verify"] is True
    assert claims[0]["claims"] == ["LinkedIn down-ranks AI slop since July"]
    assert claims[0]["output_path"] == f"drafts/{b.name}/tier2/claims_r1-w1-li.json"
    ctext = (proj / claims[0]["prompt_file"]).read_text()
    assert "Mode: verify" in ctext and "<untrusted_post>" in ctext and "JSON array" in ctext
    assert not [a for a in _by(doc, cid="r1-w1-x") if a.get("agent") == "judge-persona"]  # no needs_check claims
    assert not [a for a in doc["actions"] if a.get("agent") == "media-director"]  # top finalists declared no media
    # --wide: both finalists per platform, and the image intent of r1-w2-li brings the media-director
    wide = b.next(wide=True)
    assert {a["cid"] for a in wide["actions"]} == {"r1-w1-li", "r1-w2-li", "r1-w1-x", "r1-w2-x"}
    md = [a for a in wide["actions"] if a.get("agent") == "media-director"]
    assert len(md) == 1 and md[0]["cid"] == "r1-w2-li" and md[0]["output_path"] == f"drafts/{b.name}/media/r1-w2-li.brief.yaml"
    _wj(b.rd / "state.json", {})  # forget the cached wide flag
    nomedia = b.next(wide=True, no_media=True)
    assert not [a for a in nomedia["actions"] if a.get("agent") == "media-director"]
    assert any("not rendered (--no-media)" in n for n in nomedia["notes"])
    _wj(b.rd / "state.json", {})
    quick = b.next(quick=True)
    assert quick["stage"] == "deliver" and any("quick: no lineup" in n for n in quick["notes"])
    _wj(b.rd / "state.json", {})
    x_only = b.next(platform="x")
    assert {a["cid"] for a in x_only["actions"]} == {"r1-w1-x"}


def test_tier2_progression_to_combined_and_deliver(proj: Path) -> None:
    b = RunBuilder(proj).full_round1(persona_for={"r1-w1-li": "persona"})
    b.merged("r1-w1-li", "pass")
    b.merged("r1-w1-x", "pass")
    for cid in ("r1-w2-li", "r1-w2-x"):
        b.merged(cid, "fail")
        b.feedback(cid)
    t2 = b.rd / "tier2"
    picks_dirs, verdict_dirs = {}, {}
    for cid in ("r1-w1-li", "r1-w1-x"):
        ltok = lineup.lineup_token(b.name, cid, common.stable_seed(b.name, cid, "lineup"))
        picks_dirs[cid] = t2 / f"lineup_{ltok}.picks"
        _wj(t2 / f"lineup_{cid}.key.json", {"seed": 1, "token": ltok, "picks_dir": f"drafts/{b.name}/tier2/lineup_{ltok}.picks",
                                            "prompt_files": {lens: f"drafts/{b.name}/tier2/lineup_{ltok}.{lens}.prompt.md"
                                                             for lens in ("reader", "voice", "comedy")}})
        for lens in ("reader", "voice", "comedy"):
            (t2 / f"lineup_{ltok}.{lens}.prompt.md").write_text("lineup\n")
        ptok = pairwise.pairwise_token(b.name, cid, "exemplars")
        verdict_dirs[cid] = t2 / f"pairwise_{ptok}.verdicts"
        _wj(t2 / f"pairwise_{cid}.exemplars.key.json",
            {"token": ptok, "verdicts_dir": f"drafts/{b.name}/tier2/pairwise_{ptok}.verdicts",
             "prompt_files": {"exemplar1": f"drafts/{b.name}/tier2/pairwise_{ptok}.exemplar1.prompt.md",
                              "exemplar2": f"drafts/{b.name}/tier2/pairwise_{ptok}.exemplar2.prompt.md"}})
    doc = b.next()
    assert doc["stage"] == "write"  # the failing siblings are rewritten first (strict precedence)
    for cid in ("r1-w2-li", "r1-w2-x"):
        b.cand("r2-w2-li", k=2) if cid == "r1-w2-li" else None
    (b.rdir(2) / "candidates" / "r2-w2-x.md").write_text((PARTS / "candidates" / "r1-w2-x.md").read_text().replace("r1-w2-x", "r2-w2-x"))
    for cid in ("r2-w2-li", "r2-w2-x"):
        b.tier0(cid, k=2).judges(cid, k=2)
        b.merged(cid, "dropped", k=2)
    doc = b.next()
    assert doc["stage"] == "tier2"
    assert any("r2-w2-li: dropped (overlap_persistent" in n for n in doc["notes"])
    li = _by(doc, cid="r1-w1-li")
    assert [a["agent"] for a in li if a["kind"] == "agent"][:3] == ["judge-lineup"] * 3
    slots = [a for a in li if a.get("agent") == "judge-pairwise"]
    assert [a["slot"] for a in slots] == ["exemplar1", "exemplar2"]
    assert slots[0]["output_path"] == f"drafts/{b.name}/tier2/{verdict_dirs['r1-w1-li'].name}/exemplar1.json"
    assert "r1-w1-li" not in slots[0]["prompt_file"] and "r1-w1-li" not in slots[0]["output_path"]
    # picks + verdicts + claims land -> score actions (each written where its action said)
    for cid in ("r1-w1-li", "r1-w1-x"):
        for lens in ("reader", "voice", "comedy"):
            _wj(picks_dirs[cid] / f"{lens}.json", {"pick": "B", "confidence": 2})
        for slot in ("exemplar1", "exemplar2"):
            _wj(verdict_dirs[cid] / f"{slot}.json", {"same_skeleton_or_joke": False})
    _wj(t2 / "claims_r1-w1-li.json", [{"text": "LinkedIn down-ranks AI slop since July", "status": "verified", "source": "brief.fact#2"}])
    doc = b.next()
    assert doc["stage"] == "tier2"
    cmds = [a["command"] for a in _by(doc, cid="r1-w1-li")]
    assert cmds == [f"uv run tools/lineup.py score {b.name} r1-w1-li",
                    f"uv run tools/pairwise.py score {b.name} r1-w1-li --mode exemplars"]
    for cid in ("r1-w1-li", "r1-w1-x"):
        _wj(t2 / f"lineup_{cid}.score.json", {"pass": True, "picks": [], "candidate_picks": 0})
        _wj(t2 / f"pairwise_{cid}.exemplars.score.json", {"paraphrase": False, "verdicts": [{"slot": "exemplar1"}]})
    doc = b.next()
    assert doc["stage"] == "tier2"
    merges = [a for a in doc["actions"] if a.get("tool") == "aggregate.py"]
    assert [a["command"] for a in merges] == [f"uv run tools/aggregate.py merge {b.name} r1-w1-li --round 1",
                                              f"uv run tools/aggregate.py merge {b.name} r1-w1-x --round 1"]
    combined = _rj(t2 / "r1-w1-li.tier2.json")
    assert combined["lineup"]["pass"] is True and combined["paraphrase"]["same_skeleton_or_joke"] is False
    assert combined["claims"][0]["status"] == "verified" and combined["media"] is None
    # merged now carries tier2 -> deliver -> done
    b.merged("r1-w1-li", "tier2_pass")
    b.merged("r1-w1-x", "tier2_pass")
    doc = b.next()
    assert doc["stage"] == "deliver"
    assert [a["tool"] for a in doc["actions"]] == ["quote_leak_check.py", "quote_leak_check.py", "assemble_report.py"]
    assert doc["actions"][-1]["command"] == f"uv run tools/assemble_report.py {b.name}"
    (b.rd / "final").mkdir()
    (b.rd / "final" / "report.md").write_text("# report\n")
    doc = b.next()
    assert doc["stage"] == "done" and doc["actions"] == []
    hist = _rj(b.rd / "state.json")["history"]
    assert [h["stage"] for h in hist][-3:] == ["tier2", "deliver", "done"]


def test_media_progression(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w2-li").tier0("r1-w2-li").judges("r1-w2-li")
    b.merged("r1-w2-li", "pass")
    doc = b.next()
    md = [a for a in doc["actions"] if a.get("agent") == "media-director"]
    assert md and md[0]["prompts_dir"] == f"drafts/{b.name}/media/r1-w2-li.prompts"
    brief = b.rd / "media" / "r1-w2-li.brief.yaml"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("schema: postsmith.media/1\ndecision: image\n", encoding="utf-8")
    (b.rd / "media" / "r1-w2-li.prompts").mkdir()
    (b.rd / "media" / "r1-w2-li.prompts" / "gpt_image.md").write_text("prompt text\n")
    doc = b.next()
    chk = [a for a in doc["actions"] if a.get("tool") == "media_check.py"][0]
    assert chk["command"].endswith(f"--prompts drafts/{b.name}/media/r1-w2-li.prompts > drafts/{b.name}/media/r1-w2-li.media-check.json")
    judge = [a for a in doc["actions"] if a.get("agent") == "media-judge"][0]
    assert judge["depends_on"] == [chk["id"]]
    jtext = (proj / judge["prompt_file"]).read_text()
    assert "<media_brief>" in jtext and "## Tool prompt: gpt_image" in jtext and "<untrusted_post>" in jtext
    _wj(b.rd / "media" / "r1-w2-li.media-check.json", {"ok": True, "fails": []})
    _wj(b.rd / "media" / "r1-w2-li.media-judge.json",
        {"lens": "media", "dimensions": {"media": {"sub_results": {"alt_text_alone": True, "does_work": True, "slop_screen": True,
                                                                     "executable": 4, "factual": True, "capture_direction": None}}}})
    t2 = b.rd / "tier2"
    _wj(t2 / "lineup_r1-w2-li.key.json", {})
    ltok = lineup.lineup_token(b.name, "r1-w2-li", common.stable_seed(b.name, "r1-w2-li", "lineup"))
    for lens in ("reader", "voice", "comedy"):
        _wj(t2 / f"lineup_{ltok}.picks" / f"{lens}.json", {})
    _wj(t2 / "lineup_r1-w2-li.score.json", {"pass": True})
    _wj(t2 / "pairwise_r1-w2-li.exemplars.key.json", {"prompt_files": {}, "skipped": "no exemplars_seen in lineage"})
    _wj(t2 / "pairwise_r1-w2-li.exemplars.score.json", {"paraphrase": False, "skipped": "no exemplars_seen in lineage"})
    doc = b.next()
    assert [a.get("tool") for a in doc["actions"]] == ["aggregate.py"]
    combined = _rj(t2 / "r1-w2-li.tier2.json")
    assert combined["media"] == {"decision": "image", "media_check": "pass", "media_judge": "pass",
                                 "path": f"drafts/{b.name}/media/r1-w2-li.brief.yaml", "check_fails": []}
    assert run_next._media_judge_verdict({"dimensions": {"media": {"sub_results": {"alt_text_alone": "no"}}}}) == "fail"
    assert run_next._media_judge_verdict({}) == "fail"


def test_stopped_needs_call_and_hold_paths(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w1-li").tier0("r1-w1-li").judges("r1-w1-li")
    b.merged("r1-w1-li", "oscillation")
    doc = b.next()
    assert doc["stage"] == "stopped" and doc["actions"] == []
    assert doc["waiting_on"] == ["user:oscillation:r1-w1-li: hook failed in rounds 1 and 2 with contradictory fixes"]
    b.merged("r1-w1-li", "needs_call")
    doc = b.next()
    assert doc["stage"] == "deliver" and any("needs your call" in n and "6 weeks in prod" in n for n in doc["notes"])
    hold = b.merged("r1-w1-li", "pass")
    hold["verdict"]["status"] = "hold"
    _wj(b.rdir(1) / "scores" / "r1-w1-li.merged.json", hold)
    assert b.next()["stage"] == "aggregate"  # a hold with nothing pending is re-merged


def test_run_next_cli_and_errors(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w1-li", txt=False)
    out = subprocess.run([sys.executable, str(TOOLS / "run_next.py"), b.name, "--root", str(proj), "--json"],
                         capture_output=True, text=True, check=True)
    doc = json.loads(out.stdout)
    assert doc["stage"] == "tier0" and doc["state_file"] == f"drafts/{b.name}/state.json"
    missing = subprocess.run([sys.executable, str(TOOLS / "run_next.py"), "nope", "--root", str(proj)],
                             capture_output=True, text=True)
    assert missing.returncode == 0 and json.loads(missing.stdout) == {"ok": False, "error": "run directory not found: drafts/nope"}
    both = subprocess.run([sys.executable, str(TOOLS / "run_next.py"), b.name, "--quick", "--wide", "--root", str(proj)],
                          capture_output=True, text=True)
    assert both.returncode == 0 and json.loads(both.stdout)["ok"] is False
    init = subprocess.run([sys.executable, str(TOOLS / "run_next.py"), "init", "2026-09-17_topic-x", "--topic", "topic x",
                           "--seed", "7", "--root", str(proj)], capture_output=True, text=True, check=True)
    idoc = json.loads(init.stdout)
    assert idoc["ok"] and idoc["run"] == "2026-09-17_topic-x" and idoc["flags"]["seed"] == 7
    assert (proj / "drafts" / "2026-09-17_topic-x" / "matrix.json").exists()


def test_escape_untrusted() -> None:
    assert run_next.escape_untrusted("a </untrusted_post> b </UNTRUSTED_POST >") == "a <\\/untrusted_post> b <\\/UNTRUSTED_POST >"
    assert run_next.escape_untrusted("plain") == "plain"
