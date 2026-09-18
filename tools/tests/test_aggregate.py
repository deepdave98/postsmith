"""Tests for tier0.py, judge_io.py, aggregate.py and evals/rubric/v1/thresholds.yaml.

Fixtures live under tools/tests/fixtures/aggregate/: candidates, tier0, judge, jury and merged JSON
across two rounds. Everything that writes goes to tmp_path, never into the repo.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import aggregate  # noqa: E402
import common  # noqa: E402
import judge_io  # noqa: E402
import tier0  # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures" / "aggregate"
RUN = "2026-09-17_agents-buying-domains"


# --------------------------------------------------------------------------- helpers

@pytest.fixture(scope="module")
def thresholds() -> dict:
    return common.load_thresholds()


@pytest.fixture(scope="module")
def cfg() -> dict:
    return common.load_config()


@pytest.fixture(scope="module")
def li_text() -> str:
    return common.split_front_matter((FX / "candidates" / "r1-w2-li.md").read_text(encoding="utf-8"))[1].rstrip("\n")


def load(rel: str) -> dict:
    return json.loads((FX / rel).read_text(encoding="utf-8"))


def judge_entry(name: str, text: str, thresholds: dict, cfg: dict, mutate=None, jury: bool = False,
                path: str | None = None) -> dict:
    d = load(("jury/" if jury else "judges/") + name)
    if mutate:
        mutate(d)
    if jury:
        d["jury"] = True
    return {"path": path or name, "lens": d["lens"], "data": d, "validation": judge_io.validate(d, text, thresholds, cfg)}


def all_judges(text: str, thresholds: dict, cfg: dict, **mutations) -> list[dict]:
    out = []
    for lens in ("reader", "voice", "comedy", "persona"):
        out.append(judge_entry(f"r1-w2-li.{lens}.json", text, thresholds, cfg, mutate=mutations.get(lens)))
    return out


def jury_entry(lens: str, dim: str, score: int, quote: str, text: str, thresholds: dict, cfg: dict, na: bool = False) -> dict:
    d = {"schema": "postsmith.judge/1", "rubric_version": "v1", "lens": lens, "jury": True, "candidate_sha": None,
         "dimensions": {dim: {"score": None if na else score, "na": na, "threshold": 4, "pre_step": "jury: no basis to score" if na else "jury",
                              "evidence": [] if na else [{"quote": quote, "why": "jury"}], "suggested_fix": None}}}
    return {"path": f"r1-w2-li.jury.{lens}.json", "lens": lens, "data": d, "validation": judge_io.validate(d, text, thresholds, cfg)}


def merge_li(thresholds, cfg, judges, juries=(), tier2=None, previous=None, tier0_doc=None, waived=()):
    t0 = tier0_doc or load("tier0/r1-w2-li.tier0.json")
    return aggregate.merge(RUN, t0["cid"], t0.get("round", 1), t0, judges, list(juries), tier2, previous, thresholds, cfg,
                           None, set(waived))


# =========================================================================== thresholds.yaml

def test_thresholds_cover_every_check_and_dimension(thresholds):
    checks = thresholds["checks"]
    for cid in tier0.CHECK_IDS:
        assert cid in checks, cid
        assert checks[cid]["class"] in {"hard", "soft", "flag", "advisory"}
    assert checks["P_min_words"]["class"] == "hard"
    for dim, cls, thr in [("clarity", "hard", 4), ("substance", "hard", 4), ("hook", "soft", 4), ("regret_risk", "hard", 4),
                          ("reply_worthiness", "advisory", 3), ("register_match_self", "soft", 4), ("level_and_move", "soft", 3),
                          ("not_ai", "soft", 4), ("platform_register", "soft", 4), ("humor", "soft", 4), ("uniqueness", "soft", 4),
                          ("emotion", "advisory", 4), ("persona_fit", "hard", 4)]:
        assert thresholds["dimensions"][dim]["class"] == cls, dim
        assert thresholds["dimensions"][dim]["threshold"] == thr, dim
    assert thresholds["dimensions"]["claims"]["class"] == "special"
    assert thresholds["dimensions"]["media"]["class"] == "special"
    j = thresholds["jury"]
    assert j["soft_trigger"] == "threshold_minus_1" and j["hard_trigger_score"] == 3 and j["size"] == 3
    assert j["known_false_positive_checks"] == ["P8_opener", "P10_contrast_flip", "P12_closer", "P17_lists"]
    assert set(thresholds["verdict_states"]) == {"pass", "fail", "hold", "needs_your_call", "passed_tier1_only"}
    # base-rate downgrade flags mirror the config list exactly
    downgradable = {k for k, v in checks.items() if v.get("base_rate_downgrade")}
    assert downgradable == set(common.load_config()["base_rate_downgrade"]["applies_to"])
    for never in common.load_config()["base_rate_downgrade"]["never"]:
        assert not checks[never].get("base_rate_downgrade")
    # every lens dimension has a spec
    for lens, dims in thresholds["lenses"].items():
        for d in dims:
            assert d in thresholds["dimensions"], (lens, d)


# =========================================================================== tier0.py

def test_tier0_pass_path_writes_txt_and_json(tmp_path):
    doc = tier0.run(str(FX / "candidates" / "r1-w2-li.md"), run=RUN, out_dir=str(tmp_path))
    assert doc["schema"] == "postsmith.tier0/1"
    assert doc["cid"] == "r1-w2-li" and doc["platform"] == "linkedin" and doc["round"] == 1 and doc["run"] == RUN
    assert doc["lens"] == "lara-acosta" and doc["writer"] == "post-writer-2"
    assert set(tier0.CHECK_IDS) <= set(doc["checks"])
    assert doc["checks"]["P0_schema"]["pass"] is True
    for cid, res in doc["checks"].items():
        assert res["class"] in {"hard", "soft", "flag", "advisory"}, cid
        assert isinstance(res["pass"], bool)
        assert isinstance(res["evidence"], list)
    txt = tmp_path / "candidates" / "r1-w2-li.txt"
    js = tmp_path / "scores" / "r1-w2-li.tier0.json"
    assert txt.exists() and js.exists()
    assert txt.read_text(encoding="utf-8").startswith("We killed our AI strategy last week.")
    assert "cid:" not in txt.read_text(encoding="utf-8")  # no front matter reaches judges
    assert json.loads(js.read_text(encoding="utf-8"))["cid"] == "r1-w2-li"
    assert doc["text_path"].endswith("candidates/r1-w2-li.txt")
    assert doc["candidate_sha"] == common.content_sha(txt.read_text(encoding="utf-8").rstrip("\n"))
    assert doc["chars"] == len(txt.read_text(encoding="utf-8").rstrip("\n"))
    assert doc["x_len"] is None
    assert "fold_preview" in doc and doc["fold_preview"].startswith("We killed")
    assert isinstance(doc["small_corpus_mode"], bool)


def test_tier0_x_counts_and_no_write(tmp_path):
    doc = tier0.run(str(FX / "candidates" / "r1-w2-x.md"), write=False, out_dir=str(tmp_path))
    assert doc["platform"] == "x" and doc["x_len"] is not None and doc["x_len"] <= 280
    assert doc["lens"] is None
    assert not (tmp_path / "candidates").exists() and not (tmp_path / "scores").exists()


def test_tier0_p0_schema_lists_missing_keys(tmp_path):
    doc = tier0.run(str(FX / "candidates" / "r1-w9-li.md"), write=False, out_dir=str(tmp_path))
    p0 = doc["checks"]["P0_schema"]
    assert p0["class"] == "hard" and p0["pass"] is False
    assert p0["missing"] == ["claims", "angle_sheet", "ending", "media_intent.decision"]
    assert doc["hard_fail"] is True
    assert p0["evidence"] and "angle_sheet" in p0["evidence"][0]["why"]


def test_tier0_as_golden_skips_p0_and_sets_expected_na(tmp_path):
    doc = tier0.run(str(FX / "candidates" / "golden_p2.md"), as_golden=True, write=False, out_dir=str(tmp_path))
    assert doc["checks"]["P0_schema"]["pass"] is True and doc["checks"]["P0_schema"].get("skipped") is True
    assert doc["as_golden"] is True and doc["cid"] == "golden_p2" and doc["platform"] == "linkedin"
    assert "persona_fit" in doc["expected_na"] and "register_match_self" in doc["expected_na"]


def test_tier0_every_check_comes_from_a_real_module(tmp_path):
    doc = tier0.run(str(FX / "candidates" / "r1-w2-li.md"), write=False, out_dir=str(tmp_path))
    assert set(doc["modules"]) == {"platform_check", "stylometry", "envelope_check", "ai_tells", "overlap_check"}
    assert all(v == "ok" for v in doc["modules"].values())
    for res in doc["checks"].values():
        assert "error" not in res and res["class"] in {"hard", "soft", "flag", "advisory"}
    assert doc["checks"]["P1_length"]["class"] == "hard" and doc["checks"]["O1_ngram"]["class"] == "flag"
    # E1 is advisory until a profile exists to measure against, soft after. The assertion is that tier0
    # reports a real class either way, not which of the two states the project is in.
    profiled = bool((common.load_profile() or {}).get("scopes"))
    assert doc["checks"]["E1_envelope"]["class"] == ("soft" if profiled else "advisory")


def test_tier0_missing_module_is_a_real_failure(monkeypatch, tmp_path):
    for mod in ("platform_check", "stylometry", "envelope_check", "ai_tells", "overlap_check"):
        with monkeypatch.context() as m:
            m.setattr(tier0, mod, None)
            with pytest.raises(tier0.CheckModuleError, match=mod):
                tier0.run(str(FX / "candidates" / "r1-w2-li.md"), write=False, out_dir=str(tmp_path))
    assert not (tmp_path / "scores").exists()


def test_tier0_raising_module_is_fatal(monkeypatch, tmp_path):
    class Boom:
        @staticmethod
        def run_checks(*a, **k):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(tier0, "platform_check", Boom())
    with pytest.raises(tier0.CheckModuleError, match="kaboom"):
        tier0.run(str(FX / "candidates" / "r1-w2-li.md"), out_dir=str(tmp_path))
    assert not (tmp_path / "scores").exists() and not (tmp_path / "candidates").exists()


def test_tier0_invalid_module_result_is_rejected():
    with pytest.raises(tier0.CheckModuleError, match="invalid class"):
        tier0._normalize_check("P1_length", {"class": "fatal", "pass": False}, "platform_check")
    with pytest.raises(tier0.CheckModuleError, match="non-boolean pass"):
        tier0._normalize_check("P1_length", {"class": "hard", "pass": "no"}, "platform_check")
    with pytest.raises(tier0.CheckModuleError, match="P1_length missing"):
        tier0._take_checks("platform_check", {"checks": {}}, ["P1_length"])
    with pytest.raises(tier0.CheckModuleError, match="no 'checks'"):
        tier0._take_checks("platform_check", {}, ["P1_length"])


def test_tier0_base_rate_downgrade_for_platform_and_envelope_checks(cfg):
    checks = {"P6_emoji": {"class": "hard", "pass": False, "evidence": [], "downgraded": False},
              "P14_dashes": {"class": "soft", "pass": False, "evidence": [], "downgraded": False},
              "P16_broetry": {"class": "soft", "pass": True, "evidence": [], "downgraded": False},
              "P3_hashtags": {"class": "hard", "pass": False, "evidence": [], "downgraded": False}}
    rates = {"P6_emoji": 0.5, "P14_dashes": 0.9, "P16_broetry": 0.25, "P3_hashtags": 0.9}
    out = tier0.apply_base_rate_downgrade(checks, cfg, rates)
    assert out["P6_emoji"]["class"] == "flag" and out["P6_emoji"]["class_original"] == "hard"
    assert out["P6_emoji"]["downgraded"] is True and out["P6_emoji"]["base_rate"] == 0.5
    assert out["P14_dashes"]["class"] == "advisory" and out["P14_dashes"]["class_original"] == "soft"
    assert out["P16_broetry"]["class"] == "soft" and out["P16_broetry"]["downgraded"] is False  # rate == threshold
    assert out["P3_hashtags"]["class"] == "hard" and out["P3_hashtags"]["downgraded"] is False  # never list
    tier0.apply_base_rate_downgrade(out, cfg, rates)  # idempotent
    assert out["P6_emoji"]["class"] == "flag" and out["P6_emoji"]["class_original"] == "hard"
    assert tier0.apply_base_rate_downgrade(checks, cfg, None) is checks


def test_pick_weaker_prefers_fewer_flags_then_shorter():
    a = load("tier0/r1-w2-li.tier0.json")
    b = load("tier0/r1-w3-li.tier0.json")  # has failing P10 (hard), E1 (soft), O1 (flag)
    assert tier0.count_flags(a) == 0 and tier0.count_flags(b) == 3
    assert tier0.pick_weaker(a, b)["cid"] == "r1-w3-li"
    assert tier0.pick_weaker(b, a)["cid"] == "r1-w3-li"
    c = copy.deepcopy(a); c["cid"] = "r1-w4-li"; c["chars"] = a["chars"] + 200
    assert tier0.pick_weaker(a, c)["cid"] == "r1-w4-li"  # same flags: the longer one is weaker
    assert tier0.pick_weaker(c, a)["cid"] == "r1-w4-li"


def test_tier0_cli_user_error_is_json_exit_0():
    r = subprocess.run([sys.executable, str(TOOLS / "tier0.py"), "does-not-exist.md", "--json"], capture_output=True, text=True,
                       cwd=common.ROOT, check=False)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["ok"] is False and "not found" in out["error"]


def test_tier0_cli_roundtrip(tmp_path):
    r = subprocess.run([sys.executable, str(TOOLS / "tier0.py"), str(FX / "candidates" / "r1-w2-li.md"), "--out", str(tmp_path),
                        "--run", RUN, "--json"], capture_output=True, text=True, cwd=common.ROOT, check=False)
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["cid"] == "r1-w2-li" and (tmp_path / "scores" / "r1-w2-li.tier0.json").exists()


# =========================================================================== judge_io.py

def test_validate_accepts_good_reader_file(li_text, thresholds, cfg):
    res = judge_io.validate(load("judges/r1-w2-li.reader.json"), li_text, thresholds, cfg)
    assert res["ok"] is True and res["rejected"] == []
    dims = res["normalized"]["dimensions"]
    assert set(dims) == {"clarity", "substance", "hook", "regret_risk", "reply_worthiness"}
    assert all(e["match"] == "exact" for d in dims.values() for e in d["evidence"])
    assert res["normalized"]["schema"] == "postsmith.judge/1"


def test_validate_folds_curly_quotes_and_whitespace(li_text, thresholds, cfg):
    j = load("judges/r1-w2-li.persona.json")
    j["dimensions"]["persona_fit"]["evidence"] = [{"quote": "a Notion board with 41 \"AI initiatives\".   Last Tuesday", "why": "x"}]
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert res["ok"], res["rejected"]
    assert res["normalized"]["dimensions"]["persona_fit"]["evidence"][0]["match"] == "exact"


def test_validate_fuzzy_window_accepts_near_verbatim(li_text, thresholds, cfg):
    j = load("judges/r1-w2-li.reader.json")
    j["dimensions"]["clarity"]["evidence"] = [{"quote": "One of them registred a domain in staging on Thursday, which is the most", "why": "typo"}]
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert res["ok"], res["rejected"]
    ev = res["normalized"]["dimensions"]["clarity"]["evidence"][0]
    assert ev["match"] == "fuzzy" and ev["ratio"] >= cfg["judges"]["evidence_fuzzy_ratio"]


def test_validate_rejects_fabricated_quote_and_float_score(li_text, thresholds, cfg):
    res = judge_io.validate(load("judges/r1-w2-li.comedy.bad.json"), li_text, thresholds, cfg)
    assert res["ok"] is False
    reasons = {r["dimension"]: r["reason"] for r in res["rejected"]}
    assert "uniqueness" in reasons and "verbatim" in reasons["uniqueness"]
    assert "humor" in reasons and "integer" in reasons["humor"]
    assert set(res["normalized"]["dimensions"]) == {"emotion"}  # only the accepted dimension survives


def test_validate_na_needs_no_evidence_and_scored_needs_some(li_text, thresholds, cfg):
    j = load("judges/r1-w2-li.voice.json")
    assert j["dimensions"]["register_match_self"]["na"] is True and j["dimensions"]["register_match_self"]["evidence"] == []
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert res["ok"], res["rejected"]
    j["dimensions"]["not_ai"]["evidence"] = []
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert [r["dimension"] for r in res["rejected"]] == ["not_ai"] and "no evidence" in res["rejected"][0]["reason"]


def test_validate_whole_file_rejections(li_text, thresholds, cfg):
    j = load("judges/r1-w2-li.reader.json")
    j["rubric_version"] = "v0"
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert res["ok"] is False and res["rejected"][0]["dimension"] == "*" and "rubric_version" in res["rejected"][0]["reason"]
    j["rubric_version"] = "v1"; j["lens"] = "oracle"
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert any("lens" in r["reason"] for r in res["rejected"])
    assert judge_io.validate("nope", li_text, thresholds, cfg)["ok"] is False


def test_validate_dimension_lens_membership_jury_and_rerun(li_text, thresholds, cfg):
    j = load("judges/r1-w2-li.reader.json")
    j["dimensions"]["not_ai"] = copy.deepcopy(j["dimensions"]["clarity"])
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert [r["dimension"] for r in res["rejected"]] == ["not_ai"]
    j["jury"] = True  # a jury file may score any dimension or a known-false-positive check
    j["dimensions"]["P10_contrast_flip"] = copy.deepcopy(j["dimensions"]["clarity"])
    assert judge_io.validate(j, li_text, thresholds, cfg)["ok"]
    j.pop("jury"); j.pop("P10_contrast_flip", None); j["dimensions"].pop("P10_contrast_flip")
    j["lens"] = "voice"; j["rerun_for"] = "reader"  # the voice agent rerunning reader dimensions
    j["dimensions"].pop("not_ai")
    assert judge_io.validate(j, li_text, thresholds, cfg)["ok"]


def test_validate_claims_and_missing_dimensions(li_text, thresholds, cfg):
    j = load("judges/r1-w2-li.persona.json")
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert res["ok"] and len(res["normalized"]["dimensions"]["claims"]["claims"]) == 3
    j["dimensions"]["claims"]["claims"][0]["status"] = "made_up"
    res = judge_io.validate(j, li_text, thresholds, cfg)
    assert [r["dimension"] for r in res["rejected"]] == ["claims"]
    j["dimensions"].pop("claims")
    res = judge_io.validate(j, li_text, thresholds, cfg)
    # a full judgement that drops one of its lens's dimensions is rejected for that dimension (rerun ladder)
    assert res["ok"] is False and res["normalized"]["missing"] == ["claims"]
    assert res["rejected"] == [{"dimension": "claims", "reason": "dimension missing from judge output"}]
    # jury and rerun files score only what they were asked for: never rejected for the rest of the lens
    jury = dict(j, jury=True)
    assert judge_io.validate(jury, li_text, thresholds, cfg)["ok"]
    rerun = dict(j, lens="voice", rerun_for="persona")
    assert judge_io.validate(rerun, li_text, thresholds, cfg)["ok"]


def test_validate_lineup_and_pairwise_shapes(thresholds, cfg):
    ok = {"schema": "postsmith.judge/1", "rubric_version": "v1", "lens": "lineup", "pick": "C", "confidence": 2, "tell": "tidy ending", "quote": "x"}
    assert judge_io.validate(ok, None, thresholds, cfg)["ok"]
    bad = dict(ok, pick="E", confidence=7)
    res = judge_io.validate(bad, None, thresholds, cfg)
    assert res["ok"] is False and len(res["rejected"]) == 2
    pw = {"schema": "postsmith.judge/1", "rubric_version": "v1", "lens": "pairwise", "better": 1, "better_evidence": "a", "voice": 2,
          "voice_evidence": "b", "same_post_rewritten": None, "same_skeleton_or_joke": False, "evidence": ""}
    assert judge_io.validate(pw, None, thresholds, cfg)["ok"]
    res = judge_io.validate(dict(pw, better=3, same_post_rewritten="yes"), None, thresholds, cfg)
    assert res["ok"] is False and len(res["rejected"]) == 2


def test_rerun_plan_rotation(thresholds):
    rej = [{"dimension": "hook", "reason": "no evidence"}]
    assert judge_io.rerun_plan(rej, "reader", thresholds)["rerun_lens"] == "voice"
    assert judge_io.rerun_plan(rej, "voice", thresholds)["rerun_lens"] == "comedy"
    assert judge_io.rerun_plan(rej, "comedy", thresholds)["rerun_lens"] == "reader"
    assert judge_io.rerun_plan(rej, "persona", thresholds)["rerun_lens"] == "voice"
    plan = judge_io.rerun_plan(rej, "reader", thresholds)
    assert plan["dimensions"] == ["hook"] and plan["whole_file"] is False
    whole = judge_io.rerun_plan([{"dimension": "*", "reason": "rubric_version"}], "reader", thresholds)
    assert whole["whole_file"] is True and whole["dimensions"] == thresholds["lenses"]["reader"]
    assert judge_io.rerun_plan(rej, "reader")["rerun_lens"] == "voice"  # no thresholds: built-in rotation


def test_judge_io_cli(tmp_path):
    r = subprocess.run([sys.executable, str(TOOLS / "judge_io.py"), "validate", str(FX / "judges" / "r1-w2-li.reader.json"),
                        "--candidate", str(FX / "candidates" / "r1-w2-li.md"), "--json"], capture_output=True, text=True, cwd=common.ROOT, check=False)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is True
    r = subprocess.run([sys.executable, str(TOOLS / "judge_io.py"), "validate", "missing.json", "--candidate", "x.txt"],
                       capture_output=True, text=True, cwd=common.ROOT, check=False)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is False


# =========================================================================== aggregate.merge

def test_merge_pass_path(li_text, thresholds, cfg):
    def clean(d):
        d["dimensions"]["not_ai"]["score"] = 5
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean))
    assert m["schema"] == "postsmith.scores/2" and m["rubric_version"] == "v1" and m["cid"] == "r1-w2-li"
    v = m["verdict"]
    assert v["status"] == "pass" and v["hard_fails"] == [] and v["soft_fails"] == [] and v["flags"] == [] and v["unscored"] == []
    assert v["tier2_tested"] is False and m["jury_requests"] == [] and m["stop"] is None
    t1 = m["tier1"]
    assert t1["clarity"]["result"] == "pass" and t1["clarity"]["class"] == "hard" and t1["clarity"]["score"] == 5
    assert t1["clarity"]["judge"] == "judge-reader"
    assert t1["register_match_self"]["result"] == "na" and t1["humor"]["result"] == "pass"
    assert t1["level_and_move"]["result"] == "pass" and t1["level_and_move"]["threshold"] == 3
    assert v["advisory"]["reply_worthiness"] == 4 and v["advisory"]["emotion"] == 4
    assert m["tier2"]["claims"] and all(c["status"] == "user_provided" for c in m["tier2"]["claims"])
    assert m["judge_io"] == {"rejected": [], "na_by_rejection": [], "na_declared": [], "holds": []}


def test_soft_threshold_minus_one_requests_jury_and_holds(li_text, thresholds, cfg):
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg))  # fixture voice: not_ai = 3
    assert m["verdict"]["status"] == "hold"
    assert m["jury_requests"] == [{"dimension": "not_ai", "reason": "threshold-1", "lenses": ["comedy", "reader"], "size": 3,
                                   "needs": 2, "score": 3, "threshold": 4.0, "met": False}]
    assert m["tier1"]["not_ai"]["jury_pending"] is True and "jury:not_ai" in m["verdict"]["waiting_on"]
    # score two below threshold fails outright, no jury
    def low(d): d["dimensions"]["not_ai"]["score"] = 2
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=low))
    assert m["verdict"]["status"] == "fail" and m["verdict"]["soft_fails"] == ["not_ai"] and m["jury_requests"] == []


def test_jury_median_clears_soft_fail(li_text, thresholds, cfg):
    juries = [judge_entry("r1-w2-li.jury.comedy.json", li_text, thresholds, cfg, jury=True),
              judge_entry("r1-w2-li.jury.reader.json", li_text, thresholds, cfg, jury=True)]
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg), juries)
    row = m["tier1"]["not_ai"]
    assert row["jury"]["votes"] == [3, 4, 4] and row["jury"]["median"] == 4 and row["jury"]["lenses"] == ["original", "comedy", "reader"]
    assert row["result"] == "pass" and m["verdict"]["status"] == "pass" and m["jury_requests"][0]["met"] is True
    # jury that does not clear (3, 3, 4) -> fail, and a split of >= 2 is logged as a disagreement
    juries = [jury_entry("comedy", "not_ai", 3, "Nobody noticed.", li_text, thresholds, cfg),
              jury_entry("reader", "not_ai", 5, "Nobody noticed.", li_text, thresholds, cfg)]
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg), juries)
    assert m["tier1"]["not_ai"]["jury"]["median"] == 3 and m["verdict"]["status"] == "fail"
    assert m["tier1"]["not_ai"]["jury"]["split"] == 2 and m["disagreements"][0]["kind"] == "jury_split"


def test_hard_score_three_triggers_jury(li_text, thresholds, cfg):
    def three(d): d["dimensions"]["clarity"]["score"] = 3
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, reader=three, voice=clean))
    assert m["verdict"]["status"] == "hold"
    assert m["jury_requests"][0]["dimension"] == "clarity" and m["jury_requests"][0]["reason"] == "hard_score_3"
    juries = [jury_entry("voice", "clarity", 4, "Nobody noticed.", li_text, thresholds, cfg),
              jury_entry("comedy", "clarity", 4, "Nobody noticed.", li_text, thresholds, cfg)]
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, reader=three, voice=clean), juries)
    assert m["tier1"]["clarity"]["result"] == "pass" and m["verdict"]["status"] == "pass"


def test_hard_na_rerun_hold_jury_unscored_needs_your_call(li_text, thresholds, cfg):
    def na(d):
        d["dimensions"]["clarity"] = {"score": None, "na": True, "threshold": 4, "pre_step": "cannot judge clarity", "evidence": []}
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    # 1. hard-gate na -> rerun once with the alternate lens
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, reader=na, voice=clean))
    assert m["verdict"]["status"] == "hold" and "rerun:clarity" in m["verdict"]["waiting_on"]
    rej = m["judge_io"]["rejected"]
    assert rej == [{"file": "r1-w2-li.reader.json", "dimension": "clarity", "kind": "na",
                    "reason": "hard-gate na (needs a scored judgement)", "rerun_lens": "voice"}]
    # 2. rerun still na -> hold -> jury of three fresh judges
    rerun = judge_entry("r1-w2-li.reader.json", li_text, thresholds, cfg,
                        mutate=lambda d: (na(d), d.update(lens="voice", rerun_for="reader")), path="r1-w2-li.reader.rerun.json")
    judges = all_judges(li_text, thresholds, cfg, reader=na, voice=clean) + [rerun]
    m = merge_li(thresholds, cfg, judges)
    assert m["tier1"]["clarity"]["result"] == "hold" and m["judge_io"]["holds"] == ["clarity"]
    req = m["jury_requests"][0]
    assert req["reason"] == "hold" and req["needs"] == 3 and req["lenses"] == ["reader", "voice", "comedy"] and req["met"] is False
    assert m["verdict"]["status"] == "hold"
    # 3a. jury with real votes decides
    juries = [jury_entry(l, "clarity", s, "Nobody noticed.", li_text, thresholds, cfg) for l, s in (("reader", 4), ("voice", 5), ("comedy", 4))]
    m = merge_li(thresholds, cfg, judges, juries)
    assert m["tier1"]["clarity"]["result"] == "pass" and m["tier1"]["clarity"]["jury"]["votes"] == [4, 5, 4]
    assert m["verdict"]["status"] == "pass"
    # 3b. jury without evidence (all na) -> unscored -> needs_your_call
    juries = [jury_entry(l, "clarity", 0, "", li_text, thresholds, cfg, na=True) for l in ("reader", "voice", "comedy")]
    m = merge_li(thresholds, cfg, judges, juries)
    assert m["tier1"]["clarity"]["result"] == "unscored" and m["verdict"]["unscored"] == ["clarity"]
    assert m["verdict"]["status"] == "needs_your_call"


def test_expected_na_on_golden_items_is_na_not_hold(li_text, thresholds, cfg):
    def na(d):
        d["dimensions"]["persona_fit"] = {"score": None, "na": True, "threshold": 4, "pre_step": "no persona excerpt", "evidence": []}
        d["dimensions"]["claims"] = {"na": True, "pre_step": "no checkable claims", "claims": []}
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    t0 = load("tier0/r1-w2-li.tier0.json"); t0["expected_na"] = ["persona_fit", "claims", "register_match_self"]
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, persona=na, voice=clean), tier0_doc=t0)
    assert m["tier1"]["persona_fit"]["result"] == "na" and m["verdict"]["status"] == "pass"
    # the same na is acceptable when the dimension is waived
    t0["expected_na"] = []
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, persona=na, voice=clean), tier0_doc=t0, waived={"persona_fit"})
    assert m["tier1"]["persona_fit"]["result"] == "na" and m["verdict"]["status"] == "pass"


def test_na_by_rejection_twice_routes_to_needs_your_call(li_text, thresholds, cfg):
    def fabricate(d):
        for dim in ("hook", "reply_worthiness"):
            d["dimensions"][dim]["evidence"] = [{"quote": "this is not in the post", "why": "x"}]
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    judges = all_judges(li_text, thresholds, cfg, reader=fabricate, voice=clean)
    m = merge_li(thresholds, cfg, judges)
    assert m["verdict"]["status"] == "hold" and {r["dimension"] for r in m["judge_io"]["rejected"]} == {"hook", "reply_worthiness"}
    assert all(r["rerun_lens"] == "voice" for r in m["judge_io"]["rejected"])
    rerun = judge_entry("r1-w2-li.reader.json", li_text, thresholds, cfg,
                        mutate=lambda d: (fabricate(d), d.update(lens="voice", rerun_for="reader")), path="r1-w2-li.reader.rerun.json")
    m = merge_li(thresholds, cfg, judges + [rerun])
    assert m["judge_io"]["na_by_rejection"] == ["hook", "reply_worthiness"]
    assert m["tier1"]["hook"]["result"] == "na" and m["tier1"]["hook"]["rejections"] == 2
    assert m["verdict"]["status"] == "needs_your_call"


def test_rejected_twice_on_hard_dimension_becomes_hold(li_text, thresholds, cfg):
    def fabricate(d): d["dimensions"]["substance"]["evidence"] = [{"quote": "nowhere", "why": "x"}]
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    rerun = judge_entry("r1-w2-li.reader.json", li_text, thresholds, cfg,
                        mutate=lambda d: (fabricate(d), d.update(lens="voice", rerun_for="reader")), path="r1-w2-li.reader.rerun.json")
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, reader=fabricate, voice=clean) + [rerun])
    assert m["tier1"]["substance"]["result"] == "hold" and m["judge_io"]["holds"] == ["substance"]
    assert m["jury_requests"][0]["reason"] == "hold" and m["verdict"]["status"] == "hold"


def test_lens_free_writer_makes_level_and_move_na(li_text, thresholds, cfg):
    def clean(d):
        d["dimensions"]["not_ai"]["score"] = 5
        d["dimensions"]["level_and_move"]["score"] = 1
    t0 = load("tier0/r1-w2-li.tier0.json"); t0["lens"] = None
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0)
    assert m["tier1"]["level_and_move"]["result"] == "na" and m["tier1"]["level_and_move"]["score_ignored"] == 1
    assert m["verdict"]["status"] == "pass"


def test_tier0_hard_and_soft_fails_and_kfp_jury_override(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    t0 = load("tier0/r1-w3-li.tier0.json")  # P10 hard (known false positive), E1 soft, O1 flag
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0)
    v = m["verdict"]
    assert v["status"] == "hold"  # the P10 jury is outstanding
    assert v["hard_fails"] == ["P10_contrast_flip"] and v["soft_fails"] == ["E1_envelope"] and v["flags"] == ["O1_ngram"]
    req = next(r for r in m["jury_requests"] if r["dimension"] == "P10_contrast_flip")
    assert req["reason"] == "known_false_positive" and req["needs"] == 3
    juries = [jury_entry(l, "P10_contrast_flip", s, "The rest was a PDF.", li_text, thresholds, cfg) for l, s in (("voice", 5), ("reader", 4), ("comedy", 4))]
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), juries, tier0_doc=t0)
    assert m["tier0"]["P10_contrast_flip"]["pass"] is True and m["tier0"]["P10_contrast_flip"]["jury_override"] is True
    assert m["verdict"]["status"] == "fail" and m["verdict"]["hard_fails"] == []
    assert m["verdict"]["soft_fails"] == ["E1_envelope"] and m["verdict"]["flags"] == ["O1_ngram"]
    # a jury that confirms the tell keeps the hard fail
    juries = [jury_entry(l, "P10_contrast_flip", 2, "The rest was a PDF.", li_text, thresholds, cfg) for l in ("voice", "reader", "comedy")]
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), juries, tier0_doc=t0)
    assert m["tier0"]["P10_contrast_flip"]["pass"] is False and m["tier0"]["P10_contrast_flip"]["jury_confirmed"] is True
    assert "P10_contrast_flip" in m["verdict"]["hard_fails"]


def test_waived_flag_passes(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    t0 = load("tier0/r1-w2-li.tier0.json")
    # the shape platform_check really emits for a word-boundary cut: the hard gate passed, a flag was raised
    t0["checks"]["P2_fold"] = {"class": "flag", "pass": True, "flag": True, "downgraded": False,
                               "evidence": [{"span": "Six weeks ago we had a 14-page deck, a steering committee and a Notion board with 41", "why": "clause incomplete at 140"}]}
    assert tier0.count_flags(t0) == 1
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0)
    assert m["verdict"]["status"] == "fail" and m["verdict"]["flags"] == ["P2_fold"]
    assert m["jury_requests"] == []  # a raised flag is addressed by a rewrite or a waiver, never a jury
    md, packet = aggregate.feedback(m, {})
    assert [it["check"] for it in packet["tier0"]] == ["P2_fold"] and "P2_fold (flag)" in md
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0, waived={"P2_fold"})
    assert m["verdict"]["status"] == "pass" and m["verdict"]["flags"] == [] and m["verdict"]["waived"] == ["P2_fold"]
    assert m["tier0"]["P2_fold"]["waived"] is True
    # hard checks cannot be waived
    t0["checks"]["P7_bait"] = {"class": "hard", "pass": False, "evidence": [{"span": "Agree?", "why": "bait"}]}
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0, waived={"P2_fold", "P7_bait"})
    assert m["verdict"]["hard_fails"] == ["P7_bait"] and m["verdict"]["waived"] == ["P2_fold"]


def test_p14_never_fails_alone(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    t0 = load("tier0/r1-w2-li.tier0.json")
    t0["checks"]["P14_dashes"] = {"class": "soft", "pass": False, "evidence": [{"span": "-", "why": "dash density above envelope"}]}
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0)
    assert m["verdict"]["status"] == "pass" and m["verdict"]["advisory"]["tier0"] == ["P14_dashes"]
    assert m["tier0"]["P14_dashes"]["solo_fail_demoted"] is True
    # together with another failure it counts
    t0["checks"]["P18_hedges"] = {"class": "soft", "pass": False, "evidence": [{"span": "perhaps", "why": "hedges"}]}
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0)
    assert m["verdict"]["status"] == "fail" and set(m["verdict"]["soft_fails"]) == {"P14_dashes", "P18_hedges"}


def test_persona_only_failure_with_needs_confirmation(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    def weak(d):
        d["dimensions"]["persona_fit"]["score"] = 2
        d["dimensions"]["persona_fit"]["needs_confirmation"] = [{"claim": "6 weeks in prod", "source": "persona.can_claim#4"}]
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean, persona=weak))
    assert m["verdict"]["hard_fails"] == ["persona_fit"] and m["verdict"]["status"] == "needs_your_call"
    assert m["verdict"]["needs_confirmation"][0]["claim"] == "6 weeks in prod"
    # with another failure it is a plain fail
    def low(d): d["dimensions"]["not_ai"]["score"] = 1
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=low, persona=weak))
    assert m["verdict"]["status"] == "fail"


def test_tier2_gating(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    judges = all_judges(li_text, thresholds, cfg, voice=clean)
    good = {"lineup": {"seed": 1, "picks": [{"judge": "lineup-reader", "picked_candidate": False, "confidence": 2, "tell": "x"},
                                            {"judge": "lineup-voice", "picked_candidate": True, "confidence": 2, "tell": "too tidy ending", "quote": "The rest was a PDF."},
                                            {"judge": "lineup-comedy", "picked_candidate": False, "confidence": 3, "tell": "y"}]},
            "pairwise": {"mode": "reference", "better": {"wins": 1, "ties": 1, "losses": 0}, "same_post_rewritten": False},
            "claims": [{"text": "41 AI initiatives", "status": "verified", "source": "brief.user_detail"}],
            "media": {"decision": "none", "media_check": "na", "media_judge": "na"}}
    m = merge_li(thresholds, cfg, judges, tier2=good)
    assert m["verdict"]["status"] == "pass" and m["verdict"]["tier2_tested"] is True
    assert m["tier2"]["lineup"]["pass"] is True and m["tier2"]["paraphrase"]["pass"] is True and m["tier2"]["media"]["pass"] is True
    # lineup: two picks at confidence >= 4 fail
    bad = copy.deepcopy(good)
    bad["lineup"]["picks"][0].update(picked_candidate=True, confidence=4); bad["lineup"]["picks"][1].update(confidence=5)
    m = merge_li(thresholds, cfg, judges, tier2=bad)
    assert m["verdict"]["status"] == "fail" and m["verdict"]["hard_fails"] == ["lineup"]
    # paraphrase from any pairwise judge
    bad = copy.deepcopy(good); bad["pairwise"]["same_skeleton_or_joke"] = True
    m = merge_li(thresholds, cfg, judges, tier2=bad)
    assert m["verdict"]["hard_fails"] == ["paraphrase"]
    # wrong claim
    bad = copy.deepcopy(good); bad["claims"][0]["status"] = "wrong"
    m = merge_li(thresholds, cfg, judges, tier2=bad)
    assert m["verdict"]["hard_fails"] == ["claims"] and m["verdict"]["status"] == "fail"
    # unverifiable claim about a named entity: needs confirmation, not a fail
    nc = copy.deepcopy(good); nc["claims"][0]["status"] = "unverifiable"
    m = merge_li(thresholds, cfg, judges, tier2=nc)
    assert m["verdict"]["status"] == "pass" and m["verdict"]["needs_confirmation"][0]["from"] == "claims"
    # media fail
    bad = copy.deepcopy(good); bad["media"] = {"decision": "image", "media_check": "pass", "media_judge": "fail"}
    m = merge_li(thresholds, cfg, judges, tier2=bad)
    assert m["verdict"]["hard_fails"] == ["media"]
    # exemplar-mode pairwise with 0 wins and 0 ties is a hard gate
    bad = copy.deepcopy(good); bad["pairwise"] = {"mode": "exemplars", "better": {"wins": 0, "ties": 0, "losses": 4}}
    m = merge_li(thresholds, cfg, judges, tier2=bad)
    assert m["verdict"]["hard_fails"] == ["pairwise"]


def test_o3_flag_jury_or_pairwise(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    t0 = load("tier0/r1-w2-li.tier0.json")
    t0["checks"]["O3_skeleton"] = {"class": "flag", "pass": False, "evidence": [{"span": "We killed our AI strategy last week.", "why": "same skeleton as acosta_003"}]}
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0)
    assert m["verdict"]["status"] == "hold" and m["jury_requests"][0]["reason"] == "o3_flag"
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=t0,
                 tier2={"pairwise": {"mode": "reference", "better": {"wins": 2, "ties": 0, "losses": 0}, "same_post_rewritten": False}})
    assert m["verdict"]["status"] == "pass" and m["tier0"]["O3_skeleton"]["cleared_by"].startswith("pairwise")


# =========================================================================== stop conditions across rounds

def test_oscillation_from_contradictory_fixes(li_text, thresholds, cfg):
    prev = load("merged/r1-w2-li.merged.json")
    assert prev["verdict"]["soft_fails"] == ["not_ai"] and prev["stop"] is None
    cur = load("merged/r2-w2-li.merged.json")
    assert cur["stop"]["reason"] == "oscillation" and cur["stop"]["drop"] is False and "not_ai" in cur["stop"]["detail"]
    # rebuild round 2 from parts: opposite keywords, then an explicit contradicts field
    def r2(d):
        d["dimensions"]["not_ai"]["score"] = 2
        d["dimensions"]["not_ai"]["suggested_fix"] = "Add a longer closing line that lands the joke."
    t0 = load("tier0/r1-w2-li.tier0.json"); t0["cid"] = "r2-w2-li"; t0["round"] = 2
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=r2), previous=prev, tier0_doc=t0)
    assert m["stop"]["reason"] == "oscillation"
    def r2b(d):
        d["dimensions"]["not_ai"]["score"] = 2
        d["dimensions"]["not_ai"]["suggested_fix"] = "Move the punch word to the end of the last line."
        d["dimensions"]["not_ai"]["contradicts"] = True
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=r2b), previous=prev, tier0_doc=t0)
    assert m["stop"]["reason"] == "oscillation"
    # a compatible fix does not stop
    def r2c(d):
        d["dimensions"]["not_ai"]["score"] = 2
        d["dimensions"]["not_ai"]["suggested_fix"] = "Cut the summarising clause after the comma as well."
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=r2c), previous=prev, tier0_doc=t0)
    assert m["stop"] is None
    assert aggregate.fixes_conflict("make it shorter", "make it longer")
    assert aggregate.fixes_conflict("remove the last line", "keep the last line")
    assert not aggregate.fixes_conflict("cut the last line", "cut the first line")
    assert not aggregate.fixes_conflict(None, "anything")


def test_hard_gate_flip_is_oscillation_then_regression(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    prev = load("merged/r1-w2-li.merged.json")  # P13_specifics passed in round 1
    t0 = load("tier0/r1-w2-li.tier0.json"); t0["cid"] = "r2-w2-li"; t0["round"] = 2
    t0["checks"]["P13_specifics"] = {"class": "hard", "pass": False, "evidence": [{"span": "...", "why": "zero specifics"}]}
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), previous=prev, tier0_doc=t0)
    assert m["stop"]["reason"] == "oscillation" and "P13_specifics" in m["stop"]["detail"] and m["stop"]["drop"] is False
    assert m["counters"]["regression_events"] == [{"round": 2, "gate": "P13_specifics", "previous_round": 1}]
    # a second passed-then-failed event (a judged hard gate this time) -> regression -> drop
    m["tier0"]["P13_specifics"]["pass"] = True  # pretend round 2 ended with P13 fixed, clarity passing
    t0c = load("tier0/r1-w2-li.tier0.json"); t0c["cid"] = "r3-w2-li"; t0c["round"] = 3
    def low(d): d["dimensions"]["clarity"]["score"] = 2
    m3 = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean, reader=low), previous=m, tier0_doc=t0c)
    assert m3["stop"]["reason"] == "regression" and m3["stop"]["drop"] is True
    assert [e["gate"] for e in m3["counters"]["regression_events"]] == ["P13_specifics", "clarity"]


def test_overlap_flag_persisting_two_rewrites_drops(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    flagged = load("tier0/r1-w3-li.tier0.json"); flagged["cid"] = "r1-w3-li"
    for k in ("P10_contrast_flip", "E1_envelope"):
        flagged["checks"][k]["pass"] = True
    judges = all_judges(li_text, thresholds, cfg, voice=clean)
    m1 = merge_li(thresholds, cfg, judges, tier0_doc=flagged)
    assert m1["verdict"]["flags"] == ["O1_ngram"] and m1["counters"]["overlap_streak"]["O1_ngram"] == 1 and m1["stop"] is None
    t2 = copy.deepcopy(flagged); t2["cid"] = "r2-w3-li"; t2["round"] = 2
    m2 = merge_li(thresholds, cfg, judges, previous=m1, tier0_doc=t2)
    assert m2["counters"]["overlap_streak"]["O1_ngram"] == 2 and m2["stop"] is None
    t3 = copy.deepcopy(flagged); t3["cid"] = "r3-w3-li"; t3["round"] = 3
    m3 = merge_li(thresholds, cfg, judges, previous=m2, tier0_doc=t3)
    assert m3["stop"]["reason"] == "overlap_persistent" and m3["stop"]["drop"] is True
    # a clean rewrite resets the streak
    clean_t0 = load("tier0/r1-w2-li.tier0.json"); clean_t0["round"] = 3
    m3b = merge_li(thresholds, cfg, judges, previous=m2, tier0_doc=clean_t0)
    assert m3b["counters"]["overlap_streak"]["O1_ngram"] == 0 and m3b["stop"] is None


# =========================================================================== feedback and ranking

def test_feedback_packet_content(li_text, thresholds, cfg):
    t0 = load("tier0/r1-w3-li.tier0.json")
    judges = all_judges(li_text, thresholds, cfg)  # not_ai = 3 with a suggested fix
    juries = [jury_entry("comedy", "not_ai", 3, "Nobody noticed.", li_text, thresholds, cfg),
              jury_entry("reader", "not_ai", 3, "Nobody noticed.", li_text, thresholds, cfg)]
    # the P10 known-false-positive jury confirms the tell (median 2 < override threshold 4)
    juries += [jury_entry(l, "P10_contrast_flip", 2, "The rest was a PDF.", li_text, thresholds, cfg) for l in ("voice", "reader", "comedy")]
    tier2 = {"lineup": {"pass": True, "picks": [{"judge": "lineup-voice", "picked_candidate": True, "confidence": 4,
                                                 "tell": "too tidy ending", "quote": "The rest was a PDF."}]}}
    m = merge_li(thresholds, cfg, judges, juries, tier2=tier2, tier0_doc=t0)
    assert all(r["met"] for r in m["jury_requests"])
    meta = common.split_front_matter((FX / "candidates" / "r1-w2-li.md").read_text(encoding="utf-8"))[0]
    md, packet = aggregate.feedback(m, meta)
    assert packet["schema"] == "postsmith.feedback/1" and packet["cid"] == "r1-w3-li" and packet["verdict"] == "fail"
    assert next(i for i in packet["tier0"] if i["check"] == "P10_contrast_flip")["jury_confirmed"] is True
    assert packet["instruction"] == ("Fix these, keep everything that passed; do not change the move or the claims unless "
                                     "uniqueness or persona_fit failed.")
    assert packet["move"] == "corporate_register_for_trivial_event"
    checks = {i["check"] for i in packet["tier0"]}
    assert checks == {"P10_contrast_flip", "E1_envelope", "O1_ngram"}  # only failing checks, nothing that passed
    e1 = next(i for i in packet["tier0"] if i["check"] == "E1_envelope")
    assert e1["score"] == 0.61 and e1["out"][0] == {"feature": "line_words.median", "value": 11, "envelope": [5, 10]}
    dims = {i["dimension"] for i in packet["tier1"]}
    assert dims == {"not_ai"}
    na = packet["tier1"][0]
    assert na["suggested_fix"].startswith("Cut the last line") and na["jury_median"] == 3
    assert na["evidence"][0]["quote"].startswith("Turns out the strategy")
    assert packet["lineup_tells"] == [{"judge": "lineup-voice", "confidence": 4, "tell": "too tidy ending", "quote": "The rest was a PDF."}]
    # markdown mirrors the packet
    assert md.startswith("# Feedback for r1-w3-li")
    assert "line_words.median 11; author:lara-acosta envelope 5-10" in md
    assert "P10_contrast_flip (hard)" in md and "Turns out the strategy was the three agents. The rest was a PDF." in md
    assert "shared 6-gram with welsh_004" in md
    assert "suggested fix: Cut the last line" in md and "jury median 3" in md
    assert "lineup tell (lineup-voice, confidence 4): too tidy ending" in md
    assert md.rstrip().endswith("Fix these, keep everything that passed; do not change the move or the claims unless uniqueness or persona_fit failed.")
    assert "clarity" not in md and "humor" not in md  # passing dimensions are not in the packet


def test_feedback_with_nothing_failing(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    m = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean))
    md, packet = aggregate.feedback(m, {})
    assert packet["tier0"] == [] and packet["tier1"] == [] and "Nothing failed or flagged." in md


def test_rank_order(li_text, thresholds, cfg):
    def clean(d): d["dimensions"]["not_ai"]["score"] = 5
    def clean_low_reply(d): d["dimensions"]["reply_worthiness"]["score"] = 2
    def soft(d): d["dimensions"]["not_ai"]["score"] = 2
    a = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean)); a["cid"] = "a-pass"
    b = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean, reader=clean_low_reply)); b["cid"] = "b-pass-lowreply"
    c = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=soft)); c["cid"] = "c-soft"
    d = merge_li(thresholds, cfg, all_judges(li_text, thresholds, cfg, voice=clean), tier0_doc=load("tier0/r1-w3-li.tier0.json")); d["cid"] = "d-hard"
    assert [m["cid"] for m in aggregate.rank([d, c, b, a])] == ["a-pass", "b-pass-lowreply", "c-soft", "d-hard"]
    assert aggregate.rank_key(a) == (0, 0, -4.0, -aggregate.rank_key(a)[3] * -1)
    assert aggregate.rank_key(a)[2] == -4.0 and aggregate.rank_key(b)[2] == -2.0
    assert aggregate.rank_key(d)[0] == 1 and aggregate.rank_key(c)[1] == 1


# =========================================================================== CLI round trip

def _build_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "round1" / "candidates").mkdir(parents=True)
    (run / "round1" / "scores").mkdir(parents=True)
    (run / "round1" / "candidates" / "r1-w2-li.md").write_bytes((FX / "candidates" / "r1-w2-li.md").read_bytes())
    for lens in ("reader", "voice", "comedy", "persona"):
        (run / "round1" / "scores" / f"r1-w2-li.{lens}.json").write_bytes((FX / "judges" / f"r1-w2-li.{lens}.json").read_bytes())
    return run


def _cli(*args: str) -> dict:
    r = subprocess.run([sys.executable, str(TOOLS / "aggregate.py"), *args, "--json"], capture_output=True, text=True, cwd=common.ROOT, check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_cli_merge_feedback_rank_roundtrip(tmp_path):
    run = _build_run(tmp_path)
    r = subprocess.run([sys.executable, str(TOOLS / "tier0.py"), str(run / "round1" / "candidates" / "r1-w2-li.md"), "--run", "smoke"],
                       capture_output=True, text=True, cwd=common.ROOT, check=False)
    assert r.returncode == 0 and (run / "round1" / "scores" / "r1-w2-li.tier0.json").exists()
    m = _cli("merge", str(run), "r1-w2-li", "--round", "1")
    assert m["verdict"]["status"] == "hold" and m["jury_requests"][0]["dimension"] == "not_ai"
    assert (run / "round1" / "scores" / "r1-w2-li.merged.json").exists()
    for name in ("r1-w2-li.jury.comedy.json", "r1-w2-li.jury.reader.json"):
        (run / "round1" / "scores" / name).write_bytes((FX / "jury" / name).read_bytes())
    m = _cli("merge", str(run), "r1-w2-li", "--round", "1")
    assert m["verdict"]["status"] == "pass" and m["tier1"]["not_ai"]["jury"]["median"] == 4
    f = _cli("feedback", str(run), "r1-w2-li", "--round", "1")
    assert f["ok"] and (run / "round1" / "feedback" / "r1-w2-li.md").exists() and (run / "round1" / "feedback" / "r1-w2-li.json").exists()
    rk = _cli("rank", str(run), "--round", "1")
    assert rk["ranked"][0]["cid"] == "r1-w2-li" and rk["ranked"][0]["status"] == "pass"
    # round 2 discovers the previous merged file via lineage.rewrite_of
    (run / "round2" / "candidates").mkdir(parents=True); (run / "round2" / "scores").mkdir(parents=True)
    (run / "round2" / "candidates" / "r2-w2-li.md").write_bytes((FX / "candidates" / "r2-w2-li.md").read_bytes())
    subprocess.run([sys.executable, str(TOOLS / "tier0.py"), str(run / "round2" / "candidates" / "r2-w2-li.md")], capture_output=True, cwd=common.ROOT, check=False)
    for lens in ("reader", "voice", "comedy", "persona"):
        d = load(f"judges/r1-w2-li.{lens}.json")
        if lens == "voice":
            d["dimensions"]["not_ai"]["score"] = 2
            d["dimensions"]["not_ai"]["suggested_fix"] = "Add a longer closing line."
        (run / "round2" / "scores" / f"r2-w2-li.{lens}.json").write_text(json.dumps(d), encoding="utf-8")
    # make round 1 look like a not_ai fail with a 'cut' fix so round 2 oscillates
    m1 = json.loads((run / "round1" / "scores" / "r1-w2-li.merged.json").read_text(encoding="utf-8"))
    m1["tier1"]["not_ai"]["result"] = "fail"; m1["tier1"]["not_ai"]["suggested_fix"] = "Cut the last line."
    (run / "round1" / "scores" / "r1-w2-li.merged.json").write_text(json.dumps(m1), encoding="utf-8")
    m2 = _cli("merge", str(run), "r2-w2-li", "--round", "2")
    assert m2["stop"]["reason"] == "oscillation"


def test_cli_errors_are_json(tmp_path):
    out = _cli("merge", str(tmp_path / "nope"), "r1-w2-li", "--round", "1")
    assert out["ok"] is False and "tier0 file not found" in out["error"]
    out = _cli("feedback", str(tmp_path / "nope"), "r1-w2-li", "--round", "1")
    assert out["ok"] is False
    out = _cli("rank", str(tmp_path / "nope"), "--round", "1")
    assert out["ok"] is False
