import json

import pandas as pd
import pytest

from rowlint import CheckResult, DataQualityChecker, Report


def test_profiling_only_is_explicit_in_all_report_formats():
    report = DataQualityChecker(pd.DataFrame({"id": [None, None]})).validate()
    assert report.passed  # Keep the original success/exit-code contract.
    assert report.summary["mode"] == "profiling"
    assert report.summary["status"] == "not_run"
    assert report.summary["total_checks"] == 0
    assert json.loads(report.to_json())["summary"] == report.summary
    for render in (report.to_terminal, report.to_markdown, report.to_html):
        assert "PROFILING ONLY (validation not run)" in render()
        assert "Status: PASS" not in render()


def test_mixed_rule_summary_counts_checks_and_prioritizes_errors():
    report = Report(
        checks=[
            CheckResult("ok"),
            CheckResult("missing_optional", status="skip"),
            CheckResult("duplicate", status="fail", failed_count=2, evaluated_count=2),
            CheckResult("wrong_range", status="fail", failed_count=2, evaluated_count=2),
            CheckResult("broken_callback", status="error", message="Unavailable"),
        ],
        metadata={"row_count": 2, "column_count": 1},
    )
    assert report.summary == {
        "mode": "validation",
        "status": "error",
        "total_checks": 5,
        "passed_checks": 1,
        "failed_checks": 2,
        "skipped_checks": 1,
        "error_checks": 1,
    }
    concise = report.to_terminal(concise=True)
    assert "Status: ERROR" in concise
    assert "2 failed; 1 errors; 1 skipped" in concise
    assert "FAIL duplicate" in concise and "ERROR broken_callback" in concise
    assert "PASS ok" not in concise and "SKIP missing_optional" not in concise
    assert "Profile:" not in concise
    assert "Profile:" in report.to_terminal()


@pytest.mark.parametrize("status,label", [("pass", "PASS"), ("fail", "FAIL"), ("skip", "SKIPPED")])
def test_validation_statuses_are_distinct_from_profiling(status, label):
    report = Report(checks=[CheckResult("rule", status=status)])
    assert report.summary["mode"] == "validation"
    for render in (report.to_terminal, report.to_markdown, report.to_html):
        assert f"Status: {label}" in render()


def test_concise_file_matches_terminal_output_and_preserves_samples(tmp_path):
    report = DataQualityChecker(pd.DataFrame({"id": [1, 1]})).validate(
        {"columns": {"id": {"unique": True}}}
    )
    path = tmp_path / "report.txt"
    report.write(path, "text", concise=True)
    assert path.read_text() == report.to_terminal(concise=True)
    assert "Row indices: [0, 1]" in path.read_text()
    with pytest.raises(ValueError, match="only for text"):
        report.write(path, "json", concise=True)


def test_old_baseline_without_summary_still_loads():
    report = DataQualityChecker(pd.DataFrame({"id": [1]})).validate()
    baseline = report.to_dict()
    baseline.pop("summary")
    assert all(check.status == "pass" for check in report.compare_baseline(baseline))
