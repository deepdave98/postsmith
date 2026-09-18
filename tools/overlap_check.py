#!/usr/bin/env python3
"""Overlap checks O1-O5 for postsmith candidates (contracts section 16).

Checks (all on `common.normalize_text` output, spans reported verbatim from the candidate):

- O1_ngram      shared word n-gram with any corpus post (train + heldout + self): 6-gram = flag, 8-gram = fail;
                longest common substring >= cfg.overlap.lcs_fail_chars = fail. Prior finalists
                (drafts/*/final/*.md) count at flag level only.
- O2_phrases    do-not-reuse phrases from lexicon.do_not_reuse (every author) plus every indexed card's
                distinctive_phrases, minus excluded posts so a post never matches its own card. A phrase hits
                when a candidate window of the same word count is within cfg.overlap.phrase_edit_distance
                edits. Hard.
- O3_skeleton   flag when the candidate's archetype + hook_type + ending equal a corpus card's and the word-3-gram
                Jaccard >= cfg.overlap.skeleton_jaccard.
- O4_sibling    flag when the word-3-gram Jaccard with another candidate of the run >= cfg.overlap.sibling_jaccard.
- O5_published  shared 8-gram or LCS >= cfg.overlap.lcs_fail_chars with memory/published/* = hard fail; 6-gram = flag.

Library use (tier0 composes these without a CLI round trip):

    idx = build_index(("train", "heldout", "self"), include_cards=True, include_drafts_final=True, root=None)
    res = run_checks(text, meta, cfg, lexicon, idx, siblings, published, exclude_ids)

Every check result carries class (hard|flag), pass (bool), result (pass|flag|fail), hits, and evidence
([{span, why}], verbatim spans, empty when passing).

CLI:  uv run tools/overlap_check.py <candidate.md> [--run <run>] [--exclude id,id] [--root R] [--json]
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from common import edit_distance, jaccard, normalize_text, split_front_matter, word_ngrams  # noqa: E402

CHECK_IDS = ("O1_ngram", "O2_phrases", "O3_skeleton", "O4_sibling", "O5_published")
SPLIT_DIRS = {"train": ("corpus", "posts"), "heldout": ("corpus", "heldout"), "self": ("corpus", "self")}
CARD_DIRS = (("corpus", "cards"), ("corpus", "heldout", "cards"))
FINAL_SKIP = {"report.md", "clipboard.md"}
DEFAULT_OVERLAP_CFG: dict[str, Any] = {
    "ngram_flag": 6,
    "ngram_fail": 8,
    "lcs_fail_chars": 40,
    "phrase_edit_distance": 2,
    "skeleton_jaccard": 0.15,
    "sibling_jaccard": 0.5,
}
MAX_HITS = 25           # hits kept per check in the output (n_hits_total always reports the true count)
DIAG_LCS_REFS = 3       # most-similar refs used for the below-threshold lcs_chars diagnostic
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)\n```", re.DOTALL)


class UserError(Exception):
    """Bad input from the user (reported as {"ok": false, "error": ...}, exit 0)."""


# --------------------------------------------------------------------------- root / config / lexicon

def resolve_root(root: str | Path | None = None) -> Path:
    """Project root: explicit argument, else $POSTSMITH_ROOT, else the root common.py found."""
    if root:
        return Path(root).expanduser().resolve()
    env = os.environ.get("POSTSMITH_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return common.ROOT


def load_cfg(root: Path) -> dict:
    """<root>/config/postsmith.yaml when present, else the shared config (so fixture roots stay self-contained)."""
    p = root / "config" / "postsmith.yaml"
    if p.exists():
        return common.load_yaml(p)
    return common.load_config()


def load_lexicon(root: Path) -> dict:
    p = root / "style" / "lexicon.yaml"
    if p.exists():
        return common.load_yaml(p) or {}
    if root == common.ROOT:
        return common.load_lexicon()
    return {"lexicon_version": 0, "tiers": {}, "do_not_reuse": {}, "user_tells": []}


def overlap_cfg(cfg: dict | None) -> dict:
    out = dict(DEFAULT_OVERLAP_CFG)
    out.update((cfg or {}).get("overlap") or {})
    out["ngram_flag"] = int(out["ngram_flag"])
    out["ngram_fail"] = int(out["ngram_fail"])
    out["lcs_fail_chars"] = int(out["lcs_fail_chars"])
    out["phrase_edit_distance"] = int(out["phrase_edit_distance"])
    out["skeleton_jaccard"] = float(out["skeleton_jaccard"])
    out["sibling_jaccard"] = float(out["sibling_jaccard"])
    return out


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- candidate preparation

@dataclass
class Prepared:
    """A text with its normalized tokens and, when recoverable, the raw span of every token."""

    raw: str
    tokens: list[str]
    spans: list[tuple[int, int]] | None   # raw [start, end) per token; None when the mapping could not be verified
    norm: str                             # == normalize_text(raw) == " ".join(tokens)
    offsets: list[int]                    # char offset of each token inside `norm`


def token_spans(raw: str) -> tuple[list[str], list[tuple[int, int]] | None]:
    """Normalized tokens plus the raw [start, end) of the whitespace chunk each token came from.

    Normalization runs chunk by chunk (a chunk is a run of non-whitespace), which yields exactly the token
    sequence of `normalize_text(raw)`. That equality is checked, and the spans come back None when it fails,
    so the caller falls back to normalized spans.
    """
    tokens: list[str] = []
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"\S+", raw):
        for tok in normalize_text(m.group()).split():
            tokens.append(tok)
            spans.append((m.start(), m.end()))
    if " ".join(tokens) != normalize_text(raw):
        return normalize_text(raw).split(), None
    return tokens, spans


def prepare(raw: str) -> Prepared:
    tokens, spans = token_spans(raw)
    offsets: list[int] = []
    pos = 0
    for t in tokens:
        offsets.append(pos)
        pos += len(t) + 1
    return Prepared(raw=raw, tokens=tokens, spans=spans, norm=" ".join(tokens), offsets=offsets)


_EDGE_PUNCT_RE = re.compile(r"^[^\w]+|[^\w]+$")


def span_of(prep: Prepared, i: int, j: int) -> str:
    """Verbatim raw text covering normalized tokens [i, j); punctuation hugging the two ends is trimmed."""
    if not prep.tokens or i >= j:
        return ""
    j = min(j, len(prep.tokens))
    if prep.spans is None:
        return " ".join(prep.tokens[i:j])
    span = prep.raw[prep.spans[i][0]:prep.spans[j - 1][1]]
    trimmed = _EDGE_PUNCT_RE.sub("", span)
    return trimmed or span


def span_of_chars(prep: Prepared, c0: int, c1: int) -> str:
    """Verbatim raw text covering the tokens that overlap normalized char range [c0, c1)."""
    if c1 <= c0 or not prep.tokens:
        return ""
    first = last = None
    for idx, (off, tok) in enumerate(zip(prep.offsets, prep.tokens)):
        end = off + len(tok)
        if end > c0 and off < c1:
            if first is None:
                first = idx
            last = idx
    if first is None:
        return ""
    return span_of(prep, first, last + 1)


def char_kgrams(s: str, k: int) -> set[str]:
    return {s[i:i + k] for i in range(max(0, len(s) - k + 1))}


# --------------------------------------------------------------------------- pairwise primitives

def shared_runs(cand: list[str], ref: list[str], n: int) -> list[tuple[int, int, int]]:
    """Maximal shared word runs of length >= n as (cand_start, ref_start, length).

    Each run is a genuine contiguous match in both texts (not just consecutive shared n-grams).
    A run fully covered by an earlier, longer run at the same candidate position is not repeated.
    """
    if n <= 0 or len(cand) < n or len(ref) < n:
        return []
    ref_pos: dict[tuple[str, ...], list[int]] = {}
    for j in range(len(ref) - n + 1):
        ref_pos.setdefault(tuple(ref[j:j + n]), []).append(j)
    runs: list[tuple[int, int, int]] = []
    covered = 0
    for i in range(len(cand) - n + 1):
        positions = ref_pos.get(tuple(cand[i:i + n]))
        if not positions:
            continue
        best_j, best_len = -1, 0
        for j in positions:
            length = n
            while i + length < len(cand) and j + length < len(ref) and cand[i + length] == ref[j + length]:
                length += 1
            if length > best_len:
                best_j, best_len = j, length
        if i + best_len > covered:
            runs.append((i, best_j, best_len))
            covered = i + best_len
    return runs


def longest_common_substring(a: str, b: str) -> tuple[int, int, int]:
    """Exact longest common substring of two strings as (start_in_a, start_in_b, length)."""
    if not a or not b:
        return 0, 0, 0
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.a, m.b, m.size


def lcs_at_least(cand_norm: str, cand_kgrams: set[str], ref_norm: str, k: int) -> tuple[int, int, int] | None:
    """(start_in_cand, start_in_ref, length) of the LCS when it is >= k chars, else None.

    An LCS >= k exists iff the two strings share a character k-gram, so the k-gram scan is an exact prefilter
    and the O(n*m) computation only runs on real hits.
    """
    if k <= 0 or len(cand_norm) < k or len(ref_norm) < k:
        return None
    if not any(ref_norm[i:i + k] in cand_kgrams for i in range(len(ref_norm) - k + 1)):
        return None
    a, b, size = longest_common_substring(cand_norm, ref_norm)
    return (a, b, size) if size >= k else None


# --------------------------------------------------------------------------- index

def _entry(ref_id: str, text: str, **extra: Any) -> dict:
    tokens = normalize_text(text).split()
    e = {"id": ref_id, "text": text, "tokens": tokens, "norm": " ".join(tokens)}
    e.update(extra)
    return e


def _finalist_text(body: str) -> str:
    """Post text of a drafts/<run>/final/<id>.md body: the first fenced block when there is one, else the body."""
    m = _FENCE_RE.search(body)
    return (m.group(1) if m else body).rstrip("\n")


def _read_card(root: Path, post_id: str) -> dict | None:
    for parts in CARD_DIRS:
        p = root.joinpath(*parts) / f"{post_id}.md"
        if p.exists():
            meta, _ = split_front_matter(p.read_text(encoding="utf-8"))
            return meta or {}
    return None


def build_index(splits: Iterable[str] = ("train", "heldout", "self"), include_cards: bool = True,
                include_drafts_final: bool = True, root: str | Path | None = None,
                exclude_run: str | None = None) -> dict:
    """Build the in-memory overlap index for a project root.

    Returns {"posts": {post_id: entry}, "prior_finalists": {"final:<run>/<id>": entry, "passed:<run>/<cid>": entry},
             "published": {<file stem>: entry}, "ngrams": {n: {gram: [post_id, ...]}}, ...}.
    Entry: {id, text, tokens, norm, author, platform, split, path, crosspost_of, variant_of,
            archetype, hook_types, ending}. Card fields are None/[] when no card exists.
    Prior finalists (flag-level targets for O1) are every drafts/*/final/*.md plus every candidate of another run
    whose merged.json says pass / passed_tier1_only (their candidates/<cid>.txt); `exclude_run` names the current
    run so its own candidates are never counted against it.
    """
    root = resolve_root(root)
    ocfg = overlap_cfg(load_cfg(root))
    splits = tuple(splits)
    for s in splits:
        if s not in SPLIT_DIRS:
            raise UserError(f"unknown split {s!r} (expected train, heldout, self)")

    posts: dict[str, dict] = {}
    for split in splits:
        d = root.joinpath(*SPLIT_DIRS[split])
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            meta, body = split_front_matter(p.read_text(encoding="utf-8"))
            meta = meta or {}
            pid = str(meta.get("post_id") or p.stem)
            author = meta.get("author")
            slug = author.get("slug") if isinstance(author, dict) else author
            posts[pid] = _entry(
                pid, body.rstrip("\n"), author=slug, platform=meta.get("platform"), split=split,
                path=_relpath(p, root), crosspost_of=meta.get("crosspost_of"), variant_of=meta.get("variant_of"),
                archetype=None, hook_types=[], ending=None, card=False, distinctive_phrases=[],
            )
    if include_cards:
        for pid, e in posts.items():
            card = _read_card(root, pid)
            if card is None:
                continue
            hook = card.get("hook") or {}
            types = hook.get("types") if isinstance(hook, dict) else None
            phrases = card.get("distinctive_phrases") or []
            e.update(archetype=card.get("archetype"), hook_types=list(types or []), ending=card.get("ending"),
                     card=True,
                     distinctive_phrases=[str(x).strip() for x in (phrases if isinstance(phrases, list) else [])
                                          if str(x).strip()])

    prior: dict[str, dict] = {}
    if include_drafts_final and (root / "drafts").exists():
        for run_dir in sorted(p for p in (root / "drafts").iterdir() if p.is_dir()):
            final = run_dir / "final"
            if not final.is_dir():
                continue
            for f in sorted(final.glob("*.md")):
                if f.name in FINAL_SKIP:
                    continue
                meta, body = split_front_matter(f.read_text(encoding="utf-8"))
                text = _finalist_text(body)
                if text.strip():
                    rid = f"final:{run_dir.name}/{f.stem}"
                    prior[rid] = _entry(rid, text, path=_relpath(f, root), platform=(meta or {}).get("platform"))
        for run_dir in sorted(p for p in (root / "drafts").iterdir() if p.is_dir()):
            if exclude_run and run_dir.name == str(exclude_run).strip("/").split("/")[-1]:
                continue
            for mp in sorted(run_dir.glob("round*/scores/*.merged.json")):
                try:
                    merged = json.loads(mp.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                status = ((merged or {}).get("verdict") or {}).get("status") if isinstance(merged, dict) else None
                if status not in ("pass", "passed_tier1_only"):
                    continue
                cid = mp.name[: -len(".merged.json")]
                txt = mp.parent.parent / "candidates" / f"{cid}.txt"
                if not txt.exists():
                    continue
                text = txt.read_text(encoding="utf-8").rstrip("\n")
                if text.strip():
                    rid = f"passed:{run_dir.name}/{cid}"
                    prior.setdefault(rid, _entry(rid, text, path=_relpath(txt, root), platform=merged.get("platform")))

    published: dict[str, dict] = {}
    pub_dir = root / "memory" / "published"
    if pub_dir.exists():
        for f in sorted(pub_dir.glob("*.md")):
            meta, body = split_front_matter(f.read_text(encoding="utf-8"))
            text = body.rstrip("\n")
            if text.strip():
                published[f.stem] = _entry(f.stem, text, path=_relpath(f, root), platform=(meta or {}).get("platform"))

    sizes = sorted({ocfg["ngram_flag"], ocfg["ngram_fail"]})
    ngrams: dict[int, dict[tuple[str, ...], list[str]]] = {n: {} for n in sizes}
    for pid, e in posts.items():
        for n in sizes:
            inv = ngrams[n]
            for g in word_ngrams(e["tokens"], n):
                inv.setdefault(g, []).append(pid)

    return {
        "schema": "postsmith.overlap_index/1",
        "root": str(root),
        "splits": list(splits),
        "posts": posts,
        "prior_finalists": prior,
        "published": published,
        "ngrams": ngrams,
        "ngram_sizes": sizes,
        "overlap_cfg": ocfg,
    }


def expand_excludes(index: dict, exclude_ids: Iterable[str] | None) -> set[str]:
    """Close the exclude set over crosspost_of / variant_of links in both directions."""
    excluded = {str(x) for x in (exclude_ids or ()) if x}
    posts = index.get("posts", {})
    changed = True
    while changed:
        changed = False
        for pid, e in posts.items():
            links = {e.get("crosspost_of"), e.get("variant_of")} - {None, ""}
            if pid in excluded:
                new = links - excluded
            elif links & excluded:
                new = {pid}
            else:
                continue
            if new:
                excluded |= new
                changed = True
    return excluded


# --------------------------------------------------------------------------- check helpers

def _result(check_id: str, hits: list[dict], nominal: str, why: str) -> dict:
    """Assemble a check result. Level = worst hit level; class = hard on fail, flag on flag, nominal when passing."""
    levels = {h.get("level", "flag") for h in hits}
    result = "fail" if "fail" in levels else ("flag" if hits else "pass")
    klass = {"fail": "hard", "flag": "flag"}.get(result, nominal)
    ordered = sorted(hits, key=lambda h: (0 if h.get("level") == "fail" else 1, -int(h.get("n") or h.get("chars") or 0),
                                          str(h.get("ref", "")), h.get("span", "")))
    evidence = [{"span": h["span"], "why": h["why"]} for h in ordered[:MAX_HITS] if h.get("span")]
    return {
        "class": klass,
        "pass": result == "pass",
        "result": result,
        "hits": [{k: v for k, v in h.items() if k != "why"} for h in ordered[:MAX_HITS]],
        "n_hits_total": len(hits),
        "evidence": evidence if result != "pass" else [],
        "note": why,
    }


def _text_hits(prep: Prepared, ref: dict, ocfg: dict, kgrams: set[str], *, flag_only: bool,
               ngram_refs: bool = True) -> list[dict]:
    """n-gram runs and LCS hits of the candidate against one reference entry."""
    n_flag, n_fail, k = ocfg["ngram_flag"], ocfg["ngram_fail"], ocfg["lcs_fail_chars"]
    hits: list[dict] = []
    if ngram_refs:
        for i, _j, length in shared_runs(prep.tokens, ref["tokens"], n_flag):
            level = "flag" if flag_only or length < n_fail else "fail"
            hits.append({"ref": ref["id"], "kind": "ngram", "n": length, "level": level, "span": span_of(prep, i, i + length),
                         "why": f"shared {length}-word run with {ref['id']}"})
    m = lcs_at_least(prep.norm, kgrams, ref["norm"], k)
    if m:
        a, _b, size = m
        hits.append({"ref": ref["id"], "kind": "lcs", "chars": size, "level": "flag" if flag_only else "fail",
                     "span": span_of_chars(prep, a, a + size),
                     "why": f"longest common substring of {size} chars with {ref['id']} (limit {k})"})
    return hits


def _candidate_refs(prep: Prepared, index: dict, n: int) -> set[str]:
    """Ids of corpus posts sharing at least one word n-gram with the candidate (via the inverted index)."""
    inv = index.get("ngrams", {}).get(n)
    grams = word_ngrams(prep.tokens, n)
    if inv is None:
        return {pid for pid, e in index["posts"].items() if grams & word_ngrams(e["tokens"], n)}
    refs: set[str] = set()
    for g in grams:
        ids = inv.get(g)
        if ids:
            refs.update(ids)
    return refs


def _diagnostics(prep: Prepared, entries: list[dict], kgrams: set[str], ocfg: dict) -> tuple[int, int | None]:
    """(max shared word run of any length >= 3, best-effort max LCS chars) across `entries`."""
    if not entries:
        return 0, None
    best_run = 0
    cand_vocab = set(prep.tokens)
    ranked: list[tuple[int, int, str]] = []
    for e in entries:
        runs = shared_runs(prep.tokens, e["tokens"], 3)
        best_run = max(best_run, max((r[2] for r in runs), default=0))
        ranked.append((sum(r[2] for r in runs), len(cand_vocab & set(e["tokens"])), e["id"]))
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
    by_id = {e["id"]: e for e in entries}
    lcs = 0
    for _runs, _shared, rid in ranked[:DIAG_LCS_REFS]:
        lcs = max(lcs, longest_common_substring(prep.norm, by_id[rid]["norm"])[2])
    return best_run, lcs


# --------------------------------------------------------------------------- the checks

def check_o1(prep: Prepared, index: dict, excluded: set[str], ocfg: dict) -> dict:
    posts = index.get("posts", {})
    kgrams = char_kgrams(prep.norm, ocfg["lcs_fail_chars"])
    hits: list[dict] = []
    ngram_ids = _candidate_refs(prep, index, ocfg["ngram_flag"]) - excluded
    for pid in sorted(posts):
        if pid in excluded:
            continue
        hits.extend(_text_hits(prep, posts[pid], ocfg, kgrams, flag_only=False, ngram_refs=pid in ngram_ids))
    for rid in sorted(index.get("prior_finalists", {})):
        hits.extend(_text_hits(prep, index["prior_finalists"][rid], ocfg, kgrams, flag_only=True))
    res = _result("O1_ngram", hits, "flag",
                  f"word {ocfg['ngram_flag']}-gram = flag, {ocfg['ngram_fail']}-gram = fail, "
                  f"LCS >= {ocfg['lcs_fail_chars']} chars = fail; prior finalists flag only")
    entries = [e for pid, e in posts.items() if pid not in excluded] + list(index.get("prior_finalists", {}).values())
    max_run, lcs_chars = _diagnostics(prep, entries, kgrams, ocfg)
    res["max_shared_ngram"] = max_run
    res["lcs_chars"] = lcs_chars
    res["n_refs"] = len(entries)
    return res


def iter_do_not_reuse(lexicon: dict | None) -> list[tuple[str, str]]:
    """(author, phrase) pairs from lexicon.do_not_reuse; accepts {author: [str|{phrase}]} or a flat list."""
    raw = (lexicon or {}).get("do_not_reuse") or {}
    out: list[tuple[str, str]] = []
    items: list[tuple[str, Any]]
    if isinstance(raw, dict):
        items = [(str(a), v) for a, v in raw.items()]
    else:
        items = [("*", raw)]
    for author, phrases in items:
        if isinstance(phrases, (str, dict)):
            phrases = [phrases]
        for ph in phrases or []:
            text = ph.get("phrase") if isinstance(ph, dict) else ph
            if text and str(text).strip():
                out.append((author, str(text).strip()))
    return out


def _bag_distance_lower_bound(a: Counter, b: Counter) -> int:
    diff = sum((a - b).values()) + sum((b - a).values())
    return (diff + 1) // 2


def card_phrases(index: dict | None, excluded: Iterable[str] | None = None) -> list[tuple[str, str, str]]:
    """(post_id, author, phrase) triples from the distinctive_phrases of every indexed card, skipping excluded posts."""
    ex = set(excluded or ())
    out: list[tuple[str, str, str]] = []
    for pid, e in sorted(((index or {}).get("posts") or {}).items()):
        if pid in ex:
            continue
        for ph in e.get("distinctive_phrases") or []:
            if str(ph).strip():
                out.append((pid, str(e.get("author") or "?"), str(ph).strip()))
    return out


def check_o2(prep: Prepared, lexicon: dict | None, ocfg: dict, index: dict | None = None,
             excluded: Iterable[str] | None = None) -> dict:
    """Do-not-reuse phrases: lexicon.do_not_reuse (ref = author, source "lexicon") plus the distinctive_phrases of
    indexed cards (ref = post_id, source "card"); a phrase already in the lexicon is not repeated from a card."""
    d = int(ocfg["phrase_edit_distance"])
    hits: list[dict] = []
    windows: dict[int, list[str]] = {}
    seen: set[str] = set()
    sources: list[tuple[str, str, str, str]] = [(a, a, ph, "lexicon") for a, ph in iter_do_not_reuse(lexicon)]
    sources += [(pid, a, ph, "card") for pid, a, ph in card_phrases(index, excluded)]
    for ref, author, phrase, source in sources:
        p = normalize_text(phrase)
        k = len(p.split())
        if k == 0 or k > len(prep.tokens) or p in seen:
            continue
        seen.add(p)
        d_eff = phrase_tolerance(p, d)
        p_nums = _numeric_tokens(p)
        if k not in windows:
            windows[k] = [" ".join(prep.tokens[i:i + k]) for i in range(len(prep.tokens) - k + 1)]
        pc = Counter(p)
        best: tuple[int, int] | None = None
        for i, w in enumerate(windows[k]):
            if abs(len(w) - len(p)) > d_eff:
                continue
            if w == p:
                dist = 0
            else:
                if d_eff == 0 or _bag_distance_lower_bound(Counter(w), pc) > d_eff:
                    continue
                if p_nums and _numeric_tokens(w) != p_nums:  # a different number is a different fact, not a typo
                    continue
                dist = edit_distance(w, p)
                if dist > d_eff:
                    continue
            if best is None or dist < best[1]:
                best = (i, dist)
                if dist == 0:
                    break
        if best is not None:
            i, dist = best
            origin = f" (card {ref})" if source == "card" else ""
            hits.append({"ref": ref, "author": author, "source": source, "phrase": phrase, "distance": dist,
                         "distance_allowed": d_eff, "n": k, "level": "fail", "span": span_of(prep, i, i + k),
                         "why": f"do-not-reuse phrase of {author}{origin}: {phrase!r} (edit distance {dist} <= {d_eff})"})
    return _result("O2_phrases", hits, "hard",
                   f"lexicon do_not_reuse + card distinctive_phrases, fuzzy (edit distance <= {d}, scaled by phrase "
                   f"length: exact below 8 normalized chars, then 1 per 8 chars; numbers must match exactly)")


def phrase_tolerance(normalized_phrase: str, max_distance: int) -> int:
    """Edit-distance budget for a do-not-reuse phrase: 0 below 8 normalized characters (so 'moat' never matches
    'most'), otherwise one edit per 8 characters capped at cfg.overlap.phrase_edit_distance."""
    n = len(normalized_phrase)
    return 0 if n < 8 else min(int(max_distance), n // 8)


def _numeric_tokens(s: str) -> list[str]:
    return [t for t in s.split() if any(ch.isdigit() for ch in t)]


def skeleton_of_meta(meta: dict | None) -> tuple[str | None, list[str], str | None]:
    """(archetype, hook_types, ending) declared by a candidate's front matter (top level or assignment)."""
    meta = meta or {}
    assignment = meta.get("assignment") if isinstance(meta.get("assignment"), dict) else {}
    archetype = meta.get("archetype") or assignment.get("archetype")
    hook = meta.get("hook_type") or assignment.get("hook_type")
    if not hook and isinstance(meta.get("hook"), dict):
        hook = meta["hook"].get("types") or meta["hook"].get("type")
    ending = meta.get("ending") or assignment.get("ending")
    hooks = [str(h) for h in (hook if isinstance(hook, list) else [hook]) if h]
    return (str(archetype) if archetype else None), hooks, (str(ending) if ending else None)


def check_o3(prep: Prepared, meta: dict | None, index: dict, excluded: set[str], ocfg: dict) -> dict:
    archetype, hooks, ending = skeleton_of_meta(meta)
    thr = ocfg["skeleton_jaccard"]
    if not (archetype and hooks and ending):
        res = _result("O3_skeleton", [], "flag", "candidate front matter lacks archetype/hook_type/ending; not compared")
        res["compared"] = 0
        return res
    cand3 = word_ngrams(prep.tokens, 3)
    hits: list[dict] = []
    compared = 0
    for pid in sorted(index.get("posts", {})):
        e = index["posts"][pid]
        if pid in excluded or not e.get("card"):
            continue
        matched_hook = next((h for h in hooks if h in (e.get("hook_types") or [])), None)
        if e.get("archetype") != archetype or matched_hook is None or e.get("ending") != ending:
            continue
        compared += 1
        jac = jaccard(cand3, word_ngrams(e["tokens"], 3))
        if jac >= thr:
            runs = shared_runs(prep.tokens, e["tokens"], 3)
            longest = max(runs, key=lambda r: r[2], default=None)
            span = span_of(prep, longest[0], longest[0] + longest[2]) if longest else prep.raw.strip().split("\n")[0]
            hits.append({"ref": pid, "jaccard": round(jac, 3), "archetype": archetype, "hook_type": matched_hook,
                         "ending": ending, "level": "flag", "span": span,
                         "why": f"same skeleton as {pid} ({archetype} + {matched_hook} + {ending}) and 3-gram Jaccard "
                                f"{jac:.2f} >= {thr}"})
    res = _result("O3_skeleton", hits, "flag", f"same archetype + hook type + ending and 3-gram Jaccard >= {thr}")
    res["compared"] = compared
    return res


def check_o4(prep: Prepared, meta: dict | None, siblings: Iterable[tuple[str, str]] | None, ocfg: dict) -> dict:
    thr = ocfg["sibling_jaccard"]
    own = str((meta or {}).get("cid") or "")
    cand3 = word_ngrams(prep.tokens, 3)
    hits: list[dict] = []
    compared = 0
    for cid, text in siblings or []:
        if own and str(cid) == own:
            continue
        compared += 1
        sib = normalize_text(text or "").split()
        jac = jaccard(cand3, word_ngrams(sib, 3))
        if jac >= thr:
            runs = shared_runs(prep.tokens, sib, 3)
            longest = max(runs, key=lambda r: r[2], default=None)
            span = span_of(prep, longest[0], longest[0] + longest[2]) if longest else ""
            hits.append({"ref": str(cid), "jaccard": round(jac, 3), "level": "flag", "span": span,
                         "why": f"near-duplicate of sibling {cid}: 3-gram Jaccard {jac:.2f} >= {thr}"})
    res = _result("O4_sibling", hits, "flag", f"3-gram Jaccard with another candidate of the run >= {thr}")
    res["compared"] = compared
    return res


def check_o5(prep: Prepared, published: Iterable[tuple[str, str]] | None, index: dict, ocfg: dict) -> dict:
    entries: dict[str, dict] = dict(index.get("published", {}))
    for pid, text in published or []:
        if text and str(text).strip():
            entries[str(pid)] = _entry(str(pid), str(text))
    kgrams = char_kgrams(prep.norm, ocfg["lcs_fail_chars"])
    hits: list[dict] = []
    for pid in sorted(entries):
        hits.extend(_text_hits(prep, entries[pid], ocfg, kgrams, flag_only=False))
    res = _result("O5_published", hits, "hard",
                  f"vs memory/published: {ocfg['ngram_fail']}-gram or LCS >= {ocfg['lcs_fail_chars']} = fail, "
                  f"{ocfg['ngram_flag']}-gram = flag")
    res["n_refs"] = len(entries)
    return res


def run_checks(text: str, meta: dict | None, cfg: dict | None, lexicon: dict | None, corpus_index: dict,
               siblings: list[tuple[str, str]] | None = None, published: list[tuple[str, str]] | None = None,
               exclude_ids: Iterable[str] | None = None) -> dict:
    """Run O1-O5 on a candidate text.

    meta: candidate front matter (may be {}); siblings: [(cid, text)] of the other candidates in the run;
    published: extra [(id, text)] published posts (merged with the index's memory/published entries);
    exclude_ids: corpus post ids removed from comparison, closed over crosspost_of/variant_of.
    Returns {"checks": {each check by id}, "excluded": [...], "n_tokens": int}.
    """
    ocfg = overlap_cfg(cfg)
    prep = prepare(text or "")
    excluded = expand_excludes(corpus_index, exclude_ids)
    checks = {
        "O1_ngram": check_o1(prep, corpus_index, excluded, ocfg),
        "O2_phrases": check_o2(prep, lexicon, ocfg, corpus_index, excluded),
        "O3_skeleton": check_o3(prep, meta, corpus_index, excluded, ocfg),
        "O4_sibling": check_o4(prep, meta, siblings, ocfg),
        "O5_published": check_o5(prep, published, corpus_index, ocfg),
    }
    return {"checks": checks, "excluded": sorted(excluded), "n_tokens": len(prep.tokens)}


# --------------------------------------------------------------------------- CLI

def _resolve_candidate(arg: str, root: Path) -> Path:
    p = Path(arg).expanduser()
    if p.is_absolute():
        return p
    if p.exists():
        return p.resolve()
    return (root / p).resolve()


def collect_siblings(root: Path, cand_path: Path, meta: dict, run: str | None) -> list[tuple[str, str]]:
    """Other candidates of the run: round<meta.round>/candidates of --run (all rounds when unknown), else the
    candidate's own candidates/ directory."""
    dirs: list[Path] = []
    if run:
        rp = Path(run)
        run_dir = rp if rp.is_absolute() else (root / rp if rp.parts and rp.parts[0] == "drafts" else root / "drafts" / rp)
        if not run_dir.is_dir():
            raise UserError(f"run not found: {run} (looked in {run_dir})")
        rnd = meta.get("round")
        if rnd is not None and str(rnd).isdigit():
            dirs = [run_dir / f"round{rnd}" / "candidates"]
        else:
            dirs = sorted(run_dir.glob("round*/candidates"))
    elif cand_path.parent.name == "candidates":
        dirs = [cand_path.parent]
    own = str(meta.get("cid") or cand_path.stem)
    sibs: list[tuple[str, str]] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            if f.resolve() == cand_path.resolve():
                continue
            m, body = split_front_matter(f.read_text(encoding="utf-8"))
            cid = str((m or {}).get("cid") or f.stem)
            if cid == own or not body.strip():
                continue
            sibs.append((cid, body.rstrip("\n")))
    return sibs


def _human(out: dict) -> str:
    lines = [f"overlap: {out['candidate']} (cid {out['cid']}, {out['index']['n_posts']} corpus posts)"]
    for cid in CHECK_IDS:
        c = out["checks"][cid]
        lines.append(f"  {cid:13s} {c['result']:5s} class={c['class']} hits={c['n_hits_total']}")
        for h in c["hits"][:3]:
            lines.append(f"      - {h.get('ref')}: {h.get('span', '')[:90]!r}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Overlap checks O1-O5 for a candidate post (builds the corpus index itself)")
    ap.add_argument("candidate", help="candidate .md (front matter + text) or .txt")
    ap.add_argument("--run", help="run name or drafts/<run> path; other candidates of the run become O4 siblings")
    ap.add_argument("--exclude", default="", help="comma-separated corpus post ids to exclude (closed over crosspost/variant)")
    ap.add_argument("--root", help="project root (default: $POSTSMITH_ROOT or the repo containing tools/)")
    ap.add_argument("--splits", default="train,heldout,self", help="corpus splits to index (default: train,heldout,self)")
    ap.add_argument("--no-cards", action="store_true", help="do not read cards (disables O3)")
    ap.add_argument("--no-prior-finalists", action="store_true", help="do not compare against drafts/*/final/*.md")
    ap.add_argument("--json", action="store_true", help="JSON output (the default)")
    ap.add_argument("--human", action="store_true", help="short human summary instead of JSON")
    args = ap.parse_args(argv)
    try:
        root = resolve_root(args.root)
        if not root.is_dir():
            raise UserError(f"root is not a directory: {root}")
        cand_path = _resolve_candidate(args.candidate, root)
        if not cand_path.is_file():
            raise UserError(f"candidate not found: {args.candidate}")
        meta, body = split_front_matter(cand_path.read_text(encoding="utf-8"))
        meta = meta if isinstance(meta, dict) else {}
        text = body.rstrip("\n")
        if not text.strip():
            raise UserError(f"candidate has no post text: {args.candidate}")
        splits = tuple(s.strip() for s in args.splits.split(",") if s.strip())
        cfg = load_cfg(root)
        lexicon = load_lexicon(root)
        index = build_index(splits, include_cards=not args.no_cards, include_drafts_final=not args.no_prior_finalists,
                            root=root)
        siblings = collect_siblings(root, cand_path, meta, args.run)
        exclude = {s.strip() for s in args.exclude.split(",") if s.strip()}
        res = run_checks(text, meta, cfg, lexicon, index, siblings, [], exclude)
    except UserError as e:
        common.error(str(e), as_json=True)
        return 0
    except (OSError, UnicodeDecodeError) as e:
        common.error(f"{type(e).__name__}: {e}", as_json=True)
        return 0
    except Exception as e:  # noqa: BLE001 - programmer error: contract says exit 2
        if common.yaml is not None and isinstance(e, common.yaml.YAMLError):
            common.error(f"invalid YAML: {e}", as_json=True)
            return 0
        common.emit({"ok": False, "error": f"internal error: {type(e).__name__}: {e}"})
        return 2
    out = {
        "ok": True,
        "schema": "postsmith.overlap/1",
        "candidate": _relpath(cand_path, root),
        "cid": str(meta.get("cid") or cand_path.stem),
        "platform": meta.get("platform"),
        "run": args.run,
        "checks": res["checks"],
        "excluded": res["excluded"],
        "siblings": [cid for cid, _ in siblings],
        "index": {"root": str(root), "splits": list(splits), "n_posts": len(index["posts"]),
                  "n_prior_finalists": len(index["prior_finalists"]), "n_published": len(index["published"])},
    }
    common.emit(out, as_json=not args.human or args.json, human=_human(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
