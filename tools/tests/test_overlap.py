"""Tests for tools/overlap_check.py and tools/quote_leak_check.py.

Both tools are always pointed at tools/tests/fixtures/overlap, by explicit root argument or --root, never
at the real corpus.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import overlap_check as oc  # noqa: E402
import quote_leak_check as qlc  # noqa: E402
from common import jaccard, normalize_text, split_front_matter, word_ngrams  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "overlap"
CLEAN_META = {"cid": "t-clean", "platform": "linkedin", "archetype": "list_of_lessons", "hook_type": "question",
              "ending": "cta"}


# --------------------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def cfg() -> dict:
    return oc.load_cfg(FIX)


@pytest.fixture(scope="module")
def lexicon() -> dict:
    return oc.load_lexicon(FIX)


@pytest.fixture(scope="module")
def index() -> dict:
    return oc.build_index(("train", "heldout", "self"), True, True, root=FIX)


def post_text(pid: str) -> str:
    for sub in ("corpus/posts", "corpus/heldout", "corpus/self"):
        p = FIX / sub / f"{pid}.md"
        if p.exists():
            _, body = split_front_matter(p.read_text(encoding="utf-8"))
            return body.rstrip("\n")
    raise FileNotFoundError(pid)


def clean_text() -> str:
    _, body = split_front_matter((FIX / "drafts/run_cli/round1/candidates/r1-w1-li.md").read_text(encoding="utf-8"))
    return body.rstrip("\n")


def run(text: str, index: dict, cfg: dict, lexicon: dict, meta: dict | None = None, siblings=None, published=None,
        exclude=None) -> dict:
    return oc.run_checks(text, meta or CLEAN_META, cfg, lexicon, index, siblings or [], published or [],
                         exclude or set())["checks"]


# --------------------------------------------------------------------------- index

def test_build_index_reads_posts_cards_finalists_published(index):
    assert set(index["posts"]) == {"quill_001", "quill_002", "voss_001", "voss_002", "marsh_001", "self_001"}
    q = index["posts"]["quill_001"]
    assert q["author"] == "ada-quill" and q["platform"] == "linkedin" and q["split"] == "train"
    assert q["archetype"] == "announcement_with_twist" and q["hook_types"] == ["deadpan_announcement"]
    assert q["ending"] == "aphorism" and q["card"] is True
    assert index["posts"]["marsh_001"]["split"] == "heldout" and index["posts"]["marsh_001"]["card"] is False
    assert index["posts"]["voss_002"]["crosspost_of"] == "voss_001"
    assert q["tokens"] == normalize_text(q["text"]).split()
    # prior finalist: text comes from the fenced block only; report.md is skipped
    assert list(index["prior_finalists"]) == ["final:2026-09-10_meeting-notes/li_1"]
    fin = index["prior_finalists"]["final:2026-09-10_meeting-notes/li_1"]
    assert fin["text"].startswith("We ran a retrospective") and "Why this works" not in fin["text"]
    assert list(index["published"]) == ["2026-09-01_agent-domains_linkedin"]
    assert set(index["ngrams"]) == {6, 8}
    gram = tuple("we killed our ai strategy last".split())
    assert index["ngrams"][6][gram] == ["quill_001"]


def test_build_index_respects_splits_and_flags():
    idx = oc.build_index(("train",), include_cards=False, include_drafts_final=False, root=FIX)
    assert set(idx["posts"]) == {"quill_001", "quill_002", "voss_001", "voss_002"}
    assert idx["posts"]["quill_001"]["card"] is False and idx["posts"]["quill_001"]["archetype"] is None
    assert idx["prior_finalists"] == {}
    with pytest.raises(oc.UserError):
        oc.build_index(("bogus",), root=FIX)


# --------------------------------------------------------------------------- span mapping

@pytest.mark.parametrize("raw", [
    "We killed our AI strategy last quarter.\n\nNot because it failed.",
    "Don't  panic — it's “fine”… see https://example.com/x?y=1 for #details @someone 🚀 ok",
    "hello,world\tnext line 'quoted' end.",
    "",
])
def test_token_spans_match_normalize_text(raw):
    prep = oc.prepare(raw)
    assert prep.norm == normalize_text(raw)
    assert prep.tokens == normalize_text(raw).split()
    if prep.tokens:
        assert prep.spans is not None
        for tok, (a, b) in zip(prep.tokens, prep.spans):
            assert tok in normalize_text(raw[a:b])
        full = oc.span_of(prep, 0, len(prep.tokens))
        assert full == re.sub(r"^\W+|\W+$", "", raw.strip()) and full in raw


def test_span_of_returns_verbatim_substring():
    raw = "We killed our AI strategy last quarter.\n\nNot because it failed. Because nobody could say what it was for."
    prep = oc.prepare(raw)
    assert oc.span_of(prep, 2, 6) == "our AI strategy last"
    assert oc.span_of(prep, 5, 9) == "last quarter.\n\nNot because"
    c0 = prep.norm.index("strategy")
    assert oc.span_of_chars(prep, c0 + 2, c0 + 12) == "strategy last"


def test_shared_runs_are_true_contiguous_matches():
    cand = "a b c d e f g x y b c d e f g h".split()
    ref = "z a b c d e f q b c d e f g h".split()
    runs = oc.shared_runs(cand, ref, 3)
    assert (0, 1, 6) in runs          # "a b c d e f"
    assert (9, 8, 7) in runs          # "b c d e f g h"
    assert all(cand[i:i + n] == ref[j:j + n] for i, j, n in runs)


# --------------------------------------------------------------------------- O1 / O2: exact copy and synonym swap

def test_exact_copy_fails_o1_and_o2(index, cfg, lexicon):
    text = post_text("quill_001")
    checks = run(text, index, cfg, lexicon)
    o1 = checks["O1_ngram"]
    assert o1["result"] == "fail" and o1["class"] == "hard" and o1["pass"] is False
    refs = {h["ref"] for h in o1["hits"]}
    assert "quill_001" in refs
    ngram_hit = next(h for h in o1["hits"] if h["ref"] == "quill_001" and h["kind"] == "ngram")
    assert ngram_hit["n"] >= cfg["overlap"]["ngram_fail"] and ngram_hit["level"] == "fail"
    assert ngram_hit["span"] in text
    lcs_hit = next(h for h in o1["hits"] if h["ref"] == "quill_001" and h["kind"] == "lcs")
    assert lcs_hit["chars"] >= cfg["overlap"]["lcs_fail_chars"] and lcs_hit["span"] in text
    assert o1["evidence"] and all(e["span"] in text for e in o1["evidence"])
    assert o1["max_shared_ngram"] == len(normalize_text(text).split())
    o2 = checks["O2_phrases"]
    assert o2["result"] == "fail" and o2["class"] == "hard" and o2["pass"] is False
    phrases = {h["phrase"] for h in o2["hits"]}
    assert {"killed our AI strategy", "small, boring, real"} <= phrases
    hit = next(h for h in o2["hits"] if h["phrase"] == "killed our AI strategy")
    assert hit["distance"] == 0 and hit["ref"] == "ada-quill" and hit["span"] == "killed our AI strategy"


def test_o2_is_fuzzy_within_edit_distance(index, cfg, lexicon):
    text = "Last spring we kiled our AI stratagy and nobody noticed for a month.\n\nThe budget did."
    o2 = run(text, index, cfg, lexicon)["O2_phrases"]
    assert o2["result"] == "fail"
    hit = next(h for h in o2["hits"] if h["phrase"] == "killed our AI strategy")
    assert hit["distance"] == 2 and hit["span"] == "kiled our AI stratagy"
    far = "Last spring we cancelled our AI roadmap and nobody noticed for a month."
    assert run(far, index, cfg, lexicon)["O2_phrases"]["pass"] is True


def test_o2_reads_card_distinctive_phrases_and_honours_exclusion(index, cfg, lexicon):
    text = post_text("quill_001")
    no_lexicon = {"lexicon_version": 0, "tiers": {}, "do_not_reuse": {}, "user_tells": []}
    o2 = run(text, index, cfg, no_lexicon)["O2_phrases"]
    assert o2["result"] == "fail" and o2["class"] == "hard"
    hit = next(h for h in o2["hits"] if h["phrase"] == "killed our AI strategy")
    assert hit["ref"] == "quill_001" and hit["source"] == "card" and hit["author"] == "ada-quill"
    assert hit["span"] in text and any("card quill_001" in e["why"] for e in o2["evidence"])
    # the oracle case: the post itself is excluded, so its own card phrases do not count
    assert run(text, index, cfg, no_lexicon, exclude={"quill_001"})["O2_phrases"]["pass"] is True
    # a phrase listed in the lexicon is reported once, from the lexicon
    hits = [h for h in run(text, index, cfg, lexicon)["O2_phrases"]["hits"] if h["phrase"] == "killed our AI strategy"]
    assert len(hits) == 1 and hits[0]["ref"] == "ada-quill" and hits[0]["source"] == "lexicon"
    rest = oc.card_phrases(index, {"quill_001"})
    assert rest and all(pid != "quill_001" for pid, _, _ in rest)


SYNONYMS = {"interviewed": "screened", "engineers": "developers", "spring": "season", "question": "prompt",
            "delete": "remove", "paused": "hesitated", "feature": "capability", "added": "built",
            "answer": "reply", "offers": "contracts", "code": "software", "skill": "ability", "resume": "cv",
            "asking": "raising", "loud": "clear", "month": "quarter", "people": "candidates"}


def synonym_swap(text: str, every: int = 7) -> str:
    """Replace roughly 1 in `every` words (~15%) with a synonym, deterministically, keeping punctuation."""
    out = []
    for i, chunk in enumerate(text.split(" ")):
        if i % every == every - 1:
            m = re.match(r"^(\W*)([A-Za-z']+)(.*)$", chunk, re.DOTALL)
            if m:
                word = m.group(2)
                rep = SYNONYMS.get(word.lower(), "thing")
                if word[:1].isupper():
                    rep = rep.capitalize()
                chunk = m.group(1) + rep + m.group(3)
        out.append(chunk)
    return " ".join(out)


def test_synonym_swap_is_caught_by_o1(index, cfg, lexicon):
    original = post_text("quill_002")
    swapped = synonym_swap(original)
    n_changed = sum(1 for a, b in zip(original.split(" "), swapped.split(" ")) if a != b)
    assert 0.10 <= n_changed / len(original.split(" ")) <= 0.20
    assert swapped != original
    o1 = run(swapped, index, cfg, lexicon)["O1_ngram"]
    assert o1["result"] in ("flag", "fail") and o1["pass"] is False
    hits = [h for h in o1["hits"] if h["ref"] == "quill_002"]
    assert hits and all(h["span"] in swapped for h in hits)
    assert any(h["kind"] == "ngram" and h["n"] >= cfg["overlap"]["ngram_flag"] for h in hits) or \
        any(h["kind"] == "lcs" for h in hits)


def test_six_gram_flags_not_fails(index, cfg, lexicon):
    # exactly six shared words with quill_002, then the text diverges; LCS stays under 40 chars
    text = "Seven people had an answer ready for the board, which is rarer than it sounds.\n\nMost decks answer nothing."
    o1 = run(text, index, cfg, lexicon)["O1_ngram"]
    assert o1["result"] == "flag" and o1["class"] == "flag" and o1["pass"] is False
    hit = next(h for h in o1["hits"] if h["ref"] == "quill_002")
    assert hit["kind"] == "ngram" and hit["n"] == 6 and hit["span"] == "Seven people had an answer ready"
    assert not any(h["kind"] == "lcs" for h in o1["hits"])


# --------------------------------------------------------------------------- clean text

def test_clean_text_passes_all(index, cfg, lexicon):
    checks = run(clean_text(), index, cfg, lexicon)
    for cid in oc.CHECK_IDS:
        assert checks[cid]["pass"] is True, (cid, checks[cid])
        assert checks[cid]["result"] == "pass" and checks[cid]["hits"] == [] and checks[cid]["evidence"] == []
    assert checks["O1_ngram"]["class"] == "flag" and checks["O2_phrases"]["class"] == "hard"
    assert checks["O5_published"]["class"] == "hard" and checks["O3_skeleton"]["class"] == "flag"
    assert checks["O1_ngram"]["max_shared_ngram"] < cfg["overlap"]["ngram_flag"]
    assert checks["O1_ngram"]["lcs_chars"] is not None and checks["O1_ngram"]["lcs_chars"] < 40


def test_empty_candidate_passes_without_crashing(index, cfg, lexicon):
    checks = run("", index, cfg, lexicon, meta={})
    assert all(checks[cid]["pass"] for cid in oc.CHECK_IDS)


# --------------------------------------------------------------------------- O3 skeleton

def skeleton_text_from(pid: str, chunk: int = 4) -> str:
    """Reverse the order of 4-word chunks: 3-gram overlap stays high, no 6-gram survives."""
    ws = post_text(pid).split()
    chunks = [ws[i:i + chunk] for i in range(0, len(ws), chunk)]
    return " ".join(" ".join(c) for c in reversed(chunks))


def test_skeleton_flag_requires_matching_meta(index, cfg, lexicon):
    text = skeleton_text_from("voss_001")
    ref = index["posts"]["voss_001"]["tokens"]
    jac = jaccard(word_ngrams(normalize_text(text).split(), 3), word_ngrams(ref, 3))
    assert jac >= cfg["overlap"]["skeleton_jaccard"]
    meta = {"cid": "t-skel", "archetype": "story_to_lesson", "hook_type": "story_in_medias_res", "ending": "callback"}
    checks = run(text, index, cfg, lexicon, meta=meta)
    o3 = checks["O3_skeleton"]
    assert o3["result"] == "flag" and o3["class"] == "flag" and o3["pass"] is False
    hit = o3["hits"][0]
    assert hit["ref"] == "voss_001" and hit["jaccard"] >= 0.15 and hit["span"] in text
    assert o3["evidence"][0]["span"] == hit["span"]
    assert checks["O1_ngram"]["result"] != "fail"
    # same text, different declared skeleton -> no flag; assignment-nested meta also works
    other = dict(meta, ending="punchline")
    assert run(text, index, cfg, lexicon, meta=other)["O3_skeleton"]["pass"] is True
    nested = {"cid": "t-skel", "assignment": {"archetype": "story_to_lesson", "hook_type": "story_in_medias_res"},
              "ending": "callback"}
    assert run(text, index, cfg, lexicon, meta=nested)["O3_skeleton"]["pass"] is False
    # no skeleton meta -> not compared, passes with a note
    bare = run(text, index, cfg, lexicon, meta={"cid": "t"})["O3_skeleton"]
    assert bare["pass"] is True and bare["compared"] == 0


# --------------------------------------------------------------------------- O4 sibling

def test_sibling_flag(index, cfg, lexicon):
    me = clean_text()
    twin = me.replace("on the team", "in the company")
    checks = run(me, index, cfg, lexicon, meta={"cid": "r1-w1-li"},
                 siblings=[("r1-w1-li", me), ("r1-w2-li", twin), ("r1-w3-li", post_text("self_001"))])
    o4 = checks["O4_sibling"]
    assert o4["result"] == "flag" and o4["pass"] is False and o4["compared"] == 2   # own cid skipped
    assert [h["ref"] for h in o4["hits"]] == ["r1-w2-li"]
    assert o4["hits"][0]["jaccard"] >= cfg["overlap"]["sibling_jaccard"] and o4["hits"][0]["span"] in me
    assert run(me, index, cfg, lexicon, siblings=[("r1-w3-li", post_text("self_001"))])["O4_sibling"]["pass"]


# --------------------------------------------------------------------------- O5 published

def test_published_eight_gram_is_hard_fail(index, cfg, lexicon):
    text = ("Nobody tells you what an agent costs.\n\nMine spent the twelve dollars it spent on a database it never used, "
            "and then apologised in a footnote.")
    o5 = run(text, index, cfg, lexicon)["O5_published"]
    assert o5["result"] == "fail" and o5["class"] == "hard" and o5["pass"] is False
    hit = next(h for h in o5["hits"] if h["kind"] == "ngram")
    assert hit["ref"] == "2026-09-01_agent-domains_linkedin" and hit["n"] >= 8
    assert hit["span"] == "the twelve dollars it spent on a database it never used" and hit["span"] in text
    assert o5["evidence"] and o5["evidence"][0]["span"] in text


def test_published_lcs_is_hard_fail_and_six_gram_flags(index, cfg, lexicon):
    lcs_text = "Line one.\n\nIt is the only employee whose receipts always add up, which is also a warning."
    o5 = run(lcs_text, index, cfg, lexicon)["O5_published"]
    assert o5["result"] == "fail"
    assert any(h["kind"] == "lcs" and h["chars"] >= 40 for h in o5["hits"])
    flag_text = "The finance team loves it. It also loves the intern who wrote the first invoice."
    o5 = run(flag_text, index, cfg, lexicon)["O5_published"]
    assert o5["result"] == "flag" and o5["class"] == "flag" and o5["pass"] is False
    assert o5["hits"][0]["n"] == 6 and o5["hits"][0]["span"] == "The finance team loves it. It"


def test_published_param_is_merged_with_index(index, cfg, lexicon):
    text = clean_text()
    o5 = run(text, index, cfg, lexicon, published=[("2026-09-15_calendar_linkedin", text)])["O5_published"]
    assert o5["result"] == "fail" and o5["hits"][0]["ref"] == "2026-09-15_calendar_linkedin"


# --------------------------------------------------------------------------- prior finalists and exclusion

def test_prior_finalist_counts_at_flag_level_only(index, cfg, lexicon):
    text = index["prior_finalists"]["final:2026-09-10_meeting-notes/li_1"]["text"]
    o1 = run(text, index, cfg, lexicon)["O1_ngram"]
    assert o1["result"] == "flag" and o1["class"] == "flag"
    refs = {h["ref"] for h in o1["hits"]}
    assert refs == {"final:2026-09-10_meeting-notes/li_1"}
    assert all(h["level"] == "flag" for h in o1["hits"])


def test_exclude_ids_removes_post_and_its_crosspost(index, cfg, lexicon):
    text = post_text("voss_001")
    o1 = run(text, index, cfg, lexicon)["O1_ngram"]
    assert o1["result"] == "fail" and {h["ref"] for h in o1["hits"]} == {"voss_001", "voss_002"}
    res = oc.run_checks(text, CLEAN_META, cfg, lexicon, index, [], [], {"voss_001"})
    assert res["excluded"] == ["voss_001", "voss_002"]
    o1 = res["checks"]["O1_ngram"]
    assert o1["pass"] is True and o1["hits"] == []
    # excluding the crosspost also excludes its source
    assert oc.expand_excludes(index, {"voss_002"}) == {"voss_001", "voss_002"}
    # O3 honours the exclusion too
    meta = {"cid": "t", "archetype": "story_to_lesson", "hook_type": "story_in_medias_res", "ending": "callback"}
    assert run(text, index, cfg, lexicon, meta=meta)["O3_skeleton"]["pass"] is False
    assert run(text, index, cfg, lexicon, meta=meta, exclude={"voss_001"})["O3_skeleton"]["pass"] is True


# --------------------------------------------------------------------------- CLI

def cli(*args: str) -> dict:
    proc = subprocess.run([sys.executable, str(TOOLS / "overlap_check.py"), *args], capture_output=True, text=True,
                          cwd=str(FIX), check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_cli_builds_index_and_finds_siblings():
    out = cli("drafts/run_cli/round1/candidates/r1-w1-li.md", "--run", "run_cli", "--root", str(FIX), "--json")
    assert out["ok"] is True and out["cid"] == "r1-w1-li" and out["siblings"] == ["r1-w2-li"]
    assert out["index"]["n_posts"] == 6 and out["index"]["n_prior_finalists"] == 1 and out["index"]["n_published"] == 1
    assert set(out["checks"]) == set(oc.CHECK_IDS)
    assert out["checks"]["O4_sibling"]["pass"] is False and out["checks"]["O4_sibling"]["hits"][0]["ref"] == "r1-w2-li"
    assert all(out["checks"][c]["pass"] for c in oc.CHECK_IDS if c != "O4_sibling")


def test_cli_exclude_and_errors(tmp_path):
    cand = tmp_path / "copy.md"
    cand.write_text("---\ncid: t-copy\nplatform: linkedin\n---\n" + post_text("voss_001") + "\n", encoding="utf-8")
    out = cli(str(cand), "--root", str(FIX), "--json")
    assert out["checks"]["O1_ngram"]["result"] == "fail" and out["checks"]["O2_phrases"]["result"] == "fail"
    out = cli(str(cand), "--root", str(FIX), "--exclude", "voss_001", "--json")
    assert out["excluded"] == ["voss_001", "voss_002"] and out["checks"]["O1_ngram"]["pass"] is True
    assert cli("does/not/exist.md", "--root", str(FIX), "--json") == {"ok": False, "error": "candidate not found: does/not/exist.md"}
    out = cli(str(cand), "--root", str(FIX), "--run", "nope", "--json")
    assert out["ok"] is False and "run not found" in out["error"]
    empty = tmp_path / "empty.md"
    empty.write_text("---\ncid: e\n---\n\n", encoding="utf-8")
    assert cli(str(empty), "--root", str(FIX), "--json")["ok"] is False
    help_out = subprocess.run([sys.executable, str(TOOLS / "overlap_check.py"), "--help"], capture_output=True, text=True, check=False)
    assert help_out.returncode == 0 and "--exclude" in help_out.stdout


# --------------------------------------------------------------------------- quote leak

def test_quote_leak_clean_root():
    out = qlc.scan(FIX)
    assert out["ok"] is True and out["leaks"] == [] and out["heldout_posts"] == 1
    assert "style/common.md" in out["scanned"] and "style/authors/ada-quill.md" in out["scanned"]
    assert "memory/lessons.md" in out["scanned"] and "drafts/run_cli/brief.md" in out["scanned"]
    assert not any(s.startswith("corpus/") for s in out["scanned"])


def test_quote_leak_detects_planted_heldout_ngram(tmp_path):
    root = tmp_path / "root"
    shutil.copytree(FIX, root)
    planted = root / "style" / "authors" / "cleo-marsh.md"
    planted.write_text("---\nauthor: cleo-marsh\n---\n# Cleo Marsh\n\nSignature line: \"what is the first thing you want "
                       "this tool\" (a line she reuses).\n", encoding="utf-8")
    out = qlc.scan(root)
    assert out["ok"] is False
    assert len(out["leaks"]) == 1
    leak = out["leaks"][0]
    assert leak["file"] == "style/authors/cleo-marsh.md" and leak["heldout_id"] == "marsh_001"
    assert leak["span"] == "what is the first thing you want this tool" and leak["n"] == 9
    # a train-post quote is allowed
    planted.write_text("---\nauthor: cleo-marsh\n---\nQuote: We killed our AI strategy last quarter.\n", encoding="utf-8")
    assert qlc.scan(root)["ok"] is True


def test_quote_leak_scans_extra_files_and_skips_heldout_inputs(tmp_path):
    cand = tmp_path / "r1-w1-li.md"
    cand.write_text("---\ncid: r1-w1-li\n---\nReply rate is now 31 percent. The question was simple.\n", encoding="utf-8")
    out = qlc.scan(FIX, [cand])
    assert out["ok"] is False and out["leaks"][0]["heldout_id"] == "marsh_001"
    assert out["leaks"][0]["span"] == "Reply rate is now 31 percent. The question was" and str(cand) in out["scanned"]
    out = qlc.scan(FIX, [FIX / "corpus/heldout/marsh_001.md"])
    assert out["ok"] is True and out["skipped_heldout_inputs"] == ["corpus/heldout/marsh_001.md"]
    with pytest.raises(oc.UserError):
        qlc.scan(FIX, ["missing.md"])


def test_quote_leak_cli(tmp_path):
    proc = subprocess.run([sys.executable, str(TOOLS / "quote_leak_check.py"), "--root", str(FIX), "--json"],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["ok"] is True and out["leaks"] == []
    proc = subprocess.run([sys.executable, str(TOOLS / "quote_leak_check.py"), "nope.md", "--root", str(FIX), "--json"],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0 and json.loads(proc.stdout) == {"ok": False, "error": "file not found: nope.md"}
