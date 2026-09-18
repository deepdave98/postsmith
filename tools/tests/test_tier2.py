"""Tests for tools/lineup.py, tools/pairwise.py and tools/media_check.py.

Every test works on a scratch copy of tools/tests/fixtures/tier2: 8 heldout posts, 3 fictional authors, 2
platforms, train exemplars, self samples, and one run with candidates, media briefs and rendered prompts.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
PROJECT = TOOLS.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tier2"
sys.path.insert(0, str(TOOLS))

import common  # noqa: E402
import lineup  # noqa: E402
import media_check  # noqa: E402
import pairwise  # noqa: E402

RUN = "run1"
LI = "r1-w1-li"
LI_NO_ARCH = "r1-w2-li"
X = "r1-w1-x"


@pytest.fixture()
def root(tmp_path: Path):
    """Scratch copy of the fixture tree, with common.ROOT pointed at it for the duration of the test."""
    dst = tmp_path / "root"
    shutil.copytree(FIXTURES, dst)
    old_root, old_cfg = common.ROOT, common._CONFIG
    lineup.apply_root(str(dst))
    yield dst
    common.ROOT, common._CONFIG = old_root, old_cfg


def _cli(tool: str, *args: str, env_root: Path | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "POSTSMITH_ROOT")}
    if env_root is not None:
        env["POSTSMITH_ROOT"] = str(env_root)
    proc = subprocess.run([sys.executable, str(TOOLS / tool), *args], capture_output=True, text=True, env=env,
                          cwd=str(PROJECT), check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _key(root: Path, cid: str, mode: str | None = None) -> dict:
    name = (f"lineup_{cid}.key.json" if mode is None else
            f"pairwise_{cid}.key.json" if mode == "reference" else f"pairwise_{cid}.exemplars.key.json")
    return json.loads((root / "drafts" / RUN / "tier2" / name).read_text(encoding="utf-8"))


def _write_pick(root: Path, cid: str, lens: str, pick: str, confidence: int, tell: str = "too tidy",
                nonce: str | None = "auto") -> None:
    """Write a pick file where the key says the judge writes it, echoing the prompt's nonce."""
    key = _key(root, cid)
    d = root / key["picks_dir"]
    d.mkdir(parents=True, exist_ok=True)
    doc = {"pick": pick, "confidence": confidence, "tell": tell, "quote": "x"}
    if nonce == "auto":
        doc["nonce"] = key["nonces"][lens]
    elif nonce:
        doc["nonce"] = nonce
    (d / f"{lens}.json").write_text(json.dumps(doc), encoding="utf-8")


def _slot_for(key: dict, lens: str) -> str:
    return key["candidate_slot_by_lens"][lens]


def _other_slot(key: dict, lens: str) -> str:
    cand = _slot_for(key, lens)
    return next(l for l in "ABCD" if l != cand and l in key["slots"])


def _write_verdict(root: Path, cid: str, name: str, doc: dict, nonce: str | None = "auto") -> None:
    mode = "exemplars" if name.startswith("exemplar") else "reference"
    key = _key(root, cid, mode)
    d = root / key["verdicts_dir"]
    d.mkdir(parents=True, exist_ok=True)
    doc = dict(doc)
    if nonce == "auto":
        doc["nonce"] = key["nonces"][name]
    elif nonce:
        doc["nonce"] = nonce
    (d / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")


def _load_brief(root: Path, name: str) -> dict:
    return yaml.safe_load((root / "drafts" / RUN / "media" / f"{name}.brief.yaml").read_text(encoding="utf-8"))


def _load_prompts(root: Path, name: str) -> dict[str, str]:
    return media_check.load_prompts(root / "drafts" / RUN / "media" / f"{name}.prompts")


def _cfg() -> dict:
    return common.load_config()


# =============================================================================== lineup: build

def test_lineup_build_constraints_and_prompt(root: Path):
    out = lineup.build(LI, RUN, seed=7)
    assert out["ok"], out
    assert out["n_fillers"] == 3 and out["distinct_authors"] == 3
    assert out["advisory"] is False and out["eligible_count"] == 6
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    assert set(key["slots"]) == {"A", "B", "C", "D"}
    assert key["slots"][key["candidate_slot"]] == lineup.CANDIDATE_ID
    assert key["candidate_slot_by_lens"].keys() == {"reader", "voice", "comedy"}
    for f in key["fillers"]:
        assert f["post_id"].split("_")[0] in ("okafor", "vale", "lindqvist")
        assert f["archetype"] in ("contrarian_take", "story", "announcement_with_twist")
    prompt = (root / out["prompt"]).read_text(encoding="utf-8")
    assert lineup.QUESTION_TEXT in prompt
    assert '{"pick":"A|B|C|D","confidence":1-5,"tell":"...","quote":"..."}' in prompt
    assert "Length is not quality" in prompt
    for letter in "ABCD":
        assert f"## Post {letter}" in prompt and f'<untrusted_post id="{letter}">' in prompt
    assert "key.json" not in prompt and "__candidate__" not in prompt
    assert LI not in prompt  # the judge never learns the cid from the prompt (the output path names only the run)
    assert out["token"] == lineup.lineup_token(RUN, LI, 7) and f"lineup_{out['token']}." in out["prompt"]
    for lens in ("reader", "voice", "comedy"):
        lp = (root / out["lens_prompts"][lens]).read_text(encoding="utf-8")
        assert lineup.LENS_WORDING[lens] in lp
        assert f"{key['picks_dir']}/{lens}.json" in lp and f"lineup_{out['token']}.picks" in key["picks_dir"]
        assert f'"nonce": "{key["nonces"][lens]}"' in lp and LI not in lp


def test_lineup_anonymizes_fillers(root: Path):
    out = lineup.build(LI_NO_ARCH, RUN, seed=3)
    assert out["ok"], out
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    assert "vale_102" in {f["post_id"] for f in key["fillers"]}
    prompt = (root / out["prompt"]).read_text(encoding="utf-8")
    assert "@gregvale" not in prompt and "Tomas Vale" not in prompt
    assert "Ledger got four votes" in prompt  # casing and body preserved


def test_lineup_prefers_lower_likes_and_three_authors(root: Path):
    out = lineup.build(LI_NO_ARCH, RUN, seed=5)  # candidate without archetype -> pure likes preference
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    assert {f["post_id"] for f in key["fillers"]} == {"okafor_102", "vale_102", "lindqvist_101"}
    assert len({f["author"] for f in key["fillers"]}) == 3


def test_lineup_prefers_same_archetype(root: Path):
    out = lineup.build(LI, RUN, seed=7)  # candidate archetype contrarian_take
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    archetypes = [f["archetype"] for f in key["fillers"]]
    assert archetypes.count("contrarian_take") >= 2


def test_lineup_seed_is_deterministic(root: Path):
    a = lineup.build(LI, RUN, seed=42)
    key_a = json.loads((root / a["key"]).read_text(encoding="utf-8"))
    prompt_a = (root / a["prompt"]).read_text(encoding="utf-8")
    b = lineup.build(LI, RUN, seed=42)
    key_b = json.loads((root / b["key"]).read_text(encoding="utf-8"))
    assert key_a["orders"] == key_b["orders"] and key_a["slots"] == key_b["slots"]
    assert prompt_a == (root / b["prompt"]).read_text(encoding="utf-8")


def test_lineup_never_uses_pairwise_reference(root: Path):
    t2 = root / "drafts" / RUN / "tier2"
    t2.mkdir(parents=True)
    (t2 / f"pairwise_{LI_NO_ARCH}.key.json").write_text(json.dumps({"reference_id": "vale_102"}), encoding="utf-8")
    out = lineup.build(LI_NO_ARCH, RUN, seed=5)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    ids = {f["post_id"] for f in key["fillers"]}
    assert "vale_102" not in ids and "vale_101" in ids
    assert key["excluded"]["pairwise_reference"] == ["vale_102"]


def test_lineup_train_pool_excludes_exemplars_seen_and_is_advisory(root: Path):
    out = lineup.build(LI, RUN, seed=1, pool="train")
    assert out["ok"], out
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    ids = {f["post_id"] for f in key["fillers"]}
    assert ids == {"okafor_002", "lindqvist_002"}
    assert key["excluded"]["exemplars_seen"] == ["lindqvist_001", "okafor_001", "vale_001"]
    assert out["advisory"] is True


def test_lineup_small_corpus_builds_with_what_exists(root: Path):
    out = lineup.build(X, RUN, seed=9)
    assert out["ok"] and out["advisory"] is True and out["n_fillers"] == 2
    prompt = (root / out["prompt"]).read_text(encoding="utf-8")
    assert "Below are three posts" in prompt and '"pick":"A|B|C"' in prompt
    assert "advisory" in prompt.lower()


def test_lineup_build_errors_are_json(root: Path):
    assert lineup.build("nope-li", RUN, seed=1)["ok"] is False
    assert lineup.build(LI, RUN, seed=1, pool="bogus")["ok"] is False
    assert lineup.score("nope-li", RUN)["ok"] is False


def test_select_fillers_band_ladder():
    def f(pid, author, chars, likes=None):
        return {"post_id": pid, "author": author, "chars": chars, "likes": likes, "archetype": None, "text": "", "path": ""}

    # 30% band around 1000 chars holds only two posts from one author -> relax to 50% to reach three authors
    eligible = [f("p1", "a1", 1250), f("p2", "a1", 990), f("p3", "a2", 1400), f("p4", "a3", 1450)]
    picked, band = lineup.select_fillers(eligible, 1000, None, seed=1)
    assert band == "50%" and {p["author"] for p in picked} == {"a1", "a2", "a3"}
    # nothing within 50% -> any
    eligible = [f("p1", "a1", 3000), f("p2", "a2", 2600), f("p3", "a3", 100)]
    picked, band = lineup.select_fillers(eligible, 1000, None, seed=1)
    assert band == "any" and len(picked) == 3
    # inside the band, lower likes win and one post per author
    eligible = [f("p1", "a1", 1000, 900), f("p2", "a1", 1010, 10), f("p3", "a2", 1020, 50), f("p4", "a3", 1030, 5),
                f("p5", "a2", 1040, 1)]
    picked, band = lineup.select_fillers(eligible, 1000, None, seed=1)
    assert band == "30%" and {p["post_id"] for p in picked} == {"p2", "p4", "p5"}


# =============================================================================== lineup: score

def test_lineup_score_fails_on_two_strong_picks(root: Path):
    out = lineup.build(LI, RUN, seed=7)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    _write_pick(root, LI, "reader", _slot_for(key, "reader"), 5)
    _write_pick(root, LI, "voice", _slot_for(key, "voice"), 4)
    _write_pick(root, LI, "comedy", _other_slot(key, "comedy"), 5)
    res = lineup.score(LI, RUN)
    assert res["ok"] and res["pass"] is False and res["strong_picks"] == 2
    assert res["advisory"] is False and len(res["picks"]) == 3
    assert (root / "drafts" / RUN / "tier2" / f"lineup_{LI}.score.json").exists()


def test_lineup_score_fails_when_all_three_pick_it_at_low_confidence(root: Path):
    out = lineup.build(LI, RUN, seed=7)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    for lens in ("reader", "voice", "comedy"):
        _write_pick(root, LI, lens, _slot_for(key, lens), 2)
    res = lineup.score(LI, RUN)
    assert res["pass"] is False and res["strong_picks"] == 0 and res["candidate_picks"] == 3


def test_lineup_score_passes_single_strong_pick_and_logs_tell(root: Path):
    out = lineup.build(LI, RUN, seed=7)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    _write_pick(root, LI, "reader", _slot_for(key, "reader"), 5, tell="tricolon")
    _write_pick(root, LI, "voice", _other_slot(key, "voice"), 4)
    _write_pick(root, LI, "comedy", _other_slot(key, "comedy"), 3)
    res = lineup.score(LI, RUN)
    assert res["pass"] is True and res["strong_picks"] == 1
    assert res["tells"] == [{"lens": "reader", "confidence": 5, "tell": "tricolon", "quote": "x"}]


def test_lineup_score_uses_per_lens_orders(root: Path):
    out = lineup.build(LI, RUN, seed=7)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    # the reader letter is not the candidate for another lens unless the orders coincide
    reader_slot = _slot_for(key, "reader")
    for lens in ("reader", "voice", "comedy"):
        _write_pick(root, LI, lens, reader_slot, 5)
    res = lineup.score(LI, RUN)
    expected = sum(1 for lens in ("reader", "voice", "comedy") if _slot_for(key, lens) == reader_slot)
    assert res["candidate_picks"] == expected


def test_lineup_score_single_judge_returns_flag(root: Path):
    out = lineup.build(LI, RUN, seed=7)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    _write_pick(root, LI, "reader", _slot_for(key, "reader"), 4)
    res = lineup.score(LI, RUN)
    assert "pass" not in res and res["flag"] is True and res["n_judges"] == 1
    _write_pick(root, LI, "reader", _slot_for(key, "reader"), 2)
    assert lineup.score(LI, RUN)["flag"] is False
    _write_pick(root, LI, "reader", _other_slot(key, "reader"), 5)
    assert lineup.score(LI, RUN)["flag"] is False


def test_lineup_score_advisory_and_invalid_pick(root: Path):
    out = lineup.build(X, RUN, seed=9)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    _write_pick(root, X, "reader", _slot_for(key, "reader"), 5)
    _write_pick(root, X, "voice", _slot_for(key, "voice"), 5)
    (root / out["picks_dir"] / "comedy.json").write_text("{not json", encoding="utf-8")
    res = lineup.score(X, RUN)
    assert res["advisory"] is True and res["pass"] is False and len(res["invalid"]) == 1


def test_lineup_score_accepts_judge_document_shape(root: Path):
    out = lineup.build(LI, RUN, seed=7)
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    d = root / out["picks_dir"]
    d.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "postsmith.judge/1", "lens": "lineup", "nonce": key["nonces"]["reader"],
           "dimensions": {"lineup": {"pick": _slot_for(key, "reader"), "confidence": 5, "tell": "t", "quote": "q"}}}
    (d / "reader.json").write_text(json.dumps(doc), encoding="utf-8")
    res = lineup.score(LI, RUN)
    assert res["flag"] is True


def test_lineup_cli_root_flag_and_env(root: Path):
    out = _cli("lineup.py", "build", RUN, LI, "--seed", "3", "--root", str(root))
    assert out["ok"] and (root / out["key"]).exists()
    res = _cli("lineup.py", "score", RUN, LI, "--root", str(root))
    assert res["ok"] is False and "pick" in res["error"]
    out2 = _cli("lineup.py", "build", RUN, LI_NO_ARCH, "--seed", "3", env_root=root)
    assert out2["ok"] and (root / out2["key"]).exists()
    proc = subprocess.run([sys.executable, str(TOOLS / "lineup.py"), "--help"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0 and "build" in proc.stdout


# =============================================================================== pairwise: reference

def _expected_reference(root: Path, cid: str) -> str:
    meta, text = common.read_front_matter_file(root / "drafts" / RUN / "round1" / "candidates" / f"{cid}.md")
    best = None
    for m, t, p in common.iter_posts(["heldout"]):
        if m["platform"] != "linkedin":
            continue
        if lineup.card_fields(m["post_id"], "heldout").get("archetype") != meta["assignment"]["archetype"]:
            continue
        j = pairwise.trigram_jaccard(text, t)
        if best is None or (j, m["post_id"]) > best[0]:
            best = ((j, m["post_id"]), m["post_id"])
    return best[1]


def test_pairwise_reference_build(root: Path):
    out = pairwise.build(LI, RUN, mode="reference")
    assert out["ok"], out
    assert out["reference_id"] == _expected_reference(root, LI)
    assert out["archetype_fallback"] is False
    assert out["sample_source"] == "self" and out["n_samples"] == 3
    assert set(out["prompts"]) == {"reader.12", "reader.21", "voice.12", "voice.21"}
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    assert key["orders"]["reader.12"]["post1"] == "candidate" and key["orders"]["reader.21"]["post2"] == "candidate"
    p12 = (root / out["prompts"]["reader.12"]).read_text(encoding="utf-8")
    p21 = (root / out["prompts"]["reader.21"]).read_text(encoding="utf-8")
    for p in (p12, p21):
        assert pairwise.QUESTION_TEXT in p and pairwise.OUTPUT_SHAPE in p
        assert "Length is not quality" in p and "Post 1:" in p and "characters" in p
        assert "## Post A" in p and "## Post B" in p and "## Post C" in p
        assert "@" not in p and "http" not in p and "Tomas Vale" not in p
        assert "Also answer: " + pairwise.REWRITE_QUESTION not in p  # O3 passed in the fixture tier0
    cand_line = "Every AI budget review I sat in this year"
    assert p12.index(cand_line) < p12.index("## Post 2") < p21.index(cand_line)
    assert "as an engineer who reads this feed daily" in p12
    assert "as an editor who has ghostwritten" in (root / out["prompts"]["voice.12"]).read_text(encoding="utf-8")


def test_pairwise_reference_falls_back_without_archetype_and_uses_exemplars_when_no_self(root: Path):
    for p in (root / "corpus" / "self").glob("*.md"):
        p.unlink()
    out = pairwise.build(LI_NO_ARCH, RUN, mode="reference")
    assert out["ok"] and out["archetype_fallback"] is True
    assert out["sample_source"] == "exemplars" and out["n_samples"] == 3
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    assert {s["post_id"] for s in key["samples"]} <= {"vale_001", "okafor_001", "lindqvist_001"}


def test_pairwise_reference_avoids_lineup_fillers(root: Path):
    expected = _expected_reference(root, LI)
    t2 = root / "drafts" / RUN / "tier2"
    t2.mkdir(parents=True)
    (t2 / f"lineup_{LI}.key.json").write_text(json.dumps({"fillers": [{"post_id": expected}]}), encoding="utf-8")
    out = pairwise.build(LI, RUN, mode="reference")
    assert out["ok"] and out["reference_id"] != expected


def test_pairwise_ask_rewrite_from_tier0_and_flag(root: Path):
    scores = root / "drafts" / RUN / "round1" / "scores"
    ref = _expected_reference(root, LI)
    (scores / f"{LI}.tier0.json").write_text(json.dumps({
        "checks": {"O3_skeleton": {"class": "flag", "pass": False, "hits": [{"ref": ref, "span": "x"}]}}}), encoding="utf-8")
    out = pairwise.build(LI, RUN, mode="reference")
    assert out["ask_rewrite"] is True
    assert "Also answer: " + pairwise.REWRITE_QUESTION in (root / out["prompts"]["reader.12"]).read_text(encoding="utf-8")
    (scores / f"{LI}.tier0.json").write_text(json.dumps({
        "checks": {"O3_skeleton": {"class": "flag", "pass": False, "hits": [{"ref": "zzz_999"}]}}}), encoding="utf-8")
    assert pairwise.build(LI, RUN, mode="reference")["ask_rewrite"] is False
    assert pairwise.build(LI, RUN, mode="reference", ask_rewrite=True)["ask_rewrite"] is True


def test_pairwise_score_inconsistent_orders_is_tie(root: Path):
    pairwise.build(LI, RUN, mode="reference")
    # reader: order 12 says Post 1 (candidate) better, order 21 says Post 1 (reference) better -> inconsistent -> tie
    _write_verdict(root, LI, "reader.12", {"better": 1, "better_evidence": "a", "voice": 1, "voice_evidence": "b"})
    _write_verdict(root, LI, "reader.21", {"better": 1, "better_evidence": "a", "voice": 2, "voice_evidence": "b"})
    # voice lens: consistent candidate win on better, consistent loss on voice
    _write_verdict(root, LI, "voice.12", {"better": 1, "better_evidence": "a", "voice": 2, "voice_evidence": "b"})
    _write_verdict(root, LI, "voice.21", {"better": 2, "better_evidence": "a", "voice": 1, "voice_evidence": "b"})
    res = pairwise.score(LI, RUN, mode="reference")
    assert res["ok"] and res["advisory"] is True
    assert (res["wins"], res["ties"], res["losses"]) == (1, 1, 0)
    assert res["per_lens"]["reader"]["better"] == "tie" and res["per_lens"]["voice"]["better"] == "win"
    assert res["voice"] == {"wins": 1, "ties": 0, "losses": 1}
    assert res["pass"] is True and res["paraphrase"] is None


def test_pairwise_score_zero_wins_zero_ties_fails_and_missing_orders(root: Path):
    pairwise.build(LI, RUN, mode="reference")
    _write_verdict(root, LI, "reader.12", {"better": 2, "voice": 2})
    _write_verdict(root, LI, "reader.21", {"better": 1, "voice": 1})
    _write_verdict(root, LI, "voice.12", {"better": 2, "voice": 1})
    res = pairwise.score(LI, RUN, mode="reference")
    assert (res["wins"], res["ties"], res["losses"]) == (0, 0, 1)
    assert res["pass"] is False and res["missing"] == ["voice.21"]


def test_pairwise_score_same_post_rewritten_is_paraphrase(root: Path):
    pairwise.build(LI, RUN, mode="reference", ask_rewrite=True)
    _write_verdict(root, LI, "reader.12", {"better": 1, "voice": 1, "same_post_rewritten": False})
    _write_verdict(root, LI, "reader.21", {"better": 2, "voice": 2, "same_post_rewritten": "yes"})
    _write_verdict(root, LI, "voice.12", {"better": 1, "voice": 1, "same_post_rewritten": False})
    _write_verdict(root, LI, "voice.21", {"better": 2, "voice": 2, "same_post_rewritten": False})
    res = pairwise.score(LI, RUN, mode="reference")
    assert res["wins"] == 2 and res["paraphrase"] is True and res["pass"] is False


def test_pairwise_score_errors(root: Path):
    assert pairwise.score(LI, RUN, mode="reference")["ok"] is False
    pairwise.build(LI, RUN, mode="reference")
    assert pairwise.score(LI, RUN, mode="reference")["ok"] is False
    assert pairwise.build(LI, RUN, mode="bogus")["ok"] is False
    assert pairwise.build("nope-li", RUN)["ok"] is False


# =============================================================================== pairwise: exemplars

def test_pairwise_exemplars_build_picks_two_closest(root: Path):
    out = pairwise.build(LI, RUN, mode="exemplars")
    assert out["ok"] and out["skipped"] is None
    slots = [e["post_id"] for e in out["exemplars"]]
    assert slots[0] == "vale_001" and out["exemplars"][0]["matches"] == 3
    assert len(slots) == 2 and slots[1] in ("okafor_001", "lindqvist_001")
    p = (root / out["prompts"]["exemplar1"]).read_text(encoding="utf-8")
    assert pairwise.EXEMPLAR_QUESTION in p and "## Candidate" in p and "## Reference" in p
    assert "vale_001" not in p and "Tomas Vale" not in p and "Length is not quality" in p
    key = json.loads((root / out["key"]).read_text(encoding="utf-8"))
    assert key["exemplar_ids"] == slots


def test_pairwise_exemplars_score_yes_is_hard_paraphrase(root: Path):
    pairwise.build(LI, RUN, mode="exemplars")
    _write_verdict(root, LI, "exemplar1", {"same_skeleton_or_joke": False, "evidence": ""})
    _write_verdict(root, LI, "exemplar2", {"same_skeleton_or_joke": "yes", "evidence": "the invoice"})
    res = pairwise.score(LI, RUN, mode="exemplars")
    assert res["ok"] and res["paraphrase"] is True and res["hard"] is True
    _write_verdict(root, LI, "exemplar2", {"same_skeleton_or_joke": "no", "evidence": ""})
    assert pairwise.score(LI, RUN, mode="exemplars")["paraphrase"] is False


def test_pairwise_exemplars_skips_without_lineage(root: Path):
    out = pairwise.build(LI_NO_ARCH, RUN, mode="exemplars")
    assert out["ok"] and out["skipped"] and out["prompts"] == {}
    res = pairwise.score(LI_NO_ARCH, RUN, mode="exemplars")
    assert res["ok"] and res["paraphrase"] is False and res["skipped"]


def test_pairwise_exemplars_finds_self_and_x_exemplars(root: Path):
    out = pairwise.build(X, RUN, mode="exemplars")
    assert out["ok"] and {e["post_id"] for e in out["exemplars"]} == {"vale_002", "self_003"}


def test_pairwise_cli(root: Path):
    out = _cli("pairwise.py", "build", RUN, LI, "--mode", "exemplars", "--root", str(root))
    assert out["ok"] and (root / out["key"]).exists()
    res = _cli("pairwise.py", "score", RUN, LI, "--mode", "exemplars", "--root", str(root))
    assert res["ok"] is False
    out = _cli("pairwise.py", "build", RUN, LI, "--ask-rewrite", env_root=root)
    assert out["ok"] and out["ask_rewrite"] is True


# =============================================================================== media_check

@pytest.mark.parametrize("name", ["good_li_image", "good_x_video", "none_decision", "real_capture", "parody_ui_named"])
def test_media_check_passes(root: Path, name: str):
    brief = _load_brief(root, name)
    res = media_check.check(brief, _load_prompts(root, name), _cfg(), brief["platform"])
    assert res["ok"] is True and res["fails"] == [], res


@pytest.mark.parametrize("name,needle", [
    ("empty_delete_test", "delete_test"),
    ("wrong_aspect", "aspect: 16:9"),
    ("veo_negation", "negation:"),
    ("fake_screenshot", "M6"),
    ("parody_ui_no_name", "parody_ui:"),
    ("alt_too_long", "alt_text:"),
    ("person_name", "person: real person named"),
    ("no_rule_cited", "M1-M7"),
])
def test_media_check_fails(root: Path, name: str, needle: str):
    brief = _load_brief(root, name)
    res = media_check.check(brief, _load_prompts(root, name), _cfg(), brief["platform"])
    assert res["ok"] is False
    assert any(needle in f for f in res["fails"]), res["fails"]


def test_media_check_fake_screenshot_names_real_product(root: Path):
    brief = _load_brief(root, "fake_screenshot")
    res = media_check.check(brief, {}, _cfg(), "linkedin")
    m6 = [f for f in res["fails"] if f.startswith("M6")]
    assert len(m6) == 1 and "Claude Code" in m6[0] and "real_capture_direction" in m6[0]


def test_media_check_required_fields(root: Path):
    brief = _load_brief(root, "good_li_image")
    for field in ("visual_concept", "aspect_ratio", "decision_reason"):
        b = copy.deepcopy(brief)
        b.pop(field)
        res = media_check.check(b, {}, _cfg(), "linkedin")
        assert any(f.startswith("required:") and field in f for f in res["fails"]), (field, res["fails"])
    b = copy.deepcopy(brief)
    b["tool"] = {}
    assert any("tool.primary" in f for f in media_check.check(b, {}, _cfg(), "linkedin")["fails"])
    b = copy.deepcopy(brief)
    b["delete_test"] = "Nothing."
    assert any("loses nothing" in f for f in media_check.check(b, {}, _cfg(), "linkedin")["fails"])
    b = copy.deepcopy(brief)
    b["decision"] = "maybe"
    assert media_check.check(b, {}, _cfg(), "linkedin")["ok"] is False
    assert media_check.check({}, {}, _cfg(), "linkedin")["ok"] is False
    assert media_check.check(brief, {}, _cfg(), "mastodon")["ok"] is False


def test_media_check_text_budgets_and_verbatim(root: Path):
    brief = _load_brief(root, "good_li_image")
    prompts = _load_prompts(root, "good_li_image")
    b = copy.deepcopy(brief)
    b["on_image_text"]["lines"] = ["one two three four five six seven eight nine"]
    res = media_check.check(b, {}, _cfg(), "linkedin")
    assert any("exceeds 8 words" in f for f in res["fails"])
    b = copy.deepcopy(brief)
    b["tool"]["primary"] = "gpt_image"
    b["on_image_text"]["lines"] = ["one two three four five", "six seven eight nine ten", "eleven twelve thirteen"]
    res = media_check.check(b, {}, _cfg(), "linkedin")
    assert any("GPT Image allows <= 12" in f for f in res["fails"])
    b = copy.deepcopy(brief)
    b["on_image_text"]["lines"] = ["a", "b", "c", "d", "e", "f"]
    res = media_check.check(b, {}, _cfg(), "linkedin")
    assert any("Nano Banana allows <= 5" in f for f in res["fails"])
    broken = dict(prompts)
    broken["gpt_image"] = prompts["gpt_image"].replace('"Item: one domain, to be safe"', "Item: one domain, to be safe")
    res = media_check.check(brief, broken, _cfg(), "linkedin")
    assert any(f.startswith("text_verbatim:") and "gpt_image" in f for f in res["fails"])
    assert not any("nano_banana" in f for f in res["fails"])
    curly = dict(prompts)
    curly["nano_banana"] = prompts["nano_banana"].replace('"AGENT PURCHASE ORDER"', "\u201cAGENT PURCHASE ORDER\u201d")
    assert media_check.check(brief, curly, _cfg(), "linkedin")["ok"] is True


def test_media_check_negation_word_boundaries(root: Path):
    brief = _load_brief(root, "good_li_image")
    prompts = _load_prompts(root, "good_li_image")
    ok_prompt = prompts["nano_banana"] + "\nA piano stands in the corner and the paper is a plain non-glossy laminate.\n"
    assert media_check.check(brief, {"nano_banana": ok_prompt}, _cfg(), "linkedin")["ok"] is True
    bad_prompt = prompts["nano_banana"] + "\nAvoid clutter and don\u2019t add a watermark.\n"
    res = media_check.check(brief, {"nano_banana": bad_prompt}, _cfg(), "linkedin")
    assert any("negation:" in f and "'avoid'" in f and '"don\'t"' in f for f in res["fails"])
    # GPT Image prompts may say "no watermark" (positive-only rule applies to Veo/Runway/Nano Banana)
    assert media_check.check(brief, {"gpt_image": prompts["gpt_image"]}, _cfg(), "linkedin")["ok"] is True


def test_media_check_video_rules(root: Path):
    brief = _load_brief(root, "good_x_video")
    prompts = _load_prompts(root, "good_x_video")
    cfg = _cfg()
    b = copy.deepcopy(brief)
    b["video"]["duration_s"] = 5
    res = media_check.check(b, prompts, cfg, "x")
    assert any("veo: duration 5s" in f for f in res["fails"])
    b = copy.deepcopy(brief)
    b["video"]["dialogue"] = [{"speaker_desc": "a man", "line": " ".join(["word"] * 21)}]
    res = media_check.check(b, prompts, cfg, "x")
    assert any("veo: dialogue has 21 words" in f for f in res["fails"])
    p = dict(prompts)
    p["veo"] = prompts["veo"] + "\nA title card reads the item line as a caption.\n"
    res = media_check.check(brief, p, cfg, "x")
    assert any("veo:" in f and "on-screen text" in f for f in res["fails"])
    p = dict(prompts)
    p["veo"] = " ".join(["word"] * 701)
    assert any("701 words" in f for f in media_check.check(brief, p, cfg, "x")["fails"])
    p = dict(prompts)
    p["runway"] = "x" * 1001
    assert any("runway:" in f and "1001 chars" in f for f in media_check.check(brief, p, cfg, "x")["fails"])
    b = copy.deepcopy(brief)
    b["tool"]["primary"] = "runway_gen_4_5"
    b["video"]["start_frame"] = "none"
    b["references"] = []
    b["video"]["dialogue"] = []
    res = media_check.check(b, prompts, cfg, "x")
    assert any("text-to-video renders only 16:9" in f for f in res["fails"])
    b["aspect_ratio"] = "16:9"
    res = media_check.check(b, prompts, cfg, "x")
    assert not any(f.startswith("runway:") for f in res["fails"]), res["fails"]
    assert any("video aspect" in f for f in res["fails"])  # 16:9 is not an X video aspect
    b = copy.deepcopy(brief)
    b["video"] = None
    assert any("video block" in f for f in media_check.check(b, {}, cfg, "x")["fails"])
    b = copy.deepcopy(brief)
    b["aspect_ratio"] = "4:5"
    assert any("aspect: 4:5 is not a x video aspect" in f for f in media_check.check(b, prompts, cfg, "x")["fails"])


def test_media_check_brands_and_people(root: Path):
    brief = _load_brief(root, "good_li_image")
    cfg = _cfg()
    b = copy.deepcopy(brief)
    b["subject"] = "a laminated form next to a Cursor sticker and a Notion mug"
    res = media_check.check(b, {}, cfg, "linkedin")
    assert res["ok"] is True
    assert {w for w in res["warnings"] if w.startswith("brand:")} == {
        "brand: Cursor named in the brief; only the user's own brand may appear (real_capture_direction is exempt)",
        "brand: Notion named in the brief; only the user's own brand may appear (real_capture_direction is exempt)"}
    cfg2 = copy.deepcopy(cfg)
    cfg2["persona"] = {"name": "Deep Dave", "brands": ["Cursor", "Notion"]}
    assert not [w for w in media_check.check(b, {}, cfg2, "linkedin")["warnings"] if w.startswith("brand:")]
    b = copy.deepcopy(brief)
    b["subject"] = "a form signed by Priya Natarajan"
    res = media_check.check(b, {}, cfg, "linkedin")
    assert res["ok"] is True and any("Priya Natarajan" in w for w in res["warnings"])
    # the real-capture block is exempt from the brand scan
    rc = _load_brief(root, "real_capture")
    rc["real_capture_direction"]["what_to_open"] = "the Claude Code session in Cursor"
    res = media_check.check(rc, {}, cfg, "linkedin")
    assert res["ok"] is True and not [w for w in res["warnings"] if w.startswith("brand:")]
    # a brand inside a rendered prompt is a warning; a real person in a prompt is a fail
    res = media_check.check(brief, {"gpt_image": "Text: \"AGENT PURCHASE ORDER\" \"Item: one domain, to be safe\" on a Stripe receipt"}, cfg, "linkedin")
    assert any("brand: Stripe named in prompt gpt_image" in w for w in res["warnings"])
    res = media_check.check(brief, {"gpt_image": "\"AGENT PURCHASE ORDER\" \"Item: one domain, to be safe\" signed by Elon Musk"}, cfg, "linkedin")
    assert any("person: real person named in prompt gpt_image: Elon Musk" == f for f in res["fails"])


def test_media_check_safety_flags(root: Path):
    b = _load_brief(root, "good_li_image")
    b["safety_checks"]["no_logos_or_trademarks"] = False
    assert any("safety:" in f for f in media_check.check(b, {}, _cfg(), "linkedin")["fails"])


def test_media_check_cli(root: Path):
    out = _cli("media_check.py", "drafts/run1/media/good_li_image.brief.yaml", "--root", str(root))
    assert out["ok"] is True and out["prompts_dir"].endswith("good_li_image.prompts") and out["fails"] == []
    out = _cli("media_check.py", str(root / "drafts/run1/media/veo_negation.brief.yaml"), "--platform", "x",
               "--prompts", str(root / "drafts/run1/media/veo_negation.prompts"), "--root", str(root))
    assert out["ok"] is False and any("negation:" in f for f in out["fails"])
    out = _cli("media_check.py", "drafts/run1/media/does_not_exist.brief.yaml", "--root", str(root))
    assert out["ok"] is False and "not found" in out["error"]
    bad = root / "drafts/run1/media/bad.brief.yaml"
    bad.write_text("decision: [unclosed\n", encoding="utf-8")
    out = _cli("media_check.py", str(bad), "--root", str(root))
    assert out["ok"] is False and "parse" in out["error"]
    proc = subprocess.run([sys.executable, str(TOOLS / "media_check.py"), "--help"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0 and "--prompts" in proc.stdout
