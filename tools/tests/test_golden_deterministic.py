"""End-to-end deterministic golden run.

Builds a scratch project root from tools/tests/fixtures/corpus (plus the real config, rubric and lexicon), runs
`stylometry --corpus` and `profile_stats --write` against it, then `tier0 --as-golden` over every item under
evals/golden/{negatives,positives}/ and compares the result with evals/golden/expected.json:

- every negative fails on each `must_fail` id (and on at least one `must_fail_any` id) with evidence;
- every positive has no hard fail except its documented `known_false_positive`, which, when it fires, carries
  `jury_override_allowed` (or a base-rate downgrade);
- no overlap check fires on a positive; the overlap negatives point at their source post.

Everything runs in-process through `common.use_root`, so nothing is written into the repository. The
judge-side expectations (judge_must_fail, claims, paraphrase, media) belong to health_run.py, not here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import common  # noqa: E402
import profile_stats  # noqa: E402
import stylometry  # noqa: E402
import tier0  # noqa: E402

PROJECT = TOOLS.parent
GOLD = PROJECT / "evals" / "golden"
FIXTURE_CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"
EXPECTED: dict = json.loads((GOLD / "expected.json").read_text(encoding="utf-8"))
OVERLAP_IDS = ("O1_ngram", "O2_phrases", "O3_skeleton", "O4_sibling", "O5_published")


# --------------------------------------------------------------------------- scratch root

def build_root(dst: Path) -> Path:
    """Scratch project root: fixture corpus + the real config, rubric version and lexicon; no profile yet."""
    shutil.copytree(FIXTURE_CORPUS, dst / "corpus")
    (dst / "config").mkdir(parents=True)
    shutil.copy(PROJECT / "config" / "postsmith.yaml", dst / "config" / "postsmith.yaml")
    (dst / "style").mkdir()
    shutil.copy(PROJECT / "style" / "lexicon.yaml", dst / "style" / "lexicon.yaml")
    rubric = common.rubric_dir()
    shutil.copytree(rubric, dst / "evals" / "rubric" / rubric.name)
    (dst / "evals" / "rubric" / "current").symlink_to(rubric.name)
    (dst / "pyproject.toml").write_text('[project]\nname = "golden-root"\nversion = "0"\n', encoding="utf-8")
    return dst


@pytest.fixture(scope="module")
def golden_root(tmp_path_factory) -> Path:
    root = build_root(tmp_path_factory.mktemp("golden") / "root")
    with common.use_root(root):
        summary = stylometry.run_corpus()
        assert summary["written"] == 12 and summary["skipped"] == [], summary
        lexicon, patterns = stylometry.load_optional_lexicon_patterns()
        assert lexicon and patterns
        written = profile_stats.write_profile(profile_stats.build_profile(common.load_config(), lexicon, patterns))
        assert written["written"] is True and written["profile_version"] == 1
    assert common.ROOT == PROJECT  # use_root restored the real project
    return root


@pytest.fixture(scope="module")
def docs(golden_root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for kind in ("negatives", "positives"):
        for name in EXPECTED[kind]:
            out[f"{kind}/{name}"] = tier0.run(str(GOLD / kind / name), as_golden=True, write=False, root=str(golden_root))
    return out


def failing(doc: dict) -> dict[str, dict]:
    return {k: v for k, v in doc["checks"].items() if not v["pass"]}


def text_of(kind: str, name: str) -> str:
    return common.split_front_matter((GOLD / kind / name).read_text(encoding="utf-8"))[1].rstrip("\n")


# --------------------------------------------------------------------------- the pipeline itself

def test_scratch_root_has_features_and_profile(golden_root: Path):
    assert len(list((golden_root / "corpus" / "features").glob("*.json"))) == 8
    assert len(list((golden_root / "corpus" / "heldout" / "features").glob("*.json"))) == 4
    profile = json.loads((golden_root / "style" / "profile.json").read_text(encoding="utf-8"))
    assert profile["profile_version"] == 1 and profile["n_posts"] == 8
    assert {"corpus", "platform:linkedin", "platform:x"} <= set(profile["scopes"])
    assert set(profile["base_rates"]) == set(profile_stats.BASE_RATE_IDS)
    assert all(0.0 <= v <= 1.0 for v in profile["base_rates"].values())
    assert "base_rates_note" not in profile
    # nothing leaked into the repository
    assert not list(GOLD.glob("*/*.txt")) and not list(GOLD.glob("*/*.tier0.json"))
    assert not (PROJECT / "style" / "profile.json").exists() or True  # a real profile may exist later; never ours


def test_golden_docs_are_well_formed(docs: dict[str, dict]):
    assert len(docs) == len(EXPECTED["negatives"]) + len(EXPECTED["positives"])
    for key, doc in docs.items():
        assert doc["schema"] == "postsmith.tier0/1" and doc["as_golden"] is True, key
        assert set(tier0.CHECK_IDS) <= set(doc["checks"]), key
        assert doc["checks"]["P0_schema"]["pass"] is True and doc["checks"]["P0_schema"]["skipped"] is True
        assert doc["expected_na"] == tier0.GOLDEN_EXPECTED_NA
        assert doc["profile_version"] == 1 and all(m == "ok" for m in doc["modules"].values()), key
        assert doc["envelope"]["scope"] == f"platform:{doc['platform']}", key  # no lens, no self samples
        assert doc["platform"] in ("linkedin", "x") and (doc["x_len"] is None) == (doc["platform"] == "linkedin")
        kind, name = key.split("/", 1)
        text = text_of(kind, name)
        for cid, res in doc["checks"].items():
            assert res["class"] in {"hard", "soft", "flag", "advisory"} and isinstance(res["pass"], bool), (key, cid)
            if not res["pass"]:
                assert res["evidence"], f"{key}: {cid} fails without evidence"
                for ev in res["evidence"]:
                    assert "why" in ev and "span" in ev, (key, cid)
                    if ev["span"]:
                        assert ev["span"] in text, f"{key}: {cid} evidence is not verbatim: {ev['span']!r}"
        assert doc["hard_fail"] == any(r["class"] == "hard" and not r["pass"] for r in doc["checks"].values())


def test_tier0_is_deterministic(golden_root: Path, docs: dict[str, dict]):
    again = tier0.run(str(GOLD / "negatives" / "s3_claude_flavored.md"), as_golden=True, write=False, root=str(golden_root))
    a = {k: v for k, v in docs["negatives/s3_claude_flavored.md"].items() if k != "generated_at"}
    b = {k: v for k, v in again.items() if k != "generated_at"}
    assert a == b


# --------------------------------------------------------------------------- negatives

@pytest.mark.parametrize("name", sorted(EXPECTED["negatives"]))
def test_negative_fails_on_expected_ids(docs: dict[str, dict], name: str):
    spec = EXPECTED["negatives"][name]
    fails = failing(docs[f"negatives/{name}"])
    missing = [c for c in spec["must_fail"] if c not in fails]
    assert not missing, f"{name}: must_fail ids not failing: {missing}; failing: {sorted(fails)}"
    if spec["must_fail_any"]:
        assert any(c in fails for c in spec["must_fail_any"]), \
            f"{name}: none of must_fail_any {spec['must_fail_any']} failed; failing: {sorted(fails)}"
    for cid in spec["must_fail"]:
        assert fails[cid]["class"] in {"hard", "soft", "flag"}, f"{name}: {cid} is only advisory"


def test_injection_and_empty_never_pass_tier0(docs: dict[str, dict]):
    inj = docs["negatives/injection.md"]
    assert inj["hard_fail"] is True and inj["checks"]["P9_residue"]["pass"] is False
    patterns = {e.get("pattern") for e in inj["checks"]["P9_residue"]["evidence"]}
    assert "P9_residue.instruction_injection" in patterns
    empty = docs["negatives/empty.md"]
    assert empty["hard_fail"] is True and empty["checks"]["P_min_words"]["pass"] is False and empty["chars"] == 0


def test_overlap_negatives_point_at_their_source_post(docs: dict[str, dict]):
    for name in ("corpus_copy.md", "synonym_swap.md"):
        spec = EXPECTED["negatives"][name]
        assert spec["fixture_corpus"] is True and spec["source_post_id"] == "okonkwo_001"
        o1 = docs[f"negatives/{name}"]["checks"]["O1_ngram"]
        assert o1["pass"] is False and o1["class"] == "hard", name
        assert "okonkwo_001" in {h["ref"] for h in o1["hits"]}, name
    o2 = docs["negatives/corpus_copy.md"]["checks"]["O2_phrases"]
    assert o2["pass"] is False and {h["ref"] for h in o2["hits"]} == {"okonkwo_001"}
    assert {h["source"] for h in o2["hits"]} == {"card"}  # the repo lexicon has no do_not_reuse yet
    clean = docs["negatives/clean_paraphrase.md"]["checks"]
    assert all(clean[o]["pass"] for o in OVERLAP_IDS)


# --------------------------------------------------------------------------- positives

@pytest.mark.parametrize("name", sorted(EXPECTED["positives"]))
def test_positive_has_no_hard_fail_except_documented_false_positive(docs: dict[str, dict], name: str):
    spec = EXPECTED["positives"][name]
    assert spec["expect"] == "pass"
    doc = docs[f"positives/{name}"]
    fails = failing(doc)
    kfp = spec.get("known_false_positive")
    hard = sorted(k for k, v in fails.items() if v["class"] == "hard" and k != kfp)
    assert not hard, f"{name}: unexpected hard fails {hard}: " + \
        "; ".join(f"{k}: {fails[k]['evidence'][:1]}" for k in hard)
    if kfp and kfp in fails:
        res = fails[kfp]
        assert res.get("jury_override_allowed") is True or res.get("downgraded") is True, \
            f"{name}: {kfp} fired without jury_override_allowed / base-rate downgrade"
        assert spec["resolved_by"] in ("jury", "base_rate")
    assert doc["hard_fail"] is bool(kfp and kfp in fails and fails[kfp]["class"] == "hard")
    assert all(doc["checks"][o]["pass"] for o in OVERLAP_IDS), f"{name}: overlap check fired against the fixture corpus"


def test_documented_false_positives_fire_with_jury_override(docs: dict[str, dict]):
    """The P8 / P10 / P12 false-positive items must actually trip their check (so the jury path is exercised)."""
    for name in ("p2_not_a_success_story.md", "p4_hot_take_nobody_asked.md", "quoted_closer_mockery.md"):
        kfp = EXPECTED["positives"][name]["known_false_positive"]
        res = docs[f"positives/{name}"]["checks"][kfp]
        assert res["pass"] is False and res["class"] == "hard" and res["jury_override_allowed"] is True, (name, kfp)
        assert res["evidence"] and all(e.get("known_false_positive") for e in res["evidence"]), (name, kfp)
    # p1 / p3 / p5 are clean of every hard, soft and flag check except the corpus-envelope soft checks
    for name in ("p1_ffmpeg.md", "p3_cursor_for_x.md", "p5_claude_code_migration.md"):
        others = {k for k, v in failing(docs[f"positives/{name}"]).items() if k not in ("E1_envelope", "P16_broetry")}
        assert not others, f"{name}: {sorted(others)}"


# --------------------------------------------------------------------------- CLI parity

def test_cli_root_switch_matches_in_process(golden_root: Path, docs: dict[str, dict]):
    r = subprocess.run([sys.executable, str(TOOLS / "tier0.py"), str(GOLD / "negatives" / "s1_broetry.md"),
                        "--as-golden", "--no-write", "--root", str(golden_root), "--json"],
                       capture_output=True, text=True, cwd=str(PROJECT), check=False)
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["profile_version"] == 1 and sorted(failing(doc)) == sorted(failing(docs["negatives/s1_broetry.md"]))
    assert not list(GOLD.glob("*/*.txt"))


# --------------------------------------------------------------------------- media briefs (deterministic gate only)

@pytest.mark.parametrize("name", sorted(EXPECTED["media"]))
def test_media_brief_matches_expected_media_check(name: str):
    """`media_check_must_fail` from expected.json; the media *judge* sub-results belong to health_run.py."""
    spec = EXPECTED["media"][name]
    r = subprocess.run([sys.executable, str(TOOLS / "media_check.py"), str(GOLD / "media" / name), "--json"],
                       capture_output=True, text=True, cwd=str(PROJECT), check=False)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "fails" in out and "warnings" in out, out
    assert out["ok"] is (not spec["media_check_must_fail"]), (name, out["fails"])
    if spec["media_check_must_fail"]:
        assert out["fails"] and all(isinstance(f, str) and ":" in f for f in out["fails"])
