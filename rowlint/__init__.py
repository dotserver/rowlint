"""Lightweight data profiling and validation for pandas and CSV pipelines."""

from importlib.metadata import PackageNotFoundError, version

from .checker import DataQualityChecker
from .config import ConfigError, load_yaml_config
from .report import CheckResult, Report

try:
    __version__ = version("rowlint")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["DataQualityChecker", "CheckResult", "Report", "ConfigError", "load_yaml_config"]
