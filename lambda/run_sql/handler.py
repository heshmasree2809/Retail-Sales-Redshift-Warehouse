"""Lambda used by the Step Functions state machine to run a packaged .sql file on Redshift.

Event: {"sql_file": "sql/03_transform.sql", "batch_id": "<execution name>", "mode": "run" | "checks"}
 - run:    execute every statement in the file, in order, waiting for each to finish.
 - checks: the file holds one query returning (check_name, failed_count); any count > 0 raises
           DataQualityError, which fails the state machine.
"""
import os
import time

try:  # packaged layout: modules sit next to this file
    from sqlfiles import render, split_statements
    from redshift_data import DataApi
except ImportError:  # repo layout (tests)
    from rdw.sqlfiles import render, split_statements
    from rdw.redshift_data import DataApi


class DataQualityError(Exception):
    pass


def _read_sql(sql_file):
    if not sql_file.startswith("sql/") or ".." in sql_file or not sql_file.endswith(".sql"):
        raise ValueError("sql_file must be a packaged file under sql/: %r" % sql_file)
    here = os.path.dirname(os.path.abspath(__file__))
    # packaged: sql/ sits next to this file. repo checkout (tests): sql/ is two levels up.
    for base in (here, os.path.join(here, "..", "..")):
        path = os.path.join(base, sql_file)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError(sql_file)


def handler(event, context=None, api=None):
    params = {
        "BUCKET": os.environ.get("BUCKET", ""),
        "IAM_ROLE_ARN": os.environ.get("IAM_ROLE_ARN", ""),
        "BATCH_ID": event.get("batch_id", "manual"),
    }
    sql = render(_read_sql(event["sql_file"]), params)
    statements = split_statements(sql)
    api = api or DataApi(os.environ["WORKGROUP"], os.environ["DATABASE"])
    started = time.time()

    if event.get("mode") == "checks":
        rows = api.query(statements[0])
        failed = {r["check_name"]: r["failed_count"] for r in rows if r["failed_count"]}
        if failed:
            raise DataQualityError("data quality checks failed: %s" % failed)
        return {"sql_file": event["sql_file"], "checks_passed": len(rows), "seconds": round(time.time() - started, 1)}

    for stmt in statements:
        api.execute(stmt)
    return {"sql_file": event["sql_file"], "statements_run": len(statements), "seconds": round(time.time() - started, 1)}
