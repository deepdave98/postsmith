#!/usr/bin/env python3
"""Platform mechanics checks for a candidate post (Tier 0, contracts §16).

Pure entry point:

    run_checks(text, platform, meta, cfg) -> {"checks": {...}, "chars": int, "x_len": int|None,
                                             "fold_preview": str, "advisory": {...}}

Checks (ids fixed by contracts §5):
  P1_length    LinkedIn <= max_chars; X <= 280 as X counts (twitter-text weights via common.x_count: URL 23,
               one emoji sequence 2, code points outside the light ranges 2; long post only when the persona
               allows it).
  P2_fold      LinkedIn: what survives the mobile fold (first 3 lines or 140 units, whichever cuts first;
               a blank line is a line; emoji count 2 units). Hard fail only when the 140 cut lands mid-word
               AND no sentence/clause boundary (. ! ? : ; or a line break) occurs before it; a cut on a word
               boundary with no clause boundary is a flag. The 210-unit desktop cut is reported too.
               X: pass when x_len <= 280; otherwise the first 280 must end at a sentence boundary.
  P_min_words  fewer words than platforms.<p>.min_words (defaults: linkedin 8, x 2) is a hard fail.
  P3_hashtags  X: any hashtag fails. LinkedIn: more than the persona/config maximum fails; any hashtag is
               noted (target is 0). A trailing hashtag block (>= 2 hashtags on final hashtag-only lines) fails
               on both platforms. Evidence: one verbatim row per hashtag.
  P4_links     X: any URL or lowercase bare domain in the body fails (the link belongs in front-matter `reply_1`;
               `it.So` after a missing space is prose, not a link).
               LinkedIn: 0 or >= 2 links pass; exactly one naked link is advisory. The phrase
               "link in (the) comments" is a hard fail on both.
  P5_markup    markdown, unicode mathematical bold/italic letters, placeholders, leaked labels at line start,
               variant labels alone on their line ("Option A"), citation artifacts, character-count notes at the
               end of the text or alone on a line; curly quotes only when meta["corpus_uses_straight_quotes"] is
               true (one evidence row per line that carries one).
  P6_emoji     emoji count (common.EMOJI_RE) vs persona/config emoji_max.

Persona policy precedence (per platform): meta["platform_choices"] > style/persona.md front matter
`platform_choices` > config/postsmith.yaml `platforms.<p>`. Inside `platform_choices` a nested per-platform
mapping (`linkedin: {...}` / `x: {...}`) beats a flat key. Keys: `hashtags_max`, `emoji_max`, `long_posts`
(bool, X only); `hashtags_never: true` is read as `hashtags_max: 0`.

Result shape per check: {"class": hard|soft|flag|advisory, "pass": bool, "evidence": [{"span", "why"}],
"downgraded": false, ...check-specific fields}. `pass` always answers the gate; a P2 result with
`"class": "flag"` and `"flag": true` passed the hard gate but must be addressed or waived.

CLI: platform_check.py <candidate.md|text file> [--platform linkedin|x] [--json]
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import (  # noqa: E402
    EMOJI_RE,
    HASHTAG_RE,
    URL_RE,
    emit,
    error,
    load_config,
    read_front_matter_file,
    rel,
    split_front_matter,
    words,
    x_count,
)

PLATFORMS = ("linkedin", "x")
CHECK_IDS = ("P1_length", "P2_fold", "P_min_words", "P3_hashtags", "P4_links", "P5_markup", "P6_emoji")

# Defaults used when neither persona nor config says otherwise.
DEFAULT_MIN_WORDS = {"linkedin": 8, "x": 2}
DEFAULT_HASHTAGS_MAX = {"linkedin": 3, "x": 0}
DEFAULT_EMOJI_MAX = {"linkedin": 3, "x": 1}
FOLD_EMOJI_UNITS = 2          # research-linkedin §1: emoji consume more than one unit on the fold
READING_WPM = 230
LINK_REPLY_FIELD = "reply_1"
EVIDENCE_MAX = 160          # evidence spans are cut, never rewritten, so they stay verbatim substrings

# --------------------------------------------------------------------------- regexes

# A sentence/clause boundary: terminal punctuation (optionally followed by closing quotes/brackets) that is
# followed by whitespace or the end of the text, or a line break.
BOUNDARY_RE = re.compile(r"[.!?:;…][\"”'’)\]]*(?=\s|$)|\n")
SENTENCE_END_RE = re.compile(r"[.!?…][\"”'’)\]]*$")

LINK_IN_COMMENTS_RE = re.compile(
    r"\blinks?(?:'s|’s|\s+(?:is|are|will be|be))?\s+(?:is\s+)?(?:in|below\s+in|down\s+in)\s+(?:the\s+)?(?:first\s+)?comments?\b",
    re.IGNORECASE,
)
# Case-sensitive and lowercase only: platforms auto-link `floqer.com`, while `it.So` (a missing space after a
# sentence-ending period followed by a capitalised word that happens to be a TLD) is prose, not a link.
BARE_DOMAIN_RE = re.compile(
    r"(?<![\w.@/\-])(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+"
    r"(?:com|net|org|io|ai|co|dev|app|me|so|xyz|gg|ly|to|tv|fm|info|biz|us|uk|ca|au|eu|in|de|fr|nl|se|ch)\b"
    r"(?:/[^\s]*)?"
)
HASHTAG_ONLY_LINE_RE = re.compile(r"\s*(?:#[A-Za-z]\w*[\s,]*)+")

MARKUP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("markdown_bold", re.compile(r"\*\*[^*\n]+?\*\*|__[^_\n]*?\s[^_\n]*?__")),
    ("markdown_header", re.compile(r"^#{1,6}[ \t]+\S.*$", re.MULTILINE)),
    ("markdown_code", re.compile(r"`[^`\n]*`|```")),
    ("markdown_link", re.compile(r"\[[^\]\n]+\]\([^)\n]*\)")),
    ("unicode_math_letters", re.compile(r"[\U0001D400-\U0001D7FF]+")),
    (
        "placeholder",
        re.compile(
            r"\[\s*(?:your\b[^\]\n]{0,40}|insert\b[^\]\n]{0,40}|company|name|product|date|link|url|number|"
            r"x|n|tbd|placeholder|topic|city)\s*\]|\{\{[^}\n]{0,60}\}\}|<\s*insert\b[^>\n]{0,40}>",
            re.IGNORECASE,
        ),
    ),
    (
        "leaked_label",
        re.compile(
            r"^[ \t]*(?:hook|rehook|caption|post|body|title|headline|tweet|cta|alt[ -]?text|word count|"
            r"linkedin post|x post|punchline|takeaway|subject)[ \t]*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        # "Option A" / "Version 2:" alone on its line (a leaked variant heading); "Option A: pay the vendor" is prose
        "leaked_variant_label",
        re.compile(
            r"^[ \t]*(?:option|version|variant|draft)[ \t]*(?:\d+|[A-Z])(?![\w'’])[ \t]*(?::|[-–—]|\))?[ \t]*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    ("citation_artifact", re.compile(r"turn\d+(?:search|view|news|image)\d+|oaicite|\[cite:|contentReference|【\d+†")),
    (
        # "(≈280 chars)" only at the very end of the text or alone on its line; "(12 words)" mid-sentence is prose
        "char_count_note",
        re.compile(
            r"(?:(?<=^)|(?<=\n))[ \t]*\(\s*[≈~]?\s*\d{1,3}(?:,\d{3})*\s*(?:chars?|characters|words)\s*\)[ \t]*(?=\n|$)"
            r"|\(\s*[≈~]?\s*\d{1,3}(?:,\d{3})*\s*(?:chars?|characters|words)\s*\)[ \t]*$",
            re.IGNORECASE,
        ),
    ),
]
CURLY_QUOTE_RE = re.compile(r"[“”‘’„‚]")

# --------------------------------------------------------------------------- small helpers


def _res(cls: str, passed: bool, evidence: list[dict] | None = None, **extra: Any) -> dict:
    out: dict[str, Any] = {"class": cls, "pass": bool(passed), "evidence": list(evidence or []), "downgraded": False}
    out.update(extra)
    return out


def _ev(span: str, why: str) -> dict:
    """Evidence row. `span` must be a verbatim substring of the text (truncated, never rewritten)."""
    return {"span": span[:EVIDENCE_MAX], "why": why}


def _snippet(s: str, n: int = 80) -> str:
    s = s.replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 1] + "…"


def _is_wordchar(ch: str) -> bool:
    return ch.isalnum() or ch in "'’_-"


def _clean_text(text: str) -> str:
    """NFC, LF line endings, trailing newlines dropped (candidate bodies end with one newline)."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return text.rstrip("\n")


def _first_nonblank_line(text: str) -> str:
    for ln in text.split("\n"):
        if ln.strip():
            return ln.strip()
    return ""


# --------------------------------------------------------------------------- policy


def load_persona_choices(path: Path | str | None = None) -> dict:
    """`platform_choices` mapping from style/persona.md front matter, or {} when absent/unreadable."""
    p = Path(path) if path else common.ROOT / "style" / "persona.md"
    try:
        if not p.exists():
            return {}
        meta, _ = read_front_matter_file(p)
        pc = meta.get("platform_choices") if isinstance(meta, dict) else None
        return pc if isinstance(pc, dict) else {}
    except Exception:  # noqa: BLE001 - persona.md is user-edited; never let it crash a check
        return {}


def _choice(choices: dict, platform: str, key: str) -> tuple[Any, bool]:
    """Look up key in choices[platform] then flat choices. Returns (value, found)."""
    if not isinstance(choices, dict):
        return None, False
    nested = choices.get(platform)
    if isinstance(nested, dict) and key in nested:
        return nested[key], True
    if key in choices:
        return choices[key], True
    return None, False


def resolve_policy(platform: str, meta: dict, cfg: dict, persona_choices: dict | None = None) -> dict:
    """Merge config defaults, persona.md platform_choices and candidate front matter into one policy dict."""
    pcfg = (cfg.get("platforms") or {}).get(platform) or {}
    if persona_choices is None:
        persona_choices = load_persona_choices()
    meta_choices = meta.get("platform_choices") if isinstance(meta, dict) else None
    layers = [("meta", meta_choices or {}), ("persona", persona_choices or {})]

    def pick(key: str, default: Any) -> tuple[Any, str]:
        for name, layer in layers:
            val, found = _choice(layer, platform, key)
            if found and val is not None:
                return val, name
        if key in pcfg and pcfg[key] is not None:
            return pcfg[key], "config"
        return default, "default"

    hashtags_max, h_src = pick("hashtags_max", DEFAULT_HASHTAGS_MAX[platform])
    never, n_src = pick("hashtags_never", False)
    if never:
        hashtags_max, h_src = 0, n_src
    emoji_max, e_src = pick("emoji_max", DEFAULT_EMOJI_MAX[platform])
    long_posts, l_src = pick("long_posts", False)
    if platform == "x" and l_src == "default":
        long_posts, l_src = pick("x_long_posts", False)
    min_words, m_src = pick("min_words", DEFAULT_MIN_WORDS[platform])
    return {
        "hashtags_max": int(hashtags_max),
        "emoji_max": int(emoji_max),
        "long_posts": bool(long_posts) if platform == "x" else False,
        "min_words": int(min_words),
        "sources": {"hashtags_max": h_src, "emoji_max": e_src, "long_posts": l_src, "min_words": m_src},
    }


# --------------------------------------------------------------------------- fold geometry


def display_cut_index(s: str, budget: int, emoji_units: int = FOLD_EMOJI_UNITS) -> int:
    """Index i such that s[:i] fits in `budget` display units (emoji = emoji_units, any other code point 1)."""
    units = 0
    i = 0
    n = len(s)
    while i < n:
        m = EMOJI_RE.match(s, i)
        if m and m.end() > i:
            w, step = emoji_units, m.end() - i
        else:
            w, step = 1, 1
        if units + w > budget:
            break
        units += w
        i += step
    return i


def x_cut_index(text: str, budget: int, xcfg: dict) -> int:
    """Index i such that text[:i] fits in `budget` X units (same segmentation and weights as common.x_count)."""
    return common.x_cut_index(text, budget, xcfg)


def boundary_before(text: str, cut_index: int) -> dict | None:
    """First sentence/clause boundary that ends at or before cut_index, or None."""
    for m in BOUNDARY_RE.finditer(text):
        if m.start() >= cut_index:
            break
        if m.end() <= cut_index:
            return {"index": m.end(), "span": "\\n" if m.group(0) == "\n" else m.group(0)}
    return None


def cut_is_mid_word(text: str, cut_index: int) -> bool:
    if cut_index <= 0 or cut_index >= len(text):
        return False
    return _is_wordchar(text[cut_index - 1]) and _is_wordchar(text[cut_index])


def ends_at_sentence_boundary(text: str, cut_index: int) -> bool:
    """True when text[:cut_index] ends (ignoring trailing whitespace) at a sentence end or a line break."""
    prefix = text[:cut_index]
    stripped = prefix.rstrip()
    if "\n" in prefix[len(stripped):]:
        return True
    if cut_index < len(text) and text[cut_index] == "\n":
        return True
    return bool(SENTENCE_END_RE.search(stripped))


def linkedin_fold(text: str, char_budget: int, max_lines: int) -> dict:
    """What a reader sees before '…see more': the first `max_lines` lines cut at `char_budget` units."""
    ls = text.split("\n")
    head = "\n".join(ls[:max_lines])
    idx = display_cut_index(head, char_budget)
    cut_by_chars = idx < len(head)
    cut_by_lines = len(ls) > max_lines
    if cut_by_chars:
        cut_by: str | None = "chars"
        cut_index = idx
    elif cut_by_lines:
        cut_by = "lines"
        cut_index = len(head)
    else:
        cut_by = None
        cut_index = len(text)
    preview = text[:cut_index].rstrip()
    boundary = boundary_before(text, cut_index) if cut_by else {"index": cut_index, "span": "<end>"}
    mid_word = cut_is_mid_word(text, cut_index) if cut_by == "chars" else False
    return {
        "preview": preview,
        "cut_at": char_budget,
        "cut_by": cut_by,
        "cut_index": cut_index,
        "lines_in_fold": min(len(ls), max_lines),
        "blank_lines_in_fold": sum(1 for ln in ls[:max_lines] if not ln.strip()),
        "boundary_within": boundary is not None,
        "boundary": boundary,
        "mid_word": mid_word,
        "next_chars": _snippet(text[cut_index:cut_index + 20], 24) if cut_by else "",
    }


# --------------------------------------------------------------------------- individual checks


def check_length(text: str, platform: str, chars: int, x_len: int | None, pcfg: dict, policy: dict) -> dict:
    if platform == "linkedin":
        limit = int(pcfg.get("max_chars", 3000))
        if chars <= limit:
            return _res("hard", True, value=chars, limit=limit)
        return _res(
            "hard", False,
            [_ev(text[limit:], f"{chars} chars exceeds the LinkedIn cap of {limit} by {chars - limit}")],
            value=chars, limit=limit,
        )
    limit = int(pcfg.get("max_chars", 280))
    assert x_len is not None
    if x_len <= limit:
        return _res("hard", True, value=x_len, limit=limit, long_post=False)
    cut = x_cut_index(text, limit, pcfg)
    if policy["long_posts"]:
        long_limit = int(pcfg.get("long_post_max_chars", 25000))
        ok = x_len <= long_limit
        ev = [] if ok else [_ev(text[cut:], f"{x_len} X units exceeds the long-post cap of {long_limit}")]
        return _res("hard", ok, ev, value=x_len, limit=long_limit, long_post=True,
                    note=f"over {limit}: allowed as a long post by persona policy; only the first {limit} show in the timeline")
    return _res(
        "hard", False,
        [_ev(text[cut:], f"{x_len} X units exceeds {limit} (URLs count {pcfg.get('url_weight', 23)}, "
                                   f"emoji {pcfg.get('emoji_weight', 2)}); persona does not allow long posts")],
        value=x_len, limit=limit, long_post=False,
    )


def check_fold(text: str, platform: str, x_len: int | None, pcfg: dict, policy: dict) -> dict:
    if platform == "linkedin":
        mobile = linkedin_fold(text, int(pcfg.get("fold_mobile_chars", 140)), int(pcfg.get("fold_lines", 3)))
        desktop = linkedin_fold(text, int(pcfg.get("fold_desktop_chars", 210)), int(pcfg.get("fold_lines", 3)))
        common_fields = {"preview": mobile["preview"], "cut_at": mobile["cut_at"], "mobile": mobile, "desktop": desktop}
        if mobile["boundary_within"]:
            return _res("hard", True, flag=False, **common_fields)
        why_base = f"no sentence/clause boundary (. ! ? : ; or line break) within the first {mobile['cut_at']} chars"
        ci = mobile["cut_index"]
        around = text[max(0, ci - 40):ci + 12]
        if mobile["mid_word"]:
            return _res(
                "hard", False,
                [_ev(around, f"mobile fold cuts mid-word after {text[max(0, ci - 12):ci]!r} and {why_base}")],
                flag=False, **common_fields,
            )
        return _res(
            "flag", True,
            [_ev(around, f"{why_base}; the cut after {text[max(0, ci - 12):ci]!r} lands on a word boundary, "
                         "so the hook is readable but incomplete")],
            flag=True, **common_fields,
        )
    limit = int(pcfg.get("max_chars", 280))
    assert x_len is not None
    if x_len <= limit:
        return _res("hard", True, preview=text, cut_at=limit, cut_by=None, ends_at_sentence=True, flag=False)
    cut = x_cut_index(text, limit, pcfg)
    preview = text[:cut].rstrip()
    ends_ok = ends_at_sentence_boundary(text, cut)
    ev = [] if ends_ok else [_ev(text[max(0, cut - 50):cut + 20],
                                 f"the first {limit} X units end after {text[max(0, cut - 12):cut]!r}, not at a sentence "
                                 "boundary; the timeline shows only that much")]
    return _res("hard", ends_ok, ev, preview=preview, cut_at=limit, cut_by="chars", ends_at_sentence=ends_ok,
                long_posts_allowed=policy["long_posts"], flag=False)


def check_min_words(text: str, n_words: int, policy: dict) -> dict:
    minimum = policy["min_words"]
    if n_words >= minimum:
        return _res("hard", True, value=n_words, min=minimum)
    return _res("hard", False, [_ev(text.strip(), f"{n_words} words is below the minimum of {minimum}")],
                value=n_words, min=minimum)


def _trailing_hashtag_block(text: str) -> str | None:
    ls = text.rstrip().split("\n")
    i = len(ls) - 1
    tail: list[str] = []
    while i >= 0 and ls[i].strip() and HASHTAG_ONLY_LINE_RE.fullmatch(ls[i]):
        tail.insert(0, ls[i])
        i -= 1
    block = "\n".join(tail)
    return block if tail and len(HASHTAG_RE.findall(block)) >= 2 else None


def check_hashtags(text: str, platform: str, policy: dict) -> dict:
    tags = HASHTAG_RE.findall(text)
    block = _trailing_hashtag_block(text)
    limit = policy["hashtags_max"] if platform == "linkedin" else 0
    ev: list[dict] = []
    if block:
        ev.append(_ev(block, "hashtag block at the end of the post"))
    if platform == "x" and tags:
        ev.extend(_ev(m.group(0), "X posts carry no hashtags") for m in HASHTAG_RE.finditer(text))
    elif platform == "linkedin" and len(tags) > limit:
        ev.extend(_ev(m.group(0), f"{len(tags)} hashtags exceeds the policy maximum of {limit}")
                  for m in HASHTAG_RE.finditer(text))
    passed = not ev
    note = None
    if passed and tags:
        note = f"{len(tags)} hashtag(s) within the maximum of {limit}; the target is 0"
    return _res("hard", passed, ev, count=len(tags), max=limit, tags=tags, block=bool(block), note=note)


def find_links(text: str) -> list[str]:
    """URLs (common.URL_RE) plus bare domains that platforms auto-link, in document order."""
    spans: list[tuple[int, int, str]] = [(m.start(), m.end(), m.group(0)) for m in URL_RE.finditer(text)]
    for m in BARE_DOMAIN_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _ in spans):
            spans.append((m.start(), m.end(), m.group(0)))
    spans.sort()
    return [s.rstrip(".,;:!?)") for _, _, s in spans]


def check_links(text: str, platform: str, meta: dict) -> dict:
    links = find_links(text)
    phrase = LINK_IN_COMMENTS_RE.search(text)
    ev: list[dict] = []
    cls = "hard"
    if phrase:
        ev.append(_ev(phrase.group(0), "'link in comments' is a known reach-killer and reads as a workaround"))
    if platform == "x":
        for link in links:
            ev.append(_ev(link, f"X body must contain no link; put it in the front-matter `{LINK_REPLY_FIELD}` field"))
        reply_1 = meta.get(LINK_REPLY_FIELD) if isinstance(meta, dict) else None
        return _res(cls, not ev, ev, count=len(links), links=links, reply_1_present=bool(reply_1))
    if len(links) == 1 and not phrase:
        cls = "advisory"
        return _res(cls, True, [], count=1, links=links,
                    note="exactly one naked link: single-link posts get ~19% less reach; use 0 or >= 2 links, "
                         "and make sure the post reads complete without it")
    return _res(cls, not ev, ev, count=len(links), links=links)


def check_markup(text: str, meta: dict) -> dict:
    ev: list[dict] = []
    kinds: list[str] = []
    for kind, rx in MARKUP_PATTERNS:
        for m in rx.finditer(text):
            span = m.group(0)
            if not span.strip():
                continue
            if kind not in kinds:
                kinds.append(kind)
            ev.append(_ev(span, _MARKUP_WHY[kind]))
    if isinstance(meta, dict) and meta.get("corpus_uses_straight_quotes"):
        curly = CURLY_QUOTE_RE.findall(text)
        if curly:
            kinds.append("curly_quotes")
            why = f"{len(curly)} curly quote(s) but the corpus uses straight quotes"
            for ln in [ln for ln in text.split("\n") if CURLY_QUOTE_RE.search(ln)][:5]:
                ev.append(_ev(ln, why))
    return _res("hard", not ev, ev, kinds=kinds, count=len(ev))


_MARKUP_WHY = {
    "markdown_bold": "markdown bold/underline markers do not render in a plain-text post",
    "markdown_header": "markdown header at line start",
    "markdown_code": "backticks leak into the pasted text",
    "markdown_link": "markdown link syntax leaks into the pasted text",
    "unicode_math_letters": "unicode mathematical bold/italic letters break screen readers and search",
    "placeholder": "unfilled placeholder",
    "leaked_label": "leaked drafting label at line start",
    "leaked_variant_label": "leaked option/version label",
    "citation_artifact": "citation artifact from a chatbot",
    "char_count_note": "character/word-count note left in the text",
}


def check_emoji(text: str, policy: dict) -> dict:
    found = EMOJI_RE.findall(text)
    limit = policy["emoji_max"]
    if len(found) <= limit:
        return _res("hard", True, count=len(found), max=limit, emoji=found)
    ev = [_ev(e, f"emoji {i} of {len(found)} (policy allows {limit})") for i, e in enumerate(found, 1)]
    return _res("hard", False, ev, count=len(found), max=limit, emoji=found)


# --------------------------------------------------------------------------- advisory


def advisory_fields(text: str, platform: str, chars: int, n_words: int, pcfg: dict, meta: dict, x_len: int | None) -> dict:
    first = _first_nonblank_line(text)
    band = None
    if platform == "linkedin":
        lo, hi = (pcfg.get("length_band_advisory") or [1000, 2500])[:2]
        band = "short" if chars < lo else "long" if chars > hi else "in"
    out = {
        "li_length_band": band,
        "first_line_words": len(words(first)),
        "first_line_chars": len(first),
        "question_opener": bool(re.match(r"[^.!?\n]*\?", first)),
        "reading_time_s": (max(1, round(n_words / READING_WPM * 60)) if n_words else 0),
        "words": n_words,
        "lines": len(text.split("\n")) if text else 0,
        "blank_lines": sum(1 for ln in text.split("\n") if not ln.strip()) if text else 0,
    }
    if platform == "x":
        cid = str(meta.get("cid", "")) if isinstance(meta, dict) else ""
        if cid.endswith("x1") or (isinstance(meta, dict) and meta.get("shape") == "one_liner"):
            one_max = int(pcfg.get("one_liner_max", 140))
            out["one_liner_limit"] = one_max
            out["one_liner_over"] = bool(x_len is not None and x_len > one_max)
    return out


# --------------------------------------------------------------------------- entry point


def run_checks(text: str, platform: str, meta: dict, cfg: dict, persona_choices: dict | None = None) -> dict:
    """Contracts §16. `persona_choices` overrides the style/persona.md lookup (tests, tier0 caching)."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {', '.join(PLATFORMS)}, got {platform!r}")
    meta = meta if isinstance(meta, dict) else {}
    cfg = cfg or load_config()
    pcfg = (cfg.get("platforms") or {}).get(platform) or {}
    policy = resolve_policy(platform, meta, cfg, persona_choices)

    text = _clean_text(text)
    chars = len(text)
    x_len = x_count(text, pcfg) if platform == "x" else None
    n_words = len(words(text))

    checks = {
        "P1_length": check_length(text, platform, chars, x_len, pcfg, policy),
        "P2_fold": check_fold(text, platform, x_len, pcfg, policy),
        "P_min_words": check_min_words(text, n_words, policy),
        "P3_hashtags": check_hashtags(text, platform, policy),
        "P4_links": check_links(text, platform, meta),
        "P5_markup": check_markup(text, meta),
        "P6_emoji": check_emoji(text, policy),
    }
    return {
        "checks": checks,
        "chars": chars,
        "x_len": x_len,
        "fold_preview": checks["P2_fold"]["preview"],
        "advisory": advisory_fields(text, platform, chars, n_words, pcfg, meta, x_len),
        "policy": policy,
    }


def summarize(result: dict) -> dict:
    """Failing hard checks, flags and advisories, as lists, for the CLI and for callers."""
    checks = result["checks"]
    hard_fails = [k for k, v in checks.items() if v["class"] == "hard" and not v["pass"]]
    flags = [k for k, v in checks.items() if v["class"] == "flag" and (v.get("flag") or not v["pass"])]
    advisories = [k for k, v in checks.items() if v["class"] == "advisory" and v.get("note")]
    return {"hard_fails": hard_fails, "flags": flags, "advisories": advisories, "all_hard_pass": not hard_fails}


# --------------------------------------------------------------------------- CLI


def _human(result: dict, platform: str, path: str) -> str:
    s = summarize(result)
    header = (
        f"{path} [{platform}] chars={result['chars']} x_len={result['x_len']} "
        f"hard_fails={len(s['hard_fails'])} flags={len(s['flags'])}"
    )
    out = [header]
    for cid, r in result["checks"].items():
        status = "PASS" if r["pass"] else "FAIL"
        if r["class"] == "flag" and r.get("flag"):
            status = "FLAG"
        extra = ""
        if "value" in r and "limit" in r:
            extra = f" {r['value']}/{r['limit']}"
        elif "count" in r and "max" in r:
            extra = f" {r['count']}/{r['max']}"
        elif "count" in r:
            extra = f" n={r['count']}"
        out.append(f"  {status:4} {cid:12} [{r['class']}]{extra}")
        for e in r["evidence"][:4]:
            out.append(f"       - {e['why']}: {e['span']!r}")
        if r.get("note"):
            out.append(f"       note: {r['note']}")
    out.append("fold preview:")
    out.extend("  | " + ln for ln in result["fold_preview"].split("\n"))
    adv = result["advisory"]
    out.append("advisory: " + ", ".join(f"{k}={v}" for k, v in adv.items()))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Platform checks (P1_length, P2_fold, P_min_words, P3_hashtags, "
                                             "P4_links, P5_markup, P6_emoji) for a candidate or plain text file.")
    ap.add_argument("path", help="candidate .md (front matter optional) or plain text file")
    ap.add_argument("--platform", choices=PLATFORMS, help="linkedin | x (default: front matter `platform`)")
    ap.add_argument("--json", action="store_true", help="JSON output (default is a human-readable summary)")
    args = ap.parse_args(argv)

    p = Path(args.path)
    if not p.is_absolute():
        p = (common.ROOT / p) if (common.ROOT / p).exists() else p.resolve()
    if not p.exists() or not p.is_file():
        error(f"file not found: {args.path}", args.json)
        return 0
    try:
        raw = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        error(f"not a UTF-8 text file: {args.path}", args.json)
        return 0
    try:
        meta, body = split_front_matter(raw)
    except Exception as exc:  # noqa: BLE001 - malformed YAML front matter
        error(f"bad front matter in {args.path}: {exc}", args.json)
        return 0
    meta = meta if isinstance(meta, dict) else {}
    platform = args.platform or meta.get("platform")
    if platform not in PLATFORMS:
        error("platform missing: pass --platform linkedin|x or set `platform:` in the front matter", args.json)
        return 0
    try:
        result = run_checks(body, platform, meta, load_config())
    except ValueError as exc:
        error(str(exc), args.json)
        return 0
    result.update(summarize(result))
    payload = {"ok": True, "path": rel(p), "platform": platform, "cid": meta.get("cid"), **result}
    emit(payload, args.json, human=_human(result, platform, rel(p)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
