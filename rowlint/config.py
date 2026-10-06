"""Strict configuration loading, without executing code from configuration files."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

DEFAULT_CHECKS = dict.fromkeys(
    (
        "null_values",
        "data_types",
        "unique_values",
        "constant_columns",
        "numeric_outliers",
        "empty_or_nan_strings",
        "duplicate_rows",
    ),
    True,
)
LOGICAL_DTYPES = {"integer", "number", "string", "boolean", "datetime"}


class ConfigError(ValueError):
    """A configuration contains an unsupported key or value."""


def _mapping(value: Any, context: str) -> dict:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{context} keys must be strings")
    return dict(value)


def _keys(value: dict, allowed: set, context: str) -> None:
    unknown = value.keys() - allowed
    if unknown:
        raise ConfigError(f"Unknown {context} keys: {', '.join(sorted(unknown))}")


def _bool(value: Any, context: str) -> None:
    if type(value) is not bool:
        raise ConfigError(f"{context} must be true or false, not {value!r}")


def _number(value: Any, context: str, fraction: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ConfigError(f"{context} must be a finite number")
    if fraction and not 0 <= value <= 1:
        raise ConfigError(f"{context} must be between 0 and 1")


@dataclass(frozen=True)
class Config:
    checks: dict[str, bool] = field(default_factory=lambda: DEFAULT_CHECKS.copy())
    columns: dict[str, dict[str, Any]] = field(default_factory=dict)
    unique_keys: list[list[str]] = field(default_factory=list)
    cross_column_checks: list[dict[str, Any]] = field(default_factory=list)
    sample_limit: int = 5
    whitespace_as_empty: bool = True
    max_null_increase: float = 0.05
    max_unique_change: float = 0.2
    unique_rows: bool = False


def parse_config(raw: Mapping | None = None) -> Config:
    """Empty configurations use defaults; a nonempty checks mapping selects checks."""
    if raw is None:
        return Config()
    data = _mapping(raw, "configuration")
    # Preserve the original flat profiling configuration format.
    if data and data.keys() <= DEFAULT_CHECKS.keys():
        data = {"checks": data}
    _keys(
        data,
        {
            "checks",
            "columns",
            "unique_keys",
            "cross_column_checks",
            "report",
            "baseline",
            "unique_rows",
        },
        "configuration",
    )
    checks = _mapping(data.get("checks", {}), "checks")
    _keys(checks, set(DEFAULT_CHECKS), "checks")
    for key, value in checks.items():
        _bool(value, f"checks.{key}")
    checks = (
        {name: checks.get(name, False) for name in DEFAULT_CHECKS}
        if checks
        else DEFAULT_CHECKS.copy()
    )

    columns = _mapping(data.get("columns", {}), "columns")
    for column, raw_rules in columns.items():
        rules = _mapping(raw_rules, f"columns.{column}")
        _keys(
            rules,
            {
                "required",
                "dtype",
                "nullable",
                "unique",
                "min",
                "max",
                "max_null_fraction",
                "allowed_values",
                "regex",
                "non_blank",
            },
            f"columns.{column}",
        )
        for name in ("required", "nullable", "unique", "non_blank"):
            if name in rules:
                _bool(rules[name], f"{column}.{name}")
        for name in ("min", "max", "max_null_fraction"):
            if name in rules:
                _number(rules[name], f"{column}.{name}", name == "max_null_fraction")
        if "min" in rules and "max" in rules and rules["min"] > rules["max"]:
            raise ConfigError(f"{column}.min cannot exceed max")
        if "allowed_values" in rules and not isinstance(rules["allowed_values"], list):
            raise ConfigError(f"{column}.allowed_values must be a list")
        if "regex" in rules:
            if not isinstance(rules["regex"], str):
                raise ConfigError(f"{column}.regex must be a string")
            try:
                re.compile(rules["regex"])
            except re.error as exc:
                raise ConfigError(f"Invalid regex for {column}: {exc}") from exc
        if "dtype" in rules:
            dtype = rules["dtype"]
            if not isinstance(dtype, str):
                raise ConfigError(f"{column}.dtype must be a string")
            if dtype not in LOGICAL_DTYPES:
                try:
                    pd.api.types.pandas_dtype(dtype)
                except (TypeError, ValueError) as exc:
                    raise ConfigError(f"Invalid dtype for {column}: {dtype}") from exc
        columns[column] = rules

    unique_keys = data.get("unique_keys", [])
    if not isinstance(unique_keys, list):
        raise ConfigError("unique_keys must be a list of column lists")
    for key in unique_keys:
        if (
            not isinstance(key, list)
            or not key
            or not all(isinstance(col, str) for col in key)
            or len(set(key)) != len(key)
        ):
            raise ConfigError("Each unique key must be a nonempty list of distinct column names")

    cross_checks = data.get("cross_column_checks", [])
    if not isinstance(cross_checks, list):
        raise ConfigError("cross_column_checks must be a list")
    normalized = []
    for raw_check in cross_checks:
        check = _mapping(raw_check, "cross_column_check")
        _keys(
            check, {"name", "left", "op", "right", "operation", "tolerance"}, "cross_column_check"
        )
        if not isinstance(check.get("left"), str):
            raise ConfigError("A cross-column check requires a left column name")
        if not isinstance(check.get("op"), str) or check["op"] not in {
            "eq",
            "ne",
            "lt",
            "le",
            "gt",
            "ge",
        }:
            raise ConfigError("Cross-column op must be eq, ne, lt, le, gt, or ge")
        if "name" in check and (not isinstance(check["name"], str) or not check["name"]):
            raise ConfigError("Cross-column name must be a nonempty string")
        right = check.get("right")
        if "operation" in check:
            if not isinstance(check["operation"], str) or check["operation"] not in {
                "add",
                "multiply",
                "subtract",
                "divide",
            }:
                raise ConfigError("operation must be add, multiply, subtract, or divide")
            if (
                not isinstance(right, list)
                or len(right) < 2
                or not all(isinstance(col, str) for col in right)
            ):
                raise ConfigError("Arithmetic right operand must contain at least two columns")
            if check["operation"] in {"subtract", "divide"} and len(right) != 2:
                raise ConfigError("subtract and divide require exactly two right columns")
        elif not isinstance(right, str):
            raise ConfigError("right must be a column name when no operation is supplied")
        if "tolerance" in check:
            _number(check["tolerance"], "tolerance")
            if check["tolerance"] < 0 or check["op"] not in {"eq", "ne"}:
                raise ConfigError("A nonnegative tolerance is only supported for eq/ne")
        normalized.append(check)

    report = _mapping(data.get("report", {}), "report")
    _keys(report, {"sample_limit", "whitespace_as_empty"}, "report")
    sample_limit = report.get("sample_limit", 5)
    if type(sample_limit) is not int or not 0 <= sample_limit <= 1000:
        raise ConfigError("report.sample_limit must be an integer between 0 and 1000")
    whitespace = report.get("whitespace_as_empty", True)
    _bool(whitespace, "report.whitespace_as_empty")
    baseline = _mapping(data.get("baseline", {}), "baseline")
    _keys(baseline, {"max_null_increase", "max_unique_change"}, "baseline")
    null_change = baseline.get("max_null_increase", 0.05)
    unique_change = baseline.get("max_unique_change", 0.2)
    _number(null_change, "baseline.max_null_increase", True)
    _number(unique_change, "baseline.max_unique_change")
    if unique_change < 0:
        raise ConfigError("baseline.max_unique_change cannot be negative")
    unique_rows = data.get("unique_rows", False)
    _bool(unique_rows, "unique_rows")
    return Config(
        checks,
        columns,
        unique_keys,
        normalized,
        sample_limit,
        whitespace,
        null_change,
        unique_change,
        unique_rows,
    )


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject accidental duplicate YAML keys instead of silently overriding rules."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ConfigError("YAML mapping keys must be strings")
        if key in result:
            raise ConfigError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_yaml_config(path: str | Path) -> dict:
    """Read and validate a YAML configuration; an empty file uses defaults."""
    with Path(path).open(encoding="utf-8") as stream:
        try:
            raw = yaml.load(stream, Loader=_UniqueKeyLoader)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML: {exc}") from exc
    data = {} if raw is None else _mapping(raw, "configuration")
    parse_config(data)
    return data
