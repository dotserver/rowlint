"""Command line interface. Exit codes: 0 pass, 1 validation failure, 2 error."""

import argparse
import sys
from importlib.resources import files
from pathlib import Path

import pandas as pd

from . import __version__
from .checker import DataQualityChecker
from .config import load_yaml_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile and validate a CSV or Parquet dataset.")
    parser.add_argument("csv_path", nargs="?", help="Input CSV or Parquet path")
    parser.add_argument("--input", help="Alternative input path")
    parser.add_argument("--input-format", choices=["auto", "csv", "parquet"], default="auto")
    parser.add_argument("--config", help="YAML rules and profiling configuration")
    parser.add_argument("--output", help="Output report path (stdout when omitted)")
    parser.add_argument("--format", choices=["text", "md", "json", "html"], default="text")
    parser.add_argument("--baseline", help="Compare against a previously saved JSON report")
    parser.add_argument("--init-config", action="store_true", help="Write a default YAML template")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing config template"
    )
    parser.add_argument("--sep", default=",", help="CSV delimiter (default: comma)")
    parser.add_argument("--encoding", default="utf-8", help="CSV encoding (default: utf-8)")
    parser.add_argument(
        "--dtype",
        action="append",
        default=[],
        metavar="COLUMN=DTYPE",
        help="CSV dtype override; repeatable, e.g. --dtype id=string",
    )
    parser.add_argument("--version", action="version", version=f"rowlint {__version__}")
    args = parser.parse_args(argv)
    if args.input and args.csv_path:
        parser.error("Provide only one input path, either positional or --input")
    try:
        if args.init_config:
            if args.input or args.csv_path or args.baseline or args.dtype:
                parser.error("--init-config cannot be combined with dataset input options")
            target = Path(args.config or "rowlint_config.yaml")
            template = files("rowlint").joinpath("default_config.yaml").read_text(encoding="utf-8")
            with target.open("w" if args.force else "x", encoding="utf-8") as stream:
                stream.write(template)
            print(f"Configuration written to {target}")
            return 0
        if args.force:
            parser.error("--force requires --init-config")
        input_path = args.input or args.csv_path
        if not input_path:
            parser.error("An input dataset path is required")
        config = load_yaml_config(args.config) if args.config else None
        input_format = args.input_format
        if input_format == "auto":
            input_format = (
                "parquet" if Path(input_path).suffix.lower() in {".parquet", ".pq"} else "csv"
            )
        if input_format == "parquet":
            if args.dtype:
                parser.error("--dtype applies only to CSV input")
            try:
                df = pd.read_parquet(input_path, engine="pyarrow")
            except ImportError as exc:
                raise ImportError("Parquet input requires pip install 'rowlint[parquet]'") from exc
        else:
            dtypes = {}
            for override in args.dtype:
                name, separator, dtype = override.partition("=")
                if not separator or not name or not dtype or name in dtypes:
                    parser.error("Each --dtype must be a distinct COLUMN=DTYPE pair")
                dtypes[name] = dtype
            df = pd.read_csv(input_path, sep=args.sep, encoding=args.encoding, dtype=dtypes or None)
            unknown = dtypes.keys() - set(df.columns)
            if unknown:
                parser.error(f"--dtype references unknown columns: {', '.join(sorted(unknown))}")
        report = DataQualityChecker(df).validate(config, baseline=args.baseline)
        if args.output:
            report.write(args.output, args.format)
        else:
            renderers = {
                "text": report.to_terminal,
                "md": report.to_markdown,
                "json": report.to_json,
                "html": report.to_html,
            }
            print(renderers[args.format](), end="")
        return 2 if report.has_errors else (0 if report.passed else 1)
    except Exception as exc:
        print(f"rowlint: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
