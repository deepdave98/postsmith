"""Tests for tools/platform_check.py and tools/xcount.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import platform_check as pc
import xcount
from common import load_config, split_front_matter, x_count

FIX = Path(__file__).resolve().parent / "fixtures" / "platform"
CFG = load_config()
_ORIG_LOAD = pc.load_persona_choices  # captured before the autouse fixture patches it


@pytest.fixture(autouse=True)
def _no_persona(monkeypatch):
    """Keep tests independent of whatever style/persona.md says on this machine."""
    monkeypatch.setattr(pc, "load_persona_choices", lambda path=None: {})


def run(text: str, platform: str = "linkedin", meta: dict | None = None) -> dict:
    return pc.run_checks(text, platform, meta or {}, CFG)


def fixture(name: str) -> tuple[dict, str]:
    return split_front_matter((FIX / name).read_text(encoding="utf-8"))


def cli(script: str, *args: str, stdin: str | None = None) -> dict:
    proc = subprocess.run(
        [sys.executable, str(TOOLS / script), *args], capture_output=True, text=True, input=stdin, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------- contract shape


def test_result_shape_matches_contract():
    meta, body = fixture("li_good.md")
    res = run(body, "linkedin", meta)
    for key in ("checks", "chars", "x_len", "fold_preview", "advisory"):
        assert key in res
    assert set(res["checks"]) == set(pc.CHECK_IDS)
    for cid, r in res["checks"].items():
        assert r["class"] in {"hard", "soft", "flag", "advisory"}, cid
        assert isinstance(r["pass"], bool)
        assert isinstance(r["evidence"], list)
        assert r["downgraded"] is False
        if not r["pass"]:
            assert r["evidence"], f"{cid} fails without evidence"
    assert res["x_len"] is None
    assert res["chars"] == len(body.rstrip("\n"))


def test_evidence_spans_are_verbatim():
    _, body = fixture("markup_leak.txt")
    res = run(body, "linkedin", {"corpus_uses_straight_quotes": True})
    text = body.rstrip("\n")
    for cid, r in res["checks"].items():
        for ev in r["evidence"]:
            assert ev["span"] in text, (cid, ev)


def test_bad_platform_raises():
    with pytest.raises(ValueError):
        run("hello", "threads")
    with pytest.raises(TypeError):
        run(None, "x")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- LinkedIn fold (P2)


def test_fold_boundary_inside_140_passes_and_preview_is_three_lines():
    meta, body = fixture("li_good.md")
    res = run(body, "linkedin", meta)
    p2 = res["checks"]["P2_fold"]
    assert p2["pass"] is True and p2["class"] == "hard" and p2["flag"] is False
    assert res["fold_preview"] == "We killed our AI strategy last week.\n\nNobody noticed."
    assert p2["preview"] == res["fold_preview"]
    assert p2["cut_at"] == 140
    assert p2["mobile"]["cut_by"] == "lines"
    assert p2["mobile"]["blank_lines_in_fold"] == 1
    assert p2["mobile"]["lines_in_fold"] == 3
    assert p2["mobile"]["boundary_within"] is True
    assert p2["desktop"]["cut_at"] == 210
    assert p2["desktop"]["preview"] == res["fold_preview"]


def test_fold_midword_without_boundary_is_hard_fail():
    _, body = fixture("li_midword_fail.txt")
    p2 = run(body)["checks"]["P2_fold"]
    assert p2["class"] == "hard" and p2["pass"] is False
    assert p2["mobile"]["cut_by"] == "chars"
    assert p2["mobile"]["mid_word"] is True
    assert p2["mobile"]["boundary_within"] is False
    assert "mid-word" in p2["evidence"][0]["why"]
    assert len(p2["preview"]) == 140
    # the desktop cut (210) reaches the line break after line 1, which is a boundary
    assert p2["desktop"]["boundary_within"] is True
    assert p2["desktop"]["boundary"]["span"] == "\\n"


def test_fold_word_boundary_without_clause_boundary_is_flag():
    text = "abcd " * 28 + "efgh ijkl. " + "tail " * 20  # cut at index 140 lands right before 'e'
    p2 = run(text)["checks"]["P2_fold"]
    assert p2["class"] == "flag" and p2["pass"] is True and p2["flag"] is True
    assert p2["mobile"]["mid_word"] is False
    assert p2["mobile"]["boundary_within"] is False
    assert p2["evidence"] and "word boundary" in p2["evidence"][0]["why"]
    assert p2["preview"] == ("abcd " * 28).rstrip()


def test_fold_midword_cut_with_earlier_boundary_passes():
    text = "Short hook. " + "abcdefghij" * 20
    p2 = run(text)["checks"]["P2_fold"]
    assert p2["pass"] is True and p2["class"] == "hard"
    assert p2["mobile"]["mid_word"] is True
    assert p2["mobile"]["boundary"]["span"] == "."


def test_fold_decimal_point_is_not_a_boundary():
    text = "x" * 137 + " 3.5 more words follow here"
    p2 = run(text)["checks"]["P2_fold"]
    assert p2["mobile"]["boundary_within"] is False
    assert p2["mobile"]["mid_word"] is False
    assert p2["class"] == "flag"


def test_fold_colon_and_semicolon_count_as_boundaries():
    for punct in (":", ";", "!", "?"):
        text = f"A thing happened{punct} " + "y" * 200
        p2 = run(text)["checks"]["P2_fold"]
        assert p2["pass"] is True and p2["class"] == "hard", punct


def test_fold_blank_lines_consume_lines():
    text = "Line one.\n\n\nLine four is the rest of the post and it keeps going for a while."
    p2 = run(text)["checks"]["P2_fold"]
    assert p2["preview"] == "Line one."
    assert p2["mobile"]["cut_by"] == "lines"
    assert p2["mobile"]["blank_lines_in_fold"] == 2
    assert p2["pass"] is True


def test_fold_short_post_has_no_cut():
    text = "One line.\nTwo lines."
    p2 = run(text)["checks"]["P2_fold"]
    assert p2["mobile"]["cut_by"] is None
    assert p2["preview"] == text
    assert p2["pass"] is True


def test_fold_desktop_cut_reported_independently():
    text = "y" * 150 + ". And then the rest of the sentence continued " + "z" * 100
    p2 = run(text)["checks"]["P2_fold"]
    assert p2["mobile"]["boundary_within"] is False and p2["class"] == "hard" and p2["pass"] is False
    assert p2["desktop"]["boundary_within"] is True
    assert len(p2["desktop"]["preview"]) == 210


def test_fold_emoji_count_two_units():
    assert pc.display_cut_index("\U0001F525\U0001F525a", 3) == 1
    assert pc.display_cut_index("ab\U0001F525c", 3) == 2
    assert pc.display_cut_index("abc", 10) == 3
    text = "\U0001F525" * 70 + " still going " + "w" * 100
    p2 = run(text)["checks"]["P2_fold"]
    assert p2["preview"] == "\U0001F525" * 70


# --------------------------------------------------------------------------- X counting and fold


def test_x_count_url_emoji_cjk():
    text = "check https://example.com/a/very/long/path/that/goes/on \U0001F525 日本"
    assert x_count(text, CFG["platforms"]["x"]) == 6 + 23 + 1 + 2 + 1 + 4
    assert xcount.count(text)["x_len"] == 37
    res = run(text, "x")
    assert res["x_len"] == 37 and res["chars"] == len(text)


def test_x_fits_passes_and_preview_is_whole_post():
    meta, body = fixture("x_good.md")
    res = run(body, "x", meta)
    assert res["checks"]["P1_length"]["pass"] is True
    assert res["checks"]["P1_length"]["limit"] == 280
    assert res["checks"]["P2_fold"]["pass"] is True
    assert res["fold_preview"] == body.rstrip("\n")
    assert res["advisory"]["li_length_band"] is None


def test_x_over_280_without_long_posts_fails_length_and_fold():
    text = "y" * 300
    res = run(text, "x")
    p1, p2 = res["checks"]["P1_length"], res["checks"]["P2_fold"]
    assert p1["pass"] is False and p1["value"] == 300 and p1["limit"] == 280 and p1["long_post"] is False
    assert p2["pass"] is False and p2["ends_at_sentence"] is False
    assert len(p2["preview"]) == 280


def test_x_long_post_allowed_when_first_280_ends_at_sentence():
    text = "x" * 278 + ". " + "and the optional remainder goes on after the fold."
    meta = {"platform_choices": {"x": {"long_posts": True}}}
    res = run(text, "x", meta)
    p1, p2 = res["checks"]["P1_length"], res["checks"]["P2_fold"]
    assert res["policy"]["long_posts"] is True and res["policy"]["sources"]["long_posts"] == "meta"
    assert p1["pass"] is True and p1["long_post"] is True and p1["limit"] == 25000
    assert p2["pass"] is True and p2["ends_at_sentence"] is True
    assert p2["preview"] == "x" * 278 + "."


def test_x_long_post_allowed_but_bad_cut_fails_fold():
    text = "y" * 300
    res = run(text, "x", {"platform_choices": {"long_posts": True}})
    assert res["checks"]["P1_length"]["pass"] is True
    assert res["checks"]["P2_fold"]["pass"] is False
    assert res["checks"]["P2_fold"]["long_posts_allowed"] is True


def test_x_long_post_line_break_at_cut_counts_as_boundary():
    text = "w" * 280 + "\nsecond paragraph after the fold"
    res = run(text, "x", {"platform_choices": {"x_long_posts": True}})
    assert res["checks"]["P2_fold"]["pass"] is True


def test_x_cut_index_treats_url_as_atomic():
    xcfg = CFG["platforms"]["x"]
    text = "a" * 270 + " https://example.com/path tail"
    cut = pc.x_cut_index(text, 280, xcfg)
    assert text[:cut] == "a" * 270 + " "


# --------------------------------------------------------------------------- P1 LinkedIn length, P_min_words


def test_linkedin_over_3000_fails():
    text = "Hook line.\n\n" + ("word " * 700)
    p1 = run(text)["checks"]["P1_length"]
    assert p1["pass"] is False and p1["limit"] == 3000 and p1["value"] > 3000
    assert p1["evidence"][0]["span"] in text


def test_min_words_defaults():
    assert run("Three words here.")["checks"]["P_min_words"]["pass"] is False
    assert run("")["checks"]["P_min_words"]["pass"] is False
    assert run("no.", "x")["checks"]["P_min_words"]["pass"] is False
    assert run("ship it.", "x")["checks"]["P_min_words"]["pass"] is True
    ok = run("Eight words are enough for this simple check.")["checks"]["P_min_words"]
    assert ok["pass"] is True and ok["min"] == 8


def test_min_words_from_persona_choices():
    res = run("Five words is fine here.", "linkedin", {"platform_choices": {"linkedin": {"min_words": 5}}})
    assert res["checks"]["P_min_words"]["pass"] is True


# --------------------------------------------------------------------------- P3 hashtags


def test_hashtags_linkedin_within_max_passes_with_note():
    p3 = run("We shipped the thing. #buildinpublic #ai and it went fine, mostly.")["checks"]["P3_hashtags"]
    assert p3["pass"] is True and p3["count"] == 2 and p3["max"] == 3 and p3["note"]
    assert p3["tags"] == ["#buildinpublic", "#ai"]


def test_hashtags_linkedin_over_max_fails():
    p3 = run("Four tags in one line of a post that says nothing #a #b #c #d")["checks"]["P3_hashtags"]
    assert p3["pass"] is False and p3["count"] == 4


def test_hashtag_block_at_end_fails_linkedin():
    text = "We shipped the thing and it went fine, mostly.\n\n#AI #Startups #Leadership"
    p3 = run(text)["checks"]["P3_hashtags"]
    assert p3["pass"] is False and p3["block"] is True
    assert p3["evidence"][0]["span"] == "#AI #Startups #Leadership"


def test_hashtag_single_trailing_tag_is_not_a_block():
    p3 = run("We shipped the thing and it went fine, mostly.\n\n#buildinpublic")["checks"]["P3_hashtags"]
    assert p3["block"] is False and p3["pass"] is True and p3["count"] == 1


def test_hashtags_x_any_fails():
    p3 = run("shipped it. #buildinpublic", "x")["checks"]["P3_hashtags"]
    assert p3["pass"] is False and p3["max"] == 0


def test_hashtags_persona_zero_policy():
    meta = {"platform_choices": {"hashtags_never": True}}
    p3 = run("We shipped the thing and it went fine. #ai", "linkedin", meta)["checks"]["P3_hashtags"]
    assert p3["pass"] is False and p3["max"] == 0


def test_number_sign_is_not_a_hashtag():
    p3 = run("We were #1 on the board and C# was involved somehow, sadly.")["checks"]["P3_hashtags"]
    assert p3["count"] == 0 and p3["pass"] is True


# --------------------------------------------------------------------------- P4 links


def test_x_url_in_body_fails_and_reports_reply_1():
    meta, body = fixture("x_with_url.md")
    p4 = run(body, "x", meta)["checks"]["P4_links"]
    assert p4["pass"] is False and p4["class"] == "hard" and p4["count"] == 1
    assert p4["reply_1_present"] is True
    assert "reply_1" in p4["evidence"][0]["why"]
    assert p4["evidence"][0]["span"] == "https://floqer.com/blog/agents-buying-domains"


def test_x_bare_domain_counts_as_link():
    p4 = run("the writeup is on floqer.com if you want the receipts.", "x")["checks"]["P4_links"]
    assert p4["pass"] is False and p4["links"] == ["floqer.com"]
    assert p4["reply_1_present"] is False


def test_x_no_link_passes():
    meta, body = fixture("x_good.md")
    assert run(body, "x", meta)["checks"]["P4_links"]["pass"] is True


def test_linkedin_single_naked_link_is_advisory():
    text = "We wrote it up in detail here https://floqer.com/blog/agents and the short version is: it worked."
    p4 = run(text)["checks"]["P4_links"]
    assert p4["class"] == "advisory" and p4["pass"] is True and p4["count"] == 1 and p4["note"]


def test_linkedin_two_links_pass():
    text = "Sources: https://a.example.com/one and https://b.example.com/two make the case better than I can."
    p4 = run(text)["checks"]["P4_links"]
    assert p4["class"] == "hard" and p4["pass"] is True and p4["count"] == 2


@pytest.mark.parametrize("phrase", ["Link in comments.", "link in the comments", "Link's in the first comment", "links are in the comments below"])
def test_link_in_comments_phrase_is_hard_fail_on_both(phrase):
    text = f"We shipped the thing and it went fine, mostly. {phrase}"
    for platform in ("linkedin", "x"):
        p4 = run(text, platform)["checks"]["P4_links"]
        assert p4["pass"] is False and p4["class"] == "hard", (platform, phrase)


def test_email_and_filenames_are_not_links():
    p4 = run("mail me at hey@example.com and run deploy.sh before you read setup.py, please.", "x")["checks"]["P4_links"]
    assert p4["count"] == 0 and p4["pass"] is True


# --------------------------------------------------------------------------- P5 markup


def test_markup_leak_fixture_hits_every_kind():
    _, body = fixture("markup_leak.txt")
    p5 = run(body)["checks"]["P5_markup"]
    assert p5["pass"] is False
    expected = {"markdown_bold", "markdown_header", "markdown_code", "markdown_link", "unicode_math_letters",
                "placeholder", "leaked_label", "leaked_variant_label", "citation_artifact", "char_count_note"}
    assert expected <= set(p5["kinds"])
    spans = [e["span"] for e in p5["evidence"]]
    assert "[Your Name]" in spans and "[Company]" in spans and "turn0search3" in spans and "(≈280 chars)" in spans


def test_markup_clean_text_passes():
    _, body = fixture("li_clean_text.txt")
    p5 = run(body)["checks"]["P5_markup"]
    assert p5["pass"] is True, p5["evidence"]


def test_curly_quotes_only_when_corpus_uses_straight():
    text = "We didn’t ship it. “Later,” they said, and later never came for anyone."
    assert run(text)["checks"]["P5_markup"]["pass"] is True
    p5 = run(text, "linkedin", {"corpus_uses_straight_quotes": True})["checks"]["P5_markup"]
    assert p5["pass"] is False and "curly_quotes" in p5["kinds"]


def test_leaked_labels_at_line_start_only():
    assert run("Hook: we shipped it.\nAnd then some more words follow here.")["checks"]["P5_markup"]["pass"] is False
    assert run("The hook: we shipped it, and then some more words follow.")["checks"]["P5_markup"]["pass"] is True
    assert run("Version 3\nof the pricing page shipped and nobody noticed at all.")["checks"]["P5_markup"]["pass"] is False


# --------------------------------------------------------------------------- P6 emoji


def test_emoji_policy_defaults():
    base = "We shipped the thing and it went fine, mostly. "
    assert run(base + "🔥🔥🔥")["checks"]["P6_emoji"]["pass"] is True
    p6 = run(base + "🔥🔥🔥🔥")["checks"]["P6_emoji"]
    assert p6["pass"] is False and p6["count"] == 4 and p6["max"] == 3 and len(p6["evidence"]) == 4
    assert run(base + "🔥", "x")["checks"]["P6_emoji"]["pass"] is True
    assert run(base + "🔥✅", "x")["checks"]["P6_emoji"]["pass"] is False


def test_emoji_policy_from_meta_platform_choices():
    text = "We shipped the thing and it went fine, mostly. 🔥"
    p6 = run(text, "linkedin", {"platform_choices": {"emoji_max": 0}})["checks"]["P6_emoji"]
    assert p6["pass"] is False and p6["max"] == 0


def test_persona_file_policy_is_read(tmp_path):
    persona = tmp_path / "persona.md"
    persona.write_text("---\nplatform_choices:\n  emoji_max: 0\n  x: {long_posts: true}\n---\n# Persona\n", encoding="utf-8")
    choices = _ORIG_LOAD(persona)
    assert choices == {"emoji_max": 0, "x": {"long_posts": True}}
    pol = pc.resolve_policy("x", {}, CFG, choices)
    assert pol["emoji_max"] == 0 and pol["long_posts"] is True and pol["sources"]["emoji_max"] == "persona"
    # candidate front matter beats the persona file
    pol2 = pc.resolve_policy("x", {"platform_choices": {"emoji_max": 2}}, CFG, choices)
    assert pol2["emoji_max"] == 2 and pol2["sources"]["emoji_max"] == "meta"
    # nested per-platform beats flat; missing file and bad YAML are harmless
    pol3 = pc.resolve_policy("linkedin", {}, CFG, {"emoji_max": 1, "linkedin": {"emoji_max": 2}})
    assert pol3["emoji_max"] == 2
    assert _ORIG_LOAD(tmp_path / "missing.md") == {}
    (tmp_path / "bad.md").write_text("---\nplatform_choices: [\n---\n", encoding="utf-8")
    assert _ORIG_LOAD(tmp_path / "bad.md") == {}
    # run_checks honours the persona file when no meta override is given
    res = pc.run_checks("We shipped the thing and it went fine, mostly. 🔥", "linkedin", {}, CFG, persona_choices=choices)
    assert res["checks"]["P6_emoji"]["pass"] is False and res["policy"]["sources"]["emoji_max"] == "persona"


# --------------------------------------------------------------------------- advisory


def test_advisory_fields_linkedin():
    meta, body = fixture("li_good.md")
    res = run(body, "linkedin", meta)
    adv = res["advisory"]
    assert adv["li_length_band"] == "short"  # 972 chars < 1000
    assert adv["first_line_words"] == 7 and adv["first_line_chars"] == 36
    assert adv["question_opener"] is False
    assert adv["reading_time_s"] == round(adv["words"] / 230 * 60)
    assert adv["blank_lines"] == 6 and adv["lines"] == 13


def test_advisory_length_bands():
    assert run("Hook. " + "w " * 600)["advisory"]["li_length_band"] == "in"
    assert run("Hook. " + "w " * 1300)["advisory"]["li_length_band"] == "long"


def test_question_opener():
    assert run("Why do agents buy domains?\nBecause we let them, and nobody said no.")["advisory"]["question_opener"] is True
    assert run("Why. Because we let them?\nAnd nobody said no at all.")["advisory"]["question_opener"] is False


def test_one_liner_advisory_on_x():
    res = run("a " * 80, "x", {"cid": "r1-w1-x1"})
    assert res["advisory"]["one_liner_limit"] == 140 and res["advisory"]["one_liner_over"] is True
    assert "one_liner_limit" not in run("short.", "x", {"cid": "r1-w1-x"})["advisory"]


def test_summarize_lists():
    _, body = fixture("markup_leak.txt")
    s = pc.summarize(run(body))
    assert "P5_markup" in s["hard_fails"] and s["all_hard_pass"] is False
    text = "abcd " * 28 + "efgh ijkl. " + "tail " * 20
    s2 = pc.summarize(run(text))
    assert s2["flags"] == ["P2_fold"] and s2["all_hard_pass"] is True


# --------------------------------------------------------------------------- CLIs


def test_platform_check_cli_json_and_human():
    out = cli("platform_check.py", str(FIX / "li_good.md"), "--json")
    assert out["ok"] is True and out["platform"] == "linkedin" and out["cid"] == "r1-w2-li"
    assert out["all_hard_pass"] is True and set(out["checks"]) == set(pc.CHECK_IDS)
    proc = subprocess.run([sys.executable, str(TOOLS / "platform_check.py"), str(FIX / "li_good.md")],
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0 and "P2_fold" in proc.stdout and "fold preview:" in proc.stdout


def test_platform_check_cli_plain_text_needs_platform():
    out = cli("platform_check.py", str(FIX / "li_midword_fail.txt"), "--json")
    assert out["ok"] is False and "platform" in out["error"]
    out = cli("platform_check.py", str(FIX / "li_midword_fail.txt"), "--platform", "linkedin", "--json")
    assert out["ok"] is True and "P2_fold" in out["hard_fails"]


def test_platform_check_cli_missing_file():
    out = cli("platform_check.py", "does/not/exist.md", "--json")
    assert out["ok"] is False and "not found" in out["error"]


def test_xcount_cli():
    out = cli("xcount.py", "--text", "hello 🔥 https://example.com/x")
    assert out == {"x_len": 6 + 2 + 1 + 23, "over": False, "limit": 280}
    out = cli("xcount.py", str(FIX / "x_good.md"))
    _, body = fixture("x_good.md")
    assert out["x_len"] == x_count(body.rstrip("\n"), CFG["platforms"]["x"]) and out["over"] is False
    out = cli("xcount.py", "-", stdin="y" * 300)
    assert out == {"x_len": 300, "over": True, "limit": 280}
    out = cli("xcount.py", "-", "--limit", "25000", stdin="y" * 300)
    assert out["over"] is False and out["limit"] == 25000
    assert cli("xcount.py", "nope.txt")["ok"] is False
    assert cli("xcount.py")["ok"] is False
    assert cli("xcount.py", "--text", "x", "--limit", "0")["ok"] is False
