"""status.py reads the newest health report. Newest means by time, never by file name."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import status  # noqa: E402


def _reports_dir(root: Path) -> Path:
    reports = root / "evals" / "health" / "reports"
    reports.mkdir(parents=True)
    return reports


def _report(reports: Path, name: str, verdict: str, mtime: float) -> Path:
    f = reports / name
    f.write_text(f"# Health report\n\nstatus: {verdict}\n", encoding="utf-8")
    os.utime(f, (mtime, mtime))
    return f


def test_two_reports_on_one_day_are_ordered_by_time_not_by_hash(tmp_path):
    """Seen 2026-09-28: a red report whose rubric hash sorted later by name outranked the green report written
    after it, so the dashboard stayed red once the defect was fixed."""
    reports = _reports_dir(tmp_path)
    _report(reports, "2026-09-28_3e234dc9919e_p5.md", "red", mtime=1_000_000.0)      # earlier, sorts last by name
    _report(reports, "2026-09-28_1faa4ec2f1ee_p5.md", "green", mtime=1_000_420.0)    # later, sorts first by name
    got = status.health_state(tmp_path, 5)
    assert got["latest_report"].endswith("2026-09-28_1faa4ec2f1ee_p5.md")
    assert got["state"] != "red"


def test_a_later_date_outranks_a_newer_file_from_an_earlier_date(tmp_path):
    """The date in the name is the report's date; a touched old file must not become the latest."""
    reports = _reports_dir(tmp_path)
    _report(reports, "2026-09-20_c09fd733eec3_p3.md", "red", mtime=2_000_000.0)      # old report, touched recently
    _report(reports, "2026-09-28_1faa4ec2f1ee_p5.md", "green", mtime=1_000_000.0)
    got = status.health_state(tmp_path, 5)
    assert got["latest_report"].endswith("2026-09-28_1faa4ec2f1ee_p5.md")


def test_a_red_latest_report_is_still_red(tmp_path):
    reports = _reports_dir(tmp_path)
    _report(reports, "2026-09-28_1faa4ec2f1ee_p5.md", "green", mtime=1_000_000.0)
    _report(reports, "2026-09-28_3e234dc9919e_p5.md", "red", mtime=1_000_420.0)
    assert status.health_state(tmp_path, 5)["state"] == "red"


def test_no_reports_is_none(tmp_path):
    assert status.health_state(tmp_path, 5)["state"] == "none"
