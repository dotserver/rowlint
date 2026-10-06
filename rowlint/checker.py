"""Public API combining configuration, profiling, validation, and reporting."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from .checks import (
    dataset_metadata,
    evaluate_columns,
    evaluate_cross_columns,
    evaluate_unique_keys,
    mask_result,
    profile,
)
from .config import ConfigError, load_yaml_config, parse_config
from .report import CheckResult, Report


def _to_pandas(df: Any) -> pd.DataFrame:
    if isinstance(df, pd.DataFrame):
        return df
    if type(df).__module__.split(".")[0] == "polars":
        try:
            import polars as pl
        except ImportError as exc:
            raise TypeError("Install rowlint[polars] to use Polars DataFrames") from exc
        if isinstance(df, pl.DataFrame):
            try:
                return df.to_pandas(use_pyarrow_extension_array=True)
            except ImportError as exc:
                raise ImportError("Install rowlint[polars] for the Polars adapter") from exc
    raise TypeError("Expected a pandas DataFrame or an eager Polars DataFrame")


def _validate_frame(df: pd.DataFrame) -> None:
    if not df.columns.is_unique:
        raise ValueError("Duplicate column names are unsupported; rename columns before checking")
    if not all(isinstance(column, str) for column in df.columns):
        raise ValueError("Column names must be strings; rename columns before checking")


class DataQualityChecker:
    """Profile or validate a frame. Built-in checks leave the input unchanged."""

    def __init__(self, df: Any):
        self.df = _to_pandas(df)
        _validate_frame(self.df)
        self.results: dict[str, Any] = {}
        self.report: Report | None = None
        self._custom: dict[str, tuple[Callable, str | None]] = {}

    def _profile_one(self, name: str) -> None:
        _validate_frame(self.df)
        self.results.update(profile(self.df, {name: True}))
        self.report = None

    def check_nulls(self) -> None:
        """Count missing values per column."""
        self._profile_one("null_values")

    def check_dtypes(self) -> None:
        """Describe observed dtypes; use column rules to validate expected dtypes."""
        self._profile_one("data_types")

    def check_unique(self) -> None:
        """Count distinct nonmissing values; this is not a uniqueness constraint."""
        self._profile_one("unique_values")

    def check_constant_columns(self) -> None:
        """Find columns with exactly one distinct nonmissing value."""
        self._profile_one("constant_columns")

    def check_outliers(self) -> None:
        """Count numeric values outside the 1.5 × IQR fences."""
        self._profile_one("numeric_outliers")

    def check_empty_strings_and_nans(self) -> None:
        """Count missing, empty, and whitespace-only values in text/object columns."""
        self._profile_one("empty_or_nan_strings")

    def check_duplicate_rows(self) -> None:
        """Count every row participating in an exact duplicate group."""
        self._profile_one("duplicate_rows")

    def register_check(
        self, name: str, function: Callable, *, column: str | None = None
    ) -> "DataQualityChecker":
        """Register a callback returning a boolean validity Series or CheckResult.

        The callback receives the DataFrame, or the named Series. Missing mask
        values fail. Masks must have exactly the input's index and boolean dtype.
        """
        if not isinstance(name, str) or not name or not callable(function):
            raise ValueError("Custom checks require a nonempty name and callable")
        if name in self._custom:
            raise ValueError(f"Custom check already registered: {name}")
        if column is not None and not isinstance(column, str):
            raise ValueError("Custom check column must be a string or None")
        self._custom[name] = (function, column)
        return self

    def validate(
        self,
        config: Mapping | None = None,
        *,
        baseline: Report | Mapping | str | Path | None = None,
    ) -> Report:
        """Run profiling and validation, returning a fresh structured report."""
        self.results = {}
        self.report = None
        _validate_frame(self.df)
        settings = parse_config(config)
        for name, (_, column) in self._custom.items():
            if column is not None and column not in self.df:
                raise ConfigError(f"Custom check {name} references missing column {column}")
        metadata = dataset_metadata(self.df)
        metrics = profile(
            self.df, settings.checks, whitespace=settings.whitespace_as_empty, metadata=metadata
        )
        outcomes = (
            evaluate_columns(self.df, settings)
            + evaluate_unique_keys(self.df, settings)
            + evaluate_cross_columns(self.df, settings)
        )
        if settings.unique_rows:
            outcomes.append(
                mask_result(
                    "unique_rows",
                    self.df.duplicated(keep=False),
                    sample_limit=settings.sample_limit,
                )
            )
        for name, (function, column) in self._custom.items():
            try:
                value = function(self.df if column is None else self.df[column])
                if isinstance(value, CheckResult):
                    if value.evaluated_count > len(self.df):
                        raise ValueError("Custom evaluated_count exceeds dataset row count")
                    outcome = replace(
                        value,
                        check=name,
                        column=column or value.column,
                        row_sample=value.row_sample[: settings.sample_limit],
                    )
                else:
                    if (
                        not isinstance(value, pd.Series)
                        or not value.index.equals(self.df.index)
                        or not pd.api.types.is_bool_dtype(value.dtype)
                    ):
                        raise ValueError(
                            "Custom check must return an aligned boolean Series or CheckResult"
                        )
                    outcome = mask_result(
                        name,
                        ~value.fillna(False),
                        column=column,
                        sample_limit=settings.sample_limit,
                    )
            except Exception as exc:
                outcome = CheckResult(
                    name,
                    column,
                    "error",
                    message=f"Custom check failed: {type(exc).__name__}: {exc}",
                )
            outcomes.append(outcome)
        report = Report(metrics, outcomes, metadata)
        if baseline is not None:
            report.checks.extend(
                report.compare_baseline(
                    baseline,
                    max_null_increase=settings.max_null_increase,
                    max_unique_change=settings.max_unique_change,
                )
            )
        self.results = metrics
        self.report = report
        return report

    def run_checks(self, config: Mapping | None = None) -> dict[str, Any]:
        """Return profiling metrics; rule outcomes are available on checker.report."""
        return self.validate(config).metrics

    def _current_report(self) -> Report:
        return (
            self.report
            if self.report is not None
            else Report(self.results.copy(), metadata=dataset_metadata(self.df))
        )

    def export_json(self, path: str | Path) -> None:
        """Export schema-versioned metrics, metadata, and rule outcomes."""
        self._current_report().write(path, "json")

    def export_markdown(self, path: str | Path) -> None:
        self._current_report().write(path, "md")

    def export_html(self, path: str | Path) -> None:
        self._current_report().write(path, "html")

    load_yaml_config = staticmethod(load_yaml_config)
