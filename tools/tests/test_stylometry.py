"""Tests for stylometry.py, profile_stats.py and envelope_check.py.

Fixtures live under tools/tests/fixtures/stylometry/: three posts (broetry LinkedIn, dense X, Spanish) and a
miniature project root (config, 5 train posts, 1 self post, 1 heldout post, 6 pre-computed feature files).
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
import envelope_check  # noqa: E402
import profile_stats  # noqa: E402
import stylometry  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "stylometry"
PROJECT = TOOLS.parent

CONTRACT_KEYS = [
    "post_id", "platform", "lang", "n_chars", "n_words", "n_lines", "n_blank", "n_sentences", "line_words",
    "sent_words", "hook", "pov", "tense_past_ratio", "punct_per_1k", "case", "symbols", "lexicon", "function_words",
    "ai_tells", "questions", "imperatives", "tricolons", "hedges", "fk_grade", "pct_single_sentence_paras",
]
NESTED_KEYS = {
    "line_words": ["median", "q1", "q3", "max", "pct_le4", "pct_one_word", "max_run_single_line_paras", "rhythm"],
    "sent_words": ["mean", "sd", "cv", "max", "pct_le5"],
    "hook": ["line1_chars", "line1_words", "chars_before_blank", "cut140_ends_sentence", "cut210_ends_sentence",
             "is_question"],
    "pov": ["i_per100", "you_per100", "we_per100", "dominant"],
    "punct_per_1k": ["period", "comma", "exclaim", "question", "colon", "semicolon", "em_dash", "en_dash", "ellipsis",
                     "paren", "quote", "missing_terminal_period_ratio"],
    "case": ["pct_allcaps_tokens", "pct_lower_initial_sentences"],
    "symbols": ["emoji_count", "emoji_set", "hashtags", "mentions", "urls", "bullets", "arrows"],
    "lexicon": ["ttr", "ttr_n", "mean_word_len", "pct_long_words", "contraction_rate", "numerals", "proper_nouns",
                "dollar_figures", "specificity_per100", "profanity"],
}
LEXICON = {"lexicon_version": 1, "tiers": {
    "t1": [{"phrase": "unpopular opinion", "note": "stale opener"}, {"phrase": r"\bdelv(?:e|es|ing)\b", "regex": True}],
    "t2": ["game-changer"],
    "t3": [],
    "claude": [{"phrase": "the honest answer"}],
}}
PATTERNS = {"patterns": [
    {"id": "P8_opener.unpopular", "check": "P8_opener", "regex": r"^unpopular opinion:", "flags": "i", "scope": "line1"},
    {"id": "P12_closer.lesson", "check": "P12_closer", "regex": r"\bthe lesson\b", "flags": "i", "scope": "tail2"},
    {"id": "P7_bait.agree", "check": "P7_bait", "regex": r"\bagree\?", "flags": "i"},
]}
CFG = {"envelope": {"iqr_widen": 0.5, "pass_score": 0.70}, "corpus": {"self_min_samples": 5}}


def load_post(name: str) -> tuple[dict, str]:
    return common.read_front_matter_file(FIX / "posts" / f"{name}.md")


def post_features(name: str) -> dict:
    meta, text = load_post(name)
    return stylometry.features(text.rstrip("\n"), meta["platform"], meta["lang"], LEXICON, PATTERNS,
                               post_id=meta["post_id"])


@pytest.fixture(autouse=True)
def _restore_root():
    root, cfg = common.ROOT, common._CONFIG
    yield
    common.ROOT, common._CONFIG = root, cfg


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    shutil.copytree(FIX / "root", root)
    stylometry.apply_root(root)
    return root


def run_cli(tool: str, *args: str, cwd: Path | None = None) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(TOOLS / tool), *args], capture_output=True, text=True,
                          cwd=str(cwd or PROJECT))
    assert proc.returncode == 0, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


# --------------------------------------------------------------------------- stylometry.features


def test_all_contract_keys_present_and_ordered():
    feat = post_features("broetry_li")
    assert list(feat.keys()) == CONTRACT_KEYS
    for block, keys in NESTED_KEYS.items():
        assert list(feat[block].keys()) == keys, block
    assert set(feat["ai_tells"]) == {"t1", "t2", "t3", "claude", "patterns"}
    assert set(feat["function_words"]) == set(common.FUNCTION_WORDS)


def test_broetry_linkedin_post():
    feat = post_features("broetry_li")
    assert feat["post_id"] == "fix_broetry_001" and feat["platform"] == "linkedin"
    assert feat["n_lines"] == 13 and feat["n_blank"] == 12 and feat["n_words"] == 82
    assert feat["line_words"]["max_run_single_line_paras"] == 13
    assert feat["line_words"]["rhythm"].startswith("1/1/3/1/")
    assert feat["pct_single_sentence_paras"] > 0.80
    assert feat["line_words"]["pct_one_word"] == pytest.approx(1 / 13, abs=1e-3)
    assert feat["symbols"] == {"emoji_count": 1, "emoji_set": ["🚀"], "hashtags": 3, "mentions": 0, "urls": 0,
                               "bullets": 0, "arrows": 0}
    assert feat["punct_per_1k"]["em_dash"] > 0 and feat["punct_per_1k"]["en_dash"] == 0
    assert feat["punct_per_1k"]["missing_terminal_period_ratio"] == pytest.approx(2 / 13, abs=1e-3)
    assert feat["hook"]["line1_chars"] == 74 and feat["hook"]["chars_before_blank"] == 74
    assert feat["hook"]["cut140_ends_sentence"] is True and feat["hook"]["is_question"] is False
    assert feat["pov"]["dominant"] == "first_singular" and feat["pov"]["i_per100"] > feat["pov"]["you_per100"]
    assert feat["questions"] == 2
    assert feat["tricolons"] == 1  # "Cold shower. Journal. Meditate."
    assert feat["sent_words"]["cv"] > 0.5  # bursty: 1-word lines next to 15-word lines
    assert feat["lexicon"]["specificity_per100"] < 2  # broetry: no receipts
    assert feat["ai_tells"]["t1"] == ["Unpopular opinion"]
    assert feat["ai_tells"]["t2"] == [] and feat["ai_tells"]["claude"] == []
    # line1-scoped and text-scoped patterns hit; the tail2-scoped closer does not ("The lesson?" is mid-post)
    assert feat["ai_tells"]["patterns"] == ["P8_opener.unpopular", "P7_bait.agree"]
    assert 0 < feat["fk_grade"] < 8


def test_dense_x_post():
    feat = post_features("dense_x")
    assert feat["platform"] == "x" and feat["n_lines"] == 1 and feat["n_blank"] == 0
    assert feat["line_words"]["rhythm"] == "7" and feat["n_sentences"] == 7
    assert feat["pct_single_sentence_paras"] == 0.0
    lex = feat["lexicon"]
    assert lex["proper_nouns"] == 6  # AI, SDR, Vendor, Corp, Claude, Code
    assert lex["dollar_figures"] == 2  # $1,140 and $0
    assert lex["numerals"] == 2  # "2 meetings", "11 lines"; 40%, v3.1 and the $ figures are counted elsewhere
    assert lex["specificity_per100"] == pytest.approx(100 * (2 + 6 + 2 + 1 + 1) / feat["n_words"], abs=1e-3)
    assert lex["contraction_rate"] > 0  # who'd, it's
    assert lex["ttr_n"] == feat["n_words"] == 66
    assert feat["hook"]["is_question"] is False  # first sentence is not the question; the last one is
    assert feat["questions"] == 1
    assert feat["pov"]["dominant"] == "first_plural"
    assert 17 < feat["punct_per_1k"]["period"] < 19  # decimals in $1,140 / v3.1 are not sentence periods
    assert feat["punct_per_1k"]["missing_terminal_period_ratio"] == 0.0
    assert feat["case"]["pct_lower_initial_sentences"] == 0.0
    assert feat["ai_tells"]["t1"] == [] and feat["ai_tells"]["patterns"] == []
    assert 0 < feat["tense_past_ratio"] <= 1


def test_non_english_post_nulls_english_only_features():
    feat = post_features("nonenglish")
    assert feat["lang"] == "es"
    assert feat["function_words"] is None and feat["ai_tells"] is None
    assert feat["hedges"] is None and feat["fk_grade"] is None
    assert feat["lexicon"]["contraction_rate"] is None
    assert feat["n_words"] == 80 and feat["n_lines"] == 5
    assert feat["pct_single_sentence_paras"] == pytest.approx(0.6)
    assert feat["lexicon"]["proper_nouns"] >= 2  # Claude, Code
    assert json.dumps(feat)  # serialisable


def test_empty_text_is_safe():
    feat = stylometry.features("", "x")
    assert list(feat.keys()) == CONTRACT_KEYS
    assert feat["n_words"] == 0 and feat["n_sentences"] == 0 and feat["n_lines"] == 0
    assert feat["line_words"]["median"] is None and feat["fk_grade"] is None
    assert feat["sent_words"]["cv"] == 0.0 and feat["pct_single_sentence_paras"] == 0.0
    assert feat["hook"]["cut140_ends_sentence"] is True


def test_helpers():
    assert stylometry.syllables("cheaper") == 2 and stylometry.syllables("the") == 1
    assert stylometry.syllables("banana") == 3 and stylometry.syllables("proprietary") >= 4  # vowel-group heuristic
    assert stylometry.count_tricolons(["Fast, cheap, and honest."], ["Fast, cheap, and honest."]) == 1
    assert stylometry.count_tricolons(["Fast.", "Cheap.", "Good."], ["Fast.", "Cheap.", "Good."]) == 1
    assert stylometry.count_tricolons(["We shipped it on Tuesday."], ["We shipped it on Tuesday."]) == 0
    assert stylometry.count_hedges("It might roughly work, perhaps.") == 3
    assert stylometry.cosine_distance({"a": 1.0, "b": 0.0}, {"a": 1.0, "b": 0.0}) == 0.0
    assert stylometry.cosine_distance({"a": 1.0}, {"b": 1.0}) == pytest.approx(1.0)
    assert stylometry.cosine_distance({}, {"a": 1.0}) is None
    assert stylometry.ai_tell_hits("We must delve deeper.", LEXICON, None)["t1"] == ["delve"]
    assert stylometry.ai_tell_hits("Nothing here.", None, None) == {"t1": [], "t2": [], "t3": [], "claude": [],
                                                                    "patterns": []}
    assert stylometry.features("Stop. Do it now. Ship it.", "x")["imperatives"] == 3


def test_flatten_numeric():
    flat = stylometry.flatten_numeric(post_features("dense_x"))
    assert flat["line_words.median"] == 66.0 and flat["hook.is_question"] == 0.0
    assert "function_words.the" not in flat and "ai_tells" not in flat and "line_words.rhythm" not in flat
    assert stylometry.get_path({"a": {"b": 1}}, "a.b") == 1 and stylometry.get_path({"a": 1}, "a.b") is None


def test_stylometry_cli_single_and_corpus(tmp_root: Path, tmp_path: Path):
    _, out = run_cli("stylometry.py", str(FIX / "posts" / "dense_x.md"), "--root", str(tmp_root))
    assert out["post_id"] == "fix_dense_001" and out["platform"] == "x"
    txt = tmp_path / "raw.txt"
    txt.write_text("Just a raw post. No front matter.\n", encoding="utf-8")
    _, out = run_cli("stylometry.py", str(txt), "--platform", "x", "--lang", "en", "--root", str(tmp_root))
    assert out["platform"] == "x" and out["n_sentences"] == 2 and out["post_id"] == "raw"
    _, out = run_cli("stylometry.py", "--corpus", "--root", str(tmp_root))
    assert out["ok"] is True and out["written"] == 7 and out["skipped"] == []
    assert (tmp_root / "corpus" / "heldout" / "features" / "welsh_003.json").exists()
    assert (tmp_root / "corpus" / "features" / "self_001.json").exists()
    assert "corpus/heldout/features/welsh_003.json" in out["files"]
    written = json.loads((tmp_root / "corpus" / "features" / "acosta_001.json").read_text())
    assert written["post_id"] == "acosta_001" and written["lexicon"]["dollar_figures"] == 4  # $9,000 $41 $2,500 $625


def test_stylometry_cli_user_errors(tmp_root: Path):
    _, out = run_cli("stylometry.py", str(tmp_root / "nope.md"), "--root", str(tmp_root))
    assert out["ok"] is False and "cannot read" in out["error"]
    _, out = run_cli("stylometry.py", "--root", str(tmp_root / "missing-dir"))
    assert out["ok"] is False
    _, out = run_cli("stylometry.py", "--root", str(tmp_root))
    assert out["ok"] is False and "--corpus" in out["error"]


# --------------------------------------------------------------------------- profile_stats


def test_profile_scopes_and_envelopes(tmp_root: Path, monkeypatch):
    profile = profile_stats.build_profile(common.load_config())
    assert set(profile["scopes"]) == {"corpus", "self", "platform:linkedin", "platform:x", "author:lara-acosta"}
    ns = {k: v["n"] for k, v in profile["scopes"].items()}
    assert ns == {"corpus": 6, "self": 1, "platform:linkedin": 4, "platform:x": 2, "author:lara-acosta": 3}
    assert "author:justin-welsh" not in profile["scopes"]  # 2 posts < author_profile_min_posts (3)
    assert profile["n_posts"] == 6 and len(profile["corpus_hash"]) == 64
    assert set(profile["base_rates"]) == set(profile_stats.BASE_RATE_IDS)  # real ai_tells / platform_check
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in profile["base_rates"].values())
    assert "base_rates_note" not in profile
    assert "notes" not in profile  # every post had a features file
    corpus = profile["scopes"]["corpus"]
    for path in ("line_words.median", "sent_words.cv", "punct_per_1k.em_dash", "lexicon.specificity_per100",
                 "n_chars", "pct_single_sentence_paras", "hook.cut140_ends_sentence"):
        st = corpus["features"][path]
        assert set(st) == {"median", "q1", "q3", "min", "max", "n"} and st["n"] == 6
        assert st["min"] <= st["q1"] <= st["median"] <= st["q3"] <= st["max"]
    assert "line_words.rhythm" not in corpus["features"] and "function_words.the" not in corpus["features"]
    assert set(corpus["function_word_centroid"]) == set(common.FUNCTION_WORDS)
    assert 0 < corpus["max_intra_distance"] < 1 and profile["scopes"]["self"]["max_intra_distance"] == 0.0
    assert corpus["media_rate"] == pytest.approx(1 / 6, abs=1e-3)
    assert profile["scopes"]["author:lara-acosta"]["media_rate"] == pytest.approx(1 / 3, abs=1e-3)
    x_chars = profile["scopes"]["platform:x"]["features"]["n_chars"]
    assert x_chars["max"] < 300 < profile["scopes"]["platform:linkedin"]["features"]["n_chars"]["min"]


def test_profile_base_rates_with_check_modules(tmp_root: Path, monkeypatch):
    import types

    ai = types.ModuleType("ai_tells")
    seen: list[str] = []

    def ai_run(text, platform, meta, cfg, lexicon, patterns, base_rates):
        seen.append(meta["post_id"])
        assert base_rates is None
        return {"checks": {"P8_opener": {"class": "hard", "pass": not text.startswith("Nobody")},
                           "P10_contrast_flip": {"class": "hard", "pass": True},
                           "P12_closer": {"class": "hard", "pass": True},
                           "P17_lists": {"class": "soft", "pass": False}}}

    ai.run_checks = ai_run
    pc = types.ModuleType("platform_check")
    pc.run_checks = lambda text, platform, meta, cfg: {"checks": {"P6_emoji": {"class": "hard", "pass": True}}}
    monkeypatch.setattr(profile_stats, "ai_tells", ai)
    monkeypatch.setattr(profile_stats, "platform_check", pc)
    profile = profile_stats.build_profile(common.load_config())
    assert sorted(seen) == ["acosta_001", "acosta_002", "acosta_003", "self_001", "welsh_001", "welsh_002"]
    assert profile["base_rates"] == {"P8_opener": pytest.approx(1 / 6, abs=1e-3), "P10_contrast_flip": 0.0,
                                     "P12_closer": 0.0, "P17_lists": 1.0, "P16_broetry": 0.0, "P14_dashes": 0.0,
                                     "P6_emoji": 0.0}
    assert "base_rates_note" not in profile


def test_profile_base_rates_propagate_module_errors(tmp_root: Path, monkeypatch):
    """A check module that raises is a programmer error: the profile build must not silently skip it."""
    import types

    ai = types.ModuleType("ai_tells")
    ai.run_checks = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    monkeypatch.setattr(profile_stats, "ai_tells", ai)
    with pytest.raises(RuntimeError, match="boom"):
        profile_stats.build_profile(common.load_config())


def test_profile_write_and_versioning(tmp_root: Path, monkeypatch):
    cfg = common.load_config()
    first = profile_stats.write_profile(profile_stats.build_profile(cfg))
    assert first["profile_version"] == 1 and first["previous"] is None
    assert json.loads((tmp_root / "style" / "profile.json").read_text())["profile_version"] == 1
    second = profile_stats.write_profile(profile_stats.build_profile(cfg))
    assert second["profile_version"] == 1 and second["previous"] is None  # unchanged profile keeps its version
    post = tmp_root / "corpus" / "posts" / "acosta_001.md"
    post.write_text(post.read_text() + "\nAlso: this line was added later, for $12.\n", encoding="utf-8")
    stylometry.run_corpus(("train",))
    third = profile_stats.write_profile(profile_stats.build_profile(cfg))
    assert third["profile_version"] == 2 and third["previous"] == "style/profile.p1.json"
    assert third["corpus_hash"] != first["corpus_hash"]
    backup = json.loads((tmp_root / "style" / "profile.p1.json").read_text())
    assert backup["profile_version"] == 1 and backup["corpus_hash"] == first["corpus_hash"]
    assert json.loads((tmp_root / "style" / "profile.json").read_text())["profile_version"] == 2


def test_profile_computes_missing_features_on_the_fly(tmp_root: Path, monkeypatch):
    (tmp_root / "corpus" / "features" / "welsh_002.json").unlink()
    profile = profile_stats.build_profile(common.load_config())
    assert profile["scopes"]["corpus"]["n"] == 6 and profile["notes"] == ["welsh_002: no features file, computed on the fly"]


def test_profile_cli(tmp_root: Path):
    _, out = run_cli("profile_stats.py", "--root", str(tmp_root))
    assert out["ok"] is True and out["written"] is False and out["profile_version"] == 1
    assert not (tmp_root / "style" / "profile.json").exists()
    _, out = run_cli("profile_stats.py", "--write", "--root", str(tmp_root), "--json")
    assert out["ok"] is True and out["written"] is True and out["path"] == "style/profile.json"
    assert (tmp_root / "style" / "profile.json").exists()
    shutil.rmtree(tmp_root / "corpus" / "posts")
    shutil.rmtree(tmp_root / "corpus" / "self")
    _, out = run_cli("profile_stats.py", "--root", str(tmp_root))
    assert out["ok"] is False and "no corpus posts" in out["error"]


# --------------------------------------------------------------------------- envelope_check


def _stats(q1: float, q3: float, lo: float | None = None, hi: float | None = None, n: int = 10) -> dict:
    med = (q1 + q3) / 2
    return {"median": med, "q1": q1, "q3": q3, "min": lo if lo is not None else q1, "max": hi if hi is not None else q3, "n": n}


def synthetic_profile(self_n: int = 5) -> dict:
    fw = {w: 0.0 for w in common.FUNCTION_WORDS}
    fw.update({"the": 0.05, "a": 0.03, "and": 0.03, "i": 0.04, "it": 0.02})
    scope = {
        "n": 10,
        "features": {
            "line_words.median": _stats(5, 9), "line_words.pct_le4": _stats(0.2, 0.5), "sent_words.cv": _stats(0.5, 0.8),
            "sent_words.mean": _stats(8, 12), "hook.line1_chars": _stats(30, 70), "pov.i_per100": _stats(2, 6),
            "pov.you_per100": _stats(0, 3), "punct_per_1k.em_dash": _stats(0, 1), "punct_per_1k.en_dash": _stats(0, 0),
            "punct_per_1k.exclaim": _stats(0, 2), "punct_per_1k.ellipsis": _stats(0, 1),
            "lexicon.mean_word_len": _stats(4.0, 4.6), "lexicon.contraction_rate": _stats(0.01, 0.04),
            "lexicon.specificity_per100": _stats(4, 8), "n_chars": _stats(600, 1400),
            "pct_single_sentence_paras": _stats(0.4, 0.6),
        },
        "function_word_centroid": fw, "max_intra_distance": 0.2, "media_rate": 0.5,
    }
    self_scope = json.loads(json.dumps(scope))
    self_scope["n"] = self_n
    self_scope["features"]["sent_words.cv"] = _stats(0.9, 1.1)  # the user's own posts are far burstier
    self_scope["features"]["punct_per_1k.em_dash"] = _stats(0, 0)  # and never use em dashes
    return {"profile_version": 1, "scopes": {"corpus": scope, "self": self_scope}, "base_rates": {}}


def in_envelope_features() -> dict:
    fw = {w: 0.0 for w in common.FUNCTION_WORDS}
    fw.update({"the": 0.05, "a": 0.03, "and": 0.03, "i": 0.04, "it": 0.02})
    return {
        "n_chars": 1000, "n_sentences": 12, "line_words": {"median": 7, "pct_le4": 0.3},
        "sent_words": {"cv": 0.65, "mean": 10}, "hook": {"line1_chars": 50}, "pov": {"i_per100": 4, "you_per100": 1},
        "punct_per_1k": {"em_dash": 0.0, "en_dash": 0.0, "exclaim": 1, "ellipsis": 0},
        "lexicon": {"mean_word_len": 4.3, "contraction_rate": 0.02, "specificity_per100": 6},
        "function_words": fw, "pct_single_sentence_paras": 0.5,
    }


def test_envelope_without_profile():
    res = envelope_check.run_checks(in_envelope_features(), "corpus", None, CFG)
    assert set(res["checks"]) == {"E1_envelope", "P14_dashes", "P15_burstiness", "P16_broetry"}
    for c in res["checks"].values():
        assert c == {"class": "advisory", "pass": True, "note": "no profile"}
    assert res["envelope"]["score"] is None and res["envelope"]["out"] == []
    assert envelope_check.run_checks({}, "corpus", {"scopes": {}}, CFG)["checks"]["E1_envelope"]["class"] == "advisory"


def test_envelope_all_inside():
    profile = synthetic_profile(self_n=0)
    res = envelope_check.run_checks(in_envelope_features(), "corpus", profile, CFG)
    e1 = res["checks"]["E1_envelope"]
    assert e1["pass"] is True and e1["score"] == 1.0 and e1["out"] == [] and e1["evidence"] == []
    assert e1["class"] == "soft" and e1["threshold"] == 0.70 and e1["scope"] == "corpus"
    assert res["envelope"]["weights_total"] == 18.5 and res["envelope"]["skipped"] == []
    assert all(c["pass"] for c in res["checks"].values())
    assert res["checks"]["P14_dashes"]["value"] == 0.0 and res["checks"]["P16_broetry"]["scope_median"] == 0.5


def test_envelope_out_features_listed_with_bounds():
    profile = synthetic_profile(self_n=0)
    feat = in_envelope_features()
    feat["line_words"]["median"] = 19  # q1 5, q3 9 -> widened [3, 11]
    feat["lexicon"]["specificity_per100"] = 0.5  # [2, 10]
    feat["punct_per_1k"]["em_dash"] = 4.0  # [-0.5, 1.5]
    feat["function_words"] = {w: 0.0 for w in common.FUNCTION_WORDS} | {"you": 0.2, "your": 0.1}
    res = envelope_check.run_checks(feat, "corpus", profile, CFG)
    e1 = res["checks"]["E1_envelope"]
    out = {o["feature"]: o for o in e1["out"]}
    assert set(out) == {"line_words.median", "lexicon.specificity_per100", "punct_per_1k.em_dash",
                        "function_words.cosine_distance"}
    assert out["line_words.median"]["value"] == 19 and out["line_words.median"]["envelope"] == [3.0, 11.0]
    assert out["lexicon.specificity_per100"]["envelope"] == [2.0, 10.0]
    assert out["function_words.cosine_distance"]["envelope"] == [0.0, 0.2] and out["function_words.cosine_distance"]["value"] > 0.2
    assert e1["score"] == pytest.approx((18.5 - 2 - 2 - 1 - 2) / 18.5, abs=1e-4) and e1["pass"] is False
    assert len(e1["evidence"]) == 4 and "line_words.median=19" in e1["evidence"][0]["why"]
    p14 = res["checks"]["P14_dashes"]
    assert p14["pass"] is False and p14["value"] == 4.0 and p14["limit"] == 1.5 and p14["evidence"][0]["why"]


def test_envelope_register_features_use_self_scope():
    feat = in_envelope_features()  # cv 0.65 is inside corpus [0.35, 0.95] but outside self [0.8, 1.2]
    res = envelope_check.run_checks(feat, "corpus", synthetic_profile(self_n=5), CFG)
    assert res["envelope"]["register_scope"] == "self"
    out = {o["feature"]: o for o in res["checks"]["E1_envelope"]["out"]}
    assert set(out) == {"sent_words.cv"} and out["sent_words.cv"]["scope"] == "self"
    assert out["sent_words.cv"]["envelope"] == [0.8, 1.2]
    p15 = res["checks"]["P15_burstiness"]
    assert p15["pass"] is False and p15["scope"] == "self" and p15["limit"] == 0.9
    # a single em dash is fine for the corpus but not for a self scope that never uses them
    feat["punct_per_1k"]["em_dash"] = 0.8
    res = envelope_check.run_checks(feat, "corpus", synthetic_profile(self_n=5), CFG)
    assert res["checks"]["P14_dashes"]["pass"] is False and res["checks"]["P14_dashes"]["scope"] == "self"
    # self below self_min_samples -> everything against the lens scope
    res = envelope_check.run_checks(feat, "corpus", synthetic_profile(self_n=4), CFG)
    assert res["envelope"]["register_scope"] is None and res["checks"]["E1_envelope"]["score"] == 1.0
    assert res["checks"]["P14_dashes"]["pass"] is True and res["checks"]["P15_burstiness"]["pass"] is True
    # self_profile_scope=None disables the register comparison
    res = envelope_check.run_checks(feat, "corpus", synthetic_profile(self_n=5), CFG, self_profile_scope=None)
    assert res["envelope"]["register_scope"] is None


def test_envelope_p15_and_p16_rules():
    profile = synthetic_profile(self_n=0)
    feat = in_envelope_features()
    feat["sent_words"]["cv"] = 0.3  # below corpus q1 0.5
    res = envelope_check.run_checks(feat, "corpus", profile, CFG)
    assert res["checks"]["P15_burstiness"]["pass"] is False and "low burstiness" in res["checks"]["P15_burstiness"]["evidence"][0]["why"]
    feat["n_sentences"] = 3  # fewer than 4 sentences: P15 not judged, but sent_words.* still count in E1
    res = envelope_check.run_checks(feat, "corpus", profile, CFG)
    assert res["checks"]["P15_burstiness"]["pass"] is True and "not judged" in res["checks"]["P15_burstiness"]["note"]
    assert res["envelope"]["skipped"] == [] and "sent_words.cv" in {o["feature"] for o in res["checks"]["E1_envelope"]["out"]}
    feat["n_sentences"] = 2  # fewer than 3 sentences: sent_words.* skipped in E1 as well
    res = envelope_check.run_checks(feat, "corpus", profile, CFG)
    assert {s["feature"] for s in res["envelope"]["skipped"]} == {"sent_words.cv", "sent_words.mean"}
    feat = in_envelope_features()
    feat["pct_single_sentence_paras"] = 0.9
    res = envelope_check.run_checks(feat, "corpus", profile, CFG)
    assert res["checks"]["P16_broetry"]["pass"] is True  # scope median 0.5 >= 0.30: broetry is normal here
    profile["scopes"]["corpus"]["features"]["pct_single_sentence_paras"] = _stats(0.1, 0.3)  # median 0.2
    res = envelope_check.run_checks(feat, "corpus", profile, CFG)
    p16 = res["checks"]["P16_broetry"]
    assert p16["pass"] is False and p16["scope_median"] == 0.2 and "90%" in p16["evidence"][0]["why"]


def test_envelope_unknown_scope_falls_back_to_corpus_and_skips_nulls():
    profile = synthetic_profile(self_n=0)
    feat = in_envelope_features()
    feat["lexicon"]["contraction_rate"] = None
    feat["function_words"] = None
    res = envelope_check.run_checks(feat, "author:nobody", profile, CFG)
    e1 = res["checks"]["E1_envelope"]
    assert e1["scope"] == "corpus" and "author:nobody" in e1["notes"][0]
    assert {s["feature"] for s in res["envelope"]["skipped"]} == {"lexicon.contraction_rate", "function_words.cosine_distance"}
    assert res["envelope"]["weights_total"] == 15.5 and e1["score"] == 1.0


def test_envelope_against_fixture_profile(tmp_root: Path, monkeypatch):
    cfg = common.load_config()
    profile = profile_stats.build_profile(cfg)
    res = envelope_check.run_checks(post_features("broetry_li"), "author:lara-acosta", profile, cfg)
    e1 = res["checks"]["E1_envelope"]
    assert e1["pass"] is False and e1["scope"] == "author:lara-acosta" and res["envelope"]["register_scope"] is None
    out = {o["feature"]: o for o in e1["out"]}
    assert out["line_words.median"]["value"] == 6.0 and out["line_words.median"]["envelope"][0] > 6.0
    assert "lexicon.specificity_per100" in out and "punct_per_1k.em_dash" in out
    assert res["checks"]["P14_dashes"]["pass"] is False
    own = json.loads((tmp_root / "corpus" / "features" / "acosta_002.json").read_text())
    res = envelope_check.run_checks(own, "author:lara-acosta", profile, cfg)
    assert res["checks"]["E1_envelope"]["score"] >= 0.70 and res["checks"]["P16_broetry"]["pass"] is True


def test_envelope_cli(tmp_root: Path):
    run_cli("profile_stats.py", "--write", "--root", str(tmp_root))
    _, out = run_cli("envelope_check.py", "corpus/features/acosta_001.json", "--scope", "author:lara-acosta",
                     "--root", str(tmp_root))
    assert out["ok"] is True and out["envelope"]["scope"] == "author:lara-acosta"
    assert set(out["checks"]) == {"E1_envelope", "P14_dashes", "P15_burstiness", "P16_broetry"}
    _, out = run_cli("envelope_check.py", str(FIX / "posts" / "dense_x.md"), "--scope", "platform:x",
                     "--profile", "style/profile.json", "--root", str(tmp_root))
    assert out["ok"] is True and out["envelope"]["scope"] == "platform:x" and out["envelope"]["skipped"] == []
    _, out = run_cli("envelope_check.py", "missing.json", "--root", str(tmp_root))
    assert out["ok"] is False and "not found" in out["error"]
    _, out = run_cli("envelope_check.py", "corpus/features/acosta_001.json", "--profile", "nope.json", "--root", str(tmp_root))
    assert out["ok"] is False and "profile not found" in out["error"]


def test_imperatives_count_numbered_steps():
    """A numbered step is still an imperative: the ordinal marker is not the sentence's first word.

    Regression: `words("1) Go to LinkedIn.")[0]` is "1", so token-zero matching read every numbered
    instruction as a non-imperative and reported 0 for listicle authors.
    """
    text = "How I write good copy:\n\n1) Go to LinkedIn.\n\n2) Find a job description.\n\n3) Steal the words."
    feats = stylometry.features(text, "linkedin", "en", None, None, post_id="t_imp")
    assert feats["imperatives"] == 3
    assert stylometry._first_word("1) Go to LinkedIn.") == "go"
    assert stylometry._first_word("- Stop doing that") == "stop"
    assert stylometry._first_word("") == ""
