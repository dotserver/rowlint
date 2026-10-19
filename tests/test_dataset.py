import pandas as pd
import pytest

from rowlint import DataQualityChecker


@pytest.mark.parametrize(
    "rows,limits,failures",
    [
        (0, {"min_rows": 1}, {"dataset.min_rows"}),
        (0, {"min_rows": 0, "max_rows": 0}, set()),
        (2, {"min_rows": 2, "max_rows": 2}, set()),
        (1, {"min_rows": 2}, {"dataset.min_rows"}),
        (3, {"max_rows": 2}, {"dataset.max_rows"}),
    ],
)
def test_dataset_limits_are_inclusive_metadata_checks(rows, limits, failures):
    frame = pd.DataFrame({"id": range(rows)})
    report = DataQualityChecker(frame).validate({"dataset": limits})
    assert {check.check for check in report.checks if check.status == "fail"} == failures
    assert report.passed == (not failures)
    assert all(check.evaluated_count == check.failed_count == 0 for check in report.checks)
    assert all(check.row_sample == [] for check in report.checks)
    assert all(f"found {rows}" in check.message for check in report.checks)


def test_size_rules_run_with_profiling_disabled():
    report = DataQualityChecker(pd.DataFrame({"id": []})).validate(
        {"checks": {"null_values": False}, "dataset": {"min_rows": 1}}
    )
    assert not report.metrics
    assert not report.passed
    assert report.summary["failed_checks"] == 1


def test_strict_schema_rejects_every_unexpected_column_without_row_samples():
    frame = pd.DataFrame({"id": [1], "extra": [2], "another": [3]})
    original = frame.copy(deep=True)
    report = DataQualityChecker(frame).validate(
        {"schema": {"allow_extra_columns": False}, "columns": {"id": {}}}
    )
    unexpected = [check for check in report.checks if check.check == "schema.unexpected_column"]
    assert {check.column for check in unexpected} == {"extra", "another"}
    assert all(check.status == "fail" and not check.row_sample for check in unexpected)
    assert not report.passed
    pd.testing.assert_frame_equal(frame, original)


def test_strict_schema_allows_optional_columns_and_ignores_column_order():
    config = {
        "schema": {"allow_extra_columns": False},
        "columns": {"id": {}, "note": {"required": False}},
    }
    for frame in (pd.DataFrame({"id": [1]}), pd.DataFrame({"note": ["ok"], "id": [1]})):
        report = DataQualityChecker(frame).validate(config)
        assert report.passed
        assert any(check.check == "schema.extra_columns" for check in report.checks)
    missing = DataQualityChecker(pd.DataFrame({"note": ["ok"]})).validate(config)
    assert any(check.check == "required" and check.status == "fail" for check in missing.checks)


def test_strict_schema_with_no_declared_columns_and_empty_frames():
    config = {"schema": {"allow_extra_columns": False}}
    assert DataQualityChecker(pd.DataFrame()).validate(config).passed
    report = DataQualityChecker(pd.DataFrame({"id": []})).validate(config)
    assert not report.passed
    assert report.checks[0].column == "id"


@pytest.mark.parametrize("schema", [{}, {"allow_extra_columns": True}])
def test_extra_columns_remain_allowed_by_default(schema):
    report = DataQualityChecker(pd.DataFrame({"id": [1], "extra": [2]})).validate(
        {"schema": schema, "columns": {"id": {}}}
    )
    assert report.passed
    assert all(not check.check.startswith("schema.") for check in report.checks)
