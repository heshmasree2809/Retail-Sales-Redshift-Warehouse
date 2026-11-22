"""Benchmark tuned vs untuned fact table on Redshift Serverless and write results/benchmark.md.

fact_sales          DISTKEY(product_key) SORTKEY(date_key)
fact_sales_untuned  DISTSTYLE EVEN, sorted by load order (a copy created by this script)
Result cache is switched off for the session so every run does real work. One warm-up run per
query is discarded (the first run includes compilation). Numbers are whatever your account measures.
"""
import argparse
import csv
import os
import statistics

from rdw.local import read_sql
from rdw.redshift_data import DataApi
from rdw.sqlfiles import parse_named_queries, render


def run(workgroup, database, runs=5, out_dir="results"):
    api = DataApi(workgroup, database)
    api.execute("DROP TABLE IF EXISTS fact_sales_untuned")
    api.execute("CREATE TABLE fact_sales_untuned DISTSTYLE EVEN SORTKEY (sales_key) AS SELECT * FROM fact_sales")
    api.execute("ANALYZE fact_sales_untuned")
    rows = []
    for name, template in parse_named_queries(read_sql("07_benchmark.sql")).items():
        for label, table in (("untuned", "fact_sales_untuned"), ("tuned", "fact_sales")):
            sql = render(template, {"FACT": table})
            times = []
            for i in range(runs + 1):
                durations = api.timed_batch(["SET enable_result_cache_for_session TO off", sql])
                if i > 0:
                    times.append(durations[-1])
            rows.append({"query": name, "table": label, "runs": runs, "min_ms": min(times),
                         "median_ms": statistics.median(times), "max_ms": max(times)})
            print(name, label, "median %.1f ms" % statistics.median(times))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "benchmark.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = ["| Query | Untuned median (ms) | Tuned median (ms) | Change |", "|---|---|---|---|"]
    by = {(r["query"], r["table"]): r["median_ms"] for r in rows}
    for name in parse_named_queries(read_sql("07_benchmark.sql")):
        u, t = by[(name, "untuned")], by[(name, "tuned")]
        change = "%.0f%% faster" % (100 * (u - t) / u) if u and t < u else ("%.0f%% slower" % (100 * (t - u) / u) if u else "n/a")
        lines.append("| %s | %.1f | %.1f | %s |" % (name, u, t, change))
    with open(os.path.join(out_dir, "benchmark.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workgroup", required=True)
    ap.add_argument("--database", default="dev")
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()
    run(a.workgroup, a.database, a.runs)


if __name__ == "__main__":
    main()
