#!/usr/bin/env python3
"""lessons.py: maintain memory/lessons.md in the contract §13 format.

    add --tag T --instruction '...' --evidence 'cid:quote' [--evidence ...]
        [--section PREFER|AVOID|FACTS-I-CAN-USE] [--run R] --count N | --force [--reinforce L-nnn]
    consolidate            merge near-duplicate entries (same section and tag, similar instruction) and hold
                           the config calibration.lessons_max_lines cap by merging, never dropping
    retire [--days 90]     move entries not reinforced for N days (config calibration.lessons_retire_days)
                           to RETIRED
    list                   parsed entries as JSON

Entry line: `- L-031 (2026-09-17, run <run>; tag not_funny x3) AVOID: <instruction> Evidence: r2-w3-x
"explains the joke"; r1-w1-li` under `## PREFER` / `## AVOID` / `## FACTS-I-CAN-USE` (keyword FACT) /
`## RETIRED`, where the line keeps its keyword and gains ` (retired <date>)`. `add` records the rating count
the caller passes (`x<n>`); the /rate skill enforces the 3-ratings rule, and the tool refuses below --count 3
unless --force. Entries cite tags and cids, never scores. Ids are L-nnn, monotonic across the whole file
including RETIRED. The line cap counts entry lines in the three active sections.

CLI: uv run tools/lessons.py add --tag not_funny --instruction "..." --evidence "r2-w3-x:explains the joke"
     --count 3 --json
API: add(...), consolidate(root=None, today=None), retire(days=None, root=None, today=None),
     parse(text) -> list[Entry]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

LESSONS_PATH = Path("memory") / "lessons.md"
SECTIONS = ("PREFER", "AVOID", "FACTS-I-CAN-USE", "RETIRED")
ACTIVE = ("PREFER", "AVOID", "FACTS-I-CAN-USE")
KEYWORDS = {"PREFER": "PREFER", "AVOID": "AVOID", "FACTS-I-CAN-USE": "FACT"}
SECTION_OF_KEYWORD = {v: k for k, v in KEYWORDS.items()}
TAGS = ("too_safe", "not_funny", "sounds_ai", "not_me", "too_long", "too_short", "hook_weak", "copycat", "wrong_facts",
        "too_mean", "great_hook", "great_ending", "media_miss", "media_great")
POSITIVE_TAGS = frozenset({"great_hook", "great_ending", "media_great"})
MIN_COUNT = 3
SIMILARITY = 0.6
HEADER = ("# Lessons\n\nDistilled from Deep's ratings (/rate). Entries cite tags and candidate ids, never scores. "
          "Writers read PREFER / AVOID / FACTS-I-CAN-USE (the last 40 lines); RETIRED is history.\n")

_ENTRY_RE = re.compile(
    r"^- (?P<id>L-\d{3,}) \((?P<date>\d{4}-\d{2}-\d{2})(?:, run (?P<run>[^;)]+?))?(?:; tag (?P<tag>[a-z_]+) x(?P<count>\d+))?\) "
    r"(?P<kw>PREFER|AVOID|FACT): (?P<body>.*?)(?: \(retired (?P<retired>\d{4}-\d{2}-\d{2})\))?$")
_EVIDENCE_RE = re.compile(r'^(?P<cid>[^\s"]+)(?: "(?P<quote>[^"]*)")?$')


@dataclass
class Entry:
    id: str
    date: str
    section: str
    instruction: str
    tag: str | None = None
    count: int = 0
    run: str | None = None
    evidence: list[dict] = field(default_factory=list)
    retired: str | None = None

    def render(self) -> str:
        head = self.date + (f", run {self.run}" if self.run else "") + (f"; tag {self.tag} x{self.count}" if self.tag else "")
        ev = "; ".join(e["cid"] + (f' "{e["quote"]}"' if e.get("quote") else "") for e in self.evidence)
        line = f"- {self.id} ({head}) {KEYWORDS[self.section]}: {self.instruction.strip()}"
        if ev:
            line += f" Evidence: {ev}"
        if self.retired:
            line += f" (retired {self.retired})"
        return line

    def as_dict(self) -> dict:
        return {"id": self.id, "date": self.date, "section": self.section, "tag": self.tag, "count": self.count,
                "run": self.run, "instruction": self.instruction, "evidence": self.evidence, "retired": self.retired}


# --------------------------------------------------------------------------- parse / render

def parse_evidence(items: list[str] | str | None) -> list[dict]:
    """'cid:quote' or 'cid' (comma- or list-separated) -> [{cid, quote}]."""
    if items is None:
        return []
    raw = [items] if isinstance(items, str) else list(items)
    out: list[dict] = []
    for chunk in raw:
        for part in str(chunk).split(";"):
            part = part.strip()
            if not part:
                continue
            cid, _, quote = part.partition(":")
            cid = cid.strip()
            quote = quote.strip().strip('"')
            if cid and not any(e["cid"] == cid and e.get("quote") == (quote or None) for e in out):
                out.append({"cid": cid, "quote": quote or None})
    return out


def _parse_line(line: str, section: str) -> Entry | None:
    m = _ENTRY_RE.match(line.strip())
    if not m:
        return None
    body = m.group("body")
    instruction, evidence = body, []
    idx = body.rfind(" Evidence: ")
    if idx >= 0:
        instruction, ev = body[:idx], body[idx + len(" Evidence: "):]
        for piece in ev.split("; "):
            em = _EVIDENCE_RE.match(piece.strip())
            if em:
                evidence.append({"cid": em.group("cid"), "quote": em.group("quote")})
    sec = SECTION_OF_KEYWORD[m.group("kw")] if section == "RETIRED" else section
    return Entry(id=m.group("id"), date=m.group("date"), section=sec, instruction=instruction.strip(),
                 tag=m.group("tag"), count=int(m.group("count") or 0), run=m.group("run"), evidence=evidence,
                 retired=m.group("retired") if section == "RETIRED" else None)


def parse(text: str) -> list[Entry]:
    """Every entry line in file order; a line under RETIRED carries `retired`."""
    entries: list[Entry] = []
    section: str | None = None
    for line in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            name = h.group(1).strip().upper()
            section = name if name in SECTIONS else None
            continue
        if section and line.startswith("- L-"):
            e = _parse_line(line, section)
            if e:
                if section == "RETIRED" and not e.retired:
                    e.retired = e.date
                entries.append(e)
    return entries


def render(entries: list[Entry]) -> str:
    out = [HEADER]
    for sec in SECTIONS:
        out.append(f"## {sec}\n")
        rows = [e for e in entries if (e.retired is not None) == (sec == "RETIRED") and (sec == "RETIRED" or e.section == sec)]
        rows.sort(key=lambda e: int(e.id[2:]))
        out.append("\n".join(e.render() for e in rows) + ("\n" if rows else ""))
    return "\n".join(out).rstrip("\n") + "\n"


def load(root: Path) -> list[Entry]:
    p = root / LESSONS_PATH
    return parse(p.read_text(encoding="utf-8")) if p.exists() else []


def save(root: Path, entries: list[Entry]) -> Path:
    p = root / LESSONS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(entries), encoding="utf-8")
    return p


def next_id(entries: list[Entry]) -> str:
    n = max((int(e.id[2:]) for e in entries), default=0) + 1
    return f"L-{n:03d}"


def active_lines(entries: list[Entry]) -> int:
    return sum(1 for e in entries if e.retired is None)


def _cfg(root: Path) -> dict:
    with common.use_root(root):
        if not (common.ROOT / "config" / "postsmith.yaml").exists():
            return {}
        return common.load_config().get("calibration") or {}


# --------------------------------------------------------------------------- operations

def add(tag: str | None, instruction: str, evidence: list[str] | str | None, section: str | None = None,
        run: str | None = None, count: int = 0, force: bool = False, reinforce: str | None = None,
        root: Path | None = None, today: str | None = None) -> dict:
    with common.use_root(root):
        rt = common.ROOT
        today = today or common.today()
        if tag is not None and tag not in TAGS:
            return {"ok": False, "error": f"unknown tag {tag!r}; vocabulary: {', '.join(TAGS)}"}
        if not (instruction or "").strip():
            return {"ok": False, "error": "--instruction is required"}
        if count < MIN_COUNT and not force:
            return {"ok": False, "error": f"a lesson needs >= {MIN_COUNT} ratings sharing a tag and a cause "
                                          f"(--count {count}); pass --count N or --force"}
        if section is None:
            section = "PREFER" if tag in POSITIVE_TAGS else "AVOID"
        section = section.upper()
        if section not in ACTIVE:
            return {"ok": False, "error": f"--section must be one of {', '.join(ACTIVE)}"}
        if section == "FACTS-I-CAN-USE" and tag is None:
            pass  # facts carry no tag
        elif tag is None:
            return {"ok": False, "error": "--tag is required for PREFER / AVOID"}
        ev = parse_evidence(evidence)
        if not ev and section != "FACTS-I-CAN-USE":
            return {"ok": False, "error": "--evidence 'cid:quote' is required (cite the candidates, never scores)"}
        entries = load(rt)
        if reinforce:
            target = next((e for e in entries if e.id == reinforce), None)
            if target is None:
                return {"ok": False, "error": f"no entry {reinforce} to reinforce"}
            target.date = today
            target.count = target.count + max(count, 1) if target.tag else target.count
            target.run = run or target.run
            for e in ev:
                if not any(x["cid"] == e["cid"] and x.get("quote") == e.get("quote") for x in target.evidence):
                    target.evidence.append(e)
            target.retired = None
            p = save(rt, entries)
            return {"ok": True, "action": "reinforced", "entry": target.as_dict(), "path": common.rel(p),
                    "active_lines": active_lines(entries)}
        entry = Entry(id=next_id(entries), date=today, section=section, instruction=instruction.strip(), tag=tag,
                      count=count, run=run, evidence=ev)
        entries.append(entry)
        p = save(rt, entries)
        cap = int(_cfg(rt).get("lessons_max_lines", 80))
        res = {"ok": True, "action": "added", "entry": entry.as_dict(), "path": common.rel(p),
               "active_lines": active_lines(entries), "cap": cap, "over_cap": active_lines(entries) > cap}
        if res["over_cap"]:
            res["note"] = "over the line cap: run `lessons.py consolidate`"
        return res


def _tokens(s: str) -> set[str]:
    return set(common.normalize_text(s).split())


def _merge(keep: Entry, other: Entry) -> Entry:
    keep.date = max(keep.date, other.date)
    keep.count = keep.count + other.count
    keep.run = keep.run or other.run
    if _tokens(other.instruction) - _tokens(keep.instruction) and other.instruction.strip() not in keep.instruction:
        if common.jaccard(_tokens(keep.instruction), _tokens(other.instruction)) < SIMILARITY:
            keep.instruction = f"{keep.instruction.rstrip('.')}; {other.instruction.strip()}"
        elif len(other.instruction) > len(keep.instruction):
            keep.instruction = other.instruction
    for e in other.evidence:
        if not any(x["cid"] == e["cid"] and x.get("quote") == e.get("quote") for x in keep.evidence):
            keep.evidence.append(e)
    if keep.tag is None:
        keep.tag = other.tag
    return keep


def consolidate(root: Path | None = None, today: str | None = None) -> dict:
    """Merge near-duplicates (same section and tag, token Jaccard >= SIMILARITY), then merge the oldest pairs
    of the largest section until the active lines fit config calibration.lessons_max_lines. Nothing is
    dropped."""
    with common.use_root(root):
        rt = common.ROOT
        entries = load(rt)
        cap = int(_cfg(rt).get("lessons_max_lines", 80))
        before = active_lines(entries)
        merges: list[dict] = []
        active = [e for e in entries if e.retired is None]
        # 1. near-duplicates
        i = 0
        while i < len(active):
            j = i + 1
            while j < len(active):
                a, b = active[i], active[j]
                if a.section == b.section and a.tag == b.tag and \
                        common.jaccard(_tokens(a.instruction), _tokens(b.instruction)) >= SIMILARITY:
                    _merge(a, b)
                    merges.append({"kept": a.id, "merged": b.id, "reason": "near-duplicate"})
                    entries.remove(b)
                    active.pop(j)
                    continue
                j += 1
            i += 1
        # 2. cap: merge the two oldest entries (same tag first) of the largest active section
        while active_lines(entries) > cap:
            active = [e for e in entries if e.retired is None]
            by_sec: dict[str, list[Entry]] = {}
            for e in active:
                by_sec.setdefault(e.section, []).append(e)
            _sec, rows = max(by_sec.items(), key=lambda kv: (len(kv[1]), kv[0]))
            if len(rows) < 2:
                break
            rows.sort(key=lambda e: (e.date, int(e.id[2:])))
            pair = None
            for x in range(len(rows)):
                for y in range(x + 1, len(rows)):
                    if rows[x].tag == rows[y].tag:
                        pair = (rows[x], rows[y])
                        break
                if pair:
                    break
            a, b = pair or (rows[0], rows[1])
            _merge(a, b)
            merges.append({"kept": a.id, "merged": b.id, "reason": f"line cap {cap}"})
            entries.remove(b)
        p = save(rt, entries)
        return {"ok": True, "merges": merges, "active_lines_before": before, "active_lines": active_lines(entries),
                "cap": cap, "path": common.rel(p)}


def retire(days: int | None = None, root: Path | None = None, today: str | None = None) -> dict:
    with common.use_root(root):
        rt = common.ROOT
        today = today or common.today()
        days = int(days if days is not None else _cfg(rt).get("lessons_retire_days", 90))
        cutoff = (_dt.date.fromisoformat(today) - _dt.timedelta(days=days)).isoformat()
        entries = load(rt)
        retired = []
        for e in entries:
            if e.retired is None and e.date < cutoff:
                e.retired = today
                retired.append(e.id)
        p = save(rt, entries)
        return {"ok": True, "retired": retired, "days": days, "cutoff": cutoff, "path": common.rel(p),
                "active_lines": active_lines(entries)}


def list_entries(root: Path | None = None) -> dict:
    with common.use_root(root):
        entries = load(common.ROOT)
        return {"ok": True, "entries": [e.as_dict() for e in entries], "active_lines": active_lines(entries),
                "path": common.rel(common.ROOT / LESSONS_PATH)}


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Maintain memory/lessons.md (PREFER / AVOID / FACTS-I-CAN-USE / RETIRED).")
    ap.add_argument("--root", default=None, help="project root (default: this project)")
    ap.add_argument("--json", action="store_true", help="JSON output (always JSON)")
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)
    common_flags = argparse.ArgumentParser(add_help=False)  # --root/--json/--today after the subcommand too
    common_flags.add_argument("--root", default=argparse.SUPPRESS, help="project root (default: this project)")
    common_flags.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="JSON output")
    common_flags.add_argument("--today", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", parents=[common_flags], help="append a lesson (needs --count >= 3 or --force)")
    a.add_argument("--tag", default=None, help="contract tag the ratings share (omit for FACTS-I-CAN-USE)")
    a.add_argument("--instruction", required=True, help="the lesson, one sentence, never a score")
    a.add_argument("--evidence", action="append", default=[], help="'cid:short quote' or 'cid' (repeatable; ';'-separated)")
    a.add_argument("--section", default=None, help="PREFER | AVOID | FACTS-I-CAN-USE (default from the tag)")
    a.add_argument("--run", default=None, help="the run the ratings came from")
    a.add_argument("--count", type=int, default=0, help="how many ratings share the tag and cause")
    a.add_argument("--force", action="store_true", help="bypass the --count >= 3 rule")
    a.add_argument("--reinforce", default=None, help="L-nnn: reinforce an existing entry instead of adding one")
    sub.add_parser("consolidate", parents=[common_flags], help="merge near-duplicates and enforce the line cap (merge, never drop)")
    r = sub.add_parser("retire", parents=[common_flags], help="move entries unreinforced for N days to RETIRED")
    r.add_argument("--days", type=int, default=None, help="default config calibration.lessons_retire_days")
    sub.add_parser("list", parents=[common_flags], help="parsed entries as JSON")
    args = ap.parse_args(argv)
    if args.today and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.today):
        common.error("--today must be YYYY-MM-DD")
        return 0
    try:
        with common.use_root(args.root):
            if args.cmd == "add":
                res = add(args.tag, args.instruction, args.evidence, section=args.section, run=args.run,
                          count=args.count, force=args.force, reinforce=args.reinforce, today=args.today)
            elif args.cmd == "consolidate":
                res = consolidate(today=args.today)
            elif args.cmd == "retire":
                res = retire(days=args.days, today=args.today)
            else:
                res = list_entries()
    except FileNotFoundError as e:
        common.error(str(e))
        return 0
    common.emit(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
