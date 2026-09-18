"""Shared helpers for postsmith tools.

Import as `from common import ...`; tools/ is on sys.path when a tool is run directly.
Conventions: project-relative paths, ISO-8601 UTC timestamps, JSON output via `emit`.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

# --------------------------------------------------------------------------- paths & config

def project_root(start: Path | None = None) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("POSTSMITH_ROOT")
    if env and (Path(env) / "pyproject.toml").exists():
        return Path(env).resolve()
    p = (start or Path(__file__).resolve().parent)
    for cand in [p, *p.parents]:
        if (cand / "pyproject.toml").exists() and (cand / "config" / "postsmith.yaml").exists():
            return cand
    return Path.cwd().resolve()


ROOT = project_root()


def rel(path: Path | str) -> str:
    """Project-relative string for a path (absolute paths outside the project are returned unchanged)."""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def load_yaml(path: Path | str) -> Any:
    if yaml is None:
        raise RuntimeError("pyyaml is required: run `uv sync`")
    with open(ROOT / path if not Path(path).is_absolute() else path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dump_yaml(obj: Any) -> str:
    if yaml is None:
        raise RuntimeError("pyyaml is required: run `uv sync`")
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=1000)


_CONFIG: dict | None = None


def load_config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_yaml("config/postsmith.yaml")
    return _CONFIG


def rubric_dir() -> Path:
    cur = ROOT / "evals" / "rubric" / "current"
    if cur.exists():
        return cur.resolve()
    versions = sorted((ROOT / "evals" / "rubric").glob("v*"))
    if not versions:
        raise FileNotFoundError("no rubric version under evals/rubric/")
    return versions[-1]


def rubric_version() -> str:
    return rubric_dir().name


def load_thresholds() -> dict:
    return load_yaml(rubric_dir() / "thresholds.yaml")


def load_patterns() -> dict:
    return load_yaml(rubric_dir() / "patterns.yaml")


def load_lexicon() -> dict:
    p = ROOT / "style" / "lexicon.yaml"
    return load_yaml(p) if p.exists() else {"lexicon_version": 0, "tiers": {}, "do_not_reuse": {}, "user_tells": []}


def load_profile() -> dict | None:
    p = ROOT / "style" / "profile.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return _dt.date.today().isoformat()


# --------------------------------------------------------------------------- front matter

_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)


def split_front_matter(text: str) -> tuple[dict, str]:
    """Return (meta, body). Body is everything after the closing --- (leading newline stripped once)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    meta = load_yaml_str(m.group(1))
    body = text[m.end():]
    return (meta or {}), body


def load_yaml_str(s: str) -> Any:
    if yaml is None:
        raise RuntimeError("pyyaml is required: run `uv sync`")
    return yaml.safe_load(s)


def read_front_matter_file(path: Path | str) -> tuple[dict, str]:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return split_front_matter(p.read_text(encoding="utf-8"))


def write_front_matter_file(path: Path | str, meta: dict, body: str) -> None:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    body = body.rstrip("\n") + "\n"
    p.write_text("---\n" + dump_yaml(meta) + "---\n" + body, encoding="utf-8")


# --------------------------------------------------------------------------- text utilities

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
# One emoji = one match: a regional-indicator flag pair, a keycap (digit/#/* + optional VS16 + U+20E3), or a base
# pictograph followed by any run of VS16, skin-tone modifiers (U+1F3FB-1F3FF) and ZWJ-joined elements.
_EMOJI_BASE = ("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U0001F900-\U0001F9FF"
               "⭐⬆↔-↪⏩-⏺▪-◾⤴⤵〰〽㊗㊙\U0001F1E6-\U0001F1FF]")
EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[0-9#*]️?⃣"
    "|" + _EMOJI_BASE + "(?:️|[\U0001F3FB-\U0001F3FF]|‍(?:" + _EMOJI_BASE + "|[♀♂⚕⚖✈❤])️?)*)"
)
HASHTAG_RE = re.compile(r"(?<![\w&])#[A-Za-z][\w]*")
MENTION_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_.]{2,}")
CJK_RE = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿가-힯豈-﫿＀-￯]")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n{2,}|\n(?=[A-Z0-9\"'(])")

QUOTE_MAP = {"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'", "—": "-", "–": "-", "―": "-", "…": "...", " ": " "}


def fold_punct(s: str) -> str:
    """NFKC + fold curly quotes/dashes/ellipsis/nbsp; used by judge_io and overlap matching."""
    s = unicodedata.normalize("NFKC", s)
    for k, v in QUOTE_MAP.items():
        s = s.replace(k, v)
    return s


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_text(s: str, strip_urls: bool = True, strip_punct: bool = True) -> str:
    """Canonical normalization for hashing and overlap: NFKC, folded punctuation, lowercase, URLs
    stripped, whitespace collapsed."""
    s = fold_punct(s).lower()
    if strip_urls:
        s = URL_RE.sub(" ", s)
    s = EMOJI_RE.sub(" ", s)
    if strip_punct:
        s = re.sub(r"[^\w\s']", " ", s)
        s = s.replace("'", "")
    return collapse_ws(s)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def content_sha(text: str) -> str:
    return sha256_text(normalize_text(text))


def words(s: str) -> list[str]:
    return WORD_RE.findall(fold_punct(s))


def word_tokens_normalized(s: str) -> list[str]:
    return normalize_text(s).split()


def lines(s: str) -> list[str]:
    return s.replace("\r\n", "\n").split("\n")


def nonblank_lines(s: str) -> list[str]:
    return [ln for ln in lines(s) if ln.strip()]


def sentences(s: str) -> list[str]:
    parts = [p.strip() for p in SENT_SPLIT_RE.split(fold_punct(s)) if p and p.strip()]
    return parts


def word_ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + n]) for i in range(0, max(0, len(tokens) - n + 1))}


def shared_ngrams(a: list[str], b: list[str], n: int) -> set[tuple[str, ...]]:
    return word_ngrams(a, n) & word_ngrams(b, n)


def longest_common_substring_len(a: str, b: str) -> int:
    """Length of the longest common substring (characters). O(len(a)*len(b)) memory-light DP."""
    if not a or not b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# twitter-text weightedRanges (v3 config, scale 100): code points in these ranges weigh 1, everything else
# (CJK, but also U+2022 bullet, U+2026 ellipsis, U+20AC euro, U+2192 arrow, ...) weighs `cjk_weight` (2).
X_LIGHT_RANGES: tuple[tuple[int, int], ...] = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))
_URL_TRAIL = ".,;:!?'\"]"


def x_char_weight(ch: str, heavy_w: int = 2) -> int:
    """Weight of one non-emoji, non-URL code point as X counts it."""
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in X_LIGHT_RANGES) else heavy_w


def _url_span(m: re.Match) -> tuple[int, int]:
    """Trim trailing punctuation (and an unbalanced closing paren) off a URL match, as twitter-text does."""
    s, e = m.start(), m.end()
    url = m.group(0)
    while e > s:
        last = url[e - s - 1]
        if last in _URL_TRAIL:
            e -= 1
        elif last == ")" and url[: e - s].count(")") > url[: e - s].count("("):
            e -= 1
        else:
            break
    return s, e


def x_segments(text: str, cfg: dict | None = None) -> list[tuple[int, int, int]]:
    """(start, end, weight) segments of `text` as X counts them: URL = url_weight (trailing punctuation left
    outside the URL), emoji (one EMOJI_RE match) = emoji_weight, any other code point = x_char_weight.
    `text` must already be NFC; indices refer to it directly."""
    cfg = cfg or load_config()["platforms"]["x"]
    url_w = int(cfg.get("url_weight", 23))
    emoji_w = int(cfg.get("emoji_weight", 2))
    heavy_w = int(cfg.get("cjk_weight", 2))
    urls = [_url_span(m) for m in URL_RE.finditer(text)]
    out: list[tuple[int, int, int]] = []
    i = 0
    n = len(text)
    ui = 0
    while i < n:
        while ui < len(urls) and urls[ui][1] <= i:
            ui += 1
        if ui < len(urls) and urls[ui][0] == i and urls[ui][1] > i:
            out.append((i, urls[ui][1], url_w))
            i = urls[ui][1]
            continue
        m = EMOJI_RE.match(text, i)
        if m and m.end() > i:
            out.append((i, m.end(), emoji_w))
            i = m.end()
            continue
        out.append((i, i + 1, x_char_weight(text[i], heavy_w)))
        i += 1
    return out


def x_count(text: str, cfg: dict | None = None) -> int:
    """Count characters the way X does (twitter-text v3): NFC; URL = 23; one emoji (flag pairs, keycaps,
    skin tones and ZWJ sequences included) = 2; code points outside X_LIGHT_RANGES = 2; everything else 1."""
    return sum(w for _s, _e, w in x_segments(unicodedata.normalize("NFC", text), cfg))


def x_cut_index(text: str, budget: int, cfg: dict | None = None) -> int:
    """Index i such that text[:i] fits in `budget` X units (text already NFC; a URL or emoji is atomic)."""
    units = 0
    for s, e, w in x_segments(text, cfg):
        if units + w > budget:
            return s
        units += w
    return len(text)


def strip_identity(text: str) -> str:
    """Remove URLs and @mentions for lineups/pairwise; keep casing, emoji, line breaks."""
    t = URL_RE.sub("", text)
    t = MENTION_RE.sub("", t)
    return re.sub(r"[ \t]+\n", "\n", t).strip("\n")


def detect_lang(text: str) -> str:
    """Cheap language guess: 'en' if English stopword ratio is high, 'other' otherwise, 'cjk' when CJK dominates."""
    toks = [t.lower() for t in words(text)]
    if not toks:
        return "en"
    if len(CJK_RE.findall(text)) > 0.3 * max(1, len(text.replace(" ", ""))):
        return "cjk"
    hits = sum(1 for t in toks if t in _EN_STOP)
    return "en" if hits / len(toks) >= 0.12 else "other"


_EN_STOP = set("the a an and or but so if of to in on for with at by from as is are was were be been it its this that these those i you we they he she my your our their not no do does did have has had can could will would should just very".split())

FUNCTION_WORDS = (
    "the a an and or but so if of to in on for with at by from as is are was were be been being it its this that these "
    "those i me my you your we our they them their he she his her not no do does did have has had can could will would "
    "should just very actually literally honestly really only even also still then now here there what which who when how "
    "why all any some more most much many than too about into out up down over"
).split()

HEDGES = ["typically", "might", "may", "could potentially", "arguably", "in some cases", "generally speaking", "it could be argued",
          "to be fair", "tends to", "roughly", "largely", "almost", "in many ways", "perhaps", "somewhat", "kind of", "sort of"]


def stable_seed(*parts: Any) -> int:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def is_heldout_by_hash(content_sha256: str, modulo: int = 4) -> bool:
    return int(content_sha256[:8], 16) % modulo == 0


# --------------------------------------------------------------------------- corpus access

def iter_posts(splits: Iterable[str] = ("train",),
               root: Path | str | None = None) -> Iterable[tuple[dict, str, Path]]:
    """Yield (meta, text, path) for corpus posts. Split names: train -> corpus/posts, heldout -> corpus/heldout,
    self -> corpus/self. `root` names the project to read; it defaults to the process-wide ROOT."""
    base = Path(root) if root else ROOT
    dirs = {"train": base / "corpus" / "posts", "heldout": base / "corpus" / "heldout", "self": base / "corpus" / "self"}
    for s in splits:
        d = dirs[s]
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            meta, body = split_front_matter(p.read_text(encoding="utf-8"))
            yield meta, body.rstrip("\n"), p


def read_jsonl(path: Path | str) -> list[dict]:
    p = ROOT / path if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def append_jsonl(path: Path | str, row: dict) -> None:
    p = ROOT / path if not Path(path).is_absolute() else Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_json(path: Path | str, default: Any = None) -> Any:
    p = ROOT / path if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path | str, obj: Any) -> None:
    p = ROOT / path if not Path(path).is_absolute() else Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_dir(run: str) -> Path:
    p = Path(run)
    if p.is_absolute():
        return p
    if p.parts and p.parts[0] == "drafts":
        return ROOT / p
    return ROOT / "drafts" / run


# --------------------------------------------------------------------------- CLI helpers

def emit(obj: Any, as_json: bool = True, human: str | None = None) -> None:
    if as_json or human is None:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(human)


def error(msg: str, as_json: bool = True, code: int = 0) -> None:
    emit({"ok": False, "error": msg}, as_json, human=f"error: {msg}")
    sys.exit(code)


def base_parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--json", action="store_true", help="JSON output (default for most tools)")
    return ap


def median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x)))
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    return float(xs[mid]) if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def quantile(xs: list[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


# --------------------------------------------------------------------------- project-root switching

class use_root:
    """Context manager that points ROOT, the cached config and $POSTSMITH_ROOT at another project root.

    `with use_root(path): ...` (path None = no change). Restores the previous state on exit, so tools and
    tests can run against a fixture root in-process without leaking it. Raises FileNotFoundError when the
    path is not a directory.
    """

    def __init__(self, root: Path | str | None):
        self.root = Path(root).expanduser().resolve() if root else None
        self._saved: tuple[Path, dict | None, str | None] | None = None

    def __enter__(self) -> Path:
        global ROOT, _CONFIG
        if self.root is None:
            return ROOT
        if not self.root.is_dir():
            raise FileNotFoundError(f"root is not a directory: {self.root}")
        self._saved = (ROOT, _CONFIG, os.environ.get("POSTSMITH_ROOT"))
        ROOT, _CONFIG = self.root, None
        os.environ["POSTSMITH_ROOT"] = str(self.root)
        return ROOT

    def __exit__(self, *exc: object) -> None:
        global ROOT, _CONFIG
        if self._saved is None:
            return
        ROOT, _CONFIG, env = self._saved
        if env is None:
            os.environ.pop("POSTSMITH_ROOT", None)
        else:
            os.environ["POSTSMITH_ROOT"] = env
        self._saved = None


# --------------------------------------------------------------------------- untrusted-text wrapping

# Every wrapper tag a generated prompt uses around text a writer (or the corpus) controls.
UNTRUSTED_TAGS: tuple[str, ...] = ("untrusted_post", "untrusted_claims", "fold_preview", "reference_post", "self_post",
                                   "media_brief", "tool_prompt", "persona_excerpt", "brief_facts")
_UNTRUSTED_TAG_RE = re.compile(r"<(\s*)([/／]?)(\s*)(" + "|".join(UNTRUSTED_TAGS) + r")(?![\w-])", re.IGNORECASE)


def escape_untrusted(text: str) -> str:
    """Neutralise any literal wrapper tag inside untrusted text so it can neither close nor open a block.

    ``</untrusted_post>`` becomes ``<\\/untrusted_post>`` (also for the fullwidth slash), ``<untrusted_post id="A">``
    becomes ``<\\untrusted_post id="A">``; case-insensitive over UNTRUSTED_TAGS. Idempotent.
    """
    def repl(m: re.Match) -> str:
        if m.group(2):
            return "<" + m.group(1) + "\\/" + m.group(3) + m.group(4)
        return "<" + m.group(1) + "\\" + m.group(4)

    return _UNTRUSTED_TAG_RE.sub(repl, text or "")


# --------------------------------------------------------------------------- check results

def check_needs_action(res: Any) -> bool:
    """True when a Tier 0 check result must be acted on: it failed (`pass` false) or it passed the gate but raised a
    flag (platform_check's P2_fold shape: ``class: flag, pass: true, flag: true``)."""
    if not isinstance(res, dict):
        return False
    if res.get("pass", True) is False:
        return True
    return res.get("class") == "flag" and bool(res.get("flag"))


# --------------------------------------------------------------------------- small-corpus rule

def small_corpus_mode(cfg: dict | None = None, root: Path | str | None = None,
                      platform: str | None = None) -> bool:
    """config.corpus rule, counted over the train split (corpus/posts) only, the same way status.py counts it:
    fewer than small_corpus_max_posts train posts, or fewer than small_corpus_min_per_platform on a platform.

    A platform the corpus holds no reference for at all does not put the whole corpus in small-corpus mode: with
    55 LinkedIn references and no X reference, the LinkedIn side has a real heldout split, an oracle and lineups,
    and only the X side is unanchored. Pass `platform` to ask about one side (that platform's own count decides,
    so an X candidate is still judged as small-corpus); omit it for the corpus-wide answer, which ignores
    platforms with zero posts."""
    cfg = cfg or load_config()
    ccfg = (cfg.get("corpus") or {}) if isinstance(cfg, dict) else {}
    max_posts = int(ccfg.get("small_corpus_max_posts", 24))
    min_per_platform = int(ccfg.get("small_corpus_min_per_platform", 6))
    base = Path(root) if root else ROOT
    per_platform: dict[str, int] = {"linkedin": 0, "x": 0}
    n = 0
    d = base / "corpus" / "posts"
    if d.exists():
        for p in sorted(d.glob("*.md")):
            n += 1
            try:
                meta, _ = split_front_matter(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - a malformed post counts as a post of unknown platform
                meta = {}
            plat = str((meta or {}).get("platform") or "unknown").lower() if isinstance(meta, dict) else "unknown"
            per_platform[plat] = per_platform.get(plat, 0) + 1
    if n < max_posts:
        return True
    if platform:
        return per_platform.get(str(platform).lower(), 0) < min_per_platform
    return any(0 < per_platform.get(p, 0) < min_per_platform for p in ("linkedin", "x"))
