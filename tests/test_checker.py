import json
import os
from pathlib import Path

import pandas as pd
import pytest

from rowlint.checker import DataQualityChecker


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "name": ["Alice", "Bob", "Charlie", "", None],
            "age": [25, 30, 35, 40, None],
            "gender": ["F", "M", "M", "F", "F"],
            "score": [90, 90, 90, 90, 90],
            "outlier_col": [1, 2, 3, 4, 9999],
        }
    )


@pytest.fixture
def checker(sample_df: pd.DataFrame):
    return DataQualityChecker(sample_df)


def test_null_check(checker: DataQualityChecker):
    checker.check_nulls()
    assert "null_values" in checker.results
    assert "age" in checker.results["null_values"]


def test_data_type_check(checker: DataQualityChecker):
    checker.check_dtypes()
    assert "data_types" in checker.results
    assert isinstance(checker.results["data_types"], dict)


def test_unique_check(checker: DataQualityChecker):
    checker.check_unique()
    assert "unique_values" in checker.results
    assert "id" in checker.results["unique_values"]
    assert checker.results["unique_values"]["id"] == 5


def test_constant_column_check(checker: DataQualityChecker):
    checker.check_constant_columns()
    assert "constant_columns" in checker.results
    assert "score" in checker.results["constant_columns"]


def test_outlier_check(checker: DataQualityChecker):
    checker.check_outliers()
    assert "numeric_outliers" in checker.results
    assert "outlier_col" in checker.results["numeric_outliers"]


def test_empty_string_and_nan_check(checker: DataQualityChecker):
    checker.check_empty_strings_and_nans()
    assert "empty_or_nan_strings" in checker.results
    assert "name" in checker.results["empty_or_nan_strings"]


def test_run_checks_with_config(sample_df: pd.DataFrame):
    config_path = os.path.join(os.path.dirname(__file__), "test_config.yaml")
    config = DataQualityChecker.load_yaml_config(config_path)
    checker = DataQualityChecker(sample_df)
    results = checker.run_checks(config=config)
    assert "data_types" in results
    assert "unique_values" in results
    assert "null_values" not in results


def test_export_json(checker: DataQualityChecker, tmp_path: Path):
    checker.check_nulls()
    json_path = tmp_path / "report.json"
    checker.export_json(str(json_path))
    assert json_path.exists()
    with open(json_path) as f:
        data = json.load(f)
    assert "null_values" in data["metrics"]


def test_export_markdown(checker: DataQualityChecker, tmp_path: Path):
    checker.check_nulls()
    md_path = tmp_path / "report.md"
    checker.export_markdown(str(md_path))
    assert md_path.exists()
    with open(md_path) as f:
        content = f.read()
    assert "# 🧪 Data Quality Report" in content
