#!/usr/bin/env python3
"""Write drafts/<run>/final/ from a delivered run and print the terminal layout
(contracts section 17 and 18; .claude/skills/post/references/output_contract.md).

    uv run tools/assemble_report.py <run> [--copy] [--show-verdicts | --hide-verdicts] [--root R] [--json]

Reads only the run directory (candidates, scores/<cid>.merged.json, tier2/*.score.json, tier2/claims_<cid>.json,
media/<cid>.*) plus the project's versions (rubric, profile, lexicon, health report names, small-corpus rule) and
writes:

    final/<cid>.md        one per delivered variant: front matter, the post text fenced exactly as pasted, reply_1
                          (X), "Why this works" from the candidate's own angle sheet and assignment (never judge
                          text), the media block (prompts with a settings line, or the capture direction, or
                          "No media"), "Confirm before posting"
    final/clipboard.md    texts only, one-word headers, ===== separators, reply_1 after an X text
    final/report.md       header line, per-variant score tables (every Tier 0 check and judged dimension as its own
                          row), Tier 2 results, claims, media, rounds and what changed, needs your call, did not
                          pass, ops reminders; in hidden mode the verdicts sit under "After blind rating"
    final/lineage.json    run, topic, versions, brief facts, per-variant provenance and verdict
    final/blind.json      the blind-rating set: finalist, an alternate, a did-not-pass, seed-shuffled, verdict-free
                          ({key, platform, text} only); final/blind.key.json holds the key -> cid mapping

Verdict labels come only from merged.json `verdict.status` (aggregate.py is the only writer of that file). They are
hidden by default until evals/calibration.jsonl holds a `blind: true` row for the run; --show-verdicts forces them,
--hide-verdicts forces hidden mode. --copy pipes the top LinkedIn text to pbcopy (skipped silently when absent).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import matrix  # noqa: E402
import run_next  # noqa: E402
import status as status_mod  # noqa: E402

FINAL_SCHEMA = "postsmith.final/1"
LINEAGE_SCHEMA = "postsmith.lineage/1"
BLIND_SCHEMA = "postsmith.blind/1"
BLIND_KEY_SCHEMA = "postsmith.blind_key/1"
LABELS: dict[str, str] = {
    "pass": "PASSED",
    "passed_tier1_only": "passed Tier 0-1, not lineup-tested",
    "needs_your_call": "needs your call",
    "hold": "needs your call",
    "fail": "did not pass",
}
SECTIONS = ("finalists", "alternates", "needs_your_call", "did_not_pass")
SECTION_TITLES = {"finalists": "Finalists", "alternates": "Alternates (passed Tier 0-1, not lineup-tested; run --wide to test)",
                  "needs_your_call": "Needs your call", "did_not_pass": "Did not pass"}
PLATFORM_ORDER = ("linkedin", "x")
PLATFORM_NAMES = {"linkedin": "LinkedIn", "x": "X"}
CLIP_HEADERS = {"li": "LINKEDIN", "x": "X", "x1": "X1"}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TOOL_NAMES = {"gpt_image": "GPT Image", "nano_banana": "Nano Banana", "nano_banana_pro": "Nano Banana Pro",
              "nano_banana_2": "Nano Banana 2", "veo": "Veo", "veo_3_1": "Veo 3.1", "runway": "Runway",
              "runway_gen_4_5": "Runway Gen-4.5"}
VIDEO_FAMILIES = ("veo", "runway")
HIDDEN_NOTE = "Verdicts, scores and evidence: hidden until /rate blind {run}; then in drafts/{run}/final/report.md."
CLOSING_BLIND = "Rate them blind first: /rate blind {run}"
STALE_MARKERS = (".stale", "STALE", "stale")
_ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z?")
_BRIEF_FACT_RE = re.compile(r"brief\.fact#\d+")
_STORY_RE = re.compile(r"persona\.story#\d+|story#\d+|\bS-\d{3,}\b")


# --------------------------------------------------------------------------- small helpers

def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)


def _one_line(s: Any, limit: int = 160) -> str:
    """Collapse whitespace and cut for a table cell (never used on paste text)."""
    t = common.collapse_ws(str(s or "")).replace("|", "\\|")
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _fmt_int(n: Any) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _fmt_num(x: Any) -> str:
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def _tool_name(tool_id: Any) -> str:
    t = str(tool_id or "").strip().lower()
    if not t:
        return ""
    if t in TOOL_NAMES:
        return TOOL_NAMES[t]
    fam = _tool_family(t)
    return TOOL_NAMES.get(fam, t)


def _tool_family(name: Any) -> str:
    n = str(name or "").strip().lower()
    if "gpt" in n or "dall" in n or "openai" in n:
        return "gpt_image"
    if "nano" in n or "banana" in n or "gemini" in n or "imagen" in n:
        return "nano_banana"
    if "veo" in n:
        return "veo"
    if "runway" in n:
        return "runway"
    return n


def _first_line(s: str) -> str:
    for ln in str(s or "").splitlines():
        if ln.strip():
            return ln.strip()
    return ""


def _short(s: str, limit: int = 72) -> str:
    s = common.collapse_ws(s)
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _plat_name(v: dict) -> str:
    if v["suffix"] == "x1":
        return "X1"
    return PLATFORM_NAMES.get(v["platform"], v["platform"])


def _plat_short(v: dict) -> str:
    return "li" if v["platform"] == "linkedin" else "x"


def _strip_nothing(delete_test: Any) -> str:
    t = str(delete_test or "").strip()
    return re.sub(r"^(?:nothing|none)\s*[:;,-]\s*", "", t, flags=re.IGNORECASE).strip() or t


# --------------------------------------------------------------------------- run-level inputs

def run_log_stats(rd: Path, state: dict) -> dict:
    """{"calls": int|None, "wall_s": int|None} from run.log timestamps (fallback: state.json timestamps)."""
    calls: int | None = None
    first: _dt.datetime | None = None
    last: _dt.datetime | None = None
    p = rd / "run.log"
    if p.exists():
        calls = 0
        for ln in p.read_text(encoding="utf-8").splitlines():
            m = _ISO_RE.match(ln.strip())
            if not m:
                continue
            try:
                ts = _dt.datetime.fromisoformat(m.group(1))
            except ValueError:
                continue
            first = ts if first is None else min(first, ts)
            last = ts if last is None else max(last, ts)
            if re.search(r"\bcall\b|\bagent=|\btool=", ln):
                calls += 1
    if first is None:
        for key in ("created_at", "updated_at"):
            m = _ISO_RE.match(str(state.get(key) or ""))
            if m:
                ts = _dt.datetime.fromisoformat(m.group(1))
                first = ts if first is None else min(first, ts)
                last = ts if last is None else max(last, ts)
    wall = int((last - first).total_seconds()) if first is not None and last is not None else None
    return {"calls": calls, "wall_s": wall}


def _fmt_wall(s: int | None) -> str | None:
    if s is None:
        return None
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{sec:02d}s"


def parse_brief(rd: Path) -> dict:
    """{"facts", "obvious_takes", "user_detail", "story_id"} from brief.md (every field optional)."""
    out: dict[str, Any] = {"facts": [], "obvious_takes": [], "user_detail": None, "story_id": None}
    p = rd / "brief.md"
    if not p.exists():
        return out
    section = ""
    lines = p.read_text(encoding="utf-8").splitlines()
    for i, raw in enumerate(lines):
        ln = raw.strip()
        if ln.startswith("#"):
            section = ln.lstrip("#").strip().lower()
            continue
        if _BRIEF_FACT_RE.search(ln):
            out["facts"].append(ln.lstrip("-* ").strip())
            continue
        if "brief.user_detail" in ln:
            detail = ln.split("brief.user_detail", 1)[1].lstrip(" :").strip()
            if not detail and i + 1 < len(lines):
                detail = lines[i + 1].strip()
            out["user_detail"] = detail or None
            continue
        if out["story_id"] is None and ("story" in section or ln.lower().startswith("story")):
            m = _STORY_RE.search(ln)
            if m:
                out["story_id"] = m.group(0)
        if re.search(r"do not write|obvious", section) and ln.startswith(("-", "*")):
            out["obvious_takes"].append(ln.lstrip("-* ").strip())
    if out["user_detail"] and out["user_detail"].lower() in ("none", "(none)", "-"):
        out["user_detail"] = None
    return out


def readme_ops_notes(root: Path, platforms: set[str]) -> dict[str, list[str]]:
    """The README's `## Ops notes` bullets per platform ({"LinkedIn": [...], "X": [...]}), empty when absent."""
    p = root / "README.md"
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    m = re.search(r"(?ms)^##\s+Ops notes\s*$(.*?)(?=^##\s|\Z)", text)
    if not m:
        return {}
    out: dict[str, list[str]] = {}
    current: str | None = None
    for raw in m.group(1).splitlines():
        ln = raw.strip()
        hm = re.match(r"^\*\*([^*]+)\*\*\s*$", ln)
        if hm:
            current = hm.group(1).strip()
            continue
        if current and ln.startswith(("-", "*")):
            out.setdefault(current, []).append(ln.lstrip("-* ").strip())
    wanted = {PLATFORM_NAMES[p] for p in platforms if p in PLATFORM_NAMES}
    return {k: v for k, v in out.items() if not wanted or k in wanted}


def blind_rated(root: Path, run: str) -> bool:
    """True when evals/calibration.jsonl holds a blind: true row for this run."""
    for row in common.read_jsonl(root / "evals" / "calibration.jsonl"):
        if not isinstance(row, dict) or not row.get("blind"):
            continue
        ref = str(row.get("post_ref") or row.get("run") or "")
        if ref == run or ref.startswith((run + "/", run + ":")):
            return True
    return False


def self_sample_count(root: Path, profile: dict | None) -> int | None:
    scopes = (profile or {}).get("scopes") if isinstance(profile, dict) else None
    if isinstance(scopes, dict) and isinstance(scopes.get("self"), dict) and scopes["self"].get("n") is not None:
        try:
            return int(scopes["self"]["n"])
        except (TypeError, ValueError):
            pass
    d = root / "corpus" / "self"
    return len(list(d.glob("*.md"))) if d.exists() else None


def moves_index(root: Path) -> dict[str, dict]:
    p = root / "style" / "moves.md"
    if not p.exists():
        return {}
    try:
        return {m["id"]: m for m in matrix.parse_moves_md(p.read_text(encoding="utf-8"))}
    except Exception:  # noqa: BLE001 - a malformed moves file only costs the mechanism line
        return {}


# --------------------------------------------------------------------------- media inputs

def load_media(root: Path, rd: Path, cid: str) -> dict:
    """Brief, rendered prompts, media_check and media-judge documents for one cid (each optional)."""
    md = rd / "media"
    brief_path = md / f"{cid}.brief.yaml"
    out: dict[str, Any] = {"brief": None, "brief_path": None, "prompts": {}, "check": None, "judge": None}
    if brief_path.exists():
        try:
            b = common.load_yaml(brief_path)
            if isinstance(b, dict) and isinstance(b.get("media_brief"), dict):
                b = b["media_brief"]
            out["brief"] = b if isinstance(b, dict) else None
        except Exception:  # noqa: BLE001 - an unreadable brief is reported as missing
            out["brief"] = None
        out["brief_path"] = _rel(root, brief_path)
    pdir = md / f"{cid}.prompts"
    if pdir.is_dir():
        for p in sorted(pdir.iterdir()):
            if p.suffix.lower() in (".md", ".txt") and p.is_file():
                out["prompts"][p.stem] = p.read_text(encoding="utf-8").rstrip("\n")
    chk = common.read_json(md / f"{cid}.media-check.json", default=None)
    out["check"] = chk if isinstance(chk, dict) else None
    jd = common.read_json(md / f"{cid}.media-judge.json", default=None)
    out["judge"] = jd if isinstance(jd, dict) else None
    return out


def media_settings_line(brief: dict, tool_id: str) -> str:
    """`Nano Banana Pro · 4:5 · 1080x1350 · 2K · fallback GPT Image` (duration instead of resolution for video)."""
    tool = brief.get("tool") if isinstance(brief.get("tool"), dict) else {}
    primary = str(tool.get("primary") or "")
    fallback = str(tool.get("fallback") or "")
    fam = _tool_family(tool_id)
    if primary and _tool_family(primary) == fam:
        name = _tool_name(primary)          # the brief names the exact model ("nano_banana_pro", "veo_3_1")
    elif fallback and _tool_family(fallback) == fam:
        name = _tool_name(fallback)
    else:
        name = _tool_name(tool_id)
    parts = [name or tool_id]
    if brief.get("aspect_ratio"):
        parts.append(str(brief["aspect_ratio"]))
    decision = str(brief.get("decision") or "").lower()
    video = brief.get("video") if isinstance(brief.get("video"), dict) else {}
    if decision == "video" or _tool_family(tool_id) in VIDEO_FAMILIES:
        if video.get("duration_s") is not None:
            parts.append(f"{_fmt_num(video['duration_s'])}s")
        if brief.get("target_pixels"):
            parts.append(str(brief["target_pixels"]))
    else:
        if brief.get("target_pixels"):
            parts.append(str(brief["target_pixels"]))
        if brief.get("resolution_tier"):
            parts.append(str(brief["resolution_tier"]))
    if fallback and _tool_family(fallback) != fam:
        parts.append(f"fallback {_tool_name(fallback)}")
    return " · ".join(parts)


def media_headline(brief: dict) -> str:
    """The one-line media summary for the terminal: kind · aspect · tool (fallback) · why · delete test."""
    decision = str(brief.get("decision") or "none").lower()
    reason = _one_line(brief.get("decision_reason"), 200)
    delete = _one_line(_strip_nothing(brief.get("delete_test")), 200)
    if decision == "none":
        return f"No media: {delete or reason or 'the text carries it'}"
    if decision == "real_capture_direction":
        rcd = brief.get("real_capture_direction") if isinstance(brief.get("real_capture_direction"), dict) else {}
        bits = ["Capture it yourself"]
        if brief.get("aspect_ratio"):
            bits.append(str(brief["aspect_ratio"]))
        for key, label in (("what_to_open", "open"), ("what_to_type", "type"), ("what_to_show", "show"),
                           ("crop", "crop"), ("redact", "redact")):
            if rcd.get(key):
                bits.append(f"{label}: {_one_line(rcd[key], 120)}")
        if reason:
            bits.append(f"why: {reason}")
        return " · ".join(bits)
    tool = brief.get("tool") if isinstance(brief.get("tool"), dict) else {}
    primary = _tool_name(tool.get("primary")) or "tool unspecified"
    fallback = _tool_name(tool.get("fallback"))
    kind = "Video" if decision == "video" else "Image"
    bits = [kind]
    if brief.get("aspect_ratio"):
        bits.append(str(brief["aspect_ratio"]))
    bits.append(f"{primary} (fallback {fallback})" if fallback else primary)
    video = brief.get("video") if isinstance(brief.get("video"), dict) else {}
    if decision == "video" and video.get("duration_s") is not None:
        bits.append(f"{_fmt_num(video['duration_s'])}s")
    if reason:
        bits.append(f"why: {reason}")
    if delete:
        bits.append(f"delete test: {delete}")
    return " · ".join(bits)


def media_block_lines(media: dict, intent: dict | None, flags: dict, terminal: bool = False) -> list[str]:
    """Markdown lines for the media section (final/<cid>.md) or the terminal (primary prompt only)."""
    brief = media.get("brief")
    intent = intent if isinstance(intent, dict) else {}
    decision_intent = str(intent.get("decision") or "none").lower()
    if not isinstance(brief, dict):
        if decision_intent == "none":
            return [f"No media: {_strip_nothing(intent.get('delete_test')) or 'the text carries it'}"]
        why = "not rendered: --no-media" if flags.get("no_media") else ("intent shown but not rendered: --quick" if flags.get("quick")
                                                                        else "no media brief on disk")
        return [f"Media intent: {decision_intent} ({why})" + (f"; delete test: {intent['delete_test']}" if intent.get("delete_test") else "")]
    lines = [media_headline(brief)]
    decision = str(brief.get("decision") or "none").lower()
    if decision == "none":
        return lines
    if not terminal and brief.get("alt_text"):
        lines.append(f"Alt text: {brief['alt_text']}")
    if decision == "real_capture_direction":
        rcd = brief.get("real_capture_direction") if isinstance(brief.get("real_capture_direction"), dict) else {}
        for key, label in (("what_to_open", "Open"), ("what_to_type", "Type"), ("what_to_show", "Show"),
                           ("crop", "Crop"), ("redact", "Redact")):
            if rcd.get(key):
                lines.append(f"- {label}: {rcd[key]}")
        if not rcd:
            lines.append("- (capture direction block missing from the brief)")
        return lines
    prompts: dict[str, str] = media.get("prompts") or {}
    tool = brief.get("tool") if isinstance(brief.get("tool"), dict) else {}
    primary_fam = _tool_family(tool.get("primary"))
    ordered = sorted(prompts.items(), key=lambda kv: (_tool_family(kv[0]) != primary_fam, kv[0]))
    if terminal:
        ordered = ordered[:1]
    if not ordered:
        lines.append("(no rendered tool prompt under media/<cid>.prompts/)")
    for name, text in ordered:
        lines.append(media_settings_line(brief, name))
        lines.append("```text")
        lines.append(text)
        lines.append("```")
    if terminal and len(prompts) > 1:
        others = ", ".join(_tool_name(n) for n, _ in sorted(prompts.items())[1:] if _tool_family(n) != primary_fam) or \
            ", ".join(_tool_name(n) for n in prompts if _tool_family(n) != primary_fam)
        if others:
            lines.append(f"(fallback prompt for {others} in final/<cid>.md)")
    return lines


def media_judge_rows(judge: dict | None) -> list[tuple[str, str, str]]:
    """(sub-result, result, evidence) rows from a media-judge document."""
    if not isinstance(judge, dict):
        return []
    media = ((judge.get("dimensions") or {}).get("media") or {}) if isinstance(judge.get("dimensions"), dict) else {}
    if media.get("na"):
        return [("media", "na", _one_line(media.get("pre_step")))]
    subs = media.get("sub_results") if isinstance(media.get("sub_results"), dict) else {}
    rows: list[tuple[str, str, str]] = []
    for key in ("alt_text_alone", "does_work", "slop_screen", "executable", "factual", "capture_direction"):
        s = subs.get(key)
        if not isinstance(s, dict):
            continue
        if s.get("na"):
            res = "na"
        elif "pass" in s:
            res = "pass" if s.get("pass") else "fail"
        elif s.get("score") is not None:
            res = f"score {s['score']}"
        else:
            res = "unscored"
        ev = s.get("evidence") or []
        ev0 = ev[0] if ev and isinstance(ev[0], dict) else {}
        rows.append((key, res, _one_line(f'"{ev0.get("quote", "")}" - {ev0.get("why", "")}' if ev0 else "")))
    return rows


# --------------------------------------------------------------------------- variants

def _fold_line(tier0: dict | None, text: str) -> str:
    if isinstance(tier0, dict):
        p2 = (tier0.get("checks") or {}).get("P2_fold") if isinstance(tier0.get("checks"), dict) else None
        if isinstance(p2, dict) and p2.get("preview"):
            return _first_line(str(p2["preview"]))
        if tier0.get("fold_preview"):
            return _first_line(str(tier0["fold_preview"]))
    return _first_line(text)


def _needs_confirmation(merged: dict) -> list[dict]:
    out: list[dict] = []
    for x in ((merged.get("verdict") or {}).get("needs_confirmation") or []):
        if isinstance(x, dict):
            out.append({"claim": x.get("claim") or x.get("text"), "source": x.get("source"), "from": x.get("from")})
    return out


def build_variant(root: Path, rd: Path, run: str, c: Any, cfg: dict) -> dict:
    """Everything the renderers need about one candidate (a run_next.Cand with a merged document)."""
    merged: dict = c.merged or {}
    tier0: dict = c.tier0 if isinstance(c.tier0, dict) else {}
    text = c.text.rstrip("\n")
    meta: dict = c.meta or {}
    assignment = meta.get("assignment") if isinstance(meta.get("assignment"), dict) else {}
    angle = meta.get("angle_sheet") if isinstance(meta.get("angle_sheet"), dict) else {}
    lineage = meta.get("lineage") if isinstance(meta.get("lineage"), dict) else {}
    intent = meta.get("media_intent") if isinstance(meta.get("media_intent"), dict) else {}
    verdict = merged.get("verdict") or {}
    status = str(verdict.get("status") or "unscored")
    x_len = tier0.get("x_len")
    if c.platform == "x" and x_len is None:
        try:
            x_len = common.x_count(text, (cfg.get("platforms") or {}).get("x") or None)
        except Exception:  # noqa: BLE001
            x_len = None
    t2 = rd / "tier2"
    lineup_doc = common.read_json(t2 / f"lineup_{c.cid}.score.json", default=None)
    pairwise_ref = common.read_json(t2 / f"pairwise_{c.cid}.score.json", default=None)
    paraphrase = common.read_json(t2 / f"pairwise_{c.cid}.exemplars.score.json", default=None)
    claims_t2 = common.read_json(t2 / f"claims_{c.cid}.json", default=None)
    if isinstance(claims_t2, dict):
        claims_t2 = ((claims_t2.get("dimensions") or {}).get("claims") or {}).get("claims") or claims_t2.get("claims")
    m_t2 = merged.get("tier2") if isinstance(merged.get("tier2"), dict) else {}
    if not isinstance(lineup_doc, dict) and isinstance(m_t2.get("lineup"), dict):
        lineup_doc = m_t2["lineup"]
    claims_rows = claims_t2 if isinstance(claims_t2, list) else (m_t2.get("claims") if isinstance(m_t2.get("claims"), list) else None)
    if claims_rows is None:
        t1c = (merged.get("tier1") or {}).get("claims") or {}
        claims_rows = t1c.get("claims") if isinstance(t1c, dict) and isinstance(t1c.get("claims"), list) else []
    stop = c.stop
    return {
        "cid": c.cid, "platform": c.platform, "suffix": c.suffix or ("li" if c.platform == "linkedin" else "x"),
        "round": c.round, "writer": c.writer, "writer_no": c.writer_no, "meta": meta, "text": text,
        "chars": int(tier0.get("chars") or len(text)), "x_len": x_len,
        "fold_preview": str(tier0.get("fold_preview") or text[:140]), "fold_line": _fold_line(tier0, text),
        "merged": merged, "tier0": tier0, "status": status, "tier2_tested": bool(verdict.get("tier2_tested")),
        "assignment": assignment, "lens": assignment.get("lens"), "moves": [assignment["move"]] if assignment.get("move") else [],
        "angle_family": assignment.get("angle_family") or ((angle.get("candidates") or [{}])[0].get("family") if angle.get("candidates") else None),
        "angle_pick": angle.get("pick"), "angle_sheet": angle, "hook_type": meta.get("hook_type"), "ending": meta.get("ending"),
        "exemplars_seen": list(lineage.get("exemplars_seen") or []), "lessons_used": list(lineage.get("lessons_used") or []),
        "rewrite_of": lineage.get("rewrite_of"),
        "waived": list(verdict.get("waived") or []), "needs_confirmation": _needs_confirmation(merged),
        "reply_1": meta.get("reply_1") if c.platform == "x" else None,
        "scores_path": _rel(root, c.scores / f"{c.cid}.merged.json"),
        "candidate_path": _rel(root, c.md), "text_path": _rel(root, c.txt if c.txt.exists() else c.md),
        "media": load_media(root, rd, c.cid), "media_intent": intent,
        "lineup": lineup_doc if isinstance(lineup_doc, dict) else None,
        "pairwise_ref": pairwise_ref if isinstance(pairwise_ref, dict) else None,
        "paraphrase": paraphrase if isinstance(paraphrase, dict) else None,
        "claims": claims_rows, "stop": stop, "rank": run_next.rank_key(c),
        "final_sha": common.content_sha(text), "rounds": [],
    }


def assign_sections(variants: list[dict], quick: bool) -> None:
    """Section per variant from merged verdict.status (the only source of a label) and tier2_tested."""
    for v in variants:
        st = v["status"]
        if v["stop"] and v["stop"].get("reason") != "oscillation" and st not in ("pass", "passed_tier1_only"):
            v["section"] = "did_not_pass"
        elif st == "pass" and v["tier2_tested"]:
            v["section"] = "finalists"
        elif st in ("pass", "passed_tier1_only"):
            v["section"] = "alternates"
        elif st in ("needs_your_call", "hold"):
            v["section"] = "needs_your_call"
        else:
            v["section"] = "did_not_pass"
    # under --quick Tier 2 never runs, so each platform's best passing candidate is delivered first and its header
    # says "lineup skipped (quick)"; in a full run a pass without a lineup stays an alternate
    if quick:
        for plat in PLATFORM_ORDER:
            if any(v["section"] == "finalists" and v["platform"] == plat for v in variants):
                continue
            alts = sorted((v for v in variants if v["section"] == "alternates" and v["platform"] == plat and v["status"] == "pass"),
                          key=lambda v: v["rank"])
            if alts:
                alts[0]["section"] = "finalists"
                alts[0]["promoted"] = True
    for v in variants:
        if v["status"] == "pass" and v["section"] == "alternates":
            v["label"] = LABELS["passed_tier1_only"]      # a pass that Tier 2 never tested is the alternate label
        else:
            v["label"] = LABELS.get(v["status"], v["status"])


def order_variants(variants: list[dict]) -> list[dict]:
    def key(v: dict) -> tuple:
        return (SECTIONS.index(v["section"]), PLATFORM_ORDER.index(v["platform"]) if v["platform"] in PLATFORM_ORDER else 9,
                v["suffix"] == "x1", v["rank"])
    return sorted(variants, key=key)


def hidden_order(variants: list[dict]) -> list[dict]:
    """Display order while verdicts are hidden: blind letter, and nothing else. `order_variants` sorts by section
    (finalists first), which is the verdict itself - rendering that order would hand the answer to the blind rating
    before a single score is recorded (contracts §18, .claude/skills/rate/SKILL.md)."""
    return sorted(variants, key=lambda v: str(v.get("letter") or "~"))


def build_rounds(v: dict, all_cands: dict[str, Any], root: Path, rd: Path) -> list[dict]:
    """The rewrite chain behind a delivered variant, oldest first, with each round's packet and what cleared."""
    chain: list[Any] = []
    cur = all_cands.get(v["cid"])
    seen: set[str] = set()
    while cur is not None and cur.cid not in seen:
        seen.add(cur.cid)
        chain.append(cur)
        prev_cid = cur.rewrite_of
        if not prev_cid and cur.writer_no is not None and cur.round > 1:
            guess = f"r{cur.round - 1}-w{cur.writer_no}-{cur.suffix}"
            prev_cid = guess if guess in all_cands else None
        cur = all_cands.get(str(prev_cid)) if prev_cid else None
    chain.reverse()
    rows: list[dict] = []
    for i, c in enumerate(chain):
        m = c.merged or {}
        vd = m.get("verdict") or {}
        row: dict[str, Any] = {"round": c.round, "cid": c.cid, "verdict": vd.get("status"),
                               "hard_fails": list(vd.get("hard_fails") or []), "soft_fails": list(vd.get("soft_fails") or []),
                               "flags": list(vd.get("flags") or []), "stop": (m.get("stop") or {}).get("reason") if m.get("stop") else None,
                               "packet": [], "scores_path": _rel(root, c.scores / f"{c.cid}.merged.json")}
        packet = common.read_json(rd / f"round{c.round}" / "feedback" / f"{c.cid}.json", default=None)
        nxt = chain[i + 1] if i + 1 < len(chain) else None
        nvd = ((nxt.merged or {}).get("verdict") or {}) if nxt else {}
        nt0 = ((nxt.merged or {}).get("tier0") or {}) if nxt else {}
        nt1 = ((nxt.merged or {}).get("tier1") or {}) if nxt else {}
        if isinstance(packet, dict):
            for it in packet.get("tier0") or []:
                chk = str(it.get("check"))
                cleared = None
                if nxt:
                    r = nt0.get(chk)
                    cleared = not (isinstance(r, dict) and common.check_needs_action(r) and not r.get("waived") and not r.get("addressed"))
                row["packet"].append({"kind": "tier0", "id": chk, "class": it.get("class"), "evidence": it.get("evidence") or [],
                                      "fix": it.get("note"), "cleared": cleared})
            for it in packet.get("tier1") or []:
                dim = str(it.get("dimension"))
                cleared = None
                if nxt:
                    r = nt1.get(dim)
                    cleared = isinstance(r, dict) and r.get("result") in ("pass", "na")
                row["packet"].append({"kind": "tier1", "id": dim, "class": it.get("class"), "score": it.get("score"),
                                      "threshold": it.get("threshold"), "evidence": it.get("evidence") or [],
                                      "fix": it.get("suggested_fix"), "cleared": cleared})
            for key, it in (packet.get("tier2") or {}).items():
                row["packet"].append({"kind": "tier2", "id": key, "class": "tier2", "evidence": [], "fix": None,
                                      "cleared": (key not in (nvd.get("hard_fails") or [])) if nxt else None})
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- score rows

def _ev_span(ev: Any) -> str:
    if not isinstance(ev, dict):
        return _one_line(ev)
    quote = ev.get("span", ev.get("quote", ""))
    why = ev.get("why", "")
    return _one_line(f'"{quote}" - {why}' if why else f'"{quote}"')


def tier0_rows(merged: dict) -> list[dict]:
    rows: list[dict] = []
    env = merged.get("tier0_envelope") or {}
    for chk, r in (merged.get("tier0") or {}).items():
        if not isinstance(r, dict):
            continue
        cls = str(r.get("class", "advisory"))
        if r.get("class_original") and r.get("class_original") != cls:
            cls = f"{cls} (was {r['class_original']})"
        value = ""
        threshold = ""
        if r.get("value") is not None:
            value = _fmt_num(r["value"])
        if chk == "E1_envelope":
            value = _fmt_num(r.get("score", env.get("score", "")))
            threshold = _fmt_num(r.get("threshold", 0.70))
        elif r.get("limit") is not None:
            threshold = f"<= {_fmt_num(r['limit'])}"
        elif r.get("min_words") is not None:
            threshold = f">= {_fmt_num(r['min_words'])}"
        elif chk in ("O1_ngram", "O5_published"):
            value = f"{r.get('max_shared_ngram', '')}-gram, lcs {r.get('lcs_chars', '')}" if r.get("max_shared_ngram") is not None else value
            threshold = "flag at 6-gram, reject at 8"
        raised_flag = bool(r.get("pass", True)) and bool(r.get("flag"))
        if r.get("waived"):
            result = "waived"
        elif r.get("jury_override"):
            result = "pass (jury override)"
        elif r.get("jury_confirmed"):
            result = "fail (jury confirmed)"
        elif r.get("addressed"):
            result = "cleared"
        elif common.check_needs_action(r):
            result = "flag" if (cls.startswith("flag") or raised_flag) else ("advisory" if cls.startswith("advisory") else "fail")
        else:
            result = "pass"
        evidence = ""
        evs = r.get("evidence") or []
        if evs:
            evidence = _ev_span(evs[0])
        elif chk == "E1_envelope" and (r.get("out") or env.get("out")):
            outs = [o for o in (r.get("out") or env.get("out") or []) if isinstance(o, dict)]
            evidence = _one_line("; ".join(f"{o.get('feature')} {o.get('value')} (envelope {'-'.join(str(x) for x in (o.get('envelope') or []))})" for o in outs))
        elif r.get("hits"):
            h = r["hits"][0] if isinstance(r["hits"], list) and r["hits"] else None
            if isinstance(h, dict):
                evidence = _one_line(f'{h.get("n", "")}-gram with {h.get("ref")}: "{h.get("span", "")}"')
        if r.get("jury") and isinstance(r["jury"], dict) and r["jury"].get("votes"):
            j = r["jury"]
            value = (value + " · " if value else "") + f"jury {'/'.join(str(x) for x in j['votes'])} median {_fmt_num(j.get('median'))}"
        rows.append({"id": chk, "class": cls, "value": value, "threshold": threshold, "result": result, "evidence": evidence})
    return rows


def tier1_rows(merged: dict) -> list[dict]:
    rows: list[dict] = []
    for dim, r in (merged.get("tier1") or {}).items():
        if not isinstance(r, dict):
            continue
        cls = str(r.get("class", "soft"))
        threshold = f">= {_fmt_num(r['threshold'])}" if r.get("threshold") is not None else ""
        if dim == "claims":
            claims = r.get("claims") or []
            counts: dict[str, int] = {}
            for cl in claims:
                if isinstance(cl, dict):
                    counts[str(cl.get("status"))] = counts.get(str(cl.get("status")), 0) + 1
            value = f"{len(claims)} claim(s)" + (": " + ", ".join(f"{k} {n}" for k, n in counts.items()) if counts else "")
            evidence = "; ".join(_one_line(f'{cl.get("text")} ({cl.get("status")})', 80) for cl in claims[:3] if isinstance(cl, dict))
            rows.append({"id": dim, "class": cls, "value": value, "threshold": "no wrong claim", "result": str(r.get("result")),
                         "evidence": evidence})
            continue
        value = "" if r.get("score") is None else str(r["score"])
        if r.get("na"):
            value = "na"
        j = r.get("jury")
        if isinstance(j, dict) and j.get("votes"):
            value = (value + " · " if value else "") + f"jury {'/'.join(str(x) for x in j['votes'])} median {_fmt_num(j.get('median'))}"
        result = str(r.get("result") or "unscored")
        if r.get("jury_pending"):
            result += " (jury pending)"
        evs = r.get("evidence") or []
        if evs:
            evidence = _ev_span(evs[0])
        else:
            evidence = _one_line(r.get("note") or r.get("pre_step") or "")
        if r.get("suggested_fix") and result.startswith("fail"):
            evidence = (evidence + " → fix: " if evidence else "fix: ") + _one_line(r["suggested_fix"], 100)
        rows.append({"id": dim, "class": cls, "value": value, "threshold": threshold, "result": result, "evidence": evidence})
    return rows


def lineup_summary(v: dict) -> dict | None:
    lu = v.get("lineup")
    if not isinstance(lu, dict):
        return None
    picks = [p for p in (lu.get("picks") or []) if isinstance(p, dict)]
    n = int(lu.get("n_judges") or len(picks) or 0)
    hits = [p for p in picks if p.get("picked_candidate")]
    max_conf = max((int(p.get("confidence") or 0) for p in hits), default=0)
    if "pass" in lu:
        result = "pass" if lu.get("pass") else "fail"
    elif "flag" in lu:
        result = "flag" if lu.get("flag") else "clean"
    else:
        result = "unscored"
    return {"n": n, "picks": len(hits), "strong": int(lu.get("strong_picks") or 0), "max_conf": max_conf,
            "advisory": bool(lu.get("advisory")), "result": result, "rule": lu.get("rule"), "all": picks,
            "tells": [p for p in hits]}


def pairwise_phrase(v: dict) -> str:
    """`pairwise win/tie` from a reference-mode score, `paraphrase clean vs N exemplars` from the exemplar-mode gate
    run_next runs at Tier 2, `pairwise skipped, lineup clean`, or `pairwise not run`."""
    pw = v.get("pairwise_ref")
    if isinstance(pw, dict) and pw.get("ok", True):
        per = pw.get("per_lens") if isinstance(pw.get("per_lens"), dict) else {}
        outcomes = [str(x.get("better")) for x in per.values() if isinstance(x, dict) and x.get("better")]
        if outcomes:
            return "pairwise " + "/".join(outcomes)
        return f"pairwise {pw.get('wins', 0)}W/{pw.get('ties', 0)}T/{pw.get('losses', 0)}L"
    para = (v.get("merged") or {}).get("tier2", {}).get("paraphrase") if isinstance(v.get("merged"), dict) else None
    if isinstance(para, dict) and para.get("mode") == "exemplars" and not para.get("skipped"):
        n = len(para.get("verdicts") or [])
        state = "clean" if para.get("pass") is not False else "hit"
        return f"paraphrase {state}" + (f" vs {n} exemplar{'s' if n != 1 else ''}" if n else "")
    lu = lineup_summary(v)
    if lu and lu["picks"] == 0 and lu["n"] > 0:
        return "pairwise skipped, lineup clean"
    return "pairwise not run"


def tier2_rows(v: dict) -> list[dict]:
    rows: list[dict] = []
    lu = lineup_summary(v)
    if lu:
        tells = "; ".join(_one_line(f'{p.get("lens")} conf {p.get("confidence")}: {p.get("tell")} "{p.get("quote", "")}"', 90) for p in lu["tells"])
        rows.append({"id": "lineup", "class": "tier2 advisory" if lu["advisory"] else "tier2 hard",
                     "value": f"{lu['picks']}/{lu['n']} picked" + (f" at conf {lu['max_conf']}" if lu["picks"] else "") + f", {lu['strong']} strong",
                     "threshold": "fail: >= 2 at conf >= 4, or all", "result": lu["result"], "evidence": tells or "no judge picked the candidate"})
    para = v.get("paraphrase")
    m_t2 = (v["merged"].get("tier2") or {}) if isinstance(v["merged"].get("tier2"), dict) else {}
    if isinstance(para, dict) or isinstance(m_t2.get("paraphrase"), dict):
        pd = para if isinstance(para, dict) else m_t2.get("paraphrase")
        yes = bool(pd.get("paraphrase")) if "paraphrase" in pd else bool(pd.get("same_skeleton_or_joke") or pd.get("same_post_rewritten"))
        verdicts = pd.get("verdicts") or []
        ev = "; ".join(_one_line(f'{x.get("post_id")}: {"same" if x.get("same_skeleton_or_joke") else "own"}' + (f' "{x["evidence"]}"' if x.get("evidence") else ""), 80)
                       for x in verdicts if isinstance(x, dict))
        if pd.get("skipped"):
            ev = f"skipped: {pd['skipped']}"
        rows.append({"id": "paraphrase (exemplars)", "class": "tier2 hard", "value": "same skeleton/joke" if yes else "own post",
                     "threshold": "no judge says same", "result": "fail" if yes else "pass", "evidence": ev})
    pw = v.get("pairwise_ref")
    if isinstance(pw, dict):
        per = pw.get("per_lens") if isinstance(pw.get("per_lens"), dict) else {}
        ev = "; ".join(f"{lens}: better {x.get('better')} (orders {'/'.join(str(o) for o in (x.get('orders') or {}).values())}), voice {x.get('voice')}"
                       for lens, x in per.items() if isinstance(x, dict))
        rows.append({"id": f"pairwise ({pw.get('reference_id', 'reference')})", "class": "tier2 advisory",
                     "value": f"{pw.get('wins', 0)} win / {pw.get('ties', 0)} tie / {pw.get('losses', 0)} loss",
                     "threshold": "not 0 wins and 0 ties", "result": "pass" if pw.get("pass", True) else "fail", "evidence": _one_line(ev)})
    md = m_t2.get("media") if isinstance(m_t2.get("media"), dict) else None
    if md or v["media"].get("check") or v["media"].get("judge"):
        chk = v["media"].get("check") or {}
        chk_res = (md or {}).get("media_check") or ("pass" if chk.get("ok") else ("fail" if chk else "missing"))
        jd_res = (md or {}).get("media_judge") or ("missing" if not v["media"].get("judge") else run_next._media_judge_verdict(v["media"]["judge"]))
        fails = list((md or {}).get("check_fails") or chk.get("fails") or [])
        jrows = media_judge_rows(v["media"].get("judge"))
        ev = "; ".join(fails[:2]) if fails else "; ".join(f"{k} {r}" for k, r, _ in jrows if r not in ("pass",)) or "every hard sub-result passed"
        rows.append({"id": "media", "class": "tier2 hard", "value": f"check {chk_res} · judge {jd_res}", "threshold": "both pass",
                     "result": "pass" if (md or {}).get("pass", chk_res == "pass" and jd_res == "pass") else "fail", "evidence": _one_line(ev)})
    return rows


def claims_table(v: dict) -> list[dict]:
    rows: list[dict] = []
    needs = {str(x.get("claim")) for x in v["needs_confirmation"]}
    for cl in v.get("claims") or []:
        if not isinstance(cl, dict):
            continue
        st = str(cl.get("status") or "")
        rows.append({"text": cl.get("text"), "status": st, "source": cl.get("source"), "url": cl.get("url"),
                     "why": cl.get("why"), "needs_confirmation": (str(cl.get("text")) in needs) or st == "unverifiable"})
    for x in v["needs_confirmation"]:
        if not any(str(r["text"]) == str(x.get("claim")) for r in rows):
            rows.append({"text": x.get("claim"), "status": "needs_confirmation", "source": x.get("source"), "url": None,
                         "why": f"from {x.get('from') or 'persona_fit'}", "needs_confirmation": True})
    return rows


def failing_lines(v: dict) -> list[str]:
    """`humor 3/4 (jury 3/3/2): "quote" - why` for every failing dimension / check (the did-not-pass evidence)."""
    m = v["merged"]
    vd = m.get("verdict") or {}
    out: list[str] = []
    for chk in list(vd.get("hard_fails") or []) + list(vd.get("soft_fails") or []) + list(vd.get("flags") or []):
        r0 = (m.get("tier0") or {}).get(chk)
        r1 = (m.get("tier1") or {}).get(chk)
        if isinstance(r1, dict):
            head = f"{chk} {r1.get('score')}/{_fmt_num(r1.get('threshold'))}" if r1.get("score") is not None else f"{chk} {r1.get('result')}"
            j = r1.get("jury")
            if isinstance(j, dict) and j.get("votes"):
                head += f" (jury {'/'.join(str(x) for x in j['votes'])})"
            evs = r1.get("evidence") or []
            out.append(head + (f": {_ev_span(evs[0])}" if evs else ""))
        elif isinstance(r0, dict):
            evs = r0.get("evidence") or []
            head = f"{chk} ({r0.get('class')})"
            out.append(head + (f": {_ev_span(evs[0])}" if evs else ""))
        else:
            t2 = m.get("tier2") if isinstance(m.get("tier2"), dict) else {}
            if chk == "lineup":
                lu = lineup_summary(v)
                out.append(f"lineup {lu['picks']}/{lu['n']} picked ({lu['strong']} strong)" if lu else "lineup fail")
            elif chk in ("paraphrase", "pairwise"):
                out.append(f"{chk}: same skeleton or joke as an exemplar")
            elif chk == "claims":
                wrong = [c for c in (t2.get("claims") or []) if isinstance(c, dict) and c.get("status") == "wrong"]
                out.append("claims: " + "; ".join(_one_line(f'wrong: {c.get("text")}', 80) for c in wrong))
            elif chk == "media":
                md = t2.get("media") or {}
                out.append(f"media: check {md.get('media_check')} · judge {md.get('media_judge')}")
            else:
                out.append(chk)
    for dim in vd.get("unscored") or []:
        out.append(f"{dim}: unscored (hold survived the jury without evidence)")
    if v["stop"]:
        out.append(f"stop: {v['stop'].get('reason')} - {v['stop'].get('detail', '')}")
    return out


# --------------------------------------------------------------------------- run collection

def collect(root: Path, run: str, show_verdicts: bool | None = None) -> dict:
    """Gather everything the renderers need. Raises FileNotFoundError / ValueError for user errors."""
    rd = run_next.resolve_run_dir(root, run)
    run = rd.name
    if not rd.is_dir():
        raise FileNotFoundError(f"run directory not found: {_rel(root, rd)}")
    cfg = run_next.load_config_at(root)
    state = common.read_json(rd / "state.json", default={}) or {}
    state = state if isinstance(state, dict) else {}
    mx = common.read_json(rd / "matrix.json", default={}) or {}
    mx = mx if isinstance(mx, dict) else {}
    try:
        flags = run_next.normalize_flags(state.get("flags") or {}, cfg)
    except ValueError:
        flags = run_next.normalize_flags({}, cfg)
    topic = str(state.get("topic") or mx.get("topic") or _topic_from_brief(rd) or run.split("_", 1)[-1].replace("-", " "))
    cands = run_next.scan_candidates(root, rd)
    by_cid = {c.cid: c for c in cands}
    active = [c for c in cands if not c.superseded_by and isinstance(c.merged, dict)]
    skipped = [c.cid for c in cands if not c.superseded_by and not isinstance(c.merged, dict)]
    if not active:
        raise ValueError(f"nothing to deliver: no round*/scores/<cid>.merged.json under {_rel(root, rd)} "
                         "(aggregate.py merge writes them; run run_next.py first)")
    variants = [build_variant(root, rd, run, c, cfg) for c in active]
    assign_sections(variants, bool(flags.get("quick")))
    variants = order_variants(variants)
    for v in variants:
        v["rounds"] = build_rounds(v, by_cid, root, rd)
    profile = common.read_json(root / "style" / "profile.json", default=None)
    profile = profile if isinstance(profile, dict) else None
    profile_version = profile.get("profile_version") if profile else None
    lexicon = None
    if (root / "style" / "lexicon.yaml").exists():
        try:
            lexicon = common.load_yaml(root / "style" / "lexicon.yaml")
        except Exception:  # noqa: BLE001
            lexicon = None
    lexicon_version = lexicon.get("lexicon_version") if isinstance(lexicon, dict) else None
    merged0 = variants[0]["merged"]
    rubric_version = merged0.get("rubric_version") or run_next.rubric_version_at(root)
    rubric_sha = merged0.get("rubric_sha") or status_mod.rubric_sha(root)
    if profile_version is None:
        profile_version = merged0.get("profile_version")
    if lexicon_version is None:
        lexicon_version = merged0.get("lexicon_version")
    health = status_mod.health_state(root, profile_version if isinstance(profile_version, int) else None)
    small_corpus = common.small_corpus_mode(cfg, root) or any(bool(v["tier0"].get("small_corpus_mode")) for v in variants)
    lineup_advisory = any((lineup_summary(v) or {}).get("advisory") for v in variants)
    self_n = self_sample_count(root, profile)
    self_min = int((cfg.get("corpus") or {}).get("self_min_samples", 5))
    rung = mx.get("rung_max")
    if rung is None and isinstance(mx.get("assignments"), list):
        rung = max((int(a.get("rung") or 0) for a in mx["assignments"] if isinstance(a, dict)), default=None)
    hidden = not (show_verdicts if show_verdicts is not None else blind_rated(root, run))
    blind = build_blind(run, variants)
    letters = assign_letters(variants, blind)
    for v in variants:
        v["letter"] = letters[v["cid"]]
    log = run_log_stats(rd, state)
    rounds = max((v["round"] for v in variants), default=1)
    rounds = max(rounds, max((len(v["rounds"]) for v in variants), default=1))
    platforms = {v["platform"] for v in variants}
    return {
        "run": run, "rd": rd, "root": root, "topic": topic, "flags": flags, "cfg": cfg, "state": state, "matrix": mx,
        "variants": variants, "skipped": skipped, "hidden": hidden, "blind": blind,
        "versions": {"rubric": rubric_version, "rubric_sha": rubric_sha, "profile": profile_version, "lexicon": lexicon_version},
        "health": health, "small_corpus": small_corpus, "lineup_advisory": lineup_advisory,
        "self_n": self_n, "self_min": self_min, "voice_weak": (self_n is not None and self_n < self_min),
        "matrix_rung": rung, "matrix_seed": mx.get("seed"), "rounds": rounds, "calls": log["calls"], "wall_s": log["wall_s"],
        "brief": parse_brief(rd), "moves": moves_index(root), "ops": readme_ops_notes(root, platforms),
        "nags": _status_nags(root),
    }


def _topic_from_brief(rd: Path) -> str | None:
    p = rd / "brief.md"
    if not p.exists():
        return None
    for ln in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#\s*(?:brief\s*[:·-]\s*)?(.+)$", ln.strip(), flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.match(r"^topic\s*:\s*(.+)$", ln.strip(), flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _status_nags(root: Path) -> list[str]:
    try:
        doc = status_mod.collect(root)
    except Exception:  # noqa: BLE001 - reminders are best effort
        return []
    return [str(n) for n in (doc.get("nags") or [])]


# --------------------------------------------------------------------------- blind set and letters

def build_blind(run: str, variants: list[dict]) -> dict:
    """The blind-rating set (contracts section 18): the finalist, an alternate and a did-not-pass candidate when
    available (same platform when possible), shuffled by a seed derived from the run id, verdict-free."""
    finalists = [v for v in variants if v["section"] == "finalists"]
    primary = finalists[0] if finalists else (variants[0] if variants else None)
    items: list[dict] = []
    if primary is not None:
        items.append(primary)
        plat = primary["platform"]

        def pick(section: str) -> dict | None:
            pool = [v for v in variants if v["section"] == section and v is not primary]
            same = [v for v in pool if v["platform"] == plat]
            return (same or pool or [None])[0]

        for sec in ("alternates", "did_not_pass"):
            got = pick(sec)
            if got is not None and got not in items:
                items.append(got)
        if len(items) < 2:
            for v in finalists + [x for x in variants if x["section"] == "needs_your_call"]:
                if v not in items:
                    items.append(v)
                    break
    items = items[:3]
    rng = random.Random(common.stable_seed(run))
    rng.shuffle(items)
    return {"schema": BLIND_SCHEMA, "run": run, "seed": common.stable_seed(run),
            "items": [{"key": LETTERS[i], "letter": LETTERS[i], "cid": v["cid"], "platform": v["platform"],
                       "text": v["text"], "text_path": v["text_path"]} for i, v in enumerate(items)]}


def blind_public(blind: dict) -> dict:
    """What `final/blind.json` may hold: key, platform and text (contracts §18). A cid names the round it came
    from and a round-2 cid is by construction a rewrite of something that failed, so cid and text_path would hand
    the verdict to the session that is told the file is verdict-free."""
    return {"schema": blind.get("schema", BLIND_SCHEMA), "run": blind.get("run"), "seed": blind.get("seed"),
            "items": [{"key": it["key"], "platform": it["platform"], "text": it["text"]}
                      for it in (blind.get("items") or [])]}


def blind_key_doc(blind: dict) -> dict:
    """The key -> cid / text_path mapping. `final/blind.key.json` follows the same `*.key.json` convention
    as `lineup_<cid>.key.json`, denied by name in `.claude/settings.json`, so no orchestrator or agent
    opens it. `rate_record.py` reads it."""
    return {"schema": BLIND_KEY_SCHEMA, "run": blind.get("run"),
            "items": [{"key": it["key"], "cid": it["cid"], "platform": it["platform"], "text_path": it.get("text_path")}
                      for it in (blind.get("items") or [])]}


def assign_letters(variants: list[dict], blind: dict) -> dict[str, str]:
    """Blind letters first (so the terminal and /rate blind agree), then the next free letters in display order."""
    letters: dict[str, str] = {it["cid"]: it["key"] for it in blind.get("items") or []}
    used = set(letters.values())
    nxt = 0
    for v in variants:
        if v["cid"] in letters:
            continue
        while LETTERS[nxt] in used:
            nxt += 1
        letters[v["cid"]] = LETTERS[nxt]
        used.add(LETTERS[nxt])
    return letters


# --------------------------------------------------------------------------- renderers: pieces

def header_line(rep: dict) -> str:
    vs = rep["versions"]
    bits = [rep["topic"], rep["run"], f"rubric {vs.get('rubric') or '?'}",
            f"profile p{vs['profile']}" if vs.get("profile") is not None else "profile none",
            f"lexicon v{vs['lexicon']}" if vs.get("lexicon") is not None else "lexicon none"]
    h = rep["health"] or {}
    hstate = str(h.get("state") or "unknown")
    if hstate == "stale":
        reason = h.get("reason") or ""
        m = re.search(r"sha ([0-9a-f]{6,})", str(reason))
        bits.append(f"health stale for rubric sha {m.group(1)}" if m else f"health stale ({reason})" if reason else "health stale")
    else:
        bits.append(f"health {hstate}")
    if rep["small_corpus"]:
        bits.append("small-corpus mode: lineup uses train posts")
    if rep["lineup_advisory"]:
        bits.append("lineup advisory")
    if rep["voice_weak"]:
        bits.append(f"voice anchor: weak (self n={rep['self_n']})")
    if rep.get("matrix_rung"):
        bits.append(f"matrix fallback rung {rep['matrix_rung']}")
    if rep["flags"].get("quick"):
        bits.append("quick: no lineup, no pairwise")
    if rep["flags"].get("wide"):
        bits.append("wide: Tier 2 on two finalists per platform")
    if rep["flags"].get("no_media"):
        bits.append("no-media")
    bits.append(f"{rep['rounds']} round{'s' if rep['rounds'] != 1 else ''}")
    if rep.get("calls") is not None:
        bits.append(f"{rep['calls']} calls")
    wall = _fmt_wall(rep.get("wall_s"))
    if wall:
        bits.append(wall)
    return "# " + " · ".join(bits)


def size_phrase(v: dict, cfg: dict) -> str:
    if v["platform"] == "x":
        cap = int(((cfg.get("platforms") or {}).get("x") or {}).get("max_chars", 280))
        return f"{v['x_len'] if v['x_len'] is not None else v['chars']}/{cap} as X counts"
    return f"{_fmt_int(v['chars'])} chars · fold: \"{_short(v['fold_line'])}\""


def eval_header(v: dict, cfg: dict, hidden: bool, quick: bool = False) -> str:
    """`1,420 chars · fold: "..." · lineup 1/3 picked at conf 2 · pairwise win/tie` (size only when hidden)."""
    bits = [size_phrase(v, cfg)]
    if hidden:
        return " · ".join(bits)
    lu = lineup_summary(v)
    if v["tier2_tested"] or lu:
        if lu:
            phrase = f"lineup {lu['picks']}/{lu['n']}" + (f" picked at conf {lu['max_conf']}" if lu["picks"] else "")
            if lu["advisory"]:
                phrase += " (advisory)"
            bits.append(phrase)
        else:
            bits.append("lineup not run")
        bits.append(pairwise_phrase(v))
        para = v.get("paraphrase")
        if isinstance(para, dict) and para.get("paraphrase"):
            bits.append("paraphrase: same skeleton or joke")
    elif v.get("promoted"):
        bits.append("lineup skipped (quick)" if quick else "not lineup-tested")
    return " · ".join(bits)


def why_this_works(v: dict, moves: dict[str, dict]) -> str:
    """Two or three sentences from the candidate's own angle sheet and assignment; never judge text."""
    a = v["assignment"]
    angle = v.get("angle_sheet") or {}
    sents: list[str] = []
    pick = v.get("angle_pick")
    fam = a.get("angle_family") or v.get("angle_family")
    emo = angle.get("emotion")
    if pick:
        s = f'Angle: "{pick}"'
        extras = [x for x in (f"{fam} family" if fam else None, f"emotion {emo}" if emo else None) if x]
        sents.append(s + (f" ({', '.join(extras)})." if extras else "."))
    move = a.get("move")
    if move:
        mech = (moves.get(str(move).lower()) or {}).get("mechanism")
        s = f"It runs the move `{move}`" + (f" ({mech})" if mech else "")
        if a.get("device"):
            s += f" with the device `{a['device']}`"
        if a.get("archetype"):
            s += f" in the `{a['archetype']}` shape"
        hook_bits = [x for x in (f"a `{v['hook_type']}` hook" if v.get("hook_type") else None,
                                 f"a `{v['ending']}` ending" if v.get("ending") else None) if x]
        if hook_bits:
            s += ": " + " and ".join(hook_bits)
        sents.append(s + ".")
    elif a.get("device") or a.get("archetype"):
        sents.append("Persona-only slot: " + ", ".join(x for x in (f"device `{a['device']}`" if a.get("device") else None,
                                                                    f"`{a['archetype']}` shape" if a.get("archetype") else None) if x) + ".")
    if v.get("lens"):
        s = f"Lens: {v['lens']}"
    else:
        s = "Lens-free: the persona and self register alone"
    if v["exemplars_seen"]:
        s += f"; exemplars seen: {', '.join(v['exemplars_seen'])} (mechanisms borrowed, no wording)"
    sents.append(s + ".")
    return " ".join(sents[:3])


def needs_call_reason(v: dict) -> str:
    """`persona_fit 3 (jury 3/3/3), claim "..." needs confirmation (persona.can_claim#1)`, else the failing lines."""
    bits: list[str] = []
    pf = (v["merged"].get("tier1") or {}).get("persona_fit") or {}
    if pf.get("score") is not None and pf.get("result") == "fail":
        head = f"persona_fit {pf['score']}"
        j = pf.get("jury")
        if isinstance(j, dict) and j.get("votes"):
            head += f" (jury {'/'.join(str(x) for x in j['votes'])})"
        bits.append(head)
    for x in v["needs_confirmation"]:
        bits.append(f'claim "{x.get("claim")}" needs confirmation' + (f" ({x['source']})" if x.get("source") else ""))
    if not bits:
        bits = failing_lines(v) or [v["label"]]
    return ", ".join(bits)


def confirm_lines(v: dict) -> list[str]:
    return [f'Confirm before posting: "{x.get("claim")}"' + (f" ({x['source']})" if x.get("source") else "")
            for x in v["needs_confirmation"]]


def followup_line(rep: dict, v: dict) -> str:
    p = _plat_short(v)
    return f"Rate it: /rate {rep['run']} {p} N     Log it: /posted {rep['run']} {p} <url>"


def fenced(text: str) -> list[str]:
    return ["```text", text, "```"]


# --------------------------------------------------------------------------- renderers: files

def variant_file(rep: dict, v: dict) -> tuple[dict, str]:
    """(front matter, body) for final/<cid>.md."""
    hidden = rep["hidden"]
    meta: dict[str, Any] = {
        "schema": FINAL_SCHEMA, "cid": v["cid"], "platform": v["platform"], "chars": v["chars"],
        "x_len": v["x_len"], "fold_preview": v["fold_preview"] if v["platform"] == "linkedin" else None,
        "lens": v["lens"], "moves": v["moves"], "angle_family": v["angle_family"], "round": v["round"],
        "verdict": "withheld" if hidden else v["status"], "scores_path": v["scores_path"],
        "tier2_tested": v["tier2_tested"], "reply_1": v["reply_1"] if v["platform"] == "x" else None,
        "letter": v["letter"], "run": rep["run"], "writer": v["writer"],
    }
    body: list[str] = fenced(v["text"])
    body.append("")
    if v["platform"] == "x":
        body.append(f"reply_1: {v['reply_1'] if v['reply_1'] else '(none)'}")
        body.append("")
    body += ["## Why this works", why_this_works(v, rep["moves"]), ""]
    body += ["## Media"] + media_block_lines(v["media"], v["media_intent"], rep["flags"]) + [""]
    if v["needs_confirmation"]:
        body += ["## Confirm before posting"] + [f"- \"{x.get('claim')}\"" + (f" ({x['source']})" if x.get("source") else "")
                                                for x in v["needs_confirmation"]] + [""]
    return meta, "\n".join(body)


def clipboard_md(rep: dict) -> str:
    vs = [v for v in rep["variants"] if v["section"] in ("finalists", "alternates")]
    if not vs:  # nothing passed: the best attempt per platform, still texts only
        vs = [next((x for x in rep["variants"] if x["platform"] == p), None) for p in PLATFORM_ORDER]
        vs = [x for x in vs if x]
    blocks: list[str] = []
    for v in vs:
        lines = [CLIP_HEADERS.get(v["suffix"], v["platform"].upper()), v["text"]]
        if v["platform"] == "x" and v["reply_1"]:
            lines.append(f"reply_1: {v['reply_1']}")
        blocks.append("\n".join(lines))
    return "\n=====\n".join(blocks) + ("\n" if blocks else "")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out


def variant_report_section(rep: dict, v: dict, hidden_tables: bool) -> list[str]:
    """One variant's block for report.md. `hidden_tables` drops results, scores and failing evidence."""
    cfg = rep["cfg"]
    lines: list[str] = []
    if hidden_tables:
        lines.append(f"### {_plat_name(v)} · {v['letter']} ({eval_header(v, cfg, True)})")
    else:
        lines.append(f"### {_plat_name(v)} · {v['letter']} · {v['cid']} · {v['label']} ({eval_header(v, cfg, False, quick=bool(rep["flags"].get("quick")))})")
    lines.append("")
    lines += fenced(v["text"])
    lines.append("")
    if v["platform"] == "x" and v["reply_1"]:
        lines += [f"reply_1: {v['reply_1']}", ""]
    rows = tier0_rows(v["merged"]) + tier1_rows(v["merged"]) + ([] if hidden_tables else tier2_rows(v))
    if hidden_tables:
        lines.append("#### Checks and dimensions (results withheld until the blind rating)")
        lines += _table(["id", "class", "threshold", "evidence quote"],
                        [[r["id"], r["class"], r["threshold"], _quote_only(r["evidence"])] for r in rows])
    else:
        lines.append("#### Score table")
        lines += _table(["id", "class", "value / score", "threshold", "result", "evidence"],
                        [[r["id"], r["class"], r["value"], r["threshold"], r["result"], r["evidence"]] for r in rows])
        lu = lineup_summary(v)
        if lu:
            lines += ["", f"#### Lineup ({lu['result']}{', advisory' if lu['advisory'] else ''}; rule: {_one_line(lu['rule'], 140)})"]
            lines += _table(["lens", "picked the candidate", "confidence", "tell", "quote"],
                            [[str(p.get("lens")), "yes" if p.get("picked_candidate") else "no", str(p.get("confidence")),
                              _one_line(p.get("tell"), 80), _one_line(p.get("quote"), 80)] for p in lu["all"]])
        pw = v.get("pairwise_ref")
        if isinstance(pw, dict):
            per = pw.get("per_lens") if isinstance(pw.get("per_lens"), dict) else {}
            lines += ["", f"#### Pairwise vs {pw.get('reference_id', 'reference')} (advisory): {pairwise_phrase(v)}"]
            lines += _table(["lens", "better (12 / 21)", "voice (12 / 21)"],
                            [[lens, f"{x.get('better')} ({' / '.join(str(o) for o in (x.get('orders') or {}).values())})",
                              f"{x.get('voice')} ({' / '.join(str(o) for o in (x.get('voice_orders') or {}).values())})"]
                             for lens, x in per.items() if isinstance(x, dict)])
        elif v["tier2_tested"]:
            lines += ["", f"Pairwise: {pairwise_phrase(v)}."]
    ctable = claims_table(v)
    if ctable and hidden_tables:
        lines += ["", "#### Claims"]
        lines += _table(["text", "source", "needs_confirmation"],
                        [[_one_line(r["text"], 100), _one_line(r["source"], 40), "yes" if r["needs_confirmation"] else "no"]
                         for r in ctable])
    elif ctable:
        lines += ["", "#### Claims"]
        lines += _table(["text", "status", "source", "needs_confirmation"],
                        [[_one_line(r["text"], 100), r["status"], _one_line(r["source"], 40),
                          "yes" if r["needs_confirmation"] else "no"] for r in ctable])
    lines += ["", "#### Media"]
    lines += media_block_lines(v["media"], v["media_intent"], rep["flags"])
    if not hidden_tables:
        chk = v["media"].get("check")
        if isinstance(chk, dict):
            lines.append(f"media_check: {'pass' if chk.get('ok') else 'fail'}" + (f" - {'; '.join(str(f) for f in chk.get('fails') or [])}" if chk.get("fails") else "")
                         + (f" (warnings: {'; '.join(str(w) for w in chk.get('warnings') or [])})" if chk.get("warnings") else ""))
        jrows = media_judge_rows(v["media"].get("judge"))
        if jrows:
            lines.append(f"media judge: {run_next._media_judge_verdict(v['media']['judge'])}")
            lines += _table(["sub-result", "result", "evidence"], [[k, r, e] for k, r, e in jrows])
    # a rounds block exists only for a candidate that was rewritten, i.e. only for one that failed a round: its
    # presence (and the round-2 cid inside it) names the loser, so the whole block is suppressed while hidden
    if not hidden_tables and (len(v["rounds"]) > 1 or (v["rounds"] and v["rounds"][0]["packet"])):
        lines += ["", "#### Rounds and what changed"]
        for row in v["rounds"]:
            head = f"- round {row['round']} · {row['cid']} · {LABELS.get(str(row['verdict']), row['verdict'])}"
            fails = row["hard_fails"] + row["soft_fails"] + row["flags"]
            if fails:
                head += f" · failing: {', '.join(fails)}"
            if row["stop"]:
                head += f" · stop: {row['stop']}"
            lines.append(head)
            for it in row["packet"]:
                ev = it["evidence"][0] if it["evidence"] else None
                piece = f"  - packet: {it['id']} ({it.get('class')}" + (f", {it['score']}/{_fmt_num(it['threshold'])}" if it.get("score") is not None else "") + ")"
                if ev:
                    piece += f" {_ev_span(ev)}"
                if it.get("fix"):
                    piece += f" → fix: {_one_line(it['fix'], 120)}"
                if it.get("cleared") is not None:
                    piece += " → cleared in the next round" if it["cleared"] else " → still failing in the next round"
                lines.append(piece)
    return lines


def _quote_only(evidence: str) -> str:
    m = re.match(r'^"(.*?)"(?:\s-\s.*)?$', evidence or "")
    return f'"{m.group(1)}"' if m else ""


def report_body(rep: dict) -> list[str]:
    """The full (verdict-bearing) report body: sections in order, each variant with its tables."""
    lines: list[str] = []
    for sec in SECTIONS:
        vs = [v for v in rep["variants"] if v["section"] == sec]
        if not vs:
            continue
        lines += [f"## {SECTION_TITLES[sec]}", ""]
        for v in vs:
            lines += variant_report_section(rep, v, hidden_tables=False)
            if sec == "did_not_pass":
                lines += ["", "Failing dimensions and evidence:"] + [f"- {ln}" for ln in failing_lines(v)]
            if sec == "needs_your_call":
                lines += ["", f"Your call: {needs_call_reason(v)}"]
            lines.append("")
    return lines


def ops_lines(rep: dict) -> list[str]:
    lines = ["## Ops reminders", ""]
    if rep["nags"]:
        lines += [f"- {n}" for n in rep["nags"]]
    for plat, bullets in (rep["ops"] or {}).items():
        lines += ["", f"**{plat}**"] + [f"- {b}" for b in bullets]
    if not rep["nags"] and not rep["ops"]:
        lines.append("- none")
    return lines


def report_md(rep: dict) -> str:
    run = rep["run"]
    lines: list[str] = [header_line(rep), ""]
    if not rep["hidden"]:
        lines += report_body(rep)
        lines += ops_lines(rep)
        return "\n".join(lines).rstrip("\n") + "\n"
    lines += [HIDDEN_NOTE.format(run=run), f"Rate them blind first: /rate blind {run}", "", "## Delivered", ""]
    for v in hidden_order(rep["variants"]):
        lines += variant_report_section(rep, v, hidden_tables=True)
        for ln in confirm_lines(v):
            lines.append(ln)
        lines.append("")
    lines += ops_lines(rep)
    lines += ["", "<details>", "<summary>After blind rating (verdicts, scores and failing evidence)</summary>", ""]
    lines += report_body(rep)
    lines += ["</details>", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def lineage_json(rep: dict) -> dict:
    root = rep["root"]
    final = rep["rd"] / "final"
    return {
        "schema": LINEAGE_SCHEMA, "run": rep["run"], "topic": rep["topic"], "flags": rep["flags"],
        "generated_at": common.now_iso(), "versions": rep["versions"],
        "health": (rep["health"] or {}).get("state"), "small_corpus_mode": rep["small_corpus"],
        "lineup_advisory": rep["lineup_advisory"], "voice_anchor_weak": rep["voice_weak"], "self_samples": rep["self_n"],
        "brief": rep["brief"], "matrix_rung": rep["matrix_rung"], "matrix_seed": rep["matrix_seed"],
        "rounds": rep["rounds"], "calls": rep["calls"], "wall_s": rep["wall_s"],
        "verdicts_hidden": rep["hidden"],
        "variants": [{
            "cid": v["cid"], "platform": v["platform"], "letter": v["letter"], "writer": v["writer"], "section": v["section"],
            "verdict": v["status"], "label": v["label"], "tier2_tested": v["tier2_tested"],
            "assignment": v["assignment"], "lens": v["lens"], "moves": v["moves"], "angle_family": v["angle_family"],
            "angle_sheet": {k: (v["angle_sheet"] or {}).get(k) for k in ("pick", "runner_up", "emotion", "hook_family")},
            "hook_type": v["hook_type"], "ending": v["ending"],
            "exemplars_seen": v["exemplars_seen"], "lessons_used": v["lessons_used"],
            "rounds": [{k: r[k] for k in ("round", "cid", "verdict", "hard_fails", "soft_fails", "flags", "stop", "scores_path")}
                       for r in v["rounds"]],
            "final_sha": v["final_sha"], "final_path": _rel(root, final / f"{v['cid']}.md"),
            "candidate_path": v["candidate_path"], "scores_path": v["scores_path"],
            "media_path": v["media"].get("brief_path"), "media_decision": (v["media"].get("brief") or {}).get("decision")
            if v["media"].get("brief") else (v["media_intent"] or {}).get("decision"),
            "waived": v["waived"], "needs_confirmation": v["needs_confirmation"], "reply_1": v["reply_1"],
            "stop": v["stop"],
        } for v in rep["variants"]],
        "not_delivered": rep["skipped"],
    }


# --------------------------------------------------------------------------- renderer: terminal

def terminal(rep: dict) -> str:
    run, cfg, hidden = rep["run"], rep["cfg"], rep["hidden"]
    out: list[str] = [header_line(rep), ""]
    delivered = [v for v in rep["variants"] if v["section"] == "finalists"]
    if hidden:
        # letter order, one heading level, no section split: which section a variant sits in *is* the verdict, so
        # nothing derived from it may reach the page before the blind rating (contracts §18)
        for v in hidden_order(rep["variants"]):
            out.append(f"## {_plat_name(v)} · {v['letter']} ({eval_header(v, cfg, True)})")
            out += fenced(v["text"])
            if v["platform"] == "x" and v["reply_1"]:
                out.append(f"reply_1: {v['reply_1']}")
            out += media_block_lines(v["media"], v["media_intent"], rep["flags"], terminal=True)
            out += confirm_lines(v)
            out.append("")
        out.append(f"Files: drafts/{run}/final/  report.md  clipboard.md  lineage.json  blind.json")
        out.append(HIDDEN_NOTE.format(run=run))
        out.append(CLOSING_BLIND.format(run=run))
        return "\n".join(out) + "\n"
    for v in delivered:
        out.append(f"## {_plat_name(v)} · {v['label']} ({eval_header(v, cfg, False, quick=bool(rep["flags"].get("quick")))})")
        out += fenced(v["text"])
        if v["platform"] == "x" and v["reply_1"]:
            out.append(f"reply_1: {v['reply_1']}")
        out += media_block_lines(v["media"], v["media_intent"], rep["flags"], terminal=True)
        out += confirm_lines(v)
        out.append(followup_line(rep, v))
        out.append("")
    for sec in ("alternates", "needs_your_call", "did_not_pass"):
        vs = [v for v in rep["variants"] if v["section"] == sec]
        if not vs:
            continue
        out.append(f"## {SECTION_TITLES[sec]}")
        for v in vs:
            if sec == "alternates":
                tag = " (short deadpan)" if (v["assignment"] or {}).get("short_deadpan") else ""
                out.append(f"### {_plat_name(v)} {v['letter']}{tag} · {v['label']} ({eval_header(v, cfg, False, quick=bool(rep["flags"].get("quick")))})")
                out += fenced(v["text"])
                if v["platform"] == "x" and v["reply_1"]:
                    out.append(f"reply_1: {v['reply_1']}")
                out += confirm_lines(v)
                out.append(followup_line(rep, v))
            elif sec == "needs_your_call":
                out.append(f"### {_plat_name(v)} {v['letter']} · {v['cid']}: {needs_call_reason(v)}")
                out += fenced(v["text"])
                if v["platform"] == "x" and v["reply_1"]:
                    out.append(f"reply_1: {v['reply_1']}")
                out.append(followup_line(rep, v))
            else:
                fl = failing_lines(v) or [v["label"]]
                out.append(f"### {_plat_name(v)} {v['letter']} · {v['cid']}: {fl[0]}")
                for extra in fl[1:]:
                    out.append(f"  {extra}")
                out += fenced(v["text"])
        out.append("")
    out.append(f"Files: drafts/{run}/final/  report.md  clipboard.md  lineage.json  blind.json")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- assemble

def copy_to_clipboard(text: str) -> bool:
    """Pipe `text` to pbcopy; False (silently) when pbcopy is missing or fails."""
    exe = shutil.which("pbcopy")
    if not exe:
        return False
    try:
        subprocess.run([exe], input=text.encode("utf-8"), check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def assemble(run: str, root: Path | str | None = None, copy: bool = False, show_verdicts: bool | None = None,
             write: bool = True) -> dict:
    """Collect, render and (unless write=False) write final/. Returns the JSON document the CLI prints."""
    with common.use_root(root) as active_root:
        rep = collect(active_root, run, show_verdicts)
        final = rep["rd"] / "final"
        files: dict[str, str] = {}
        if write:
            final.mkdir(parents=True, exist_ok=True)
            for v in rep["variants"]:
                meta, body = variant_file(rep, v)
                p = final / f"{v['cid']}.md"
                common.write_front_matter_file(p, meta, body)
                files[v["cid"]] = _rel(active_root, p)
            (final / "clipboard.md").write_text(clipboard_md(rep), encoding="utf-8")
            (final / "report.md").write_text(report_md(rep), encoding="utf-8")
            common.write_json(final / "lineage.json", lineage_json(rep))
            common.write_json(final / "blind.json", blind_public(rep["blind"]))
            common.write_json(final / "blind.key.json", blind_key_doc(rep["blind"]))
            for name in ("clipboard.md", "report.md", "lineage.json", "blind.json"):
                files[name] = _rel(active_root, final / name)
            for marker in STALE_MARKERS:
                if (final / marker).exists():
                    (final / marker).unlink()
        term = terminal(rep)
        copied = False
        if copy:
            top = next((v for v in rep["variants"] if v["platform"] == "linkedin" and v["section"] in ("finalists", "alternates")), None)
            if top is not None:
                copied = copy_to_clipboard(top["text"])
        variants_out: list[dict] = []
        for v in rep["variants"]:
            row: dict[str, Any] = {"cid": v["cid"], "platform": v["platform"], "letter": v["letter"], "chars": v["chars"],
                                   "x_len": v["x_len"], "tier2_tested": v["tier2_tested"], "final_path": files.get(v["cid"]),
                                   "scores_path": v["scores_path"], "needs_confirmation": v["needs_confirmation"]}
            if not rep["hidden"]:
                fl = failing_lines(v)
                t1 = v["merged"].get("tier1") or {}
                first_ev = next((_ev_span(r["evidence"][0]) for r in t1.values()
                                 if isinstance(r, dict) and r.get("evidence")), "")
                row.update({"section": v["section"], "verdict": v["status"], "label": v["label"],
                            "evidence_line": fl[0] if fl else first_ev})
            variants_out.append(row)
        return {
            "ok": True, "run": rep["run"], "final_dir": _rel(active_root, final), "files": files, "written": write,
            "verdicts_hidden": rep["hidden"], "header": header_line(rep)[2:],
            "blind": {"seed": rep["blind"]["seed"], "items": [{k: it[k] for k in ("key", "cid", "platform")} for it in rep["blind"]["items"]]},
            "variants": variants_out, "not_delivered": rep["skipped"], "copied": copied, "terminal": term,
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write drafts/<run>/final/ from a delivered run and print the terminal layout.")
    ap.add_argument("run", help="run name (YYYY-MM-DD_slug) or drafts/<run> path")
    ap.add_argument("--copy", action="store_true", help="pipe the top LinkedIn text to pbcopy (skipped when pbcopy is missing)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--show-verdicts", action="store_true", help="render verdict labels even without a blind rating row")
    g.add_argument("--hide-verdicts", action="store_true", help="force hidden-verdict mode (the default until /rate blind)")
    ap.add_argument("--no-write", action="store_true", help="render only; write nothing under final/")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="print the JSON document instead of the terminal layout")
    args = ap.parse_args(argv)
    show: bool | None = True if args.show_verdicts else (False if args.hide_verdicts else None)
    try:
        doc = assemble(args.run, root=args.root, copy=args.copy, show_verdicts=show, write=not args.no_write)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        common.error(str(e))
        return 0
    if args.json:
        common.emit(doc)
    else:
        sys.stdout.write(doc["terminal"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
