"""Vectorized profiling and rule evaluation, independent of report rendering."""

import operator
from functools import reduce
from typing import Any

import pandas as pd

from .config import Config
from .report import CheckResult, json_safe


def dataset_metadata(df: pd.DataFrame) -> dict[str, Any]:
    nulls = df.isna().sum()
    unique = df.nunique(dropna=True)
    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": {
            col: {
                "dtype": str(df[col].dtype),
                "null_count": int(nulls[col]),
                "null_fraction": float(nulls[col] / len(df)) if len(df) else 0.0,
                "unique_count": int(unique[col]),
            }
            for col in df.columns
        },
    }


def blank_mask(series: pd.Series, whitespace: bool = True) -> pd.Series:
    """Mixed object columns are supported without converting nonstrings to text."""
    if whitespace:
        try:
            return series.str.strip().eq("").fillna(False).astype(bool)
        except (AttributeError, TypeError):
            return pd.Series(False, index=series.index)
    return series.eq("").fillna(False).astype(bool)


def profile(
    df: pd.DataFrame,
    selected: dict[str, bool],
    *,
    whitespace: bool = True,
    metadata: dict | None = None,
) -> dict[str, Any]:
    stats = metadata or dataset_metadata(df)
    columns = stats["columns"]
    metrics = {}
    if selected.get("null_values"):
        metrics["null_values"] = {col: value["null_count"] for col, value in columns.items()}
    if selected.get("data_types"):
        metrics["data_types"] = {col: value["dtype"] for col, value in columns.items()}
    if selected.get("unique_values"):
        metrics["unique_values"] = {col: value["unique_count"] for col, value in columns.items()}
    if selected.get("constant_columns"):
        metrics["constant_columns"] = [
            col for col, value in columns.items() if value["unique_count"] == 1
        ]
    if selected.get("numeric_outliers"):
        outliers = {}
        for col in df.select_dtypes(include=["number"]):
            series = df[col]
            if pd.api.types.is_complex_dtype(series.dtype):
                continue
            q1, q3 = series.quantile([0.25, 0.75])
            iqr = q3 - q1
            count = int(((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum())
            if count:
                outliers[col] = count
        metrics["numeric_outliers"] = outliers
    if selected.get("empty_or_nan_strings"):
        empty = {}
        for col in df.select_dtypes(include=["object", "string"]):
            count = int((df[col].isna() | blank_mask(df[col], whitespace)).sum())
            if count:
                empty[col] = count
        metrics["empty_or_nan_strings"] = empty
    if selected.get("duplicate_rows"):
        metrics["duplicate_rows"] = int(df.duplicated(keep=False).sum())
    return metrics


def mask_result(
    name: str,
    mask: pd.Series,
    *,
    column: str | None = None,
    evaluated: int | None = None,
    sample_limit: int = 5,
    message: str = "",
) -> CheckResult:
    """Convert a failure mask into counts and a bounded sample of index labels."""
    failures = mask.fillna(False).astype(bool)
    count = int(failures.sum())
    return CheckResult(
        name,
        column,
        "fail" if count else "pass",
        count,
        len(mask) if evaluated is None else evaluated,
        message or f"{count} rows failed",
        json_safe(mask.index[failures.to_numpy()][:sample_limit].tolist()),
    )


def _dtype_matches(series: pd.Series, expected: str) -> bool:
    predicates = {
        "integer": pd.api.types.is_integer_dtype,
        "number": pd.api.types.is_numeric_dtype,
        "boolean": pd.api.types.is_bool_dtype,
        "datetime": pd.api.types.is_datetime64_any_dtype,
    }
    if expected == "string":
        # Inspect values for object columns, rather than accepting arbitrary Python objects.
        return isinstance(series.dtype, pd.StringDtype) or pd.api.types.infer_dtype(
            series.dropna(), skipna=True
        ) in {"string", "unicode"}
    if expected == "number" and pd.api.types.is_bool_dtype(series.dtype):
        return False
    if expected in predicates:
        return predicates[expected](series.dtype)
    return series.dtype == pd.api.types.pandas_dtype(expected)


def evaluate_columns(df: pd.DataFrame, config: Config) -> list[CheckResult]:
    results = []
    for col, rules in config.columns.items():
        if col not in df:
            required = rules.get("required", True)
            results.append(
                CheckResult(
                    "required",
                    col,
                    "fail" if required else "skip",
                    message="Required column is missing"
                    if required
                    else "Optional column is absent",
                )
            )
            continue
        series = df[col]
        null = series.isna()
        present = ~null
        if rules.get("required", True):
            results.append(CheckResult("required", col, message="Column exists"))
        if "dtype" in rules:
            matched = _dtype_matches(series, rules["dtype"])
            results.append(
                CheckResult(
                    "dtype",
                    col,
                    "pass" if matched else "fail",
                    message=f"Expected {rules['dtype']}; found {series.dtype}",
                )
            )
        if rules.get("nullable") is False:
            results.append(
                mask_result("nullable", null, column=col, sample_limit=config.sample_limit)
            )
        if "max_null_fraction" in rules:
            count = int(null.sum())
            fraction = count / len(df) if len(df) else 0.0
            failed = fraction > rules["max_null_fraction"]
            results.append(
                CheckResult(
                    "max_null_fraction",
                    col,
                    "fail" if failed else "pass",
                    count if failed else 0,
                    len(df),
                    f"Missing fraction {fraction:.2%}; maximum {rules['max_null_fraction']:.2%}",
                    json_safe(df.index[null][: config.sample_limit].tolist()) if failed else [],
                )
            )
        if rules.get("unique"):
            results.append(
                mask_result(
                    "unique",
                    present & series.duplicated(keep=False),
                    column=col,
                    evaluated=int(present.sum()),
                    sample_limit=config.sample_limit,
                )
            )
        for rule, comparison in (("min", operator.ge), ("max", operator.le)):
            if rule in rules:
                numeric = (
                    pd.api.types.is_numeric_dtype(series.dtype)
                    and not pd.api.types.is_complex_dtype(series.dtype)
                    and not pd.api.types.is_bool_dtype(series.dtype)
                )
                valid = comparison(series, rules[rule]) if numeric else ~present
                results.append(
                    mask_result(
                        rule,
                        present & ~valid,
                        column=col,
                        evaluated=int(present.sum()),
                        sample_limit=config.sample_limit,
                        message=f"Values must be numeric and {rule}={rules[rule]}",
                    )
                )
        if "allowed_values" in rules:
            results.append(
                mask_result(
                    "allowed_values",
                    present & ~series.isin(rules["allowed_values"]),
                    column=col,
                    evaluated=int(present.sum()),
                    sample_limit=config.sample_limit,
                )
            )
        if "regex" in rules:
            try:
                valid = series.str.fullmatch(rules["regex"], na=False).fillna(False)
            except (AttributeError, TypeError):
                valid = pd.Series(False, index=df.index)
            results.append(
                mask_result(
                    "regex",
                    present & ~valid,
                    column=col,
                    evaluated=int(present.sum()),
                    sample_limit=config.sample_limit,
                )
            )
        if rules.get("non_blank"):
            results.append(
                mask_result(
                    "non_blank",
                    null | blank_mask(series, config.whitespace_as_empty),
                    column=col,
                    sample_limit=config.sample_limit,
                )
            )
    return results


def evaluate_unique_keys(df: pd.DataFrame, config: Config) -> list[CheckResult]:
    results = []
    for cols in config.unique_keys:
        missing = [col for col in cols if col not in df]
        if missing:
            results.append(
                CheckResult(
                    "unique_key",
                    ", ".join(cols),
                    "fail",
                    message=f"Missing key columns: {', '.join(missing)}",
                )
            )
        else:
            # Key rows with any missing component are invalid, even if not duplicated.
            mask = df[cols].isna().any(axis=1) | df.duplicated(subset=cols, keep=False)
            results.append(
                mask_result(
                    "unique_key", mask, column=", ".join(cols), sample_limit=config.sample_limit
                )
            )
    return results


def evaluate_cross_columns(df: pd.DataFrame, config: Config) -> list[CheckResult]:
    comparisons = {
        "eq": operator.eq,
        "ne": operator.ne,
        "lt": operator.lt,
        "le": operator.le,
        "gt": operator.gt,
        "ge": operator.ge,
    }
    arithmetic = {
        "add": operator.add,
        "multiply": operator.mul,
        "subtract": operator.sub,
        "divide": operator.truediv,
    }
    results = []
    for check in config.cross_column_checks:
        right_cols = check["right"] if isinstance(check["right"], list) else [check["right"]]
        cols = [check["left"], *right_cols]
        name = check.get("name", "cross_column")
        missing = [col for col in cols if col not in df]
        if missing:
            results.append(
                CheckResult(name, status="fail", message=f"Missing columns: {', '.join(missing)}")
            )
            continue
        present = df[cols].notna().all(axis=1)
        try:
            right = (
                reduce(arithmetic[check["operation"]], [df[col] for col in right_cols])
                if "operation" in check
                else df[right_cols[0]]
            )
            left = df[check["left"]]
            if "tolerance" in check:
                valid = (left - right).abs() <= check["tolerance"]
                if check["op"] == "ne":
                    valid = ~valid
            else:
                valid = comparisons[check["op"]](left, right)
            mask = present & ~valid.fillna(False)
            result = mask_result(
                name,
                mask,
                evaluated=int(present.sum()),
                sample_limit=config.sample_limit,
                message=f"{check['left']} {check['op']} {check['right']}",
            )
        except (TypeError, ValueError, ArithmeticError) as exc:
            result = CheckResult(name, status="fail", message=f"Incompatible operands: {exc}")
        results.append(result)
    return results
