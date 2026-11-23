"""Runs the real transform / quality / analytics SQL on SQLite with generated data."""
import tempfile
import unittest

import _paths  # noqa: F401
from rdw import local


class LocalPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.conn, cls.manifest = local.build(rows=30_000, out_dir=cls.tmp, seed=7, bad_rate=0.01)

    def count(self, sql):
        return self.conn.execute(sql).fetchone()[1]

    def test_rejects_match_what_the_generator_injected(self):
        got = dict(self.conn.execute("SELECT reject_reason, COUNT(*) FROM sales_rejects GROUP BY 1").fetchall())
        self.assertEqual(got, self.manifest["expected_rejects"])

    def test_every_staged_row_is_either_loaded_or_rejected(self):
        staged = self.count("SELECT COUNT(*) FROM stg_sales")
        self.assertEqual(staged, self.count("SELECT COUNT(*) FROM fact_sales") + self.count("SELECT COUNT(*) FROM sales_rejects"))

    def test_quality_checks_pass(self):
        checks = local.run_checks(self.conn)
        self.assertEqual({k: v for k, v in checks.items() if v}, {})
        self.assertIn("fact_duplicate_lines", checks)

    def test_quality_checks_catch_corruption(self):
        self.conn.execute("UPDATE fact_sales SET profit = profit + 5 WHERE sales_key = (SELECT MIN(sales_key) FROM fact_sales)")
        try:
            self.assertGreater(local.run_checks(self.conn)["profit_identity_mismatch"], 0)
        finally:
            self.conn.execute("UPDATE fact_sales SET profit = profit - 5 WHERE sales_key = (SELECT MIN(sales_key) FROM fact_sales)")

    def test_rerun_is_idempotent(self):
        before = self.count("SELECT COUNT(*) FROM fact_sales")
        revenue = self.count("SELECT ROUND(SUM(revenue), 2) FROM fact_sales")
        self.conn.execute("UPDATE stg_sales SET reject_reason = NULL")
        local.run_script(self.conn, "03_transform.sql")
        self.assertEqual(before, self.count("SELECT COUNT(*) FROM fact_sales"))
        self.assertEqual(revenue, self.count("SELECT ROUND(SUM(revenue), 2) FROM fact_sales"))
        self.assertEqual(self.count("SELECT COUNT(*) FROM sales_rejects"), self.manifest["expected_reject_total"])

    def test_analytics_queries_return_sane_results(self):
        r = local.run_named(self.conn)
        self.assertTrue(all(r[name] for name in r), "every query should return rows")
        q2 = r["q2_month_over_month_growth"]
        self.assertIsNone(q2[0]["prev_revenue"])                       # LAG of the first month
        self.assertAlmostEqual(q2[1]["prev_revenue"], q2[0]["revenue"])
        for row in r["q1_top_products_per_store"]:
            self.assertLessEqual(row["rnk"], 3)
        q3 = r["q3_seven_day_moving_average"]
        self.assertAlmostEqual(q3[0]["revenue_7d_avg"], q3[0]["revenue"], places=1)
        q5 = r["q5_repeat_purchase_rate"][0]
        self.assertTrue(0 < q5["repeat_rate_pct"] < 100)
        q6 = r["q6_pareto_top_20_percent_products"][0]
        self.assertTrue(20 <= q6["top_20_percent_revenue_share_pct"] <= 100)
        total = sum(row["revenue"] for row in r["d1_monthly_kpis"])
        self.assertAlmostEqual(total, self.count("SELECT SUM(revenue) FROM fact_sales"), places=0)

    def test_dashboard_builds(self):
        from rdw.dashboard import build_html
        page = build_html(local.run_named(self.conn), "test")
        self.assertEqual(page.count("<svg"), 3)
        self.assertIn("Retail Sales Warehouse", page)


if __name__ == "__main__":
    unittest.main()
