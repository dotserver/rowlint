# RowLint examples

Six runnable examples for RowLint 0.2.0 or newer, using synthetic data. They
demonstrate validation failures deliberately: an exit code of 1 or 2 is the
expected result for several shell scripts.

From a source checkout, install RowLint into your active Python environment:

```bash
python -m pip install -e .
```

For a downloaded examples folder, install `python -m pip install 'rowlint>=0.2.0'`.
These examples use the base dependencies; Parquet and Polars extras are optional.

Run the following commands from the repository root. Shell scripts locate their
own files, so they can also be invoked by absolute path from another directory.

| Folder | Demonstrates | Command from repository root | Expected result |
| --- | --- | --- | --- |
| `01_eight_rows_seven_problems` | Several checks on a small orders extract | `bash examples/01_eight_rows_seven_problems/run.sh` | 7 failed checks; exit 1 |
| `02_no_coercion` | Numbers arriving as text | `python examples/02_no_coercion/example.py` | `dtype` and `min` fail; exit 0 |
| `03_null_semantics` | Range checks and explicit null tolerance | `python examples/03_null_semantics/example.py` | Range checks evaluate 1 of 4 rows; null tolerance fails; exit 0 |
| `04_evidence_not_data` | Bounded failure evidence | `python examples/04_evidence_not_data/example.py` | 3,000 failures and 5 numeric row labels; exit 0 |
| `05_exit_code_gate` | Branching on validation results | `bash examples/05_exit_code_gate/gate.sh` | Prints `quarantine`; exit 1 |
| `05_exit_code_gate` | Rejecting invalid rules without loading data | `bash examples/05_exit_code_gate/check_config.sh` | `ConfigError`; exit 2 |
| `06_baseline` | Comparing daily batches | `bash examples/06_baseline/run.sh` | Null-fraction and distinct-count checks fail; exit 1 |

## Eight rows, seven failed checks

The orders extract contains an unexpected `promo_code` column, duplicate order
IDs, a missing customer ID, an unsupported country code, a negative quantity,
an incorrect line-item total, and a shipment before its order. The duplicate-ID
check flags both members of the duplicate group. Seven failed checks does not
mean seven distinct bad rows: one row can fail several checks, and schema
failures describe columns rather than individual rows.

The date comparison uses normalized `YYYY-MM-DD` strings, whose lexical order
matches calendar order. For other date formats, parse dates in Python before
validation; this example does not perform date parsing.

## Exit codes and generated files

The Python examples print reports and exit normally, even when the report
contains failures. The shell examples demonstrate RowLint's CLI exit codes:
0 for success, 1 for failed rules, and 2 for errors.

`gate.sh` prints the intended pipeline action: `load`, `quarantine`, or an error.
It accepts an optional CSV path, relative to your current working directory:

```bash
bash examples/05_exit_code_gate/gate.sh ./batch.csv
```

Its rules remain those from example 01, so a passing batch must satisfy that
schema. The script writes `examples/05_exit_code_gate/report.json` when RowLint
can produce a report.

The baseline script generates two CSV batches and a `baseline.json` file inside
`06_baseline/`. Generated files are ignored by git. Re-running the examples
overwrites their generated outputs.

## Compatibility and testing

- Shell scripts need Bash. On Windows, use Git Bash or WSL with Python and
  RowLint installed in that environment.
- pandas 2.x and 3.x can describe string dtypes differently. The no-coercion
  example fails the same rules on both versions.
- The evidence example uses numeric index labels. Custom index labels and
  check messages can contain caller-supplied values; bounded samples alone do
  not anonymize a report.
- The baseline comparison detects schema and aggregate metric changes. In
  this example, country cardinality changes from 4 to 6; this is not a test of
  arbitrary value or distribution changes.

To run the example integration tests after installing the development extra:

```bash
python -m pip install -e '.[dev]'
python -m pytest tests/test_examples.py
```

Tests use temporary copies and the same Python interpreter as pytest. They
check every example plus all three gate exit paths; the source examples remain
clean. CI runs these tests with the regular test suite. Shell tests are skipped
when Bash is unavailable.
