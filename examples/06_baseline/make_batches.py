"""Generate two synthetic daily order batches for the baseline example.

The second batch has 120 missing customer IDs and lowercase country codes.
"""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
N = 1000

rng = np.random.default_rng(7)
reference = pd.DataFrame(
    {
        "order_id": np.arange(1, N + 1),
        "customer_id": [f"C{i % 400:03d}" for i in range(N)],
        "country": rng.choice(["GB", "FR", "DE", "US"], N),
        "quantity": rng.integers(1, 10, N),
    }
)

current = reference.copy()
current["order_id"] = current["order_id"] + N
current["customer_id"] = current["customer_id"].astype(object)
current.loc[rng.choice(N, 120, replace=False), "customer_id"] = None  # 12% nulls appear
current["country"] = rng.choice(["GB", "FR", "DE", "US", "gb", "Gb"], N)  # casing drift

reference.to_csv(HERE / "orders_2026-09-01.csv", index=False)
current.to_csv(HERE / "orders_2026-09-02.csv", index=False)
print("Wrote orders_2026-09-01.csv and orders_2026-09-02.csv")
