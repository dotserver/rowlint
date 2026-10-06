import json

import pandas as pd
import pytest

from rowlint import CheckResult, ConfigError, DataQualityChecker


def outcome(report, name, column=None):
    return next(
        result
        for result in report.checks
        if result.check == name and (column is None or result.column == column)
    )


def test_column_rules_and_bounded_samples():
    frame = pd.DataFrame(
        {
            "id": [1, 1, 3, 4, 5],
            "age": [-1, 30, 121, None, 40],
            "department": ["HR", "HR", "Finance", "Other", None],
            "code": pd.Series(["AB12", "wrong", "  ", "", None], dtype="string"),
        },
        index=[0, 1, 2, 3, 4],
    )
    report = DataQualityChecker(frame).validate(
        {
            "columns": {
                "id": {"dtype": "integer", "unique": True, "nullable": False},
                "age": {"dtype": "number", "min": 0, "max": 120, "max_null_fraction": 0.1},
                "department": {"allowed_values": ["HR", "Finance"]},
                "code": {"regex": "[A-Z]{2}[0-9]{2}", "non_blank": True},
                "optional": {"required": False},
                "missing": {},
            },
            "report": {"sample_limit": 1},
        }
    )
    assert not report.passed
    assert not report.has_errors
    unique = outcome(report, "unique", "id")
    assert (unique.failed_count, unique.evaluated_count, unique.row_sample) == (2, 5, [0])
    assert unique.failed_fraction == 0.4
    assert outcome(report, "min").failed_count == 1
    assert outcome(report, "max").failed_count == 1
    assert outcome(report, "max_null_fraction").status == "fail"
    assert outcome(report, "allowed_values").failed_count == 1
    assert outcome(report, "regex").failed_count == 3
    assert outcome(report, "non_blank").failed_count == 3
    assert outcome(report, "required", "optional").status == "skip"
    assert outcome(report, "required", "missing").status == "fail"
    assert outcome(report, "dtype", "id").status == "pass"


@pytest.mark.parametrize("dtype", ["object", "string", "string[pyarrow]"])
def test_string_types_and_whitespace(dtype):
    if "pyarrow" in dtype:
        pytest.importorskip("pyarrow")
    frame = pd.DataFrame({"name": pd.Series(["ok", "", " \t", None], dtype=dtype)})
    checker = DataQualityChecker(frame)
    assert checker.run_checks()["empty_or_nan_strings"] == {"name": 3}
    config = {"report": {"whitespace_as_empty": False}, "columns": {"name": {"non_blank": True}}}
    assert checker.validate(config).metrics["empty_or_nan_strings"] == {"name": 2}
    assert outcome(checker.report, "non_blank").failed_count == 2


def test_nullable_types_empty_frames_and_null_semantics():
    frame = pd.DataFrame({"id": pd.Series([1, pd.NA, pd.NA], dtype="Int64")})
    report = DataQualityChecker(frame).validate(
        {
            "columns": {
                "id": {
                    "dtype": "integer",
                    "unique": True,
                    "nullable": False,
                    "min": 0,
                }
            }
        }
    )
    assert outcome(report, "unique").status == "pass"
    assert outcome(report, "nullable").failed_count == 2
    assert outcome(report, "min").evaluated_count == 1
    empty = DataQualityChecker(frame.iloc[:0]).validate({"columns": {"id": {"min": 0}}})
    assert empty.passed
    assert empty.metadata["columns"]["id"]["null_fraction"] == 0
    assert "NaN" not in empty.to_json()


def test_ranges_reject_nonnumeric_values_without_coercing():
    frame = pd.DataFrame({"age": ["25", "bad", None]})
    original = frame.copy(deep=True)
    report = DataQualityChecker(frame).validate({"columns": {"age": {"min": 0}}})
    assert outcome(report, "min").failed_count == 2
    pd.testing.assert_frame_equal(frame, original)


def test_composite_keys_and_duplicate_rows():
    frame = pd.DataFrame({"customer": [1, 1, 2, None], "order": [1, 1, 1, 2]})
    report = DataQualityChecker(frame).validate(
        {"unique_keys": [["customer", "order"]], "unique_rows": True}
    )
    assert report.metrics["duplicate_rows"] == 2
    assert outcome(report, "unique_key").failed_count == 3
    assert outcome(report, "unique_rows").failed_count == 2
    missing = DataQualityChecker(frame).validate({"unique_keys": [["absent"]]})
    assert outcome(missing, "unique_key").status == "fail"


def test_cross_column_comparisons_arithmetic_and_tolerance():
    frame = pd.DataFrame(
        {
            "start": [1, 4, None],
            "end": [2, 3, 5],
            "total": [10.005, 21.0, None],
            "qty": [2, 2, 2],
            "price": [5, 10, 5],
        }
    )
    report = DataQualityChecker(frame).validate(
        {
            "cross_column_checks": [
                {"name": "dates", "left": "start", "op": "le", "right": "end"},
                {
                    "name": "totals",
                    "left": "total",
                    "op": "eq",
                    "right": ["qty", "price"],
                    "operation": "multiply",
                    "tolerance": 0.01,
                },
                {"name": "missing", "left": "absent", "op": "eq", "right": "total"},
            ]
        }
    )
    assert outcome(report, "dates").failed_count == 1
    assert outcome(report, "dates").evaluated_count == 2
    assert outcome(report, "totals").row_sample == [1]
    assert outcome(report, "missing").status == "fail"


def test_custom_validity_masks_and_structured_results():
    frame = pd.DataFrame({"age": [20, 10, 30]}, index=["a", "b", "c"])
    checker = DataQualityChecker(frame)
    checker.register_check("adult", lambda series: series >= 18, column="age")
    checker.register_check("reviewed", lambda df: CheckResult("anything", message="Reviewed"))
    report = checker.validate()
    assert outcome(report, "adult").row_sample == ["b"]
    assert outcome(report, "reviewed").status == "pass"
    with pytest.raises(ValueError, match="already registered"):
        checker.register_check("adult", lambda df: True)


@pytest.mark.parametrize(
    "callback",
    [
        lambda df: True,
        lambda df: pd.Series([True, True], index=["x", "y"]),
        lambda df: pd.Series([1, 1]),
        lambda df: 1 / 0,
        lambda df: CheckResult("too_many", evaluated_count=100),
    ],
)
def test_custom_callback_errors_are_visible(callback):
    checker = DataQualityChecker(pd.DataFrame({"id": [1, 2]}))
    report = checker.register_check("broken", callback).validate()
    assert report.has_errors and not report.passed
    assert outcome(report, "broken").status == "error"


def test_missing_custom_target_and_unknown_mask_values():
    checker = DataQualityChecker(pd.DataFrame({"id": [1, 2]}))
    checker.register_check("nullable", lambda df: pd.Series([True, pd.NA], dtype="boolean"))
    assert outcome(checker.validate(), "nullable").failed_count == 1
    checker.register_check("missing", lambda s: s > 0, column="absent")
    with pytest.raises(ConfigError, match="missing column"):
        checker.validate()


def test_frame_validation_and_repeated_runs():
    with pytest.raises(TypeError, match="DataFrame"):
        DataQualityChecker([1, 2])
    with pytest.raises(ValueError, match="Duplicate column"):
        DataQualityChecker(pd.DataFrame([[1, 2]], columns=["x", "x"]))
    with pytest.raises(ValueError, match="strings"):
        DataQualityChecker(pd.DataFrame({1: [1]}))
    checker = DataQualityChecker(pd.DataFrame({"id": [1]}))
    first = checker.validate({"columns": {"missing": {}}})
    second = checker.validate()
    assert not first.passed and second.passed
    assert not second.checks


def test_index_serialization_and_escaped_reports(tmp_path):
    frame = pd.DataFrame(
        {"<script>alert(1)</script>": [1, 1]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"])
    )
    report = DataQualityChecker(frame).validate({"columns": {frame.columns[0]: {"unique": True}}})
    payload = json.loads(report.to_json())
    assert payload["schema_version"] == 1
    assert payload["checks"][1]["row_sample"][0].startswith("2026-01-01")
    html = report.to_html()
    assert "<script>" not in html and "&lt;script&gt;" in html
    for fmt in ("json", "md", "html", "text"):
        path = tmp_path / f"report.{fmt}"
        report.write(path, fmt)
        assert path.read_text(encoding="utf-8")


def test_polars_adapter():
    pl = pytest.importorskip("polars")
    pytest.importorskip("pyarrow")
    report = DataQualityChecker(pl.DataFrame({"id": [1, 2], "name": ["", None]})).validate()
    assert report.metrics["empty_or_nan_strings"] == {"name": 2}
    assert report.metadata["row_count"] == 2
    nullable = DataQualityChecker(pl.DataFrame({"id": [1, None]})).validate(
        {"columns": {"id": {"dtype": "integer"}}}
    )
    assert nullable.passed
    with pytest.raises(TypeError, match="eager"):
        DataQualityChecker(pl.DataFrame({"id": [1]}).lazy())
