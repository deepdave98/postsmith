#!/usr/bin/env python3
"""matrix.py: seeded writer assignments for a /post run (contracts §16).

Every assignment differs on (angle_family, archetype, move, device, lens). Writer 1 is lens-free and exactly
one slot is the short deadpan option. Moves used in the last 3 runs (memory/topics.md) and moves scoring a
mean <= 2.5 at n >= 3 are excluded; moves with a mean >= 4 come first. When the eligible pool runs dry the
fallback ladder is climbed and the rung is recorded on the assignment:

    rung 0  full rules
    rung 1  recency relaxed to the last run only
    rung 2  a move may repeat inside this matrix when paired with a different device (recency ignored)
    rung 3  persona-only slot: no move

CLI: uv run tools/matrix.py --n 3 --seed 4171 [--lens slug] [--platform linkedin|x|both] [--root R] [--json]
API: assign(n, seed, moves, scoreboard, recent_runs, lenses, persona, taxonomies) -> list[dict]
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

FALLBACK_ANGLES = ["reveal", "receipt", "reframe", "ridicule", "rule"]
FALLBACK_ARCHETYPES = [
    "contrarian_take", "announcement_with_twist", "story_in_medias_res", "list_with_a_turn",
    "one_liner", "receipt_dump", "before_after", "confession",
]
FALLBACK_DEVICES = [
    "deadpan", "specificity", "anti_climax", "incongruous_register", "understatement", "escalation",
    "callback", "rule_of_three_escalation",
]
LENS_LIST = ["reader", "voice", "comedy"]  # not used here; kept for symmetry with run_next
RECENT_RUNS_WINDOW = 3
LOW_SCORE_MEAN = 2.5
LOW_SCORE_MIN_N = 3
PREFERRED_MEAN = 4.0
DEADPAN_DEVICE = "deadpan"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


# --------------------------------------------------------------------------- parsers (tolerant)

def _parse_list(value: str) -> list[str]:
    """'[a, b]' | 'a, b' | 'a b' -> ['a', 'b']."""
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    parts = re.split(r"[,\s]+", v)
    return [p.strip().strip("'\"") for p in parts if p.strip().strip("'\"")]


def parse_moves_md(text: str) -> list[dict]:
    """Parse style/moves.md: '### <slug>' sections with 'key: value' lines. Returns canonical moves only.

    A section carrying 'merged_into: <slug>' is treated as an alias of that slug and not returned as a move.
    Every move dict has id, platforms (list), aliases (list) and every other 'key: value' line found.
    """
    moves: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^###\s+`?([A-Za-z0-9_\-]+)`?\s*$", line)
        if m:
            if current is not None:
                moves.append(current)
            current = {"id": m.group(1).strip().lower(), "platforms": [], "aliases": []}
            continue
        if re.match(r"^#{1,2}\s", line):
            if current is not None:
                moves.append(current)
                current = None
            continue
        if current is None:
            continue
        km = re.match(r"^\s*[-*]?\s*([A-Za-z_][A-Za-z0-9_ ]*?)\s*:\s*(.*)$", line)
        if not km:
            continue
        key = km.group(1).strip().lower().replace(" ", "_")
        val = km.group(2).strip()
        if key in ("platforms", "platform"):
            current["platforms"] = [p.lower() for p in _parse_list(val)]
        elif key in ("aliases", "alias"):
            current["aliases"] = [a.lower() for a in _parse_list(val)]
        else:
            current[key] = val
    if current is not None:
        moves.append(current)
    canonical = [m for m in moves if not m.get("merged_into")]
    alias_of = {m["id"]: m["merged_into"].strip().lower() for m in moves if m.get("merged_into")}
    for m in canonical:
        for alias, target in alias_of.items():
            if target == m["id"] and alias not in m["aliases"]:
                m["aliases"].append(alias)
    return canonical


def _table_rows(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Return every markdown table as (header_cells, rows) with cells stripped and lowercased headers."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    header: list[str] | None = None
    rows: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if header is None:
                header = [c.lower().strip("`* ") for c in cells]
                rows = []
                continue
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and any(cells):
                continue
            rows.append(cells)
        else:
            if header is not None:
                tables.append((header, rows))
            header, rows = None, []
    if header is not None:
        tables.append((header, rows))
    return tables


def parse_taxonomy_ids(text: str, fallback: list[str], column: str = "id", first_table_only: bool = False) -> list[str]:
    """Slugs from the `column` of every markdown table whose header has that column (deduped, file order).

    `first_table_only` stops after the first matching table (structures.md also has an 'ending habits' table with an
    id column). Falls back to '### slug' headings, then to `fallback`.
    """
    ids: list[str] = []
    for header, rows in _table_rows(text):
        if column not in header:
            continue
        col = header.index(column)
        for r in rows:
            if col < len(r):
                v = r[col].strip("`* ").lower()
                if v and _SLUG_RE.match(v) and v not in ids:
                    ids.append(v)
        if first_table_only and ids:
            break
    if not ids:
        for m in re.finditer(r"^###?\s+`?([a-z0-9_\-]+)`?\s*$", text, re.MULTILINE):
            v = m.group(1)
            if v not in ids:
                ids.append(v)
    return ids or list(fallback)


def parse_topics_md(text: str) -> tuple[list[dict], dict]:
    """memory/topics.md -> (runs rows newest first, scoreboard {move: {mean, n, last_used}})."""
    runs: list[dict] = []
    scoreboard: dict[str, dict] = {}
    for header, rows in _table_rows(text):
        if "move" in header and any(h.startswith("mean") for h in header):
            idx = {h: i for i, h in enumerate(header)}
            mean_col = next(i for i, h in enumerate(header) if h.startswith("mean"))
            n_col = idx.get("n")
            last_col = next((i for i, h in enumerate(header) if h.startswith("last")), None)
            for r in rows:
                if not r or not r[idx["move"]].strip():
                    continue
                move = r[idx["move"]].strip("`* ").lower()
                try:
                    mean = float(r[mean_col]) if mean_col < len(r) and r[mean_col].strip() else None
                except ValueError:
                    mean = None
                try:
                    n = int(float(r[n_col])) if n_col is not None and n_col < len(r) and r[n_col].strip() else 0
                except ValueError:
                    n = 0
                last = r[last_col].strip() if last_col is not None and last_col < len(r) else ""
                scoreboard[move] = {"mean": mean, "n": n, "last_used": last or None}
        elif "date" in header and "moves" in header:
            idx = {h: i for i, h in enumerate(header)}
            for order, r in enumerate(rows):
                if not r or not r[idx["date"]].strip():
                    continue
                cell = {name: (r[i].strip() if i < len(r) else "") for name, i in idx.items()}
                runs.append({
                    "date": cell.get("date", ""),
                    "topic": cell.get("topic", ""),
                    "angle": cell.get("angle", ""),
                    "moves": [m.strip("`* ").lower() for m in _parse_list(cell.get("moves", "")) if m.strip("`* ")],
                    "lens": cell.get("lens") or None,
                    "outcome": cell.get("outcome", ""),
                    "_order": order,
                })
    runs.sort(key=lambda r: (r["date"], r["_order"]), reverse=True)
    for r in runs:
        r.pop("_order", None)
    return runs, scoreboard


# --------------------------------------------------------------------------- loading from a project root

def load_inputs(root: Path | None = None, lens: str | None = None, platform: str | None = None) -> dict:
    """Moves, scoreboard, recent runs, lenses, persona and taxonomies from a project root. All optional."""
    root = Path(root) if root else common.ROOT
    moves_p = root / "style" / "moves.md"
    moves = parse_moves_md(moves_p.read_text(encoding="utf-8")) if moves_p.exists() else []
    topics_p = root / "memory" / "topics.md"
    recent, scoreboard = parse_topics_md(topics_p.read_text(encoding="utf-8")) if topics_p.exists() else ([], {})
    authors_dir = root / "style" / "authors"
    lenses = sorted(p.stem for p in authors_dir.glob("*.md")) if authors_dir.exists() else []
    if lens:
        lenses = [lens]
    persona: dict = {}
    persona_p = root / "style" / "persona.md"
    if persona_p.exists():
        try:
            persona, _ = common.split_front_matter(persona_p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - persona front matter is optional
            persona = {}
    tax_dir = root / "style" / "taxonomies"

    def tax(name: str, fallback: list[str], column: str = "id", first_only: bool = False) -> list[str]:
        p = tax_dir / f"{name}.md"
        if not p.exists():
            return list(fallback)
        return parse_taxonomy_ids(p.read_text(encoding="utf-8"), fallback, column=column, first_table_only=first_only)

    taxonomies = {
        "angles": tax("angles", FALLBACK_ANGLES, column="family"),          # families, not angle ids
        "archetypes": tax("structures", FALLBACK_ARCHETYPES, first_only=True),  # skip the ending-habits table
        "devices": tax("devices", FALLBACK_DEVICES),                        # humor + voice tables
    }
    return {"moves": moves, "scoreboard": scoreboard, "recent_runs": recent, "lenses": lenses,
            "persona": persona or {}, "taxonomies": taxonomies, "platform": platform}


# --------------------------------------------------------------------------- assignment

def _canonical_map(moves: list[dict]) -> dict[str, str]:
    m: dict[str, str] = {}
    for mv in moves:
        m[mv["id"]] = mv["id"]
        for a in mv.get("aliases", []):
            m.setdefault(a, mv["id"])
    return m


def _recent_moves(recent_runs: list[dict], window: int, canon: dict[str, str]) -> set[str]:
    used: set[str] = set()
    for r in recent_runs[:window]:
        for mv in r.get("moves", []):
            used.add(canon.get(mv, mv))
    return used


def _low_score_moves(scoreboard: dict, canon: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for k, v in scoreboard.items():
        mean, n = v.get("mean"), v.get("n", 0)
        if mean is not None and n >= LOW_SCORE_MIN_N and mean <= LOW_SCORE_MEAN:
            out.add(canon.get(k, k))
    return out


def _preferred_moves(scoreboard: dict, canon: dict[str, str]) -> set[str]:
    return {canon.get(k, k) for k, v in scoreboard.items() if v.get("mean") is not None and v["mean"] >= PREFERRED_MEAN}


def _shuffled(rng: random.Random, items: list[str]) -> list[str]:
    xs = list(items)
    rng.shuffle(xs)
    return xs


def assign(n: int, seed: int, moves: list[dict], scoreboard: dict, recent_runs: list[dict], lenses: list[str],
           persona: dict, taxonomies: dict, platform: str | None = None) -> list[dict]:
    """Return n assignments (writer 1..n). Deterministic for a given seed and inputs.

    Each dict: writer, name, angle_family, archetype, move, device, lens, seed, short_deadpan, rung.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    rng = random.Random(seed)
    canon = _canonical_map(moves)
    plat = (platform or "both").lower()
    pool_all = [m["id"] for m in moves]
    if plat in ("linkedin", "x"):
        pool_all = [m["id"] for m in moves if not m.get("platforms") or plat in m.get("platforms", [])]
    low = _low_score_moves(scoreboard, canon)
    preferred = _preferred_moves(scoreboard, canon)
    recent3 = _recent_moves(recent_runs, RECENT_RUNS_WINDOW, canon)
    recent1 = _recent_moves(recent_runs, 1, canon)

    def ordered_pool(excluded: set[str]) -> list[str]:
        cands = [m for m in pool_all if m not in low and m not in excluded]
        pref = _shuffled(rng, [m for m in cands if m in preferred])
        rest = _shuffled(rng, [m for m in cands if m not in preferred])
        return pref + rest

    # Rung 0 and 1 pools are computed up front so the rng consumption is stable.
    pool_r0 = ordered_pool(recent3)
    pool_r1 = [m for m in ordered_pool(recent1) if m not in pool_r0]
    pool_r2 = [m for m in ordered_pool(set()) if m not in pool_r0 and m not in pool_r1]

    angles = list(taxonomies.get("angles") or FALLBACK_ANGLES)
    archetypes = list(taxonomies.get("archetypes") or FALLBACK_ARCHETYPES)
    devices = list(taxonomies.get("devices") or FALLBACK_DEVICES)
    angle_order = _shuffled(rng, angles)
    arch_order = _shuffled(rng, archetypes)
    dev_order = _shuffled(rng, devices)

    deadpan_slot = rng.randrange(n)
    lens_prefs = persona.get("lens_preferences") or persona.get("lens_prefs") or []
    if isinstance(lens_prefs, str):
        lens_prefs = _parse_list(lens_prefs)
    if not lens_prefs:
        # No stated preference yet: the corpus's primary authors are the declared style targets, so they lead.
        lens_prefs = [str(x) for x in ((common.load_config().get("corpus") or {}).get("primary_authors") or [])]
    lens_order = [x for x in lens_prefs if x in lenses] + [x for x in lenses if x not in lens_prefs]

    # Devices: the deadpan slot takes the deadpan device when the taxonomy has it; others take distinct devices.
    dev_assign: list[str] = [""] * n
    dev_iter = [d for d in dev_order if d != DEADPAN_DEVICE] if DEADPAN_DEVICE in dev_order else list(dev_order)
    if not dev_iter:
        dev_iter = list(dev_order) or [DEADPAN_DEVICE]
    di = 0
    for w in range(n):
        if w == deadpan_slot and DEADPAN_DEVICE in dev_order:
            dev_assign[w] = DEADPAN_DEVICE
        else:
            dev_assign[w] = dev_iter[di % len(dev_iter)]
            di += 1

    # Moves via the ladder.
    used_moves: list[tuple[str, str]] = []  # (move, device)
    move_assign: list[tuple[str | None, int]] = []
    r0, r1, r2 = list(pool_r0), list(pool_r1), list(pool_r2)
    for w in range(n):
        chosen: str | None = None
        rung = 3
        if r0:
            chosen, rung = r0.pop(0), 0
        elif r1:
            chosen, rung = r1.pop(0), 1
        elif r2:
            chosen, rung = r2.pop(0), 2
        else:
            # rung 2: repeat an already assigned move once, with a different device; else persona-only (rung 3)
            for mv, dv in used_moves:
                uses = [d for m2, d in used_moves if m2 == mv]
                if len(uses) < 2 and dev_assign[w] not in uses:
                    chosen, rung = mv, 2
                    break
        if chosen is not None:
            used_moves.append((chosen, dev_assign[w]))
        move_assign.append((chosen, rung))

    out: list[dict] = []
    for w in range(n):
        lens = None if w == 0 or not lens_order else lens_order[(w - 1) % len(lens_order)]
        mv, rung = move_assign[w]
        out.append({
            "writer": w + 1,
            "name": f"post-writer-{w + 1}",
            "angle_family": angle_order[w % len(angle_order)],
            "archetype": arch_order[w % len(arch_order)],
            "move": mv,
            "device": dev_assign[w],
            "lens": lens,
            "seed": seed,
            "short_deadpan": w == deadpan_slot,
            "rung": rung,
        })
    # Keep (angle, archetype, move, device, lens) distinct: when a small taxonomy makes two writers collide,
    # rotate the archetype until the tuple is unique.
    seen: set[tuple] = set()
    for idx, a in enumerate(out):
        bump = 0
        while _tuple_of(a) in seen and bump < len(arch_order):
            bump += 1
            a["archetype"] = arch_order[(idx + bump) % len(arch_order)]
        seen.add(_tuple_of(a))
    return out


def _tuple_of(a: dict) -> tuple:
    return (a["angle_family"], a["archetype"], a["move"], a["device"], a["lens"])


def build(n: int, seed: int, root: Path | None = None, lens: str | None = None,
          platform: str | None = None) -> dict:
    """Load inputs from root and assign. Returns the CLI document."""
    inputs = load_inputs(root, lens=lens, platform=platform)
    canon = _canonical_map(inputs["moves"])
    assignments = assign(n, seed, inputs["moves"], inputs["scoreboard"], inputs["recent_runs"], inputs["lenses"],
                         inputs["persona"], inputs["taxonomies"], platform=platform)
    notes: list[str] = []
    if not inputs["moves"]:
        notes.append("style/moves.md has no moves; assignments are persona-only (rung 3)")
    if not inputs["lenses"]:
        notes.append("no author lenses under style/authors/; all writers are lens-free")
    return {
        "ok": True,
        "seed": seed,
        "n": n,
        "assignments": assignments,
        "excluded": {
            "recent": sorted(_recent_moves(inputs["recent_runs"], RECENT_RUNS_WINDOW, canon)),
            "low_score": sorted(_low_score_moves(inputs["scoreboard"], canon)),
        },
        "preferred": sorted(_preferred_moves(inputs["scoreboard"], canon) & set(canon.values())),
        "rung_max": max((a["rung"] for a in assignments), default=0),
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seeded writer assignment matrix for a /post run.")
    ap.add_argument("--n", type=int, default=None, help="number of writers (default: config run.writers_default)")
    ap.add_argument("--seed", type=int, required=True, help="matrix seed (use the run's seed)")
    ap.add_argument("--lens", default=None, help="force this author lens for every lens writer")
    ap.add_argument("--platform", default=None, choices=["both", "linkedin", "x"], help="restrict moves by platform")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--write", default=None, help="also write the assignments JSON to this path")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    n = args.n
    if n is None:
        try:
            n = int(common.load_config().get("run", {}).get("writers_default", 3))
        except Exception:  # noqa: BLE001
            n = 3
    if n < 1:
        common.error("--n must be >= 1")
        return 0
    if args.lens and not _SLUG_RE.match(args.lens):
        common.error(f"--lens must be a slug, got {args.lens!r}")
        return 0
    try:
        doc = build(n, args.seed, root=root, lens=args.lens, platform=args.platform)
    except (OSError, ValueError) as e:
        common.error(str(e))
        return 0
    if args.write:
        common.write_json(args.write, doc)
    common.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
