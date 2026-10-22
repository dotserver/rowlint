"""Decision 2: make nulls a separate question.

A range check on a mostly empty column passes, because nulls are excluded.
Look at evaluated_count, then add max_null_fraction to state null tolerance.
"""

import pandas as pd

from rowlint import DataQualityChecker

df = pd.DataFrame({"age": [34, None, None, None]})

# 1. Range rules only: passes, but only one of four rows was evaluated.
report = DataQualityChecker(df).validate({"columns": {"age": {"min": 0, "max": 120}}})
print(report.passed)  # True

for check in report.to_dict()["checks"]:
    print(check["check"], check["status"], check["evaluated_count"])

print()

# 2. Range rules plus an explicit null tolerance: fails at 75% missing.
report = DataQualityChecker(df).validate(
    {"columns": {"age": {"min": 0, "max": 120, "max_null_fraction": 0.05}}}
)
print(report.to_terminal(concise=True))
