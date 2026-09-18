#!/usr/bin/env python3
"""Deterministic AI-tell checks for postsmith Tier 0 (contracts.md section 16).

Checks (ids fixed by contracts.md section 5):
  P7_bait            engagement solicitation                      hard
  P8_opener          stale opener on line 1                       hard, base-rate downgradable
  P9_residue         chatbot residue / placeholders / reply-bot   hard
  P10_contrast_flip  it's not X, it's Y / Not X. Not Y. Just Z.   hard, base-rate downgradable
  P11_cluster        lexical cluster (>=3 t1, >=5 t1+t2+t3, >=2 claude)  hard
  P12_closer         moralizing closer on the last two lines      hard on regex; aphorism heuristic -> flag
  P13_specifics      zero specifics in a post above the word floor  hard
  P17_lists          tricolons (1 soft, >=2 hard); emoji-bullet / Term: description / anaphora lists hard
  P18_hedges         >= 3 hedges                                   soft
  P19_clickbait      clickbait framing                             hard on X, soft on LinkedIn
  P20_misc           hypophora, -ing riders, copula avoidance, colon reveal, meta-signposting, false range  soft each

Matching: NFKC + curly-quote/dash folding (common.fold_punct) with a character map back to the original
text, so every evidence span is verbatim. Lexicon phrases get word boundaries; matching is case-insensitive.

Library use:  from ai_tells import run_checks
CLI:          uv run tools/ai_tells.py <file> --platform linkedin|x [--json]
"""
from __future__ import annotations

import argparse
import json
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
    MENTION_RE,
    QUOTE_MAP,
    URL_RE,
    emit,
    error,
    fold_punct,
    load_config,
    load_lexicon,
    load_patterns,
    load_profile,
    load_yaml,
    read_front_matter_file,
    rel,
    words,
)

# --------------------------------------------------------------------------- constants

CHECK_IDS = [
    "P7_bait", "P8_opener", "P9_residue", "P10_contrast_flip", "P11_cluster", "P12_closer",
    "P13_specifics", "P17_lists", "P18_hedges", "P19_clickbait", "P20_misc",
]
LEXICON_TIERS = ("t1", "t2", "t3", "claude")
TIER_RANK = {"claude": 0, "t1": 1, "t2": 2, "t3": 3}

# P13: a post above this word floor must carry at least one specific. LinkedIn uses the contract's
# "> 40 words"; X posts rarely exceed 45 words, so the floor is lower there.
# Override with cfg["ai_tells"]["specifics_min_words"] (int or {platform: int}).
SPECIFICS_MIN_WORDS = {"linkedin": 40, "x": 20}

CLUSTER_T1 = 3
CLUSTER_TOTAL = 5
CLUSTER_CLAUDE = 2
HEDGE_SOFT = 3
TRICOLON_HARD = 2

# P17 sub-patterns that fail hard on their own (list forms) vs. those counted as tricolons.
P17_HARD_SUBS = {"anaphora_triple", "templated_lines", "emoji_bullets", "term_description"}
P17_TALLY_SUBS = {"tricolon", "parallel_triple", "numbered_insights"}

# Capitalized tokens that are not specifics (generic acronyms / titles / pronoun forms).
GENERIC_CAPS = {
    "AI", "ML", "LLM", "LLMS", "GENAI", "AGI", "SAAS", "B2B", "B2C", "D2C", "CEO", "CEOS", "CTO", "CTOS", "CFO",
    "COO", "CMO", "CPO", "CRO", "VP", "VPS", "SVP", "EVP", "HR", "PR", "ROI", "KPI", "KPIS", "OKR", "OKRS", "API",
    "APIS", "UX", "UI", "IT", "PM", "PMS", "MVP", "SEO", "SEM", "SDR", "SDRS", "BDR", "BDRS", "AE", "AES", "VC",
    "VCS", "IPO", "PDF", "PDFS", "URL", "URLS", "FAQ", "FAQS", "USA", "UK", "US", "EU", "TL", "DR", "PS", "OK",
    "IMO", "IMHO", "TBH", "NGL", "LOL", "FYI", "ASAP", "DM", "DMS", "CTA", "CTAS", "CRM", "ERP", "SQL", "GPU",
    "GPUS", "CPU", "CPUS", "RAG", "ARR", "MRR", "NPS", "CAC", "LTV", "ICP", "GTM", "PLG", "SMB", "SMBS", "QA", "TV",
    "RAM", "SSD", "MBA", "PHD", "AM", "ET", "PT", "GMT", "UTC", "AND", "OR", "THE", "NOT", "I",
    "IM", "IVE", "ID", "ILL", "AGENT", "AGENTS",
}
PRONOUN_FORMS = {"i", "i'm", "i've", "i'd", "i'll"}
# Unambiguous product / tool names: count as specifics in any case and position (no ordinary-English reading).
PRODUCT_NAMES = {
    "ffmpeg", "npm", "docker", "kubernetes", "k8s", "postgres", "postgresql", "mysql", "sqlite", "redis", "nginx",
    "javascript", "typescript", "nextjs", "vercel", "supabase", "openai", "anthropic", "chatgpt", "gpt-4", "gpt-4o",
    "gpt-5", "langchain", "llamaindex", "figma", "jira", "github", "gitlab", "aws", "gcp", "azure", "twilio",
    "hubspot", "salesforce", "zapier", "n8n", "webflow", "wordpress", "shopify", "airtable", "terraform", "pytorch",
    "tensorflow", "huggingface", "ollama", "deepseek", "midjourney", "linkedin", "twitter", "youtube", "tiktok",
    "reddit", "whatsapp", "gmail", "canva", "lemlist", "databricks", "bigquery", "dbt", "golang", "kotlin", "vscode",
    "emacs", "jupyter", "numpy", "fastapi", "laravel", "tailwind",
}
# Product names that are also ordinary English words ("months of runway", "the notion that", "customers react
# instantly"). They count only when capitalised mid-sentence (the proper-noun rule below), when preceded by a
# tool cue ("in Cursor", "via Slack") or when followed by a version / artefact token ("Linear ticket", "Cursor 2.0").
AMBIGUOUS_PRODUCT_NAMES = {
    "instantly", "notion", "react", "linear", "swift", "excel", "runway", "clay", "cursor", "loom", "rust", "grok",
    "apollo", "veo", "sora", "llama", "gemini", "slack", "zoom", "python", "git", "pip", "vim", "flask", "rails",
    "django", "kafka", "pandas", "outlook", "copilot", "claude", "mistral", "perplexity", "stripe", "snowflake",
}
_PRODUCT_PRE_CUE_RE = re.compile(
    r"\b(?:in|inside|into|via|using|with|on|open(?:ed|ing|s)?|switch(?:ed|ing)? to|mov(?:e|ed|ing) to|install(?:ed)?|"
    r"running|runs? on|built (?:in|on|with)|written in|port(?:ed)? to)\s+(?:the\s+)?$", re.IGNORECASE)
_PRODUCT_POST_CUE_RE = re.compile(
    r"^\s*(?:v?\d[\w.]*|cli|sdk|api|app|plugin|extension|ticket|tickets|board|doc|docs|workspace|tab|window|agent|"
    r"agents|ide|mcp|rules|config|dashboard|channel|sheet|sheets|file|files|template|automation|models?|bot|bots|"
    r"message|messages|thread|threads|repo|repos|script|scripts|prompt|prompts)\b", re.IGNORECASE)
MONTH_RE = re.compile(
    r"\b(?:January|February|March|April|June|July|August|September|October|November|December)\b"
    r"|\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s*\d"
    r"|\b(?:\d{1,2}\s+)?May\b(?=\s*\d)|\b\d{1,2}(?:st|nd|rd|th)?\s+May\b",
)
WEEKDAY_RE = re.compile(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?\b")
NUMBER_RE = re.compile(r"\d+(?:[.,:]\d+)*[a-zA-Z%]*")
CURRENCY_RE = re.compile(r"[$€£¥]\s?\d|\d\s?(?:USD|EUR|GBP|INR|dollars|bucks|euros|pounds)\b|\d+\s?%")
PATH_RE = re.compile(r"(?:(?<=\s)|^|(?<=[(`\"']))(?:~?/|\./|[A-Za-z]:\\)[\w./\\-]{2,}|\b[\w-]+\.(?:py|js|ts|tsx|jsx|yaml|yml|json|md|txt|csv|sh|go|rs|toml|sql|html|css|pdf|png|jpg|mp4|wav|env|lock|cfg|ini)\b")
FLAG_RE = re.compile(r"(?:(?<=\s)|^|(?<=`))-{1,2}[A-Za-z][\w-]*")
ERROR_RE = re.compile(r"\b\w+(?:Error|Exception|Warning)\b|\btraceback\b|\bstack ?trace\b|\bsegfault\b|\b[A-Z][A-Z0-9]{1,}_[A-Z0-9_]{2,}\b|\bnull pointer\b|\b(?:4|5)\d\d\b")
CODE_RE = re.compile(r"`[^`\n]{2,}`")
NUMBER_WORD_RE = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|"
    r"hundred|thousand|million|billion|dozen|half a)\s+[a-z][\w-]*", re.IGNORECASE)
CAP_TOKEN_RE = re.compile(r"[A-Za-z][\w'’-]*")
CAMEL_RE = re.compile(r"[a-z][A-Z]")

APHORISM_VERB_RE = re.compile(
    r"\b(?:is|are|isn't|aren't|it's|that's|beats|wins|matters|means|requires|becomes|always|never|equals|compounds)\b",
    re.IGNORECASE)
PRONOUN_START = {"i", "i'm", "i've", "i'd", "we", "we're", "you", "you're", "he", "she", "they", "it", "it's",
                 "this", "that", "these", "those", "there", "here", "my", "our", "your", "and", "but", "so"}
FIRST_PERSON_RE = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|me|my|mine|we|we're|we've|us|our)\b", re.IGNORECASE)
STOPWORDS = set(
    "the a an and or but so if of to in on for with at by from as is are was were be been it its this that these "
    "those i me my you your we our they them their he she his her not no do does did have has had can could will "
    "would should just very about into out up down over what which who when how why all any some more most much "
    "many than too here there then now".split())

# --------------------------------------------------------------------------- folding with position map


def _fold_with_map(text: str) -> tuple[str, list[int]]:
    """Fold `text` (NFKC + quote/dash folding per common.fold_punct, applied per character) and return the
    folded string plus `origin`, where origin[k] is the index in `text` that produced folded char k."""
    out: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(text):
        f = unicodedata.normalize("NFKC", ch)
        f = QUOTE_MAP.get(f, f) if len(f) == 1 else "".join(QUOTE_MAP.get(c, c) for c in f)
        for c in f:
            out.append(c)
            origin.append(i)
    return "".join(out), origin


class _Doc:
    """Original text plus its folded view; all regexes run on `folded`, spans map back to `text`."""

    def __init__(self, text: str):
        self.text = text
        self.folded, self.origin = _fold_with_map(text)
        # nonblank line ranges in folded coordinates: (start, end) with end exclusive (no newline)
        self.line_ranges: list[tuple[int, int]] = []
        pos = 0
        for ln in self.folded.split("\n"):
            end = pos + len(ln)
            if ln.strip():
                self.line_ranges.append((pos, end))
            pos = end + 1

    def span(self, a: int, b: int) -> tuple[int, int]:
        """Map a folded [a, b) span to original-text [start, end)."""
        if not self.origin or b <= a:
            return (0, 0)
        a = max(0, min(a, len(self.origin) - 1))
        b = max(a + 1, min(b, len(self.origin)))
        return (self.origin[a], self.origin[b - 1] + 1)

    def evidence(self, a: int, b: int, why: str, **extra: Any) -> dict:
        s, e = self.span(a, b)
        item = {
            "span": self.text[s:e],
            "why": why,
            "line": self.folded.count("\n", 0, a) + 1,
            "start": s,
            "end": e,
        }
        item.update(extra)
        return item

    def line1_range(self) -> tuple[int, int] | None:
        return self.line_ranges[0] if self.line_ranges else None

    def tail2_range(self) -> tuple[int, int] | None:
        if not self.line_ranges:
            return None
        return (self.line_ranges[-2][0] if len(self.line_ranges) >= 2 else self.line_ranges[-1][0],
                self.line_ranges[-1][1])


# --------------------------------------------------------------------------- lexicon / pattern compilation

_LEX_CACHE: dict[int, tuple[Any, dict]] = {}
_PAT_CACHE: dict[int, tuple[Any, dict]] = {}


def _flags(spec: str | None) -> int:
    f = re.MULTILINE
    spec = "i" if spec is None else str(spec)
    if "i" in spec:
        f |= re.IGNORECASE
    if "s" in spec:
        f |= re.DOTALL
    if "x" in spec:
        f |= re.VERBOSE
    return f


def _phrase_regex(phrase: str) -> str:
    """Literal phrase -> regex with word boundaries where the phrase starts/ends alphanumerically."""
    phrase = fold_punct(phrase).strip()
    parts = [re.escape(p) for p in re.split(r"\s+", phrase) if p]
    body = r"\s+".join(parts)
    lead = r"(?<![A-Za-z0-9])" if phrase and phrase[0].isalnum() else ""
    trail = r"(?![A-Za-z0-9])" if phrase and phrase[-1].isalnum() else ""
    return lead + body + trail


def _compile_entry(entry: Any) -> tuple[dict, re.Pattern] | None:
    if isinstance(entry, str):
        entry = {"phrase": entry, "note": ""}
    if not isinstance(entry, dict) or not entry.get("phrase"):
        return None
    if entry.get("regex"):
        rx = re.compile(str(entry["phrase"]), _flags(entry.get("flags", "i")))
    else:
        rx = re.compile(_phrase_regex(str(entry["phrase"])), _flags("i"))
    return entry, rx


def _compiled_lexicon(lexicon: dict) -> dict[str, list[tuple[dict, re.Pattern]]]:
    key = id(lexicon)
    cached = _LEX_CACHE.get(key)
    if cached and cached[0] is lexicon:
        return cached[1]
    tiers = (lexicon or {}).get("tiers", {}) or {}
    out: dict[str, list[tuple[dict, re.Pattern]]] = {}
    for tier, entries in tiers.items():
        comp = []
        for e in entries or []:
            c = _compile_entry(e)
            if c:
                comp.append(c)
        out[tier] = comp
    extra = []
    for e in (lexicon or {}).get("user_tells", []) or []:
        c = _compile_entry(e)
        if c:
            c[0].setdefault("note", "user tell")
            extra.append(c)
    out.setdefault("t1", [])
    out["t1"] = out["t1"] + extra
    _LEX_CACHE[key] = (lexicon, out)
    return out


def _compiled_patterns(patterns: dict | list) -> dict[str, list[tuple[dict, re.Pattern]]]:
    key = id(patterns)
    cached = _PAT_CACHE.get(key)
    if cached and cached[0] is patterns:
        return cached[1]
    plist = patterns.get("patterns", []) if isinstance(patterns, dict) else (patterns or [])
    out: dict[str, list[tuple[dict, re.Pattern]]] = {}
    for p in plist:
        if not isinstance(p, dict) or not p.get("regex") or not p.get("id"):
            continue
        check = p.get("check") or str(p["id"]).split(".")[0]
        try:
            rx = re.compile(str(p["regex"]), _flags(p.get("flags", "i")))
        except re.error as ex:  # programmer error in patterns.yaml; surface loudly
            raise ValueError(f"patterns.yaml: bad regex in {p['id']}: {ex}") from ex
        out.setdefault(check, []).append((p, rx))
    _PAT_CACHE[key] = (patterns, out)
    return out


# --------------------------------------------------------------------------- matching helpers


def _iter_matches(rx: re.Pattern, folded: str, lo: int, hi: int, anchored: bool = False):
    if anchored:
        m = rx.match(folded, lo, hi)
        if m and m.end() > m.start():
            yield m
        return
    for m in rx.finditer(folded, lo, hi):
        if m.end() > m.start():
            yield m


def _lexicon_hits(doc: _Doc, comp: list[tuple[dict, re.Pattern]], lo: int, hi: int, why_prefix: str,
                  anchored: bool = False, rank: int = 2) -> list[dict]:
    hits = []
    for entry, rx in comp:
        for m in _iter_matches(rx, doc.folded, lo, hi, anchored):
            note = entry.get("note") or ""
            shown = m.group(0) if entry.get("regex") else str(entry["phrase"])  # regexes are unreadable in feedback
            why = f"{why_prefix}: '{shown}'" + (f" ({note})" if note else "")
            hits.append(doc.evidence(m.start(), m.end(), why, phrase=str(entry["phrase"]), _rank=rank))
    return hits


def _pattern_hits(doc: _Doc, comp: list[tuple[dict, re.Pattern]], lo: int, hi: int,
                  sub_filter: set[str] | None = None) -> list[dict]:
    hits = []
    for p, rx in comp:
        sub = str(p["id"]).split(".", 1)[1] if "." in str(p["id"]) else str(p["id"])
        if sub_filter is not None and sub not in sub_filter:
            continue
        for m in _iter_matches(rx, doc.folded, lo, hi):
            kfp = p.get("known_false_positive")
            hits.append(doc.evidence(
                m.start(), m.end(), str(p.get("explanation") or p["id"]),
                pattern=str(p["id"]), sub=sub, known_false_positive=bool(kfp), _rank=0 if kfp else 1))
    return hits


def _dedupe(hits: list[dict]) -> list[dict]:
    """Keep non-overlapping hits: leftmost first; at the same start pattern-with-KFP > pattern > lexicon
    (so the hit that can carry jury_override_allowed survives), then longest."""
    hits = sorted(hits, key=lambda h: (h["start"], h.get("_rank", 2), -(h["end"] - h["start"])))
    kept: list[dict] = []
    last_end = -1
    for h in hits:
        if h["start"] < last_end:
            continue
        kept.append(h)
        last_end = h["end"]
    return kept


def _strip_internal(hits: list[dict]) -> list[dict]:
    return [{k: v for k, v in h.items() if not k.startswith("_")} for h in hits]


def _result(cls: str, passed: bool, evidence: list[dict], **extra: Any) -> dict:
    r = {"class": cls, "pass": passed, "evidence": _strip_internal(evidence) if not passed else [],
         "downgraded": False}
    r.update(extra)
    return r


def _mark_override(res: dict, hits: list[dict], forced: bool = False) -> None:
    """Record on a failing P8/P10/P12/P17 result whether a jury may override it: true only when a hit came from a
    pattern that declares a known_false_positive (or `forced`); false for lexicon-only and heuristic-only hits, so
    aggregate.py routes those to the feedback packet instead of spawning a jury."""
    if res.get("pass"):
        return
    res["jury_override_allowed"] = bool(forced or any(h.get("known_false_positive") for h in hits))


# --------------------------------------------------------------------------- individual checks


def _check_bait(doc: _Doc, lex: dict, pats: dict) -> dict:
    hits = _dedupe(_lexicon_hits(doc, lex.get("bait", []), 0, len(doc.folded), "engagement bait")
                   + _pattern_hits(doc, pats.get("P7_bait", []), 0, len(doc.folded)))
    return _result("hard", not hits, hits, count=len(hits))


def _check_opener(doc: _Doc, lex: dict, pats: dict) -> dict:
    rng = doc.line1_range()
    if rng is None:
        return _result("hard", True, [], line1="")
    lo, hi = rng
    # skip leading emoji / quotes / bullets so lexicon openers anchor on the first word
    lo2 = lo
    while lo2 < hi and not doc.folded[lo2].isalnum():
        lo2 += 1
    hits = _pattern_hits(doc, pats.get("P8_opener", []), lo, hi)
    hits += _lexicon_hits(doc, lex.get("openers", []), lo2, hi, "stale opener on line 1", anchored=True)
    hits = _dedupe(hits)
    res = _result("hard", not hits, hits, line1=doc.text[doc.span(lo, hi)[0]:doc.span(lo, hi)[1]])
    _mark_override(res, hits)
    return res


def _check_residue(doc: _Doc, lex: dict, pats: dict) -> dict:
    hits = _dedupe(_lexicon_hits(doc, lex.get("residue", []), 0, len(doc.folded), "chatbot residue")
                   + _pattern_hits(doc, pats.get("P9_residue", []), 0, len(doc.folded)))
    return _result("hard", not hits, hits, count=len(hits))


def _check_contrast(doc: _Doc, pats: dict) -> dict:
    hits = _dedupe(_pattern_hits(doc, pats.get("P10_contrast_flip", []), 0, len(doc.folded)))
    res = _result("hard", not hits, hits, count=len(hits))
    _mark_override(res, hits)
    return res


def _tier_hits(doc: _Doc, lex: dict) -> dict[str, list[dict]]:
    """Lexicon hits for t1/t2/t3/claude, de-duplicated across tiers (longest span wins, then claude > t1 > t2 > t3)."""
    allh: list[dict] = []
    for tier in LEXICON_TIERS:
        for h in _lexicon_hits(doc, lex.get(tier, []), 0, len(doc.folded), f"{tier} tell",
                               rank=TIER_RANK[tier]):
            h["tier"] = tier
            allh.append(h)
    out: dict[str, list[dict]] = {t: [] for t in LEXICON_TIERS}
    for h in _dedupe(allh):
        out[h["tier"]].append(h)
    return out


def _check_cluster(tier_hits: dict[str, list[dict]]) -> dict:
    n1, n2, n3, nc = (len(tier_hits[t]) for t in LEXICON_TIERS)
    total = n1 + n2 + n3
    reasons = []
    if n1 >= CLUSTER_T1:
        reasons.append(f"{n1} t1 hits (>= {CLUSTER_T1})")
    if total >= CLUSTER_TOTAL:
        reasons.append(f"{total} hits across t1+t2+t3 (>= {CLUSTER_TOTAL})")
    if nc >= CLUSTER_CLAUDE:
        reasons.append(f"{nc} Claude-tic hits (>= {CLUSTER_CLAUDE})")
    evidence = [h for t in ("claude", "t1", "t2", "t3") for h in tier_hits[t]]
    res = _result("hard", not reasons, evidence,
                  counts={"t1": n1, "t2": n2, "t3": n3, "claude": nc, "total": total},
                  rule=reasons, **{t: [h["span"] for h in tier_hits[t]] for t in LEXICON_TIERS})
    return res


def _final_sentence(s: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|(?<=[.!?])$", s) if p and p.strip()]
    return parts[-1] if parts else ""


def _clean_line(s: str) -> str:
    s = HASHTAG_RE.sub(" ", s)
    s = EMOJI_RE.sub(" ", s)
    s = re.sub(r"[♻️️]", " ", s)
    return s.strip()


def _aphorism_flag(doc: _Doc, sentence_folded: str, lo: int, hi: int) -> dict | None:
    """Aphoristic-restatement heuristic: short impersonal 'X is Y.' with no specific
    (research-ai-tells 2.8 [AE])."""
    sent = _clean_line(sentence_folded).strip(" \"'")
    if not sent or sent.endswith("?"):
        return None
    toks = [t.lower() for t in words(sent)]
    if not (3 <= len(toks) <= 10):
        return None
    if toks[0] in PRONOUN_START or FIRST_PERSON_RE.search(sent):
        return None
    if not APHORISM_VERB_RE.search(sent):
        return None
    if _find_specifics(sent):  # sentence-initial capital is not a proper noun; anything else is a specific
        return None
    m = re.search(re.escape(sent[:20]), doc.folded[lo:hi])
    a = lo + m.start() if m else lo
    return doc.evidence(a, min(hi, a + len(sent)), "aphoristic closer: short impersonal generalisation with no specific")


def _check_closer(doc: _Doc, lex: dict, pats: dict) -> dict:
    rng = doc.tail2_range()
    if rng is None:
        return _result("hard", True, [])
    lo, hi = rng
    hits = _dedupe(_pattern_hits(doc, pats.get("P12_closer", []), lo, hi)
                   + _lexicon_hits(doc, lex.get("closers", []), lo, hi, "moralizing/summarizing closer"))
    flags: list[dict] = []
    for (a, b) in doc.line_ranges[-2:]:
        fs = _final_sentence(doc.folded[a:b])
        f = _aphorism_flag(doc, fs, a, b)
        if f:
            flags.append(f)
    if len(doc.line_ranges) >= 3:
        first = doc.folded[doc.line_ranges[0][0]:doc.line_ranges[0][1]]
        last = doc.folded[doc.line_ranges[-1][0]:doc.line_ranges[-1][1]]
        cw = lambda s: {t.lower() for t in words(_clean_line(s)) if len(t) >= 3 and t.lower() not in STOPWORDS}
        a_, b_ = cw(first), cw(last)
        shared = a_ & b_
        if len(shared) >= 3 and len(shared) / max(1, len(a_ | b_)) >= 0.4:
            flags.append(doc.evidence(doc.line_ranges[-1][0], doc.line_ranges[-1][1],
                                      f"closer restates the opener (shared: {', '.join(sorted(shared))})"))
    if hits:
        res = _result("hard", False, hits + flags, regex_hits=len(hits), heuristic_flags=len(flags))
        _mark_override(res, hits)
        return res
    if flags:
        return _result("flag", False, flags, regex_hits=0, heuristic_flags=len(flags), jury_override_allowed=False)
    return _result("hard", True, [], regex_hits=0, heuristic_flags=0)


def _is_sentence_initial(s: str, i: int) -> bool:
    """True when the token starting at s[i] begins a sentence/line (position 0 for the P13 proper-noun rule)."""
    j = i - 1
    while j >= 0:
        c = s[j]
        if c == "\n":
            return True
        if c.isalnum():
            return False
        if c in ".!?:":
            return True
        if c in ",;)":
            return False
        j -= 1
    return True


def _product_cue(w: str, start: int, end: int) -> bool:
    """An ambiguous product name counts only next to a tool cue ("in Cursor") or an artefact / version token
    ("Linear ticket", "Cursor 2.0")."""
    return bool(_PRODUCT_PRE_CUE_RE.search(w[max(0, start - 40):start]) or _PRODUCT_POST_CUE_RE.match(w[end:end + 24]))


def _find_specifics(s: str, mid_only: bool = True) -> list[tuple[int, int, str]]:
    """Return (start, end, kind) for every specific in folded string `s` (hashtags/emoji/URLs masked first)."""
    w = s
    for rx in (URL_RE, HASHTAG_RE, EMOJI_RE):
        w = rx.sub(lambda m: " " * len(m.group(0)), w)
    found: list[tuple[int, int, str]] = []
    for m in URL_RE.finditer(s):
        found.append((m.start(), m.end(), "url"))
    for m in MENTION_RE.finditer(s):
        found.append((m.start(), m.end(), "mention"))
    for rx, kind in ((NUMBER_RE, "number"), (CURRENCY_RE, "currency_or_percent"), (MONTH_RE, "month"),
                     (WEEKDAY_RE, "weekday"), (PATH_RE, "path"), (FLAG_RE, "cli_flag"), (ERROR_RE, "error_like"),
                     (CODE_RE, "code"), (NUMBER_WORD_RE, "number_word")):
        for m in rx.finditer(w):
            found.append((m.start(), m.end(), kind))
    for m in CAP_TOKEN_RE.finditer(w):
        tok = m.group(0)
        base = re.sub(r"['’]s$", "", tok)
        low = base.lower()
        if low in PRODUCT_NAMES:
            found.append((m.start(), m.end(), "product"))
            continue
        if low in AMBIGUOUS_PRODUCT_NAMES and _product_cue(w, m.start(), m.end()):
            found.append((m.start(), m.end(), "product"))
            continue
        if len(base) < 2 or not tok[0].isupper():
            continue
        if base.upper() in GENERIC_CAPS or low in PRONOUN_FORMS:
            continue
        if CAMEL_RE.search(base):
            found.append((m.start(), m.end(), "proper_noun"))
            continue
        if mid_only and _is_sentence_initial(w, m.start()):
            continue
        found.append((m.start(), m.end(), "proper_noun"))
    found.sort()
    return found


def _min_words(platform: str, cfg: dict) -> int:
    override = ((cfg or {}).get("ai_tells") or {}).get("specifics_min_words")
    if isinstance(override, dict):
        return int(override.get(platform, SPECIFICS_MIN_WORDS.get(platform, 40)))
    if isinstance(override, (int, float)):
        return int(override)
    return SPECIFICS_MIN_WORDS.get(platform, 40)


def _check_specifics(doc: _Doc, platform: str, cfg: dict) -> dict:
    n_words = len(words(doc.text))
    floor = _min_words(platform, cfg)
    found = _find_specifics(doc.folded)
    specifics = [doc.evidence(a, b, kind) for a, b, kind in found][:25]
    for s_ in specifics:
        s_["kind"] = s_.pop("why")
    if n_words == 0:
        return _result("hard", False, [doc.evidence(0, 0, "empty post: no words at all")],
                       words=0, min_words=floor, specifics=[])
    if n_words > floor and not found:
        a, b = doc.line1_range() or (0, 0)
        ev = doc.evidence(a, b, f"{n_words} words with zero specifics (no number, $/%, date, proper noun after "
                                f"position 0, product name, file path or error string); floor for {platform} is "
                                f"{floor} words")
        return _result("hard", False, [ev], words=n_words, min_words=floor, specifics=[])
    return _result("hard", True, [], words=n_words, min_words=floor, specifics=specifics)


def _check_lists(doc: _Doc, pats: dict, meta: dict) -> dict:
    raw = _pattern_hits(doc, pats.get("P17_lists", []), 0, len(doc.folded))
    # list forms are distinct tells (emoji bullets AND templated lines can both be true): dedupe per sub;
    # tricolon forms describe the same triple: dedupe across the group so one triple counts once.
    hard_hits: list[dict] = []
    for sub in sorted(P17_HARD_SUBS):
        hard_hits += _dedupe([h for h in raw if h.get("sub") == sub])
    tally_hits = _dedupe([h for h in raw if h.get("sub") in P17_TALLY_SUBS])
    hits = sorted(hard_hits + tally_hits, key=lambda h: h["start"])
    tricolons = len(tally_hits)
    list_forms = sorted({h["sub"] for h in hard_hits})
    if hard_hits or tricolons >= TRICOLON_HARD:
        cls, passed = "hard", False
    elif tricolons == 1:
        cls, passed = "soft", False
    else:
        cls, passed = "soft", True
    res = _result(cls, passed, hits, tricolons=tricolons, list_forms=list_forms)
    device = str(((meta or {}).get("assignment") or {}).get("device") or "")
    _mark_override(res, hits, forced=bool(tally_hits) and device == "rule_of_three_escalation")
    return res


def _check_hedges(doc: _Doc, lex: dict) -> dict:
    hits = _dedupe(_lexicon_hits(doc, lex.get("hedges", []), 0, len(doc.folded), "hedge"))
    return _result("soft", len(hits) < HEDGE_SOFT, hits, count=len(hits), threshold=HEDGE_SOFT)


def _check_clickbait(doc: _Doc, lex: dict, pats: dict, platform: str) -> dict:
    hits = _dedupe(_lexicon_hits(doc, lex.get("clickbait", []), 0, len(doc.folded), "clickbait framing")
                   + _pattern_hits(doc, pats.get("P19_clickbait", []), 0, len(doc.folded)))
    cls = "hard" if platform == "x" else "soft"
    return _result(cls, not hits, hits, count=len(hits))


def _check_misc(doc: _Doc, pats: dict) -> dict:
    subs: dict[str, dict] = {}
    for p, _rx in pats.get("P20_misc", []):
        sub = str(p["id"]).split(".", 1)[1]
        subs.setdefault(sub, {"pass": True, "evidence": []})
    raw = _pattern_hits(doc, pats.get("P20_misc", []), 0, len(doc.folded))
    hits: list[dict] = []
    for sub in sorted({h["sub"] for h in raw}):  # each sub-pattern is its own flag: dedupe per sub
        hits += _dedupe([h for h in raw if h["sub"] == sub])
    hits.sort(key=lambda h: h["start"])
    for h in hits:
        s = subs.setdefault(h["sub"], {"pass": True, "evidence": []})
        s["pass"] = False
        s["evidence"].append({k: v for k, v in h.items() if not k.startswith("_")})
    res = _result("soft", not hits, hits, sub=subs, fired=sorted({h["sub"] for h in hits}))
    return res


# --------------------------------------------------------------------------- downgrade and entry point


def apply_downgrade(checks: dict[str, dict], cfg: dict, base_rates: dict | None) -> None:
    """Base-rate downgrade (contracts §5): for ids in cfg.base_rate_downgrade.applies_to (never the `never`
    list) whose base rate exceeds the threshold, hard -> flag and soft -> advisory, recording class_original,
    downgraded and base_rate. Idempotent; tier0 reuses it for P6/P14/P16. Mutates `checks` in place."""
    br = (cfg or {}).get("base_rate_downgrade") or {}
    threshold = float(br.get("threshold", 0.25))
    applies = set(br.get("applies_to") or [])
    never = set(br.get("never") or [])
    rates = base_rates or {}
    mapping = {"hard": "flag", "soft": "advisory"}
    for cid, res in checks.items():
        if cid in never or cid not in applies:
            continue
        rate = rates.get(cid)
        if rate is None or float(rate) <= threshold:
            continue
        new = mapping.get(res["class"])
        if new:
            res["class_original"] = res["class"]
            res["class"] = new
            res["downgraded"] = True
            res["base_rate"] = float(rate)


_apply_downgrade = apply_downgrade  # backwards-compatible private alias


def run_checks(text: str, platform: str, meta: dict | None, cfg: dict | None, lexicon: dict | None,
               patterns: dict | list | None, base_rates: dict | None) -> dict:
    """Run every AI-tell check on `text`.

    Returns {"checks": {check_id: result}, "hits": {"t1": [...], "t2": [...], "t3": [...], "claude": [...]}}.
    Each result: {"class": hard|soft|flag|advisory, "pass": bool, "evidence": [{"span", "why", "line", ...}],
    "downgraded": bool, ...check-specific fields}. A downgraded result also carries "class_original" and
    "base_rate". A failing P8/P10/P12/P17 carries "jury_override_allowed", true only when a hit came from a
    pattern declaring a known_false_positive, or for P17 when the candidate declares device
    rule_of_three_escalation. Lexicon-only and heuristic-only hits never earn a jury.
    """
    meta = meta or {}
    cfg = cfg or {}
    platform = (platform or meta.get("platform") or "linkedin").lower()
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    doc = _Doc(text)
    lex = _compiled_lexicon(lexicon or {})
    pats = _compiled_patterns(patterns or {})
    tier_hits = _tier_hits(doc, lex)

    checks = {
        "P7_bait": _check_bait(doc, lex, pats),
        "P8_opener": _check_opener(doc, lex, pats),
        "P9_residue": _check_residue(doc, lex, pats),
        "P10_contrast_flip": _check_contrast(doc, pats),
        "P11_cluster": _check_cluster(tier_hits),
        "P12_closer": _check_closer(doc, lex, pats),
        "P13_specifics": _check_specifics(doc, platform, cfg),
        "P17_lists": _check_lists(doc, pats, meta),
        "P18_hedges": _check_hedges(doc, lex),
        "P19_clickbait": _check_clickbait(doc, lex, pats, platform),
        "P20_misc": _check_misc(doc, pats),
    }
    apply_downgrade(checks, cfg, base_rates)
    hits = {t: [{k: v for k, v in h.items() if k not in ("_rank", "tier", "why")} for h in tier_hits[t]]
            for t in LEXICON_TIERS}
    return {"checks": checks, "hits": hits}


def summarize(checks: dict[str, dict]) -> dict:
    """Group failing check ids by class (after downgrade)."""
    out = {"hard_fails": [], "soft_fails": [], "flags": [], "advisory": []}
    key = {"hard": "hard_fails", "soft": "soft_fails", "flag": "flags", "advisory": "advisory"}
    for cid, r in checks.items():
        if not r.get("pass", True):
            out[key.get(r.get("class"), "flags")].append(cid)
    return out


# --------------------------------------------------------------------------- CLI


def _human(report: dict) -> str:
    lines = [f"{report['file']}  platform={report['platform']}  words={report['words']}  chars={report['chars']}"]
    for cid, r in report["checks"].items():
        status = "pass" if r["pass"] else "FAIL"
        tag = r["class"] + (f" (was {r['class_original']})" if r.get("downgraded") else "")
        extra = " jury-override-allowed" if r.get("jury_override_allowed") else ""
        lines.append(f"  {cid:<18} {status:<4} [{tag}]{extra}")
        for ev in r.get("evidence", [])[:6]:
            span = ev["span"].replace("\n", " / ")
            lines.append(f"      L{ev.get('line', '?')}: \"{span[:90]}\"  <- {ev['why'][:100]}")
    s = report["summary"]
    lines.append(f"hard: {s['hard_fails']}  soft: {s['soft_fails']}  flags: {s['flags']}  advisory: {s['advisory']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic AI-tell checks (P7-P13, P17-P20) for one post file.")
    ap.add_argument("file", help="candidate .md (front matter + text) or plain .txt; '-' reads stdin")
    ap.add_argument("--platform", choices=["linkedin", "x"], help="platform (default: front matter `platform`)")
    ap.add_argument("--json", action="store_true", help="JSON output (default is a human-readable summary)")
    ap.add_argument("--lexicon", help="lexicon YAML (default style/lexicon.yaml)")
    ap.add_argument("--patterns", help="patterns YAML (default <rubric dir>/patterns.yaml)")
    ap.add_argument("--base-rates", help="JSON file of {check_id: rate}; 'none' disables; default style/profile.json")
    args = ap.parse_args(argv)

    try:
        if args.file == "-":
            meta, body = {}, sys.stdin.read()
        else:
            p = Path(args.file).expanduser()
            if not p.is_absolute() and not p.exists() and (common.ROOT / p).exists():
                p = common.ROOT / p
            if not p.exists() or not p.is_file():
                error(f"file not found: {args.file}", True)
            meta, body = read_front_matter_file(p.resolve())
    except UnicodeDecodeError:
        error(f"cannot decode {args.file} as UTF-8", True)
        return 0
    platform = args.platform or str((meta or {}).get("platform") or "").lower()
    if platform not in ("linkedin", "x"):
        error("--platform linkedin|x is required (no `platform` in front matter)", True)
        return 0
    try:
        cfg = load_config()
    except FileNotFoundError:
        cfg = {}
    try:
        lexicon = load_yaml(args.lexicon) if args.lexicon else load_lexicon()
    except FileNotFoundError:
        error(f"lexicon not found: {args.lexicon}", True)
        return 0
    try:
        patterns = load_yaml(args.patterns) if args.patterns else load_patterns()
    except FileNotFoundError:
        error(f"patterns not found: {args.patterns}", True)
        return 0
    base_rates: dict | None
    if args.base_rates == "none":
        base_rates = None
    elif args.base_rates:
        bp = Path(args.base_rates)
        if not bp.exists():
            error(f"base rates file not found: {args.base_rates}", True)
            return 0
        raw = json.loads(bp.read_text(encoding="utf-8"))
        base_rates = raw.get("base_rates", raw) if isinstance(raw, dict) else None
    else:
        prof = load_profile()
        base_rates = (prof or {}).get("base_rates") if prof else None

    text = body.rstrip("\n")
    out = run_checks(text, platform, meta or {}, cfg, lexicon, patterns, base_rates)
    report = {
        "ok": True,
        "file": rel(args.file) if args.file != "-" else "-",
        "platform": platform,
        "chars": len(text),
        "words": len(words(text)),
        "lexicon_version": (lexicon or {}).get("lexicon_version"),
        "checks": out["checks"],
        "hits": out["hits"],
        "summary": summarize(out["checks"]),
    }
    emit(report, args.json, human=_human(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
