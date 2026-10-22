"""Decision 1: never coerce during validation.

Numbers that arrive as text fail validation, even though every value would
pass the range check after casting. Expected: dtype and min checks fail.
"""

import pandas as pd

from rowlint import DataQualityChecker

df = pd.DataFrame({"quantity": ["2", "5", "1"]})  # numbers that arrived as text
report = DataQualityChecker(df).validate({"columns": {"quantity": {"dtype": "integer", "min": 1}}})
print(report.to_terminal(concise=True))
