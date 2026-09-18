"""Tests for tools/health_run.py, the grader health run (contracts section 17).

Scratch project roots are built from tools/tests/fixtures/corpus plus the real config, lexicon, rubric and golden
set (copied, so nothing here touches evals/golden/, corpus/ or style/ of the repository). Two roots:

* ``small_root``: the fixture corpus as is (8 train posts -> small-corpus mode, oracle = leave-one-out over the
  train posts, lineup pool = train), plus one frozen drift item; every judge action of a ``--scope all`` pass 1 is
  answered by the fake judges below and collected;
* ``heldout_root``: the same corpus with the small-corpus thresholds lowered so the 4 heldout posts are the oracle.

Fake judges write files in the exact shapes ``judge_io.validate`` / ``lineup.score`` accept, with verbatim quotes,
nonces and the rubric version under test, so pass 2 exercises the real validators.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import common  # noqa: E402
import health_run  # noqa: E402
import profile_stats  # noqa: E402
import status  # noqa: E402
import stylometry  # noqa: E402

PROJECT = TOOLS.parent
FIXTURE_CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"
DATE = "2026-09-17"
RUN = f"eval_{DATE}"
LENSES = ["reader", "voice", "comedy", "persona"]
DRIFT_TEXT = common.split_front_matter((PROJECT / "evals" / "golden" / "positives" / "p6_eval_suite.md").read_text(encoding="utf-8"))[1].rstrip("\n")
DRIFT_BASELINE = {"clarity": 4, "substance": 4, "hook": 4, "regret_risk": 4, "reply_worthiness": 4, "level_and_move": 4,
                  "not_ai": 4, "platform_register": 4, "humor": 4, "uniqueness": 4, "emotion": 4}


# --------------------------------------------------------------------------- scratch roots

def build_root(dst: Path, heldout: bool = False, drift: bool = False) -> Path:
    shutil.copytree(FIXTURE_CORPUS, dst / "corpus")
    (dst / "config").mkdir(parents=True)
    cfg = (PROJECT / "config" / "postsmith.yaml").read_text(encoding="utf-8")
    if heldout:  # 8 train posts must not count as a small corpus, so the heldout split is the oracle
        cfg = cfg.replace("small_corpus_max_posts: 24", "small_corpus_max_posts: 4")
        cfg = cfg.replace("small_corpus_min_per_platform: 6", "small_corpus_min_per_platform: 1")
    (dst / "config" / "postsmith.yaml").write_text(cfg, encoding="utf-8")
    (dst / "style").mkdir()
    shutil.copy(PROJECT / "style" / "lexicon.yaml", dst / "style" / "lexicon.yaml")
    shutil.copytree(PROJECT / "evals" / "rubric" / "v1", dst / "evals" / "rubric" / "v1")
    (dst / "evals" / "rubric" / "current").symlink_to("v1")
    shutil.copytree(PROJECT / "evals" / "golden", dst / "evals" / "golden")
    (dst / "pyproject.toml").write_text('[project]\nname = "health-root"\nversion = "0"\n', encoding="utf-8")
    if drift:
        d = dst / "evals" / "golden" / "drift"
        common.write_front_matter_file(d / "2026-09-01_r1-w1-li.md",
                                       {"platform": "linkedin", "cid": "r1-w1-li", "run": "2026-09-01_eval-suite", "rated": True,
                                        "user_score": 4, "frozen_at": "2026-09-01", "rubric_version_at_freeze": "v1"}, DRIFT_TEXT)
        common.write_json(d / "2026-09-01_r1-w1-li.baseline.json", {"rubric_version": "v1", "dimensions": DRIFT_BASELINE, "tier0_flags": []})
    with common.use_root(dst):
        stylometry.run_corpus()
        lexicon, patterns = stylometry.load_optional_lexicon_patterns()
        profile_stats.write_profile(profile_stats.build_profile(common.load_config(), lexicon, patterns))
    assert common.ROOT == PROJECT
    return dst


@pytest.fixture(scope="module")
def small_root(tmp_path_factory) -> Path:
    return build_root(tmp_path_factory.mktemp("health-small") / "root", heldout=False, drift=True)


@pytest.fixture(scope="module")
def heldout_root(tmp_path_factory) -> Path:
    return build_root(tmp_path_factory.mktemp("health-heldout") / "root", heldout=True)


@pytest.fixture(scope="module")
def pass1(small_root: Path) -> dict:
    return health_run.run(scope="all", root=small_root, date=DATE)


def state_of(root: Path, run: str = RUN) -> dict:
    return json.loads((root / "drafts" / run / "health.json").read_text(encoding="utf-8"))


def read(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def write(root: Path, rel: str, doc) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- fake judges

def _quote(text: str) -> str | None:
    for ln in text.splitlines():
        if ln.strip():
            return " ".join(ln.split()[:6])
    return None


def _dim(score: int | None, quote: str | None, na_reason: str | None = None) -> dict:
    if na_reason or quote is None:
        return {"na": True, "score": None, "pre_step": na_reason or "empty post: nothing to grade", "evidence": []}
    return {"score": score, "na": False, "pre_step": "checked", "evidence": [{"quote": quote, "why": "the span shows it"}],
            "violations": [], "suggested_fix": None, "needs_confirmation": []}


def judge_doc(kind: str, spec: dict, lens: str, dims: list[str], text: str, rubric_version: str) -> dict:
    quote = _quote(text)
    out = {"schema": "postsmith.judge/1", "rubric_version": rubric_version, "lens": lens,
           "candidate_sha": common.content_sha(text), "dimensions": {}}
    for dim in dims:
        if dim == "claims":
            out["dimensions"][dim] = {"na": True, "pre_step": "no persona in this run", "claims": []}
            continue
        if kind == "oracle" and dim in ("register_match_self", "persona_fit"):
            out["dimensions"][dim] = _dim(None, quote, na_reason="not applicable to an oracle post")
            continue
        if kind == "negative":
            if spec.get("judge_must_not_pass"):
                score = 1
            elif dim in (spec.get("judge_must_fail") or []):
                score = 2
            else:
                score = 4
        elif kind == "oracle":
            score = 4 if dim == "level_and_move" else 5
        else:
            score = 4
        out["dimensions"][dim] = _dim(score, quote)
    return out


def fake_all_judges(root: Path, run: str, rubric_version: str = "v1", hook_log: bool = True) -> dict:
    """Answer every action of a pass 1 so that pass 2 is green; returns the state."""
    state = state_of(root, run)
    thresholds = common.load_yaml(root / "evals" / "rubric" / rubric_version / "thresholds.yaml")
    lens_dims = thresholds["lenses"]
    rd = root / "drafts" / run
    rows: list[dict] = []
    for act in state["actions"]:
        cid, lens, out = act["cid"], act["lens"], act["output_path"]
        rows.append({"ts": common.now_iso(), "hook": "guard_paths", "tool": "Read", "targets": [act["prompt_file"]],
                     "decision": "allow", "reason": "allow", "agent_id": act["id"], "agent_type": act["agent"]})
        rows.append({"ts": common.now_iso(), "hook": "guard_paths", "tool": "Read", "targets": [f"evals/rubric/{rubric_version}/rubric.md"],
                     "decision": "allow", "reason": "allow", "agent_id": act["id"], "agent_type": act["agent"]})
        if act["section"] in ("lineup", "recognition", "media"):
            continue
        item = state["items"][cid]
        text = (rd / "round1" / "candidates" / f"{cid}.txt").read_text(encoding="utf-8").rstrip("\n")
        write(root, out, judge_doc(item["kind"], item.get("expected") or {}, lens, lens_dims[lens], text, rubric_version))
    for cid, info in state["lineups"].items():
        if not info.get("built"):
            continue
        key = read(root, info["key"])
        letters = sorted(key["slots"])
        for lens in health_run.LINEUP_LENSES:
            slot = key["candidate_slot_by_lens"][lens]
            other = next(x for x in letters if x != slot)
            if info["kind"] == "slop":
                pick, conf = slot, 5
            else:
                pick, conf = (slot, 3) if lens == "reader" else (other, 2)
            doc = {"schema": "postsmith.judge/1", "rubric_version": rubric_version, "lens": "lineup", "candidate_sha": None,
                   "nonce": key["nonces"][lens], "pick": pick, "confidence": conf, "tell": "even paragraphs", "quote": "x",
                   "dimensions": {"lineup": {"pick": pick, "confidence": conf, "tell": "even paragraphs", "quote": "x"}}}
            write(root, f"{key['picks_dir']}/{lens}.json", doc)
    rec = state.get("recognition")
    if rec:
        key = read(root, rec["key"])
        first = min(key["slots"])
        known = key["fillers"][key["slots"][first]]
        for lens in health_run.LINEUP_LENSES:
            answers = {letter: {"author": "unknown", "confidence": 1} for letter in key["slots"]}
            if lens in ("reader", "voice"):
                answers[first] = {"author": known["name"], "confidence": 4}
            write(root, f"{key['picks_dir']}/{lens}.json", {"nonce": key["nonces"][lens], "answers": answers})
    for m in state["media"].values():
        if not m.get("judge"):
            continue
        must = [health_run.MEDIA_SUB_ALIASES.get(s, s) for s in m["expected"].get("media_judge_must_fail") or []]
        subs = {s: (s not in must) for s in ("alt_text_alone", "does_work", "slop_screen", "executable", "factual", "capture_direction")}
        write(root, m["output"], {"schema": "postsmith.judge/1", "rubric_version": rubric_version, "lens": "media",
                                  "dimensions": {"media": {"sub_results": subs, "evidence": []}}})
    if hook_log:
        (rd / "hook.log").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return state


@pytest.fixture(scope="module")
def collected(small_root: Path, pass1: dict) -> dict:
    fake_all_judges(small_root, RUN)
    saved = os.environ.get("POSTSMITH_HOOK_LOG")
    os.environ["POSTSMITH_HOOK_LOG"] = f"drafts/{RUN}/hook.log"
    try:
        return health_run.run(scope="all", root=small_root, date=DATE, collect=True, write=True)
    finally:
        if saved is None:
            os.environ.pop("POSTSMITH_HOOK_LOG", None)
        else:
            os.environ["POSTSMITH_HOOK_LOG"] = saved


def recollect(root: Path, **kw) -> dict:
    saved = os.environ.get("POSTSMITH_HOOK_LOG")
    kw = {"date": DATE, **kw}
    os.environ["POSTSMITH_HOOK_LOG"] = f"drafts/eval_{kw['date']}/hook.log"
    try:
        return health_run.run(scope="all", root=root, collect=True, **kw)
    finally:
        if saved is None:
            os.environ.pop("POSTSMITH_HOOK_LOG", None)
        else:
            os.environ["POSTSMITH_HOOK_LOG"] = saved


# --------------------------------------------------------------------------- pass 1: deterministic scope

def test_pass1_deterministic_sections_on_small_corpus(small_root: Path, pass1: dict):
    assert pass1["ok"] is True and pass1["scope"] == "all" and pass1["rubric_version"] == "v1"
    assert pass1["small_corpus_mode"] is True and pass1["oracle_source"] == "train_leave_one_out"
    s = pass1["sections"]
    for name in ("negatives_tier0", "positives_tier0", "oracle_tier0", "media_check"):
        assert s[name]["state"] == "green", (name, [r for r in s[name]["rows"] if not r["ok"]])
    assert s["negatives_tier0"]["n"] == 15 and s["positives_tier0"]["n"] == 9 and s["media_check"]["n"] == 4
    assert s["oracle_tier0"]["n"] == 8 and {r["label"] for r in s["oracle_tier0"]["rows"]} == {
        "okonkwo_001", "okonkwo_002", "okonkwo_004", "vieira_001", "vieira_002", "vieira_004", "kessler_001", "kessler_002"}
    assert all(r["lens_scope"] == "corpus" for r in s["oracle_tier0"]["rows"])  # no author has 6 train posts
    assert s["anchors"]["state"] == "green" and s["anchors"]["n"] == 0  # every v1 strong anchor is pending
    assert s["judge_sanity"]["state"] == "skipped" and s["judge_sanity"]["blocking"] is False
    assert s["facts"]["state"] == "green" and s["facts"]["n"] >= 8
    # judges are pending, so the pass is not green yet, but nothing deterministic blocks
    assert pass1["green"] is False and pass1["pending"] == pass1["n_actions"] > 0 and pass1["blocking"] == []
    assert pass1["report"] is None
    assert (small_root / "drafts" / RUN / "health.json").exists()
    # nothing leaked into the repository or the real golden set
    assert not list((PROJECT / "evals" / "golden").glob("*/*.txt")) and not (PROJECT / "drafts" / RUN).exists()


def test_positive_known_false_positives_carry_override(pass1: dict):
    rows = {r["label"]: r for r in pass1["sections"]["positives_tier0"]["rows"]}
    for name in ("p2_not_a_success_story.md", "p4_hot_take_nobody_asked.md", "quoted_closer_mockery.md"):
        assert rows[name]["ok"] and "jury_override_allowed" in rows[name]["detail"], rows[name]
    assert "P2_fold" not in rows["quoted_closer_mockery.md"]["flags"]  # the word-boundary fold flag is waived


def test_actions_shape_and_counts(small_root: Path, pass1: dict):
    acts = pass1["actions"]
    assert len(acts) == 103  # 99 golden/oracle/lineup/media + 4 drift
    for a in acts:
        assert a["kind"] == "agent" and a["agent"] and a["prompt_file"] and a["output_path"] and a["cid"] and a["lens"]
        assert a["stage"] == "health" and a["depends_on"] == [] and re.fullmatch(r"a\d+", a["id"])
        assert (small_root / a["prompt_file"]).exists(), a
        assert a["prompt_file"].startswith(f"drafts/{RUN}/") and a["output_path"].startswith(f"drafts/{RUN}/")
    by = {}
    for a in acts:
        by.setdefault((a["agent"], a["section"]), 0)
        by[(a["agent"], a["section"])] += 1
    assert by[("judge-lineup", "lineup")] == 13 * 3 and by[("judge-lineup", "recognition")] == 3
    assert all(by[(f"judge-{lens}", "oracle")] == 8 for lens in LENSES)
    assert by[("media-judge", "media")] == 3  # empty_brief fails media_check, so no judge
    assert by[("judge-persona", "negatives")] == 6 and by[("judge-voice", "negatives")] == 5
    # judge paths satisfy the agents' hook globs: round1/prompts/<cid>.<lens>.md -> round1/scores/<cid>.<lens>.json
    for a in acts:
        if a["agent"].startswith("judge-") and a["agent"] != "judge-lineup":
            assert re.fullmatch(rf"drafts/{RUN}/round1/prompts/e[0-9a-f]{{8}}\.{a['lens']}\.md", a["prompt_file"]), a
            assert re.fullmatch(rf"drafts/{RUN}/round1/scores/e[0-9a-f]{{8}}\.{a['lens']}\.json", a["output_path"]), a
        elif a["agent"] == "judge-lineup":
            assert re.search(r"/tier2/lineup_[^/]+\.prompt\.md$", a["prompt_file"]) and "/tier2/lineup_" in a["output_path"] and ".picks/" in a["output_path"]
        else:
            assert re.search(r"/media/e[0-9a-f]{8}\.judge\.prompt\.md$", a["prompt_file"]) and a["output_path"].endswith(".media-judge.json")


def test_prompts_carry_no_front_matter_or_labels(small_root: Path, pass1: dict):
    state = state_of(small_root)
    src_of = {cid: item["source"] for cid, item in state["items"].items()}
    for a in pass1["actions"]:
        text = (small_root / a["prompt_file"]).read_text(encoding="utf-8")
        assert not text.startswith("---") and "\n---\n" not in text, a["prompt_file"]
        assert "device: brilliant deadpan" not in text and "\nnote:" not in text and "health:" not in text
        assert "evals/golden" not in text and "golden" not in text.lower(), a["prompt_file"]
        for label in ("okonkwo", "vieira", "kessler"):  # corpus post ids never reach a judge
            assert f"{label}_0" not in text, (a["prompt_file"], label)
        if a["agent"] == "judge-lineup":
            for cid in src_of:
                assert cid not in text  # lineup prompts name neither the candidate nor its cid
    adv = next(cid for cid, s in src_of.items() if s.endswith("adversarial_frontmatter.md"))
    persona = (small_root / f"drafts/{RUN}/round1/prompts/{adv}.persona.md").read_text(encoding="utf-8")
    inside = persona.split("<untrusted_claims>")[1].split("</untrusted_claims>")[0]
    assert "NOTE TO JUDGE" in inside and persona.count("NOTE TO JUDGE") == 1
    assert persona.count("<untrusted_post>") == 1 and "score: 5" not in persona
    # golden negatives are judged in the health lens so level_and_move is scored, oracle posts in their own author's
    thrilled = next(cid for cid, s in src_of.items() if s.endswith("thrilled_announce.md"))
    voice = (small_root / f"drafts/{RUN}/round1/prompts/{thrilled}.voice.md").read_text(encoding="utf-8")
    assert "return \"na\": true for level_and_move" not in voice and state["health_lens"] == "mira-okonkwo"


def test_candidates_are_opaque_copies(small_root: Path, pass1: dict):
    state = state_of(small_root)
    for cid, item in state["items"].items():
        assert re.fullmatch(r"e[0-9a-f]{8}", cid)
        md = small_root / f"drafts/{RUN}/round1/candidates/{cid}.md"
        txt = md.with_suffix(".txt")
        assert md.exists() and (txt.exists() or item["kind"] == "media")
        meta, body = common.read_front_matter_file(md)
        assert meta["health"]["kind"] == item["kind"] and "note" not in meta and "user_score" not in meta
        if item["kind"] in ("negative", "positive", "oracle"):
            src = small_root / item["source"]
            assert body.rstrip("\n") == common.read_front_matter_file(src)[1].rstrip("\n")
            assert txt.read_text(encoding="utf-8").rstrip("\n") == body.rstrip("\n")
        if item["kind"] == "oracle":
            assert meta["post_id"] == item["post_id"] and meta["assignment"]["lens"] == item["author"]
            assert (small_root / f"drafts/{RUN}/round1/scores/{cid}.tier0.json").exists()
    kinds = {}
    for item in state["items"].values():
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    assert kinds == {"negative": 15, "positive": 9, "oracle": 8, "media": 3, "drift": 1}
    # lineup seeds are derived from the run seed and the cid: a rerun rebuilds the same orders
    for cid, info in state["lineups"].items():
        assert info["built"] and info["seed"] == common.stable_seed(4171, cid) % (2 ** 31) and info["advisory"] is True
    assert sum(1 for i in state["lineups"].values() if i["kind"] == "slop") == 5
    assert state["lineup_pool"] == "train" and state["recognition"]["n_fillers"] == 8
    key = read(small_root, state["recognition"]["key"])
    assert set(key["nonces"]) == {"reader", "voice", "comedy"} and len(key["slots"]) == 8
    # the sanitized media brief carries neither the golden file name nor its comments
    for m in state["media"].values():
        if m.get("judge"):
            brief = (small_root / f"drafts/{RUN}/media/{m['cid']}.brief.yaml").read_text(encoding="utf-8")
            assert "golden" not in brief.lower() and not brief.lstrip().startswith("#")


def test_heldout_root_deterministic_scope_writes_report(heldout_root: Path):
    res = health_run.run(scope="deterministic", root=heldout_root, date=DATE, write=True)
    assert res["ok"] and res["green"] is True and res["pending"] == 0 and res["n_actions"] == 0 and res["blocking"] == []
    assert res["small_corpus_mode"] is False and res["oracle_source"] == "heldout"
    rows = res["sections"]["oracle_tier0"]["rows"]
    assert {r["label"] for r in rows} == {"okonkwo_003", "kessler_003", "vieira_003", "kessler_004"} and all(r["ok"] for r in rows)
    assert "negatives_judges" not in res["sections"] and "lineup" not in res["sections"]
    rp = res["report"]
    assert re.fullmatch(rf"evals/health/reports/{DATE}_[0-9a-f]{{12}}_p1\.md", rp), rp
    text = (heldout_root / rp).read_text(encoding="utf-8")
    assert "\nstatus: green\n" in text[:600] and "oracle = heldout posts" in text and "## Summary" in text
    assert res["writes"]["oracle_json"] == "evals/golden/oracle.json"
    oracle = read(heldout_root, "evals/golden/oracle.json")
    assert "Placeholder" in oracle["note"] and len(oracle["posts"]) == 4
    assert all(p["verdict"] == "pass" and p["rubric_version"] == "v1" and p["profile_version"] == 1 for p in oracle["posts"])
    # status.py reads the report name and the status line back as a green health state
    st = status.collect(heldout_root, today=dt.date.fromisoformat(DATE))
    assert st["health"]["state"] == "green" and st["health"]["latest_report"] == rp, st["health"]
    assert not (heldout_root / "drafts" / RUN / "round1" / "prompts").exists()


# --------------------------------------------------------------------------- pass 2: collect

def test_collect_green(small_root: Path, collected: dict):
    res = collected
    assert res["ok"] and res["green"] is True and res["blocking"] == [] and res["pending"] == 0, res["blocking"]
    s = res["sections"]
    expect = {"negatives_tier0": "green", "positives_tier0": "green", "oracle_tier0": "green", "anchors": "green",
              "media_check": "green", "negatives_judges": "green", "oracle_judges": "green", "rejection_rate": "green",
              "lineup": "green", "recognition": "green", "media_judge": "green", "drift": "green", "judge_sanity": "green",
              "facts": "green"}
    assert {k: v["state"] for k, v in s.items() if k in expect} == expect, {k: (v["state"], v["note"]) for k, v in s.items()}
    assert "judge_outputs" not in s
    assert s["negatives_judges"]["n"] == 9 and s["oracle_judges"]["n"] == 8 and s["oracle_judges"]["pass_rate"] == 1.0
    assert s["rejection_rate"]["rate"] == 0.0 and s["rejection_rate"]["attempted"] == 8 * 14
    assert abs(s["lineup"]["pick_rate"] - 8 / 24) < 1e-9 and s["lineup"]["slop_rate"] == 1.0 and s["lineup"]["advisory"] is True
    assert s["media_judge"]["n"] == 3 and s["drift"]["n"] >= 11 and all(r["ok"] for r in s["drift"]["rows"])
    assert s["judge_sanity"]["calls"] == 103
    assert len(res["retired_fillers"]) == 1 and res["retired_fillers"][0]["recognized_by"] == ["reader", "voice"]
    retired = read(small_root, "evals/golden/retired_fillers.json")
    assert retired["retired"][0]["post_id"] == res["retired_fillers"][0]["post_id"]
    assert res["writes"]["retired_fillers"] == "evals/golden/retired_fillers.json"
    assert res["writes"]["drift_baseline"] == "evals/golden/drift/baselines.json"
    assert read(small_root, "evals/golden/drift/baselines.json")[-1]["dimensions"]["clarity"] == 4.0
    oracle = read(small_root, "evals/golden/oracle.json")
    assert len(oracle["posts"]) == 8 and all(p["verdict"] == "pass" and p["failing_dimensions"] == [] for p in oracle["posts"])
    text = (small_root / res["report"]).read_text(encoding="utf-8")
    assert "\nstatus: green\n" in text[:600] and "leave-one-out" in text and "lineup pool train" in text
    assert status.collect(small_root, today=dt.date.fromisoformat(DATE))["health"]["state"] == "green"


def test_collect_red_when_a_negative_passes_a_judge(small_root: Path, collected: dict):
    state = state_of(small_root)
    cid = next(c for c, i in state["items"].items() if i["source"].endswith("thrilled_announce.md"))
    path = state["items"][cid]["judges"]["voice"]
    original = read(small_root, path)
    doc = json.loads(json.dumps(original))
    doc["dimensions"]["level_and_move"]["score"] = 4
    write(small_root, path, doc)
    try:
        res = recollect(small_root)
    finally:
        write(small_root, path, original)
    assert res["green"] is False
    sec = res["sections"]["negatives_judges"]
    assert sec["state"] == "red" and sec["blocking"] is True
    row = next(r for r in sec["rows"] if r["cid"] == cid)
    assert row["ok"] is False and "level_and_move: pass (score 4, threshold 3)" in row["detail"]
    assert any(b.startswith("negatives_judges") for b in res["blocking"])
    # a must-not-pass item that scores at threshold on any gating dimension is red too
    inj = next(c for c, i in state["items"].items() if i["source"].endswith("injection.md"))
    rpath = state["items"][inj]["judges"]["reader"]
    orig2 = read(small_root, rpath)
    doc2 = json.loads(json.dumps(orig2))
    doc2["dimensions"]["clarity"]["score"] = 4
    write(small_root, rpath, doc2)
    try:
        res2 = recollect(small_root)
    finally:
        write(small_root, rpath, orig2)
    row2 = next(r for r in res2["sections"]["negatives_judges"]["rows"] if r["cid"] == inj)
    assert row2["ok"] is False and "clarity passed (score 4, threshold 4)" in row2["detail"]
    assert recollect(small_root)["green"] is True  # restored


def test_collect_oracle_same_dimension_failures_block(small_root: Path, collected: dict):
    state = state_of(small_root)
    oracle = [c for c, i in state["items"].items() if i["kind"] == "oracle"][:2]
    originals = {}
    for cid in oracle:
        path = state["items"][cid]["judges"]["reader"]
        originals[path] = read(small_root, path)
        doc = json.loads(json.dumps(originals[path]))
        doc["dimensions"]["clarity"]["score"] = 2
        write(small_root, path, doc)
    try:
        res = recollect(small_root)
    finally:
        for path, doc in originals.items():
            write(small_root, path, doc)
    sec = res["sections"]["oracle_judges"]
    assert res["green"] is False and sec["state"] == "red" and sec["same_dimension_failures"] == ["clarity"]
    assert sec["pass_rate"] == 0.75 and any("block promotion" in b for b in res["blocking"])
    failing = [r for r in sec["rows"] if not r["ok"]]
    assert {r["cid"] for r in failing} == set(oracle) and all(r["failing_dimensions"] == ["clarity"] for r in failing)
    assert all(r["evidence"]["clarity"] for r in failing)
    oracle_json = read(small_root, "evals/golden/oracle.json")
    assert [p for p in oracle_json["posts"] if p["verdict"] == "fail"] == []  # not written: no --write on this collect


def test_collect_rejection_rate_and_missing_outputs(small_root: Path, collected: dict):
    state = state_of(small_root)
    oracle = [c for c, i in state["items"].items() if i["kind"] == "oracle"][:3]
    originals = {}
    for cid in oracle:  # three reader files with quotes that are not in the post: 15 of 112 dimensions rejected
        path = state["items"][cid]["judges"]["reader"]
        originals[path] = read(small_root, path)
        doc = json.loads(json.dumps(originals[path]))
        for d in doc["dimensions"].values():
            d["evidence"] = [{"quote": "this span does not appear anywhere in the post", "why": "made up"}]
        write(small_root, path, doc)
    try:
        res = recollect(small_root)
    finally:
        for path, doc in originals.items():
            write(small_root, path, doc)
    sec = res["sections"]["rejection_rate"]
    assert res["green"] is False and sec["state"] == "red" and sec["rejected"] == 15 and sec["attempted"] == 112
    assert res["sections"]["oracle_judges"]["state"] == "green"  # unscored is not a fail
    # a missing judge output blocks on its own
    act = next(a for a in state["actions"] if a["section"] == "oracle" and a["lens"] == "comedy")
    p = small_root / act["output_path"]
    backup = p.read_text(encoding="utf-8")
    p.unlink()
    try:
        res2 = recollect(small_root)
    finally:
        p.write_text(backup, encoding="utf-8")
    assert res2["green"] is False and res2["sections"]["judge_outputs"]["state"] == "red"
    row = next(r for r in res2["sections"]["oracle_judges"]["rows"] if r["cid"] == act["cid"])
    assert row["missing_lenses"] == ["comedy"] and row["ok"] is False


def test_collect_lineup_and_media_red(small_root: Path, collected: dict):
    state = state_of(small_root)
    # every judge picks the human oracle post: pick rate 100% is outside the 10-45% band
    originals = {}
    for info in state["lineups"].values():
        if info["kind"] != "oracle":
            continue
        key = read(small_root, info["key"])
        for lens in ("voice", "comedy"):
            path = f"{key['picks_dir']}/{lens}.json"
            originals[path] = read(small_root, path)
            doc = json.loads(json.dumps(originals[path]))
            doc["pick"] = key["candidate_slot_by_lens"][lens]
            doc["dimensions"]["lineup"]["pick"] = doc["pick"]
            write(small_root, path, doc)
    try:
        res = recollect(small_root)
    finally:
        for path, doc in originals.items():
            write(small_root, path, doc)
    sec = res["sections"]["lineup"]
    assert sec["state"] == "red" and sec["pick_rate"] == 1.0 and "outside" in sec["note"]
    assert sec["blocking"] is False and sec["advisory"] is True  # small-corpus lineups never block promotion
    assert res["green"] is True
    # the glowing-brain brief must fail the slop screen; a judge that lets it through is red and blocking
    m = state["media"]["glowing_brain.yaml"]
    original = read(small_root, m["output"])
    doc = json.loads(json.dumps(original))
    doc["dimensions"]["media"]["sub_results"]["slop_screen"] = True
    write(small_root, m["output"], doc)
    try:
        res2 = recollect(small_root)
    finally:
        write(small_root, m["output"], original)
    sec2 = res2["sections"]["media_judge"]
    assert res2["green"] is False and sec2["state"] == "red"
    assert next(r for r in sec2["rows"] if r["label"] == "glowing_brain.yaml")["detail"] == "slop_screen did not fail"


def test_collect_drift_move_needs_changelog(small_root: Path, collected: dict):
    state = state_of(small_root)
    cid = next(iter(state["drift"]))
    path = state["items"][cid]["judges"]["reader"]
    original = read(small_root, path)
    doc = json.loads(json.dumps(original))
    doc["dimensions"]["clarity"]["score"] = 2
    write(small_root, path, doc)
    try:
        res = recollect(small_root)
    finally:
        write(small_root, path, original)
    sec = res["sections"]["drift"]
    assert res["green"] is False and sec["state"] == "red" and sec["moved"] == ["clarity"]
    row = next(r for r in sec["rows"] if r["label"] == "clarity")
    assert row["previous"] == 4.0 and row["current"] == 2.0 and row["delta"] == -2.0 and "CHANGELOG" in sec["note"]


def test_collect_requires_the_hook_log(small_root: Path, collected: dict, monkeypatch):
    monkeypatch.delenv("POSTSMITH_HOOK_LOG", raising=False)
    res = health_run.run(scope="all", root=small_root, date=DATE, collect=True)
    sec = res["sections"]["judge_sanity"]
    assert sec["state"] == "skipped" and sec["blocking"] is True and res["green"] is False
    assert any(b.startswith("judge_sanity") for b in res["blocking"])
    monkeypatch.setenv("POSTSMITH_HOOK_LOG", f"drafts/{RUN}/hook.log")
    log = small_root / "drafts" / RUN / "hook.log"
    rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    dirty = dict(rows[0], targets=["corpus/heldout/okonkwo_003.md"], decision="block", reason="deny corpus/heldout/**")
    log.write_text("".join(json.dumps(r) + "\n" for r in rows + [dirty]), encoding="utf-8")
    try:
        res2 = health_run.run(scope="all", root=small_root, date=DATE, collect=True)
    finally:
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert res2["sections"]["judge_sanity"]["state"] == "red" and res2["green"] is False
    assert "contamination" in res2["sections"]["judge_sanity"]["rows"][0]["detail"]


# --------------------------------------------------------------------------- promotion of a new rubric version

def test_promote_refuses_on_red_and_moves_current_on_green(small_root: Path, collected: dict):
    shutil.copytree(small_root / "evals" / "rubric" / "v1", small_root / "evals" / "rubric" / "v2")
    date2 = "2026-09-18"
    run2 = f"eval_{date2}"
    res1 = health_run.run(scope="all", rubric="v2", root=small_root, date=date2)
    assert res1["rubric_version"] == "v2" and res1["pending"] == 103 and res1["blocking"] == []
    for a in res1["actions"]:
        text = (small_root / a["prompt_file"]).read_text(encoding="utf-8")
        assert "evals/rubric/current/" not in text and "evals/rubric/v2/" in text, a["prompt_file"]
        if a["agent"] not in ("judge-lineup", "media-judge"):
            assert '"rubric_version": "v2"' in text
    state = fake_all_judges(small_root, run2, rubric_version="v2")
    # one negative passes its must-fail dimension: red, so --promote refuses and current stays v1
    cid = next(c for c, i in state["items"].items() if i["source"].endswith("borrowed_bio.md"))
    path = state["items"][cid]["judges"]["persona"]
    good = read(small_root, path)
    bad = json.loads(json.dumps(good))
    bad["dimensions"]["persona_fit"]["score"] = 5
    write(small_root, path, bad)
    red = recollect(small_root, rubric="v2", date=date2, promote=True, write=True)
    assert red["green"] is False and red["promoted"] is False and "refused" in red["promote_error"]
    assert os.readlink(small_root / "evals" / "rubric" / "current") == "v1"
    assert red["report"] and (small_root / red["report"]).read_text(encoding="utf-8").count("status: red") == 1
    write(small_root, path, good)
    green = recollect(small_root, rubric="v2", date=date2, promote=True, write=True)
    assert green["green"] is True and green["promoted"] is True and green["current"] == "v2", green["blocking"]
    assert os.readlink(small_root / "evals" / "rubric" / "current") == "v2"
    changelog = (small_root / "evals" / "rubric" / "v2" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"### Promoted {date2}" in changelog and green["report"] in changelog
    # judge files were validated against v2 (rubric_version v2 is what the prompts asked for)
    assert green["sections"]["rejection_rate"]["rejected"] == 0
    # promotion needs scope all: a deterministic-only green result is refused
    det = health_run.run(scope="deterministic", rubric="v2", root=small_root, date="2026-09-19", promote=True)
    assert det["green"] is True and det["promoted"] is False and "scope all" in det["promote_error"]


def test_empty_corpus_root_skips_fixture_items(tmp_path: Path):
    """The real project before /ingest: no corpus, no profile. Fixture-derived negatives are skipped, the oracle is
    empty, the deterministic pass is still green and the report is named for profile p0."""
    root = tmp_path / "empty"
    (root / "config").mkdir(parents=True)
    shutil.copy(PROJECT / "config" / "postsmith.yaml", root / "config" / "postsmith.yaml")
    (root / "style").mkdir()
    shutil.copy(PROJECT / "style" / "lexicon.yaml", root / "style" / "lexicon.yaml")
    shutil.copytree(PROJECT / "evals" / "rubric" / "v1", root / "evals" / "rubric" / "v1")
    (root / "evals" / "rubric" / "current").symlink_to("v1")
    shutil.copytree(PROJECT / "evals" / "golden", root / "evals" / "golden")
    (root / "pyproject.toml").write_text('[project]\nname = "empty"\nversion = "0"\n', encoding="utf-8")
    res = health_run.run(scope="all", root=root, date=DATE, write=True)
    assert res["ok"] and res["profile_version"] == 0 and res["blocking"] == [] and res["green"] is False  # judges pending
    neg = res["sections"]["negatives_tier0"]
    skipped = {r["label"] for r in neg["rows"] if r.get("skipped")}
    assert neg["state"] == "green" and skipped == {"corpus_copy.md", "synonym_swap.md", "clean_paraphrase.md"}
    assert res["sections"]["oracle_tier0"]["state"] == "skipped" and res["sections"]["oracle_tier0"]["n"] == 0
    assert res["sections"]["positives_tier0"]["state"] == "green"
    agents = {a["agent"] for a in res["actions"]}
    assert "judge-lineup" not in agents and "media-judge" in agents and res["n_actions"] == 25
    assert any("not built" in n for n in res["notes"]) and any("recognition control skipped" in n for n in res["notes"])
    det = health_run.run(scope="deterministic", root=root, date=DATE, write=True)
    assert det["green"] is True and re.fullmatch(rf"evals/health/reports/{DATE}_[0-9a-f]{{12}}_p0\.md", det["report"])


# --------------------------------------------------------------------------- facts, helpers, CLI

def test_stale_facts_and_config_dates(heldout_root: Path):
    cfg_text = (PROJECT / "config" / "postsmith.yaml").read_text(encoding="utf-8")
    dates = health_run._config_fact_dates(cfg_text)
    labels = [lbl for lbl, _ in dates]
    assert "platforms.linkedin.max_chars" in labels and "media.veo" in labels and all(d == "2026-09-17" for _, d in dates)
    with common.use_root(heldout_root):
        cfg = common.load_config()
        thresholds = common.load_thresholds()
        ctx = health_run.Ctx(heldout_root, cfg, "v1", "v1", heldout_root / "evals" / "rubric" / "v1", thresholds,
                             common.load_profile(), DATE, 1, "deterministic")
        fresh, days = health_run.stale_facts(ctx, dt.date(2026, 9, 17))
        stale, _ = health_run.stale_facts(ctx, dt.date(2027, 1, 1))
    assert days == 90 and all(r["ok"] for r in fresh) and len(fresh) >= 8
    assert stale and not any(r["ok"] for r in stale) and all("unverified" in r["detail"] for r in stale)


def test_item_cid_and_waivers():
    assert health_run.item_cid("negative", "evals/golden/negatives/x.md") == health_run.item_cid("negative", "evals/golden/negatives/x.md")
    assert health_run.item_cid("negative", "a") != health_run.item_cid("positive", "a")
    doc = {"cid": "e1", "checks": {"P2_fold": {"class": "flag", "pass": True, "flag": True, "evidence": []},
                                    "O2_phrases": {"class": "hard", "pass": False, "hits": [{"source": "lexicon", "author": "dana-kessler"}],
                                                   "evidence": [{"span": "x", "why": "y"}]}}}
    assert health_run.waive_p2_fold(doc) == ["P2_fold"] and doc["checks"]["P2_fold"]["flag"] is False
    assert health_run.waive_own_author_o2(doc, "mira-okonkwo") == []  # another author's phrase is a real hit
    assert health_run.waive_own_author_o2(doc, "dana-kessler") == ["O2_phrases"] and doc["checks"]["O2_phrases"]["pass"] is True
    assert health_run._sub_pass({"pass": False}) is False and health_run._sub_pass("fail") is False
    assert health_run._sub_pass(True) is True and health_run._sub_pass(None) is None
    assert health_run._recognized({"author": "Dana Kessler"}, {"author": "dana-kessler", "name": "Dana Kessler", "handle": "@danakessler"})
    assert health_run._recognized("@danakessler", {"author": "dana-kessler", "name": "Dana Kessler", "handle": "@danakessler"})
    assert not health_run._recognized("unknown", {"author": "dana-kessler", "name": "Dana Kessler"})
    assert not health_run._recognized("Mira Okonkwo", {"author": "dana-kessler", "name": "Dana Kessler"})
    assert health_run.anchor_text("line one\nline two\n\nRationale:\nbecause\n") == "line one\nline two"


def test_cli_help_and_user_errors(heldout_root: Path, tmp_path: Path):
    tool = str(TOOLS / "health_run.py")
    r = subprocess.run([sys.executable, tool, "--help"], capture_output=True, text=True, check=False)
    assert r.returncode == 0 and "--collect" in r.stdout and "--promote" in r.stdout and "--scope" in r.stdout
    for args in (["--rubric", "v9"], ["--date", "not-a-date"], ["--collect", "--date", "2031-01-01"]):
        r = subprocess.run([sys.executable, tool, *args, "--root", str(heldout_root), "--json"], capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["ok"] is False and out["error"], args
    r = subprocess.run([sys.executable, tool, "--root", str(tmp_path / "nope"), "--json"], capture_output=True, text=True, check=False)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is False
    r = subprocess.run([sys.executable, tool, "--scope", "nope"], capture_output=True, text=True, check=False)
    assert r.returncode == 2  # argparse rejects an unknown scope
    # the CLI round trip agrees with the in-process run on the deterministic sections
    r = subprocess.run([sys.executable, tool, "--scope", "deterministic", "--root", str(heldout_root), "--date", "2026-09-20", "--json"],
                       capture_output=True, text=True, check=False, cwd=str(PROJECT))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] and out["green"] is True and out["oracle_source"] == "heldout" and out["sections"]["oracle_tier0"]["n"] == 4
    assert out["report"] is None and not (PROJECT / "drafts" / "eval_2026-09-20").exists()
