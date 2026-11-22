"""Static checks that keep the SQL files, the generator and the local twin schema in agreement."""
import glob
import os
import re
import unittest

import _paths
from _paths import SQL_DIR, read
from rdw.generate import LOAD_TARGET, SCHEMA
from rdw.sqlfiles import parse_named_queries, placeholders, render, split_statements

KNOWN = {"BUCKET", "IAM_ROLE_ARN", "BATCH_ID", "FACT"}


def table_columns(sql):
    tables = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \(\n(.*?)\n\)", sql, re.S):
        cols = []
        for line in m.group(2).splitlines():
            first = line.strip().split()[0].rstrip(",")
            if first.upper() not in ("PRIMARY", "FOREIGN", "UNIQUE", "CONSTRAINT"):
                cols.append(first)
        tables[m.group(1)] = cols
    return tables


class SqlContractTest(unittest.TestCase):
    def test_redshift_and_sqlite_schemas_have_identical_columns(self):
        self.assertEqual(table_columns(read("sql", "01_schema.sql")), table_columns(read("sql", "local", "schema_sqlite.sql")))

    def test_copy_column_lists_match_generator_column_order(self):
        copies = re.findall(r"COPY (\w+) \(([^)]*)\)\s+FROM 's3://\{\{BUCKET\}\}/curated/(\w+)/'", read("sql", "02_load.sql"))
        self.assertEqual({c[2] for c in copies}, set(SCHEMA))
        for table, cols, prefix in copies:
            self.assertEqual(table, LOAD_TARGET[prefix])
            self.assertEqual([c.strip() for c in cols.split(",")], [c for c, _ in SCHEMA[prefix]], prefix)

    def test_staging_columns_cover_copy_lists(self):
        schema = table_columns(read("sql", "01_schema.sql"))
        self.assertEqual([c for c, _ in SCHEMA["sales"]], schema["stg_sales"][1:-1])  # minus row_id, reject_reason

    def test_every_placeholder_is_known(self):
        for path in glob.glob(os.path.join(SQL_DIR, "*.sql")):
            with open(path, encoding="utf-8") as fh:
                self.assertTrue(placeholders(fh.read()) <= KNOWN, path)

    def test_named_queries_parse_and_render(self):
        analytics = parse_named_queries(read("sql", "06_analytics.sql"))
        self.assertEqual(len([n for n in analytics if n.startswith("q")]), 6)
        bench = parse_named_queries(read("sql", "07_benchmark.sql"))
        for sql in bench.values():
            self.assertIn("fact_sales_untuned", render(sql, {"FACT": "fact_sales_untuned"}))

    def test_render_rejects_missing_placeholder(self):
        with self.assertRaises(KeyError):
            render("SELECT '{{BATCH_ID}}'", {})

    def test_split_statements_ignores_comments(self):
        self.assertEqual(split_statements("-- hi; there\nSELECT 1;\n\nSELECT 2;"), ["SELECT 1", "SELECT 2"])

    def test_every_sql_file_splits_cleanly(self):
        for path in sorted(glob.glob(os.path.join(SQL_DIR, "0*.sql"))):
            with open(path, encoding="utf-8") as fh:
                stmts = split_statements(fh.read())
            self.assertTrue(stmts, path)


if __name__ == "__main__":
    unittest.main()
