"""Install each distribution in a fresh environment and test outside the checkout."""

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def smoke(artifact: Path, extras: str | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="rowlint-install-") as directory:
        root = Path(directory)
        env = root / "venv"
        venv.EnvBuilder(with_pip=True).create(env)
        bin_dir = env / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        command = bin_dir / ("rowlint.exe" if os.name == "nt" else "rowlint")
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        environment["PIP_NO_CACHE_DIR"] = "1"
        requirement = str(artifact.resolve()) + (f"[{extras}]" if extras else "")
        subprocess.run(
            [str(python), "-m", "pip", "install", requirement],
            cwd=root,
            env=environment,
            check=True,
        )
        subprocess.run([str(python), "-m", "pip", "check"], cwd=root, env=environment, check=True)
        subprocess.run(
            [
                str(python),
                "-c",
                "from importlib.metadata import distribution; "
                "from importlib.resources import files; "
                "from importlib.util import find_spec; "
                "import rowlint; "
                "assert distribution('rowlint').metadata['Name'] == 'rowlint'; "
                "assert rowlint.__version__ == distribution('rowlint').version; "
                "assert find_spec('dqtorch') is None; "
                "assert files('rowlint').joinpath('py.typed').is_file()",
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        subprocess.run([str(command), "--version"], cwd=root, env=environment, check=True)
        subprocess.run([str(command), "--init-config"], cwd=root, env=environment, check=True)
        assert (root / "rowlint_config.yaml").is_file()
        (root / "input.csv").write_text("id,age\n1,25\n1,150\n", encoding="utf-8")
        (root / "rules.yaml").write_text(
            "dataset: {min_rows: 2, max_rows: 2}\n"
            "schema: {allow_extra_columns: false}\n"
            "columns:\n  id: {unique: true}\n  age: {max: 120}\n",
            encoding="utf-8",
        )
        subprocess.run(
            [str(command), "--check-config", "rules.yaml"],
            cwd=root,
            env=environment,
            check=True,
        )
        result = subprocess.run(
            [str(command), "input.csv", "--config", "rules.yaml", "--format", "json"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, result.stderr
        report = json.loads(result.stdout)
        assert report["schema_version"] == 1 and not report["passed"]
        assert report["summary"]["failed_checks"] == 2
        assert any(check["failed_count"] == 2 for check in report["checks"])
        assert any(check["check"] == "dataset.min_rows" for check in report["checks"])
        assert any(check["check"] == "schema.extra_columns" for check in report["checks"])
        concise = subprocess.run(
            [str(command), "input.csv", "--config", "rules.yaml", "--concise"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert concise.returncode == 1 and "2 failed" in concise.stdout
        assert "Profile:" not in concise.stdout
        result = subprocess.run(
            [str(python), "-m", "rowlint", "input.csv", "--format", "json"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        profile = json.loads(result.stdout)
        assert profile["passed"] and profile["summary"]["status"] == "not_run"
        if extras:
            subprocess.run(
                [
                    str(python),
                    "-c",
                    "import pandas as pd; pd.DataFrame({'id': [1, 2]}).to_parquet('input.parquet')",
                ],
                cwd=root,
                env=environment,
                check=True,
            )
            result = subprocess.run(
                [str(command), "input.parquet", "--format", "json"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["metadata"]["row_count"] == 2
            if "polars" in extras.split(","):
                subprocess.run(
                    [
                        str(python),
                        "-c",
                        "import polars as pl; "
                        "from rowlint import DataQualityChecker; "
                        "report = DataQualityChecker(pl.DataFrame({'id': [1, 1]})).validate("
                        "{'columns': {'id': {'unique': True}}}); "
                        "assert not report.passed and report.summary['failed_checks'] == 1",
                    ],
                    cwd=root,
                    env=environment,
                    check=True,
                )
        result = subprocess.run(
            [str(command), "missing.csv"], cwd=root, env=environment, capture_output=True, text=True
        )
        assert result.returncode == 2 and result.stderr and not result.stdout
        print(f"Installation smoke checks passed: {artifact.name} (extras: {extras or 'none'})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extras", choices=["parquet", "polars", "parquet,polars"])
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()
    for artifact in args.artifacts:
        smoke(artifact, args.extras)
