"""Decision 3: report evidence, not data.

This example prints counts and five numeric row index labels, without email
values. Index labels and custom check messages can contain values supplied by
the caller, so bounded samples alone do not guarantee anonymized reports.
"""

import json

import pandas as pd

from rowlint import DataQualityChecker

emails = pd.DataFrame({"email": ["a@x.com"] * 5000 + ["not-an-email"] * 3000})
report = DataQualityChecker(emails).validate(
    {
        "columns": {"email": {"regex": r"[^@\s]+@[^@\s]+\.[a-z]+"}},
        "report": {"sample_limit": 5},
    }
)
failed = [c for c in report.to_dict()["checks"] if c["check"] == "regex"][0]
print(json.dumps(failed, indent=2))
