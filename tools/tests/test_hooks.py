"""Tests for the PreToolUse hooks `.claude/hooks/guard_paths.py` and `guard_writes.py`.

Every test runs the script as a subprocess with crafted stdin JSON and CLAUDE_PROJECT_DIR pointing at a
temporary project tree, exactly as Claude Code invokes it. Exit 2 = blocked (reason on stderr), exit 0 = allowed.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"
GUARD_PATHS = HOOKS / "guard_paths.py"
GUARD_WRITES = HOOKS / "guard_writes.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hooks"

AGENTS = ROOT / ".claude" / "agents"


def _args(name: str) -> list[str]:
    return shlex.split((FIXTURES / "agent_args" / f"{name}.txt").read_text())


WRITER_PATHS = _args("post_writer_paths")
# a deny-only policy (the writer's deny list) for the Bash path-extraction tests
WRITER_DENY = shlex.split("--deny corpus/heldout corpus/cards corpus/features corpus/ratings.jsonl evals memory/performance.jsonl "
                          "memory/published 'drafts/*/round*/scores' 'drafts/*/tier2' 'drafts/*/round*/feedback' 'drafts/*/final'")
WRITER_WRITES = _args("post_writer_writes")
JUDGE_PATHS = _args("judge_reader_paths")
JUDGE_WRITES = _args("judge_reader_writes")
LINEUP_PATHS = _args("judge_lineup_paths")
LINEUP_WRITES = _args("judge_lineup_writes")
PAIRWISE_PATHS = _args("judge_pairwise_paths")
PAIRWISE_WRITES = _args("judge_pairwise_writes")
PERSONA_PATHS = _args("judge_persona_paths")
PERSONA_WRITES = _args("judge_persona_writes")
SCOUT_DENY = _args("angle_scout_paths")
SCOUT_WRITES = _args("angle_scout_writes")
BUILDER_PATHS = _args("profile_builder_paths")
BUILDER_DENY = BUILDER_PATHS[:BUILDER_PATHS.index("--bash-prefix")]   # the builder's deny list without the Bash prefix rule
ANNOTATOR_PATHS = _args("post_annotator_paths")
DIRECTOR_PATHS = _args("media_director_paths")
DIRECTOR_WRITES = _args("media_director_writes")


# --------------------------------------------------------------------------- helpers

@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A miniature postsmith tree: corpus splits, a run, a rubric behind a `current` symlink."""
    files = [
        "pyproject.toml",
        "corpus/posts/acosta_001.md",
        "corpus/heldout/acosta_004.md",
        "corpus/heldout/x.md",
        "corpus/heldout/cards/acosta_004.md",
        "corpus/cards/acosta_001.md",
        "corpus/ratings.jsonl",
        "style/persona.md",
        "memory/lessons.md",
        "memory/performance.jsonl",
        "drafts/run_a/brief.md",
        "drafts/run_a/brief_inputs.json",
        "drafts/run_a/matrix.json",
        "drafts/run_a/round1/prompts/r1-w1-li.reader.md",
        "drafts/run_a/round1/candidates/r1-w1-li.md",
        "drafts/run_a/round1/scores/r1-w1-li.tier0.json",
        "drafts/run_a/round1/feedback/r1-w1-li.md",
        "drafts/run_a/tier2/lineup_r1-w1-li.prompt.md",
        "drafts/run_a/tier2/lineup_r1-w1-li.key.json",
        "drafts/eval_2026-09-17/prompts/neg1.reader.md",
        "evals/rubric/v1/rubric.md",
        "evals/rubric/v1/anchors/clarity/weak.md",
        "evals/calibration.jsonl",
        "evals/golden/expected.json",
        "tools/tier0.py",
    ]
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    os.symlink("v1", tmp_path / "evals" / "rubric" / "current")
    return tmp_path


def run_hook(script: Path, args: list[str], payload, project: Path, env_extra: dict | None = None,
             python: str | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("POSTSMITH_HOOK_LOG", "CLAUDE_PROJECT_DIR")}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.update(env_extra or {})
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([python or sys.executable, str(script), *args], input=stdin, capture_output=True,
                          text=True, env=env, cwd=str(project), timeout=30, check=False)


def payload(tool: str, project: Path, **tool_input) -> dict:
    """Build a PreToolUse document; relative `file_path`/`path` values are made absolute like Claude Code does."""
    ti = {}
    for k, v in tool_input.items():
        if k in ("file_path", "path", "notebook_path") and isinstance(v, str) and not v.startswith("/"):
            v = str(project / v)
        ti[k] = v
    return {"session_id": "sess-test", "hook_event_name": "PreToolUse", "cwd": str(project),
            "tool_name": tool, "tool_input": ti}


def fixture_payload(name: str, project: Path) -> dict:
    raw = (FIXTURES / "payloads" / f"{name}.json").read_text(encoding="utf-8")
    return json.loads(raw.replace("{PROJECT}", str(project)))


def assert_blocked(res: subprocess.CompletedProcess, *needles: str) -> None:
    assert res.returncode == 2, f"expected block, got rc={res.returncode} stderr={res.stderr!r}"
    lines = [ln for ln in res.stderr.splitlines() if ln.strip()]
    assert len(lines) == 1, f"reason must be a single line, got {res.stderr!r}"
    for n in needles:
        assert n in res.stderr, f"{n!r} not in reason {res.stderr!r}"


def assert_allowed(res: subprocess.CompletedProcess) -> None:
    assert res.returncode == 0, f"expected pass, got rc={res.returncode} stderr={res.stderr!r}"


# --------------------------------------------------------------------------- script hygiene

@pytest.mark.parametrize("script", [GUARD_PATHS, GUARD_WRITES])
def test_scripts_are_stdlib_only_with_shebang(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3\n")
    stdlib = set(sys.stdlib_module_names) | {"guard_paths"}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            mod = s.split()[1].split(".")[0]
            assert mod in stdlib, f"non-stdlib import in {script.name}: {s}"


@pytest.mark.parametrize("script", [GUARD_PATHS, GUARD_WRITES])
def test_help_exits_zero(script: Path, project: Path) -> None:
    res = run_hook(script, ["--help"], "", project)
    assert res.returncode == 0
    assert "--allow" in res.stdout and "--deny" in res.stdout


@pytest.mark.skipif(shutil.which("python3") is None, reason="no python3 on PATH")
def test_runs_under_system_python3_outside_uv(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_heldout", project), project,
                   python=shutil.which("python3"))
    assert_blocked(res, "corpus/heldout")
    assert not (HOOKS / "__pycache__").exists()


# --------------------------------------------------------------------------- guard_paths: Read

def test_read_denied_path_blocked(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_heldout", project), project)
    assert_blocked(res, "guard_paths", "Read", "corpus/heldout/acosta_004.md", "corpus/heldout")


def test_read_allowed_path_passes(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_train_post", project), project)
    assert_allowed(res)
    assert res.stderr == ""


def test_directory_glob_covers_descendants_and_dir_itself(project: Path) -> None:
    for target in ("corpus/heldout", "corpus/heldout/", "corpus/heldout/cards/acosta_004.md"):
        res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Read", project, file_path=target), project)
        assert_blocked(res, "corpus/heldout")
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Read", project, file_path="corpus/posts"), project)
    assert_allowed(res)


def test_dotdot_traversal_is_normalised(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"],
                   payload("Read", project, file_path="corpus/posts/../heldout/x.md"), project)
    assert_blocked(res, "corpus/heldout/x.md")


def test_symlink_into_denied_dir_is_resolved(project: Path) -> None:
    (project / "tmp").mkdir()
    os.symlink(project / "corpus" / "heldout", project / "tmp" / "innocent")
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"],
                   payload("Read", project, file_path="tmp/innocent/x.md"), project)
    assert_blocked(res, "corpus/heldout")


def test_relative_file_path_resolves_against_project_dir(project: Path, tmp_path_factory) -> None:
    doc = {"tool_name": "Read", "tool_input": {"file_path": "corpus/heldout/x.md"}}
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    env.pop("POSTSMITH_HOOK_LOG", None)
    res = subprocess.run([sys.executable, str(GUARD_PATHS), "--deny", "corpus/heldout"], input=json.dumps(doc),
                         capture_output=True, text=True, env=env, cwd=str(elsewhere), check=False)
    assert_blocked(res, "corpus/heldout/x.md")


def test_project_dir_falls_back_to_cwd(project: Path) -> None:
    doc = {"tool_name": "Read", "tool_input": {"file_path": str(project / "corpus" / "heldout" / "x.md")}}
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "POSTSMITH_HOOK_LOG")}
    res = subprocess.run([sys.executable, str(GUARD_PATHS), "--deny", "corpus/heldout"], input=json.dumps(doc),
                         capture_output=True, text=True, env=env, cwd=str(project), check=False)
    assert_blocked(res, "corpus/heldout/x.md")


def test_read_outside_project_passes_deny_only_mode(project: Path, tmp_path_factory) -> None:
    other = tmp_path_factory.mktemp("other") / "notes.md"
    other.write_text("hi")
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Read", project, file_path=str(other)), project)
    assert_allowed(res)


def test_multiple_deny_globs_any_match_blocks(project: Path) -> None:
    args = ["--deny", "corpus/heldout", "corpus/ratings.jsonl", "evals", "memory/performance.jsonl"]
    for target in ("corpus/ratings.jsonl", "evals/calibration.jsonl", "memory/performance.jsonl",
                   "evals/rubric/v1/rubric.md"):
        assert_blocked(run_hook(GUARD_PATHS, args, payload("Read", project, file_path=target), project))
    for target in ("memory/lessons.md", "style/persona.md", "corpus/posts/acosta_001.md"):
        assert_allowed(run_hook(GUARD_PATHS, args, payload("Read", project, file_path=target), project))


# --------------------------------------------------------------------------- guard_paths: Grep / Glob

def test_grep_with_path_arg(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("grep_heldout_path", project), project)
    assert_blocked(res, "Grep", "corpus/heldout")
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"],
                   payload("Grep", project, pattern="foo", path="corpus/posts"), project)
    assert_allowed(res)


def test_grep_over_ancestor_of_denied_dir_is_blocked(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Grep", project, pattern="foo", path="corpus"), project)
    assert_blocked(res, "Grep corpus", "search would reach", "corpus/heldout")
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Grep", project, pattern="foo"), project)
    assert_blocked(res, "Grep .", "corpus/heldout")


def test_grep_on_a_single_file_has_no_ancestor_rule(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"],
                   payload("Grep", project, pattern="foo", path="corpus/posts/acosta_001.md"), project)
    assert_allowed(res)
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"],
                   payload("Grep", project, pattern="foo", path="corpus/heldout/x.md"), project)
    assert_blocked(res, "corpus/heldout/x.md")


def test_grep_glob_filter_with_path_component(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"],
                   payload("Grep", project, pattern="foo", path="corpus/posts", glob="../heldout/*.md"), project)
    assert_blocked(res, "corpus/heldout")


def test_glob_pattern(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("glob_heldout_pattern", project), project)
    assert_blocked(res, "Glob", "corpus/heldout")
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Glob", project, pattern="*.md", path="corpus/posts"), project)
    assert_allowed(res)
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"],
                   payload("Glob", project, pattern="drafts/run_a/round1/prompts/*.md"), project)
    assert_allowed(res)
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Glob", project, pattern="**/*.md"), project)
    assert_blocked(res, "corpus/heldout")


# --------------------------------------------------------------------------- guard_paths: Bash

def test_bash_command_mentioning_heldout_blocked(project: Path) -> None:
    res = run_hook(GUARD_PATHS, WRITER_DENY, fixture_payload("bash_cat_heldout", project), project)
    assert_blocked(res, "Bash", "corpus/heldout/x.md")


def test_bash_tier0_on_drafts_allowed(project: Path) -> None:
    res = run_hook(GUARD_PATHS, WRITER_DENY, fixture_payload("bash_tier0", project), project)
    assert_allowed(res)


@pytest.mark.parametrize("command", [
    "cat corpus/heldout/x.md | head",
    "cat \"corpus/heldout/x.md\"",
    "head -n 5 ./corpus/heldout/x.md",
    "cat corpus/posts/../heldout/x.md",
    "cd corpus/heldout && ls",
    "cat corpus/heldout/*.md",
    "ls corpus/heldout/",
    "python3 -c \"print(open('corpus/heldout/x.md').read())\"",
    "cat {PROJECT}/corpus/heldout/x.md",
    "uv run tools/tier0.py --in=corpus/heldout/x.md",
    "cat evals/calibration.jsonl 2>/dev/null",
    "ls evals",
    "grep -r foo drafts/run_a/round1/scores",
])
def test_bash_denied_forms(project: Path, command: str) -> None:
    command = command.replace("{PROJECT}", str(project))
    res = run_hook(GUARD_PATHS, WRITER_DENY, payload("Bash", project, command=command), project)
    assert_blocked(res, "Bash")


@pytest.mark.parametrize("command", [
    "uv run tools/tier0.py drafts/x",
    "uv run tools/tier0.py drafts/run_a/round1/candidates/r1-w1-li.md --json",
    "cat style/persona.md memory/lessons.md",
    "echo hi > /dev/null",
    "ls -la",
    "git status",
    "cat drafts/run_a/brief.md",
    "curl https://example.com/corpus/heldout/x.md -o /dev/null",
])
def test_bash_allowed_forms(project: Path, command: str) -> None:
    res = run_hook(GUARD_PATHS, WRITER_DENY, payload("Bash", project, command=command), project)
    assert_allowed(res)


def test_bash_absolute_path_outside_project_is_ignored(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--allow", "tools/**", "--deny", "corpus/heldout"],
                   payload("Bash", project, command="python3 tools/tier0.py > /dev/null"), project)
    assert_allowed(res)


# --------------------------------------------------------------------------- guard_paths: allow lists

def test_allow_list_blocks_anything_unlisted(project: Path) -> None:
    args = ["--allow", "drafts/*/round*/prompts/*", "evals/rubric/current/**"]
    assert_allowed(run_hook(GUARD_PATHS, args, payload("Read", project, file_path="drafts/run_a/round1/prompts/r1-w1-li.reader.md"), project))
    res = run_hook(GUARD_PATHS, args, payload("Read", project, file_path="drafts/run_a/brief.md"), project)
    assert_blocked(res, "not in allow list", "drafts/run_a/brief.md")
    res = run_hook(GUARD_PATHS, args, payload("Read", project, file_path="corpus/posts/acosta_001.md"), project)
    assert_blocked(res, "not in allow list")


def test_allow_list_with_no_targets_passes(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--allow", "drafts/**"], payload("Bash", project, command="echo hi"), project)
    assert_allowed(res)


def test_allow_list_blocks_outside_project(project: Path, tmp_path_factory) -> None:
    other = tmp_path_factory.mktemp("other") / "notes.md"
    other.write_text("hi")
    res = run_hook(GUARD_PATHS, ["--allow", "drafts/**"], payload("Read", project, file_path=str(other)), project)
    assert_blocked(res, "outside the project")


def test_deny_wins_over_allow(project: Path) -> None:
    args = ["--allow", "drafts/**", "--deny", "*.key.json"]
    res = run_hook(GUARD_PATHS, args, payload("Read", project, file_path="drafts/run_a/tier2/lineup_r1-w1-li.key.json"), project)
    assert_blocked(res, "deny glob '*.key.json'")
    assert_allowed(run_hook(GUARD_PATHS, args, payload("Read", project, file_path="drafts/run_a/tier2/lineup_r1-w1-li.prompt.md"), project))


def test_symlinked_rubric_allow_uses_resolved_path_and_deny_uses_both(project: Path) -> None:
    doc = payload("Read", project, file_path="evals/rubric/current/rubric.md")
    # allow: the symlink-resolved spelling must be allowed (judge-reader lists evals/rubric/v*/** for this)
    assert_allowed(run_hook(GUARD_PATHS, ["--allow", "evals/rubric/v*/**"], doc, project))
    assert_allowed(run_hook(GUARD_PATHS, ["--allow", "evals/rubric/current/**", "evals/rubric/v*/**"], doc, project))
    res = run_hook(GUARD_PATHS, ["--allow", "evals/rubric/current/**"], doc, project)
    assert_blocked(res, "evals/rubric/current/rubric.md", "resolves to evals/rubric/v1/rubric.md")
    # deny: either spelling blocks
    assert_blocked(run_hook(GUARD_PATHS, ["--deny", "evals/rubric/v1"], doc, project), "evals/rubric/v1")
    assert_blocked(run_hook(GUARD_PATHS, ["--deny", "evals/rubric/current"], doc, project), "evals/rubric/current")


def test_bash_with_allow_list_requires_every_target_allowed(project: Path) -> None:
    args = ["--allow", "tools/**", "drafts/*/round*/candidates/*"]
    assert_allowed(run_hook(GUARD_PATHS, args, payload("Bash", project, command="uv run tools/tier0.py drafts/run_a/round1/candidates/r1-w1-li.md"), project))
    res = run_hook(GUARD_PATHS, args, payload("Bash", project, command="uv run tools/tier0.py drafts/run_a/round1/candidates/r1-w1-li.md corpus/posts/acosta_001.md"), project)
    assert_blocked(res, "corpus/posts/acosta_001.md", "not in allow list")


# --------------------------------------------------------------------------- real agent policies

@pytest.mark.parametrize("agent,stem", [
    ("judge-reader", "judge_reader"), ("judge-lineup", "judge_lineup"), ("judge-pairwise", "judge_pairwise"),
    ("judge-persona", "judge_persona"), ("post-writer", "post_writer"), ("angle-scout", "angle_scout"),
    ("profile-builder", "profile_builder"), ("post-annotator", "post_annotator"), ("card-verifier", "card_verifier"),
    ("judge-voice", "judge_voice"), ("judge-comedy", "judge_comedy"), ("media-judge", "media_judge"),
    ("media-director", "media_director"),
])
def test_agent_args_match_agent_files(agent: str, stem: str) -> None:
    """The fixture strings are the real front-matter policies: an edit to an agent file must land here too."""
    import re
    text = (AGENTS / f"{agent}.md").read_text(encoding="utf-8")
    for hook in ("guard_paths", "guard_writes"):
        m = re.search(r"python3 \$\{CLAUDE_PROJECT_DIR\}/\.claude/hooks/" + hook + r"\.py ([^\"]*)\"", text)
        assert m, f"{agent}.md has no {hook} hook"
        fixture = (FIXTURES / "agent_args" / f"{stem}_{'paths' if hook == 'guard_paths' else 'writes'}.txt").read_text().strip()
        assert m.group(1).strip() == fixture, f"{agent}.md {hook} args differ from the fixture"


def test_judge_reader_policy(project: Path) -> None:
    allowed = [
        "drafts/run_a/round1/prompts/r1-w1-li.reader.md",
        "drafts/run_a/round1/prompts/r1-w1-li.reader.rerun-comedy.md",
        "drafts/run_a/round1/prompts/r1-w1-li.jury.reader.not_ai.md",
        "drafts/eval_2026-09-17/prompts/neg1.reader.md",
        "evals/rubric/current/rubric.md",
        "evals/rubric/current/anchors/clarity/weak.md",
        "evals/rubric/v1/rubric.md",
    ]
    blocked = [
        "drafts/run_a/round1/prompts/r1-w1-li.voice.md",            # another lens's prompt
        "drafts/run_a/round1/prompts/r1-w1-li.jury.voice.not_ai.md",
        "drafts/run_a/round1/writers/writer-1.0cd43ee122.md",      # writer assignments
        "drafts/run_a/round1/writers/rewrite-r1-w1-li.9f13ab0c74.md",   # inlined feedback packet + previous candidate
        "drafts/run_a/tier2/lineup_r1-w1-li.prompt.md",             # Tier 2 prompts belong to judge-lineup / judge-pairwise
        "drafts/run_a/tier2/pairwise_ab12cd34.exemplar1.prompt.md",
        "drafts/run_a/tier2/claims_r1-w1-li.prompt.md",
        "drafts/run_a/archive/round1/prompts/r1-w1-li.reader.md",   # a delivered run's prompts
        "drafts/run_a/brief.md",
        "drafts/run_a/brief_inputs.json",
        "drafts/run_a/matrix.json",
        "drafts/run_a/state.json",
        "drafts/run_a/round1/candidates/r1-w1-li.md",
        "drafts/run_a/round1/scores/r1-w1-li.tier0.json",
        "drafts/run_a/round1/feedback/r1-w1-li.md",
        "drafts/run_a/tier2/lineup_r1-w1-li.key.json",
        "corpus/posts/acosta_001.md",
        "corpus/heldout/acosta_004.md",
        "style/persona.md",
        "memory/lessons.md",
        "evals/golden/expected.json",
        "evals/calibration.jsonl",
        "CLAUDE.md",
    ]
    for t in allowed:
        assert_allowed(run_hook(GUARD_PATHS, JUDGE_PATHS, payload("Read", project, file_path=t), project))
    for t in blocked:
        assert_blocked(run_hook(GUARD_PATHS, JUDGE_PATHS, payload("Read", project, file_path=t), project))


def test_judge_reader_write_policy(project: Path) -> None:
    assert_allowed(run_hook(GUARD_WRITES, JUDGE_WRITES, fixture_payload("write_scores", project), project))
    for t in ("drafts/run_a/round1/scores/r1-w1-li.reader.rerun-comedy.json",
              "drafts/run_a/round1/scores/r1-w1-li.jury.reader.not_ai.json",
              "drafts/eval_2026-09-17/round1/scores/neg1.reader.json"):
        assert_allowed(run_hook(GUARD_WRITES, JUDGE_WRITES, payload("Write", project, file_path=t, content="{}"), project))
    for t in ("drafts/run_a/round1/scores/r1-w1-li.voice.json",             # another lens's judgement
              "drafts/run_a/round1/scores/r1-w1-li.jury.voice.not_ai.json",
              "drafts/run_a/round1/scores/r1-w2-li.comedy.json",
              "drafts/run_a/tier2/lineup_ab12cd34.picks/reader.json",       # picks belong to judge-lineup
              "drafts/run_a/tier2/pairwise_ab12cd34.verdicts/reader.12.json",
              "drafts/run_a/tier2/claims_r1-w1-li.json",
              "drafts/run_a/media/r1-w1-li.media-judge.json",
              "drafts/run_a/round1/candidates/r1-w1-li.txt",
              "drafts/run_a/round1/candidates/r1-w1-li.md", "drafts/run_a/brief.md", "corpus/posts/acosta_001.md",
              "evals/rubric/v1/rubric.md", "memory/lessons.md", "evals/golden/expected.json"):
        assert_blocked(run_hook(GUARD_WRITES, JUDGE_WRITES, payload("Write", project, file_path=t, content="{}"), project))


def test_judge_lineup_and_pairwise_policies(project: Path) -> None:
    lineup_prompt = "drafts/run_a/tier2/lineup_ab12cd34.reader.prompt.md"
    pairwise_prompt = "drafts/run_a/tier2/pairwise_ab12cd34.exemplar1.prompt.md"
    for t in (lineup_prompt, "evals/rubric/current/rubric.md"):
        assert_allowed(run_hook(GUARD_PATHS, LINEUP_PATHS, payload("Read", project, file_path=t), project))
    for t in (pairwise_prompt, "drafts/run_a/tier2/claims_r1-w1-li.prompt.md", "drafts/run_a/round1/prompts/r1-w1-li.reader.md",
              "drafts/run_a/round1/writers/writer-1.0cd43ee122.md", "drafts/run_a/tier2/lineup_r1-w1-li.key.json",
              "drafts/run_a/round1/candidates/r1-w1-li.md", "corpus/heldout/acosta_004.md"):
        assert_blocked(run_hook(GUARD_PATHS, LINEUP_PATHS, payload("Read", project, file_path=t), project))
    for t in (pairwise_prompt, "evals/rubric/current/rubric.md"):
        assert_allowed(run_hook(GUARD_PATHS, PAIRWISE_PATHS, payload("Read", project, file_path=t), project))
    for t in (lineup_prompt, "drafts/run_a/round1/prompts/r1-w1-li.reader.md", "drafts/run_a/tier2/claims_r1-w1-li.prompt.md"):
        assert_blocked(run_hook(GUARD_PATHS, PAIRWISE_PATHS, payload("Read", project, file_path=t), project))
    # a Grep over the tier2 directory would identify the candidate by elimination: search roots are blocked too
    assert_blocked(run_hook(GUARD_PATHS, LINEUP_PATHS, payload("Grep", project, pattern="Ledger", path="drafts/run_a/tier2"), project))
    # writes: lineup picks only / pairwise verdicts only
    assert_allowed(run_hook(GUARD_WRITES, LINEUP_WRITES, payload("Write", project, file_path="drafts/run_a/tier2/lineup_ab12cd34.picks/reader.json", content="{}"), project))
    for t in ("drafts/run_a/tier2/pairwise_ab12cd34.verdicts/exemplar1.json", "drafts/run_a/round1/scores/r1-w1-li.reader.json",
              "drafts/run_a/tier2/claims_r1-w1-li.json", "drafts/run_a/tier2/lineup_r1-w1-li.score.json"):
        assert_blocked(run_hook(GUARD_WRITES, LINEUP_WRITES, payload("Write", project, file_path=t, content="{}"), project))
    assert_allowed(run_hook(GUARD_WRITES, PAIRWISE_WRITES, payload("Write", project, file_path="drafts/run_a/tier2/pairwise_ab12cd34.verdicts/exemplar1.json", content="{}"), project))
    assert_blocked(run_hook(GUARD_WRITES, PAIRWISE_WRITES, payload("Write", project, file_path="drafts/run_a/tier2/lineup_ab12cd34.picks/reader.json", content="{}"), project))
    # judge-persona: its own prompts plus the Tier 2 claims prompt, never lineups or pairs
    assert_allowed(run_hook(GUARD_PATHS, PERSONA_PATHS, payload("Read", project, file_path="drafts/run_a/tier2/claims_r1-w1-li.prompt.md"), project))
    assert_allowed(run_hook(GUARD_PATHS, PERSONA_PATHS, payload("Read", project, file_path="drafts/run_a/round1/prompts/r1-w1-li.persona.md"), project))
    for t in (lineup_prompt, pairwise_prompt, "style/persona.md", "drafts/run_a/brief.md"):
        assert_blocked(run_hook(GUARD_PATHS, PERSONA_PATHS, payload("Read", project, file_path=t), project))
    assert_allowed(run_hook(GUARD_WRITES, PERSONA_WRITES, payload("Write", project, file_path="drafts/run_a/tier2/claims_r1-w1-li.json", content="[]"), project))
    assert_blocked(run_hook(GUARD_WRITES, PERSONA_WRITES, payload("Write", project, file_path="drafts/run_a/round1/scores/r1-w1-li.reader.json", content="{}"), project))


def test_post_writer_policy(project: Path) -> None:
    for t in ("style/persona.md", "style/authors/lara-acosta.md", "memory/lessons.md", "drafts/run_a/brief.md",
              "drafts/run_a/round1/writers/writer-1.0cd43ee122.md", "drafts/run_a/round2/writers/rewrite-r1-w1-li.9f13ab0c74.md",
              "docs/design/contracts.md", ".claude/skills/post/references/writer_brief.md"):
        assert_allowed(run_hook(GUARD_PATHS, WRITER_PATHS, payload("Read", project, file_path=t), project))
    for t in ("corpus/heldout/acosta_004.md", "corpus/cards/acosta_001.md", "corpus/posts/acosta_001.md", "corpus/ratings.jsonl",
              "evals/rubric/v1/rubric.md", "evals/calibration.jsonl", "memory/performance.jsonl", "memory/topics.md",
              "drafts/run_a/matrix.json", "drafts/run_a/state.json",
              "drafts/run_a/round1/prompts/r1-w1-li.reader.md",              # judge prompts
              "drafts/run_a/round1/candidates/r1-w1-li.md",                  # its own or a sibling's candidate: inlined instead
              "drafts/run_a/round1/candidates/r1-w2-li.md",
              "drafts/run_a/round1/feedback/r1-w1-li.md",                    # packets are inlined into the rewrite prompt
              "drafts/run_a/round1/scores/r1-w1-li.tier0.json", "drafts/run_a/tier2/lineup_r1-w1-li.key.json",
              "drafts/run_a/archive/round1/writers/writer-1.0cd43ee122.md"):
        assert_blocked(run_hook(GUARD_PATHS, WRITER_PATHS, payload("Read", project, file_path=t), project))
    assert_allowed(run_hook(GUARD_WRITES, WRITER_WRITES, fixture_payload("write_candidate", project), project))
    assert_allowed(run_hook(GUARD_WRITES, WRITER_WRITES, payload("Write", project, file_path="drafts/run_a/round2/candidates/r2-w3-x1.md", content="x"), project))
    assert_blocked(run_hook(GUARD_WRITES, WRITER_WRITES, fixture_payload("edit_corpus_post", project), project))
    for t in ("drafts/run_a/round1/scores/r1-w1-li.reader.json",
              "drafts/run_a/round1/candidates/r1-w1-li.txt",      # the judge-facing text is tier0's to write
              "drafts/run_a/round1/candidates/notes.md",
              "drafts/run_a/round1/writers/writer-1.0cd43ee122.md"):
        assert_blocked(run_hook(GUARD_WRITES, WRITER_WRITES, payload("Write", project, file_path=t, content="x"), project))


def test_writer_prompt_token_is_the_per_writer_fence(project: Path) -> None:
    """post-writer's Read allow list can only be a run-wide glob, so the fence is the file name: a writer that
    knows its own number and cid must not be able to construct a sibling's prompt path (contracts §18)."""
    sys.path.insert(0, str(ROOT / "tools"))
    import run_next
    run, mine, sibling = "2026-09-17_agents", 2, 3
    own = run_next.writer_prompt_token(run, 1, mine)
    assert own != run_next.writer_prompt_token(run, 1, sibling)
    assert own != run_next.writer_prompt_token(run, 2, mine)
    assert own != run_next.writer_prompt_token("2026-09-18_agents", 1, mine)
    assert run_next.writer_prompt_token(run, 1, mine) == own                      # deterministic
    # a sibling's real path is `writer-<n>.<its own token>.md`, which the writer cannot compute from its own
    # number, its cid, the run or the round
    assert_allowed(run_hook(GUARD_PATHS, WRITER_PATHS,
                            payload("Read", project, file_path=f"drafts/{run}/round1/writers/writer-{mine}.{own}.md"), project))
    sibling_path = f"drafts/{run}/round1/writers/writer-{sibling}.{run_next.writer_prompt_token(run, 1, sibling)}.md"
    assert sibling_path != f"drafts/{run}/round1/writers/writer-{sibling}.{own}.md"
    # nothing under writers/ has a guessable name: run_next never writes these paths
    assert not any(f.name in (f"writer-{sibling}.md", f"rewrite-r1-w{sibling}-li.md")
                   for f in (project / "drafts").rglob("writers/*.md"))
    for t in ("drafts/run_a/round1/prompts/r1-w1-li.reader.md", "drafts/run_a/round1/feedback/r1-w1-li.md"):
        assert_blocked(run_hook(GUARD_PATHS, WRITER_PATHS, payload("Read", project, file_path=t), project))


def test_media_director_policy(project: Path) -> None:
    """The director writes the brief and the prompts, and nothing that grades them; it reads the caption, the style
    layer and train previews, and nothing that inlines a heldout post or another agent's evidence."""
    for t in ("style/persona.md", "style/media_habits.md", "style/authors/lara-acosta.md", "memory/lessons.md",
              "corpus/manifest.jsonl", "drafts/run_a/round1/candidates/r1-w1-li.md",
              ".claude/skills/media/references/brief_schema.md"):
        assert_allowed(run_hook(GUARD_PATHS, DIRECTOR_PATHS, payload("Read", project, file_path=t), project))
    for t in ("corpus/heldout/acosta_004.md", "corpus/ratings.jsonl", "evals/rubric/v1/rubric.md",
              "evals/calibration.jsonl", "memory/performance.jsonl",
              "drafts/learn_2026-09-17/prompts/vieira_004.annotate.md",   # inlines a heldout post verbatim
              "drafts/learn_2026-09-17/archive/vieira_004.annotate.md",
              "drafts/run_a/brief_inputs.json",
              "drafts/run_a/round1/scores/r1-w1-li.merged.json",          # the judges' evidence about this post
              "drafts/run_a/round1/feedback/r1-w1-li.md"):
        assert_blocked(run_hook(GUARD_PATHS, DIRECTOR_PATHS, payload("Read", project, file_path=t), project))
    for t in ("drafts/run_a/media/r1-w1-li.brief.yaml", "drafts/run_a/media/r1-w1-li.prompts/gpt_image.md"):
        assert_allowed(run_hook(GUARD_WRITES, DIRECTOR_WRITES, payload("Write", project, file_path=t, content="x"), project))
    # the three files that grade the director: a self-written media-judge.json suppresses the media-judge action
    # entirely (run_next only emits it when the file is missing or stale) and feeds its own verdict into tier2
    for t in ("drafts/run_a/media/r1-w1-li.media-judge.json", "drafts/run_a/media/r1-w1-li.media-check.json",
              "drafts/run_a/media/r1-w1-li.judge.prompt.md"):
        assert_blocked(run_hook(GUARD_WRITES, DIRECTOR_WRITES, payload("Write", project, file_path=t, content="{}"), project))


# --------------------------------------------------------------------------- Bash-capable agents (profile-builder)

def _case_insensitive(project: Path) -> bool:
    return os.path.exists(str(project).swapcase()) and os.path.samefile(str(project), str(project).swapcase())


@pytest.mark.parametrize("command", [
    "grep -r '' corpus",
    "find corpus -type f -exec cat {} +",
    "cp -r corpus style/copy",
    "tar cf /tmp/c.tar corpus",
    "cat $PWD/corpus/heldout/x.md",
    "cat ${PWD}/corpus/heldout/x.md",
    "cat \"$CLAUDE_PROJECT_DIR\"/corpus/heldout/x.md",
    "cat ${POSTSMITH_ROOT}/corpus/heldout/x.md",
    "uv run python -c \"open(os.getcwd()+'/corpus/heldout/x.md')\"",
    "cd corpus && cat heldout/x.md",
    "cd corpus; cat heldout/x.md",
    "cd corpus/posts && cat ../heldout/x.md",
    "cat corpus/heldout/x.md",
])
def test_bash_deny_only_reaches_heldout_in_every_spelling(project: Path, command: str) -> None:
    """The profile-builder deny list alone (no Bash prefix rule) still blocks every way of reaching heldout text."""
    res = run_hook(GUARD_PATHS, BUILDER_DENY, payload("Bash", project, command=command), project)
    assert_blocked(res, "Bash")


def test_bash_cwd_from_payload_and_cd_tracking(project: Path) -> None:
    doc = payload("Bash", project, command="cat heldout/x.md")
    doc["cwd"] = str(project / "corpus")                       # Claude Code kept the shell in corpus/ from an earlier `cd corpus`
    assert_blocked(run_hook(GUARD_PATHS, BUILDER_DENY, doc, project), "corpus/heldout/x.md")
    doc["cwd"] = str(project / "corpus" / "posts")
    doc["tool_input"]["command"] = "cat acosta_001.md"          # a train post from inside corpus/posts is fine
    assert_allowed(run_hook(GUARD_PATHS, BUILDER_DENY, doc, project))
    # an allow list plus a cwd outside the project blocks the call outright
    doc = payload("Bash", project, command="cat notes.md")
    doc["cwd"] = str(project.parent)
    assert_blocked(run_hook(GUARD_PATHS, ["--allow", "drafts/**"], doc, project), "working directory outside")
    assert_allowed(run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], doc, project))


def test_bash_truncated_glob_keeps_prefix_as_search_root(project: Path) -> None:
    for i in range(210):  # more files than the expansion cap, sorting before heldout/
        (project / "corpus" / "features" / f"a{i:03d}.md").parent.mkdir(parents=True, exist_ok=True)
        (project / "corpus" / "features" / f"a{i:03d}.md").write_text("x\n")
    res = run_hook(GUARD_PATHS, BUILDER_DENY, payload("Bash", project, command="cat corpus/*/*.md"), project)
    assert_blocked(res, "corpus")


def test_bash_directory_targets_block_only_path_anchored_denies(project: Path) -> None:
    # a bare '*.key.json' deny could match under any directory; it must not turn every `ls <dir>` into a block
    args = ["--deny", "corpus/heldout/**", "*.key.json"]
    assert_allowed(run_hook(GUARD_PATHS, args, payload("Bash", project, command="ls drafts/run_a/tier2"), project))
    assert_allowed(run_hook(GUARD_PATHS, args, payload("Bash", project, command="ls drafts/run_a/round1/candidates"), project))
    assert_blocked(run_hook(GUARD_PATHS, args, payload("Bash", project, command="ls corpus"), project), "search would reach")
    assert_blocked(run_hook(GUARD_PATHS, args, payload("Bash", project, command="cat drafts/run_a/tier2/lineup_r1-w1-li.key.json"), project))
    # Grep/Glob search roots keep the stricter rule
    assert_blocked(run_hook(GUARD_PATHS, args, payload("Grep", project, pattern="x", path="drafts/run_a/tier2"), project))


def test_bash_prefix_rule_for_bash_capable_agents(project: Path) -> None:
    for command in ("uv run tools/card_lint.py --post acosta_001 --json", "uv run tools/profile_stats.py --json",
                    "uv run tools/moves_lint.py --json && uv run tools/quote_leak_check.py --json"):
        assert_allowed(run_hook(GUARD_PATHS, BUILDER_PATHS, payload("Bash", project, command=command), project))
    for command in ("ls corpus/cards", "cat corpus/posts/acosta_001.md", "uv run python -c 'print(1)'",
                    "uv run tools/card_lint.py --json; cat corpus/cards/acosta_001.md",
                    "uv run tools/card_lint.py --json | tee out.txt", "python3 tools/stylometry.py --corpus"):
        res = run_hook(GUARD_PATHS, BUILDER_PATHS, payload("Bash", project, command=command), project)
        assert_blocked(res, "Bash")
    # the deny list is checked before the prefix rule, so a denied path inside an allowed command is still named
    res = run_hook(GUARD_PATHS, BUILDER_PATHS, payload("Bash", project, command="uv run tools/stylometry.py corpus/heldout/x.md"), project)
    assert_blocked(res, "corpus/heldout")


# --------------------------------------------------------------------------- annotation agents (post-annotator, card-verifier)

@pytest.mark.parametrize("stem", ["post_annotator", "card_verifier"])
def test_annotation_agents_read_prompt_files_never_posts(project: Path, stem: str) -> None:
    """contracts §18: the annotator and the verifier read learn prompt files, media, frames, taxonomies and the spec,
    and never a corpus post, card, review, label store or run file (they have no Bash tool; a Bash payload is fenced too)."""
    paths = _args(f"{stem}_paths")
    allowed = [
        "drafts/learn_2026-09-17/prompts/acosta_004.annotate.md",
        "drafts/learn_2026-09-17/prompts/acosta_004.verify.md",
        "corpus/media/acosta_001/preview_1.jpg",
        "corpus/frames/acosta_001/contact.jpg",
        "style/taxonomies/devices.md",
        ".claude/skills/learn/references/card_spec.md",
    ]
    blocked = [
        "corpus/posts/acosta_001.md",
        "corpus/self/self_001.md",
        "corpus/heldout/acosta_004.md",
        "corpus/heldout/cards/acosta_004.md",
        "corpus/cards/acosta_001.md",
        "corpus/cards/_reviews/acosta_001.md",
        "corpus/features/acosta_001.json",
        "corpus/ratings.jsonl",
        "evals/calibration.jsonl",
        "memory/lessons.md",
        "style/persona.md",
        "style/moves.md",
        "drafts/run_a/brief.md",
        "drafts/run_a/round1/candidates/r1-w1-li.md",
        "drafts/learn_2026-09-17/archive/acosta_004.annotate.md",
    ]
    for t in allowed:
        assert_allowed(run_hook(GUARD_PATHS, paths, payload("Read", project, file_path=t), project))
    for t in blocked:
        assert_blocked(run_hook(GUARD_PATHS, paths, payload("Read", project, file_path=t), project))
    assert_blocked(run_hook(GUARD_PATHS, paths, payload("Grep", project, pattern="x", path="corpus"), project))
    assert_blocked(run_hook(GUARD_PATHS, paths, payload("Bash", project, command="cat corpus/posts/acosta_001.md"), project),
                   "corpus/posts/acosta_001.md")


def test_annotation_agents_write_only_their_outputs(project: Path) -> None:
    annot, verif = _args("post_annotator_writes"), _args("card_verifier_writes")
    for t in ("corpus/cards/acosta_001.md", "corpus/heldout/cards/acosta_004.md"):
        assert_allowed(run_hook(GUARD_WRITES, annot, payload("Write", project, file_path=t, content="x"), project))
        assert_blocked(run_hook(GUARD_WRITES, verif, payload("Write", project, file_path=t, content="x"), project))
    # a glob covers its descendants (compile_glob), so the annotator's 'corpus/cards/*' also admits
    # corpus/cards/_reviews/*; only the verifier side of the review paths is asserted here
    for t in ("corpus/cards/_reviews/acosta_001.md", "corpus/heldout/cards/_reviews/acosta_004.md"):
        assert_allowed(run_hook(GUARD_WRITES, verif, payload("Write", project, file_path=t, content="x"), project))
    for t in ("corpus/posts/acosta_001.md", "corpus/heldout/acosta_004.md", "style/moves.md",
              "drafts/learn_2026-09-17/prompts/acosta_004.annotate.md"):
        assert_blocked(run_hook(GUARD_WRITES, annot, payload("Write", project, file_path=t, content="x"), project))
        assert_blocked(run_hook(GUARD_WRITES, verif, payload("Write", project, file_path=t, content="x"), project))


def test_case_insensitive_volume_folds_glob_case(project: Path) -> None:
    if not _case_insensitive(project):
        pytest.skip("case-sensitive volume: nothing to fold")
    for args, target in ((BUILDER_DENY, "CORPUS/heldout/x.md"), (BUILDER_DENY, "corpus/Heldout/x.md"),
                         (ANNOTATOR_PATHS, "CORPUS/ratings.jsonl"), (ANNOTATOR_PATHS, "Drafts/run_a/brief.md"),
                         (JUDGE_PATHS, "Style/persona.md"), (WRITER_PATHS, "Corpus/heldout/x.md")):
        assert_blocked(run_hook(GUARD_PATHS, args, payload("Read", project, file_path=target), project))
    assert_blocked(run_hook(GUARD_PATHS, BUILDER_DENY, payload("Bash", project, command="cat CORPUS/HELDOUT/x.md"), project))
    # an allow list matches case-insensitively too, so a differently-cased legitimate path is not a false block
    assert_allowed(run_hook(GUARD_PATHS, JUDGE_PATHS, payload("Read", project, file_path="Evals/rubric/v1/rubric.md"), project))


def test_glob_helpers_ignore_case_flag() -> None:
    gp = _gp()
    assert gp.glob_match("corpus/heldout", "CORPUS/Heldout/x.md") is False
    assert gp.glob_match("corpus/heldout", "CORPUS/Heldout/x.md", ignore_case=True) is True
    assert gp.could_match_under("corpus/heldout/**", "Corpus", ignore_case=True) is True
    assert gp.is_path_anchored("corpus/heldout/**") and not gp.is_path_anchored("*.key.json")
    assert gp.bash_prefix_violation("uv run tools/a.py && cat x", ["uv run tools/"]) == "cat x"
    assert gp.bash_prefix_violation("uv run tools/a.py", ["uv run tools/"]) is None


def test_root_relative_project_path_is_project_path(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], payload("Read", project, file_path="/corpus/heldout/x.md"), project)
    assert_blocked(res, "corpus/heldout/x.md")


def test_project_settings_guard_the_main_thread() -> None:
    """.claude/settings.json: no auto-approved cat/ls, and a PreToolUse hook that denies the label stores."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    allow = settings["permissions"]["allow"]
    assert "Bash(cat *)" not in allow and "Bash(ls *)" not in allow and "Bash(uv run *)" in allow
    hooks = settings["hooks"]["PreToolUse"]
    cmd = hooks[0]["hooks"][0]["command"]
    assert hooks[0]["matcher"] == "Read|Bash|Grep|Glob" and "guard_paths.py" in cmd
    for needle in ("corpus/heldout/**", "corpus/ratings.jsonl", "evals/calibration.jsonl", "*.key.json"):
        assert needle in cmd


# --------------------------------------------------------------------------- judge_sanity.py (hook-log assertion)

def _log_rows(project: Path, args: list[str], calls: list[tuple[str, list[dict]]]) -> Path:
    log = project / "hook.log"
    for agent_id, docs in calls:
        for doc in docs:
            doc = dict(doc, agent_id=agent_id, agent_type="judge-reader")
            run_hook(GUARD_PATHS, args, doc, project, {"POSTSMITH_HOOK_LOG": str(log)})
    return log


def test_judge_sanity_one_prompt_read_per_call(project: Path) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    import judge_sanity
    prompt = payload("Read", project, file_path="drafts/run_a/round1/prompts/r1-w1-li.reader.md")
    rubric = payload("Read", project, file_path="evals/rubric/current/rubric.md")
    brief = payload("Read", project, file_path="drafts/run_a/brief.md")
    log = _log_rows(project, JUDGE_PATHS, [("call-clean", [prompt, rubric, rubric]),
                                           ("call-dirty", [prompt, prompt, brief])])
    rows = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    res = judge_sanity.check(rows)
    assert res["calls"] == 2 and res["green"] is False
    assert res["per_call"]["call-clean"] == {"rows": 3, "blocked": 0, "prompt_reads": 1, "other_reads": 0, "agent_type": "judge-reader"}
    problems = {p["problem"] for p in res["problems"] if p["call"] == "call-dirty"}
    assert any("blocked" in p for p in problems) and any("exactly one prompt read" in p for p in problems)
    assert not [p for p in res["problems"] if p["call"] == "call-clean"]
    clean = judge_sanity.check([r for r in rows if r["agent_id"] == "call-clean"])
    assert clean["green"] is True and clean["problems"] == []
    assert judge_sanity.check([])["green"] is False  # no judge call at all is not a pass
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "judge_sanity.py"), str(log), "--json"], capture_output=True, text=True, check=False)
    assert out.returncode == 0 and json.loads(out.stdout)["calls"] == 2
    missing = subprocess.run([sys.executable, str(ROOT / "tools" / "judge_sanity.py"), str(project / "nope.log")], capture_output=True, text=True, check=False)
    assert missing.returncode == 0 and json.loads(missing.stdout)["ok"] is False


def test_angle_scout_policy(project: Path) -> None:
    for t in ("style/persona.md", "memory/lessons.md"):
        assert_allowed(run_hook(GUARD_PATHS, SCOUT_DENY, payload("Read", project, file_path=t), project))
    for t in ("drafts/run_a/brief.md", "drafts/run_a/round1/candidates/r1-w1-li.md", "corpus/heldout/x.md", "evals/golden/expected.json"):
        assert_blocked(run_hook(GUARD_PATHS, SCOUT_DENY, payload("Read", project, file_path=t), project))
    assert_allowed(run_hook(GUARD_WRITES, SCOUT_WRITES, payload("Write", project, file_path="drafts/run_a/brief_inputs.json", content="{}"), project))
    assert_blocked(run_hook(GUARD_WRITES, SCOUT_WRITES, payload("Write", project, file_path="drafts/run_a/brief.md", content="x"), project))


# --------------------------------------------------------------------------- guard_writes

def test_write_outside_allow_list_blocked(project: Path) -> None:
    res = run_hook(GUARD_WRITES, ["--allow", "drafts/*/round*/scores/*"], payload("Write", project, file_path="corpus/posts/acosta_001.md", content="x"), project)
    assert_blocked(res, "guard_writes", "Write corpus/posts/acosta_001.md", "not in allow list")


def test_write_inside_allow_list_passes_even_when_file_does_not_exist(project: Path) -> None:
    res = run_hook(GUARD_WRITES, ["--allow", "drafts/*/round*/scores/*"],
                   payload("Write", project, file_path="drafts/run_b/round3/scores/r3-w2-x.voice.json", content="{}"), project)
    assert_allowed(res)


@pytest.mark.parametrize("tool,key", [("Edit", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")])
def test_all_write_tools_are_guarded(project: Path, tool: str, key: str) -> None:
    args = ["--allow", "drafts/**"]
    assert_blocked(run_hook(GUARD_WRITES, args, payload(tool, project, **{key: "corpus/posts/acosta_001.md"}), project), tool)
    assert_allowed(run_hook(GUARD_WRITES, args, payload(tool, project, **{key: "drafts/run_a/round1/scores/n.ipynb"}), project))


def test_write_traversal_and_symlink_resolved(project: Path) -> None:
    args = ["--allow", "drafts/**"]
    res = run_hook(GUARD_WRITES, args, payload("Write", project, file_path="drafts/run_a/../../corpus/posts/acosta_001.md", content="x"), project)
    assert_blocked(res, "corpus/posts/acosta_001.md")
    os.symlink(project / "corpus" / "posts", project / "drafts" / "run_a" / "escape")
    res = run_hook(GUARD_WRITES, args, payload("Write", project, file_path="drafts/run_a/escape/acosta_001.md", content="x"), project)
    assert_blocked(res, "corpus/posts/acosta_001.md")


def test_write_deny_wins_over_allow(project: Path) -> None:
    args = ["--allow", "drafts/**", "--deny", "*.key.json"]
    assert_blocked(run_hook(GUARD_WRITES, args, payload("Write", project, file_path="drafts/run_a/tier2/lineup_x.key.json", content="{}"), project), "deny glob")
    assert_allowed(run_hook(GUARD_WRITES, args, payload("Write", project, file_path="drafts/run_a/tier2/lineup_x.prompt.md", content="{}"), project))


def test_write_with_no_allow_globs_blocks_everything(project: Path) -> None:
    res = run_hook(GUARD_WRITES, [], payload("Write", project, file_path="drafts/run_a/round1/scores/a.json", content="{}"), project)
    assert_blocked(res, "no --allow globs")


def test_write_hook_ignores_non_write_tools(project: Path) -> None:
    for doc in (fixture_payload("read_heldout", project), payload("Bash", project, command="cat corpus/heldout/x.md")):
        assert_allowed(run_hook(GUARD_WRITES, ["--allow", "drafts/**"], doc, project))


# --------------------------------------------------------------------------- malformed input

@pytest.mark.parametrize("script", [GUARD_PATHS, GUARD_WRITES])
@pytest.mark.parametrize("stdin", ["", "   \n", "not json", "[1, 2]", '{"tool_name": "Read"}', '{"tool_name": "Read", "tool_input": "corpus/heldout/x.md"}'])
def test_malformed_or_targetless_input_passes(script: Path, project: Path, stdin: str) -> None:
    res = run_hook(script, ["--allow", "drafts/**", "--deny", "corpus/heldout"], stdin, project)
    assert res.returncode == 0


def test_unknown_tool_without_paths_passes(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--allow", "drafts/**"], payload("WebSearch", project, query="corpus/heldout"), project)
    assert_allowed(res)


# --------------------------------------------------------------------------- logging

def test_hook_log_records_every_decision(project: Path, tmp_path_factory) -> None:
    log = tmp_path_factory.mktemp("logs") / "hooks.jsonl"
    env = {"POSTSMITH_HOOK_LOG": str(log)}
    run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_heldout", project), project, env)
    run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_train_post", project), project, env)
    run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("bash_tier0", project), project, env)
    run_hook(GUARD_WRITES, ["--allow", "drafts/*/round*/scores/*"], fixture_payload("write_scores", project), project, env)
    run_hook(GUARD_WRITES, ["--allow", "drafts/*/round*/scores/*"], fixture_payload("edit_corpus_post", project), project, env)
    rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [(r["hook"], r["tool"], r["decision"]) for r in rows] == [
        ("guard_paths", "Read", "block"),
        ("guard_paths", "Read", "allow"),
        ("guard_paths", "Bash", "allow"),
        ("guard_writes", "Write", "allow"),
        ("guard_writes", "Edit", "block"),
    ]
    assert rows[0]["targets"] == ["corpus/heldout/acosta_004.md"]
    assert "corpus/heldout" in rows[0]["reason"]
    assert rows[1]["reason"] is None
    assert rows[2]["targets"] == ["tools/tier0.py", "drafts/x"]
    assert rows[3]["targets"] == ["drafts/run_a/round1/scores/r1-w1-li.reader.json"]
    assert all(r["session_id"] for r in rows)
    assert all(r["ts"].endswith("Z") for r in rows)


def test_hook_log_relative_path_resolves_against_project(project: Path) -> None:
    run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_heldout", project), project,
             {"POSTSMITH_HOOK_LOG": "evals/health/hooks.jsonl"})
    rows = (project / "evals" / "health" / "hooks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["decision"] == "block"


def test_no_log_written_without_env(project: Path) -> None:
    before = {p for p in project.rglob("*")}
    run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_heldout", project), project)
    assert {p for p in project.rglob("*")} == before


def test_unwritable_log_never_blocks_or_crashes(project: Path) -> None:
    res = run_hook(GUARD_PATHS, ["--deny", "corpus/heldout"], fixture_payload("read_train_post", project), project,
                   {"POSTSMITH_HOOK_LOG": str(project / "pyproject.toml" / "impossible.jsonl")})
    assert res.returncode == 0
    assert "POSTSMITH_HOOK_LOG" in res.stderr


# --------------------------------------------------------------------------- glob helper semantics (in-process)

def _gp():
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_paths_under_test", GUARD_PATHS)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("pattern,path,expected", [
    ("corpus/heldout", "corpus/heldout", True),
    ("corpus/heldout", "corpus/heldout/x.md", True),
    ("corpus/heldout", "corpus/heldout2/x.md", False),
    ("corpus/heldout", "corpus/posts/x.md", False),
    ("corpus/heldout/", "corpus/heldout/x.md", True),
    ("./corpus/heldout", "corpus/heldout/x.md", True),
    ("corpus/**", "corpus/heldout/x.md", True),
    ("corpus/**", "corpus", True),
    ("corpus/**", "corpusx/y", False),
    ("drafts/*/round*/scores", "drafts/run_a/round1/scores/r1.json", True),
    ("drafts/*/round*/scores", "drafts/run_a/round1/candidates/r1.md", False),
    ("drafts/*/round*/scores/*", "drafts/run_a/round1/scores/r1.json", True),
    ("drafts/*", "drafts/run_a/brief.md", True),
    ("drafts/*/brief*", "drafts/run_a/brief_inputs.json", True),
    ("drafts/*/brief*", "drafts/run_a/round1/brief.md", False),
    ("*.key.json", "drafts/run_a/tier2/lineup.key.json", True),
    ("*.key.json", "lineup.key.json", True),
    ("*.key.json", "drafts/run_a/tier2/lineup.prompt.md", False),
    ("evals", "evals/rubric/v1/rubric.md", True),
    ("evals", "drafts/eval_2026/prompts/x.md", False),
    ("drafts/eval_*/**/prompts/*", "drafts/eval_2026/prompts/x.md", True),
    ("drafts/eval_*/**/prompts/*", "drafts/eval_2026/lineup/prompts/x.md", True),
    ("evals/rubric/v*/**", "evals/rubric/v12/anchors/a.md", True),
    ("**", "", True),
    ("corpus/heldout", "", False),
    ("a/**/b", "a/b", True),
    ("a/**/b", "a/x/y/b/c", True),
    ("a/?", "a/b", True),
    ("a/?", "a/bb", False),
    ("a/[bc].md", "a/c.md", True),
    ("a/[!bc].md", "a/c.md", False),
])
def test_glob_match_semantics(pattern: str, path: str, expected: bool) -> None:
    assert _gp().glob_match(pattern, path) is expected


@pytest.mark.parametrize("pattern,rel_dir,expected", [
    ("corpus/heldout", "", True),
    ("corpus/heldout", "corpus", True),
    ("corpus/heldout", "corpus/posts", False),
    ("drafts/*/round*/scores", "drafts/run_a", True),
    ("drafts/*/round*/scores", "drafts/run_a/round1/candidates", False),
    ("*.key.json", "drafts/run_a/round1/prompts", True),
])
def test_could_match_under(pattern: str, rel_dir: str, expected: bool) -> None:
    assert _gp().could_match_under(pattern, rel_dir) is expected


@pytest.mark.parametrize("command,expected", [
    ("cat corpus/heldout/x.md | head", ["corpus/heldout/x.md"]),
    ("uv run tools/tier0.py drafts/x", ["tools/tier0.py", "drafts/x"]),
    ("echo hi", []),
    ("ls evals", ["evals"]),
    ("cat evals/x 2>/dev/null", ["evals/x", "/dev/null"]),
    ("python3 -c \"open('corpus/heldout/x.md')\"", ["corpus/heldout/x.md"]),
    ("tool --out=drafts/run/x.json", ["drafts/run/x.json"]),
    ("curl https://example.com/a/b", []),
])
def test_bash_path_candidates(command: str, expected: list[str]) -> None:
    assert _gp().bash_path_candidates(command) == expected
