#!/usr/bin/env python3
"""Per-post stylometric features (contracts.md section 3).

`features(text, platform, lang, lexicon, patterns)` returns the feature dict with every key present.
English-only features (`function_words`, `lexicon.contraction_rate`, `hedges`, `fk_grade`, `ai_tells`) are
`None` when `lang != "en"`.

Definitions, all deterministic and stdlib only:
- sentences: `common.sentences`; lines: `common.nonblank_lines`; paragraphs: blocks split on blank lines.
- `line_words.rhythm`: sentences-per-paragraph joined by "/" (Ship 30 notation).
- `sent_words.sd` is the population standard deviation; `cv = sd / mean` (burstiness proxy).
- `hook.cut140_ends_sentence`: a sentence boundary (. ! ? ...) falls inside the first 140 chars, or the post
  is shorter than 140 chars so nothing is cut. Same for 210.
- `pov.*_per100`: I/me/my/mine/I'm/I've/I'd/I'll vs you/your/you're/yours vs we/our/us/we're per 100 words;
  `dominant` is the largest group, "third" when all are zero, "mixed" when the top two are within 25 %.
- `tense_past_ratio` (APPROXIMATE): (-ed tokens + was/were/had/did) over verb-ish tokens (those plus present
  auxiliaries and -ing tokens).
- `punct_per_1k`: counts per 1,000 chars; periods inside numbers/versions and ellipsis dots are not periods;
  `missing_terminal_period_ratio` = fraction of nonblank lines not ending in . ! ? or an ellipsis.
- `lexicon.specificity_per100` = (numerals + proper nouns + $ figures + % figures + version strings) per 100
  words, where numerals exclude numbers already counted as $/%/version. Proper nouns = capitalised tokens
  that are not the first token of a sentence or line and not in a small stoplist.
- `lexicon.contraction_rate`: tokens ending in 't 're 've 'll 'd 'm (plus it's/that's/let's forms) / words.
- `function_words`: relative frequency over `common.FUNCTION_WORDS`.
- `ai_tells`: verbatim spans matched per lexicon tier (word-boundary, case-insensitive) and the ids of
  matching `patterns.yaml` regexes; empty lists when no lexicon or patterns are passed.
- `tricolons`: "A, B(,) and C" inside one sentence, plus triples of short parallel one-line fragments.
- `imperatives`: sentences whose first word, past any ordinal list marker, is a base verb from a small list.
- `questions`: sentences ending in "?".
- `fk_grade`: Flesch-Kincaid grade with a vowel-group syllable heuristic.
- `pct_single_sentence_paras` (beyond section 3): fraction of paragraphs holding exactly one sentence.

CLI: `stylometry.py <post.md|txt> [--platform P] [--lang L] [--json]` prints the features of one post;
`stylometry.py --corpus [--root R]` (re)writes corpus/features/<id>.json for train/self posts and
corpus/heldout/features/<id>.json for heldout posts. `--root` (or env POSTSMITH_ROOT) selects the root.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import (  # noqa: E402
    EMOJI_RE, FUNCTION_WORDS, HASHTAG_RE, HEDGES, MENTION_RE, URL_RE, emit, fold_punct, median, nonblank_lines, quantile,
    sentences, split_front_matter, words,
)

# --------------------------------------------------------------------------- constants

PARA_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
TERMINAL_RE = re.compile(r"[.!?…]+[\"'”’)\]]*\s*$")
BOUNDARY_RE = re.compile(r"[.!?…][\"'”’)\]]*(?:\s|$)")
BULLET_RE = re.compile(r"^\s*(?:[-*•▪‣◦]|\d{1,3}[.)])\s+")
ARROW_RE = re.compile(r"→|←|⇒|➡|↑|↓|->|=>")
NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w.])")
DOLLAR_RE = re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d+)?\s?[kKmMbB]?(?![\w.])")
PERCENT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s?%")
VERSION_RE = re.compile(r"\bv?\d+\.\d+(?:\.\d+)*\b", re.I)
PERIOD_RE = re.compile(r"(?<![\w.])\.(?!\.)|(?<=\w)\.(?![\w.])")
ELLIPSIS_RE = re.compile(r"\.{3,}|…")
QUOTE_RE = re.compile(r"[\"“”]")
ALLCAPS_RE = re.compile(r"^[A-Z][A-Z0-9'’\-]*$")
ED_RE = re.compile(r"^[a-z]{3,}ed$")
ING_RE = re.compile(r"^[a-z]{3,}ing$")
CONTRACTION_RE = re.compile(r"^[a-z]+'(t|re|ve|ll|d|m)$")
TRICOLON_RE = re.compile(
    r"\b[\w'’-]+(?:\s+[\w'’-]+){0,3}\s*,\s*[\w'’-]+(?:\s+[\w'’-]+){0,3}\s*,?\s+(?:and|or)\s+[\w'’-]+", re.I
)

I_WORDS = {"i", "me", "my", "mine", "i'm", "i've", "i'd", "i'll", "myself"}
YOU_WORDS = {"you", "your", "you're", "yours", "you've", "you'll", "you'd", "yourself"}
WE_WORDS = {"we", "our", "us", "ours", "we're", "we've", "we'll", "we'd", "ourselves"}
PAST_AUX = {"was", "were", "had", "did"}
PRESENT_AUX = {"is", "are", "am", "has", "have", "do", "does", "can", "will", "be"}
ED_EXCEPTIONS = {"need", "feed", "seed", "speed", "bleed", "breed", "deed", "reed", "weed", "shed", "bed", "red",
                 "led", "wed", "fed", "hundred", "naked", "wicked", "sacred", "indeed", "ahead", "instead", "unused"}
S_CONTRACTIONS = {"it's", "that's", "what's", "there's", "here's", "he's", "she's", "let's", "who's", "where's",
                  "how's", "when's", "everything's", "nothing's", "something's"}
PROPER_STOPLIST = {"i", "i'm", "i've", "i'd", "i'll", "a", "ok", "okay", "ps", "lol", "omg", "wtf", "fyi", "imo",
                   "btw", "tl", "dr", "the", "and", "but", "or"}
PROFANITY_RE = re.compile(
    r"(?<!\w)(?:fuck\w*|shit\w*|bullshit|damn\w*|crap|wtf|asshole\w*|bastard\w*|piss\w*|dick\w*|bloody|goddamn)(?!\w)",
    re.I,
)
IMPERATIVE_VERBS = {
    "stop", "start", "try", "think", "imagine", "remember", "forget", "don't", "do", "ask", "read", "write", "build",
    "ship", "go", "take", "make", "get", "let", "look", "watch", "check", "use", "keep", "consider", "notice", "tell",
    "give", "listen", "learn", "pick", "say", "share", "run", "put", "hire", "fire", "be", "avoid", "ignore", "never",
    "please", "call", "send", "pay", "buy", "sell", "skip", "delete", "add", "cut", "open", "close", "find", "come",
    "wait", "want", "know", "see", "hear", "feel", "pause", "test", "measure", "steal", "focus", "choose",
}
REGEX_META = set("\\()[]|*+?{}^$")

# --------------------------------------------------------------------------- small helpers


def _r(x: float | None, nd: int = 4) -> float | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return round(float(x), nd)


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def paragraphs(text: str) -> list[str]:
    """Blocks separated by one or more blank lines (whitespace-only lines count as blank)."""
    return [p.strip("\n") for p in PARA_SPLIT_RE.split(_normalize_newlines(text)) if p.strip()]


def syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    return max(1, n)


def _phrase_regex(phrase: str, is_regex: bool | None = None, flags: str | None = None) -> re.Pattern | None:
    """Word-boundary regex for a lexicon phrase. `is_regex` (lexicon `regex: true`) uses the phrase as a
    Python regex; when it is unknown, a phrase holding regex metacharacters is treated as one. `flags`:
    "" means case-sensitive."""
    phrase = phrase.strip()
    if not phrase:
        return None
    if is_regex is None:
        is_regex = any(ch in REGEX_META for ch in phrase)
    body = phrase if is_regex else r"\s+".join(re.escape(part) for part in phrase.split())
    re_flags = re.M | (0 if flags == "" else re.I)
    try:
        return re.compile(r"(?<!\w)(?:" + body + r")(?!\w)", re_flags)
    except re.error:
        return re.compile(r"(?<!\w)(?:" + re.escape(phrase) + r")(?!\w)", re_flags)


def _lexicon_entries(lexicon: dict | None, tier: str) -> list[tuple[str, bool | None, str | None]]:
    """(phrase, is_regex, flags) per entry of a lexicon tier. An entry is a string or
    {phrase, regex?, flags?}."""
    if not lexicon:
        return []
    tiers = lexicon.get("tiers") or {}
    out: list[tuple[str, bool | None, str | None]] = []
    for item in tiers.get(tier) or []:
        if isinstance(item, dict):
            phrase = item.get("phrase") or item.get("regex")
            is_regex = True if item.get("regex") is True or "phrase" not in item else None
            flags = item.get("flags")
            flags = None if flags is None else str(flags)
        else:
            phrase, is_regex, flags = item, None, None
        if phrase:
            out.append((str(phrase), is_regex, flags))
    return out


def cosine_distance(a: dict[str, float], b: dict[str, float]) -> float | None:
    """1 - cosine similarity over the union of keys; None when either vector is empty/zero."""
    if not a or not b:
        return None
    keys = set(a) | set(b)
    dot = sum(float(a.get(k, 0.0)) * float(b.get(k, 0.0)) for k in keys)
    na = math.sqrt(sum(float(v) ** 2 for v in a.values()))
    nb = math.sqrt(sum(float(v) ** 2 for v in b.values()))
    if na == 0 or nb == 0:
        return None
    return _r(1.0 - dot / (na * nb), 6)


# --------------------------------------------------------------------------- feature blocks


def _line_features(nb_lines: list[str], paras: list[str]) -> tuple[dict, list[int], list[int]]:
    counts = [len(words(ln)) for ln in nb_lines]
    sent_per_para = [max(1, len(sentences(p))) if p.strip() else 0 for p in paras]
    run = best = 0
    for p in paras:
        if len(nonblank_lines(p)) == 1:
            run += 1
            best = max(best, run)
        else:
            run = 0
    n = len(counts)
    block = {
        "median": _r(median(counts)),
        "q1": _r(quantile(counts, 0.25)),
        "q3": _r(quantile(counts, 0.75)),
        "max": max(counts) if counts else 0,
        "pct_le4": _r(_safe_div(sum(1 for c in counts if c <= 4), n)),
        "pct_one_word": _r(_safe_div(sum(1 for c in counts if c == 1), n)),
        "max_run_single_line_paras": best,
        "rhythm": "/".join(str(s) for s in sent_per_para),
    }
    return block, counts, sent_per_para


def _first_word(sentence: str) -> str:
    """The sentence's first actual word, lower case, past any ordinal list marker.

    A numbered step ("1) Go to LinkedIn.") tokenizes as ["1", "Go", ...], so taking token zero read every
    numbered imperative as a non-imperative and made `imperatives` zero for exactly the listicle authors the
    feature exists to describe. Bullets, arrows and emoji are already dropped by the word regex; a leading run
    of digits is the only marker that survives it.
    """
    for w in words(sentence):
        if w.isdigit():
            continue
        return w.lower()
    return ""


def _sentence_features(sents: list[str]) -> dict:
    counts = [len(words(s)) for s in sents]
    counts = [c for c in counts if c > 0] or counts
    n = len(counts)
    mean = statistics.fmean(counts) if counts else 0.0
    sd = statistics.pstdev(counts) if n > 1 else 0.0
    return {
        "mean": _r(mean),
        "sd": _r(sd),
        "cv": _r(_safe_div(sd, mean)),
        "max": max(counts) if counts else 0,
        "pct_le5": _r(_safe_div(sum(1 for c in counts if c <= 5), n)),
    }


def _cut_ends_sentence(text: str, cut: int) -> bool:
    if len(text) <= cut:
        return True
    return BOUNDARY_RE.search(text[:cut]) is not None


def _hook_features(text: str, nb_lines: list[str], paras: list[str]) -> dict:
    line1 = nb_lines[0] if nb_lines else ""
    first_para = paras[0] if paras else ""
    return {
        "line1_chars": len(line1.strip()),
        "line1_words": len(words(line1)),
        "chars_before_blank": len(first_para),
        "cut140_ends_sentence": _cut_ends_sentence(text, 140),
        "cut210_ends_sentence": _cut_ends_sentence(text, 210),
        "is_question": (sentences(line1) or [""])[0].rstrip().rstrip("\"'”’)").endswith("?"),
    }


def _pov_features(toks_lower: list[str]) -> dict:
    n = len(toks_lower)
    i = sum(1 for t in toks_lower if t in I_WORDS)
    you = sum(1 for t in toks_lower if t in YOU_WORDS)
    we = sum(1 for t in toks_lower if t in WE_WORDS)
    scores = {"first_singular": i, "second": you, "first_plural": we}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if ranked[0][1] == 0:
        dominant = "third"
    elif ranked[1][1] > 0 and ranked[0][1] < 1.25 * ranked[1][1]:
        dominant = "mixed"
    else:
        dominant = ranked[0][0]
    return {
        "i_per100": _r(_safe_div(100.0 * i, n)),
        "you_per100": _r(_safe_div(100.0 * you, n)),
        "we_per100": _r(_safe_div(100.0 * we, n)),
        "dominant": dominant,
    }


def _tense_past_ratio(toks_lower: list[str]) -> float:
    past = sum(1 for t in toks_lower if t in PAST_AUX or (ED_RE.match(t) and t not in ED_EXCEPTIONS))
    present = sum(1 for t in toks_lower if t in PRESENT_AUX or ING_RE.match(t))
    return _r(_safe_div(past, past + present))


def _punct_features(text: str, nb_lines: list[str]) -> dict:
    n_chars = len(text)
    per_1k = lambda c: _r(_safe_div(1000.0 * c, n_chars))  # noqa: E731
    no_ellipsis = ELLIPSIS_RE.sub(" ", text)
    missing = sum(1 for ln in nb_lines if not TERMINAL_RE.search(ln))
    return {
        "period": per_1k(len(PERIOD_RE.findall(no_ellipsis))),
        "comma": per_1k(text.count(",")),
        "exclaim": per_1k(text.count("!")),
        "question": per_1k(text.count("?")),
        "colon": per_1k(text.count(":")),
        "semicolon": per_1k(text.count(";")),
        "em_dash": per_1k(text.count("—")),
        "en_dash": per_1k(text.count("–")),
        "ellipsis": per_1k(len(ELLIPSIS_RE.findall(text))),
        "paren": per_1k(text.count("(")),
        "quote": per_1k(len(QUOTE_RE.findall(text))),
        "missing_terminal_period_ratio": _r(_safe_div(missing, len(nb_lines))),
    }


def _case_features(toks: list[str], sents: list[str]) -> dict:
    caps = [t for t in toks if len(t) >= 2 and ALLCAPS_RE.match(t) and any(ch.isalpha() for ch in t)]
    lower_initial = 0
    for s in sents:
        m = re.search(r"[A-Za-z]", s)
        if m and m.group(0).islower():
            lower_initial += 1
    return {
        "pct_allcaps_tokens": _r(_safe_div(len(caps), len(toks))),
        "pct_lower_initial_sentences": _r(_safe_div(lower_initial, len(sents))),
    }


def _symbol_features(text: str, nb_lines: list[str]) -> dict:
    emojis = EMOJI_RE.findall(text)
    return {
        "emoji_count": len(emojis),
        "emoji_set": sorted(set(emojis)),
        "hashtags": len(HASHTAG_RE.findall(text)),
        "mentions": len(MENTION_RE.findall(text)),
        "urls": len(URL_RE.findall(text)),
        "bullets": sum(1 for ln in nb_lines if BULLET_RE.match(ln)),
        "arrows": len(ARROW_RE.findall(text)),
    }


def _proper_nouns(nb_lines: list[str]) -> int:
    """Capitalised tokens that are not the first token of a sentence (or line) and not in the stoplist."""
    count = 0
    for ln in nb_lines:
        for s in sentences(ln):
            for tok in words(s)[1:]:
                if tok[0].isupper() and any(ch.isalpha() for ch in tok) and tok.lower() not in PROPER_STOPLIST:
                    count += 1
    return count


def _lexicon_features(text: str, toks: list[str], toks_lower: list[str], nb_lines: list[str], is_en: bool) -> dict:
    n = len(toks)
    folded = fold_punct(text)
    dollars = len(DOLLAR_RE.findall(folded))
    percents = len(PERCENT_RE.findall(folded))
    versions = len(VERSION_RE.findall(folded))
    stripped = DOLLAR_RE.sub(" ", folded)
    stripped = PERCENT_RE.sub(" ", stripped)
    stripped = VERSION_RE.sub(" ", stripped)
    numerals = len(NUMBER_RE.findall(stripped))
    proper = _proper_nouns(nb_lines)
    alpha = [t for t in toks if any(ch.isalpha() for ch in t)]
    contractions = sum(1 for t in toks_lower if CONTRACTION_RE.match(t) or t in S_CONTRACTIONS)
    return {
        "ttr": _r(_safe_div(len(set(toks_lower)), n)),
        "ttr_n": n,
        "mean_word_len": _r(_safe_div(sum(len(t) for t in alpha), len(alpha))),
        "pct_long_words": _r(_safe_div(sum(1 for t in alpha if len(t) >= 9), len(alpha))),
        "contraction_rate": _r(_safe_div(contractions, n)) if is_en else None,
        "numerals": numerals,
        "proper_nouns": proper,
        "dollar_figures": dollars,
        "specificity_per100": _r(_safe_div(100.0 * (numerals + proper + dollars + percents + versions), n)),
        "profanity": len(PROFANITY_RE.findall(folded)),
    }


def _function_words(toks_lower: list[str]) -> dict[str, float]:
    n = len(toks_lower)
    counts: dict[str, int] = {}
    for t in toks_lower:
        counts[t] = counts.get(t, 0) + 1
    return {w: _r(_safe_div(counts.get(w, 0), n), 5) for w in dict.fromkeys(FUNCTION_WORDS)}


def ai_tell_hits(text: str, lexicon: dict | None, patterns: dict | None) -> dict:
    """Verbatim spans per lexicon tier (t1/t2/t3/claude) and ids of matching rubric patterns.

    Pattern `scope` is honoured: "line1" searches the first nonblank line, "tail2" the last two."""
    folded = fold_punct(text)
    nb = nonblank_lines(folded)
    scoped = {"line1": nb[0] if nb else "", "tail2": "\n".join(nb[-2:]), "text": folded}
    out: dict[str, list] = {"t1": [], "t2": [], "t3": [], "claude": [], "patterns": []}
    for tier in ("t1", "t2", "t3", "claude"):
        for phrase, is_regex, flags in _lexicon_entries(lexicon, tier):
            rx = _phrase_regex(phrase, is_regex, flags)
            if rx is None:
                continue
            out[tier].extend(m.group(0) for m in rx.finditer(folded))
    for pat in (patterns or {}).get("patterns") or []:
        if not isinstance(pat, dict) or not pat.get("regex"):
            continue
        flag_s = str(pat.get("flags") if pat.get("flags") is not None else "i").lower()
        flags = re.M | (re.I if "i" in flag_s else 0)
        try:
            rx = re.compile(str(pat["regex"]), flags)
        except re.error:
            continue
        hay = scoped.get(str(pat.get("scope") or "text"), folded)
        if rx.search(hay) and pat.get("id") not in out["patterns"]:
            out["patterns"].append(pat.get("id"))
    return out


def count_tricolons(sents: list[str], nb_lines: list[str]) -> int:
    """'A, B(,) and C' inside one sentence, plus triples of short parallel one-line fragments."""
    count = sum(len(TRICOLON_RE.findall(fold_punct(s))) for s in sents)
    for ln in nb_lines:  # "Cold shower. Journal. Meditate.": three short fragments on one line
        frags = [len(words(s)) for s in sentences(ln)]
        j = 0
        while j + 2 < len(frags):
            if all(0 < c <= 3 for c in frags[j:j + 3]):
                count += 1
                j += 3
            else:
                j += 1
    i = 0
    while i + 2 < len(nb_lines):
        trio = [ln.strip() for ln in nb_lines[i:i + 3]]
        toks = [words(ln) for ln in trio]
        short = all(0 < len(t) <= 4 for t in toks) and not any(BULLET_RE.match(ln) for ln in trio)
        same_len = len({len(t) for t in toks}) == 1
        same_first = len({t[0].lower() for t in toks if t}) == 1
        same_end = len({ln[-1] for ln in trio if ln}) == 1 and trio[0][-1] in ".!?"
        if short and (same_first or (same_len and same_end)):
            count += 1
            i += 3
        else:
            i += 1
    return count


def count_hedges(text: str) -> int:
    folded = fold_punct(text)
    return sum(len(rx.findall(folded)) for rx in (_phrase_regex(h) for h in HEDGES) if rx is not None)


def fk_grade(toks: list[str], n_sentences: int) -> float | None:
    alpha = [t for t in toks if any(ch.isalpha() for ch in t)]
    if not alpha or n_sentences == 0:
        return None
    syl = sum(syllables(t) for t in alpha)
    return _r(0.39 * (len(alpha) / n_sentences) + 11.8 * (syl / len(alpha)) - 15.59, 1)


# --------------------------------------------------------------------------- public API


def features(text: str, platform: str, lang: str = "en", lexicon: dict | None = None,
             patterns: dict | None = None, post_id: str | None = None) -> dict:
    """The contracts section 3 feature dict for one post text. `post_id` is optional metadata."""
    text = _normalize_newlines(text or "")
    is_en = (lang or "en") == "en"
    all_lines = common.lines(text) if text else []
    nb_lines = nonblank_lines(text)
    paras = paragraphs(text)
    sents = sentences(text)
    toks = words(text)
    toks_lower = [t.lower() for t in toks]
    n_sent = len(sents)

    line_block, _, sent_per_para = _line_features(nb_lines, paras)
    single_sentence = sum(1 for s in sent_per_para if s == 1)
    return {
        "post_id": post_id,
        "platform": platform,
        "lang": lang,
        "n_chars": len(text),
        "n_words": len(toks),
        "n_lines": len(nb_lines),
        "n_blank": sum(1 for ln in all_lines if not ln.strip()),
        "n_sentences": n_sent,
        "line_words": line_block,
        "sent_words": _sentence_features(sents),
        "hook": _hook_features(text, nb_lines, paras),
        "pov": _pov_features(toks_lower),
        "tense_past_ratio": _tense_past_ratio(toks_lower),
        "punct_per_1k": _punct_features(text, nb_lines),
        "case": _case_features(toks, sents),
        "symbols": _symbol_features(text, nb_lines),
        "lexicon": _lexicon_features(text, toks, toks_lower, nb_lines, is_en),
        "function_words": _function_words(toks_lower) if is_en else None,
        "ai_tells": ai_tell_hits(text, lexicon, patterns) if is_en else None,
        "questions": sum(1 for s in sents if s.rstrip().rstrip("\"'”’)").endswith("?")),
        "imperatives": sum(1 for s in sents if _first_word(s) in IMPERATIVE_VERBS),
        "tricolons": count_tricolons(sents, nb_lines),
        "hedges": count_hedges(text) if is_en else None,
        "fk_grade": fk_grade(toks, n_sent) if is_en else None,
        "pct_single_sentence_paras": _r(_safe_div(single_sentence, len(paras))),
    }


def flatten_numeric(feat: dict, prefix: str = "", skip: tuple[str, ...] = ("function_words", "ai_tells")) -> dict:
    """Dotted path -> number for every numeric or bool leaf. Bools become 0/1; strings, lists and skipped
    keys are dropped."""
    out: dict[str, float] = {}
    for k, v in feat.items():
        if k in skip and not prefix:
            continue
        path = f"{prefix}{k}"
        if isinstance(v, bool):
            out[path] = 1.0 if v else 0.0
        elif isinstance(v, (int, float)):
            out[path] = float(v)
        elif isinstance(v, dict):
            out.update(flatten_numeric(v, path + ".", skip=()))
    return out


def get_path(d: dict, path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


# --------------------------------------------------------------------------- root handling & corpus mode


def apply_root(root: str | Path | None) -> Path:
    """Point common.ROOT (and the cached config) at `root` for this process; returns the effective root."""
    if root:
        p = Path(root).expanduser().resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"root is not a directory: {p}")
        common.ROOT = p
        common._CONFIG = None
        os.environ["POSTSMITH_ROOT"] = str(p)
    return common.ROOT


def load_optional_lexicon_patterns() -> tuple[dict | None, dict | None]:
    """Lexicon and rubric patterns when present in the project; (None, None) otherwise (never raises)."""
    lexicon = patterns = None
    try:
        lexicon = common.load_lexicon()
    except Exception:  # noqa: BLE001 - optional input
        lexicon = None
    try:
        patterns = common.load_patterns()
    except Exception:  # noqa: BLE001 - optional input
        patterns = None
    return lexicon, patterns


def features_dir_for(split: str) -> Path:
    return common.ROOT / "corpus" / ("heldout/features" if split == "heldout" else "features")


def run_corpus(splits: tuple[str, ...] = ("train", "self", "heldout"), lexicon: dict | None = None,
               patterns: dict | None = None) -> dict:
    """(Re)write the features file of every post in `splits`; returns a summary dict."""
    written: list[str] = []
    skipped: list[dict] = []
    for split in splits:
        for meta, text, path in common.iter_posts((split,)):
            post_id = str(meta.get("post_id") or path.stem)
            platform = str(meta.get("platform") or "linkedin")
            lang = str(meta.get("lang") or common.detect_lang(text))
            try:
                feat = features(text, platform, lang, lexicon, patterns, post_id=post_id)
            except Exception as exc:  # noqa: BLE001 - keep going, report
                skipped.append({"post_id": post_id, "error": f"{type(exc).__name__}: {exc}"})
                continue
            out = features_dir_for(split) / f"{post_id}.json"
            common.write_json(out, feat)
            written.append(common.rel(out))
    return {"ok": True, "written": len(written), "files": written, "skipped": skipped}


def features_for_file(path: str | Path, platform: str | None = None, lang: str | None = None,
                      lexicon: dict | None = None, patterns: dict | None = None) -> dict:
    """Features for a .md (front matter honoured) or .txt post file."""
    p = Path(path)
    if not p.is_absolute():
        p = (Path.cwd() / p) if (Path.cwd() / p).exists() else common.ROOT / p
    raw = p.read_text(encoding="utf-8")
    meta, body = split_front_matter(raw) if p.suffix.lower() == ".md" else ({}, raw)
    platform = platform or str(meta.get("platform") or "linkedin")
    lang = lang or str(meta.get("lang") or common.detect_lang(body))
    return features(body, platform, lang, lexicon, patterns, post_id=meta.get("post_id") or p.stem)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-post stylometric features (contracts section 3).")
    ap.add_argument("post", nargs="?", help="post file (.md with front matter, or .txt)")
    ap.add_argument("--platform", choices=["linkedin", "x"], help="override platform")
    ap.add_argument("--lang", help="override language code (en, other, cjk, ...)")
    ap.add_argument("--corpus", action="store_true", help="(re)write corpus/features/*.json for every post")
    ap.add_argument("--root", help="project root (default: env POSTSMITH_ROOT / auto-detected)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        apply_root(args.root)
    except FileNotFoundError as exc:
        common.error(str(exc))
        return 0
    lexicon, patterns = load_optional_lexicon_patterns()
    if args.corpus:
        emit(run_corpus(lexicon=lexicon, patterns=patterns))
        return 0
    if not args.post:
        common.error("give a post file or --corpus")
        return 0
    try:
        feat = features_for_file(args.post, args.platform, args.lang, lexicon, patterns)
    except (FileNotFoundError, IsADirectoryError, PermissionError) as exc:
        common.error(f"cannot read post: {exc}")
        return 0
    except UnicodeDecodeError:
        common.error(f"post is not UTF-8 text: {args.post}")
        return 0
    emit(feat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
