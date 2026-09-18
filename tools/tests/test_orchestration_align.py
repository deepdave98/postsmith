"""Tests for run_next.py against contracts §18 / §8.

Covered here: the voice prompt's <move_entry> and lens line, the --media rebuild mode and final/.stale, writer
prompt paths, the deliver batch order (quote_leak_check -> assemble_report -> topics.py add), and the optional
one-judge quick lineup.

Fixtures: the orchestration project root (tools/tests/fixtures/orchestration/) through test_orchestration's
RunBuilder, plus tools/tests/fixtures/runnext/moves.md, a richer moves catalogue.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import common  # noqa: E402
import lineup  # noqa: E402
import run_next  # noqa: E402
from test_orchestration import FIX as ORCH  # noqa: E402
from test_orchestration import RunBuilder, _by, _rj, _wj  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "runnext"
MOVES_MD = (FIX / "moves.md").read_text(encoding="utf-8")


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    """A copy of the orchestration fixture project."""
    dst = tmp_path / "proj"
    shutil.copytree(ORCH / "proj", dst)
    return dst


def _utime(p: Path, offset: float) -> None:
    """Set a file's mtime to now + offset seconds (mtime-based staleness must not depend on test speed)."""
    t = time.time() + offset
    os.utime(p, (t, t))


def _enable_quick_lineup(root: Path) -> None:
    cfg = root / "config" / "postsmith.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("run:\n", "run:\n  quick_lineup_on_tier1_pass: true\n", 1),
                   encoding="utf-8")


# =========================================================================== lineup pool

def test_lineup_pool_falls_back_to_train_while_the_corpus_is_small(proj: Path) -> None:
    """`lineup.py build --pool heldout` fails with "no eligible heldout fillers" while the heldout split is
    empty, which is every corpus in small-corpus mode, so run_next asks for the train pool there. health_run.py
    uses the same rule."""
    posts = proj / "corpus" / "posts"
    posts.mkdir(parents=True, exist_ok=True)
    heldout = proj / "corpus" / "heldout"
    heldout.mkdir(parents=True, exist_ok=True)
    for old_post in heldout.glob("*.md"):   # the fixture ships one heldout post; start from an empty split
        old_post.unlink()
    with common.use_root(proj):
        assert run_next.lineup_pool("linkedin") == "train"          # small corpus: no heldout split yet
        for i in range(30):                                          # over small_corpus_max_posts, both platforms
            plat = "linkedin" if i % 2 else "x"
            (posts / f"filler_{i:03}.md").write_text(
                f"---\npost_id: filler_{i:03}\nplatform: {plat}\n---\nbody {i}\n", encoding="utf-8")
        assert run_next.lineup_pool("linkedin") == "train"           # corpus big enough, heldout still empty
        (heldout / "held_001.md").write_text("---\npost_id: held_001\nplatform: linkedin\n---\nbody\n",
                                             encoding="utf-8")
        assert run_next.lineup_pool("linkedin") == "heldout"
        assert run_next.lineup_pool("x") == "train"                  # nothing held out for X yet
        assert run_next.lineup_pool() == "heldout"                   # platform-blind: any heldout post will do


# =========================================================================== moves catalogue

def test_parse_move_entries_is_tolerant() -> None:
    cat = run_next.parse_move_entries(MOVES_MD)
    assert sorted(cat) == ["corporate_register_for_trivial_event", "quote_then_deflate", "receipt_as_proof"]
    c = cat["corporate_register_for_trivial_event"]
    assert c["mechanism"].startswith("incongruous register")
    assert c["trigger"] == "a small daily irritation on a tech topic"
    # indented continuation lines and bulleted sub-items (even with a colon) stay inside the field
    assert c["execute_without_copying"].splitlines() == [
        "change the institution parodied and the specific;",
        'never reuse the framing phrase "root cause accepted"',
        "what to change: the incident vocabulary (postmortem, SLA, on-call)",
        "what never to reuse: the exact line shape of acosta_001",
    ]
    assert "what_to_change" not in c
    assert c["platforms"] == "linkedin, x" and c["aliases"] == ["incident_report_framing"]  # list + merged_into
    assert c["seen_in"] == "[acosta_001 L1-4, welsh_002 L1-6]"
    r = cat["receipt_as_proof"]  # backticked heading, unbracketed platforms
    assert r["platforms"] == "linkedin, x" and "</move_entry>" in r["mechanism"]
    assert "trigger" not in cat["quote_then_deflate"]
    assert run_next.parse_move_entries("") == {}


def test_find_move_entry_resolves_aliases() -> None:
    cat = run_next.parse_move_entries(MOVES_MD)
    assert run_next.find_move_entry(cat, "incident_report_framing")["id"] == "corporate_register_for_trivial_event"
    assert run_next.find_move_entry(cat, "Receipt_As_Proof")["id"] == "receipt_as_proof"
    assert run_next.find_move_entry(cat, "nope") is None and run_next.find_move_entry(cat, None) is None


def test_move_entry_block_never_carries_seen_in_post_ids_or_a_live_tag() -> None:
    cat = run_next.parse_move_entries(MOVES_MD)
    block = "\n".join(run_next.move_entry_lines("receipt_as_proof", cat["receipt_as_proof"]))
    assert block.startswith("<move_entry>\nmove: receipt_as_proof\nmechanism: ")
    assert block.count("</move_entry>") == 1 and "<\\/move_entry>" in block  # the literal tag inside the field is escaped
    assert "seen_in" not in block and "welsh_002" not in block and "acosta_002" not in block
    block2 = "\n".join(run_next.move_entry_lines("corporate_register_for_trivial_event",
                                                 cat["corporate_register_for_trivial_event"]))
    assert "risk: reads as a bit when the event is not trivial (see (post))" in block2  # ids scrubbed, never listed
    assert "acosta_001" not in block2 and "aliases" not in block2 and "incident_report_framing" not in block2
    body = block2.splitlines()[1:-1]
    assert [ln.split(":")[0] for ln in body if not ln.startswith("  ")] == \
        ["move", "mechanism", "trigger", "shape", "execute_without_copying", "risk", "platforms"]
    assert "  what to change: the incident vocabulary (postmortem, SLA, on-call)" in body  # continuation, indented


def test_moves_lint_parser_is_preferred_when_present_and_fallback_otherwise(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "style").mkdir()
    (tmp_path / "style" / "moves.md").write_text(MOVES_MD, encoding="utf-8")
    stub = types.ModuleType("moves_lint")
    seen: list[str] = []

    def parse_moves(text: str):
        seen.append(text)
        return [{"id": "from_lint", "mechanism": "lint says so", "aliases": ["alias_x"]}]

    stub.parse_moves = parse_moves  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "moves_lint", stub)
    cat = run_next.load_moves_catalogue(tmp_path)
    assert seen == [MOVES_MD] and list(cat) == ["from_lint"]
    assert run_next.find_move_entry(cat, "alias_x")["mechanism"] == "lint says so"
    # a parser that raises, or returns an unusable shape, falls back to the local parser
    stub.parse_moves = lambda text: (_ for _ in ()).throw(TypeError("wrong signature"))  # type: ignore[attr-defined]
    assert "receipt_as_proof" in run_next.load_moves_catalogue(tmp_path)
    stub.parse_moves = lambda text: "not a catalogue"  # type: ignore[attr-defined]
    assert "receipt_as_proof" in run_next.load_moves_catalogue(tmp_path)
    monkeypatch.delitem(sys.modules, "moves_lint")
    assert "receipt_as_proof" in run_next.load_moves_catalogue(tmp_path)
    assert run_next.load_moves_catalogue(tmp_path / "missing") == {}


# =========================================================================== voice prompt: lens line + move entry

def test_voice_prompt_inlines_move_entry_and_states_the_lens(proj: Path) -> None:
    (proj / "style" / "moves.md").write_text(MOVES_MD, encoding="utf-8")
    b = RunBuilder(proj)
    for cid in ("r1-w1-li", "r1-w2-li"):
        b.cand(cid).tier0(cid)
    doc = b.next()
    assert doc["stage"] == "tier1"
    voice = (proj / _by(doc, cid="r1-w2-li", lens="voice")[0]["prompt_file"]).read_text(encoding="utf-8")
    assert "## Assignment (for level_and_move" in voice and "\nlens: lara-acosta\n" in voice
    assert voice.count("<move_entry>") == 1 and voice.count("</move_entry>") == 1
    assert "move: corporate_register_for_trivial_event" in voice
    assert "mechanism: incongruous register; the scale of the language mismatches" in voice
    assert "execute_without_copying: change the institution parodied" in voice
    assert "shape: announcement line / one-line proof / flat root cause" in voice
    assert "seen_in" not in voice and "acosta_001" not in voice and "welsh_002" not in voice  # never a post id
    assert "aliases" not in voice and "lens: none" not in voice
    assert "level_and_move: this candidate has no author lens" not in voice
    # the lens-free writer: `lens: none` is stated, level_and_move is na, the entry is still supplied as context
    free = (proj / _by(doc, cid="r1-w1-li", lens="voice")[0]["prompt_file"]).read_text(encoding="utf-8")
    assert "\nlens: none\n" in free and "level_and_move: this candidate has no author lens" in free
    assert "<move_entry>" in free
    # the assignment block appears before the reference posts and only in prompts that score level_and_move
    assert free.index("## Assignment") < free.index("## Reference posts")
    reader = (proj / _by(doc, cid="r1-w2-li", lens="reader")[0]["prompt_file"]).read_text(encoding="utf-8")
    assert "<move_entry>" not in reader and "\nlens: " not in reader and "## Assignment" not in reader
    comedy = (proj / _by(doc, cid="r1-w2-li", lens="comedy")[0]["prompt_file"]).read_text(encoding="utf-8")
    assert "<move_entry>" not in comedy
    # a jury on level_and_move gets the same block
    ctx = run_next.PromptContext(proj, b.name, run_next.load_config_at(proj))
    c = next(x for x in run_next.scan_candidates(proj, b.rd) if x.cid == "r1-w2-li")
    jury = run_next.judge_prompt(ctx, c, "comedy", "out.json", ["level_and_move"],
                                 jury={"dimension": "level_and_move", "reason": "threshold-1"})
    assert "<move_entry>" in jury and "lens: lara-acosta" in jury
    other = run_next.judge_prompt(ctx, c, "comedy", "out.json", ["humor"], jury={"dimension": "humor", "reason": "x"})
    assert "<move_entry>" not in other


def test_voice_prompt_without_an_entry_or_a_move_says_so(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w2-li").tier0("r1-w2-li")
    md = b.rdir(1) / "candidates" / "r1-w2-li.md"
    meta, body = common.split_front_matter(md.read_text(encoding="utf-8"))
    meta["assignment"]["move"] = "move_nobody_wrote_down"
    common.write_front_matter_file(md, meta, body)
    doc = b.next()
    voice = (proj / _by(doc, cid="r1-w2-li", lens="voice")[0]["prompt_file"]).read_text(encoding="utf-8")
    assert "lens: lara-acosta" in voice and "move: move_nobody_wrote_down" in voice
    assert "no entry for move_nobody_wrote_down" in voice and 'write "move entry not supplied" in pre_step' in voice
    assert "<move_entry>" not in voice
    meta["assignment"]["move"] = None  # persona-only rung: no move at all
    common.write_front_matter_file(md, meta, body)
    voice = (proj / _by(b.next(), cid="r1-w2-li", lens="voice")[0]["prompt_file"]).read_text(encoding="utf-8")
    assert "move: none (no move assigned" in voice and "<move_entry>" not in voice
    # a candidate assigned an alias resolves to the canonical entry (fixture moves.md carries the merged section)
    meta["assignment"]["move"] = "incident_report_framing"
    common.write_front_matter_file(md, meta, body)
    voice = (proj / _by(b.next(), cid="r1-w2-li", lens="voice")[0]["prompt_file"]).read_text(encoding="utf-8")
    assert "move: corporate_register_for_trivial_event" in voice and "mechanism: incongruous register" in voice


# =========================================================================== writer prompt paths (verify)

def test_writer_prompts_live_under_writers_and_the_rewrite_inlines_packet_and_candidate(proj: Path) -> None:
    b = RunBuilder(proj)
    doc = b.next()
    writers = _by(doc, kind="agent", agent="post-writer")
    # writer-<n>.<token>.md: the token is not derivable from a writer's own identity, so no writer can name a
    # sibling's prompt file (and read the packet and previous candidate inlined in it)
    files = [a["prompt_file"] for a in writers]
    assert [re.fullmatch(rf"drafts/{b.name}/round1/writers/writer-{n}\.[0-9a-f]{{10}}\.md", f) is not None
            for n, f in zip((1, 2, 3), files)] == [True, True, True], files
    assert files == [f"drafts/{b.name}/round1/writers/writer-{n}.{run_next.writer_prompt_token(b.name, 1, n)}.md"
                     for n in (1, 2, 3)]
    assert all((proj / a["prompt_file"]).exists() for a in writers)
    assert not list((b.rdir(1) / "prompts").glob("*.md")) if (b.rdir(1) / "prompts").exists() else True
    b.cand("r1-w2-li").tier0("r1-w2-li").judges("r1-w2-li")
    b.merged("r1-w2-li", "fail")
    b.feedback("r1-w2-li")
    doc = b.next()
    assert doc["stage"] == "write"
    act = doc["actions"][0]
    assert act["prompt_file"] == (f"drafts/{b.name}/round2/writers/rewrite-r1-w2-li."
                                  f"{run_next.writer_prompt_token(b.name, 2, 2, 'r1-w2-li')}.md")
    text = (proj / act["prompt_file"]).read_text(encoding="utf-8")
    assert text.count("<feedback_packet>") == 1 and text.count("</feedback_packet>") == 1
    assert text.count("<previous_candidate>") == 1 and text.count("</previous_candidate>") == 1
    packet = b.rdir(1).joinpath("feedback", "r1-w2-li.md").read_text(encoding="utf-8").rstrip("\n")
    assert run_next.escape_untrusted(packet) in text
    assert "open no candidates/ or feedback/ file" in text
    assert not list((b.rdir(2) / "prompts").glob("*.md")) if (b.rdir(2) / "prompts").exists() else True


# =========================================================================== deliver batch

def _deliverable(proj: Path, topic: bool) -> RunBuilder:
    if topic:
        run_next.init("2026-09-16_cursor-rules", "cursor rules, the short version", {}, root=proj)
    b = RunBuilder(proj).full_round1()
    for cid in ("r1-w1-li", "r1-w1-x", "r1-w2-li", "r1-w2-x"):
        b.merged(cid, "tier2_pass" if cid.startswith("r1-w1") else "pass_low")
    return b


def test_deliver_emits_leak_check_report_and_topics_in_order_then_archives(proj: Path) -> None:
    b = _deliverable(proj, topic=True)
    assert _rj(b.rd / "state.json")["topic"] == "cursor rules, the short version"
    (b.rdir(1) / "prompts").mkdir(exist_ok=True)
    (b.rdir(1) / "prompts" / "r1-w1-li.reader.md").write_text("judge prompt\n", encoding="utf-8")
    doc = b.next()
    assert doc["stage"] == "deliver"
    tools = [a["tool"] for a in doc["actions"]]
    assert tools == ["quote_leak_check.py", "quote_leak_check.py", "assemble_report.py", "topics.py"]
    leak, leak2, report, topics = doc["actions"]
    assert leak["args"] == [f"drafts/{b.name}/round1/candidates/r1-w1-li.txt"] and leak2["cid"] == "r1-w1-x"
    assert report["command"] == f"uv run tools/assemble_report.py {b.name}" and report["depends_on"] == [leak["id"], leak2["id"]]
    assert topics["command"] == f"uv run tools/topics.py add {b.name} --outcome pass"
    assert topics["args"] == ["add", b.name, "--outcome", "pass"] and topics["depends_on"] == [report["id"]]
    assert topics["output_path"] == "memory/topics.md" and topics["stage"] == "deliver"
    assert (b.rd / "archive" / "round1" / "prompts" / "r1-w1-li.reader.md").exists()  # archived after the batch
    assert not list((b.rdir(1) / "prompts").glob("*.md"))
    st = _rj(b.rd / "state.json")
    assert "memory/topics.md" in st["requested_outputs"] and st["requested_outputs"]["memory/topics.md"]["by"] == "topics.py"


def test_deliver_without_a_recorded_topic_notes_it_and_without_a_pass_omits_the_outcome(proj: Path) -> None:
    b = _deliverable(proj, topic=False)
    doc = b.next()
    assert doc["stage"] == "deliver"
    assert [a["tool"] for a in doc["actions"]] == ["quote_leak_check.py", "quote_leak_check.py", "assemble_report.py"]
    assert any("topics.py add skipped" in n and "no topic" in n for n in doc["notes"])
    # a run with a topic but no passing candidate: the row is added without --outcome pass
    b2 = RunBuilder(proj, name="2026-09-16_nothing-passed")
    _wj(b2.rd / "state.json", {"schema": run_next.STATE_SCHEMA, "run": b2.name, "topic": "nothing passed", "history": []})
    b2.cand("r1-w2-li").tier0("r1-w2-li").judges("r1-w2-li")
    b2.merged("r1-w2-li", "fail", k=1)
    b2.feedback("r1-w2-li")
    b2.cand("r2-w2-li", k=2).tier0("r2-w2-li", k=2).judges("r2-w2-li", k=2)
    b2.merged("r2-w2-li", "fail", k=2)
    doc = b2.next(quick=True)  # max 2 rounds under --quick: exhausted -> deliver
    assert doc["stage"] == "deliver"
    topics = [a for a in doc["actions"] if a.get("tool") == "topics.py"]
    assert len(topics) == 1 and topics[0]["args"] == ["add", b2.name] and "no passing candidate" in topics[0]["note"]
    assert any("no passing candidate" in n for n in doc["notes"])


# =========================================================================== quick lineup

def test_quick_lineup_is_off_by_default_and_documented_in_config() -> None:
    real_cfg = common.load_yaml(TOOLS.parent / "config" / "postsmith.yaml")
    assert real_cfg["run"][run_next.QUICK_LINEUP_KEY] is False
    assert run_next.normalize_flags({}, {"run": {}})["quick_lineup"] is False
    assert run_next.normalize_flags({}, {"run": {run_next.QUICK_LINEUP_KEY: True}})["quick_lineup"] is True
    assert run_next.normalize_flags({"quick_lineup": True}, {"run": {}})["quick_lineup"] is True


def test_quick_lineup_rides_along_after_a_tier1_pass_and_feeds_tier2(proj: Path) -> None:
    _enable_quick_lineup(proj)
    b = RunBuilder(proj)
    for cid in ("r1-w1-li", "r1-w2-li"):
        b.cand(cid).tier0(cid).judges(cid)
    b.merged("r1-w1-li", "pass")
    b.merged("r1-w2-li", "fail")
    doc = b.next()
    assert doc["stage"] == "feedback"  # the failing sibling still owns the stage ...
    assert doc["actions"][0]["tool"] == "aggregate.py" and doc["actions"][0]["args"][0] == "feedback"
    quick = [a for a in doc["actions"] if a.get("quick")]  # ... and the passing one gets its quick lineup alongside
    seed = common.stable_seed(b.name, "r1-w1-li", "lineup")
    tok = lineup.lineup_token(b.name, "r1-w1-li", seed)
    lens = run_next.LINEUP_LENSES[common.stable_seed(b.name, "r1-w1-li", "quick_lineup") % 3]
    assert [a.get("tool") or a.get("agent") for a in quick] == ["lineup.py", "judge-lineup"]
    build, judge = quick
    with common.use_root(proj):   # the root the run was built under; the working project may have a heldout split
        pool = run_next.lineup_pool("linkedin")
    assert pool == "train"   # this fixture's corpus is small, so the heldout split is not drawn from
    assert build["args"] == ["build", b.name, "r1-w1-li", "--seed", str(seed), "--pool", pool]
    assert build["stage"] == "quick_lineup" and judge["depends_on"] == [build["id"]] and judge["lens"] == lens
    assert judge["prompt_file"] == f"drafts/{b.name}/tier2/lineup_{tok}.{lens}.prompt.md"
    assert judge["output_path"] == f"drafts/{b.name}/tier2/lineup_{tok}.picks/{lens}.json"
    assert not _by(doc, cid="r1-w2-li", quick=True)
    # --quick runs no lineup at all
    _wj(b.rd / "state.json", {})
    assert not [a for a in b.next(quick=True)["actions"] if a.get("quick")]
    _wj(b.rd / "state.json", {})
    # the build and the pick land -> score; a one-judge score carries `flag`, which the summary and the ranking read
    t2 = b.rd / "tier2"
    picks = t2 / f"lineup_{tok}.picks"
    _wj(t2 / "lineup_r1-w1-li.key.json", {"token": tok, "picks_dir": f"drafts/{b.name}/tier2/{picks.name}",
                                          "prompt_files": {x: f"drafts/{b.name}/tier2/lineup_{tok}.{x}.prompt.md" for x in run_next.LINEUP_LENSES}})
    _wj(picks / f"{lens}.json", {"pick": "B", "confidence": 5})
    doc = b.next()
    quick = [a for a in doc["actions"] if a.get("quick")]
    assert [a["command"] for a in quick] == [f"uv run tools/lineup.py score {b.name} r1-w1-li"]
    _wj(t2 / "lineup_r1-w1-li.score.json", {"ok": True, "n_judges": 1, "flag": True, "candidate_picks": 1, "picks": []})
    doc = b.next()
    assert not [a for a in doc["actions"] if a.get("quick")]
    assert doc["candidates"]["r1-w1-li"]["lineup"] == {"n_judges": 1, "flag": True, "candidate_picks": 1, "advisory": False}
    # ranking: the flagged candidate ranks below an unflagged sibling that also passed; Tier 2 picks the sibling
    b.feedback("r1-w2-li")
    b.cand("r2-w2-li", k=2).tier0("r2-w2-li", k=2).judges("r2-w2-li", k=2)
    b.merged("r2-w2-li", "pass", k=2)
    doc = b.next(platform="linkedin")
    assert doc["stage"] == "tier2"
    assert {a["cid"] for a in doc["actions"] if not a.get("quick")} == {"r2-w2-li"}
    assert any("r1-w1-li: alternate (linkedin), passed Tier 0-1, quick-lineup flagged" in n for n in doc["notes"])
    assert not [a for a in doc["actions"] if a.get("quick")]  # r1-w1-li's quick lineup is complete, r2-w2-li is top
    # the finalist's Tier 2 lineup reuses a quick build: no rebuild, only the two missing lenses, then a re-score
    _wj(b.rd / "state.json", {})
    ptok = lineup.lineup_token(b.name, "r2-w2-li", common.stable_seed(b.name, "r2-w2-li", "lineup"))
    ppicks = t2 / f"lineup_{ptok}.picks"
    _wj(t2 / "lineup_r2-w2-li.key.json", {"token": ptok, "picks_dir": f"drafts/{b.name}/tier2/{ppicks.name}",
                                          "prompt_files": {x: f"drafts/{b.name}/tier2/lineup_{ptok}.{x}.prompt.md" for x in run_next.LINEUP_LENSES}})
    _wj(ppicks / "reader.json", {"pick": "A", "confidence": 2})
    _wj(t2 / "lineup_r2-w2-li.score.json", {"ok": True, "n_judges": 1, "flag": False})
    _utime(t2 / "lineup_r2-w2-li.score.json", 5)
    doc = b.next(platform="linkedin")
    li = _by(doc, cid="r2-w2-li")
    assert not [a for a in li if a.get("tool") == "lineup.py" and a["args"][0] == "build"]
    assert [a["lens"] for a in li if a.get("agent") == "judge-lineup"] == ["voice", "comedy"]
    assert not [a for a in li if a.get("tool") == "lineup.py" and a["args"][0] == "score"]  # score fresh, picks missing
    for x in ("voice", "comedy"):
        _wj(ppicks / f"{x}.json", {"pick": "C", "confidence": 1})
        _utime(ppicks / f"{x}.json", 10)  # newer than the one-judge score
    doc = b.next(platform="linkedin")
    scores = [a for a in _by(doc, cid="r2-w2-li") if a.get("tool") == "lineup.py"]
    assert [a["args"] for a in scores] == [["score", b.name, "r2-w2-li"]] and "re-score" in scores[0]["note"]
    assert not [a for a in _by(doc, cid="r2-w2-li") if a.get("agent") == "judge-lineup"]


def test_quick_lineup_reuses_a_tier2_pick_and_skips_tier2_done_candidates(proj: Path) -> None:
    _enable_quick_lineup(proj)
    b = RunBuilder(proj)
    for cid in ("r1-w1-li", "r1-w2-li"):
        b.cand(cid).tier0(cid).judges(cid)
    b.merged("r1-w1-li", "tier2_pass")  # lineup already folded into merged: nothing to add
    b.merged("r1-w2-li", "fail")
    doc = b.next()
    assert doc["stage"] == "feedback" and not [a for a in doc["actions"] if a.get("quick")]
    # a Tier 2 pick that landed first counts as the quick judge (no second judge on another lens)
    b.merged("r1-w1-li", "pass")
    t2 = b.rd / "tier2"
    tok = lineup.lineup_token(b.name, "r1-w1-li", common.stable_seed(b.name, "r1-w1-li", "lineup"))
    _wj(t2 / "lineup_r1-w1-li.key.json", {"token": tok, "picks_dir": f"drafts/{b.name}/tier2/lineup_{tok}.picks"})
    _wj(t2 / f"lineup_{tok}.picks" / "comedy.json", {"pick": "D", "confidence": 3})
    doc = b.next()
    quick = [a for a in doc["actions"] if a.get("quick")]
    assert [a.get("tool") for a in quick] == ["lineup.py"] and quick[0]["args"][0] == "score"


# =========================================================================== --media rebuild

def _delivered(proj: Path) -> RunBuilder:
    b = RunBuilder(proj).cand("r1-w2-li").tier0("r1-w2-li").judges("r1-w2-li")
    b.merged("r1-w2-li", "tier2_pass")
    (b.rd / "final").mkdir()
    (b.rd / "final" / "report.md").write_text("# report\n", encoding="utf-8")
    _utime(b.rd / "final" / "report.md", -60)
    _utime(b.rdir(1) / "scores" / "r1-w2-li.merged.json", -60)
    return b


def test_media_rebuild_walks_director_check_judge_merge_report_and_marks_final_stale(proj: Path) -> None:
    b = _delivered(proj)
    assert b.next()["stage"] == "done"
    with pytest.raises(ValueError, match="candidate r9-w9-li not found"):
        run_next.derive_media(proj, b.name, "r9-w9-li")
    with pytest.raises(FileNotFoundError):
        run_next.derive_media(proj, "nope", "r1-w2-li")
    # 1. no brief -> media-director, final/.stale written with the reason
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    assert doc["ok"] and doc["mode"] == "media" and doc["stage"] == "media" and doc["complete"] is False
    assert [a["agent"] for a in doc["actions"]] == ["media-director"]
    md = doc["actions"][0]
    assert md["rebuild"] is True and md["candidate"] == f"drafts/{b.name}/round1/candidates/r1-w2-li.md"
    assert md["output_path"] == f"drafts/{b.name}/media/r1-w2-li.brief.yaml"
    assert md["prompts_dir"] == f"drafts/{b.name}/media/r1-w2-li.prompts" and md["inputs"] == run_next.MEDIA_DIRECTOR_INPUTS
    assert doc["stale"] == f"drafts/{b.name}/final/.stale"
    marker = json.loads((b.rd / "final" / ".stale").read_text(encoding="utf-8"))
    assert marker["schema"] == "postsmith.stale/1" and marker["cid"] == "r1-w2-li" and "media rebuild" in marker["reason"]
    assert marker["by"] == "run_next.py --media" and "media-director" in marker["reason"]
    st = _rj(b.rd / "state.json")
    assert st["stage"] == "done"  # the cached stage is untouched ...
    assert st["requested_outputs"][md["output_path"]]["stage"] == "media"  # ... but the request is on record
    assert st["history"][-1]["stage"] == "media" and st["history"][-1]["cid"] == "r1-w2-li"
    # the normal derivation now re-assembles instead of saying done
    doc = b.next()
    assert doc["stage"] == "deliver" and [a["tool"] for a in doc["actions"]] == ["assemble_report.py"]
    assert ".stale" in doc["actions"][0]["note"] and "media rebuild" in doc["actions"][0]["note"]
    # 2. brief + prompts -> media_check then media-judge (prompt built by the tool)
    brief = b.rd / "media" / "r1-w2-li.brief.yaml"
    brief.parent.mkdir(exist_ok=True)
    brief.write_text("schema: postsmith.media/1\ndecision: image\n", encoding="utf-8")
    pdir = b.rd / "media" / "r1-w2-li.prompts"
    pdir.mkdir()
    (pdir / "gpt_image.md").write_text("prompt text\n", encoding="utf-8")
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    chk, judge = doc["actions"]
    assert chk["tool"] == "media_check.py" and chk["command"].endswith(f"> drafts/{b.name}/media/r1-w2-li.media-check.json")
    assert judge["agent"] == "media-judge" and judge["depends_on"] == [chk["id"]] and judge["stage"] == "media"
    assert judge["prompt_file"] == f"drafts/{b.name}/media/r1-w2-li.judge.prompt.md"
    jtext = (proj / judge["prompt_file"]).read_text(encoding="utf-8")
    assert "<media_brief>" in jtext and "## Tool prompt: gpt_image" in jtext and "<untrusted_post>" in jtext
    assert judge["output_path"] == f"drafts/{b.name}/media/r1-w2-li.media-judge.json"
    # 3. check + judge (newer than the brief) -> the media part is folded, merge + assemble_report emitted
    _wj(b.rd / "media" / "r1-w2-li.media-check.json", {"ok": True, "fails": []})
    _wj(b.rd / "media" / "r1-w2-li.media-judge.json",
        {"lens": "media", "dimensions": {"media": {"sub_results": {"alt_text_alone": True, "does_work": True, "slop_screen": True,
                                                                     "executable": 4, "factual": True, "capture_direction": None}}}})
    for name in ("r1-w2-li.media-check.json", "r1-w2-li.media-judge.json"):
        _utime(b.rd / "media" / name, 5)
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    assert doc["complete"] is True
    merge, report = doc["actions"]
    assert merge["command"] == f"uv run tools/aggregate.py merge {b.name} r1-w2-li --round 1"
    assert report["tool"] == "assemble_report.py" and report["depends_on"] == [merge["id"]]
    assert doc["media"] == {"decision": "image", "media_check": "pass", "media_judge": "pass",
                            "path": f"drafts/{b.name}/media/r1-w2-li.brief.yaml", "check_fails": []}
    combined = _rj(b.rd / "tier2" / "r1-w2-li.tier2.json")
    assert combined["media"] == doc["media"] and combined["lineup"] is None and combined["cid"] == "r1-w2-li"
    assert (b.rd / "final" / ".stale").exists()
    # 4. merge ran (merged.json newer than the judge) but the report is still stale -> assemble_report only
    _utime(b.rdir(1) / "scores" / "r1-w2-li.merged.json", 20)
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    assert [a["tool"] for a in doc["actions"]] == ["assemble_report.py"]
    # 5. assemble_report re-ran: it removed the marker and rewrote the report -> nothing left to do
    (b.rd / "final" / ".stale").unlink()
    _utime(b.rd / "final" / "report.md", 30)
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    assert doc["actions"] == [] and doc["stale"] is None and any("up to date" in n for n in doc["notes"])
    assert not (b.rd / "final" / ".stale").exists()
    assert b.next()["stage"] == "done"
    # 6. a rewritten brief makes the check and the judge stale again (a rebuild overwrites the brief)
    _utime(brief, 60)
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    chk, judge = doc["actions"]
    assert chk["tool"] == "media_check.py" and "older than the brief" in chk["note"]
    assert judge["agent"] == "media-judge" and "older than the brief" in judge["note"]
    assert (b.rd / "final" / ".stale").exists()
    # 7. the rebuild closes when a poll finds nothing left, so the skill's "repeat until no action" loop terminates
    for name in ("r1-w2-li.media-check.json", "r1-w2-li.media-judge.json"):
        _utime(b.rd / "media" / name, 70)
    run_next.derive_media(proj, b.name, "r1-w2-li")                  # folds the part, emits merge + assemble_report
    _utime(b.rdir(1) / "scores" / "r1-w2-li.merged.json", 80)
    (b.rd / "final" / ".stale").unlink()
    _utime(b.rd / "final" / "report.md", 90)
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    assert doc["actions"] == [] and doc["rebuild_phase"] == "done"
    assert _rj(b.rd / "state.json")["media_rebuilds"]["r1-w2-li"]["phase"] == "done"
    # 8. the NEXT --media is a new request, not another poll: the complete brief is superseded and the director
    #    runs again, which is the only way /media can redo a brief or honour --tool / --genre / --none
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    assert [a["agent"] for a in doc["actions"]] == ["media-director"] and doc["actions"][0]["rebuild"] is True
    assert doc["rebuild_phase"] == "pending" and doc["stale"] == f"drafts/{b.name}/final/.stale"
    assert (b.rd / "media" / "r1-w2-li.brief.superseded.yaml").exists()
    assert not (b.rd / "media" / "r1-w2-li.brief.yaml").exists()
    # 9. once the director has written the new brief the director is not asked again (no infinite loop)
    brief.write_text("schema: postsmith.media/1\ndecision: image\n", encoding="utf-8")
    _utime(brief, 100)
    doc = run_next.derive_media(proj, b.name, "r1-w2-li")
    assert [a.get("agent") or a.get("tool") for a in doc["actions"]] == ["media_check.py", "media-judge"]


def test_media_rebuild_before_delivery_and_cli(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w1-li").tier0("r1-w1-li").judges("r1-w1-li")
    b.merged("r1-w1-li", "pass")
    doc = run_next.derive_media(proj, b.name, "r1-w1-li")  # decision none, no final/ yet
    assert [a["agent"] for a in doc["actions"]] == ["media-director"] and doc["stale"] is None
    assert any("media_intent.decision none" in n for n in doc["notes"])
    assert any("final/ does not exist yet" in n for n in doc["notes"])
    out = subprocess.run([sys.executable, str(TOOLS / "run_next.py"), b.name, "--media", "r1-w1-li", "--root", str(proj), "--json"],
                         capture_output=True, text=True, check=True)
    cli = json.loads(out.stdout)
    assert cli["ok"] and cli["mode"] == "media" and cli["cid"] == "r1-w1-li" and cli["state_file"] == f"drafts/{b.name}/state.json"
    bad = subprocess.run([sys.executable, str(TOOLS / "run_next.py"), b.name, "--media", "r9-w9-x", "--root", str(proj)],
                         capture_output=True, text=True, check=False)
    assert bad.returncode == 0 and json.loads(bad.stdout)["ok"] is False and "r9-w9-x not found" in json.loads(bad.stdout)["error"]
    helptext = subprocess.run([sys.executable, str(TOOLS / "run_next.py"), "--help"], capture_output=True, text=True, check=True).stdout
    assert "--media CID" in helptext


def test_tier2_media_step_treats_a_check_older_than_the_brief_as_missing(proj: Path) -> None:
    b = RunBuilder(proj).cand("r1-w2-li").tier0("r1-w2-li").judges("r1-w2-li")
    b.merged("r1-w2-li", "pass")
    media = b.rd / "media"
    media.mkdir(exist_ok=True)
    _wj(media / "r1-w2-li.media-check.json", {"ok": True, "fails": []})
    _wj(media / "r1-w2-li.media-judge.json", {"lens": "media", "dimensions": {"media": {"na": True, "sub_results": {}}}})
    for name in ("r1-w2-li.media-check.json", "r1-w2-li.media-judge.json"):
        _utime(media / name, -60)
    (media / "r1-w2-li.brief.yaml").write_text("schema: postsmith.media/1\ndecision: image\n", encoding="utf-8")
    doc = b.next()
    assert doc["stage"] == "tier2"
    assert [a.get("tool") or a.get("agent") for a in doc["actions"] if a.get("cid") == "r1-w2-li" and a.get("stage") == "tier2"
            and (a.get("tool") == "media_check.py" or a.get("agent") == "media-judge")] == ["media_check.py", "media-judge"]
    assert doc["actions"][-1]["agent"] == "media-judge" and doc["actions"][-1].get("rebuild") is None


# =========================================================================== stage docs stay accurate

def test_contracts_section_8_names_the_deliver_actions_and_media_mode() -> None:
    text = (TOOLS.parent / "docs" / "design" / "contracts.md").read_text(encoding="utf-8")
    sec = text.split("## 8. Run state")[1].split("\n## 9.")[0]
    for needle in ("`topics.py add <run> --outcome pass`", "`quote_leak_check.py <finalist.txt>`", "`assemble_report.py <run>`",
                   "`final/.stale`", "--media <cid>", "`<move_entry>`", "`lens: none`", "run.quick_lineup_on_tier1_pass",
                   "`round<k>/writers/`", "aggregate|jury"):
        assert needle in sec, needle
