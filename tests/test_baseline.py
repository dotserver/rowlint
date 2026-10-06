import pandas as pd
import pytest

from rowlint import DataQualityChecker


def test_baseline_roundtrip_and_changes(tmp_path):
    previous = DataQualityChecker(pd.DataFrame({"id": [1, 2, 3, 4], "removed": [1] * 4})).validate()
    path = tmp_path / "baseline.json"
    previous.write(path)
    checker = DataQualityChecker(pd.DataFrame({"id": [1.0, 1.0, None, None], "new": [1] * 4}))
    report = checker.validate(baseline=path)
    assert not report.passed
    failed = {(result.check, result.column) for result in report.checks if result.status == "fail"}
    assert {
        ("baseline.schema", "new"),
        ("baseline.schema", "removed"),
        ("baseline.dtype", "id"),
        ("baseline.null_fraction", "id"),
        ("baseline.unique_count", "id"),
    } <= failed
    assert all(result.status == "pass" for result in previous.compare_baseline(previous))


def test_baseline_thresholds_and_zero_cardinality():
    previous = DataQualityChecker(pd.DataFrame({"id": [1.0, 2.0, 3.0, 4.0]})).validate()
    current = DataQualityChecker(pd.DataFrame({"id": [1.0, 2.0, 3.0, None]})).validate(
        {
            "baseline": {"max_null_increase": 0.25, "max_unique_change": 0.25},
        },
        baseline=previous,
    )
    assert current.passed
    empty = DataQualityChecker(pd.DataFrame({"id": pd.Series([], dtype="float64")})).validate()
    assert any(result.status == "fail" for result in previous.compare_baseline(empty))


@pytest.mark.parametrize(
    "baseline",
    [
        {},
        {"schema_version": 2},
        {"schema_version": 1, "metadata": {"columns": {}, "row_count": -1}},
        {"schema_version": 1, "metadata": {"columns": {"id": {}}, "row_count": 1}},
    ],
)
def test_invalid_baseline_rejected(baseline):
    report = DataQualityChecker(pd.DataFrame({"id": [1]})).validate()
    with pytest.raises(ValueError, match="Baseline|baseline"):
        report.compare_baseline(baseline)
