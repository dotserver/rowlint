# Contributing to RowLint

Bug reports, documentation improvements, and code contributions are welcome.
Report issues on [GitHub](https://github.com/dotserver/rowlint/issues), including
the RowLint, Python, and pandas versions, a small reproducible example, and the
expected and actual results.

## Development setup

Use Python 3.11 or newer. From a source checkout:

```bash
git clone https://github.com/dotserver/rowlint.git
cd rowlint
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,parquet,polars]'
```

If you already have a checkout, start with the virtual environment commands.
On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in
PowerShell instead of `source .venv/bin/activate`.

The editable installation makes local source changes available immediately.
The `dev` extra installs lint, test, and packaging tools; `parquet` and `polars`
install the optional backends so their tests can run locally.

To install just the library from a checkout, use `python -m pip install .`.
Optional source installations use `python -m pip install '.[parquet]'` or
`python -m pip install '.[polars]'`.

## Checks

Run these commands from the repository root with the environment activated:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=rowlint
```

To format changed Python files, run `python -m ruff format .` and repeat the
checks. For changes to packaging or the README, also run the build and metadata
checks in the [release guide](RELEASING.md#build-and-check-the-distributions).

CI tests Python 3.11–3.14, the minimum supported pandas version, and pandas
2.x/3.x. The pandas 2.2.0 job uses NumPy 1.x and PyArrow below 26; the remaining
jobs use NumPy 2.x and current PyArrow releases. It also checks lint, formatting,
distribution metadata, and installation
of both the wheel and source distribution in fresh environments. Optional
backend tests run when their dependencies are installed. CI checks packages;
maintainers publish releases separately.

## Project structure

- `rowlint/config.py`: YAML loading, defaults, and configuration validation.
- `rowlint/checks.py`: vectorized profiling and validation checks.
- `rowlint/checker.py`: execution and the public `DataQualityChecker` API.
- `rowlint/baseline.py`: schema and metric comparisons.
- `rowlint/report.py`: result objects and report rendering.
- `rowlint/cli.py`: command-line arguments and exit codes.
- `tests/`: coverage for configuration, rules, reports, adapters, and the CLI.
- `scripts/smoke_install.py`: wheel and source installation checks.

Checks run on the complete dataset in memory. Reports contain aggregates and
bounded index samples rather than full data rows. Configuration, rule semantics,
and the public API are documented in the [README](README.md).

## Submitting a change

1. Create a branch for the change.
2. Keep the change focused and update the relevant documentation.
3. Add or update tests when changing behavior, including failure cases.
4. Run the relevant checks and open a pull request against `main`.

Describe the problem, the resulting behavior, and how you verified the change.
For documentation changes, identify the affected examples or instructions.

Release preparation and publication are documented in [RELEASING.md](RELEASING.md).
