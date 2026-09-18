"""Tests for tools/assemble_report.py.

Every test works on a scratch copy of tools/tests/fixtures/report/. `proj/` is a small project root (config,
rubric thresholds, a profile with 2 self samples, moves, lexicon, a README with an Ops notes section).
`2026-09-17_agents-buying-domains/` is a delivered two-round run. Its tier0, judge, jury, merged and
feedback documents are real aggregate.py output rather than hand-written JSON, its Tier 2 scores carry the
filenames lineup.py, pairwise.py and run_next.py write, and it ships a media brief with rendered prompts and
its media_check / media-judge outputs.

It carries one variant per report section: r1-w1-li (LinkedIn finalist, lineup 1/3, pairwise win/tie, image
media), r1-w1-x (X finalist, lineup 0/3, reply_1), r1-w2-li (alternate, passed_tier1_only, O1 flag waived),
r1-w2-x (needs your call: persona_fit 3 with a claim to confirm), r2-w3-li (did not pass: humor 3 with jury
3/3/2, rewrite of r1-w3-li).
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
PROJECT = TOOLS.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "report"
sys.path.insert(0, str(TOOLS))

import assemble_report as ar  # noqa: E402
import common  # noqa: E402
import draft_id  # noqa: E402
import status as status_mod  # noqa: E402

RUN = "2026-09-17_agents-buying-domains"
LI, X, ALT, NYC, DNP = "r1-w1-li", "r1-w1-x", "r1-w2-li", "r1-w2-x", "r2-w3-li"
ALL = (LI, X, ALT, NYC, DNP)
# Anything that would leak a verdict onto the page before the blind rating.
VERDICT_RE = re.compile(
    r"PASSED|DID NOT PASS|did not pass|needs your call|passed Tier 0-1|not lineup-tested|needs_your_call|"
    r"passed_tier1_only|\bpass(?:ed|es)?\b|\bfail(?:ed|s|ing)?\b|\bhold\b|\bjury\b|lineup \d/\d|pairwise|"
    r"Rate it:|Log it:|verdict:",
    re.IGNORECASE,
)


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    dst = tmp_path / "proj"
    shutil.copytree(FIX / "proj", dst)
    shutil.copytree(FIX / RUN, dst / "drafts" / RUN)
    return dst


def _cli(*args: str, root: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "POSTSMITH_ROOT")}
    proc = subprocess.run([sys.executable, str(TOOLS / "assemble_report.py"), *args, "--root", str(root)],
                          capture_output=True, text=True, env=env, cwd=str(PROJECT), check=False)
    assert proc.returncode == 0, proc.stderr
    return proc


def _final(root: Path) -> Path:
    return root / "drafts" / RUN / "final"


def _rj(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _wj(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _text(root: Path, cid: str, k: int = 1) -> str:
    return (root / "drafts" / RUN / f"round{k}" / "candidates" / f"{cid}.txt").read_text(encoding="utf-8").rstrip("\n")


def _fenced_blocks(md: str) -> list[str]:
    return re.findall(r"```text\n(.*?)\n```", md, flags=re.DOTALL)


def _add_blind_row(root: Path, ref: str = f"{RUN}/{LI}", blind: bool = True) -> None:
    common.append_jsonl(root / "evals" / "calibration.jsonl",
                        {"ts": "2026-09-17T10:00:00Z", "post_ref": ref, "kind": "generated", "platform": "linkedin",
                         "user_score": 4, "tags": [], "blind": blind})


# =============================================================================== hidden mode (the default)

def test_hidden_mode_is_the_default_and_writes_every_final_file(proj: Path):
    proc = _cli(RUN, root=proj)
    out = proc.stdout
    final = _final(proj)
    for name in ("clipboard.md", "report.md", "lineage.json", "blind.json", *(f"{c}.md" for c in ALL)):
        assert (final / name).exists(), name
    assert out.startswith("# agents buying domains to be safe · " + RUN + " · rubric v1 · profile p3 · lexicon v1 · health none")
    # neutral headers: platform, letter, size only
    assert re.search(r'^## LinkedIn · [A-Z] \(822 chars · fold: "We gave an agent a company card', out, flags=re.MULTILINE)
    assert re.search(r"^## X · [A-Z] \(205/280 as X counts\)$", out, flags=re.MULTILINE)
    # no section split: every variant sits under one "##" heading, in letter order, so nothing about which
    # section a variant belongs to (i.e. its verdict) reaches the page before the blind rating
    assert "## Also delivered" not in out
    assert re.findall(r"^#{2,3} (?:LinkedIn|X) · ([A-Z]) \(", out, flags=re.MULTILINE) == sorted(
        re.findall(r"^## (?:LinkedIn|X) · ([A-Z]) \(", out, flags=re.MULTILINE))
    # texts are printed exactly as pasted
    for cid, k in ((LI, 1), (X, 1), (ALT, 1), (NYC, 1), (DNP, 2)):
        assert _text(proj, cid, k) in _fenced_blocks(out)
    # media prompt, claims to confirm, disclosures and the closing line survive hiding
    assert "Image · 4:5 · Nano Banana (fallback GPT Image) · why: M3: fake-document punchline" in out
    assert "Create a photorealistic fake-document image for a LinkedIn post." in out
    assert 'Confirm before posting: "3 domains in prod for 6 weeks" (persona.can_claim#1)' in out
    assert "small-corpus mode: lineup uses train posts" in out and "voice anchor: weak (self n=2)" in out
    assert "matrix fallback rung 1" in out
    assert out.rstrip().endswith(f"Rate them blind first: /rate blind {RUN}")


def test_hidden_terminal_carries_no_verdict_word(proj: Path):
    out = _cli(RUN, root=proj).stdout
    hits = VERDICT_RE.findall(out)
    assert not hits, hits
    # letter order only (the section order is the verdict); the follow-up lines wait for the blind rating
    assert "Rate it:" not in out and "Log it:" not in out
    assert "lineup 1/3" not in out and "conf 2" not in out


def test_hidden_terminal_letters_match_blind_json(proj: Path):
    out = _cli(RUN, root=proj).stdout
    blind = _rj(_final(proj) / "blind.json")
    for it in blind["items"]:
        plat = "LinkedIn" if it["platform"] == "linkedin" else "X"
        assert re.search(rf"^#{{2,3}} {plat} · {it['key']} \(", out, flags=re.MULTILINE), it
    letters = re.findall(r"^#{2,3} (?:LinkedIn|X) · ([A-Z]) \(", out, flags=re.MULTILINE)
    assert len(letters) == 5 and len(set(letters)) == 5


def test_hidden_variant_files_withhold_the_verdict(proj: Path):
    _cli(RUN, root=proj)
    meta, body = common.read_front_matter_file(_final(proj) / f"{LI}.md")
    assert meta["verdict"] == "withheld"
    assert "PASSED" not in body and "did not pass" not in body


# =============================================================================== full mode

def test_show_verdicts_renders_labels_eval_headers_and_followups(proj: Path):
    out = _cli(RUN, "--show-verdicts", root=proj).stdout
    assert ('## LinkedIn · PASSED (822 chars · fold: "We gave an agent a company card and asked it to register one domain for…"'
            " · lineup 1/3 picked at conf 2 · pairwise win/tie)") in out
    assert "## X · PASSED (205/280 as X counts · lineup 0/3 · paraphrase clean vs 2 exemplars)" in out
    assert f"Rate it: /rate {RUN} li N     Log it: /posted {RUN} li <url>" in out
    assert f"Rate it: /rate {RUN} x N     Log it: /posted {RUN} x <url>" in out
    assert "## Alternates (passed Tier 0-1, not lineup-tested; run --wide to test)" in out
    assert re.search(r"^### LinkedIn [A-Z] \(short deadpan\) · passed Tier 0-1, not lineup-tested \(252 chars", out, flags=re.MULTILINE)
    assert "## Needs your call" in out
    assert re.search(r'^### X [A-Z] · r1-w2-x: persona_fit 3 \(jury 3/3/3\), claim "3 domains in prod for 6 weeks" '
                     r"needs confirmation \(persona\.can_claim#1\)$", out, flags=re.MULTILINE)
    assert "## Did not pass" in out
    assert re.search(r'^### LinkedIn [A-Z] · r2-w3-li: humor 3/4 \(jury 3/3/2\): "The agent has asked for a replacement\." - ',
                     out, flags=re.MULTILINE)
    # finalists first, then the other sections in order
    idx = [out.index(s) for s in ("## LinkedIn · PASSED", "## X · PASSED", "## Alternates", "## Needs your call", "## Did not pass",
                                  f"Files: drafts/{RUN}/final/")]
    assert idx == sorted(idx)
    assert "Rate them blind first" not in out


def test_blind_calibration_row_switches_to_full_mode(proj: Path):
    _add_blind_row(proj, ref=f"{RUN}/{LI}", blind=False)
    assert "PASSED" not in _cli(RUN, root=proj).stdout           # a non-blind row does not count
    _add_blind_row(proj, ref="2026-09-10_other-run/r1-w1-li")
    assert "PASSED" not in _cli(RUN, root=proj).stdout           # another run's row does not count
    _add_blind_row(proj, ref=f"{RUN}:B")
    out = _cli(RUN, root=proj).stdout
    assert "## LinkedIn · PASSED" in out and "Rate it:" in out
    assert "Rate them blind first" not in out
    meta, _ = common.read_front_matter_file(_final(proj) / f"{LI}.md")
    assert meta["verdict"] == "pass"


def test_hide_verdicts_forces_hidden_mode_even_after_a_blind_row(proj: Path):
    _add_blind_row(proj)
    out = _cli(RUN, "--hide-verdicts", root=proj).stdout
    assert not VERDICT_RE.findall(out)


def test_verdict_labels_come_only_from_merged_status(proj: Path):
    scores = proj / "drafts" / RUN / "round1" / "scores"
    m = _rj(scores / f"{LI}.merged.json")
    m["verdict"]["status"] = "fail"
    m["verdict"]["soft_fails"] = ["not_ai"]
    m["tier1"]["not_ai"]["result"] = "fail"
    m["tier1"]["not_ai"]["score"] = 2
    _wj(scores / f"{LI}.merged.json", m)
    a = _rj(scores / f"{ALT}.merged.json")
    a["verdict"]["status"] = "pass"          # what aggregate.py really writes for a Tier 0-1 pass without Tier 2
    _wj(scores / f"{ALT}.merged.json", a)
    out = _cli(RUN, "--show-verdicts", root=proj).stdout
    assert "## LinkedIn · PASSED" not in out
    assert re.search(r"^### LinkedIn [A-Z] · r1-w1-li: not_ai 2/4: ", out, flags=re.MULTILINE)
    assert re.search(r"^### LinkedIn [A-Z] \(short deadpan\) · passed Tier 0-1, not lineup-tested", out, flags=re.MULTILINE)
    assert "## X · PASSED" in out


def test_quick_run_promotes_the_top_pass_without_a_lineup(proj: Path):
    rd = proj / "drafts" / RUN
    st = _rj(rd / "state.json")
    st["flags"]["quick"] = True
    _wj(rd / "state.json", st)
    for cid in (LI, X):
        m = _rj(rd / "round1" / "scores" / f"{cid}.merged.json")
        m["verdict"]["tier2_tested"] = False
        m["tier2"] = {"ran": False, "lineup": None, "paraphrase": None, "pairwise": None, "claims": None, "media": None}
        _wj(rd / "round1" / "scores" / f"{cid}.merged.json", m)
    shutil.rmtree(rd / "tier2")
    out = _cli(RUN, "--show-verdicts", root=proj).stdout
    assert "quick: no lineup, no pairwise" in out.splitlines()[0]
    assert "## LinkedIn · PASSED (822 chars" in out and "lineup skipped (quick)" in out
    assert "## X · PASSED (205/280 as X counts · lineup skipped (quick))" in out
    # the second LinkedIn pass stays an alternate
    assert re.search(r"^### LinkedIn [A-Z] \(short deadpan\) · passed Tier 0-1, not lineup-tested", out, flags=re.MULTILINE)


# =============================================================================== blind.json

def test_blind_json_is_deterministic_and_verdict_free(proj: Path):
    _cli(RUN, root=proj)
    first = (_final(proj) / "blind.json").read_bytes()
    shutil.rmtree(_final(proj))
    _cli(RUN, "--show-verdicts", root=proj)
    assert (_final(proj) / "blind.json").read_bytes() == first
    blind = json.loads(first)
    assert blind["run"] == RUN and blind["seed"] == common.stable_seed(RUN)
    assert [it["key"] for it in blind["items"]] == ["A", "B", "C"]
    # contracts §18: key, platform and text, nothing else. A cid names the round a text came from and a round-2
    # cid is a rewrite of something that failed, so the mapping lives in the sibling key file instead.
    for it in blind["items"]:
        assert set(it) == {"key", "platform", "text"}
    assert not re.search(r"verdict|status|label|PASSED|fail|r\d-w\d-", first.decode("utf-8"))
    key = _rj(_final(proj) / "blind.key.json")
    assert {it["cid"] for it in key["items"]} == {LI, ALT, DNP}    # finalist, alternate, did-not-pass, same platform
    by_key = {it["key"]: it for it in key["items"]}
    for it in blind["items"]:
        row = by_key[it["key"]]
        k = 2 if row["cid"] == DNP else 1
        assert it["text"] == _text(proj, row["cid"], k)
        assert row["text_path"] == f"drafts/{RUN}/round{k}/candidates/{row['cid']}.txt"


def test_blind_order_is_the_seeded_shuffle_of_finalist_alternate_did_not_pass(proj: Path):
    doc = ar.assemble(RUN, root=proj, write=False)
    expected = [LI, ALT, DNP]
    random.Random(common.stable_seed(RUN)).shuffle(expected)
    assert [it["cid"] for it in doc["blind"]["items"]] == expected


def test_blind_falls_back_to_both_finalists_when_nothing_else_exists(proj: Path):
    rd = proj / "drafts" / RUN
    for cid in (ALT, NYC):
        (rd / "round1" / "candidates" / f"{cid}.md").unlink()
    shutil.rmtree(rd / "round2")
    (rd / "round1" / "candidates" / "r1-w3-li.md").unlink()
    doc = ar.assemble(RUN, root=proj, write=False)
    assert {it["cid"] for it in doc["blind"]["items"]} == {LI, X}


# =============================================================================== clipboard, X reply_1, variant files

def test_clipboard_holds_texts_only(proj: Path):
    _cli(RUN, root=proj)
    clip = (_final(proj) / "clipboard.md").read_text(encoding="utf-8")
    blocks = clip.split("\n=====\n")
    assert len(blocks) == 3
    assert blocks[0] == "LINKEDIN\n" + _text(proj, LI)
    assert blocks[1] == "X\n" + _text(proj, X) + "\nreply_1: the incident report, redacted: https://example.com/incident-0400"
    assert blocks[2].rstrip("\n") == "LINKEDIN\n" + _text(proj, ALT)
    assert _text(proj, DNP, 2) not in clip and _text(proj, NYC) not in clip
    assert not VERDICT_RE.findall(clip)


def test_x1_one_liner_gets_its_own_clipboard_header(proj: Path):
    rd = proj / "drafts" / RUN
    src_md = (rd / "round1" / "candidates" / f"{X}.md").read_text(encoding="utf-8")
    one = "it bought 400 domains. to be safe.\n"
    (rd / "round1" / "candidates" / "r1-w1-x1.md").write_text(
        src_md.replace(f"cid: {X}", "cid: r1-w1-x1").split("\n---\n", 1)[0] + "\n---\n" + one, encoding="utf-8")
    (rd / "round1" / "candidates" / "r1-w1-x1.txt").write_text(one, encoding="utf-8")
    for name in ("tier0", "merged"):
        d = _rj(rd / "round1" / "scores" / f"{ALT}.{name}.json")
        d["cid"] = "r1-w1-x1"
        d["platform"] = "x"
        if name == "tier0":
            d["chars"] = len(one.rstrip("\n"))
            d["x_len"] = len(one.rstrip("\n"))
        _wj(rd / "round1" / "scores" / f"r1-w1-x1.{name}.json", d)
    _cli(RUN, root=proj)
    clip = (_final(proj) / "clipboard.md").read_text(encoding="utf-8")
    assert "\n=====\nX1\nit bought 400 domains. to be safe." in clip
    assert (_final(proj) / "r1-w1-x1.md").exists()


def test_x_variant_carries_reply_1_and_the_linkedin_one_does_not(proj: Path):
    out = _cli(RUN, root=proj).stdout
    meta, body = common.read_front_matter_file(_final(proj) / f"{X}.md")
    assert meta["platform"] == "x" and meta["x_len"] == 205 and meta["chars"] == 205 and meta["fold_preview"] is None
    assert meta["reply_1"] == "the incident report, redacted: https://example.com/incident-0400"
    assert "\nreply_1: the incident report, redacted: https://example.com/incident-0400\n" in body
    assert _fenced_blocks(body)[0] == _text(proj, X)
    # the terminal prints reply_1 right after the X text
    assert re.search(r"it was being helpful\.\n```\nreply_1: the incident report, redacted: https://example\.com/incident-0400\n", out)
    li_meta, li_body = common.read_front_matter_file(_final(proj) / f"{LI}.md")
    assert li_meta["reply_1"] is None and "reply_1:" not in li_body


def test_linkedin_variant_file_front_matter_body_and_media_block(proj: Path):
    _cli(RUN, "--show-verdicts", root=proj)
    meta, body = common.read_front_matter_file(_final(proj) / f"{LI}.md")
    assert meta["schema"] == "postsmith.final/1" and meta["cid"] == LI and meta["platform"] == "linkedin"
    assert meta["chars"] == 822 and meta["x_len"] is None and meta["round"] == 1
    assert meta["fold_preview"].startswith("We gave an agent a company card") and len(meta["fold_preview"]) == 140
    assert meta["lens"] is None and meta["moves"] == ["corporate_register_for_trivial_event"] and meta["angle_family"] == "receipt"
    assert meta["verdict"] == "pass" and meta["tier2_tested"] is True
    assert meta["scores_path"] == f"drafts/{RUN}/round1/scores/{LI}.merged.json"
    blocks = _fenced_blocks(body)
    assert blocks[0] == _text(proj, LI)                       # exactly as pasted, first block
    why = body.split("## Why this works\n", 1)[1].split("\n## ", 1)[0]
    assert '"the agent that over-delivered: 400 domains to be safe"' in why
    assert "`corporate_register_for_trivial_event`" in why and "`anti_climax`" in why and "acosta_003" in why
    assert "a trivial event narrated in the register of an incident report" in why    # the move's mechanism line
    assert "thesis" not in why and "judge" not in why                                   # no judge text
    assert 2 <= why.count(". ") + 1 <= 3
    media = body.split("## Media\n", 1)[1]
    assert media.startswith("Image · 4:5 · Nano Banana (fallback GPT Image) · why: M3: fake-document punchline")
    assert "delete test: Without it the caption ends on a setup and the reader never sees the receipt." in media
    assert "Alt text: Laminated purchase order on a fridge; the item line reads: one domain, to be safe." in media
    assert "\nNano Banana · 4:5 · 1080x1350 · 2K · fallback GPT Image\n```text\n" in media
    assert "\nGPT Image · 4:5 · 1080x1350 · 2K\n```text\n" in media
    prompts = proj / "drafts" / RUN / "media" / f"{LI}.prompts"
    for name in ("nano_banana", "gpt_image"):
        assert (prompts / f"{name}.md").read_text(encoding="utf-8").rstrip("\n") in blocks[1:]
    assert media.index("Nano Banana ·") < media.index("GPT Image ·")      # primary tool first


def test_media_block_renders_capture_direction_video_none_and_unrendered_intent():
    flags = {"no_media": False, "quick": False}
    rc = {"decision": "real_capture_direction", "decision_reason": "M6: real product output is never faked; capture the real terminal",
          "delete_test": "The receipt is the joke.", "aspect_ratio": "4:5", "alt_text": "Terminal log: the agent reports buying one domain.",
          "real_capture_direction": {"what_to_open": "the agent run log in the terminal", "what_to_type": None,
                                     "what_to_show": "the purchase confirmation line", "crop": "tight to the three lines, 4:5",
                                     "redact": "card digits, registrar account id"}}
    lines = ar.media_block_lines({"brief": rc, "prompts": {}, "check": None, "judge": None}, {"decision": "real_capture_direction"}, flags)
    assert lines[0].startswith("Capture it yourself · 4:5 · open: the agent run log in the terminal · show: the purchase confirmation line"
                               " · crop: tight to the three lines, 4:5 · redact: card digits, registrar account id · why: M6")
    assert "Alt text: Terminal log: the agent reports buying one domain." in lines
    assert "- Open: the agent run log in the terminal" in lines and "- Redact: card digits, registrar account id" in lines
    assert not any(ln.startswith("```") for ln in lines)
    video = {"decision": "video", "decision_reason": "M2: native video with the hook in the first second", "delete_test": "Without it the reader never sees the hand.",
             "aspect_ratio": "9:16", "target_pixels": "1080x1920", "resolution_tier": "2K", "alt_text": "A hand writes on a form.",
             "tool": {"primary": "veo_3_1", "reason": "native audio", "fallback": "runway_gen_4_5"}, "video": {"duration_s": 8}}
    lines = ar.media_block_lines({"brief": video, "prompts": {"veo": "Static medium close-up...", "runway": "Locked frame..."}, "check": None, "judge": None},
                                 {"decision": "video"}, flags)
    assert lines[0] == ("Video · 9:16 · Veo 3.1 (fallback Runway Gen-4.5) · 8s · why: M2: native video with the hook in the first second"
                        " · delete test: Without it the reader never sees the hand.")
    assert lines[2] == "Veo 3.1 · 9:16 · 8s · 1080x1920 · fallback Runway Gen-4.5" and lines[3:6] == ["```text", "Static medium close-up...", "```"]
    assert lines[6] == "Runway Gen-4.5 · 9:16 · 8s · 1080x1920" and lines[8] == "Locked frame..."
    none = ar.media_block_lines({"brief": {"decision": "none", "decision_reason": "M1: the line is the joke", "delete_test": "nothing: the line is the joke"},
                                 "prompts": {}, "check": None, "judge": None}, {"decision": "none"}, flags)
    assert none == ["No media: the line is the joke"]
    intent = ar.media_block_lines({"brief": None, "prompts": {}, "check": None, "judge": None},
                                  {"decision": "image", "delete_test": "the form is the receipt"}, {"no_media": True, "quick": False})
    assert intent == ["Media intent: image (not rendered: --no-media); delete test: the form is the receipt"]
    assert ar.media_block_lines({"brief": None, "prompts": {}, "check": None, "judge": None}, {"decision": "none", "delete_test": "nothing: the rhythm is the hook"},
                                flags) == ["No media: the rhythm is the hook"]


def test_terminal_prints_only_the_primary_prompt_and_points_at_the_fallback(proj: Path):
    out = _cli(RUN, "--show-verdicts", root=proj).stdout
    li_block = out.split("## LinkedIn · PASSED", 1)[1].split("## X · PASSED", 1)[0]
    assert "Nano Banana · 4:5 · 1080x1350 · 2K · fallback GPT Image\n```text\nCreate a photorealistic fake-document image" in li_block
    assert "Use: fake-document photo for a LinkedIn post" not in li_block
    assert "(fallback prompt for GPT Image in final/<cid>.md)" in li_block
    assert "No media: the line is the joke" in out.split("## X · PASSED", 1)[1]


# =============================================================================== report.md

def test_report_full_mode_has_every_check_and_dimension_as_its_own_row(proj: Path):
    _cli(RUN, "--show-verdicts", root=proj)
    rep = (_final(proj) / "report.md").read_text(encoding="utf-8")
    head = rep.splitlines()[0]
    for piece in ("agents buying domains to be safe", RUN, "rubric v1", "profile p3", "lexicon v1", "health none",
                  "small-corpus mode: lineup uses train posts", "voice anchor: weak (self n=2)", "matrix fallback rung 1",
                  "2 rounds", "65 calls", "9m40s"):
        assert piece in head, piece
    li_section = rep.split("### LinkedIn · ", 1)[1].split("### X · ", 1)[0]
    merged = _rj(proj / "drafts" / RUN / "round1" / "scores" / f"{LI}.merged.json")
    for chk in merged["tier0"]:
        assert re.search(rf"^\| {re.escape(chk)} \| ", li_section, flags=re.MULTILINE), chk
    for dim in merged["tier1"]:
        assert re.search(rf"^\| {dim} \| ", li_section, flags=re.MULTILINE), dim
    assert "| P1_length | hard | 822 | <= 3000 | pass |  |" in li_section
    assert "| E1_envelope | advisory (was soft) | 0.81 | 0.7 | pass | sent_words.cv 0.31 (envelope 0.48-0.9) |" in li_section
    assert ('| clarity | hard | 5 | >= 4 | pass | "We gave an agent a company card and asked it to register one domain for the launch." '
            "- the thesis is recoverable from the first two lines |") in li_section
    assert "| register_match_self | soft | na | >= 4 | na | fewer than 5 self samples; register_match_self is na |" in li_section
    assert "| claims | special | 3 claim(s): needs_check 2, joke 1 | no wrong claim | pass |" in li_section
    assert "| lineup | tier2 hard | 1/3 picked at conf 2, 0 strong | fail: >= 2 at conf >= 4, or all | pass | reader conf 2: the Estonian aside feels engineered" in li_section
    assert "| paraphrase (exemplars) | tier2 hard | own post | no judge says same | pass | acosta_003: own; welsh_011: own |" in li_section
    assert "| pairwise (vale_102) | tier2 advisory | 1 win / 1 tie / 0 loss | not 0 wins and 0 ties | pass |" in li_section
    assert "| media | tier2 hard | check pass · judge pass | both pass | pass |" in li_section
    assert "#### Lineup (pass; rule: fail iff >= 2 picks" in li_section
    assert "| reader | yes | 2 | the Estonian aside feels engineered | which the agent noted was \"available and cheap\" |" in li_section
    assert "#### Pairwise vs vale_102 (advisory): pairwise win/tie" in li_section and "| voice | tie (win / loss) | win (win / win) |" in li_section
    assert "| the agent registered 400 domains | verified | brief.user_detail | no |" in li_section
    assert "media_check: pass (warnings: person: capitalized name-like pair" in li_section
    assert "| alt_text_alone | pass | \"the item line reads: one domain, to be safe\" - the alt text lands the joke by itself |" in li_section
    assert "| executable | score 4 |" in li_section and "| capture_direction | na |  |" in li_section


def test_report_full_mode_alternate_needs_call_did_not_pass_rounds_and_ops(proj: Path):
    _cli(RUN, "--show-verdicts", root=proj)
    rep = (_final(proj) / "report.md").read_text(encoding="utf-8")
    order = [rep.index(s) for s in ("## Finalists", "## Alternates (passed Tier 0-1, not lineup-tested", "## Needs your call",
                                    "## Did not pass", "## Ops reminders")]
    assert order == sorted(order)
    assert '| O1_ngram | flag | 6-gram, lcs 27 | flag at 6-gram, reject at 8 | waived | "the only member of the team" - 6-gram shared with acosta_002 |' in rep
    assert '| persona_fit | hard | 3 · jury 3/3/3 median 3 | >= 4 | fail | "our agent has run 3 domains in prod for 6 weeks" - persona.can_claim#1 says three agents' in rep
    assert "| 3 domains in prod for 6 weeks | needs_check | persona.can_claim#1 | yes |" in rep
    assert 'Your call: persona_fit 3 (jury 3/3/3), claim "3 domains in prod for 6 weeks" needs confirmation (persona.can_claim#1)' in rep
    assert ('| humor | soft | 3 · jury 3/3/2 median 3 | >= 4 | fail | "The agent has asked for a replacement." - the third item escalates in size, '
            "not in kind; the button is a callback without a turn → fix: make Wednesday break the pattern of the list, not extend it |") in rep
    assert "#### Rounds and what changed" in rep
    assert "- round 1 · r1-w3-li · did not pass · failing: not_ai" in rep
    assert ('  - packet: not_ai (soft, 2/4) "Guardrails are not a feature. They are the product." - a moralising closer that restates the thesis as a slogan'
            " → fix: cut the closing aphorism; end on the incident report → cleared in the next round") in rep
    assert "- round 2 · r2-w3-li · did not pass · failing: humor" in rep
    assert 'Failing dimensions and evidence:\n- humor 3/4 (jury 3/3/2): "The agent has asked for a replacement."' in rep
    ops = rep.split("## Ops reminders", 1)[1]
    assert "**LinkedIn**" in ops and "- Zero hashtags; links either none or two or more." in ops
    assert "**X**" in ops and "- No link in the body; the system emits it as `reply_1`." in ops
    assert "small-corpus mode" in ops


def test_report_hidden_mode_collapses_verdicts_under_after_blind_rating(proj: Path):
    _cli(RUN, root=proj)
    rep = (_final(proj) / "report.md").read_text(encoding="utf-8")
    above, below = rep.split("<details>", 1)
    assert "<summary>After blind rating" in below and "## Finalists" in below and "## Did not pass" in below
    assert "| humor | soft | 3 · jury 3/3/2 median 3 | >= 4 | fail |" in below
    hits = [h for h in VERDICT_RE.findall(above.split("## Ops reminders", 1)[0]) if h.lower() != "pass"]
    assert not hits, hits
    assert f"Rate them blind first: /rate blind {RUN}" in above
    assert "#### Checks and dimensions (results withheld until the blind rating)" in above
    assert "| id | class | threshold | evidence quote |" in above
    assert '| clarity | hard | >= 4 | "We gave an agent a company card and asked it to register one domain for the launch." |' in above
    assert "| humor | soft | >= 4 |" in above and "median" not in above.split("## Ops reminders", 1)[0]
    assert "| text | source | needs_confirmation |" in above and "| 3 domains in prod for 6 weeks | persona.can_claim#1 | yes |" in above
    assert re.search(r"^### LinkedIn · [A-Z] \(822 chars", above, flags=re.MULTILINE)
    assert "r1-w1-li · PASSED" not in above


# =============================================================================== lineage.json and interop

def test_lineage_json_fields(proj: Path):
    _cli(RUN, "--show-verdicts", root=proj)
    lin = _rj(_final(proj) / "lineage.json")
    assert lin["schema"] == "postsmith.lineage/1" and lin["run"] == RUN and lin["topic"] == "agents buying domains to be safe"
    assert lin["versions"]["rubric"] == "v1" and lin["versions"]["profile"] == 3 and lin["versions"]["lexicon"] == 1
    assert re.fullmatch(r"[0-9a-f]{64}", lin["versions"]["rubric_sha"])
    assert lin["flags"]["quick"] is False and lin["flags"]["platform"] == "both"
    assert lin["brief"]["facts"][0].startswith("brief.fact#1: LinkedIn readers can flag") and len(lin["brief"]["facts"]) == 2
    assert len(lin["brief"]["obvious_takes"]) == 5 and lin["brief"]["story_id"] == "persona.story#2"
    assert lin["brief"]["user_detail"].startswith("the agent registered 400 domains")
    assert lin["matrix_rung"] == 1 and lin["matrix_seed"] == 4171 and lin["rounds"] == 2 and lin["calls"] == 65 and lin["wall_s"] == 580
    by = {v["cid"]: v for v in lin["variants"]}
    assert list(by) == [LI, X, ALT, NYC, DNP]
    li = by[LI]
    assert li["writer"] == "post-writer-1" and li["assignment"]["move"] == "corporate_register_for_trivial_event"
    assert li["angle_sheet"]["pick"] == "the agent that over-delivered: 400 domains to be safe"
    assert li["exemplars_seen"] == ["acosta_003", "welsh_011"] and li["lessons_used"] == ["L-023"]
    assert li["final_sha"] == common.content_sha(_text(proj, LI))
    assert li["scores_path"] == f"drafts/{RUN}/round1/scores/{LI}.merged.json"
    assert li["media_path"] == f"drafts/{RUN}/media/{LI}.brief.yaml" and li["media_decision"] == "image"
    assert li["verdict"] == "pass" and li["tier2_tested"] is True and li["final_path"] == f"drafts/{RUN}/final/{LI}.md"
    assert by[ALT]["waived"] == ["O1_ngram"] and by[ALT]["verdict"] == "passed_tier1_only" and by[ALT]["media_path"] is None
    assert by[NYC]["needs_confirmation"] == [{"claim": "3 domains in prod for 6 weeks", "source": "persona.can_claim#1", "from": "persona_fit"}]
    assert [r["cid"] for r in by[DNP]["rounds"]] == ["r1-w3-li", DNP]
    assert by[DNP]["rounds"][0]["soft_fails"] == ["not_ai"] and by[DNP]["rounds"][1]["soft_fails"] == ["humor"]
    assert by[X]["reply_1"].startswith("the incident report")


def test_draft_id_and_status_read_the_output(proj: Path):
    _cli(RUN, "--show-verdicts", root=proj)
    got = draft_id.resolve("agents li", root=proj)
    assert got["ok"] and got["cid"] == LI and got["path"] == f"drafts/{RUN}/final/{LI}.md" and got["platform"] == "linkedin"
    assert draft_id.resolve("agents x", root=proj)["cid"] == X
    assert draft_id.resolve(f"{RUN} {ALT}", root=proj)["cid"] == ALT
    doc = status_mod.collect(proj)
    assert doc["drafts"]["finished"] == 1 and doc["drafts"]["pending_blind_ratings"] == [RUN]


# =============================================================================== --copy, --json, errors, hygiene

def test_copy_pipes_the_top_linkedin_text_to_pbcopy(proj: Path, monkeypatch: pytest.MonkeyPatch):
    seen: dict = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ar.shutil, "which", lambda name: "/usr/bin/pbcopy" if name == "pbcopy" else None)
    monkeypatch.setattr(ar.subprocess, "run", fake_run)
    doc = ar.assemble(RUN, root=proj, copy=True)
    assert doc["copied"] is True and seen["cmd"] == ["/usr/bin/pbcopy"]
    assert seen["input"].decode("utf-8") == _text(proj, LI)


def test_copy_skips_silently_without_pbcopy(proj: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ar.shutil, "which", lambda name: None)
    monkeypatch.setattr(ar.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    doc = ar.assemble(RUN, root=proj, copy=True)
    assert doc["ok"] and doc["copied"] is False


def test_json_output_shapes(proj: Path):
    hidden = json.loads(_cli(RUN, "--json", root=proj).stdout)
    assert hidden["ok"] and hidden["verdicts_hidden"] is True and hidden["run"] == RUN
    assert set(hidden["files"]) == {*ALL, "clipboard.md", "report.md", "lineage.json", "blind.json"}
    assert [it["key"] for it in hidden["blind"]["items"]] == ["A", "B", "C"]
    for v in hidden["variants"]:
        assert "verdict" not in v and "label" not in v and "section" not in v and v["letter"]
    shown = json.loads(_cli(RUN, "--json", "--show-verdicts", root=proj).stdout)
    assert shown["verdicts_hidden"] is False
    by = {v["cid"]: v for v in shown["variants"]}
    assert by[LI]["verdict"] == "pass" and by[LI]["label"] == "PASSED" and by[LI]["section"] == "finalists"
    assert by[ALT]["label"] == "passed Tier 0-1, not lineup-tested" and by[NYC]["section"] == "needs_your_call"
    assert by[DNP]["evidence_line"].startswith('humor 3/4 (jury 3/3/2): "The agent has asked for a replacement."')
    assert by[LI]["evidence_line"].startswith('"We gave an agent a company card')
    assert shown["terminal"].startswith("# agents buying domains to be safe")
    assert shown["header"].startswith("agents buying domains to be safe · ")


def test_user_errors_exit_zero_with_json(proj: Path):
    doc = json.loads(_cli("2026-01-01_no-such-run", "--json", root=proj).stdout)
    assert doc == {"ok": False, "error": "run directory not found: drafts/2026-01-01_no-such-run"}
    rd = proj / "drafts" / "2026-09-18_empty"
    (rd / "round1" / "candidates").mkdir(parents=True)
    (rd / "round1" / "candidates" / "r1-w1-li.md").write_text("---\ncid: r1-w1-li\nplatform: linkedin\n---\nhello there friend\n", encoding="utf-8")
    doc = json.loads(_cli("2026-09-18_empty", "--json", root=proj).stdout)
    assert doc["ok"] is False and "nothing to deliver" in doc["error"]
    assert not (rd / "final").exists()


def test_writes_only_under_final_and_keeps_live_text(proj: Path):
    rd = proj / "drafts" / RUN
    before = {str(p.relative_to(rd)): p.read_bytes() for p in rd.rglob("*") if p.is_file()}
    (rd / "final").mkdir()
    (rd / "final" / f"{LI}.live.txt").write_text("posted text\n", encoding="utf-8")
    (rd / "final" / ".stale").write_text("", encoding="utf-8")
    _cli(RUN, root=proj)
    after = {str(p.relative_to(rd)): p.read_bytes() for p in rd.rglob("*") if p.is_file() and "final" not in p.parts}
    assert after == before
    assert (rd / "final" / f"{LI}.live.txt").read_text(encoding="utf-8") == "posted text\n"
    assert not (rd / "final" / ".stale").exists()
    assert not (PROJECT / "drafts" / RUN).exists()


def test_health_state_reaches_the_header(proj: Path):
    reports = proj / "evals" / "health" / "reports"
    sha = status_mod.rubric_sha(proj)
    (reports / f"2026-09-16_{sha[:8]}_p3.md").write_text("# health\nstate: green\n", encoding="utf-8")
    assert " · health green · " in ar.assemble(RUN, root=proj, write=False)["header"]
    (reports / "2026-09-17_0badcafe_p3.md").write_text("# health\nstate: green\n", encoding="utf-8")
    assert f" · health stale for rubric sha {sha[:8]} · " in ar.assemble(RUN, root=proj, write=False)["header"]


def test_run_log_stats_and_brief_parser(proj: Path):
    rd = proj / "drafts" / RUN
    assert ar.run_log_stats(rd, {}) == {"calls": 65, "wall_s": 580}
    (rd / "run.log").unlink()
    assert ar.run_log_stats(rd, {"created_at": "2026-09-17T09:00:00Z", "updated_at": "2026-09-17T09:01:30Z"}) == {"calls": None, "wall_s": 90}
    (rd / "brief.md").unlink()
    assert ar.parse_brief(rd) == {"facts": [], "obvious_takes": [], "user_detail": None, "story_id": None}
    doc = ar.assemble(RUN, root=proj, write=False)
    assert "calls" not in doc["header"] and doc["ok"]


def test_failing_lines_and_pairwise_phrase(proj: Path):
    rep = ar.collect(proj, RUN, show_verdicts=True)
    by = {v["cid"]: v for v in rep["variants"]}
    assert ar.failing_lines(by[DNP]) == [('humor 3/4 (jury 3/3/2): "The agent has asked for a replacement." - the third item escalates '
                                          "in size, not in kind; the button is a callback without a turn")]
    assert ar.failing_lines(by[LI]) == []
    # the X finalist has no reference-mode score; its Tier 2 pairwise is the exemplar paraphrase gate run_next runs
    assert ar.pairwise_phrase(by[LI]) == "pairwise win/tie" and ar.pairwise_phrase(by[X]) == "paraphrase clean vs 2 exemplars"
    assert ar.pairwise_phrase(by[ALT]) == "pairwise not run"
    assert ar.lineup_summary(by[LI])["picks"] == 1 and ar.lineup_summary(by[X])["picks"] == 0 and ar.lineup_summary(by[ALT]) is None
