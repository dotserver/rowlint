"""Exercise the documented examples against the checkout, without writing into it."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from rowlint import ConfigError, DataQualityChecker, load_yaml_config

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="requires bash")


@pytest.fixture
def example_runner(tmp_path):
    examples = tmp_path / "examples"
    shutil.copytree(
        EXAMPLES,
        examples,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "report.json", "baseline.json", "orders_*.csv"
        ),
    )
    environment = os.environ.copy()
    # Match subprocesses to pytest's Python and the checkout under test. An
    # unrelated globally installed console command must not influence results.
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["PYTHONIOENCODING"] = "utf-8"

    def run(relative, *args):
        path = examples / relative
        interpreter = "bash" if path.suffix == ".sh" else sys.executable
        return subprocess.run(
            [interpreter, str(path), *args],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )

    return examples, run


@needs_bash
def test_eight_rows_seven_problems(example_runner):
    examples, run = example_runner
    result = run("01_eight_rows_seven_problems/run.sh")
    assert result.returncode == 1, result.stderr
    assert "7 failed" in result.stdout
    assert "FAIL ships_after_order" in result.stdout
    folder = examples / "01_eight_rows_seven_problems"
    report = DataQualityChecker(pd.read_csv(folder / "orders.csv")).validate(
        load_yaml_config(folder / "rules.yaml")
    )
    assert report.metadata["row_count"] == 8
    assert report.summary["failed_checks"] == 7
    failures = {
        (check.check, check.column): (check.failed_count, check.row_sample)
        for check in report.checks
        if check.status == "fail"
    }
    assert failures == {
        ("schema.unexpected_column", "promo_code"): (0, []),
        ("unique", "order_id"): (2, [2, 3]),
        ("nullable", "customer_id"): (1, [4]),
        ("allowed_values", "country"): (1, [5]),
        ("min", "quantity"): (1, [5]),
        ("total_matches_line_items", None): (1, [6]),
        ("ships_after_order", None): (1, [2]),
    }


def test_no_coercion(example_runner):
    _, run = example_runner
    result = run("02_no_coercion/example.py")
    assert result.returncode == 0, result.stderr
    # pandas 2.x and 3.x describe string dtypes differently.
    assert "FAIL dtype [quantity]: Expected integer; found" in result.stdout
    assert "FAIL min [quantity]" in result.stdout
    assert "2 failed" in result.stdout


def test_null_semantics(example_runner):
    _, run = example_runner
    result = run("03_null_semantics/example.py")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("True\n")
    assert "min pass 1" in result.stdout
    assert "max pass 1" in result.stdout
    assert "FAIL max_null_fraction [age]" in result.stdout
    assert "Missing fraction 75.00%" in result.stdout


def test_evidence_not_data(example_runner):
    _, run = example_runner
    result = run("04_evidence_not_data/example.py")
    assert result.returncode == 0, result.stderr
    check = json.loads(result.stdout)
    assert check["status"] == "fail"
    assert check["failed_count"] == 3000
    assert check["evaluated_count"] == 8000
    assert check["row_sample"] == [5000, 5001, 5002, 5003, 5004]
    assert "not-an-email" not in result.stdout and "a@x.com" not in result.stdout


@needs_bash
def test_exit_code_gate_quarantines_invalid_data(example_runner):
    examples, run = example_runner
    result = run("05_exit_code_gate/gate.sh")
    assert result.returncode == 1, result.stderr
    assert result.stdout.startswith("quarantine ")
    report = json.loads((examples / "05_exit_code_gate/report.json").read_text())
    assert not report["passed"] and report["summary"]["failed_checks"] == 7


@needs_bash
def test_exit_code_gate_loads_valid_relative_path_with_spaces(example_runner):
    examples, run = example_runner
    batch = examples.parent / "clean batch.csv"
    batch.write_text(
        "order_id,customer_id,order_date,ship_date,country,quantity,unit_price,total\n"
        "2001,C001,2026-09-01,2026-09-03,GB,2,15.00,30.00\n",
        encoding="utf-8",
    )
    result = run("05_exit_code_gate/gate.sh", batch.name)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"load {batch.name}"
    report = json.loads((examples / "05_exit_code_gate/report.json").read_text())
    assert report["passed"] and report["summary"]["failed_checks"] == 0


@needs_bash
def test_exit_code_gate_distinguishes_input_errors(example_runner):
    examples, run = example_runner
    result = run("05_exit_code_gate/gate.sh", "missing.csv")
    assert result.returncode == 2
    assert "validation could not run" in result.stderr
    assert "load " not in result.stdout and "quarantine " not in result.stdout
    assert not (examples / "05_exit_code_gate/report.json").exists()


@needs_bash
def test_exit_code_gate_rejects_broken_configuration(example_runner):
    _, run = example_runner
    result = run("05_exit_code_gate/check_config.sh")
    assert result.returncode == 2
    assert "ConfigError" in result.stderr and "quantity.min" in result.stderr


@needs_bash
def test_baseline(example_runner):
    examples, run = example_runner
    result = run("06_baseline/run.sh")
    assert result.returncode == 1, result.stderr
    assert "2 failed" in result.stdout
    assert "Missing fraction 0.00% → 12.00%" in result.stdout
    assert "Distinct count 4 → 6" in result.stdout
    folder = examples / "06_baseline"
    baseline = json.loads((folder / "baseline.json").read_text())
    assert baseline["metadata"]["row_count"] == 1000
    assert baseline["summary"]["status"] == "not_run"
    current = pd.read_csv(folder / "orders_2026-09-02.csv")
    assert current["customer_id"].isna().sum() == 120
    assert current["country"].nunique() == 6


@pytest.mark.parametrize(
    "relative",
    ["01_eight_rows_seven_problems/rules.yaml", "06_baseline/baseline_rules.yaml"],
)
def test_example_rules_are_valid(relative):
    load_yaml_config(EXAMPLES / relative)


def test_broken_configuration_is_intentionally_invalid():
    with pytest.raises(ConfigError, match="quantity.min"):
        load_yaml_config(EXAMPLES / "05_exit_code_gate/broken.yaml")
