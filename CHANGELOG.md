# Changelog

## Unreleased

### Added

- Six runnable examples with synthetic data covering validation failures,
  type preservation, null semantics, bounded evidence, exit-code gates, and
  baseline comparisons.
- Integration tests for the examples, including success, validation failure,
  and input-error gate paths, run in temporary copies of the example files.
- Example sources and documentation included in source distributions.

## 0.2.0 — 2026-10-19

### Added

- Inclusive dataset row-count limits with `dataset.min_rows` and `dataset.max_rows`.
- Strict schema validation with `schema.allow_extra_columns: false`, using
  declared `columns` as the allowlist and preserving optional-column behavior.
- A `Report.summary` property and additive JSON `summary` field with profiling
  mode, validation status, and totals for passing, failing, skipped, and errored
  checks. Existing JSON fields and `schema_version=1` are retained.
- Clear profiling-only labels and consistent summaries in terminal, Markdown,
  and HTML reports, including distinct error and all-skipped statuses.
- Configuration validation without data through `rowlint --check-config PATH`,
  using the same strict YAML and rule validation as normal execution.
- Concise text reports through CLI `--concise`, `to_terminal(concise=True)`, and
  `write(path, "text", concise=True)`, retaining failures, errors, and samples.

### Changed

- Optional Parquet and Polars extras require pandas 2.2.2+, NumPy 2+, and
  PyArrow 16+, preventing installation of the NumPy 1.x/PyArrow 26 combination.
  The base installation retains pandas 2.2.0 and NumPy 1.x support. Environments
  pinned to NumPy 1.x must upgrade to use these extras in RowLint 0.2.0.
- CI covers minimum core dependencies, minimum optional dependencies, and
  current optional backends. Installation smoke checks exercise both artifacts
  with and without extras.
- Published installation instructions and separate contributor and release
  guides replace the original pre-publication README instructions.

## 0.1.0

Initial public release: profiling, YAML/Python validation rules, custom checks,
baseline comparisons, CSV/Parquet CLI input, optional eager Polars conversion,
and terminal, JSON, Markdown, and HTML reports.
