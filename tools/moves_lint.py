#!/usr/bin/env python3
"""moves_lint.py: structural checks on the moves catalogue `style/moves.md` (contracts section 17).

    uv run tools/moves_lint.py [--root R] [--json]

The catalogue is markdown: one `### <slug>` section per move with `key: value` lines (optionally bulleted with
`- `). Keys: mechanism, trigger, shape, seen_in, execute_without_copying, risk, platforms, aliases. `seen_in`,
`platforms` and `aliases` are lists, written either as a bracket list (`seen_in: [kessler_001 L1-4, okonkwo_002]`)
or as a YAML list (`seen_in:` then `- kessler_001 L1-4` lines). A section that carries `merged_into: <slug>` is an
alias stub, not a move: it keeps an old id resolving to the move it was merged into.

Checks: ids are unique slugs `[a-z0-9_]+`; every move has mechanism, trigger, shape, execute_without_copying and at
least 2 well-formed `seen_in` citations (`<post_id>` or `<post_id> L1-4`; a cited post must exist in the corpus when
the corpus has posts); `platforms` entries are linkedin|x; aliases (inline and stubs) resolve to exactly one real
move, never to another real id, with no cycles; every key of the `## Moves scoreboard` table in `memory/topics.md`
resolves through ids or aliases.

Output: {"ok": bool, "problems": [{"move", "field", "problem"}], "moves": n, "ids": [...], "aliases": {alias: id}}.
API: parse_moves(text) -> list[dict] (canonical moves, stub ids folded into `aliases`; run_next reads the
catalogue through this, while matrix.py keeps its own tolerant parser) ; parse_sections(text) -> list[dict]
(every section, stubs included, for lint) ; resolve_aliases(sections) -> dict[name, canonical_id] ;
lint_text(text, corpus_ids, scoreboard) -> dict ; lint(root) -> dict.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import matrix  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9_]+$")
POST_ID_RE = re.compile(r"^[a-z][a-z0-9\-]*_\d{3,}$")
CITATION_RE = re.compile(r"^([a-z][a-z0-9\-]*_\d{3,})(?:\s+L(\d+)(?:-(\d+))?)?$")
REQUIRED_KEYS = ("mechanism", "trigger", "shape", "seen_in", "execute_without_copying")
LIST_KEYS = ("seen_in", "platforms", "aliases")
KNOWN_KEYS = REQUIRED_KEYS + ("risk", "platforms", "aliases", "merged_into")
PLATFORMS = ("linkedin", "x")
MIN_CITATIONS = 2
SPLIT_DIRS = ("corpus/posts", "corpus/self", "corpus/heldout")

_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")   # the whole heading is the id: lint reports a non-slug, never skips
_OTHER_HEADING_RE = re.compile(r"^#{1,2}\s")
_KEY_RE = re.compile(r"^\s*(?:[-*]\s+)?[*_`]*([A-Za-z_][A-Za-z0-9_ ]*?)[*_`]*\s*:\s*(.*)$")
_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*)$")


class UserError(ValueError):
    """A problem with the inputs (reported as {"ok": false, "error": ...}, exit 0)."""


# --------------------------------------------------------------------------- parsing

def _split_list(value: str, comma_only: bool) -> list[str]:
    """'[a, b]' | 'a, b' (| 'a b' unless comma_only) -> ['a', 'b']; quotes and backticks stripped."""
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    parts = v.split(",") if comma_only else re.split(r"[,\s]+", v)
    return [p.strip().strip("'\"`") for p in parts if p.strip().strip("'\"`")]


def _new_move(slug: str, line_no: int) -> dict:
    return {"id": slug, "line": line_no, "mechanism": "", "trigger": "", "shape": "", "execute_without_copying": "",
            "risk": "", "seen_in": [], "platforms": [], "aliases": [], "merged_into": None, "fields": {}}


def _set_key(move: dict, key: str, value: str) -> None:
    if key in LIST_KEYS:
        items = _split_list(value, comma_only=(key == "seen_in"))
        move[key] = [i.lower() for i in items] if key != "seen_in" else items
    elif key == "merged_into":
        move["merged_into"] = value.strip().strip("'\"`").lower() or None
    elif key in KNOWN_KEYS:
        move[key] = value.strip()
    else:
        move["fields"][key] = value.strip()


def parse_sections(text: str) -> list[dict]:
    """Parse the catalogue into one dict per `### <slug>` section, in file order, alias stubs included.

    Each dict: id (as written, lowercased), line (1-based heading line), mechanism, trigger, shape,
    execute_without_copying, risk (str, "" when absent), seen_in (list of citation strings, verbatim), platforms and
    aliases (lowercased lists), merged_into (str | None), fields (any other key: value pairs). Values are
    single-line; an indented continuation line is appended to the previous scalar. A `## ` or `# ` heading ends
    the current section.
    """
    moves: list[dict] = []
    current: dict | None = None
    pending_list: str | None = None   # list key whose items follow on `- item` lines
    last_scalar: str | None = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        hm = _HEADING_RE.match(line)
        if hm:
            if current is not None:
                moves.append(current)
            current = _new_move(hm.group(1).strip("`").strip().lower(), n)
            pending_list, last_scalar = None, None
            continue
        if _OTHER_HEADING_RE.match(line):
            if current is not None:
                moves.append(current)
            current, pending_list, last_scalar = None, None, None
            continue
        if current is None or not line.strip():
            continue
        indented = line[:1].isspace()
        im = _ITEM_RE.match(line)
        km = _KEY_RE.match(line)
        key = km.group(1).strip().lower().replace(" ", "_") if km else None
        # While a YAML list is open, a bulleted line is one of its items unless it is an unindented known key
        # (`- risk: ...` closes the list; `  - kessler_001 L1-4` and `- some_id: note` stay items).
        item_of_open_list = bool(pending_list and im and (indented or key not in KNOWN_KEYS))
        if km is not None and not item_of_open_list:
            value = km.group(2).strip()
            if key in LIST_KEYS and not value:
                current[key] = []
                pending_list, last_scalar = key, None
            else:
                _set_key(current, key, value)
                pending_list = None
                last_scalar = key if key not in LIST_KEYS and key != "merged_into" else None
            continue
        if im and pending_list:
            item = im.group(1).strip().strip("'\"`")
            if item:
                current[pending_list].append(item if pending_list == "seen_in" else item.lower())
            continue
        if indented and last_scalar and not im:
            target = current if last_scalar in KNOWN_KEYS else current["fields"]
            target[last_scalar] = (target.get(last_scalar, "") + " " + line.strip()).strip()
    if current is not None:
        moves.append(current)
    return moves


def parse_moves(text: str) -> list[dict]:
    """The canonical moves of a catalogue (parse_sections minus `merged_into` stubs), in file order.

    Every stub id that resolves to a real move is appended to that move's `aliases`, so a consumer that resolves a
    name through `id` and `aliases` (run_next.find_move_entry, matrix) sees one entry per move and every old id
    still resolves. Cyclic or orphaned stubs are dropped here and reported by lint_text.
    """
    sections = parse_sections(text)
    moves = [dict(m, aliases=list(m["aliases"])) for m in sections if not m["merged_into"]]
    by_id = {m["id"]: m for m in moves}
    for name, target in resolve_aliases(sections).items():
        if name != target and target in by_id and name not in by_id[target]["aliases"]:
            by_id[target]["aliases"].append(name)
    return moves


def parse_citation(cit: str) -> tuple[str, int | None, int | None] | None:
    """'kessler_001' -> ('kessler_001', None, None); 'kessler_001 L3-5' -> ('kessler_001', 3, 5); malformed -> None."""
    m = CITATION_RE.match(str(cit).strip())
    if not m:
        return None
    lo = int(m.group(2)) if m.group(2) else None
    hi = int(m.group(3)) if m.group(3) else lo
    return m.group(1), lo, hi


def resolve_aliases(moves: list[dict]) -> dict[str, str]:
    """{name: canonical id} over real ids, inline aliases and stub sections (chains followed, cycles dropped).
    Accepts the output of parse_sections (stubs resolved) or parse_moves (stubs already folded into aliases)."""
    real_ids = {m["id"] for m in moves if not m["merged_into"]}
    out: dict[str, str] = {i: i for i in real_ids}
    for m in moves:
        if m["merged_into"]:
            continue
        for a in m["aliases"]:
            out.setdefault(a, m["id"])
    stubs = {m["id"]: m["merged_into"] for m in moves if m["merged_into"]}
    for stub, target in stubs.items():
        seen = {stub}
        cur = target
        while cur in stubs and cur not in seen:
            seen.add(cur)
            cur = stubs[cur]
        if cur in real_ids:
            out.setdefault(stub, cur)
    return out


# --------------------------------------------------------------------------- lint

def lint_text(text: str, corpus_ids: set[str] | None = None, scoreboard: dict | None = None) -> dict:
    """Lint a catalogue text. `corpus_ids` (post ids that exist) enables the unknown-post check; None skips it.
    `scoreboard` is {move_key: {...}} from memory/topics.md (matrix.parse_topics_md); None or {} skips it."""
    moves = parse_sections(text)
    problems: list[dict] = []

    def add(move: str, field: str, problem: str) -> None:
        problems.append({"move": move, "field": field, "problem": problem})

    seen_ids: set[str] = set()
    for m in moves:
        if not SLUG_RE.match(m["id"]):
            add(m["id"], "id", f"line {m['line']}: id is not a slug of [a-z0-9_]+")
        if m["id"] in seen_ids:
            add(m["id"], "id", f"line {m['line']}: duplicate id")
        seen_ids.add(m["id"])

    real = [m for m in moves if not m["merged_into"]]
    real_ids = {m["id"] for m in real}
    stubs = {m["id"]: m for m in moves if m["merged_into"]}

    alias_owner: dict[str, str] = {}
    for m in real:
        for a in m["aliases"]:
            if not SLUG_RE.match(a):
                add(m["id"], "aliases", f"alias {a!r} is not a slug of [a-z0-9_]+")
            if a == m["id"]:
                add(m["id"], "aliases", f"alias {a!r} is the move's own id")
            elif a in real_ids:
                add(m["id"], "aliases", f"alias {a!r} is also a real move id")
            elif a in stubs:
                add(m["id"], "aliases", f"alias {a!r} is also a merged_into stub section")
            elif a in alias_owner and alias_owner[a] != m["id"]:
                add(m["id"], "aliases", f"alias {a!r} is already an alias of {alias_owner[a]}")
            else:
                alias_owner.setdefault(a, m["id"])
    for stub_id, stub in stubs.items():
        target = stub["merged_into"]
        chain = [stub_id]
        cur = target
        cyclic = False
        while cur in stubs:
            if cur in chain:
                cyclic = True
                break
            chain.append(cur)
            cur = stubs[cur]["merged_into"]
        if cyclic:
            add(stub_id, "merged_into", "alias cycle: " + " -> ".join(chain + [cur]))
        elif cur not in real_ids:
            add(stub_id, "merged_into", f"merged_into {target!r} names no real move")
        elif stub_id in alias_owner and alias_owner[stub_id] != cur:
            add(stub_id, "merged_into", f"stub resolves to {cur} but {alias_owner[stub_id]} lists it as an alias")
        else:
            alias_owner.setdefault(stub_id, cur)

    for m in real:
        for k in REQUIRED_KEYS:
            if k == "seen_in":
                continue
            if not str(m.get(k) or "").strip():
                add(m["id"], k, f"line {m['line']}: missing or empty")
        valid = 0
        for cit in m["seen_in"]:
            parsed = parse_citation(cit)
            if parsed is None:
                add(m["id"], "seen_in", f"malformed citation {cit!r}: expected <post_id> or <post_id> L1-4")
                continue
            pid, lo, hi = parsed
            if lo is not None and hi is not None and (lo < 1 or hi < lo):
                add(m["id"], "seen_in", f"citation {cit!r}: invalid line range")
                continue
            if corpus_ids is not None and pid not in corpus_ids:
                add(m["id"], "seen_in", f"citation {cit!r}: post {pid} is not in the corpus")
                continue
            valid += 1
        if valid < MIN_CITATIONS:
            add(m["id"], "seen_in", f"{valid} valid citation(s); at least {MIN_CITATIONS} required")
        for p in m["platforms"]:
            if p not in PLATFORMS:
                add(m["id"], "platforms", f"unknown platform {p!r} (linkedin | x)")

    resolved = resolve_aliases(moves)
    for key in (scoreboard or {}):
        k = str(key).strip().lower()
        if k and k not in resolved:
            add(k, "scoreboard", "memory/topics.md scoreboard move resolves to no move id or alias")

    aliases = {name: cid for name, cid in resolved.items() if name != cid}
    return {"ok": not problems, "problems": problems, "moves": len(real), "ids": sorted(real_ids),
            "aliases": dict(sorted(aliases.items()))}


def corpus_post_ids(root: Path) -> set[str] | None:
    """Post ids (file stems) under corpus/posts, corpus/self and corpus/heldout; None when the corpus has none."""
    ids: set[str] = set()
    for rel in SPLIT_DIRS:
        d = root / rel
        if d.is_dir():
            ids.update(p.stem for p in d.glob("*.md"))
    return ids or None


def load_scoreboard(root: Path) -> dict:
    p = root / "memory" / "topics.md"
    if not p.exists():
        return {}
    _runs, scoreboard = matrix.parse_topics_md(p.read_text(encoding="utf-8"))
    return scoreboard


def lint(root: Path | str | None = None) -> dict:
    """Lint <root>/style/moves.md against the corpus and memory/topics.md. Raises UserError when the file is absent."""
    root = Path(root).resolve() if root else common.ROOT
    p = root / "style" / "moves.md"
    if not p.is_file():
        raise UserError("style/moves.md not found (the wave-2 profile-builder writes it)")
    doc = lint_text(p.read_text(encoding="utf-8"), corpus_ids=corpus_post_ids(root), scoreboard=load_scoreboard(root))
    doc["file"] = "style/moves.md"
    return doc


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint style/moves.md: unique slug ids, >= 2 seen_in citations per move, "
                                             "alias resolution without cycles, scoreboard keys resolving.")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    a = ap.parse_args(argv)
    try:
        doc = lint(a.root)
    except (UserError, FileNotFoundError, OSError) as e:
        common.error(str(e))
        return 0
    common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
