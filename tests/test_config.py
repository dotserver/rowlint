import pandas as pd
import pytest

from rowlint import ConfigError, DataQualityChecker, load_yaml_config
from rowlint.config import DEFAULT_CHECKS, parse_config


@pytest.mark.parametrize("config", [None, {}, {"checks": {}}])
def test_empty_configurations_use_same_defaults(config):
    assert parse_config(config).checks == DEFAULT_CHECKS


def test_selective_checks_flat_compatibility_and_disable_all():
    checker = DataQualityChecker(pd.DataFrame({"id": [1]}))
    assert checker.run_checks({"data_types": True}) == {"data_types": {"id": "int64"}}
    assert checker.run_checks({"checks": dict.fromkeys(DEFAULT_CHECKS, False)}) == {}


@pytest.mark.parametrize(
    "config",
    [
        [],
        {"empty_strings": True},
        {"checks": None},
        {"checks": {"null_values": "false"}},
        {"columns": {"x": {"uniqe": True}}},
        {"columns": {"x": {"nullable": "false"}}},
        {"columns": {"x": {"dtype": "invalid-dtype"}}},
        {"columns": {"x": {"regex": "["}}},
        {"columns": {"x": {"min": 10, "max": 1}}},
        {"columns": {"x": {"max_null_fraction": 2}}},
        {"columns": {"x": {"min": True}}},
        {"columns": {"x": {"max": float("inf")}}},
        {"columns": {"x": {"allowed_values": "HR"}}},
        {"columns": {1: {}}},
        {"unique_keys": [["id", "id"]]},
        {"unique_keys": ["id"]},
        {"cross_column_checks": [{"left": "x", "op": "eval", "right": "y"}]},
        {"cross_column_checks": [{"left": "x", "op": [], "right": "y"}]},
        {"cross_column_checks": [{"left": "x", "op": "eq", "right": ["a", "b"], "operation": []}]},
        {"cross_column_checks": [{"left": "x", "op": "eq", "right": "y", "tolerance": -1}]},
        {"cross_column_checks": [{"left": "x", "op": "eq", "right": ["y"], "operation": "add"}]},
        {"report": {"sample_limit": True}},
        {"report": {"sample_limit": -1}},
        {"report": {"whitespace_as_empty": "false"}},
        {"baseline": {"max_unique_change": -1}},
        {"baseline": {"max_null_increase": 2}},
        {"unique_rows": "false"},
    ],
)
def test_invalid_configuration_rejected(config):
    with pytest.raises(ConfigError):
        parse_config(config)


def test_yaml_empty_duplicate_keys_and_malformed(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    assert load_yaml_config(path) == {}
    path.write_text("checks:\n  null_values: true\n  null_values: false\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Duplicate YAML"):
        load_yaml_config(path)
    path.write_text("checks: [", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_yaml_config(path)


def test_shipped_defaults_match_no_config():
    from importlib.resources import files

    config = load_yaml_config(str(files("rowlint").joinpath("default_config.yaml")))
    assert parse_config(config) == parse_config()
