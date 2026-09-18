#!/usr/bin/env python3
"""Mechanical checks on annotation cards (contracts section 2, card_spec section 9).

    uv run tools/card_lint.py --post <id> [--root R] [--json]
    uv run tools/card_lint.py --all [--root R] [--json]

Per card: the YAML front matter parses and every required field is present with the right type; every `lines`
citation in beats, expectation_ledger and devices (forms "3", "5-9", "1,4", "3, 5-9") lies within 1..last nonblank
line of the post, where post line 1 is the first line after the post's front matter and blank lines count (a single
citation of a blank line is a problem, a range may span one); archetype, hook.types, angle, device and media
genre/role ids exist in style/taxonomies/*.md (first-column slugs of the markdown tables: hooks.md, structures.md
first table, angles.md, devices.md, media_roles.md genres and roles); moves slugs resolve to an id or alias of
style/moves.md when that file exists; heldout cards keep every quoted field (hook.text, rehook,
distinctive_phrases[], on_media_text[]) at 6 words or fewer.

Output: {"ok": bool, "problems": [{"post_id", "field", "problem"}], "checked": [ids]}. A post or card that does not
exist under --post is a user error ({"ok": false, "error"}); missing taxonomy files are too. Meaning (does line 7
really carry the device?) is the card-verifier's job, not this tool's.
API: lint_post(root, post_id, tax=None, moves_map=None) -> dict ; lint_all(root) -> dict ;
lint_card(card_text, post_meta, post_body, post_id, split, tax, moves_map) -> [problems] ;
find_post(root, post_id) -> (split, path) | None ; card_path / review_path(root, post_id, split) ; post_lines(body).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import moves_lint  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

SPLIT_DIRS: dict[str, str] = {"train": "corpus/posts", "self": "corpus/self", "heldout": "corpus/heldout"}
CARD_DIRS: dict[str, str] = {"train": "corpus/cards", "self": "corpus/cards", "heldout": "corpus/heldout/cards"}
TAXONOMY_FILES: dict[str, str] = {"angles": "angles.md", "hooks": "hooks.md", "structures": "structures.md",
                                  "devices": "devices.md", "media_roles": "media_roles.md"}
CARD_SCHEMA = "postsmith.card/1"
HELDOUT_MAX_WORDS = 6
MAX_HOOK_TYPES = 2
EMOTIONS = ("LOL", "OHHH", "WOW", "WTF", "AWW", "YAY", "NSFW", "FINALLY", "none")
BEATS = ("hook", "rehook", "setup", "complication", "turn", "proof", "escalation", "list", "aside", "punchline",
         "callback", "lesson", "cta", "close", "ps")
POVS = ("first_singular", "second", "first_plural", "third", "mixed")
TENSES = ("past", "present", "mixed")
ADDRESSES = ("direct_you", "none")
GENERIC_RISKS = ("low", "medium", "high")
CAPTION_DEPENDENCIES = ("standalone", "media_dependent")
REPRODUCIBILITIES = ("promptable", "needs_real_photo", "needs_real_screenshot", "needs_real_face")
STANCE_KEYS = ("earnest_ironic", "humble_brash", "warm_cold", "dense_airy", "abstract_specific")
CITATION_FIELDS = ("beats", "expectation_ledger", "devices")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")
_CIT_PART_RE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


class UserError(ValueError):
    """A problem with the inputs (reported as {"ok": false, "error": ...}, exit 0)."""


# --------------------------------------------------------------------------- posts, cards, lines

def find_post(root: Path, post_id: str) -> tuple[str, Path] | None:
    """(split, path) of a post id, looking in corpus/posts, corpus/self, corpus/heldout; None when absent."""
    for split, rel in SPLIT_DIRS.items():
        p = root / rel / f"{post_id}.md"
        if p.is_file():
            return split, p
    return None


def iter_post_ids(root: Path) -> list[tuple[str, str]]:
    """Every (post_id, split) in the corpus, sorted by id (train, self, heldout directories)."""
    out: list[tuple[str, str]] = []
    for split, rel in SPLIT_DIRS.items():
        d = root / rel
        if d.is_dir():
            out.extend((p.stem, split) for p in d.glob("*.md"))
    return sorted(out)


def card_path(root: Path, post_id: str, split: str) -> Path:
    return root / CARD_DIRS[split] / f"{post_id}.md"


def review_path(root: Path, post_id: str, split: str) -> Path:
    return root / CARD_DIRS[split] / "_reviews" / f"{post_id}.md"


def post_lines(body: str) -> list[str]:
    """The post's citable lines: line 1 is the first line after the front matter, blank lines count, trailing blank
    lines are dropped (so len() is the last nonblank line number)."""
    ls = body.replace("\r\n", "\n").split("\n")
    while ls and not ls[-1].strip():
        ls.pop()
    return ls


def parse_citation(value: Any) -> list[tuple[int, int]] | None:
    """'3' | 3 | '5-9' | '1,4' | '3, 5-9' -> [(lo, hi), ...]; None when malformed (including a reversed range)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return [(value, value)] if value >= 0 else None
    if not isinstance(value, str):
        return None
    out: list[tuple[int, int]] = []
    for part in value.split(","):
        m = _CIT_PART_RE.match(part)
        if not m:
            return None
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi < lo:
            return None
        out.append((lo, hi))
    return out or None


def citation_problems(value: Any, lines: list[str]) -> list[str]:
    """Why a `lines` citation does not resolve against the post's lines ([] when it does)."""
    ranges = parse_citation(value)
    if ranges is None:
        return [f"malformed citation {value!r} (use \"3\", \"5-9\" or \"1,4\")"]
    n = len(lines)
    out: list[str] = []
    for lo, hi in ranges:
        if lo < 1 or hi > n:
            out.append(f"cites line{'s' if hi != lo else ''} {lo}{'-' + str(hi) if hi != lo else ''} but the post has "
                       f"lines 1-{n}")
        elif lo == hi and not lines[lo - 1].strip():
            out.append(f"cites line {lo}, which is blank")
    return out


# --------------------------------------------------------------------------- taxonomies

def markdown_tables(text: str) -> list[dict]:
    """Every markdown table as {"section": heading text, "header": [lowercased cells], "rows": [[cells]]}."""
    tables: list[dict] = []
    section = ""
    header: list[str] | None = None
    rows: list[list[str]] = []

    def flush() -> None:
        nonlocal header, rows
        if header is not None:
            tables.append({"section": section, "header": header, "rows": rows})
        header, rows = None, []

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            flush()
            section = line.lstrip("#").strip()
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if header is None:
                header = [c.strip("`* ").lower() for c in cells]
                rows = []
                continue
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and any(cells):
                continue
            rows.append(cells)
        else:
            flush()
    flush()
    return tables


def first_column_slugs(table: dict) -> list[str]:
    out: list[str] = []
    for r in table["rows"]:
        v = (r[0] if r else "").strip("`* ").lower()
        if v and SLUG_RE.match(v) and v not in out:
            out.append(v)
    return out


def _id_tables(text: str) -> list[dict]:
    return [t for t in markdown_tables(text) if t["header"] and t["header"][0] == "id"]


def load_taxonomies(root: Path) -> dict[str, list[str]]:
    """{"hooks", "archetypes", "endings", "angles", "devices", "genres", "roles"} -> ids. Raises UserError when a
    taxonomy file is missing (the ids cannot be checked without it)."""
    tax_dir = root / "style" / "taxonomies"
    texts: dict[str, str] = {}
    for key, name in TAXONOMY_FILES.items():
        p = tax_dir / name
        if not p.is_file():
            raise UserError(f"taxonomy file missing: style/taxonomies/{name}")
        texts[key] = p.read_text(encoding="utf-8")

    def all_ids(key: str) -> list[str]:
        ids: list[str] = []
        for t in _id_tables(texts[key]):
            ids.extend(i for i in first_column_slugs(t) if i not in ids)
        return ids

    def section_ids(key: str, word: str, fallback_index: int) -> list[str]:
        tables = _id_tables(texts[key])
        for t in tables:
            if t["section"].lower().startswith(word):
                return first_column_slugs(t)
        return first_column_slugs(tables[fallback_index]) if len(tables) > fallback_index else []

    structures = _id_tables(texts["structures"])
    return {
        "hooks": all_ids("hooks"),
        "archetypes": first_column_slugs(structures[0]) if structures else [],
        "endings": section_ids("structures", "ending", 1),
        "angles": all_ids("angles"),
        "devices": all_ids("devices"),
        "genres": section_ids("media_roles", "genre", 0),
        "roles": section_ids("media_roles", "role", 1),
    }


def load_moves_map(root: Path) -> dict[str, str] | None:
    """{name: canonical move id} from style/moves.md (ids and aliases); None when the catalogue does not exist."""
    p = root / "style" / "moves.md"
    if not p.is_file():
        return None
    return moves_lint.resolve_aliases(moves_lint.parse_sections(p.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- card checks

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _words(s: str) -> int:
    return len(common.words(s))


def lint_card(card_text: str, post_meta: dict, post_body: str, post_id: str, split: str,
              tax: dict[str, list[str]], moves_map: dict[str, str] | None) -> list[dict]:
    """All problems of one card text against its post. Pure: no file access."""
    problems: list[dict] = []

    def add(field: str, problem: str) -> None:
        problems.append({"post_id": post_id, "field": field, "problem": problem})

    try:
        meta, _body = common.split_front_matter(card_text)
    except Exception as e:  # noqa: BLE001 - yaml errors are the user's problem, reported as such
        add("front_matter", f"YAML error: {str(e).splitlines()[0]}")
        return problems
    if not meta:
        add("front_matter", "missing or empty front matter (--- yaml ---)")
        return problems
    if not isinstance(meta, dict):
        add("front_matter", "front matter is not a mapping")
        return problems

    lines = post_lines(post_body)
    heldout = split == "heldout"

    def req(name: str, kind: str, enum: tuple[str, ...] | None = None, nullable: bool = False) -> Any:
        """Presence + type check; returns the value (or None when missing/invalid)."""
        if name not in meta:
            add(name, "missing required field")
            return None
        v = meta[name]
        if v is None and nullable:
            return None
        ok = {"str": lambda x: isinstance(x, str), "bool": lambda x: isinstance(x, bool),
              "int": lambda x: isinstance(x, int) and not isinstance(x, bool),
              "list": lambda x: isinstance(x, list), "dict": lambda x: isinstance(x, dict),
              "str_or_int": lambda x: isinstance(x, (str, int)) and not isinstance(x, bool)}[kind](v)
        if not ok:
            add(name, f"must be {kind}{' or null' if nullable else ''}, got {type(v).__name__}")
            return None
        if kind == "str" and not v.strip():
            add(name, "must not be empty")
            return None
        if enum is not None and v not in enum:
            add(name, f"{v!r} is not one of {', '.join(enum)}")
            return None
        return v

    schema = req("schema", "str")
    if schema is not None and schema != CARD_SCHEMA:
        add("schema", f"expected {CARD_SCHEMA}, got {schema!r}")
    pid = req("post_id", "str")
    if pid is not None and pid != post_id:
        add("post_id", f"card says {pid!r} but the file is {post_id}")
    req("annotated_by", "str")
    req("verified", "bool")
    pv = req("profile_version_at_annotation", "int")
    if pv is not None and pv < 0:
        add("profile_version_at_annotation", "must be >= 0")
    req("thesis", "str")
    req("subtext", "str")
    arch = req("archetype", "str")
    if arch is not None and arch not in tax["archetypes"]:
        add("archetype", f"{arch!r} is not an id in style/taxonomies/structures.md")
    angle = req("angle", "str")
    if angle is not None and angle not in tax["angles"]:
        add("angle", f"{angle!r} is not an id in style/taxonomies/angles.md")
    req("emotion", "str", enum=EMOTIONS)

    hook = req("hook", "dict")
    if hook is not None:
        text = hook.get("text")
        if not isinstance(text, str) or not text.strip():
            add("hook.text", "must be a non-empty string")
        elif heldout and _words(text) > HELDOUT_MAX_WORDS:
            add("hook.text", f"heldout card: {_words(text)} words (max {HELDOUT_MAX_WORDS})")
        types = hook.get("types")
        if not isinstance(types, list) or not types:
            add("hook.types", "must be a non-empty list of hook type ids")
        else:
            if len(types) > MAX_HOOK_TYPES:
                add("hook.types", f"{len(types)} ids (at most {MAX_HOOK_TYPES})")
            for i, t in enumerate(types):
                if not isinstance(t, str) or t not in tax["hooks"]:
                    add(f"hook.types[{i}]", f"{t!r} is not an id in style/taxonomies/hooks.md")
        afc = hook.get("above_fold_chars")
        if not _is_num(afc) or afc < 0:
            add("hook.above_fold_chars", "must be a non-negative integer")
        if not isinstance(hook.get("standalone"), bool):
            add("hook.standalone", "must be bool")

    rehook = req("rehook", "str", nullable=True)
    if rehook is not None and heldout and _words(rehook) > HELDOUT_MAX_WORDS:
        add("rehook", f"heldout card: {_words(rehook)} words (max {HELDOUT_MAX_WORDS})")

    beats = req("beats", "list")
    if beats is not None:
        if not beats:
            add("beats", "must list at least the hook beat")
        for i, b in enumerate(beats):
            if not isinstance(b, dict):
                add(f"beats[{i}]", "must be a mapping {lines, beat}")
                continue
            for why in citation_problems(b.get("lines"), lines):
                add(f"beats[{i}].lines", why)
            label = b.get("beat")
            if not isinstance(label, str) or label not in BEATS:
                add(f"beats[{i}].beat", f"{label!r} is not one of {', '.join(BEATS)}")

    ledger = req("expectation_ledger", "list")
    if ledger is not None:
        for i, e in enumerate(ledger):
            if not isinstance(e, dict):
                add(f"expectation_ledger[{i}]", "must be a mapping {lines, sets_up, breaks_with}")
                continue
            for why in citation_problems(e.get("lines"), lines):
                add(f"expectation_ledger[{i}].lines", why)
            for k in ("sets_up", "breaks_with"):
                if not isinstance(e.get(k), str) or not e[k].strip():
                    add(f"expectation_ledger[{i}].{k}", "must be a non-empty string")

    req("rhythm", "str_or_int")

    devices = req("devices", "list")
    if devices is not None:
        for i, d in enumerate(devices):
            if not isinstance(d, dict):
                add(f"devices[{i}]", "must be a mapping {device, lines, note}")
                continue
            dev = d.get("device")
            if not isinstance(dev, str) or dev not in tax["devices"]:
                add(f"devices[{i}].device", f"{dev!r} is not an id in style/taxonomies/devices.md")
            for why in citation_problems(d.get("lines"), lines):
                add(f"devices[{i}].lines", why)
            if not isinstance(d.get("note"), str) or not d["note"].strip():
                add(f"devices[{i}].note", "must be a non-empty string")

    moves = req("moves", "list")
    if moves is not None:
        for i, mv in enumerate(moves):
            if not isinstance(mv, str) or not mv.strip():
                add(f"moves[{i}]", "must be a move slug string")
            elif moves_map is not None and mv.strip().lower() not in moves_map:
                add(f"moves[{i}]", f"{mv!r} is not an id or alias in style/moves.md")

    stance = req("stance", "dict")
    if stance is not None:
        for k in STANCE_KEYS:
            v = stance.get(k)
            if not _is_num(v) or not 0 <= v <= 1:
                add(f"stance.{k}", "must be a number in 0..1")

    req("pov", "str", enum=POVS)
    req("tense", "str", enum=TENSES)
    req("address", "str", enum=ADDRESSES)
    req("ending", "str")

    has_media = bool(post_meta.get("media")) if isinstance(post_meta, dict) else False
    ma = meta.get("media_analysis")
    if ma is None:
        if has_media:
            add("media_analysis", "the post has media entries but the card has no media_analysis block")
    elif not isinstance(ma, dict):
        add("media_analysis", "must be a mapping")
    else:
        if not has_media:
            add("media_analysis", "the post has no media but the card carries a media_analysis block")
        for k in ("literal", "style_notes", "what_it_adds"):
            if not isinstance(ma.get(k), str) or not ma[k].strip():
                add(f"media_analysis.{k}", "must be a non-empty string")
        omt = ma.get("on_media_text")
        if not isinstance(omt, list):
            add("media_analysis.on_media_text", "must be a list of strings")
        else:
            for i, t in enumerate(omt):
                if not isinstance(t, str):
                    add(f"media_analysis.on_media_text[{i}]", "must be a string")
                elif heldout and _words(t) > HELDOUT_MAX_WORDS:
                    add(f"media_analysis.on_media_text[{i}]",
                        f"heldout card: {_words(t)} words (max {HELDOUT_MAX_WORDS})")
        genre = ma.get("genre")
        if not isinstance(genre, str) or genre not in tax["genres"]:
            add("media_analysis.genre", f"{genre!r} is not a genre id in style/taxonomies/media_roles.md")
        role = ma.get("role")
        if not isinstance(role, str) or role not in tax["roles"]:
            add("media_analysis.role", f"{role!r} is not a role id in style/taxonomies/media_roles.md")
        if ma.get("caption_dependency") not in CAPTION_DEPENDENCIES:
            add("media_analysis.caption_dependency", f"must be one of {', '.join(CAPTION_DEPENDENCIES)}")
        if ma.get("reproducibility") not in REPRODUCIBILITIES:
            add("media_analysis.reproducibility", f"must be one of {', '.join(REPRODUCIBILITIES)}")
        video = ma.get("video", None)
        if video is not None and not isinstance(video, dict):
            add("media_analysis.video", "must be null or a mapping")

    req("why_it_works", "str")
    req("what_would_break_it", "str")
    phrases = req("distinctive_phrases", "list")
    if phrases is not None:
        for i, ph in enumerate(phrases):
            if not isinstance(ph, str) or not ph.strip():
                add(f"distinctive_phrases[{i}]", "must be a non-empty string")
            elif heldout and _words(ph) > HELDOUT_MAX_WORDS:
                add(f"distinctive_phrases[{i}]", f"heldout card: {_words(ph)} words (max {HELDOUT_MAX_WORDS})")
    req("generic_risk", "str", enum=GENERIC_RISKS)
    req("humor_attempted", "bool")
    eng = req("engagement", "dict")
    if eng is not None:
        for k, v in eng.items():
            if v is not None and not _is_num(v):
                add(f"engagement.{k}", "must be a number or null")
    return problems


# --------------------------------------------------------------------------- per post / per corpus

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def lint_post(root: Path | str, post_id: str, tax: dict | None = None,
              moves_map: dict[str, str] | None | bool = False) -> dict:
    """Lint the card of one post. Raises UserError when the post or its card does not exist.
    `moves_map=False` (default) loads style/moves.md itself; pass None to skip the moves check."""
    root = Path(root).resolve()
    if not SAFE_ID_RE.match(post_id or ""):
        raise UserError(f"not a post id: {post_id!r}")
    found = find_post(root, post_id)
    if found is None:
        raise UserError(f"post {post_id} not found under corpus/posts, corpus/self or corpus/heldout")
    split, ppath = found
    cpath = card_path(root, post_id, split)
    if not cpath.is_file():
        raise UserError(f"no card for {post_id} (expected {_relpath(root, cpath)})")
    tax = tax or load_taxonomies(root)
    if moves_map is False:
        moves_map = load_moves_map(root)
    post_meta, post_body = common.split_front_matter(_read(ppath))
    problems = lint_card(_read(cpath), post_meta if isinstance(post_meta, dict) else {}, post_body, post_id, split,
                         tax, moves_map)
    return {"ok": not problems, "post_id": post_id, "split": split, "card": _relpath(root, cpath),
            "problems": problems, "checked": [post_id]}


def lint_all(root: Path | str) -> dict:
    """Lint every card under corpus/cards and corpus/heldout/cards. A card whose post is missing is a problem."""
    root = Path(root).resolve()
    tax = load_taxonomies(root)
    moves_map = load_moves_map(root)
    problems: list[dict] = []
    checked: list[str] = []
    seen: set[str] = set()
    for rel in sorted(set(CARD_DIRS.values())):
        d = root / rel
        if not d.is_dir():
            continue
        for cpath in sorted(d.glob("*.md")):
            pid = cpath.stem
            if pid in seen:
                problems.append({"post_id": pid, "field": "card", "problem": f"a second card exists at {rel}/{pid}.md"})
                continue
            seen.add(pid)
            found = find_post(root, pid)
            if found is None:
                problems.append({"post_id": pid, "field": "card", "problem": "no post with this id in the corpus"})
                continue
            split, ppath = found
            if card_path(root, pid, split) != cpath:
                problems.append({"post_id": pid, "field": "card",
                                 "problem": f"card is under {rel} but the post is in the {split} split"})
                continue
            post_meta, post_body = common.split_front_matter(_read(ppath))
            problems.extend(lint_card(_read(cpath), post_meta if isinstance(post_meta, dict) else {}, post_body,
                                      pid, split, tax, moves_map))
            checked.append(pid)
    return {"ok": not problems, "problems": problems, "checked": checked, "n_cards": len(checked)}


def _relpath(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint annotation cards: YAML shape, line citations, taxonomy ids, "
                                             "move slugs and the heldout 6-word cap.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--post", default=None, help="post id whose card to lint")
    g.add_argument("--all", action="store_true", help="lint every card under corpus/cards and corpus/heldout/cards")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve() if a.root else common.ROOT
    try:
        doc = lint_all(root) if a.all else lint_post(root, a.post)
    except (UserError, FileNotFoundError, OSError) as e:
        common.error(str(e))
        return 0
    common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
