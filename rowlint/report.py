"""Serializable check results and dependency-free report renderers."""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from html import escape
from math import isfinite
from pathlib import Path
from typing import Any, Literal

import pandas as pd


def json_safe(value: Any) -> Any:
    """Normalize pandas scalars and index labels to strict JSON values."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return json_safe(value.item())
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@dataclass(frozen=True)
class CheckResult:
    """One rule outcome. Samples contain index labels, never entire data rows."""

    check: str
    column: str | None = None
    status: Literal["pass", "fail", "skip", "error"] = "pass"
    failed_count: int = 0
    evaluated_count: int = 0
    message: str = ""
    row_sample: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.check, str) or not self.check:
            raise ValueError("CheckResult.check must be a nonempty string")
        if self.column is not None and not isinstance(self.column, str):
            raise ValueError("CheckResult.column must be a column name or None")
        if self.status not in {"pass", "fail", "skip", "error"}:
            raise ValueError("CheckResult.status must be pass, fail, skip, or error")
        if (
            type(self.failed_count) is not int
            or type(self.evaluated_count) is not int
            or not 0 <= self.failed_count <= self.evaluated_count
        ):
            raise ValueError("CheckResult counts must satisfy 0 <= failed <= evaluated")
        if self.failed_count and self.status != "fail":
            raise ValueError("A result with failed rows must have status='fail'")
        if not isinstance(self.message, str) or not isinstance(self.row_sample, list):
            raise ValueError("CheckResult requires a string message and list row_sample")

    @property
    def failed_fraction(self) -> float:
        return self.failed_count / self.evaluated_count if self.evaluated_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        return json_safe({**asdict(self), "failed_fraction": self.failed_fraction})


@dataclass
class Report:
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(result.status in {"pass", "skip"} for result in self.checks)

    @property
    def has_errors(self) -> bool:
        return any(result.status == "error" for result in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "schema_version": 1,
                "passed": self.passed,
                "metadata": self.metadata,
                "metrics": self.metrics,
                "checks": [result.to_dict() for result in self.checks],
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    def to_terminal(self) -> str:
        failures = sum(result.status == "fail" for result in self.checks)
        errors = sum(result.status == "error" for result in self.checks)
        lines = [
            f"Data quality: {'PASS' if self.passed else 'FAIL'} "
            f"({len(self.checks)} rules, {failures} failures, {errors} errors)",
            f"Rows: {self.metadata.get('row_count', '?')}; "
            f"columns: {self.metadata.get('column_count', '?')}",
        ]
        for result in self.checks:
            column = f" [{result.column}]" if result.column else ""
            lines.append(f"{result.status.upper()} {result.check}{column}: {result.message}")
            if result.row_sample:
                lines.append(f"  Row indices: {json_safe(result.row_sample)}")
        lines.append("Profile: " + json.dumps(json_safe(self.metrics), ensure_ascii=False))
        return "\n".join(lines) + "\n"

    def to_markdown(self) -> str:
        def cell(value: Any) -> str:
            return escape(str(value)).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

        lines = [
            "# 🧪 Data Quality Report",
            "",
            f"**Status: {'PASS' if self.passed else 'FAIL'}**",
            "",
            f"Rows: {self.metadata.get('row_count', '?')} · "
            f"Columns: {self.metadata.get('column_count', '?')}",
            "",
            "| Check | Column | Status | Failed / evaluated | Message | Row indices |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for result in self.checks:
            values = (
                result.check,
                result.column or "—",
                result.status,
                f"{result.failed_count}/{result.evaluated_count}",
                result.message,
                json.dumps(json_safe(result.row_sample), ensure_ascii=False),
            )
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
        for name, metric in self.metrics.items():
            lines.extend(
                [
                    "",
                    f"## {name.replace('_', ' ').title()}",
                    "",
                    "    " + json.dumps(json_safe(metric), ensure_ascii=False),
                ]
            )
        return "\n".join(lines) + "\n"

    def to_html(self) -> str:
        rows = []
        for result in self.checks:
            values = (
                result.check,
                result.column or "—",
                result.status,
                f"{result.failed_count}/{result.evaluated_count}",
                result.message,
                json.dumps(json_safe(result.row_sample), ensure_ascii=False),
            )
            rows.append(
                "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in values) + "</tr>"
            )
        metrics = "".join(
            f"<h2>{escape(name.replace('_', ' ').title())}</h2>"
            f"<pre>{escape(json.dumps(json_safe(value), indent=2))}</pre>"
            for name, value in self.metrics.items()
        )
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>Data Quality Report</title><style>"
            "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:1rem}"
            "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;"
            "padding:.6rem;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            ".table{overflow:auto}</style></head><body><h1>Data Quality Report</h1>"
            f"<p><strong>Status: {'PASS' if self.passed else 'FAIL'}</strong></p>"
            f"<p>Rows: {escape(str(self.metadata.get('row_count', '?')))} · "
            f"Columns: {escape(str(self.metadata.get('column_count', '?')))}</p>"
            '<div class="table"><table><thead><tr><th>Check</th><th>Column</th><th>Status</th>'
            "<th>Failed / evaluated</th><th>Message</th><th>Row indices</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>{metrics}</body></html>\n"
        )

    def write(self, path: str | Path, format: str = "json") -> None:
        renderers = {
            "json": self.to_json,
            "md": self.to_markdown,
            "html": self.to_html,
            "text": self.to_terminal,
        }
        if format not in renderers:
            raise ValueError(f"Unsupported report format: {format}")
        Path(path).write_text(renderers[format](), encoding="utf-8")

    def compare_baseline(
        self,
        baseline: "Report | Mapping[str, Any] | str | Path",
        *,
        max_null_increase: float = 0.05,
        max_unique_change: float = 0.2,
    ) -> list[CheckResult]:
        """Compare schema, null fractions and relative distinct counts to a saved report."""
        from .baseline import compare_baseline

        return compare_baseline(self, baseline, max_null_increase, max_unique_change)
