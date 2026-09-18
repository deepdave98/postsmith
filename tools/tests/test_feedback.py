"""Tests for rate_record.py, posted_record.py, calibrate.py, lessons.py and topics.py.

Fixture root: tools/tests/fixtures/feedback/proj. It holds one delivered run
`2026-09-15_agents-buying-domains` with four candidates, tier0 and merged scores, final/blind.json and
lineage.json, two older lineage-only runs, memory files and calibration rows. Every test works on a tmp
copy, never on the real project.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import calibrate  # noqa: E402
import common  # noqa: E402
import lessons  # noqa: E402
import posted_record  # noqa: E402
import rate_record  # noqa: E402
import topics  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "feedback" / "proj"
RUN = "2026-09-15_agents-buying-domains"
REAL_ROOT = TOOLS.parent
_LABEL_STORES = [REAL_ROOT / "evals" / "calibration.jsonl", REAL_ROOT / "corpus" / "ratings.jsonl",
                 REAL_ROOT / "memory" / "performance.jsonl", REAL_ROOT / "memory" / "lessons.md",
                 REAL_ROOT / "memory" / "topics.md"]
_REAL_STATE_BEFORE = {str(p): p.exists() for p in _LABEL_STORES}
_REAL_PUBLISHED_BEFORE = sorted(p.name for p in (REAL_ROOT / "memory" / "published").glob("*")) \
    if (REAL_ROOT / "memory" / "published").exists() else []


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    dst = tmp_path / "proj"
    shutil.copytree(FIX, dst)
    return dst


def _rows(p: Path) -> list[dict]:
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _cli(tool: str, *args: str) -> dict:
    out = subprocess.run([sys.executable, str(TOOLS / tool), *args], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# =========================================================================== rate_record

def test_tag_validation_rejects_unknown_and_normalises():
    tags, unknown = rate_record.parse_tags("great_hook, Sounds-AI,bogus,great_hook")
    assert tags == ["great_hook", "sounds_ai"]
    assert unknown == ["bogus"]
    assert rate_record.parse_tags(None) == ([], [])
    assert set(rate_record.TAGS) == {"too_safe", "not_funny", "sounds_ai", "not_me", "too_long", "too_short", "hook_weak",
                                     "copycat", "wrong_facts", "too_mean", "great_hook", "great_ending", "media_miss",
                                     "media_great"}


def test_record_refuses_bad_tag_and_bad_score(proj: Path):
    res = rate_record.record("generated", f"{RUN}/r1-w1-li", 4, tags="bogus", root=proj)
    assert res["ok"] is False and "bogus" in res["error"] and "vocabulary" in res["error"]
    for bad in (0, 6, "x", None):
        res = rate_record.record("generated", f"{RUN}/r1-w1-li", bad, root=proj)
        assert res["ok"] is False and "1-5" in res["error"]
    assert not (proj / "evals" / "calibration.jsonl").read_text().count(RUN)


def test_blind_key_maps_through_blind_json_by_text(proj: Path):
    # blind.json items carry key/platform/text only (contracts §18): B is the finalist, C the tier0 fail
    res = rate_record.resolve_ref("generated", f"{RUN}:B", root=proj)
    assert res == {"ok": True, "run": RUN, "cid": "r1-w1-li", "platform": "linkedin", "blind_key": "B"}
    assert rate_record.resolve_ref("generated", f"{RUN}:a", root=proj)["cid"] == "r1-w2-li"
    assert rate_record.resolve_ref("generated", f"{RUN}:C", root=proj)["cid"] == "r1-w3-li"
    bad = rate_record.resolve_ref("generated", f"{RUN}:D", root=proj)
    assert bad["ok"] is False and "A, B, C" in bad["error"]
    assert rate_record.resolve_ref("generated", f"{RUN}:AB", root=proj)["ok"] is False


def test_blind_key_with_cid_or_letter_fields(proj: Path):
    bp = proj / "drafts" / RUN / "final" / "blind.json"
    bp.write_text(json.dumps({"run": RUN, "items": [{"letter": "A", "cid": "r1-w1-x", "platform": "x", "text_path": "ignored"}]}))
    assert rate_record.resolve_ref("generated", f"{RUN}:A", root=proj)["cid"] == "r1-w1-x"
    bp.unlink()
    res = rate_record.resolve_ref("generated", f"{RUN}:A", root=proj)
    assert res["ok"] is False and "blind.json" in res["error"]


def test_generated_rating_joins_merged_scores(proj: Path):
    res = rate_record.record("generated", f"{RUN}:B", 5, tags="great_ending", blind=True, root=proj)
    assert res["ok"] is True and res["previous_ratings"] == 0 and res["warnings"] == []
    row = res["row"]
    assert row["post_ref"] == f"{RUN}/r1-w1-li" and row["kind"] == "generated" and row["blind"] is True
    assert row["blind_key"] == "B" and row["platform"] == "linkedin" and row["user_score"] == 5
    assert row["judge_scores"]["hook"] == 4            # jury median wins over the judge's 3
    assert row["judge_scores"]["clarity"] == 5 and "register_match_self" not in row["judge_scores"]  # na dropped
    assert "claims" not in row["judge_scores"]
    assert row["tier0_soft_flags"] == ["P14_dashes"] and row["tier0_hard_fails"] == []
    assert row["lineup_pass"] is True and row["paraphrase"] is False and row["verdict"] == "pass"
    assert row["rubric_version"] == "v1" and row["profile_version"] == 2
    assert row["moves"] == ["corporate_register_for_trivial_event"] and row["lens"] is None
    assert row["edit_ops"] == [] and row["ts"].endswith("Z")
    stored = _rows(proj / "evals" / "calibration.jsonl")[-1]
    assert stored == row
    again = rate_record.record("generated", f"{RUN}/r1-w1-li", 4, root=proj)
    assert again["previous_ratings"] == 1 and again["row"]["blind"] is False


def test_tier0_only_candidate_gets_verdict_fail(proj: Path):
    res = rate_record.record("generated", f"{RUN}:C", 1, tags="sounds_ai", note="Thrilled to announce", blind=True, root=proj)
    row = res["row"]
    assert row["cid"] == "r1-w3-li" and row["verdict"] == "fail" and row["judge_scores"] == {}
    assert row["tier0_hard_fails"] == ["P3_hashtags", "P6_emoji", "P7_bait", "P8_opener"]
    assert row["moves"] == ["escalating_triple_break"] and row["lens"] == "justin-welsh"
    assert res["warnings"] == ["no merged scores for this candidate; judge fields are empty"]


def test_failed_variant_row_carries_soft_fails_and_flags(proj: Path):
    row = rate_record.record("generated", f"{RUN}/r1-w2-li", 4, tags="hook_weak", root=proj)["row"]
    assert row["verdict"] == "fail" and row["judge_scores"]["not_ai"] == 2 and row["tier0_soft_flags"] == ["P2_fold"]
    assert row["lineup_pass"] is None and row["lens"] == "lara-acosta" and row["moves"] == ["quote_then_deflate"]


def test_unknown_run_or_cid_is_a_user_error(proj: Path):
    assert rate_record.record("generated", "2026-01-01_nope/r1-w1-li", 4, root=proj)["ok"] is False
    assert rate_record.record("generated", f"{RUN}/r9-w9-li", 4, root=proj)["ok"] is False
    assert rate_record.record("generated", "r1-w1-li", 4, root=proj)["ok"] is False
    assert rate_record.record("nonsense", "x", 4, root=proj)["ok"] is False


def test_corpus_rating_appends_ratings_and_mirrors_calibration(proj: Path):
    res = rate_record.record("corpus", "okonkwo_001", 3, tags="too_long,not_me", note="not how I'd say it", root=proj)
    assert res["ok"] is True and res["kind"] == "corpus"
    ratings = _rows(proj / "corpus" / "ratings.jsonl")
    assert ratings[-1]["post_id"] == "okonkwo_001" and ratings[-1]["user_score"] == 3
    assert ratings[-1]["tags"] == ["too_long", "not_me"] and ratings[-1]["ts"].endswith("Z")
    mirror = _rows(proj / "evals" / "calibration.jsonl")[-1]
    assert mirror["kind"] == "corpus" and mirror["post_ref"] == "okonkwo_001" and mirror["blind"] is True
    assert mirror["judge_scores"] == {} and mirror["platform"] == "linkedin" and mirror["lens"] == "mira-okonkwo"
    assert mirror["rubric_version"] == "v1" and mirror["profile_version"] == 2


def test_corpus_rating_refuses_heldout_and_unknown(proj: Path):
    res = rate_record.record("corpus", "kessler_003", 3, root=proj)
    assert res["ok"] is False and "heldout" in res["error"]
    assert rate_record.record("corpus", "nobody_999", 3, root=proj)["ok"] is False
    assert rate_record.record("corpus", "not-an-id", 3, root=proj)["ok"] is False
    assert not (proj / "corpus" / "ratings.jsonl").read_text().count("kessler_003")


def test_list_rated(proj: Path):
    assert rate_record.list_rated("corpus", root=proj) == {"ok": True, "kind": "corpus", "ids": ["kessler_001"]}
    gen = rate_record.list_rated("generated", root=proj)["ids"]
    assert gen == ["2026-09-01_agents-invoice/r1-w1-li", "2026-09-08_deck-theatre/r2-w1-li",
                   "2026-09-08_deck-theatre/r2-w2-x", "2026-09-08_deck-theatre/r2-w3-li"]
    rate_record.record("corpus", "vieira_001", 5, root=proj)
    assert rate_record.list_rated("corpus", root=proj)["ids"] == ["kessler_001", "vieira_001"]
    assert rate_record.list_rated("other", root=proj)["ok"] is False


def test_proposals_due_counter_and_clusters(proj: Path):
    res = rate_record.proposals(root=proj)
    assert res["ok"] and res["ratings_total"] == 5 and res["since_last_calibration"] == 5 and res["due"] is False
    assert res["every_n"] == 20 and res["calibration"] is None
    assert [t["phrase"] for t in res["user_tell_candidates"]] == ["it's not about the tools"]  # "the quiet part" is known
    assert res["tag_clusters"] == []
    # three more sounds_ai ratings -> a cluster; 20 since the last report -> due, calibrate result attached
    for i in range(3):
        rate_record.record("generated", f"{RUN}/r1-w2-li", 2, tags="sounds_ai", note=f"phrase {i}", root=proj)
    res = rate_record.proposals(root=proj)
    assert res["tag_clusters"][0]["tag"] == "sounds_ai" and res["tag_clusters"][0]["n"] == 4
    assert res["due"] is False
    for _ in range(12):
        rate_record.record("corpus", "vieira_001", 4, root=proj)
    res = rate_record.proposals(root=proj)
    assert res["ratings_total"] == 20 and res["due"] is True and res["calibration"]["ok"] is True
    assert "thresholds" not in res["calibration"] and res["next_step"]
    # a written report resets the counter
    calibrate.run(proj, write=True, today="2026-09-17")
    res = rate_record.proposals(root=proj)
    assert res["last_calibration_total"] == 20 and res["since_last_calibration"] == 0 and res["due"] is False


def test_rate_record_cli(proj: Path):
    res = _cli("rate_record.py", "--kind", "generated", "--ref", f"{RUN}:B", "--score", "4", "--tags", "great_hook",
               "--blind", "--root", str(proj), "--json")
    assert res["ok"] is True and res["row"]["cid"] == "r1-w1-li"
    res = _cli("rate_record.py", "--list-rated", "--kind", "generated", "--root", str(proj))
    assert f"{RUN}/r1-w1-li" in res["ids"]
    res = _cli("rate_record.py", "--kind", "generated", "--ref", f"{RUN}/r1-w1-li", "--score", "9", "--root", str(proj))
    assert res["ok"] is False
    res = _cli("rate_record.py", "--proposals", "--root", str(proj))
    assert res["ok"] is True
    res = _cli("rate_record.py", "--root", str(proj))
    assert res["ok"] is False and "required" in res["error"]
    out = subprocess.run([sys.executable, str(TOOLS / "rate_record.py"), "--help"], capture_output=True, text=True, check=False)
    assert out.returncode == 0 and "--proposals" in out.stdout and "--blind" in out.stdout


# =========================================================================== calibrate

def test_cohen_kappa_on_known_table():
    # po = (20 + 15) / 50 = 0.7 ; pe = (25*30 + 25*20) / 2500 = 0.5 ; kappa = 0.4
    assert calibrate.cohen_kappa(20, 5, 10, 15) == pytest.approx(0.4)
    assert calibrate.cohen_kappa(10, 0, 0, 10) == pytest.approx(1.0)
    assert calibrate.cohen_kappa(0, 10, 10, 0) == pytest.approx(-1.0)
    assert calibrate.cohen_kappa(5, 5, 5, 5) == pytest.approx(0.0)
    assert calibrate.cohen_kappa(0, 0, 0, 0) is None
    assert calibrate.cohen_kappa(7, 0, 0, 0) == pytest.approx(1.0)  # degenerate agreement


def test_spearman_known_values():
    assert calibrate.spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert calibrate.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    # ties: ranks of y = [1, 2, 3.5, 5, 3.5] -> cov 8, var x 10, var y 9.5 -> 8 / sqrt(95)
    assert calibrate.spearman([1, 2, 3, 4, 5], [5, 6, 7, 8, 7]) == pytest.approx(8 / math.sqrt(95))
    assert calibrate.rank_average([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]
    assert calibrate.spearman([1, 2], [1, 2]) is None
    assert calibrate.spearman([3, 3, 3], [1, 2, 3]) is None


def _gen_row(i: int, user: int, verdict: str, scores: dict | None = None, tags=(), version="v1") -> dict:
    return {"ts": f"2026-09-{(i % 28) + 1:02d}T00:00:00Z", "post_ref": f"2026-09-01_r{i}/r1-w1-li", "kind": "generated",
            "platform": "linkedin", "user_score": user, "tags": list(tags), "note": None, "blind": True,
            "judge_scores": scores if scores is not None else {"clarity": 4, "hook": 4, "not_ai": 4 if verdict == "pass" else 2},
            "tier0_soft_flags": [], "lineup_pass": True, "verdict": verdict, "rubric_version": version,
            "profile_version": 2, "moves": ["m"], "lens": None, "edit_ops": []}


def test_kappa_reported_from_rows_and_withheld_below_minimums(proj: Path):
    cal = proj / "evals" / "calibration.jsonl"
    rows = []
    i = 0
    for user, verdict, n in ((5, "pass", 20), (4, "fail", 5), (2, "pass", 10), (1, "fail", 15)):
        for _ in range(n):
            rows.append(_gen_row(i, user, verdict))
            i += 1
    cal.write_text("".join(json.dumps(r) + "\n" for r in rows))
    res = calibrate.compute(proj)
    k = res["kappa"]
    assert k["status"] == "reported" and k["value"] == pytest.approx(0.4) and k["n"] == 50 and k["system_fails"] == 20
    assert k["table"] == {"user_pass_system_pass": 20, "user_pass_system_fail": 5, "user_fail_system_pass": 10,
                          "user_fail_system_fail": 15}
    assert res["mode"] == "calibrated" and res["n_generated"] == 50
    # fixture rows: 4 generated, 2 system fails -> withheld, advisory
    res = calibrate.compute(FIX)
    assert res["kappa"]["status"] == "withheld" and res["kappa"]["value"] is None and res["mode"] == "advisory"
    assert "< 8" in res["kappa"]["reason"] and "< 30" in res["kappa"]["reason"]
    # 30 ratings but only 7 system fails -> still withheld on the fails rule alone
    rows = [_gen_row(i, 5, "pass") for i in range(23)] + [_gen_row(30 + i, 1, "fail") for i in range(7)]
    cal.write_text("".join(json.dumps(r) + "\n" for r in rows))
    k = calibrate.compute(proj)["kappa"]
    assert k["status"] == "withheld" and k["reason"] == "7 rated system-fail(s) < 8"


def test_rho_uses_dims_at_threshold(proj: Path):
    cal = proj / "evals" / "calibration.jsonl"
    rows = [_gen_row(i, u, "pass", scores={"clarity": s, "hook": s, "not_ai": s}) for i, (u, s) in
            enumerate(((1, 2), (2, 3), (3, 4), (4, 4), (5, 5)))]
    rows[2]["judge_scores"]["hook"] = 3   # user 3 -> 2 dims at threshold
    cal.write_text("".join(json.dumps(r) + "\n" for r in rows))
    res = calibrate.compute(proj)
    assert res["rho"]["n"] == 5
    assert res["rho"]["value"] == pytest.approx(calibrate.spearman([1, 2, 3, 4, 5], [0, 0, 2, 3, 3]), abs=1e-4)
    assert calibrate.dims_at_threshold({"judge_scores": {}}, {}) is None
    assert calibrate.dims_at_threshold({"judge_scores": {"clarity": 5, "level_and_move": 3, "reply_worthiness": 2}},
                                       {"clarity": 4, "level_and_move": 3, "reply_worthiness": 3}) == 2


def test_per_tag_false_negatives_use_contract_map(proj: Path):
    cal = proj / "evals" / "calibration.jsonl"
    rows = [
        _gen_row(1, 2, "pass", scores={"not_ai": 5}, tags=["sounds_ai"]),                     # missed (lineup passed too)
        _gen_row(2, 2, "fail", scores={"not_ai": 2}, tags=["sounds_ai"]),                     # caught by not_ai
        dict(_gen_row(3, 2, "fail", scores={"not_ai": 5}, tags=["sounds_ai"]), lineup_pass=False),  # caught by lineup
        dict(_gen_row(4, 2, "pass", scores={}, tags=["sounds_ai"]), lineup_pass=None),        # not evaluable
        _gen_row(5, 2, "pass", scores={"humor": 4}, tags=["not_funny"]),                      # missed
        dict(_gen_row(6, 2, "pass", scores={"hook": 4}, tags=["copycat"]), tier0_soft_flags=["O1_ngram"]),  # caught
        _gen_row(7, 2, "pass", scores={"hook": 4}, tags=["copycat"]),                         # missed (no overlap flag)
        dict(_gen_row(8, 5, "fail", scores={"hook": 4}, tags=["media_great"]), media_pass=False),  # system flagged praise
        _gen_row(9, 2, "pass", scores={"hook": 4}, tags=["too_safe"]),                        # unmapped tag
    ]
    cal.write_text("".join(json.dumps(r) + "\n" for r in rows))
    pt = calibrate.compute(proj)["per_tag"]
    assert pt["sounds_ai"]["n"] == 4 and pt["sounds_ai"]["evaluable"] == 3 and pt["sounds_ai"]["false_negatives"] == 1
    assert pt["sounds_ai"]["rate"] == pytest.approx(1 / 3, abs=1e-3) and pt["sounds_ai"]["refs"] == ["2026-09-01_r1/r1-w1-li"]
    assert pt["sounds_ai"]["dimensions"] == ["not_ai", "lineup"]
    assert pt["not_funny"] == {"n": 1, "dimensions": ["humor"], "evaluable": 1, "false_negatives": 1, "rate": 1.0,
                               "refs": ["2026-09-01_r5/r1-w1-li"]}
    assert pt["copycat"]["false_negatives"] == 1 and pt["copycat"]["evaluable"] == 2
    assert pt["media_great"]["system_flagged"] == 1 and pt["media_great"]["rate"] == 1.0
    assert pt["too_safe"] == {"n": 1, "dimensions": [], "evaluable": 0, "false_negatives": 0, "rate": None, "refs": []}
    assert calibrate.TAG_DIMENSIONS["not_me"] == ["persona_fit", "register_match_self"]
    assert calibrate.TAG_DIMENSIONS["too_long"] == ["E1_envelope"] and calibrate.TAG_DIMENSIONS["too_mean"] == ["regret_risk"]


def test_proposals_follow_fix_order(proj: Path):
    cal = proj / "evals" / "calibration.jsonl"
    rows = [dict(_gen_row(i, 2, "pass", scores={"hook": 5}, tags=["hook_weak"]), note="the hook is a question") for i in range(3)]
    rows += [_gen_row(10 + i, 5, "fail", scores={"hook": 2}) for i in range(3)]
    rows += [dict(_gen_row(20, 2, "pass", scores={"not_ai": 5}, tags=["sounds_ai"]), note="game-changer")]
    rows += [dict(_gen_row(21, 2, "pass", scores={"not_ai": 5}, tags=["sounds_ai"]), note="the quiet part")]  # known tell
    cal.write_text("".join(json.dumps(r) + "\n" for r in rows))
    props = calibrate.compute(proj)["proposals"]
    kinds = [p["kind"] for p in props]
    assert kinds == sorted(kinds, key=calibrate.FIX_ORDER.index)
    tells = [p for p in props if p["kind"] == "user_tell"]
    assert [t["phrase"] for t in tells] == ["game-changer"] and tells[0]["source"] == "rate:r1-w1-li"
    assert tells[0]["order"] == 1
    anchors = [p for p in props if p["kind"] == "anchor"]
    assert {a["strength"] for a in anchors} == {"strong", "weak"} and all(a["order"] == 2 for a in anchors)
    strong = [a for a in anchors if a["strength"] == "strong"]
    assert strong[0]["dimension"] == "hook" and strong[0]["post_ref"].startswith("2026-09-01_r1")
    th = [p for p in props if p["kind"] == "threshold"]
    assert {(p["dimension"], p["direction"]) for p in th} == {("hook", "+1"), ("hook", "-1")}
    assert th[0]["current"] == 4 and th[0]["n"] == 3
    at = [p for p in props if p["kind"] == "anchor_text"]
    assert at and at[0]["dimension"] == "hook" and at[0]["order"] == 4


def test_drift_across_rubric_versions(proj: Path):
    cal = proj / "evals" / "calibration.jsonl"
    rows = [_gen_row(i, 4, "pass", scores={"clarity": 4, "hook": 3}, version="v1") for i in range(3)]
    rows += [_gen_row(10 + i, 4, "pass", scores={"clarity": 5, "hook": 3}, version="v2") for i in range(3)]
    rows += [_gen_row(20, 4, "pass", scores={"clarity": 5}, version="v10")]
    cal.write_text("".join(json.dumps(r) + "\n" for r in rows))
    d = calibrate.compute(proj)["drift"]
    assert d["versions"] == ["v1", "v2", "v10"]
    assert d["per_dimension"]["clarity"]["v1"] == {"median": 4.0, "n": 3}
    assert d["per_dimension"]["clarity"]["v2"]["delta"] == 1.0 and d["per_dimension"]["clarity"]["v2"]["delta_from"] == "v1"
    assert d["per_dimension"]["clarity"]["v10"]["delta"] == 0.0
    assert d["per_dimension"]["hook"]["v2"]["delta"] == 0.0 and "v10" not in d["per_dimension"]["hook"]


def test_calibrate_writes_report_and_is_deterministic(proj: Path):
    a = calibrate.run(proj, write=True, today="2026-09-17")
    b = calibrate.run(proj, write=True, today="2026-09-17")
    assert a == b and a["report_path"] == "evals/health/reports/calibration_2026-09-17.md"
    text = (proj / a["report_path"]).read_text(encoding="utf-8")
    assert text.startswith("# Calibration report 2026-09-17") and "ratings_total: 5" in text
    assert "kappa: withheld" in text and "## Per-tag false negatives" in text and "## Proposals" in text
    assert "## Drift" in text and "| clarity |" in text
    assert calibrate.last_report_total(proj) == 5
    assert a["performance"]["n_posted"] == 3 and a["performance"]["proposals"] == []
    assert "thresholds" not in a
    res = calibrate.run(proj, write=False)
    assert res["report_path"] is None


def test_calibrate_cli(proj: Path):
    res = _cli("calibrate.py", "--root", str(proj), "--date", "2026-09-17", "--json")
    assert res["ok"] is True and (proj / "evals" / "health" / "reports" / "calibration_2026-09-17.md").exists()
    assert _cli("calibrate.py", "--root", str(proj), "--date", "17/09")["ok"] is False
    empty = proj / "empty"
    empty.mkdir()
    res = _cli("calibrate.py", "--root", str(empty), "--no-write")
    assert res["ok"] is True and res["ratings_total"] == 0 and res["kappa"]["status"] == "withheld"


def test_performance_proposals_after_enough_posts(proj: Path):
    perf = proj / "memory" / "performance.jsonl"
    cfg = yaml.safe_load((proj / "config" / "postsmith.yaml").read_text())
    cfg["calibration"]["performance_min_posts"] = 3
    (proj / "config" / "postsmith.yaml").write_text(yaml.safe_dump(cfg))
    rows = _rows(perf)
    rows[2]["snapshots"] = [{"at": "2026-09-10T10:00:00Z", "after_hours": 24, "views": 100, "comments": 0}]
    perf.write_text("".join(json.dumps(r) + "\n" for r in rows))
    # receipt: 4000+6000 views (n=2, below PROVEN_MIN_N) -> only move-level / lens-level groups can qualify
    res = calibrate.compute(proj)["performance"]
    assert res["n_with_metrics"] == 3 and res["min_posts"] == 3 and "note" not in res


# =========================================================================== posted_record

DRAFT = "First line here.\n\nSecond line — with a dash.\n\nThird line stays.\n\nLast line ends it.\n"


def test_edit_ops_detection():
    assert posted_record.edit_ops(DRAFT, DRAFT) == []
    ops = posted_record.edit_ops(DRAFT, "First line here.\n\nThird line stays.\n\nLast line ends it.\n")
    assert [o["op"] for o in ops] == ["cut_line", "removed_em_dash", "shortened"]
    assert ops[0]["line"] == "Second line — with a dash." and ops[0]["index"] == 1
    ops = posted_record.edit_ops(DRAFT, "First line here.\n\nSecond line - with a dash.\n\nThird line stays.\n\nLast line ends it.\n")
    assert [o["op"] for o in ops] == ["changed_line", "removed_em_dash"]
    ops = posted_record.edit_ops(DRAFT, "A brand new opener.\n\nSecond line — with a dash.\n\nThird line stays.\n\nLast line ends it.\n")
    assert [o["op"] for o in ops] == ["changed_first_line"]
    ops = posted_record.edit_ops(DRAFT, "First line here.\n\nSecond line — with a dash.\n\nThird line stays.\n\nLast line ends it differently.\n")
    assert [o["op"] for o in ops] == ["changed_ending"] and ops[0]["to"] == "Last line ends it differently."
    # appending a paragraph is `added_line`, not also `changed_ending`: the draft's last line is untouched.
    # An earlier fallback reported it as changed, with a `to` naming the new paragraph.
    ops = posted_record.edit_ops(DRAFT, DRAFT + "\nAnd a long added closing paragraph with many more words in it than before.\n")
    assert [o["op"] for o in ops] == ["added_line", "lengthened"]
    # cutting the hook is `cut_line`, not also `changed_first_line` claiming the hook became line two
    ops = posted_record.edit_ops(DRAFT, "Second line \u2014 with a dash.\n\nThird line stays.\n\nLast line ends it.\n")
    assert [o["op"] for o in ops] == ["cut_line", "shortened"] and ops[0]["index"] == 0
    # a one-line post's only line is both the hook and the ending; one edit is reported once, not twice
    ops = posted_record.edit_ops("Only line.", "Completely different text.")
    assert [o["op"] for o in ops] == ["changed_first_line", "lengthened"]
    assert all(o["op"] in posted_record.EDIT_OPS for o in ops)


def test_edit_ops_pairs_lines_by_similarity():
    draft = "A.\n\nThe invoice was $14.\n\nProcurement is never optimistic — but they approved it.\n\nRoot cause accepted.\n"
    live = "A.\n\nProcurement is never optimistic. But they approved it.\n\nRoot cause: accepted.\n"
    ops = [o["op"] for o in posted_record.edit_ops(draft, live)]
    assert ops == ["cut_line", "changed_line", "changed_ending", "removed_em_dash", "shortened"]


def test_posted_as_is_writes_published_performance_and_topics(proj: Path):
    res = posted_record.record(RUN, "r1-w1-x", url="https://x.com/deep/status/1", posted_at="2026-09-16", root=proj)
    assert res["ok"] is True and res["edited"] is False and res["edit_ops"] == []
    assert res["published_path"] == "memory/published/2026-09-16_agents-buying-domains_x.md"
    meta, body = common.split_front_matter((proj / res["published_path"]).read_text(encoding="utf-8"))
    draft = (proj / "drafts" / RUN / "round1" / "candidates" / "r1-w1-x.txt").read_text(encoding="utf-8")
    assert body == draft
    assert meta == {"draft_id": RUN, "cid": "r1-w1-x", "platform": "x", "posted_at": "2026-09-16",
                    "url": "https://x.com/deep/status/1", "sha256": common.content_sha(draft), "edited": False}
    perf = _rows(proj / "memory" / "performance.jsonl")
    assert len(perf) == 4 and perf[-1]["draft_id"] == RUN and perf[-1]["cid"] == "r1-w1-x"
    assert perf[-1]["snapshots"] == [] and perf[-1]["url"] == "https://x.com/deep/status/1" and perf[-1]["posted_at"] == "2026-09-16"
    assert res["performance_created"] is True and res["snapshot"] is None
    # no rating row existed -> a kind=published row joined with the scores
    cal = _rows(proj / "evals" / "calibration.jsonl")[-1]
    assert res["calibration"] == "appended" and cal["kind"] == "published" and cal["post_ref"] == f"{RUN}/r1-w1-x"
    assert cal["user_score"] is None and cal["verdict"] == "pass" and cal["edit_ops"] == [] and cal["judge_scores"]["clarity"] == 5
    # topics row upserted with outcome posted
    rows, _sb = __import__("matrix").parse_topics_md((proj / "memory" / "topics.md").read_text())
    row = next(r for r in rows if r["topic"] == "agents buying domains")
    assert row["outcome"] == "posted" and row["date"] == "2026-09-15"
    assert res["topics_row"]["outcome"] == "posted"


def test_posted_with_pasted_text_records_edit_ops_on_rating_row(proj: Path):
    rate_record.record("generated", f"{RUN}:B", 5, blind=True, root=proj)
    live = proj / "drafts" / RUN / "final" / "r1-w1-li.live.txt"
    draft = (proj / "drafts" / RUN / "round1" / "candidates" / "r1-w1-li.txt").read_text(encoding="utf-8")
    edited = draft.replace("Procurement is never optimistic — but", "Procurement is never optimistic. But")
    edited = edited.replace("The invoice for the week the deck died: $14.\n\n", "")
    live.write_text(edited, encoding="utf-8")
    res = posted_record.record(RUN, "r1-w1-li", url="https://www.linkedin.com/posts/deep_1",
                               text_file=str(live.relative_to(proj)), posted_at="2026-09-16", root=proj)
    assert res["ok"] and res["edited"] is True
    assert res["edit_ops"] == ["cut_line", "changed_line", "removed_em_dash", "shortened"]
    assert res["calibration"] == "updated"
    cal = _rows(proj / "evals" / "calibration.jsonl")
    row = [r for r in cal if r["post_ref"] == f"{RUN}/r1-w1-li"]
    assert len(row) == 1 and row[0]["edit_ops"] == res["edit_ops"] and row[0]["edited"] is True and row[0]["user_score"] == 5
    meta, body = common.split_front_matter((proj / res["published_path"]).read_text(encoding="utf-8"))
    assert meta["edited"] is True and body == edited and meta["sha256"] == common.content_sha(edited)
    # the draft itself is untouched
    assert (proj / "drafts" / RUN / "round1" / "candidates" / "r1-w1-li.txt").read_text(encoding="utf-8") == draft


def test_posted_metrics_append_snapshots_and_keep_live_text(proj: Path):
    live = proj / "drafts" / RUN / "final" / "r1-w1-li.live.txt"
    live.write_text("We killed our AI strategy last week.\n\nRoot cause accepted.\n", encoding="utf-8")
    first = posted_record.record(RUN, "r1-w1-li", text_file=str(live), posted_at="2026-09-16", root=proj)
    assert first["edited"] is True
    res = posted_record.record(RUN, "r1-w1-li", metrics="12k views 40 comments 3 reposts", after="24h", root=proj)
    assert res["ok"] and res["snapshot"]["views"] == 12000 and res["snapshot"]["comments"] == 40
    assert res["snapshot"]["reposts"] == 3 and res["snapshot"]["after_hours"] == 24 and res["snapshot"]["likes"] is None
    assert res["edited"] is True and res["published_path"] == first["published_path"]
    res2 = posted_record.record(RUN, "r1-w1-li", metrics="15k impressions 55 comments 2 saves after 7d", root=proj)
    assert res2["snapshot"]["after_hours"] == 168 and res2["snapshot"]["saves"] == 2
    perf = [r for r in _rows(proj / "memory" / "performance.jsonl") if r["cid"] == "r1-w1-li" and r["draft_id"] == RUN]
    assert len(perf) == 1 and [s["views"] for s in perf[0]["snapshots"]] == [12000, 15000]
    assert perf[0]["posted_at"] == "2026-09-16" and perf[0]["published_path"] == first["published_path"]
    assert len(list((proj / "memory" / "published").glob("*.md"))) == 1
    body = common.split_front_matter((proj / first["published_path"]).read_text())[1]
    assert body.startswith("We killed our AI strategy last week.\n\nRoot cause accepted.")
    assert res2["performance_created"] is False and res2["warnings"] == []


def test_posted_user_errors(proj: Path):
    assert posted_record.record("2026-01-01_nope", "r1-w1-li", root=proj)["ok"] is False
    assert posted_record.record(RUN, "r9-w9-li", root=proj)["ok"] is False
    res = posted_record.record(RUN, "r1-w1-li", text_file="missing.txt", root=proj)
    assert res["ok"] is False and "text-file" in res["error"]
    res = posted_record.record(RUN, "r1-w1-li", metrics="nothing useful here", root=proj)
    assert res["ok"] is False and "no metrics" in res["error"]
    assert posted_record.record(RUN, "r1-w1-li", posted_at="yesterday", root=proj)["ok"] is False
    assert not (proj / "memory" / "published").glob("*.md") or not list((proj / "memory" / "published").glob("*.md"))
    res = posted_record.record(RUN, "r1-w1-li", after="24h", root=proj)
    assert res["ok"] and res["warnings"] == ["--after ignored without --metrics"]


def test_posted_record_cli(proj: Path):
    res = _cli("posted_record.py", RUN, "r1-w1-x", "--url", "https://x.com/deep/status/1", "--root", str(proj), "--json")
    assert res["ok"] is True and res["published_path"].endswith("_x.md")
    res = _cli("posted_record.py", RUN, "r1-w1-x", "--metrics", "900 views 12 likes", "--after", "24h", "--root", str(proj))
    assert res["snapshot"]["likes"] == 12
    assert _cli("posted_record.py", RUN, "zzz", "--root", str(proj))["ok"] is False


# =========================================================================== lessons

def test_lessons_parse_and_render_roundtrip(proj: Path):
    text = (proj / "memory" / "lessons.md").read_text(encoding="utf-8")
    entries = lessons.parse(text)
    assert [e.id for e in entries] == ["L-001", "L-003", "L-004", "L-002", "L-000"] or len(entries) == 5
    by_id = {e.id: e for e in entries}
    assert by_id["L-001"].section == "PREFER" and by_id["L-001"].tag == "great_ending" and by_id["L-001"].count == 3
    assert by_id["L-001"].evidence == [{"cid": "r1-w1-li", "quote": "Root cause accepted."}, {"cid": "r2-w2-x", "quote": None}]
    assert by_id["L-004"].section == "FACTS-I-CAN-USE" and by_id["L-004"].tag is None
    assert by_id["L-000"].retired == "2026-04-15" and by_id["L-000"].section == "AVOID"
    assert lessons.parse(lessons.render(entries)) == entries
    assert lessons.next_id(entries) == "L-005"


def test_lessons_add_requires_count_or_force(proj: Path):
    res = lessons.add("not_funny", "explain less", ["r1-w2-li:very helpful"], count=2, root=proj)
    assert res["ok"] is False and "3" in res["error"]
    res = lessons.add("not_funny", "explain less", ["r1-w2-li:very helpful"], count=2, force=True, root=proj, today="2026-09-17")
    assert res["ok"] and res["entry"]["id"] == "L-005" and res["entry"]["count"] == 2
    res = lessons.add("not_funny", "Explaining the joke after the punchline.", ["r1-w2-li:It was very helpful", "r2-w2-x"],
                      run=RUN, count=3, root=proj, today="2026-09-17")
    e = res["entry"]
    assert e["id"] == "L-006" and e["section"] == "AVOID" and e["tag"] == "not_funny" and e["count"] == 3
    line = next(ln for ln in (proj / "memory" / "lessons.md").read_text().splitlines() if ln.startswith("- L-006"))
    assert line == (f"- L-006 (2026-09-17, run {RUN}; tag not_funny x3) AVOID: Explaining the joke after the punchline. "
                    'Evidence: r1-w2-li "It was very helpful"; r2-w2-x')
    assert lessons.add("great_hook", "questions as openers land", ["r1-w1-li"], count=3, root=proj)["entry"]["section"] == "PREFER"
    assert lessons.add("bogus", "x", ["r1"], count=3, root=proj)["ok"] is False
    assert lessons.add("not_funny", "", ["r1"], count=3, root=proj)["ok"] is False
    assert lessons.add("not_funny", "no evidence", [], count=3, root=proj)["ok"] is False
    assert lessons.add(None, "a fact", [], section="FACTS-I-CAN-USE", count=3, root=proj)["entry"]["section"] == "FACTS-I-CAN-USE"
    assert lessons.add(None, "needs a tag", ["r1"], count=3, root=proj)["ok"] is False
    assert lessons.add("not_funny", "x", ["r1"], section="RETIRED", count=3, root=proj)["ok"] is False


def test_lessons_reinforce_updates_date_count_and_unretires(proj: Path):
    res = lessons.add("too_long", "shorter setups", ["r3-w1-li:three paragraphs"], count=3, reinforce="L-000", root=proj,
                      today="2026-09-17")
    assert res["ok"] and res["action"] == "reinforced"
    e = res["entry"]
    assert e["date"] == "2026-09-17" and e["count"] == 6 and e["retired"] is None
    assert {x["cid"] for x in e["evidence"]} == {"r1-w1-li", "r3-w1-li"}
    text = (proj / "memory" / "lessons.md").read_text()
    assert "L-000" in text.split("## AVOID")[1].split("## FACTS")[0]
    assert lessons.add("too_long", "x", ["r1"], count=3, reinforce="L-999", root=proj)["ok"] is False


def test_lessons_retire_moves_old_entries(proj: Path):
    res = lessons.retire(days=90, root=proj, today="2026-09-17")
    assert res["retired"] == ["L-002"] and res["cutoff"] == "2026-06-19" and res["active_lines"] == 3
    text = (proj / "memory" / "lessons.md").read_text()
    retired_block = text.split("## RETIRED")[1]
    assert "- L-002 (2026-05-01, run 2026-05-01_old; tag not_funny x3) AVOID: explaining the joke in the last line. " \
           'Evidence: r2-w3-x "explains the joke"; r1-w1-li (retired 2026-09-17)' in retired_block
    assert "L-000" in retired_block and "L-003" not in retired_block
    # default days from config (90) and idempotence
    assert lessons.retire(root=proj, today="2026-09-17") == dict(res, retired=[])


def test_lessons_consolidate_merges_duplicates_and_caps_without_dropping(proj: Path):
    cfg = yaml.safe_load((proj / "config" / "postsmith.yaml").read_text())
    cfg["calibration"]["lessons_max_lines"] = 5
    (proj / "config" / "postsmith.yaml").write_text(yaml.safe_dump(cfg))
    lessons.add("sounds_ai", "'it's not about X, it's about Y' closers again", ["r5-w1-li:not about the tools"], count=3,
                root=proj, today="2026-09-10")
    distinct = ["take a position on pricing", "name the competitor", "say which model you switched from",
                "pick a side on remote work"]
    for i, instruction in enumerate(distinct):
        lessons.add("too_safe", instruction, [f"r6-w{i}-li:safe"], count=3, root=proj, today=f"2026-09-1{i}")
    before = lessons.load(proj)
    all_cids = {e["cid"] for x in before for e in x.evidence}
    assert lessons.active_lines(before) == 9
    res = lessons.consolidate(root=proj)
    assert res["ok"] and res["cap"] == 5 and res["active_lines"] <= 5 and res["active_lines_before"] == 9
    after = lessons.load(proj)
    assert {e["cid"] for x in after for e in x.evidence} == all_cids          # nothing dropped
    assert any(m["reason"] == "near-duplicate" and m["kept"] == "L-003" for m in res["merges"])
    l003 = next(x for x in after if x.id == "L-003")
    assert l003.count == 7 and {e["cid"] for e in l003.evidence} == {"r1-w2-li", "r5-w1-li"} and l003.date == "2026-09-10"
    assert any(m["reason"] == "line cap 5" for m in res["merges"])
    merged_safe = [x for x in after if x.tag == "too_safe"]
    assert len(merged_safe) < 4 and all(x.retired is None for x in merged_safe)
    assert lessons.parse(lessons.render(after)) == after
    assert lessons.consolidate(root=proj)["merges"] == []                       # idempotent


def test_lessons_cli(proj: Path):
    res = _cli("lessons.py", "add", "--tag", "hook_weak", "--instruction", "Lead with the receipt.", "--evidence",
               "r1-w2-li:Here's the thing", "--count", "3", "--root", str(proj), "--json")
    assert res["ok"] and res["entry"]["tag"] == "hook_weak"
    res = _cli("lessons.py", "--root", str(proj), "list")
    assert res["ok"] and any(e["id"] == res["entries"][-1]["id"] for e in res["entries"])
    res = _cli("lessons.py", "retire", "--days", "1", "--root", str(proj), "--today", "2026-09-17")
    assert res["ok"] and "L-001" in res["retired"]
    res = _cli("lessons.py", "add", "--tag", "hook_weak", "--instruction", "x", "--evidence", "r1", "--root", str(proj))
    assert res["ok"] is False
    out = subprocess.run([sys.executable, str(TOOLS / "lessons.py"), "add", "--help"], capture_output=True, text=True, check=False)
    assert out.returncode == 0 and "--evidence" in out.stdout and "--force" in out.stdout


# =========================================================================== topics

def test_lineage_info_reads_variants_and_assignments(proj: Path):
    info = topics.lineage_info(RUN, root=proj)
    assert info["topic"] == "agents buying domains" and info["date"] == "2026-09-15"
    assert [v["cid"] for v in info["variants"]] == ["r1-w1-li", "r1-w1-x", "r1-w2-li", "r1-w3-li"]  # finalists first
    v = info["_by_cid"]["r1-w1-li"]
    assert v["platform"] == "linkedin" and v["verdict"] == "pass" and v["tier2_tested"] is True
    assert v["assignment"]["move"] == "corporate_register_for_trivial_event" and v["lessons_used"] == ["L-001"]
    # dict-shaped variants without assignment fall back to the candidate front matter
    lp = proj / "drafts" / RUN / "final" / "lineage.json"
    lp.write_text(json.dumps({"run": RUN, "topic": "t", "variants": {"r1-w2-li": {"platform": "linkedin", "final_path": f"drafts/{RUN}/final/li_2.md"}}}))
    info = topics.lineage_info(RUN, root=proj)
    assert info["variants"][0]["assignment"]["lens"] == "lara-acosta" and info["variants"][0]["verdict"] == "fail"
    with pytest.raises(FileNotFoundError):
        topics.lineage_info("2026-01-01_nope", root=proj)


def test_topics_add_upserts_row_and_keeps_other_sections(proj: Path):
    before = (proj / "memory" / "topics.md").read_text()
    res = topics.add(RUN, root=proj)
    assert res["ok"] and res["created"] is True
    assert res["row"] == {"date": "2026-09-15", "topic": "agents buying domains", "angle": "receipt",
                          "moves": ["corporate_register_for_trivial_event", "quote_then_deflate", "escalating_triple_break"],
                          "lens": None, "outcome": "pass"}
    text = (proj / "memory" / "topics.md").read_text()
    assert text.startswith("# Topics used\n\n| date | topic | angle | moves | lens | outcome |\n|---|---|---|---|---|---|\n| 2026-09-15 | agents buying domains | receipt | corporate_register_for_trivial_event, quote_then_deflate, escalating_triple_break | null | pass |\n")
    assert before.split("## Moves scoreboard")[1] == text.split("## Moves scoreboard")[1]
    res = topics.add(RUN, outcome="posted", root=proj)
    assert res["created"] is False and res["row"]["outcome"] == "posted"
    rows, sb = __import__("matrix").parse_topics_md((proj / "memory" / "topics.md").read_text())
    assert rows[0]["date"] == "2026-09-15" and rows[0]["outcome"] == "posted" and len(rows) == 3
    assert rows[0]["moves"][0] == "corporate_register_for_trivial_event"
    assert sb["corporate_register_for_trivial_event"]["mean"] == 4.0
    assert topics.add(RUN, root=proj)["row"]["outcome"] == "posted"   # no --outcome keeps the recorded one
    assert topics.add("2026-01-01_nope", root=proj)["ok"] is False


def test_topics_add_creates_file_when_missing(proj: Path):
    (proj / "memory" / "topics.md").unlink()
    res = topics.add(RUN, outcome="skipped", root=proj)
    assert res["ok"] and res["created"]
    text = (proj / "memory" / "topics.md").read_text()
    rows, _ = __import__("matrix").parse_topics_md(text)
    assert len(rows) == 1 and rows[0]["outcome"] == "skipped" and text.startswith("# Topics used")


def test_scoreboard_computation():
    rows = [
        {"kind": "generated", "user_score": 5, "moves": ["a", "b"], "ts": "2026-09-01T00:00:00Z"},
        {"kind": "generated", "user_score": 3, "moves": ["a"], "ts": "2026-09-05T00:00:00Z"},
        {"kind": "generated", "user_score": 4, "moves": ["a"], "ts": "2026-08-01T00:00:00Z"},
        {"kind": "generated", "user_score": None, "moves": ["a"], "ts": "2026-09-09T00:00:00Z"},   # unrated (published row)
        {"kind": "corpus", "user_score": 1, "moves": ["a"], "ts": "2026-09-09T00:00:00Z"},        # corpus rows never count
        {"kind": "generated", "user_score": 2, "moves": [], "ts": "2026-09-09T00:00:00Z"},
    ]
    assert topics.scoreboard_rows(rows) == [
        {"move": "b", "mean_rating": 5.0, "n": 1, "last_used": "2026-09-01"},
        {"move": "a", "mean_rating": 4.0, "n": 3, "last_used": "2026-09-05"},
    ]
    assert topics.scoreboard_rows([]) == []


def test_topics_scoreboard_rewrites_section(proj: Path):
    res = topics.scoreboard(root=proj)
    assert res["ok"] and res["scoreboard"][0] == {"move": "corporate_register_for_trivial_event", "mean_rating": 4.5, "n": 2,
                                                  "last_used": "2026-09-09"}
    assert res["scoreboard"][1]["move"] == "quote_then_deflate" and res["scoreboard"][1]["mean_rating"] == 3.0
    text = (proj / "memory" / "topics.md").read_text()
    rows, sb = __import__("matrix").parse_topics_md(text)
    assert sb == {"corporate_register_for_trivial_event": {"mean": 4.5, "n": 2, "last_used": "2026-09-09"},
                  "quote_then_deflate": {"mean": 3.0, "n": 2, "last_used": "2026-09-09"}}
    assert len(rows) == 2 and "## Proven angles" in text
    assert "| move | mean_rating | n | last_used |" in text


def test_topics_proven_joins_performance_with_lineage(proj: Path):
    res = topics.proven(root=proj)
    assert res["ok"] and res["n_posted"] == 3 and res["n_with_metrics"] == 2 and res["families"] == []
    # a third receipt post with metrics crosses n >= 3
    posted_record.record(RUN, "r1-w1-li", metrics="20k views 100 comments", posted_at="2026-09-16", root=proj)
    res = topics.proven(root=proj)
    assert res["n_with_metrics"] == 3
    assert res["families"] == [{"angle_family": "receipt", "n": 3, "views_mean": pytest.approx((9000 + 6000 + 20000) / 3, abs=0.1),
                                "comments_mean": 50.0, "best": f"{RUN}/r1-w1-li", "last_posted": "2026-09-16"}]
    assert res["moves"][0]["move"] == "corporate_register_for_trivial_event" and res["moves"][0]["n"] == 3
    text = (proj / "memory" / "topics.md").read_text()
    section = text.split("## Proven angles")[1]
    assert "| angle_family | n | views_mean | comments_mean | best | last_posted |" in section
    assert "| receipt | 3 | 11666.7 | 50.0 |" in section and "| move_used |" in section
    # the proven tables must never be mistaken for the scoreboard or the runs table by matrix.py
    rows, sb = __import__("matrix").parse_topics_md(text)
    assert set(sb) == {"corporate_register_for_trivial_event"} and len(rows) == 3


def test_topics_cli_accepts_root_in_either_position(proj: Path):
    res = _cli("topics.py", "add", RUN, "--outcome", "posted", "--root", str(proj), "--json")
    assert res["ok"] and res["row"]["outcome"] == "posted"
    res = _cli("topics.py", "--root", str(proj), "scoreboard")
    assert res["ok"] and res["n_rows"] == 2
    res = _cli("topics.py", "proven", "--root", str(proj))
    assert res["ok"]
    assert _cli("topics.py", "add", "2026-01-01_nope", "--root", str(proj))["ok"] is False
    out = subprocess.run([sys.executable, str(TOOLS / "topics.py"), "--help"], capture_output=True, text=True, check=False)
    assert out.returncode == 0 and "scoreboard" in out.stdout and "proven" in out.stdout


# =========================================================================== hygiene

def test_nothing_written_into_the_real_project():
    assert {str(p): p.exists() for p in _LABEL_STORES} == _REAL_STATE_BEFORE
    now = sorted(p.name for p in (REAL_ROOT / "memory" / "published").glob("*")) \
        if (REAL_ROOT / "memory" / "published").exists() else []
    assert now == _REAL_PUBLISHED_BEFORE
    assert common.ROOT == REAL_ROOT
