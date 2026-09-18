#!/usr/bin/env python3
"""Tier 0: deterministic checks on one candidate (contracts §5, §16).

Composes platform_check, stylometry + envelope_check, ai_tells and overlap_check, imported from tools/ at
load time. A check module that is missing, returns the wrong shape or raises is a programmer error: Tier 0
stops with ``CheckModuleError`` (CLI exit 2) rather than recording an advisory placeholder, so a broken
module can never let a candidate through.

Base-rate downgrade (config ``base_rate_downgrade``): ai_tells applies it to its own checks; tier0 applies
the same rule to P6_emoji, P14_dashes and P16_broetry, which platform_check and envelope_check emit
undowngraded.

Outputs, unless --no-write:
  <round>/candidates/<cid>.txt     post text only, which is what judges receive
  <round>/scores/<cid>.tier0.json  the §5 document
A candidate outside a ``candidates/`` directory gets both files beside it, unless ``--out`` names the round
directory to write ``candidates/`` and ``scores/`` under.

CLI: tier0.py <candidate.md> [--run R] [--cid ID] [--siblings a.md,b.md] [--exclude ids] [--lens scope]
               [--as-golden] [--no-write] [--out DIR] [--root PROJECT_ROOT] [--json]
``--root`` selects the project root (corpus, config, rubric, style), like the other tools. The cid is always
the file stem, or ``--cid``. A front-matter cid that disagrees, a claims list with a bad shape or source, and
front matter that does not parse are P0_schema hard fails recorded in the tier0 JSON, never reasons to write
nothing. In small-corpus mode (common.small_corpus_mode) the envelope checks are widened and advisory.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_tells  # noqa: E402
import common  # noqa: E402
import envelope_check  # noqa: E402
import overlap_check  # noqa: E402
import platform_check  # noqa: E402
import stylometry  # noqa: E402

SCHEMA = "postsmith.tier0/1"

CHECK_IDS: list[str] = [
    "P0_schema", "P1_length", "P2_fold", "P_min_words", "P3_hashtags", "P4_links", "P5_markup", "P6_emoji",
    "P7_bait", "P8_opener", "P9_residue", "P10_contrast_flip", "P11_cluster", "P12_closer", "P13_specifics",
    "P14_dashes", "P15_burstiness", "P16_broetry", "P17_lists", "P18_hedges", "P19_clickbait", "P20_misc",
    "O1_ngram", "O2_phrases", "O3_skeleton", "O4_sibling", "O5_published", "E1_envelope",
]

MODULE_CHECKS: dict[str, list[str]] = {
    "platform_check": ["P1_length", "P2_fold", "P_min_words", "P3_hashtags", "P4_links", "P5_markup", "P6_emoji"],
    "envelope_check": ["E1_envelope", "P14_dashes", "P15_burstiness", "P16_broetry"],
    "ai_tells": ["P7_bait", "P8_opener", "P9_residue", "P10_contrast_flip", "P11_cluster", "P12_closer",
                 "P13_specifics", "P17_lists", "P18_hedges", "P19_clickbait", "P20_misc"],
    "overlap_check": ["O1_ngram", "O2_phrases", "O3_skeleton", "O4_sibling", "O5_published"],
}

REQUIRED_META = ["claims", "angle_sheet", "hook_type", "ending", "media_intent.decision"]
# contracts section 4: claims: [{text, source}] with source one of persona.<section>#<n> | brief.fact#N |
# brief.user_detail | opinion | joke. Anything else is writer-controlled text reaching the persona judge.
CLAIM_SOURCE_RE = re.compile(r"^(?:persona\.[a-z_]+#\d+|brief\.fact#\d+|brief\.user_detail|opinion|joke)$")
CLAIM_TEXT_MAX = 300
VALID_CLASSES = {"hard", "soft", "flag", "advisory"}
PLATFORMS = {"linkedin", "x"}
# golden/oracle items are expected na here: health passes them, aggregate reads na as na, not hold.
GOLDEN_EXPECTED_NA = ["register_match_self", "persona_fit", "claims", "level_and_move"]


class CheckModuleError(RuntimeError):
    """A check module is missing, returned the wrong shape or raised. Programmer error, never masked."""


# --------------------------------------------------------------------------- module composition

def _call(module: Any, module_name: str, fn_name: str, *args: Any, **kwargs: Any) -> dict:
    """Call tools/<module_name>.<fn_name>; any failure is a CheckModuleError."""
    fn = getattr(module, fn_name, None) if module is not None else None
    if fn is None:
        raise CheckModuleError(f"check module {module_name}.{fn_name} is not available")
    try:
        res = fn(*args, **kwargs)
    except Exception as exc:
        raise CheckModuleError(f"{module_name}.{fn_name} raised {type(exc).__name__}: {exc}") from exc
    if not isinstance(res, dict):
        raise CheckModuleError(f"{module_name}.{fn_name} returned {type(res).__name__}, expected dict")
    return res


def _normalize_check(cid: str, res: Any, module: str) -> dict:
    """Validate a module's check result against the §5 shape: class, pass, evidence list."""
    if not isinstance(res, dict):
        raise CheckModuleError(f"{module} returned a non-dict result for {cid}")
    out = dict(res)
    if out.get("class") not in VALID_CLASSES:
        raise CheckModuleError(f"{module} set an invalid class {out.get('class')!r} for {cid}")
    if not isinstance(out.get("pass"), bool):
        raise CheckModuleError(f"{module} returned a non-boolean pass for {cid}")
    if not isinstance(out.get("evidence"), list):
        out["evidence"] = []
    out.setdefault("downgraded", False)
    return out


def _take_checks(module_name: str, res: dict, ids: list[str]) -> dict[str, dict]:
    src = res.get("checks")
    if not isinstance(src, dict):
        raise CheckModuleError(f"{module_name}.run_checks returned no 'checks' dict")
    out: dict[str, dict] = {}
    for cid in ids:
        if cid not in src:
            raise CheckModuleError(f"{cid} missing from {module_name}.run_checks output")
        out[cid] = _normalize_check(cid, src[cid], module_name)
    return out


def apply_base_rate_downgrade(checks: dict[str, dict], cfg: dict, base_rates: dict | None) -> dict[str, dict]:
    """Downgrade checks in config.base_rate_downgrade.applies_to whose corpus base rate is over the
    threshold: hard -> flag, soft -> advisory, recording class_original and base_rate. Idempotent, so a check
    its own module already downgraded keeps its class. Returns `checks` for chaining."""
    fn = getattr(ai_tells, "apply_downgrade", None) if ai_tells is not None else None
    if fn is None:
        raise CheckModuleError("check module ai_tells.apply_downgrade is not available")
    fn(checks, cfg, base_rates)
    return checks


# --------------------------------------------------------------------------- helpers

def _get_path(meta: dict, dotted: str) -> tuple[bool, Any]:
    cur: Any = meta
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def validate_claims(claims: Any) -> list[dict]:
    """Shape check for the front-matter claims list (contracts section 4): each row is
    {text: str <= CLAIM_TEXT_MAX, source: str matching CLAIM_SOURCE_RE}. Returns [{field, value, why}]
    problems quoting the offending value."""
    problems: list[dict] = []
    if claims is None:
        return problems
    if not isinstance(claims, list):
        return [{"field": "claims", "value": _short(claims), "why": "claims must be a list of {text, source}"}]
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            problems.append({"field": f"claims[{i}]", "value": _short(c), "why": "claim must be a {text, source} mapping"})
            continue
        text = c.get("text")
        src = c.get("source")
        if not isinstance(text, str) or not text.strip():
            problems.append({"field": f"claims[{i}].text", "value": _short(text), "why": "claim text must be a non-empty string"})
        elif len(text) > CLAIM_TEXT_MAX:
            problems.append({"field": f"claims[{i}].text", "value": _short(text),
                             "why": f"claim text is {len(text)} chars, above the {CLAIM_TEXT_MAX} cap"})
        if not isinstance(src, str) or not CLAIM_SOURCE_RE.match(src.strip()):
            problems.append({"field": f"claims[{i}].source", "value": _short(src),
                             "why": "claim source must be persona.<section>#<n>, brief.fact#N, brief.user_detail, opinion or joke"})
        extra = sorted(set(c) - {"text", "source"})
        if extra:
            problems.append({"field": f"claims[{i}]", "value": ", ".join(extra), "why": "claim rows carry only text and source"})
    return problems


def _short(v: Any, n: int = 160) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n - 1] + "…"


def check_schema(meta: dict, cid: str | None = None) -> dict:
    """P0_schema: the required front-matter keys are present (contracts section 4), the claims rows are well
    formed, and a declared cid equals the file stem `cid`. `angle` is accepted as an alias of angle_sheet."""
    missing: list[str] = []
    aliases: list[str] = []
    for key in REQUIRED_META:
        present, value = _get_path(meta, key)
        if key == "angle_sheet" and not present and "angle" in meta:
            aliases.append("angle->angle_sheet")
            continue
        if not present or value is None:
            missing.append(key)
    platform = meta.get("platform")
    if platform not in PLATFORMS:
        missing.append("platform")
    invalid = validate_claims(meta.get("claims")) if "claims" in meta and meta.get("claims") is not None else []
    declared = meta.get("cid")
    if cid is not None and declared not in (None, "") and str(declared) != cid:
        invalid.append({"field": "cid", "value": str(declared), "why": f"cid {declared} != filename {cid}"})
    result: dict[str, Any] = {"class": "hard", "pass": not missing and not invalid, "missing": missing,
                              "invalid": invalid, "evidence": [], "downgraded": False}
    if aliases:
        result["aliases_used"] = aliases
    if missing:
        result["evidence"].append({"span": "", "why": "front matter missing: " + ", ".join(missing)})
    for pr in invalid:
        result["evidence"].append({"span": pr["value"], "why": f"{pr['field']}: {pr['why']}"})
    return result


def synthesize_golden_meta(meta: dict, path: Path) -> dict:
    """Minimal candidate front matter for golden and oracle items so the rest of Tier 0 has what it needs."""
    out = dict(meta)
    out.setdefault("schema", "postsmith.candidate/1")
    out.setdefault("cid", meta.get("cid") or meta.get("post_id") or path.stem)
    platform = meta.get("platform") or "linkedin"
    out["platform"] = platform if platform in PLATFORMS else "linkedin"
    out.setdefault("claims", [])
    out.setdefault("angle_sheet", {"candidates": [], "pick": None})
    out.setdefault("hook_type", None)
    out.setdefault("ending", None)
    mi = out.get("media_intent")
    if not isinstance(mi, dict):
        mi = {}
    mi.setdefault("decision", "none")
    out["media_intent"] = mi
    out.setdefault("assignment", {"lens": None})
    out["as_golden"] = True
    return out


def _parse_run_and_round(path: Path, meta: dict, run: str | None) -> tuple[str | None, int]:
    parts = list(path.resolve().parts)
    run_name = run
    rnd: int | None = None
    if "drafts" in parts:
        i = parts.index("drafts")
        if run_name is None and len(parts) > i + 1:
            run_name = parts[i + 1]
    for p in parts:
        m = re.fullmatch(r"round(\d+)", p)
        if m:
            rnd = int(m.group(1))
    if isinstance(meta.get("round"), int):
        rnd = meta["round"]
    if rnd is None:
        m = re.match(r"r(\d+)-", str(meta.get("cid") or path.stem))
        rnd = int(m.group(1)) if m else 1
    if run_name is None and meta.get("run"):
        run_name = str(meta["run"])
    return run_name, rnd


def _output_dirs(path: Path, out_dir: str | None) -> tuple[Path, Path]:
    """(candidates_dir, scores_dir) for the .txt and .tier0.json."""
    if out_dir:
        r = Path(out_dir)
        if not r.is_absolute():
            r = common.ROOT / r
        return r / "candidates", r / "scores"
    parent = path.resolve().parent
    if parent.name == "candidates":
        return parent, parent.parent / "scores"
    return parent, parent


def _read_pairs(paths: list[str] | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for p in paths or []:
        pp = Path(p)
        if not pp.is_absolute():
            pp = common.ROOT / pp
        if not pp.exists():
            continue
        try:
            _meta, body = common.split_front_matter(pp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a sibling with broken YAML still has a body to compare against
            body = _body_after_front_matter(pp.read_text(encoding="utf-8"))
        out.append((pp.stem, body.rstrip("\n")))  # the file stem is the authoritative cid
    return out


def _body_after_front_matter(raw: str) -> str:
    """Post text after a (possibly unparseable) front-matter block."""
    m = common._FM_RE.match(raw)
    return raw[m.end():] if m else raw


def _published_pairs() -> list[tuple[str, str]]:
    d = common.ROOT / "memory" / "published"
    if not d.exists():
        return []
    out: list[tuple[str, str]] = []
    for p in sorted(d.glob("*.md")):
        _, body = common.split_front_matter(p.read_text(encoding="utf-8"))
        out.append((p.stem, body.rstrip("\n")))
    return out


def _small_corpus_mode(profile: dict | None, cfg: dict, platform: str | None = None) -> bool:
    """The config.corpus rule over the train split only (shared with status.py via
    common.small_corpus_mode), asked about the candidate's own platform: a post written for a platform the
    corpus has no reference for is judged against a widened, advisory envelope however large the corpus is on
    the other platform."""
    return common.small_corpus_mode(cfg, platform=platform)


def _pick_scope(meta: dict, lens_scope: str | None, profile: dict | None, platform: str, cfg: dict) -> str:
    if lens_scope:
        return lens_scope
    lens = (meta.get("assignment") or {}).get("lens") if isinstance(meta.get("assignment"), dict) else None
    scopes = (profile or {}).get("scopes", {}) if profile else {}
    if lens:
        return f"author:{lens}"
    self_min = int(cfg.get("corpus", {}).get("self_min_samples", 5))
    if scopes.get("self", {}).get("n", 0) >= self_min:
        return "self"
    if f"platform:{platform}" in scopes:
        return f"platform:{platform}"
    return "corpus"


def count_flags(doc: dict) -> int:
    """Tier 0 checks that need action: failed, or passed the gate with a flag raised, such as P2_fold's
    word-boundary cut. Advisory checks are excluded. This is the O4 tie-break metric."""
    return sum(1 for c in doc.get("checks", {}).values()
               if common.check_needs_action(c) and c.get("class") != "advisory")


def pick_weaker(a: dict | str | Path, b: dict | str | Path) -> dict:
    """Sibling near-duplicate rule (O4): return the WEAKER of two tier0 documents, the one with more Tier 0
    flags, then the longer one. On a tie (same flags, same length) the second argument is the weaker."""
    da = _load_doc(a)
    db = _load_doc(b)
    fa, fb = count_flags(da), count_flags(db)
    if fa != fb:
        return da if fa > fb else db
    la, lb = int(da.get("chars", 0) or 0), int(db.get("chars", 0) or 0)
    if la != lb:
        return da if la > lb else db
    return db


def _load_doc(x: dict | str | Path) -> dict:
    if isinstance(x, dict):
        return x
    p = Path(x)
    if not p.is_absolute():
        p = common.ROOT / p
    return json.loads(p.read_text(encoding="utf-8"))


def _load_inputs() -> tuple[dict, dict, dict, dict | None]:
    """(cfg, lexicon, patterns, profile) from the current project root. Bad project state is a user error."""
    try:
        cfg = common.load_config()
    except FileNotFoundError as exc:
        raise ValueError(f"config not found: {exc}") from exc
    lexicon = common.load_lexicon()
    try:
        patterns = common.load_patterns()
    except FileNotFoundError as exc:
        raise ValueError(f"rubric patterns not found: {exc}") from exc
    try:
        profile = common.load_profile()
    except json.JSONDecodeError as exc:
        raise ValueError(f"style/profile.json is not valid JSON: {exc}") from exc
    return cfg, lexicon, patterns, profile


# --------------------------------------------------------------------------- main entry

def run(candidate_path: str, run: str | None = None, siblings: list[str] | None = None,
        exclude_ids: set[str] | None = None, lens_scope: str | None = None, as_golden: bool = False,
        write: bool = True, out_dir: str | None = None, root: str | None = None, cid: str | None = None) -> dict:
    """Run Tier 0 on one candidate and return the §5 document.

    Raises FileNotFoundError / ValueError on bad input and CheckModuleError when a check module is broken.
    `root` points every module at another project root for the duration of the call; `out_dir` is the round
    directory to write candidates/ and scores/ under. The cid is the candidate's file stem, or `cid` when
    given; a front-matter cid that disagrees is a P0_schema hard fail, never a different output name.
    """
    with common.use_root(root):
        return _run(candidate_path, run, siblings, exclude_ids, lens_scope, as_golden, write, out_dir, cid)


def _run(candidate_path: str, run: str | None, siblings: list[str] | None, exclude_ids: set[str] | None,
         lens_scope: str | None, as_golden: bool, write: bool, out_dir: str | None, cid_override: str | None = None) -> dict:
    path = Path(candidate_path).expanduser()
    if not path.is_absolute():
        path = path.resolve() if path.exists() else common.ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"candidate not found: {common.rel(path)}")
    raw = path.read_text(encoding="utf-8")
    yaml_error: str | None = None
    try:
        meta, body = common.split_front_matter(raw)
    except Exception as exc:  # broken YAML is a writer error: Tier 0 records it and still runs
        if as_golden:
            raise ValueError(f"front matter is not valid YAML: {exc}") from exc
        yaml_error = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        meta, body = {}, _body_after_front_matter(raw)
    if not isinstance(meta, dict):
        meta = {}
    text = body.rstrip("\n")
    cid = str(cid_override or path.stem)

    checks: dict[str, dict] = {}
    if as_golden:
        meta = synthesize_golden_meta(meta, path)
        checks["P0_schema"] = {"class": "hard", "pass": True, "skipped": True, "note": "as-golden: front matter synthesized",
                               "evidence": [], "downgraded": False}
    else:
        p0 = check_schema(meta, cid)
        if yaml_error:
            p0["pass"] = False
            p0["missing"] = ["front matter"] + [m for m in p0["missing"] if m != "front matter"]
            p0["yaml_error"] = yaml_error
            p0["evidence"].insert(0, {"span": "", "why": f"front matter is not valid YAML: {yaml_error}"})
        checks["P0_schema"] = p0

    declared_cid = meta.get("cid")
    platform = meta.get("platform") if meta.get("platform") in PLATFORMS else "linkedin"
    run_name, round_k = _parse_run_and_round(path, meta, run)
    cfg, lexicon, patterns, profile = _load_inputs()
    base_rates = (profile or {}).get("base_rates") if profile else None
    lang = common.detect_lang(text) if text.strip() else "en"
    modules: dict[str, str] = {}

    # ---- platform_check: P1, P2, P_min_words, P3, P4, P5, P6
    pc = _call(platform_check, "platform_check", "run_checks", text, platform, meta, cfg)
    modules["platform_check"] = "ok"
    checks.update(apply_base_rate_downgrade(_take_checks("platform_check", pc, MODULE_CHECKS["platform_check"]),
                                            cfg, base_rates))
    chars = int(pc.get("chars", len(text)) or len(text))
    x_len = pc.get("x_len", common.x_count(text, cfg["platforms"]["x"]) if platform == "x" else None)
    fold_preview = pc.get("fold_preview") or text[: int(cfg["platforms"]["linkedin"].get("fold_mobile_chars", 140))]
    advisory: dict[str, Any] = dict(pc["advisory"]) if isinstance(pc.get("advisory"), dict) else {}

    # ---- stylometry + envelope_check: E1, P14, P15, P16
    scope = _pick_scope(meta, lens_scope, profile, platform, cfg)
    feats = _call(stylometry, "stylometry", "features", text, platform, lang, lexicon, patterns)
    modules["stylometry"] = "ok"
    if "fk_grade" in feats and "fk_grade" not in advisory:
        advisory["fk_grade"] = feats["fk_grade"]
    self_n = int((profile or {}).get("scopes", {}).get("self", {}).get("n", 0) or 0) if profile else 0
    self_scope = "self" if self_n >= int(cfg.get("corpus", {}).get("self_min_samples", 5)) else None
    small_corpus = _small_corpus_mode(profile, cfg, platform)
    ec = _call(envelope_check, "envelope_check", "run_checks", feats, scope, profile, cfg, self_scope,
               small_corpus=small_corpus)
    modules["envelope_check"] = "ok"
    checks.update(apply_base_rate_downgrade(_take_checks("envelope_check", ec, MODULE_CHECKS["envelope_check"]),
                                            cfg, base_rates))
    envelope: dict[str, Any] = {"scope": scope, "score": None, "out": []}
    if isinstance(ec.get("envelope"), dict):
        envelope = {**envelope, **ec["envelope"]}
        envelope.setdefault("scope", scope)

    # ---- ai_tells: P7-P13, P17-P20 (downgrade applied inside the module)
    at = _call(ai_tells, "ai_tells", "run_checks", text, platform, meta, cfg, lexicon, patterns, base_rates)
    modules["ai_tells"] = "ok"
    checks.update(_take_checks("ai_tells", at, MODULE_CHECKS["ai_tells"]))
    hits: dict[str, list] = at["hits"] if isinstance(at.get("hits"), dict) else {}

    # ---- overlap_check: O1-O5
    excl = set(exclude_ids or set())
    if as_golden:
        for key in ("post_id", "crosspost_of", "variant_of"):
            if meta.get(key):
                excl.add(str(meta[key]))
    sib_pairs = [(c, t) for c, t in _read_pairs(siblings) if c != cid]
    index = _call(overlap_check, "overlap_check", "build_index", exclude_run=run_name)
    oc = _call(overlap_check, "overlap_check", "run_checks", text, meta, cfg, lexicon, index, sib_pairs,
               _published_pairs(), excl)
    modules["overlap_check"] = "ok"
    checks.update(_take_checks("overlap_check", oc, MODULE_CHECKS["overlap_check"]))

    ordered = {k: checks[k] for k in CHECK_IDS if k in checks}
    for k, v in checks.items():
        ordered.setdefault(k, v)

    nb = common.nonblank_lines(text)
    advisory.setdefault("first_line_words", len(common.words(nb[0])) if nb else 0)
    advisory.setdefault("question_opener", bool(nb) and nb[0].rstrip().endswith("?"))
    advisory.setdefault("reading_time_s", round(len(common.words(text)) / 3.8) if text else 0)
    if platform == "linkedin":
        lo, hi = cfg["platforms"]["linkedin"].get("length_band_advisory", [1000, 2500])
        advisory.setdefault("li_length_band", "in" if lo <= chars <= hi else ("short" if chars < lo else "long"))

    cand_dir, scores_dir = _output_dirs(path, out_dir)
    txt_path = cand_dir / f"{cid}.txt"
    json_path = scores_dir / f"{cid}.tier0.json"
    assignment = meta.get("assignment") if isinstance(meta.get("assignment"), dict) else {}
    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "run": run_name,
        "cid": cid,
        "declared_cid": str(declared_cid) if declared_cid not in (None, "") else None,
        "round": round_k,
        "platform": platform,
        "writer": meta.get("writer"),
        "lens": assignment.get("lens"),
        "candidate_sha": common.content_sha(text),
        "candidate_path": common.rel(path),
        "text_path": common.rel(txt_path),
        "chars": chars,
        "x_len": x_len,
        "fold_preview": fold_preview,
        "lang": lang,
        "checks": ordered,
        "hits": hits,
        "advisory": advisory,
        "envelope": envelope,
        "small_corpus_mode": small_corpus,
        "as_golden": bool(as_golden),
        "expected_na": GOLDEN_EXPECTED_NA if as_golden else [],
        "profile_version": (profile or {}).get("profile_version") if profile else None,
        "modules": modules,
        "hard_fail": any(c.get("class") == "hard" and not c.get("pass", True) for c in ordered.values()),
        "n_flags": 0,
        "generated_at": common.now_iso(),
    }
    doc["n_flags"] = count_flags(doc)
    if write:
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(text + "\n", encoding="utf-8")
        common.write_json(json_path, doc)
    return doc


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tier 0 deterministic checks on one candidate (writes <cid>.txt and <cid>.tier0.json).")
    ap.add_argument("candidate", help="path to the candidate .md (front matter + post text)")
    ap.add_argument("--run", help="run id (default: parsed from the path drafts/<run>/...)")
    ap.add_argument("--siblings", help="comma-separated sibling candidate .md paths for O4_sibling")
    ap.add_argument("--exclude", help="comma-separated corpus post ids to exclude from overlap (oracle items)")
    ap.add_argument("--lens", dest="lens_scope", help="envelope scope, e.g. author:lara-acosta, self, corpus")
    ap.add_argument("--as-golden", action="store_true", help="synthesize minimal front matter and skip P0_schema")
    ap.add_argument("--no-write", action="store_true", help="do not write the .txt / .tier0.json files")
    ap.add_argument("--out", help="round directory to write candidates/ and scores/ under")
    ap.add_argument("--root", help="project root (default: env POSTSMITH_ROOT / auto-detected)")
    ap.add_argument("--cid", help="candidate id (default: the file stem; a differing front-matter cid fails P0_schema)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    try:
        doc = run(args.candidate, run=args.run,
                  siblings=[s for s in (args.siblings or "").split(",") if s.strip()] or None,
                  exclude_ids={e.strip() for e in (args.exclude or "").split(",") if e.strip()} or None,
                  lens_scope=args.lens_scope, as_golden=args.as_golden, write=not args.no_write,
                  out_dir=args.out, root=args.root, cid=args.cid)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        common.error(str(exc))
        return 0
    except CheckModuleError as exc:
        common.error(f"programmer error: {exc}", code=2)
        return 2
    common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
