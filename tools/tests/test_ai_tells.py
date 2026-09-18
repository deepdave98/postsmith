"""Tests for tools/ai_tells.py, style/lexicon.yaml and evals/rubric/v1/patterns.yaml.

Fixtures under tools/tests/fixtures/ai-tells/ are the five slop posts (S1-S5) and five human posts
(P1-P5) of docs/design/research-ai-tells.md section 7, in golden format: front matter {platform, note}
plus text.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from ai_tells import CHECK_IDS, run_checks, summarize  # noqa: E402
from common import ROOT, load_config, load_lexicon, load_patterns, read_front_matter_file  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ai-tells"

EXPECTED_HARD = {
    "s1_broetry": {"P7_bait", "P8_opener", "P10_contrast_flip", "P11_cluster", "P13_specifics", "P17_lists"},
    "s2_x_unpopular": {"P10_contrast_flip", "P7_bait", "P8_opener", "P13_specifics"},
    "s3_claude_flavored": {"P10_contrast_flip", "P11_cluster", "P13_specifics"},
    "s4_x_reply_bot": {"P9_residue", "P11_cluster", "P13_specifics"},
    "s5_fake_vulnerability": {"P7_bait", "P12_closer", "P17_lists"},
}
CLEAN_HUMAN = ["p1_ffmpeg", "p3_cursor_for_x", "p5_claude_code_migration"]


@pytest.fixture(scope="module")
def env():
    return {"cfg": load_config(), "lex": load_lexicon(), "pats": load_patterns()}


def fixture(name: str) -> tuple[dict, str]:
    meta, body = read_front_matter_file(FIXTURES / f"{name}.md")
    return meta, body.rstrip("\n")


def run(env, text, platform="linkedin", meta=None, base_rates=None, cfg=None):
    return run_checks(text, platform, meta or {}, cfg or env["cfg"], env["lex"], env["pats"], base_rates)


def failing(checks: dict) -> dict[str, str]:
    return {cid: r["class"] for cid, r in checks.items() if not r["pass"]}


# --------------------------------------------------------------------------- lexicon and patterns files


def test_lexicon_shape():
    lex = load_lexicon()
    assert isinstance(lex["lexicon_version"], int) and lex["lexicon_version"] >= 1  # bumps whenever the lexicon grows
    tiers = lex["tiers"]
    for t in ("t1", "t2", "t3", "claude", "bait", "openers", "closers", "residue", "clickbait", "hedges"):
        assert t in tiers and len(tiers[t]) >= 20, t
        seen = set()
        for e in tiers[t]:
            assert isinstance(e, dict) and e.get("phrase") and "note" in e, (t, e)
            key = e["phrase"].lower()
            assert key not in seen, (t, key)
            seen.add(key)
            if e.get("regex"):
                re.compile(e["phrase"], re.IGNORECASE | re.MULTILINE)
    assert isinstance(lex["do_not_reuse"], dict)
    assert isinstance(lex["user_tells"], list)
    assert len(tiers["t1"]) >= 100 and len(tiers["claude"]) >= 30


def test_patterns_shape_and_known_false_positives():
    pats = load_patterns()["patterns"]
    ids = [p["id"] for p in pats]
    assert len(ids) == len(set(ids))
    kfp_checks = set()
    for p in pats:
        assert p["id"].startswith(p["check"] + "."), p["id"]
        assert p["check"] in CHECK_IDS, p["check"]
        assert p.get("explanation")
        flags = p.get("flags", "i") or ""
        rx = re.compile(p["regex"], (re.IGNORECASE if "i" in flags else 0) | re.MULTILINE)
        if p.get("known_false_positive"):
            kfp_checks.add(p["check"])
            assert rx.search(p["known_false_positive"]), f"{p['id']} does not match its own known_false_positive"
    assert {"P8_opener", "P10_contrast_flip", "P12_closer", "P17_lists"} <= kfp_checks
    texts = " || ".join(p.get("known_false_positive") or "" for p in pats)
    assert "Not a success story. Just cheaper." in texts
    assert "Hot take nobody asked for" in texts
    for check in ("P8_opener", "P10_contrast_flip", "P12_closer", "P17_lists", "P19_clickbait", "P20_misc"):
        assert any(p["check"] == check for p in pats), check
    subs = {p["id"].split(".", 1)[1] for p in pats if p["check"] == "P20_misc"}
    assert {"hypophora", "ing_rider", "copula_avoidance", "colon_reveal", "meta_signposting", "false_range"} <= subs


# --------------------------------------------------------------------------- research posts S1-S5 / P1-P5


@pytest.mark.parametrize("name", sorted(EXPECTED_HARD))
def test_slop_posts_produce_expected_hard_fails(env, name):
    meta, text = fixture(name)
    out = run(env, text, meta["platform"], meta)
    assert set(out["checks"]) == set(CHECK_IDS)
    hard = set(summarize(out["checks"])["hard_fails"])
    missing = EXPECTED_HARD[name] - hard
    assert not missing, f"{name}: missing hard fails {missing}; got {hard}"


@pytest.mark.parametrize("name", CLEAN_HUMAN)
def test_human_posts_are_clean(env, name):
    meta, text = fixture(name)
    out = run(env, text, meta["platform"], meta)
    s = summarize(out["checks"])
    assert s["hard_fails"] == [], (name, failing(out["checks"]))
    assert s["soft_fails"] == [] and s["flags"] == [], (name, failing(out["checks"]))


def test_p2_trips_only_p10_with_jury_override(env):
    meta, text = fixture("p2_not_a_success_story")
    out = run(env, text, meta["platform"], meta)
    assert failing(out["checks"]) == {"P10_contrast_flip": "hard"}
    r = out["checks"]["P10_contrast_flip"]
    assert r["jury_override_allowed"] is True
    assert r["evidence"][0]["span"] == "Not a success story. Just cheaper"
    assert r["evidence"][0]["known_false_positive"] is True


def test_p4_trips_only_p8_with_jury_override(env):
    meta, text = fixture("p4_hot_take_nobody_asked")
    out = run(env, text, meta["platform"], meta)
    assert failing(out["checks"]) == {"P8_opener": "hard"}
    r = out["checks"]["P8_opener"]
    assert r["jury_override_allowed"] is True
    assert r["evidence"][0]["span"] == "Hot take"
    assert r["evidence"][0]["pattern"] == "P8_opener.hot_take"


def test_s3_cluster_is_claude_driven(env):
    meta, text = fixture("s3_claude_flavored")
    r = run(env, text, meta["platform"], meta)["checks"]["P11_cluster"]
    assert r["counts"]["claude"] >= 2 and any("Claude" in x for x in r["rule"])
    assert {"The honest answer", "Structurally", "genuinely", "nuanced", "Put differently", "This matters because"} <= set(r["claude"])


def test_s5_closer_and_anaphora(env):
    meta, text = fixture("s5_fake_vulnerability")
    checks = run(env, text, meta["platform"], meta)["checks"]
    assert checks["P12_closer"]["jury_override_allowed"] is True
    assert "The lesson" in [e["span"] for e in checks["P12_closer"]["evidence"]]
    assert checks["P17_lists"]["list_forms"] == ["anaphora_triple"]
    assert checks["P7_bait"]["evidence"][-1]["span"] == "Repost if"


def test_s1_list_forms_and_opener(env):
    meta, text = fixture("s1_broetry")
    checks = run(env, text, meta["platform"], meta)["checks"]
    assert {"emoji_bullets", "templated_lines"} <= set(checks["P17_lists"]["list_forms"])
    assert checks["P17_lists"]["tricolons"] == 1
    assert checks["P8_opener"]["evidence"][0]["line"] == 1
    assert len(checks["P10_contrast_flip"]["evidence"]) == 4
    assert checks["P20_misc"]["fired"] == ["hypophora"]


# --------------------------------------------------------------------------- evidence spans


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.md")), ids=lambda p: p.stem)
def test_evidence_spans_are_verbatim(env, path):
    meta, body = read_front_matter_file(path)
    text = body.rstrip("\n")
    out = run(env, text, meta["platform"], meta)
    for cid, r in out["checks"].items():
        for ev in r["evidence"]:
            assert text[ev["start"]:ev["end"]] == ev["span"], (cid, ev)
            assert ev["span"] in text and ev["why"]
            assert ev["line"] == text.count("\n", 0, ev["start"]) + 1
    for tier, hits in out["hits"].items():
        for h in hits:
            assert text[h["start"]:h["end"]] == h["span"], (tier, h)


def test_curly_quotes_and_nfkc_map_back_to_original(env):
    text = "The ﬁrst run: it’s not about the model, it’s about the workﬂow. “Agree?” he asked on March 3."
    checks = run(env, text)["checks"]
    span = checks["P10_contrast_flip"]["evidence"][0]["span"]
    assert span.startswith("it’s not about the model, it’s about the") and span in text
    bait = checks["P7_bait"]["evidence"][0]["span"]
    assert bait == "Agree?" and text.count(bait) == 1
    assert checks["P13_specifics"]["pass"] is True


# --------------------------------------------------------------------------- P11 cluster thresholds


def test_cluster_three_t1_hits_is_hard(env):
    r = run(env, "We should delve into the landscape and leverage this. It is a testament to the 3 people who built it.")["checks"]["P11_cluster"]
    assert r["pass"] is False and r["class"] == "hard" and r["counts"]["t1"] >= 3


def test_cluster_five_across_tiers_is_hard_but_four_is_not(env):
    five = "This is crucial and pivotal work with a robust, seamless ecosystem, tested on 3 laptops."
    r = run(env, five)["checks"]["P11_cluster"]
    assert r["counts"]["t1"] < 3 and r["counts"]["total"] >= 5 and r["pass"] is False
    four = "This is crucial and pivotal work with a robust ecosystem, tested on 3 laptops."
    r = run(env, four)["checks"]["P11_cluster"]
    assert r["counts"]["total"] == 4 and r["pass"] is True and r["evidence"] == []


def test_cluster_two_claude_tics_is_hard_single_hit_reported_only(env):
    r = run(env, "Genuinely, the fix is structurally simple: bump the timeout to 30s.")["checks"]["P11_cluster"]
    assert r["pass"] is False and r["counts"]["claude"] == 2
    out = run(env, "Genuinely the fix was to bump the timeout to 30s.")
    assert out["checks"]["P11_cluster"]["pass"] is True
    assert [h["span"] for h in out["hits"]["claude"]] == ["Genuinely"]
    assert out["checks"]["P11_cluster"]["claude"] == ["Genuinely"]


def test_cluster_dedupes_overlapping_phrases(env):
    out = run(env, "In today's fast-paced world we ship on Tuesdays.")
    spans = [h["span"] for t in out["hits"].values() for h in t]
    assert spans == ["In today's fast-paced world"]  # "fast-paced" (t2) is inside the t1 span, counted once


# --------------------------------------------------------------------------- base-rate downgrade


def test_base_rate_downgrade_hard_to_flag_and_never_list(env):
    meta, text = fixture("s2_x_unpopular")
    rates = {"P8_opener": 0.5, "P10_contrast_flip": 0.3, "P7_bait": 0.9, "P13_specifics": 0.9, "P9_residue": 0.9}
    checks = run(env, text, "x", meta, base_rates=rates)["checks"]
    for cid in ("P8_opener", "P10_contrast_flip"):
        r = checks[cid]
        assert r["class"] == "flag" and r["class_original"] == "hard" and r["downgraded"] is True
        assert r["pass"] is False and r["base_rate"] == rates[cid]
    for cid in ("P7_bait", "P13_specifics"):  # in `never`
        assert checks[cid]["class"] == "hard" and checks[cid]["downgraded"] is False
    assert checks["P9_residue"]["downgraded"] is False  # not in applies_to
    s = summarize(checks)
    assert set(s["hard_fails"]) == {"P7_bait", "P13_specifics"} and set(s["flags"]) == {"P8_opener", "P10_contrast_flip"}


def test_base_rate_at_threshold_does_not_downgrade(env):
    meta, text = fixture("s2_x_unpopular")
    checks = run(env, text, "x", meta, base_rates={"P8_opener": 0.25})["checks"]
    assert checks["P8_opener"]["class"] == "hard" and checks["P8_opener"]["downgraded"] is False
    checks = run(env, text, "x", meta, base_rates=None)["checks"]
    assert checks["P8_opener"]["downgraded"] is False


def test_base_rate_downgrade_soft_to_advisory(env):
    text = "We tested it fast, cheap, and loud. Version 2 lands Friday."
    r = run(env, text, base_rates={"P17_lists": 0.6})["checks"]["P17_lists"]
    assert r["class"] == "advisory" and r["class_original"] == "soft" and r["downgraded"] is True


# --------------------------------------------------------------------------- P13 specifics


def test_p13_empty_post_fails(env):
    r = run(env, "")["checks"]["P13_specifics"]
    assert r["pass"] is False and r["class"] == "hard" and r["words"] == 0


GENERIC_26 = ("most teams think the problem is the model when the actual problem is the workflow around the model "
              "and the people who never look at outputs")


def test_p13_platform_floors(env):
    assert run(env, GENERIC_26, "x")["checks"]["P13_specifics"]["pass"] is False
    assert run(env, GENERIC_26, "linkedin")["checks"]["P13_specifics"]["pass"] is True
    long_generic = GENERIC_26 + " and the way they " * 6
    r = run(env, long_generic, "linkedin")["checks"]["P13_specifics"]
    assert r["pass"] is False and r["words"] > 40 and "zero specifics" in r["evidence"][0]["why"]
    cfg = dict(env["cfg"], ai_tells={"specifics_min_words": 10})
    assert run(env, GENERIC_26, "linkedin", cfg=cfg)["checks"]["P13_specifics"]["pass"] is False


@pytest.mark.parametrize("text, kind", [
    ("most teams never look at outputs until a customer does, which took us 3 weeks " * 3, "number"),
    ("most teams never look at outputs until a customer does, and ours paid $40 for it " * 3, "currency_or_percent"),
    ("most teams never look at outputs until a customer does, and ours did in March " * 3, "month"),
    ("most teams never look at outputs until a customer does, and ours lives in config/postsmith.yaml " * 3, "path"),
    ("most teams never look at outputs until a customer does, and ours threw a KeyError " * 3, "error_like"),
    ("most teams never look at outputs until a customer does, and ours runs on ffmpeg " * 3, "product"),
    ("most teams never look at outputs until a customer does, and ours was Acme " * 3, "proper_noun"),
    ("most teams never look at outputs until a customer does, and ours was on OpenTable " * 3, "proper_noun"),
    ("most teams never look at outputs until a customer does, and ours was on LinkedIn " * 3, "product"),
])
def test_p13_specific_kinds(env, text, kind):
    r = run(env, text)["checks"]["P13_specifics"]
    assert r["pass"] is True and r["words"] > 40
    assert kind in {s["kind"] for s in r["specifics"]}


def test_p13_sentence_initial_and_generic_caps_are_not_specifics(env):
    text = ("Teams never look at outputs. Everyone assumes the workflow is fine. The AI and the LLM are blamed, "
            "the SDR is blamed, the CEO is blamed, and nobody opens the log until a customer does. Nobody. Ever. "
            "Then the whole team acts surprised when the customer leaves and blames the model again.")
    r = run(env, text)["checks"]["P13_specifics"]
    assert r["words"] > 40 and r["pass"] is False


# --------------------------------------------------------------------------- P17 lists


def test_p17_one_tricolon_soft_two_hard(env):
    one = "We tested it fast, cheap, and loud. Version 2 lands Friday."
    r = run(env, one)["checks"]["P17_lists"]
    assert r["class"] == "soft" and r["pass"] is False and r["tricolons"] == 1
    assert r["jury_override_allowed"] is True  # the tricolon pattern declares a known false positive
    two = one + " Then we shipped it hot, cold, and sideways."
    r = run(env, two)["checks"]["P17_lists"]
    assert r["class"] == "hard" and r["pass"] is False and r["tricolons"] == 2


def test_p17_list_forms_are_hard(env):
    term = "Speed: we cut build time to 4 minutes.\nCost: $12 a month.\nRisk: none so far."
    assert run(env, term)["checks"]["P17_lists"]["list_forms"] == ["term_description"]
    emoji = "Three things shipped on the 4th:\n🚀 faster builds\n💡 cheaper tests\n🔥 fewer pages"
    assert "emoji_bullets" in run(env, emoji)["checks"]["P17_lists"]["list_forms"]
    anaphora = "I was humbled. I was broken. I was lost. Then the 4th rejection came."
    r = run(env, anaphora)["checks"]["P17_lists"]
    assert r["class"] == "hard" and r["list_forms"] == ["anaphora_triple"] and r["jury_override_allowed"] is True


def test_p17_triple_with_specifics_is_not_a_tricolon(env):
    _meta, text = fixture("p3_cursor_for_x")
    assert run(env, text, "x")["checks"]["P17_lists"]["pass"] is True
    assert run(env, "we paid $40, $400, and $4,000 for the same thing")["checks"]["P17_lists"]["pass"] is True


def test_p17_device_declares_comic_triple(env):
    text = "We tested it fast, cheap, and loud. Version 2 lands Friday."
    meta = {"assignment": {"device": "rule_of_three_escalation"}}
    assert run(env, text, meta=meta)["checks"]["P17_lists"]["jury_override_allowed"] is True


# --------------------------------------------------------------------------- P7, P8, P9, P12, P18, P19, P20


def test_p7_bait_patterns(env):
    r = run(env, "Comment GUIDE and I'll DM you the 12-page pdf.")["checks"]["P7_bait"]
    assert r["pass"] is False and r["evidence"][0]["span"] == "Comment GUIDE and I'll DM"
    assert run(env, "We shipped v2 on the 4th and nobody noticed.")["checks"]["P7_bait"]["pass"] is True


def test_p8_only_line_one_counts(env):
    text = "We shipped v2 on the 4th.\nUnpopular opinion: nobody noticed."
    checks = run(env, text)["checks"]
    assert checks["P8_opener"]["pass"] is True
    assert [h["span"] for h in run(env, text)["hits"]["t1"]] == ["Unpopular opinion"]
    text = "🚀 Unpopular opinion: nobody noticed v2 on the 4th."
    r = run(env, text)["checks"]["P8_opener"]
    assert r["pass"] is False and r["evidence"][0]["span"].endswith("Unpopular opinion")


def test_p9_residue_and_placeholders(env):
    r = run(env, "Big news from [Company]! I hope this helps. Want me to draft the 3 follow-ups?")["checks"]["P9_residue"]
    spans = [e["span"] for e in r["evidence"]]
    assert r["pass"] is False and "[Company]" in spans and "I hope this helps" in spans and "Want me to" in spans


def test_p12_regex_is_hard_heuristic_is_flag(env):
    hard = "We rewrote one 40-line prompt.\nExtraction errors fell 31%.\nIn conclusion, prompts matter."
    r = run(env, hard)["checks"]["P12_closer"]
    assert r["class"] == "hard" and r["pass"] is False and r["jury_override_allowed"] is True
    flag = "We rewrote one 40-line prompt.\nExtraction errors fell 31%.\nConsistency beats intensity."
    r = run(env, flag)["checks"]["P12_closer"]
    assert r["class"] == "flag" and r["pass"] is False and r["evidence"][0]["span"] == "Consistency beats intensity."
    assert r["regex_hits"] == 0 and r["heuristic_flags"] == 1
    early = "Ultimately this is the intro.\nWe rewrote one 40-line prompt.\nExtraction errors fell 31%.\nThe last line mattered most."
    assert run(env, early)["checks"]["P12_closer"]["pass"] is True  # closer regex only looks at the last two lines


def test_p12_restatement_of_opener_flags(env):
    text = ("Dedup your documents before you touch the embedding model.\nWe found 39,000 duplicates at one bank.\n"
            "The 2014 policy had been rescinded 4 times.\nAlways dedup your documents before you touch the embedding model.")
    r = run(env, text)["checks"]["P12_closer"]
    assert r["class"] == "flag" and any("restates the opener" in e["why"] for e in r["evidence"])


def test_p18_hedges_soft_at_three(env):
    text = "It might work. It may help. It could potentially scale for teams of 12."
    r = run(env, text)["checks"]["P18_hedges"]
    assert r["class"] == "soft" and r["pass"] is False and r["count"] >= 3
    assert run(env, "It might work for teams of 12.")["checks"]["P18_hedges"]["pass"] is True


def test_p19_hard_on_x_soft_on_linkedin(env):
    text = "BREAKING: the 4.2 release drops Friday 🚨"
    assert run(env, text, "x")["checks"]["P19_clickbait"]["class"] == "hard"
    r = run(env, text, "linkedin")["checks"]["P19_clickbait"]
    assert r["class"] == "soft" and r["pass"] is False
    assert run(env, "the 4.2 release drops Friday", "x")["checks"]["P19_clickbait"]["pass"] is True


def test_p20_each_sub_pattern_is_its_own_flag(env):
    text = ("The build has a name: Rosie. Why? Because it serves as a reminder, highlighting the importance of naming. "
            "The most important part: from intimate gatherings to global movements, 12 teams use it.")
    r = run(env, text)["checks"]["P20_misc"]
    assert r["class"] == "soft" and r["pass"] is False
    assert r["fired"] == ["colon_reveal", "copula_avoidance", "false_range", "hypophora", "ing_rider", "meta_signposting"]
    assert r["sub"]["hypophora"]["evidence"][0]["span"] == "Why? Because"
    assert r["sub"]["false_range"]["evidence"][0]["span"] == "from intimate gatherings to global movements"
    clean = run(env, "We renamed the build to Rosie on the 4th because the old name was a slur in Dutch.")["checks"]["P20_misc"]
    assert clean["pass"] is True and all(s["pass"] for s in clean["sub"].values())


# --------------------------------------------------------------------------- CLI


def test_cli_json_output_and_errors(tmp_path):
    tool = TOOLS / "ai_tells.py"
    proc = subprocess.run([sys.executable, str(tool), str(FIXTURES / "s2_x_unpopular.md"), "--json",
                           "--base-rates", "none"], capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["ok"] is True and out["platform"] == "x" and set(out["checks"]) == set(CHECK_IDS)
    assert {"P7_bait", "P8_opener", "P10_contrast_flip", "P13_specifics"} <= set(out["summary"]["hard_fails"])

    proc = subprocess.run([sys.executable, str(tool), str(tmp_path / "missing.md"), "--platform", "x", "--json"],
                          capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0 and json.loads(proc.stdout) == {"ok": False, "error": f"file not found: {tmp_path / 'missing.md'}"}

    plain = tmp_path / "post.txt"
    plain.write_text("spent 4 hours on ffmpeg.\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(tool), str(plain), "--json"], capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0 and json.loads(proc.stdout)["ok"] is False  # platform required for plain text

    proc = subprocess.run([sys.executable, str(tool), str(plain), "--platform", "x"], capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0 and "P13_specifics" in proc.stdout and "hard: []" in proc.stdout
    proc = subprocess.run([sys.executable, str(tool), "--help"], capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0 and "--platform" in proc.stdout
