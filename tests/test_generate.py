import json
import os
import tempfile
import unittest

import _paths  # noqa: F401
from rdw.generate import SCHEMA, generate


class GenerateTest(unittest.TestCase):
    def test_deterministic_for_a_seed(self):
        a, _ = generate(2000, tempfile.mkdtemp(), seed=1, fmt="csv")
        b, _ = generate(2000, tempfile.mkdtemp(), seed=1, fmt="csv")
        self.assertTrue(a["sales"].equals(b["sales"]))

    def test_columns_follow_the_schema_contract(self):
        tables, _ = generate(2000, tempfile.mkdtemp(), seed=2, fmt="csv")
        for name, df in tables.items():
            self.assertEqual(list(df.columns), [c for c, _ in SCHEMA[name]])

    def test_manifest_matches_injected_rows(self):
        out = tempfile.mkdtemp()
        tables, manifest = generate(10_000, out, seed=3, bad_rate=0.01, fmt="csv")
        self.assertTrue(manifest["synthetic"])
        self.assertEqual(manifest["sales_rows_written"], len(tables["sales"]))
        self.assertEqual(len(tables["sales"]), 10_000 + manifest["expected_rejects"]["duplicate_line"])
        with open(os.path.join(out, "manifest.json")) as fh:
            self.assertEqual(json.load(fh)["expected_reject_total"], manifest["expected_reject_total"])

    def test_zero_bad_rate_injects_nothing(self):
        _, manifest = generate(2000, tempfile.mkdtemp(), seed=4, bad_rate=0, fmt="csv")
        self.assertEqual(manifest["expected_rejects"], {})

    def test_parquet_layout_when_pyarrow_is_available(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            self.skipTest("pyarrow not installed")
        out = tempfile.mkdtemp()
        generate(3000, out, seed=5, fmt="parquet")
        sales = os.path.join(out, "curated", "sales")
        self.assertTrue(any(d.startswith("sale_date=") for d in os.listdir(sales)))
        self.assertTrue(os.path.exists(os.path.join(out, "curated", "dim_product", "part-0000.parquet")))
        import pandas as pd
        part = next(d for d in os.listdir(sales) if d.startswith("sale_date="))
        cols = list(pd.read_parquet(os.path.join(sales, part)).columns)
        self.assertEqual(cols, [c for c, _ in SCHEMA["sales"]])


if __name__ == "__main__":
    unittest.main()
