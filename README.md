# RowLint

Lightweight data profiling and validation for pandas DataFrames, CSV files,
and Parquet datasets. Define rules in YAML or Python, receive actionable
results, and fail a pipeline when its data violates your expectations.

Requires Python 3.11+ and pandas 2.2 or 3.x. All checks operate in memory.

## Install

Install from PyPI:

```bash
python -m pip install rowlint
```

Optional Parquet input or eager Polars DataFrames:

```bash
python -m pip install 'rowlint[parquet]'
python -m pip install 'rowlint[polars]'
```

For installation from a source checkout, see the
[contributor guide](https://github.com/dotserver/rowlint/blob/main/CONTRIBUTING.md).

## Python quick start

```python
import pandas as pd
from rowlint import DataQualityChecker

df = pd.DataFrame({"id": [1, 1, 3], "age": [25, 150, None]})
report = DataQualityChecker(df).validate(
    {
        "columns": {
            "id": {"unique": True, "nullable": False},
            "age": {"dtype": "number", "min": 0, "max": 120, "max_null_fraction": 0.05},
        },
    }
)

print(report.passed)  # False
print(report.to_terminal())
report.write("report.json")
report.write("report.md", "md")
report.write("report.html", "html")
```

Each `CheckResult` has `check`, `column`, `status`, `failed_count`,
`evaluated_count`, `failed_fraction`, `message`, and bounded `row_sample`
index labels. Status is `pass`, `fail`, `skip`, or `error`.

An example uniqueness result:

| Check | Column | Status | Failed / evaluated | Row indices |
| --- | --- | --- | --- | --- |
| unique | id | fail | 2 / 3 | [0, 1] |

`report.passed` is false if any rule fails or errors. A report with profiling
only has no validation rules and passes; profiling findings such as outlier
counts are descriptive, not automatic failures.

## CLI quick start

```bash
rowlint --init-config
rowlint data.csv --config rowlint_config.yaml
rowlint data.csv --config rowlint_config.yaml --format json --output report.json
rowlint data.csv --config rowlint_config.yaml --format html --output report.html
python -m rowlint data.csv --format md
```

Exit codes: **0** for success, **1** for failed validation, **2** for invalid
configuration, arguments, input/output errors, or custom-check errors.
Errors go to stderr. With no `--output`, stdout contains only the requested
report, so JSON output can be piped directly into another tool.

`--init-config` defaults to `rowlint_config.yaml`. Use `--config rules.yaml`
to choose a destination and `--force` to replace an existing template.

CSV parsing follows pandas conventions: empty fields and recognized missing
tokens become nulls. Use `--dtype id=string` to preserve leading zeros;
repeat `--dtype` for multiple columns. `--sep ';'` and `--encoding utf-8`
control CSV parsing. Validation does not silently cast or clean your data.

Parquet input is detected from `.parquet` or `.pq`, or can be selected with
`--input-format parquet`. Install the `parquet` extra first.

## Configuration

```yaml
checks:
  null_values: true
  data_types: true
  unique_values: true
  constant_columns: true
  numeric_outliers: true
  empty_or_nan_strings: true
  duplicate_rows: true

columns:
  id: {required: true, dtype: integer, nullable: false, unique: true}
  age: {dtype: number, min: 0, max: 120, max_null_fraction: 0.05}
  department: {allowed_values: [HR, Engineering, Finance]}
  code: {dtype: string, regex: '[A-Z]{2}[0-9]{4}', non_blank: true}
  optional_note: {required: false}

unique_rows: false
unique_keys: [[customer_id, order_id]]
cross_column_checks:
  - {name: date_order, left: start_date, op: le, right: end_date}
  - name: total_matches
    left: total
    op: eq
    right: [quantity, unit_price]
    operation: multiply
    tolerance: 0.01

report:
  sample_limit: 5
  whitespace_as_empty: true
baseline:
  max_null_increase: 0.05
  max_unique_change: 0.2
```

Unknown keys, quoted boolean strings such as `"false"`, duplicate YAML keys,
malformed regexes, and invalid values raise `ConfigError`. No Python
expressions are evaluated from YAML.

Defaults and selection:

- No config, an empty YAML file, `{}`, and `checks: {}` all use the shipped
  defaults: every profiling check enabled, no validation rules.
- A nonempty `checks` mapping selects profiling checks; omitted names are
  disabled. Set every check to `false` to disable all profiling output.
- Flat mappings such as `{null_values: true}` remain supported.
- `columns` and other rules run independently of profiling selection.
- Columns mentioned in rules are required by default. `required: false`
  skips that column's rules when the column is absent. Unspecified extra
  columns are accepted.

Rule semantics:

- `dtype` accepts logical `integer`, `number`, `string`, `boolean`, and
  `datetime`, or concrete pandas dtypes such as `Int64` and `float64`.
  Logical `integer` accepts nullable integers; concrete dtypes require an
  exact match. Datetime comparisons require already parsed date columns.
- `min` and `max` are inclusive numeric bounds. Stringified numbers fail
  instead of being coerced.
- `regex` matches the entire string. `allowed_values` tests membership.
- Nulls are excluded from uniqueness, ranges, membership, regex, and
  cross-column comparisons. Add `nullable: false` when they must fail.
- `non_blank: true` rejects nulls and empty strings; whitespace-only
  strings also fail unless `whitespace_as_empty` is false.
- `max_null_fraction` is a fraction in `[0, 1]`; a rate exactly at the
  limit passes. Empty datasets have a null fraction of zero.
- Column uniqueness flags every nonnull row participating in a duplicate
  group. Composite keys also reject rows with any missing key component.
- `unique_rows: true` rejects exact duplicate rows. The `duplicate_rows`
  profile counts all participating rows, rather than only later copies.
- Cross-column comparisons support `eq`, `ne`, `lt`, `le`, `gt`, `ge`.
  Arithmetic supports `add`, `multiply`, `subtract`, and `divide`.
  `subtract`/`divide` take two right columns in order. Nonnegative
  absolute `tolerance` is available for numeric `eq`/`ne` comparisons.
- Metadata-level failures, such as a missing column or wrong dtype, have
  zero row counts. Row rules with no eligible rows pass with zero evaluated
  rows. Check `evaluated_count` when enforcing minimum usable data.

## Custom checks

```python
checker = DataQualityChecker(df)
checker.register_check("adult", lambda age: age >= 18, column="age")
checker.register_check("ordered_ids", lambda frame: frame["id"] > 0)
report = checker.validate()
```

Callbacks receive the named Series or the full DataFrame and must treat it
as read-only. Return an aligned boolean Series where **true means valid**,
or a `CheckResult`. Missing mask values fail; wrong types, mismatched indices,
and callback exceptions become visible error results. Sample sizes are
bounded by `report.sample_limit` (0–1000). Duplicate registration names are
rejected. Register callbacks in Python; YAML does not import user code.

## Baseline comparisons

```python
baseline = DataQualityChecker(reference_df).validate()
baseline.write("baseline.json")
report = DataQualityChecker(current_df).validate(baseline="baseline.json")
```

```bash
rowlint reference.csv --format json --output baseline.json
rowlint current.csv --baseline baseline.json --format html --output changes.html
```

Comparisons flag added/removed columns, changed dtypes, increased null
fractions, and changed distinct-value counts. `max_null_increase: 0.05`
allows five percentage points; `max_unique_change: 0.2` allows a 20%
relative cardinality change in either direction. An increase from zero
distinct values to a positive count fails. Use comparable batch sizes and
dtype parsing settings: distinct counts depend on dataset size. This is
schema and metric comparison, not statistical distribution-drift detection.

`report.compare_baseline(other_report)` returns a list of outcomes without
mutating either report. `validate(baseline=...)` includes those outcomes in
its returned report and overall pass/fail status.

## Polars adapter

```python
import polars as pl
from rowlint import DataQualityChecker

report = DataQualityChecker(pl.DataFrame({"id": [1, 1]})).validate(
    {
        "columns": {"id": {"unique": True}},
    }
)
```

Install the adapter with `python -m pip install 'rowlint[polars]'`.
The adapter materializes an eager Polars frame as pandas; it does not run
native Polars expressions or support LazyFrames. Samples use the converted
frame's row indices. Dtypes are reported after conversion.
Arrow extension arrays preserve nullable integer and boolean types during conversion.

## Existing profiling API

`check_nulls()`, `check_dtypes()`, `check_unique()`,
`check_constant_columns()`, `check_outliers()`, and
`check_empty_strings_and_nans()` remain available. `check_duplicate_rows()`
adds row duplication profiling.

`run_checks(config)` still returns the metrics dictionary and stores it in
`checker.results`. Prefer `validate(config)` for rule outcomes.
`check_unique()` returns distinct-value **counts**, not booleans.

JSON exports now use a versioned envelope with `schema_version`, `passed`,
`metadata`, `metrics`, and `checks`; consumers of the prototype's JSON should
read profiling values under `metrics`. CLI output now defaults to text;
select `--format md` for Markdown. Duplicate or nonstring column labels
raise a clear error; rename them before validation.

## Contributing

See the [contributor guide](https://github.com/dotserver/rowlint/blob/main/CONTRIBUTING.md)
for development setup, tests, and contribution guidance. Maintainers can find
build and publishing instructions in the
[release guide](https://github.com/dotserver/rowlint/blob/main/RELEASING.md).
