#!/usr/bin/env python3
"""PreToolUse hook: block tool calls that touch denied paths (the isolation boundary for writers and judges).

Usage in an agent's frontmatter (see docs/design/contracts.md section 15):

    python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/guard_paths.py --deny corpus/heldout 'drafts/*/round*/scores'
    python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/guard_paths.py --allow 'drafts/*/round*/prompts/*' --deny 'corpus/**'

The hook reads the PreToolUse JSON on stdin ({"tool_name": ..., "tool_input": {...}}), collects every path
the call would touch, resolves each against CLAUDE_PROJECT_DIR (fallback: the current directory) with `..`
and symlinks folded, then:

* deny wins: any deny glob matching any target exits 2 with a one-line reason on stderr;
* with --allow, every target must match an allow glob, or exit 2;
* otherwise exit 0. A call with no path targets (`Bash echo hi`) passes.

Targets per tool: `file_path`, `path`, `notebook_path`; for Glob/Grep the search root (`path`, default
project root) plus `pattern`/`glob` when it carries a path component; for Bash a best-effort scan of the
command for tokens that look like project paths (anything with a '/' or rooted at a known top-level dir),
simple globs expanded. Relative Bash paths resolve against the payload's `cwd` (Claude Code keeps the shell
directory across calls), `cd <dir> && ...` is followed inside one command, `$PWD` / `$CLAUDE_PROJECT_DIR` /
`$POSTSMITH_ROOT` and `~` are expanded before the scan, and a root-relative `/corpus/heldout/x.md` is read as
the project path. Grep/Glob search roots and Bash directory targets (`grep -r '' corpus`, `find corpus`,
`cp -r corpus dst`, `cd corpus`) are blocked when a path-anchored deny glob could match something *below*
them, since the command would read that content; a glob whose expansion is truncated keeps its literal prefix
as such a search root. With `--bash-prefix P ...` every command segment (split on && ; || | and newlines)
must start with one of the prefixes, otherwise the call is blocked. On a case-insensitive volume (macOS APFS
by default) globs match case-insensitively, so `CORPUS/Heldout/x.md` is `corpus/heldout/x.md`. With an allow
list a Bash call whose cwd lies outside the project is blocked.

Glob semantics: fnmatch-style with '**'; a pattern also covers everything below it ('corpus/heldout' behaves
as 'corpus/heldout/**'); a pattern without any '/' matches at any depth ('*.key.json' behaves as
'**/*.key.json'). Deny globs are matched against both the requested spelling and the symlink-resolved path,
either hit blocks; allow globs against the resolved path only, so a symlink cannot smuggle a path into the
allowed area. Reading `evals/rubric/current/rubric.md` therefore needs an allow glob covering the resolved
`evals/rubric/v1/...` (judge-reader allows `evals/rubric/v*/**`).

Set POSTSMITH_HOOK_LOG=<file> (relative to the project dir unless absolute) to append one JSON line per
decision: {"ts", "hook", "tool", "targets", "decision": "allow"|"block", "reason"}. The judge-sanity health
item reads that log to prove a judge never reached outside its handed paths.

Stdlib only: this runs under the system python3, outside uv. `guard_writes.py` imports the helpers from here.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob as _glob
import json
import os
import re
import shlex
import sys
from collections.abc import Iterable
from pathlib import Path

HOOK_NAME = "guard_paths"
KNOWN_DIRS = ("corpus", "style", "drafts", "evals", "memory", "tools", "config", "docs")
SEARCH_TOOLS = ("Grep", "Glob")
PATH_KEYS = ("file_path", "path", "notebook_path")
GLOB_CHARS = "*?["
MAX_GLOB_EXPANSION = 200
BLOCK_EXIT = 2

_KNOWN_DIR_ALT = "|".join(KNOWN_DIRS)
# A relative path rooted at a known top-level dir, anywhere in a shell command (also inside quoted code).
_REL_PATH_RE = re.compile(
    r"(?<![\w./-])((?:\.\./)*(?:" + _KNOWN_DIR_ALT + r")(?:/[^\s'\"`;|&<>(){}\[\],:$]*)?)"
)
# An absolute path anywhere in a shell command.
_ABS_PATH_RE = re.compile(r"(?<![\w.:/])(/[^\s'\"`;|&<>(){}\[\],:$]+)")
_REDIR_RE = re.compile(r"^\d*[<>]+&?\d*")
_ASSIGN_RE = re.compile(r"^(?:--?[\w-]+|[A-Za-z_]\w*)=(.*)$", re.DOTALL)
_TRIM_CHARS = "'\"`;,()[]{}"
_CODE_CHARS = "()[]{}'\"`$"
_SEGMENT_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
_CD_RE = re.compile(r"^\s*(?:cd|pushd)\s+(?:--\s+)?(\S+)")


# --------------------------------------------------------------------------- glob matching

def pattern_segments(pattern: str) -> list[str]:
    """Normalise a glob into path segments.

    Leading './' and '/' and trailing '/' or '/**' are dropped (a pattern always covers its descendants);
    a pattern without '/' becomes ['**', pattern] so it matches at any depth; '' and '**' cover everything.
    """
    p = pattern.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.strip("/")
    while p.endswith("/**"):
        p = p[:-3].rstrip("/")
    segs = [s for s in p.split("/") if s not in ("", ".")]
    if not segs:
        return ["**"]
    if len(segs) == 1 and segs[0] != "**":
        segs = ["**", segs[0]]
    return segs


def _segment_regex(seg: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(seg):
        c = seg[i]
        if c == "*":
            out.append("[^/]*")
            while i < len(seg) and seg[i] == "*":
                i += 1
            continue
        if c == "?":
            out.append("[^/]")
        elif c == "[":
            j = seg.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                body = seg[i + 1:j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                body = body.replace("\\", "\\\\")
                out.append("[" + body + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


_COMPILED: dict[tuple[str, bool], re.Pattern[str]] = {}
_SEG_COMPILED: dict[tuple[str, bool], re.Pattern[str]] = {}


def compile_glob(pattern: str, ignore_case: bool = False) -> re.Pattern[str]:
    """Regex for a glob that matches the path itself and anything below it."""
    cached = _COMPILED.get((pattern, ignore_case))
    if cached is not None:
        return cached
    segs = pattern_segments(pattern)
    out = ""
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        if seg == "**":
            out += ".*" if last else "(?:.*/)?"
        else:
            out += _segment_regex(seg) + ("" if last else "/")
    rx = re.compile("^(?:" + out + ")(?:/.*)?$", re.IGNORECASE if ignore_case else 0)
    _COMPILED[(pattern, ignore_case)] = rx
    return rx


def glob_match(pattern: str, rel_path: str, ignore_case: bool = False) -> bool:
    """True when `pattern` matches `rel_path` (project-relative POSIX, '' = root) or an ancestor of it."""
    return compile_glob(pattern, ignore_case).match(rel_path) is not None


def _seg_match(seg: str, value: str, ignore_case: bool = False) -> bool:
    rx = _SEG_COMPILED.get((seg, ignore_case))
    if rx is None:
        rx = re.compile("^(?:" + _segment_regex(seg) + ")$", re.IGNORECASE if ignore_case else 0)
        _SEG_COMPILED[(seg, ignore_case)] = rx
    return rx.match(value) is not None


def could_match_under(pattern: str, rel_dir: str, ignore_case: bool = False) -> bool:
    """True when `pattern` could match a path strictly below directory `rel_dir` ('' = project root).

    Grep/Glob search roots and Bash directory targets need this: a search over `corpus` reads `corpus/heldout`
    even though the root itself does not match the deny glob.
    """
    segs = pattern_segments(pattern)
    tsegs = [s for s in rel_dir.split("/") if s]
    for i, tseg in enumerate(tsegs):
        if i >= len(segs):
            return False
        if segs[i] == "**":
            return True
        if not _seg_match(segs[i], tseg, ignore_case):
            return False
    return True


def is_path_anchored(pattern: str) -> bool:
    """A glob with a directory component ('corpus/heldout/**'); a bare '*.key.json' matches at any depth and
    would otherwise block every directory-targeted Bash command."""
    return "/" in pattern.strip().strip("/")


def literal_prefix(pattern: str) -> str:
    """Directory part of a glob before its first wildcard ('corpus/heldout/*.md' -> 'corpus/heldout')."""
    p = pattern.replace("\\", "/")
    absolute = p.startswith("/")
    segs = p.split("/")
    keep: list[str] = []
    for seg in segs:
        if any(ch in seg for ch in GLOB_CHARS):
            break
        keep.append(seg)
    else:
        return p
    out = "/".join(keep)
    if absolute and not out.startswith("/"):
        out = "/" + out.lstrip("/")
    return out


def has_glob(s: str) -> bool:
    return any(ch in s for ch in GLOB_CHARS)


# --------------------------------------------------------------------------- project paths

class Target:
    """One path a tool call would touch, in every project-relative spelling it has.

    `forms` holds the lexical spelling (as the call wrote it, '..' folded) and the physical one (symlinks resolved);
    deny globs are matched against all of them, allow globs only against `phys_forms`.
    """

    __slots__ = ("bash_dir", "display", "forms", "inside", "phys", "phys_forms", "search_root")

    def __init__(self, display: str, forms: list[str], phys_forms: list[str], inside: bool, phys: Path) -> None:
        self.display = display
        self.forms = forms
        self.phys_forms = phys_forms
        self.inside = inside
        self.search_root = False
        self.bash_dir = False   # a directory in a Bash command: only path-anchored deny globs reach below it
        self.phys = phys

    @property
    def resolved(self) -> str:
        """The physical project-relative spelling ('.' for the root), or the absolute path when outside."""
        if not self.inside or not self.phys_forms:
            return self.phys.as_posix()
        return self.phys_forms[0] or "."

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"Target({self.display!r}, forms={self.forms!r}, inside={self.inside!r}, "
                f"search_root={self.search_root!r})")


class Project:
    """The project directory in its lexical and symlink-resolved spellings."""

    def __init__(self, root: str | None = None) -> None:
        raw = root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        self.lex = Path(os.path.abspath(os.path.expanduser(raw)))
        try:
            self.phys = self.lex.resolve()
        except (OSError, RuntimeError):  # pragma: no cover - defensive
            self.phys = self.lex
        self.ignore_case = self._case_insensitive_volume()

    def _case_insensitive_volume(self) -> bool:
        """True when the project directory's volume folds case (macOS APFS default)."""
        try:
            swapped = str(self.phys).swapcase()
            if swapped == str(self.phys):
                return False
            return os.path.exists(swapped) and os.path.samefile(str(self.phys), swapped)
        except (OSError, ValueError):
            return False

    def relativize(self, raw: str, base: Path | None = None) -> Target | None:
        """Resolve `raw` against `base` (default: the project dir). None for an empty string; a root-relative
        spelling of a project path ('/corpus/heldout/x.md') is read as the project path."""
        s = raw.strip()
        if not s:
            return None
        p = Path(os.path.expanduser(s))
        if p.is_absolute():
            parts = p.parts
            if len(parts) > 1 and parts[1] in KNOWN_DIRS and not p.exists():
                p = self.lex.joinpath(*parts[1:])
        else:
            p = (base or self.lex) / p
        lex = Path(os.path.normpath(str(p)))
        try:
            phys = lex.resolve()
        except (OSError, RuntimeError):  # pragma: no cover - defensive
            phys = lex
        forms: list[str] = []
        phys_forms: list[str] = []
        for root_dir, cand, physical in ((self.lex, lex, False), (self.phys, lex, False),
                                         (self.phys, phys, True), (self.lex, phys, True)):
            try:
                r = cand.relative_to(root_dir).as_posix()
            except ValueError:
                continue
            r = "" if r == "." else r
            if r not in forms:
                forms.append(r)
            if physical and r not in phys_forms:
                phys_forms.append(r)
        if forms:
            return Target(forms[0] or ".", forms, phys_forms, True, phys)
        a = phys.as_posix()
        return Target(a, [a.lstrip("/")], [a.lstrip("/")], False, phys)

    def expand(self, raw: str, base: Path | None = None) -> tuple[list[str], bool]:
        """Expand a simple glob against `base` (default: the project dir), bounded: (matches, truncated).
        A non-glob is returned unchanged."""
        if not has_glob(raw):
            return [raw], False
        pat = os.path.expanduser(raw)
        if not os.path.isabs(pat):
            pat = os.path.join(str(base or self.lex), pat)
        try:
            found = sorted(_glob.glob(pat, recursive=True))
        except (OSError, ValueError, re.error):  # pragma: no cover - defensive
            found = []
        return found[:MAX_GLOB_EXPANSION], len(found) > MAX_GLOB_EXPANSION


# --------------------------------------------------------------------------- target extraction

def _token_candidate(tok: str) -> str | None:
    """Return the path-like part of a shell token, or None when it does not look like a project path."""
    t = _REDIR_RE.sub("", tok.strip())
    m = _ASSIGN_RE.match(t)
    if m:
        t = m.group(1)
    t = t.strip(_TRIM_CHARS)
    if not t or t.startswith("-") or "://" in t:
        return None
    if any(ch in t for ch in _CODE_CHARS):  # inline code such as python -c "..."; the regex sweep covers it
        return None
    first = t.split("/", 1)[0]
    if "/" in t or first in KNOWN_DIRS:
        return t
    return None


def bash_path_candidates(command: str) -> list[str]:
    """Best-effort list of path-like strings in a shell command: tokens plus a regex sweep of the text."""
    out: list[str] = []
    seen = set()

    def push(c: str | None) -> None:
        if c and c not in seen:
            seen.add(c)
            out.append(c)

    try:
        toks = shlex.split(command, posix=True)
    except ValueError:
        toks = command.split()
    for tok in toks:
        push(_token_candidate(tok))
    for rx in (_REL_PATH_RE, _ABS_PATH_RE):
        for m in rx.finditer(command):
            push(_token_candidate(m.group(1)))
    return out


def expand_shell_vars(command: str, project: Project, cwd: Path) -> str:
    """Expand `~` and the variables that name the project or the working directory, so the path scan reads
    `$PWD/corpus/heldout/x.md` as a project path."""
    subs = {"PWD": str(cwd), "CLAUDE_PROJECT_DIR": str(project.lex), "POSTSMITH_ROOT": str(project.lex),
            "HOME": os.path.expanduser("~")}
    for name, val in subs.items():
        command = command.replace("${" + name + "}", val).replace("$" + name, val)
    command = re.sub(r"(?<![\w/])~(?=/|\s|$)", os.path.expanduser("~"), command)
    return command


def bash_candidates_with_cwd(command: str, cwd: Path) -> list[tuple[Path, str]]:
    """(base directory, path-like token) pairs for a shell command, following `cd <dir>` between segments."""
    out: list[tuple[Path, str]] = []
    cur = cwd
    for seg in _SEGMENT_SPLIT_RE.split(command):
        if not seg.strip():
            continue
        for cand in bash_path_candidates(seg):
            out.append((cur, cand))
        m = _CD_RE.match(seg)
        if m:
            target = m.group(1).strip(_TRIM_CHARS)
            if target and target != "-":
                tp = Path(os.path.expanduser(target))
                cur = Path(os.path.normpath(str(tp if tp.is_absolute() else cur / tp)))
    return out


def collect_targets(tool: str, tool_input: dict, project: Project, cwd: Path | None = None) -> list[Target]:
    """Every path the tool call would touch, as Targets (deduplicated, in discovery order). `cwd` is the
    payload's working directory, against which relative Bash paths resolve (default: the project dir)."""
    targets: list[Target] = []
    seen = set()

    def add(raw: str | None, search_root: bool = False, bash: bool = False, base_dir: Path | None = None) -> None:
        if not isinstance(raw, str) or not raw.strip():
            return
        cands: list[tuple[str, bool]] = [(raw, search_root)]
        if has_glob(raw):
            prefix = literal_prefix(raw)
            found, truncated = project.expand(raw, base_dir)
            # a truncated expansion keeps its literal prefix as a search root, so the cut-off part still counts
            cands = ([(prefix, search_root or truncated)] if prefix else []) + [(m, False) for m in found]
        for cand, is_root in cands:
            t = project.relativize(cand, base_dir)
            if t is None or (bash and not t.inside):
                continue
            if is_root and not t.phys.is_file():
                t.search_root = True
            if bash and t.phys.is_dir():
                t.search_root = True
                t.bash_dir = True
            if t.display in seen:
                continue
            seen.add(t.display)
            targets.append(t)

    if tool == "Bash":
        base_dir = cwd or project.lex
        command = expand_shell_vars(str(tool_input.get("command") or ""), project, base_dir)
        for seg_dir, cand in bash_candidates_with_cwd(command, base_dir):
            add(cand, bash=True, base_dir=seg_dir)
    elif tool in SEARCH_TOOLS:
        base = tool_input.get("path")
        base = base.strip() if isinstance(base, str) else ""
        file_glob = tool_input.get("pattern") if tool == "Glob" else tool_input.get("glob")
        file_glob = file_glob.strip() if isinstance(file_glob, str) else ""
        if "/" in file_glob:
            joined = file_glob if os.path.isabs(file_glob) or not base else os.path.join(base, file_glob)
            add(joined, search_root=True)
        else:
            add(base or ".", search_root=True)
        if tool == "Grep":
            regex = tool_input.get("pattern")
            if isinstance(regex, str) and "/" in regex:
                add(_token_candidate(regex))
    else:
        for key in PATH_KEYS:
            add(tool_input.get(key))
    return targets


# --------------------------------------------------------------------------- decision

def _matches_any(patterns: Iterable[str], target: Target, ignore_case: bool = False) -> str | None:
    for pat in patterns:
        for form in target.forms:
            if glob_match(pat, form, ignore_case):
                return pat
            if target.search_root and could_match_under(pat, form, ignore_case) and (not target.bash_dir or is_path_anchored(pat)):
                return pat
    return None


def decide(tool: str, targets: list[Target], allow: list[str], deny: list[str],
           ignore_case: bool = False, cwd_outside: bool = False) -> tuple[str, str | None]:
    """Return ('allow'|'block', reason). Deny wins; with an allow list every target must match one allow
    glob, and a Bash call whose cwd lies outside the project is blocked."""
    for t in targets:
        hit = _matches_any(deny, t, ignore_case)
        if hit:
            how = "search would reach" if t.search_root and not any(glob_match(hit, f, ignore_case) for f in t.forms) \
                else "matches"
            return "block", f"{tool} {t.display}: {how} deny glob '{hit}'"
    if allow and tool == "Bash" and cwd_outside:
        return "block", f"{tool}: working directory outside the project with an allow list in force"
    if allow and targets:
        for t in targets:
            if not t.inside:
                return "block", f"{tool} {t.display}: outside the project and not in the allow list"
            if any(glob_match(pat, f, ignore_case) for pat in allow for f in t.phys_forms):
                continue
            shown = ", ".join(f"'{a}'" for a in allow[:4]) + (", ..." if len(allow) > 4 else "")
            where = t.display
            if t.resolved != t.display:
                where = f"{t.display} (resolves to {t.resolved})"
            return "block", f"{tool} {where}: not in allow list ({shown})"
    return "allow", None


# --------------------------------------------------------------------------- I/O

def read_payload(stream=None) -> dict | None:
    """Parse the hook JSON from stdin; None when it is empty or malformed."""
    stream = stream or sys.stdin
    try:
        raw = stream.read()
    except (OSError, ValueError):
        return None
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def log_decision(project: Project, hook: str, tool: str, targets: list[Target], decision: str,
                 reason: str | None, payload: dict) -> None:
    """Append one JSON line to $POSTSMITH_HOOK_LOG when set; never raises."""
    path = os.environ.get("POSTSMITH_HOOK_LOG")
    if not path:
        return
    try:
        p = Path(os.path.expanduser(path))
        if not p.is_absolute():
            p = project.lex / p
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "hook": hook,
            "tool": tool,
            "targets": [t.display for t in targets],
            "decision": decision,
            "reason": reason,
        }
        for key in ("session_id", "agent_id", "agent_type"):
            if key in payload:
                row[key] = payload[key]
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 - logging must never break the hook
        print(f"{hook}: could not write POSTSMITH_HOOK_LOG ({exc})", file=sys.stderr)


def tool_and_input(payload: dict) -> tuple[str, dict]:
    tool = payload.get("tool_name")
    tool = tool if isinstance(tool, str) else ""
    tool_input = payload.get("tool_input")
    return tool, tool_input if isinstance(tool_input, dict) else {}


def payload_cwd(payload: dict, project: Project) -> tuple[Path, bool]:
    """(working directory the call runs in, whether it lies outside the project); default: the project dir."""
    raw = payload.get("cwd")
    if not isinstance(raw, str) or not raw.strip():
        return project.lex, False
    cwd = Path(os.path.normpath(os.path.abspath(os.path.expanduser(raw))))
    try:
        phys = cwd.resolve()
    except (OSError, RuntimeError):  # pragma: no cover - defensive
        phys = cwd
    inside = any(_is_under(c, b) for c in (cwd, phys) for b in (project.lex, project.phys))
    return cwd, not inside


def _is_under(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def bash_prefix_violation(command: str, prefixes: list[str]) -> str | None:
    """The first command segment that does not start with an allowed prefix, or None."""
    if not prefixes:
        return None
    for seg in _SEGMENT_SPLIT_RE.split(command):
        seg = seg.strip()
        if not seg:
            continue
        if not any(seg.startswith(p) for p in prefixes):
            return seg
    return None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="guard_paths.py",
        description="PreToolUse hook: exit 2 when a tool call touches a denied path (deny wins) or, with "
                    "--allow, a path outside the allow list. Reads the hook JSON on stdin.")
    ap.add_argument("--allow", nargs="*", default=[], metavar="GLOB",
                    help="globs every target must match (project-relative; '**' supported)")
    ap.add_argument("--deny", nargs="*", default=[], metavar="GLOB",
                    help="globs that block when matched; a directory glob covers everything below it")
    ap.add_argument("--project-dir", default=None, metavar="DIR",
                    help="project root (default: $CLAUDE_PROJECT_DIR, then the current directory)")
    ap.add_argument("--bash-prefix", nargs="*", default=[], metavar="PREFIX",
                    help="every Bash command segment must start with one of these (e.g. 'uv run tools/'); "
                         "anything else is blocked outright")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = read_payload()
    if payload is None:
        print(f"{HOOK_NAME}: no hook JSON on stdin; nothing to check", file=sys.stderr)
        return 0
    tool, tool_input = tool_and_input(payload)
    project = Project(args.project_dir)
    cwd, cwd_outside = payload_cwd(payload, project)
    targets = collect_targets(tool, tool_input, project, cwd)
    decision, reason = decide(tool, targets, list(args.allow), list(args.deny), project.ignore_case, cwd_outside)
    if decision == "allow" and tool == "Bash" and args.bash_prefix:
        bad = bash_prefix_violation(str(tool_input.get("command") or ""), list(args.bash_prefix))
        if bad is not None:
            shown = ", ".join(f"'{p}'" for p in args.bash_prefix)
            decision, reason = "block", f"Bash segment {bad[:60]!r}: only commands starting with {shown} are allowed"
    log_decision(project, HOOK_NAME, tool, targets, decision, reason, payload)
    if decision == "block":
        print(f"{HOOK_NAME}: blocked {reason}", file=sys.stderr)
        return BLOCK_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main())
