#!/usr/bin/env python3
"""Deterministic media brief gate (contracts section 11).

Validates `drafts/<run>/media/<cid>.brief.yaml` and the rendered tool prompts beside it
(`<cid>.prompts/{gpt_image,nano_banana,veo,runway}.md`). What it enforces: required fields once media is
chosen; an M1-M7 citation in `decision_reason`; aspect ratio per platform; on-image text budgets per tool
(every line <= 8 words, GPT Image total words, Nano Banana element count) and those lines quoted verbatim in
every rendered image prompt; positive phrasing (no negation words) in Veo, Runway and Nano Banana prompts;
Veo and Runway caps; alt text caps per platform; real-person names; brand names other than the user's own;
and M6, which bars a fake screenshot of a real product and makes a parody UI name a fictional one.

Output: {"ok": bool, "fails": [str], "warnings": [str], ...}. Each fail string starts with its check id.

Usage:
  uv run tools/media_check.py <brief.yaml> [--prompts DIR] [--platform linkedin|x] [--root DIR]

Importable: `media_check.check(brief: dict, prompts: dict[str, str], cfg: dict, platform: str) -> dict`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import yaml  # noqa: E402

DECISIONS = ("none", "image", "video", "real_capture_direction")
IMAGE_FAMILIES = ("gpt_image", "nano_banana")
VIDEO_FAMILIES = ("veo", "runway")
POSITIVE_ONLY_FAMILIES = ("veo", "runway", "nano_banana")
LINE_MAX_WORDS = 8
RULE_RE = re.compile(r"\bM[1-7]\b")
ON_SCREEN_TEXT_WORDS = ("caption", "text on screen", "on-screen text", "onscreen text", "title card", "subtitle")
M6_MESSAGE = ("M6: real product output is never faked; genre fake_screenshot is rejected. Use "
              "decision/genre real_capture_direction with exact capture instructions for a real product, or "
              "genre parody_ui with a fictional product name and no real logos.")

# Not exhaustive: real people who turn up in tech and business posts, matched case-insensitively.
REAL_PEOPLE = [
    "Elon Musk", "Sam Altman", "Mark Zuckerberg", "Jeff Bezos", "Tim Cook", "Satya Nadella", "Sundar Pichai",
    "Bill Gates", "Steve Jobs", "Jensen Huang", "Dario Amodei", "Demis Hassabis", "Larry Page", "Sergey Brin",
    "Peter Thiel", "Marc Andreessen", "Paul Graham", "Warren Buffett", "Taylor Swift", "Donald Trump",
    "Joe Biden", "Barack Obama", "Kamala Harris", "Oprah Winfrey", "Kanye West", "Cristiano Ronaldo",
    "Lionel Messi", "LeBron James", "Greg Brockman", "Ilya Sutskever", "Yann LeCun", "Andrej Karpathy",
    "Lex Fridman", "Joe Rogan", "Mr Beast", "MrBeast", "Beyonce", "Beyoncé", "Rihanna", "Zuckerberg", "Musk",
    "Bezos", "Altman", "Zuck",
]
# Brands matched case-insensitively (unambiguous names).
BRANDS_CI = [
    "OpenAI", "ChatGPT", "Anthropic", "Microsoft", "Salesforce", "Facebook", "Instagram", "TikTok", "Netflix",
    "Tesla", "Coca-Cola", "Starbucks", "Airbnb", "Spotify", "Shopify", "GitHub", "Jira", "Vercel", "Supabase",
    "Datadog", "HubSpot", "Zapier", "Dropbox", "YouTube", "Reddit", "WhatsApp", "Gmail", "Perplexity",
    "Midjourney", "Nvidia", "Samsung", "McDonald's", "Walmart", "Snapchat", "Pinterest", "Photoshop",
    "Mailchimp", "Intercom", "Asana", "Trello", "Calendly", "Grammarly", "iPhone", "MacBook", "Android",
    "Claude Code", "Nike", "Amazon", "Google", "Apple Watch", "Copilot",
]
# Brands that are also ordinary words: matched only with their exact capitalization.
BRANDS_CS = ["Cursor", "Claude", "Gemini", "Slack", "Notion", "Zoom", "Windows", "Excel", "Stripe", "Uber",
             "Apple", "Chrome", "Discord", "Loom", "Canva", "Oracle", "Figma", "Meta", "Twitter", "Intel", "Sony",
             "Adobe", "Linear", "Monday.com", "Lovable", "Replit"]
NAME_STOPWORDS = set("""
The A An This That These Those Use Scene Subject Details Text Constraints If Create Render Output Keep Static
Medium Close Wide Slow Soft Late Ambient Camera Speaker Post Platform Root Cause Incident Report Date Severity
Nano Banana GPT Image Veo Runway Gen LinkedIn Twitter Google Gemini Flow Claude Code Cursor Silicon Valley New
York San Francisco London Berlin Paris Tokyo Agent Photorealistic Then When While After Before Also Using With
For And But Or Not No Yes Each Every One Two Three Four Five First Second Third Left Right Top Bottom Center
Centre Header Footer Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May
June July August September October November December AI API UI UX CEO CTO VP HR IT OK Slack Notion Zoom Excel
Chrome Windows Apple Amazon Microsoft OpenAI Anthropic ChatGPT Series Seed Board Fridge Kitchen Product Hunt
Reported By Will Happen Again Dear Team Update Notes Version Status Total Balance Cash Account Bank Order
Confirmed Pending Failed Success Error Warning Sent Received Draft Reply Forward Delete Save Cancel Submit Login
Sign Up Log In Out Home Settings Profile Search Menu Help About Contact Terms Privacy Pro Lite Plus Max Mini Enterprise
""".split())


# --------------------------------------------------------------------------- helpers

def tool_family(name: Any) -> str:
    """Map a tool id or prompt file stem to gpt_image | nano_banana | veo | runway | <other>."""
    n = str(name or "").strip().lower()
    if not n:
        return ""
    if "gpt" in n or "dall" in n or "openai" in n:
        return "gpt_image"
    if "nano" in n or "banana" in n or "gemini" in n or "imagen" in n:
        return "nano_banana"
    if "veo" in n:
        return "veo"
    if "runway" in n:
        return "runway"
    return n


def _words(s: str) -> int:
    return len(common.words(s))


def _fold(s: str) -> str:
    return common.fold_punct(s or "")


def _str(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _is_nothing(delete_test: str) -> bool:
    t = delete_test.strip().lower().rstrip(".")
    return t in ("", "nothing", "none", "n/a", "na", "no loss", "-")


def _walk_strings(obj: Any, path: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, str):
        if obj.strip():
            out.append((path or "value", obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_walk_strings(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out.extend(_walk_strings(v, f"{path}[{i}]"))
    return out


CONTENT_FIELDS = ("visual_concept", "subject", "setting", "composition", "style", "on_image_text", "must_show",
                  "keep_out_as_positive", "alt_text", "humor_or_hook_device", "video", "factual_claims_in_visual",
                  "fictional_product", "genre_note")


def content_texts(brief: dict) -> list[tuple[str, str]]:
    """(field path, text) pairs for the fields describing what gets rendered, not tool or capture blocks."""
    out: list[tuple[str, str]] = []
    for f in CONTENT_FIELDS:
        if f in brief:
            out.extend(_walk_strings(brief[f], f))
    return out


def _own_allowlist(cfg: dict, own: dict | None) -> tuple[list[str], list[str]]:
    persona = cfg.get("persona") if isinstance(cfg.get("persona"), dict) else {}
    names = [str(x) for x in ([persona.get("name")] if persona.get("name") else []) + list(persona.get("aliases") or [])]
    brands = [str(x) for x in (persona.get("brands") or persona.get("brand_allowlist") or [])]
    if isinstance(persona.get("brand"), str):
        brands.append(persona["brand"])
    if own:
        names += [str(x) for x in own.get("names") or []]
        brands += [str(x) for x in own.get("brands") or []]
    return [n for n in names if n.strip()], [b for b in brands if b.strip()]


def find_people(text: str, allow_names: list[str]) -> tuple[list[str], list[str]]:
    """(known real names found, capitalized First Last pairs worth a look)."""
    folded = _fold(text)
    allow = {a.lower() for a in allow_names}
    known: list[str] = []
    for name in REAL_PEOPLE:
        if name.lower() in allow:
            continue
        if re.search(r"(?<![\w'])" + re.escape(name) + r"(?![\w'])", folded, flags=re.IGNORECASE):
            known.append(name)
    pairs: list[str] = []
    for m in re.finditer(r"\b([A-Z][a-z]{1,}(?:-[A-Z][a-z]+)?)\s+([A-Z][a-z]{1,}(?:-[A-Z][a-z]+)?)\b", folded):
        first, second = m.group(1), m.group(2)
        if first in NAME_STOPWORDS or second in NAME_STOPWORDS:
            continue
        pair = f"{first} {second}"
        if pair.lower() in allow or any(pair.lower() == k.lower() for k in known):
            continue
        if pair not in pairs:
            pairs.append(pair)
    return _dedupe_substrings(known), pairs


def find_brands(text: str, allow_brands: list[str]) -> list[str]:
    folded = _fold(text)
    allow = {b.lower() for b in allow_brands}
    found: list[str] = []
    for b in BRANDS_CI:
        if b.lower() in allow:
            continue
        if re.search(r"(?<![\w-])" + re.escape(b) + r"(?![\w-])", folded, flags=re.IGNORECASE):
            found.append(b)
    for b in BRANDS_CS:
        if b.lower() in allow:
            continue
        if re.search(r"(?<![\w-])" + re.escape(b) + r"(?![\w-])", folded):
            found.append(b)
    return _dedupe_substrings(found)


def _dedupe_substrings(items: list[str]) -> list[str]:
    """Drop duplicates and any hit that is contained in a longer hit ("Altman" inside "Sam Altman")."""
    uniq: list[str] = []
    for it in items:
        if it.lower() not in {u.lower() for u in uniq}:
            uniq.append(it)
    return [a for a in uniq if not any(a is not b and a.lower() != b.lower() and a.lower() in b.lower() for b in uniq)]


def negation_hits(text: str, negation_words: list[str]) -> list[str]:
    folded = _fold(text)
    hits: list[str] = []
    for w in negation_words:
        raw = str(w)
        if raw.endswith(" "):
            pat = r"(?<![A-Za-z'])" + re.escape(raw.strip()) + r"(?=\s)"
        else:
            pat = r"(?<![A-Za-z'])" + re.escape(raw.strip()) + r"(?![A-Za-z])"
        if re.search(pat, folded, flags=re.IGNORECASE):
            hits.append(raw.strip())
    return hits


def on_screen_text_hits(text: str) -> list[str]:
    folded = _fold(text).lower()
    return [w for w in ON_SCREEN_TEXT_WORDS if re.search(r"(?<![A-Za-z])" + re.escape(w) + r"s?(?![A-Za-z])", folded)]


def line_in_quotes(prompt: str, line: str) -> bool:
    p = common.collapse_ws(_fold(prompt))
    q = common.collapse_ws(_fold(line))
    return f'"{q}"' in p or f"'{q}'" in p


def product_name_candidates(brief: dict) -> list[str]:
    """Names a parody UI could carry: `fictional_product`, quoted spans, CamelCase tokens, or capitalized
    words introduced by called/named/titled/branded."""
    names: list[str] = []
    fp = _str(brief.get("fictional_product"))
    if fp:
        names.append(fp)
    texts = [t for f, t in content_texts(brief) if f.split(".")[0] in ("visual_concept", "subject", "on_image_text")]
    for t in texts:
        folded = _fold(t)
        names += [m.strip() for m in re.findall(r'"([^"]{2,40})"', folded)]
        names += re.findall(r"\b[A-Z][a-z]+[A-Z][A-Za-z]+\b", folded)
        names += re.findall(r"\b(?:called|named|titled|branded)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?)", folded)
    seen: set[str] = set()
    return [n for n in names if n and not (n in seen or seen.add(n))]


# --------------------------------------------------------------------------- the check

def check(brief: dict, prompts: dict[str, str], cfg: dict, platform: str, own: dict | None = None) -> dict:
    """Validate a media brief and its rendered prompts. Pure: no files are read."""
    fails: list[str] = []
    warns: list[str] = []
    if not isinstance(brief, dict) or not brief:
        return {"ok": False, "fails": ["schema: brief is empty or not a mapping"], "warnings": [], "decision": None}
    platform = str(platform or brief.get("platform") or "").strip().lower()
    pcfg = (cfg.get("platforms") or {}).get(platform)
    if not isinstance(pcfg, dict):
        return {"ok": False, "fails": [f"schema: unknown platform {platform!r} (expected linkedin or x)"],
                "warnings": [], "decision": brief.get("decision")}
    mcfg = cfg.get("media") or {}
    decision = _str(brief.get("decision")).lower()
    if decision not in DECISIONS:
        fails.append(f"schema: decision must be one of {', '.join(DECISIONS)} (got {brief.get('decision')!r})")
        return _result(fails, warns, decision, None, platform)
    fam_prompts: dict[str, tuple[str, str]] = {}
    for key, text in (prompts or {}).items():
        fam = tool_family(key)
        if fam in fam_prompts:
            warns.append(f"prompts: two prompt files map to {fam} ({fam_prompts[fam][0]} and {key}); using {key}")
        fam_prompts[fam] = (str(key), text or "")

    if decision == "none":
        if fam_prompts:
            warns.append("prompts: decision is none but rendered prompts are present; they will be ignored")
        return _result(fails, warns, decision, None, platform)

    # ---- required fields
    for field in ("visual_concept", "aspect_ratio", "delete_test", "decision_reason"):
        if not _str(brief.get(field)):
            fails.append(f"required: {field} is missing or empty (decision={decision})")
    tool = brief.get("tool") if isinstance(brief.get("tool"), dict) else {}
    primary = _str(tool.get("primary")) if tool else ""
    fallback = _str(tool.get("fallback")) if tool else ""
    primary_fam = tool_family(primary)
    fallback_fam = tool_family(fallback)
    if not primary:
        if decision == "real_capture_direction":
            warns.append("required: tool.primary absent (acceptable for real_capture_direction, nothing is generated)")
        else:
            fails.append(f"required: tool.primary is missing (decision={decision})")
    reason = _str(brief.get("decision_reason"))
    if reason and not RULE_RE.search(reason):
        fails.append("required: decision_reason must cite one of the rules M1-M7")
    delete_test = _str(brief.get("delete_test"))
    if delete_test and _is_nothing(delete_test):
        fails.append(f"required: delete_test says the post loses nothing ({delete_test!r}); decision must then be none")

    # ---- tool / decision agreement
    if primary_fam and decision == "image" and primary_fam in VIDEO_FAMILIES:
        fails.append(f"tool: decision image but tool.primary {primary} is a video tool")
    if primary_fam and decision == "video" and primary_fam in IMAGE_FAMILIES:
        fails.append(f"tool: decision video but tool.primary {primary} is an image tool")

    # ---- real capture block
    if decision == "real_capture_direction":
        rcd = brief.get("real_capture_direction")
        if not isinstance(rcd, dict) or not rcd:
            fails.append("required: real_capture_direction block (what_to_open, what_to_show, crop, redact) is missing")
        else:
            for k in ("what_to_open", "what_to_show", "crop", "redact"):
                if not _str(rcd.get(k)):
                    warns.append(f"real_capture_direction.{k} is empty")

    # ---- aspect ratio
    aspect = _str(brief.get("aspect_ratio")).replace("x", ":").replace(" ", "")
    image_aspects = [str(a) for a in pcfg.get("image_aspects") or []]
    video_aspects = [str(a) for a in pcfg.get("video_aspects") or []]
    if aspect:
        if decision == "image" and aspect not in image_aspects:
            fails.append(f"aspect: {aspect} is not a {platform} image aspect ({', '.join(image_aspects)})")
        elif decision == "video" and aspect not in video_aspects:
            fails.append(f"aspect: {aspect} is not a {platform} video aspect ({', '.join(video_aspects)})")
        elif decision == "real_capture_direction" and aspect not in image_aspects + video_aspects:
            warns.append(f"aspect: {aspect} is outside the {platform} image aspects ({', '.join(image_aspects)}); "
                         "crop the capture accordingly")

    # ---- genre rules (M6)
    genre = _str(brief.get("genre")).lower()
    allow_names, allow_brands = _own_allowlist(cfg, own)
    content_blob = "\n".join(t for _, t in content_texts(brief))
    content_brands = find_brands(content_blob, allow_brands)
    if genre == "fake_screenshot":
        named = f" (names {', '.join(content_brands)})" if content_brands else ""
        fails.append(M6_MESSAGE + named)
    if genre == "parody_ui":
        if content_brands:
            fails.append(f"M6: parody_ui must be obviously fictional; real brand(s) named: {', '.join(content_brands)}")
        names = [n for n in product_name_candidates(brief) if not find_brands(n, allow_brands)]
        if not names:
            fails.append("parody_ui: the brief must name a fictional product (set `fictional_product` or put the "
                         "product name in quotes inside visual_concept/subject)")

    # ---- on-image text
    oit = brief.get("on_image_text")
    lines: list[str] = []
    if isinstance(oit, dict):
        raw = oit.get("lines")
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            lines = [str(x) for x in raw if str(x).strip()]
    elif isinstance(oit, list):
        lines = [str(x) for x in oit if str(x).strip()]
    for ln in lines:
        if _words(ln) > LINE_MAX_WORDS:
            fails.append(f"text_budget: on-image line exceeds {LINE_MAX_WORDS} words ({_words(ln)}): {ln!r}")
    total_words = sum(_words(ln) for ln in lines)
    gpt_max = int(((mcfg.get("gpt_image") or {}).get("on_image_text_max_words")) or 12)
    nb_max = int(((mcfg.get("nano_banana") or {}).get("on_image_text_max_elements")) or 5)
    budget_fams = {primary_fam} | set(fam_prompts)
    if lines:
        if "gpt_image" in budget_fams and total_words > gpt_max:
            fails.append(f"text_budget: GPT Image allows <= {gpt_max} on-image words in total, got {total_words}")
        elif fallback_fam == "gpt_image" and total_words > gpt_max:
            warns.append(f"text_budget: fallback GPT Image would exceed {gpt_max} on-image words ({total_words})")
        if "nano_banana" in budget_fams and len(lines) > nb_max:
            fails.append(f"text_budget: Nano Banana allows <= {nb_max} text elements, got {len(lines)}")
        elif fallback_fam == "nano_banana" and len(lines) > nb_max:
            warns.append(f"text_budget: fallback Nano Banana would exceed {nb_max} text elements ({len(lines)})")
        tier = _str(brief.get("resolution_tier")).upper()
        if tier and tier == "1K":
            warns.append("resolution: on-image text present but resolution_tier is 1K (2K minimum for crisp type)")
        for fam in IMAGE_FAMILIES:
            if fam in fam_prompts:
                name, ptxt = fam_prompts[fam]
                for ln in lines:
                    if not line_in_quotes(ptxt, ln):
                        fails.append(f"text_verbatim: on-image line {ln!r} does not appear verbatim in quotes in prompt {name}")
    elif decision == "image" and any(fam in fam_prompts for fam in IMAGE_FAMILIES):
        for fam in IMAGE_FAMILIES:
            if fam in fam_prompts and re.search(r'text \(exact|render the text exactly', fam_prompts[fam][1], flags=re.IGNORECASE):
                warns.append(f"text: prompt {fam_prompts[fam][0]} asks for exact text but the brief has no on_image_text")

    # ---- positive phrasing
    negation_words = [str(w) for w in (mcfg.get("negation_words") or ["no ", "don't", "do not", "without", "avoid", "never"])]
    for fam in POSITIVE_ONLY_FAMILIES:
        if fam in fam_prompts:
            name, ptxt = fam_prompts[fam]
            hits = negation_hits(ptxt, negation_words)
            if hits:
                fails.append(f"negation: prompt {name} contains negation word(s) {', '.join(repr(h) for h in hits)}; "
                             "rewrite as what should be there instead")

    # ---- video
    video = brief.get("video") if isinstance(brief.get("video"), dict) else None
    if decision == "video" and not video:
        fails.append("required: video block (duration_s, camera, beats, dialogue, captions_plan) is missing for a video decision")
    duration = None
    if video:
        try:
            duration = float(video.get("duration_s")) if video.get("duration_s") is not None else None
        except (TypeError, ValueError):
            fails.append(f"video: duration_s is not a number ({video.get('duration_s')!r})")
        beats = video.get("beats") if isinstance(video.get("beats"), list) else []
        if len(beats) > 3:
            warns.append(f"video: {len(beats)} beats; keep at most 3 per clip")
        if _str(video.get("captions_plan")).lower() not in ("", "none", "burn_in_in_editor"):
            warns.append(f"video: captions_plan {video.get('captions_plan')!r} is not none|burn_in_in_editor")
    dialogue_lines = _dialogue_lines(video)

    veo_cfg = mcfg.get("veo") or {}
    veo_relevant = decision == "video" and (primary_fam == "veo" or "veo" in fam_prompts)
    if veo_relevant:
        durations = [float(d) for d in (veo_cfg.get("durations") or [4, 6, 8])]
        if duration is None:
            fails.append("veo: video.duration_s is required")
        elif duration not in durations:
            fails.append(f"veo: duration {duration:g}s is not one of {', '.join(f'{d:g}' for d in durations)}")
        if primary_fam == "veo" and aspect and aspect not in [str(a) for a in (veo_cfg.get("aspects") or [])]:
            fails.append(f"veo: aspect {aspect} is not a Veo aspect ({', '.join(str(a) for a in veo_cfg.get('aspects') or [])})")
        if "veo" in fam_prompts:
            name, ptxt = fam_prompts["veo"]
            max_words = int(veo_cfg.get("max_prompt_words") or 700)
            n = _words(ptxt)
            if n > max_words:
                fails.append(f"veo: prompt {name} has {n} words, above the {max_words}-word cap")
            if not dialogue_lines:
                dialogue_lines = re.findall(r'says?,?\s*"([^"]+)"', _fold(ptxt))
            hits = on_screen_text_hits(ptxt)
            if hits:
                fails.append(f"veo: prompt {name} asks for on-screen text ({', '.join(hits)}); add captions in an editor")
        if duration and dialogue_lines:
            rate = float(veo_cfg.get("dialogue_words_per_second") or 2.5)
            dw = sum(_words(x) for x in dialogue_lines)
            if dw > rate * duration:
                fails.append(f"veo: dialogue has {dw} words, above {rate:g} x {duration:g}s = {rate * duration:g}")

    rw_cfg = mcfg.get("runway") or {}
    runway_relevant = decision == "video" and (primary_fam == "runway" or "runway" in fam_prompts)
    if runway_relevant:
        i2v = _is_i2v(brief, video)
        t2v_aspects = [str(a) for a in (rw_cfg.get("t2v_aspects") or ["16:9"])]
        i2v_aspects = [str(a) for a in (rw_cfg.get("i2v_aspects") or ["9:16", "1:1", "3:4", "16:9"])]
        if primary_fam == "runway" and aspect:
            if not i2v and aspect not in t2v_aspects:
                fails.append(f"runway: text-to-video renders only {', '.join(t2v_aspects)} (got {aspect}); set "
                             "video.start_frame: generated_still for image-to-video or change the aspect")
            elif i2v and aspect not in i2v_aspects:
                fails.append(f"runway: image-to-video aspect {aspect} is not one of {', '.join(i2v_aspects)}")
        dr = rw_cfg.get("duration_range") or [2, 10]
        if duration is not None and not (float(dr[0]) <= duration <= float(dr[1])):
            fails.append(f"runway: duration {duration:g}s is outside {dr[0]}-{dr[1]}s")
        if dialogue_lines and primary_fam == "runway":
            warns.append("runway: dialogue lines present but Runway generates no dialogue; plan voiceover in an editor")
        if "runway" in fam_prompts:
            name, ptxt = fam_prompts["runway"]
            max_chars = int(rw_cfg.get("max_prompt_chars") or 1000)
            if len(ptxt.strip()) > max_chars:
                fails.append(f"runway: prompt {name} has {len(ptxt.strip())} chars, above the {max_chars}-char cap")
            hits = on_screen_text_hits(ptxt)
            if hits:
                fails.append(f"runway: prompt {name} asks for on-screen text ({', '.join(hits)}); add captions in an editor")
    if decision != "video":
        for fam in VIDEO_FAMILIES:
            if fam in fam_prompts:
                warns.append(f"prompts: {fam} prompt present but decision is {decision}")

    # ---- alt text
    alt = _str(brief.get("alt_text"))
    alt_max = int(pcfg.get("alt_text_max") or (120 if platform == "linkedin" else 1000))
    if not alt:
        warns.append("alt_text: missing; the media judge needs it for the alt-text-alone probe")
    elif len(alt) > alt_max:
        fails.append(f"alt_text: {len(alt)} chars, above the {platform} cap of {alt_max}")

    # ---- people and brands (content fields + every prompt)
    scan_blobs = [("brief", content_blob)] + [(f"prompt {name}", ptxt) for name, ptxt in fam_prompts.values()]
    for where, blob in scan_blobs:
        known, pairs = find_people(blob, allow_names)
        for k in known:
            fails.append(f"person: real person named in {where}: {k}")
        for p in pairs:
            warns.append(f"person: capitalized name-like pair in {where}: {p!r} (confirm it is not a real person)")
        if where != "brief":
            for b in find_brands(blob, allow_brands):
                warns.append(f"brand: {b} named in {where}; only the user's own brand may appear")
    for b in content_brands:
        if genre not in ("fake_screenshot", "parody_ui"):
            warns.append(f"brand: {b} named in the brief; only the user's own brand may appear (real_capture_direction is exempt)")

    # ---- safety flags
    sc = brief.get("safety_checks")
    if isinstance(sc, dict):
        for k, v in sc.items():
            if v is False:
                fails.append(f"safety: safety_checks.{k} is false")
    else:
        warns.append("safety_checks block missing")

    # ---- factual claims in charts
    if genre in ("diagram_chart", "whiteboard_explainer") and not brief.get("factual_claims_in_visual"):
        blob = "\n".join(ptxt for _, ptxt in fam_prompts.values()) + "\n" + content_blob
        if re.search(r"\d+(?:\.\d+)?\s*(?:%|percent|x\b|\$|k\b|m\b|million|billion)|\$\s*\d", blob, flags=re.IGNORECASE):
            warns.append("factual: chart/explainer asserts numbers but factual_claims_in_visual is empty")

    return _result(fails, warns, decision, primary or None, platform, genre=genre or None,
                   prompts=sorted(name for name, _ in fam_prompts.values()))


def _dialogue_lines(video: dict | None) -> list[str]:
    if not video:
        return []
    out: list[str] = []
    for d in video.get("dialogue") or []:
        if isinstance(d, dict) and _str(d.get("line")):
            out.append(d["line"])
        elif isinstance(d, str) and d.strip():
            out.append(d)
    return out


def _is_i2v(brief: dict, video: dict | None) -> bool:
    if video and _str(video.get("start_frame")).lower() not in ("", "none", "null"):
        return True
    for r in brief.get("references") or []:
        if isinstance(r, dict) and _str(r.get("role")).lower() == "first_frame":
            return True
    return False


def _result(fails: list[str], warns: list[str], decision: str | None, tool: str | None, platform: str,
            **extra: Any) -> dict:
    return {"ok": not fails, "fails": fails, "warnings": warns, "decision": decision, "tool": tool,
            "platform": platform, "n_fails": len(fails), "n_warnings": len(warns), **extra}


# --------------------------------------------------------------------------- CLI

def load_prompts(prompts_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not prompts_dir.is_dir():
        return out
    for p in sorted(prompts_dir.iterdir()):
        if p.suffix.lower() in (".md", ".txt") and p.is_file():
            out[p.stem] = p.read_text(encoding="utf-8")
    return out


def default_prompts_dir(brief_path: Path, brief: dict) -> Path:
    pid = _str(brief.get("post_id")) if isinstance(brief, dict) else ""
    cands = []
    if pid:
        cands.append(brief_path.parent / f"{pid}.prompts")
    stem = brief_path.name
    for suffix in (".brief.yaml", ".brief.yml", ".yaml", ".yml"):
        if stem.endswith(suffix):
            cands.append(brief_path.parent / f"{stem[: -len(suffix)]}.prompts")
            break
    for c in cands:
        if c.is_dir():
            return c
    return cands[0] if cands else brief_path.parent / "prompts"


def persona_allowlist() -> dict:
    """Optional `name`/`brands` from style/persona.md front matter (user's own identity is never flagged)."""
    p = common.ROOT / "style" / "persona.md"
    if not p.exists():
        return {"names": [], "brands": []}
    try:
        meta, _ = common.split_front_matter(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return {"names": [], "brands": []}
    names = [str(meta["name"])] if isinstance(meta.get("name"), str) else []
    brands = meta.get("brands") or ([meta["brand"]] if isinstance(meta.get("brand"), str) else [])
    return {"names": names, "brands": [str(b) for b in brands] if isinstance(brands, list) else []}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a media brief YAML and its rendered tool prompts.")
    ap.add_argument("brief", help="path to <cid>.brief.yaml")
    ap.add_argument("--prompts", help="directory of rendered prompts (default: <cid>.prompts next to the brief)")
    ap.add_argument("--platform", choices=["linkedin", "x"], help="override the brief's platform")
    ap.add_argument("--json", action="store_true", help="JSON output (always on)")
    ap.add_argument("--root", help="project root override (default: POSTSMITH_ROOT / auto-detect)")
    args = ap.parse_args(argv)
    if args.root:
        common.ROOT = Path(args.root).resolve()
        common._CONFIG = None
    brief_path = Path(args.brief)
    if not brief_path.is_absolute():
        brief_path = (Path.cwd() / brief_path) if (Path.cwd() / brief_path).exists() else common.ROOT / brief_path
    if not brief_path.exists():
        common.emit({"ok": False, "error": f"brief not found: {args.brief}"})
        return 0
    try:
        brief = common.load_yaml(brief_path)
    except (OSError, ValueError, yaml.YAMLError) as e:  # yaml errors are user errors
        common.emit({"ok": False, "error": f"cannot parse brief YAML: {e}"})
        return 0
    if isinstance(brief, dict) and isinstance(brief.get("media_brief"), dict):
        brief = brief["media_brief"]
    if not isinstance(brief, dict) or not brief:
        common.emit({"ok": False, "fails": ["schema: brief is empty or not a mapping"], "warnings": [],
                     "brief": common.rel(brief_path), "error": "brief is empty or not a mapping"})
        return 0
    prompts_dir = Path(args.prompts) if args.prompts else default_prompts_dir(brief_path, brief)
    if args.prompts and not prompts_dir.is_absolute():
        prompts_dir = (Path.cwd() / prompts_dir) if (Path.cwd() / prompts_dir).exists() else common.ROOT / prompts_dir
    if args.prompts and not prompts_dir.is_dir():
        common.emit({"ok": False, "error": f"prompts directory not found: {args.prompts}"})
        return 0
    prompts = load_prompts(prompts_dir)
    platform = args.platform or _str(brief.get("platform")).lower()
    try:
        cfg = common.load_config()
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as e:
        common.emit({"ok": False, "error": f"cannot load config: {e}"})
        return 0
    out = check(brief, prompts, cfg, platform, own=persona_allowlist())
    out["brief"] = common.rel(brief_path)
    out["prompts_dir"] = common.rel(prompts_dir) if prompts_dir.is_dir() else None
    common.emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
