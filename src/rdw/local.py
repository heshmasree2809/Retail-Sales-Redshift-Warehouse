"""Offline demo: run the same transform, quality checks and analytics SQL on SQLite.

This proves the SQL logic (validation, rejects, idempotent merge, window functions) without AWS.
It is NOT a Redshift performance test: SQLite has no distribution keys, sort keys or columnar storage.
"""
import argparse
import os
import sqlite3

import pandas as pd

from rdw.generate import generate, SCHEMA
from rdw.sqlfiles import parse_named_queries, render, split_statements

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SQL_DIR = os.path.join(ROOT, "sql")


def read_sql(name):
    with open(os.path.join(SQL_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def connect_and_create(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.executescript(read_sql("local/schema_sqlite.sql"))
    return conn


def load_tables(conn, tables):
    for name, df in tables.items():
        target = {"sales": "stg_sales"}.get(name, name)
        out = df.copy()
        for col, kind in SCHEMA[name]:
            if kind == "date":
                out[col] = out[col].astype(str)
        out.to_sql(target, conn, if_exists="append", index=False)
    conn.commit()


def run_script(conn, sql_name, batch_id="local"):
    sql = render(read_sql(sql_name), {"BATCH_ID": batch_id})
    for stmt in split_statements(sql):
        conn.execute(stmt)
    conn.commit()


def run_checks(conn):
    stmt = split_statements(read_sql("05_quality_checks.sql"))[0]
    return {name: count for name, count in conn.execute(stmt).fetchall()}


def run_named(conn, sql_name="06_analytics.sql"):
    out = {}
    for name, stmt in parse_named_queries(read_sql(sql_name)).items():
        cur = conn.execute(stmt)
        cols = [d[0] for d in cur.description]
        out[name] = [dict(zip(cols, row)) for row in cur.fetchall()]
    return out


def build(rows=200_000, out_dir="build/local", seed=42, bad_rate=0.005):
    os.makedirs(out_dir, exist_ok=True)
    tables, manifest = generate(rows, os.path.join(out_dir, "data"), seed, bad_rate, fmt="csv")
    db_path = os.path.join(out_dir, "warehouse.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = connect_and_create(db_path)
    load_tables(conn, tables)
    run_script(conn, "03_transform.sql")
    return conn, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", type=int, default=200_000)
    ap.add_argument("--out", default="build/local")
    ap.add_argument("--no-dashboard", action="store_true")
    a = ap.parse_args()

    conn, manifest = build(a.rows, a.out)
    staged = conn.execute("SELECT COUNT(*) FROM stg_sales").fetchone()[0]
    fact = conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    rejects = conn.execute("SELECT reject_reason, COUNT(*) FROM sales_rejects GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print("staged rows: %d | fact rows: %d | rejected: %d (%.2f%%)"
          % (staged, fact, staged - fact, 100.0 * (staged - fact) / staged))
    print("rejects by reason:", dict(rejects))
    print("expected (from generator manifest):", manifest["expected_rejects"])

    checks = run_checks(conn)
    print("quality checks:", "ALL PASS" if not any(checks.values()) else checks)

    results = run_named(conn)
    for name, rows in results.items():
        print("\n== %s (%d rows) ==" % (name, len(rows)))
        print(pd.DataFrame(rows).head(5).to_string(index=False))

    if not a.no_dashboard:
        from rdw.dashboard import build_html
        path = os.path.join(a.out, "dashboard.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(build_html(results, "Local SQLite demo (synthetic data)"))
        print("\ndashboard written to", path)


if __name__ == "__main__":
    main()
