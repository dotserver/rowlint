"""Compare reports without storing raw dataset values."""

import json
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .report import CheckResult

if TYPE_CHECKING:
    from .report import Report


def _metadata(report: "Report | Mapping[str, Any] | str | Path") -> dict:
    from .report import Report

    if isinstance(report, (str, Path)):
        try:
            report = json.loads(Path(report).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid baseline JSON: {exc}") from exc
    data = report.to_dict() if isinstance(report, Report) else report
    if not isinstance(data, Mapping) or data.get("schema_version") != 1:
        raise ValueError("Baseline must be a rowlint report with schema_version=1")
    metadata = data.get("metadata")
    if not isinstance(metadata, Mapping) or not isinstance(metadata.get("columns"), Mapping):
        raise ValueError("Baseline is missing column metadata")
    rows = metadata.get("row_count")
    if type(rows) is not int or rows < 0:
        raise ValueError("Baseline row_count must be a nonnegative integer")
    for column, stats in metadata["columns"].items():
        if not isinstance(column, str) or not isinstance(stats, Mapping):
            raise ValueError("Invalid baseline column metadata")
        fraction = stats.get("null_fraction")
        distinct = stats.get("unique_count")
        if (
            not isinstance(stats.get("dtype"), str)
            or isinstance(fraction, bool)
            or not isinstance(fraction, (int, float))
            or not isfinite(fraction)
            or not 0 <= fraction <= 1
            or type(distinct) is not int
            or not 0 <= distinct <= rows
        ):
            raise ValueError(f"Invalid baseline statistics for {column}")
    return dict(metadata)


def compare_baseline(
    current: "Report",
    baseline: "Report | Mapping[str, Any] | str | Path",
    max_null_increase: float,
    max_unique_change: float,
) -> list[CheckResult]:
    for value, name in (
        (max_null_increase, "max_null_increase"),
        (max_unique_change, "max_unique_change"),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{name} must be a nonnegative finite number")
    if max_null_increase > 1:
        raise ValueError("max_null_increase cannot exceed 1")
    previous = _metadata(baseline)["columns"]
    columns = _metadata(current)["columns"]
    results = []
    for column in sorted(previous.keys() | columns.keys()):
        if column not in previous or column not in columns:
            results.append(
                CheckResult(
                    "baseline.schema",
                    column,
                    "fail",
                    message="Column added" if column in columns else "Column removed",
                )
            )
            continue
        before, after = previous[column], columns[column]
        results.append(
            CheckResult(
                "baseline.dtype",
                column,
                "pass" if before["dtype"] == after["dtype"] else "fail",
                message=f"{before['dtype']} → {after['dtype']}",
            )
        )
        increase = after["null_fraction"] - before["null_fraction"]
        results.append(
            CheckResult(
                "baseline.null_fraction",
                column,
                "fail" if increase > max_null_increase + 1e-12 else "pass",
                message=f"Missing fraction {before['null_fraction']:.2%} → "
                f"{after['null_fraction']:.2%}; allowed increase "
                f"{max_null_increase:.2%}",
            )
        )
        old_count, new_count = before["unique_count"], after["unique_count"]
        changed = (
            abs(new_count - old_count) / old_count
            if old_count
            else (0.0 if new_count == 0 else float("inf"))
        )
        results.append(
            CheckResult(
                "baseline.unique_count",
                column,
                "fail" if changed > max_unique_change + 1e-12 else "pass",
                message=f"Distinct count {old_count} → {new_count}; "
                f"allowed relative change {max_unique_change:.2%}",
            )
        )
    return results
