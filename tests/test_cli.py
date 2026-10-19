import json
import subprocess
import sys

import pandas as pd
import pytest

from rowlint.cli import main


def test_cli_json_success_and_leading_zero_dtype(tmp_path, capsys):
    path = tmp_path / "input.csv"
    path.write_text("id;age\n001;20\n002;30\n", encoding="utf-8")
    assert main([str(path), "--sep", ";", "--dtype", "id=string", "--format", "json"]) == 0
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["passed"] and payload["metrics"]["data_types"]["id"] == "string"
    assert output.err == ""


def test_cli_failure_report_and_exit_code(tmp_path, capsys):
    path = tmp_path / "input.csv"
    path.write_text("id\n1\n1\n", encoding="utf-8")
    config = tmp_path / "rules.yaml"
    config.write_text("columns:\n  id: {unique: true}\n", encoding="utf-8")
    output = tmp_path / "report.html"
    assert (
        main([str(path), "--config", str(config), "--output", str(output), "--format", "html"]) == 1
    )
    assert "Status: FAIL" in output.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""
    result = subprocess.run(
        [sys.executable, "-m", "rowlint", str(path), "--config", str(config)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1 and "FAIL" in result.stdout


def test_cli_io_and_configuration_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv")]) == 2
    output = capsys.readouterr()
    assert not output.out and "FileNotFoundError" in output.err
    path = tmp_path / "input.csv"
    path.write_text("id\n1\n", encoding="utf-8")
    assert main([str(path), "--output", str(tmp_path / "missing" / "report.json")]) == 2
    assert "FileNotFoundError" in capsys.readouterr().err
    config = tmp_path / "bad.yaml"
    config.write_text("checks: {null_values: 'false'}", encoding="utf-8")
    assert main([str(path), "--config", str(config)]) == 2
    assert "ConfigError" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args", [[], ["a.csv", "--input", "b.csv"], ["a.csv", "--force"], ["--init-config", "a.csv"]]
)
def test_cli_argument_errors(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_config_template_overwrite_protection(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["--init-config"]) == 0
    path = tmp_path / "rowlint_config.yaml"
    path.write_text("# existing", encoding="utf-8")
    assert main(["--init-config"]) == 2
    assert path.read_text() == "# existing"
    assert main(["--init-config", "--force"]) == 0
    assert "columns:" in path.read_text()
    capsys.readouterr()


def test_cli_parquet_and_baseline(tmp_path, capsys):
    pytest.importorskip("pyarrow")
    path = tmp_path / "input.parquet"
    pd.DataFrame({"id": [1, 2]}).to_parquet(path)
    baseline = tmp_path / "baseline.json"
    assert main([str(path), "--format", "json", "--output", str(baseline)]) == 0
    assert main([str(path), "--baseline", str(baseline), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"]


def test_cli_header_only_csv_fails_minimum_size_rule(tmp_path, capsys):
    path = tmp_path / "empty.csv"
    path.write_text("id\n", encoding="utf-8")
    config = tmp_path / "rules.yaml"
    config.write_text("dataset: {min_rows: 1}\n", encoding="utf-8")
    assert main([str(path), "--config", str(config), "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["metadata"]["row_count"] == 0
    assert payload["summary"]["failed_checks"] == 1
    assert payload["checks"][0]["check"] == "dataset.min_rows"


def test_cli_strict_schema_and_concise_stdout_and_file(tmp_path, capsys):
    path = tmp_path / "input.csv"
    path.write_text("id,unexpected\n1,10\n", encoding="utf-8")
    config = tmp_path / "rules.yaml"
    config.write_text("schema: {allow_extra_columns: false}\ncolumns: {id: {}}\n", encoding="utf-8")
    args = [str(path), "--config", str(config), "--concise"]
    assert main(args) == 1
    terminal = capsys.readouterr().out
    assert "Status: FAIL" in terminal and "1 failed" in terminal
    assert "schema.unexpected_column [unexpected]" in terminal
    assert "Profile:" not in terminal and "PASS required" not in terminal
    report = tmp_path / "report.txt"
    assert main([*args, "--output", str(report)]) == 1
    assert capsys.readouterr().out == ""
    assert report.read_text() == terminal


@pytest.mark.parametrize("extra", [["--format", "json"], ["--format", "html"], ["--init-config"]])
def test_concise_rejects_options_that_would_ignore_it(extra):
    with pytest.raises(SystemExit) as exc:
        main(["--concise", *extra])
    assert exc.value.code == 2


def test_cli_concise_profile_remains_successful(tmp_path, capsys):
    path = tmp_path / "input.csv"
    path.write_text("id\n1\n", encoding="utf-8")
    assert main([str(path), "--concise"]) == 0
    assert "PROFILING ONLY" in capsys.readouterr().out


def test_check_config_validates_rules_without_loading_data(tmp_path, capsys, monkeypatch):
    config = tmp_path / "rules.yaml"
    config.write_text(
        "dataset: {min_rows: 1}\nschema: {allow_extra_columns: false}\ncolumns: {id: {}}\n",
        encoding="utf-8",
    )

    def unexpected_read(*args, **kwargs):
        pytest.fail("Configuration validation must not load a dataset")

    monkeypatch.setattr(pd, "read_csv", unexpected_read)
    monkeypatch.setattr(pd, "read_parquet", unexpected_read)
    assert main(["--check-config", str(config)]) == 0
    output = capsys.readouterr()
    assert "Configuration valid:" in output.out and not output.err


@pytest.mark.parametrize(
    "content", ["dataset: {min_rows: -1}", "columns: [", "schema: {strict: true}"]
)
def test_check_config_invalid_yaml_or_rules_exit_two(tmp_path, capsys, content):
    config = tmp_path / "rules.yaml"
    config.write_text(content, encoding="utf-8")
    assert main(["--check-config", str(config)]) == 2
    output = capsys.readouterr()
    assert "ConfigError" in output.err and not output.out


def test_check_config_missing_file_exit_two(tmp_path, capsys):
    assert main(["--check-config", str(tmp_path / "missing.yaml")]) == 2
    output = capsys.readouterr()
    assert "FileNotFoundError" in output.err and not output.out


@pytest.mark.parametrize(
    "options",
    [
        ["input.csv"],
        ["--input", "input.csv"],
        ["--config", "other.yaml"],
        ["--init-config"],
        ["--force"],
        ["--output", "report.txt"],
        ["--concise"],
        ["--format", "json"],
        ["--baseline", "baseline.json"],
        ["--dtype", "id=string"],
        ["--input-format", "parquet"],
        ["--sep", ";"],
        ["--encoding", "ascii"],
    ],
)
def test_check_config_rejects_conflicting_modes(options):
    with pytest.raises(SystemExit) as exc:
        main(["--check-config", "rules.yaml", *options])
    assert exc.value.code == 2
