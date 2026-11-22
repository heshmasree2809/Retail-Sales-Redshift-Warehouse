"""Thin wrapper over the Redshift Data API (works with Redshift Serverless via WorkgroupName).

Used by the Lambda runner, the benchmark and the dashboard. boto3 is imported lazily so the
rest of the project (generator, local demo, tests) does not need it.
"""
import time


class QueryError(RuntimeError):
    pass


class DataApi:
    def __init__(self, workgroup, database, client=None, poll_seconds=1.0, timeout_seconds=840):
        if client is None:
            import boto3
            client = boto3.client("redshift-data")
        self.client = client
        self.workgroup = workgroup
        self.database = database
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def _wait(self, statement_id):
        deadline = time.time() + self.timeout_seconds
        while True:
            desc = self.client.describe_statement(Id=statement_id)
            status = desc["Status"]
            if status == "FINISHED":
                return desc
            if status in ("FAILED", "ABORTED"):
                raise QueryError("statement %s %s: %s" % (statement_id, status, desc.get("Error", "no error text")))
            if time.time() > deadline:
                raise QueryError("statement %s still %s after %ss" % (statement_id, status, self.timeout_seconds))
            time.sleep(self.poll_seconds)

    def execute(self, sql):
        """Run one statement and wait for it to finish. Returns the statement id."""
        resp = self.client.execute_statement(WorkgroupName=self.workgroup, Database=self.database, Sql=sql)
        self._wait(resp["Id"])
        return resp["Id"]

    def query(self, sql):
        """Run a SELECT and return rows as a list of dicts."""
        statement_id = self.execute(sql)
        rows, token, columns = [], None, None
        while True:
            kwargs = {"Id": statement_id}
            if token:
                kwargs["NextToken"] = token
            page = self.client.get_statement_result(**kwargs)
            if columns is None:
                columns = [c["name"] for c in page["ColumnMetadata"]]
            for record in page["Records"]:
                rows.append({col: _value(field) for col, field in zip(columns, record)})
            token = page.get("NextToken")
            if not token:
                return rows

    def timed_batch(self, sqls):
        """Run statements in one session; return each statement's duration in milliseconds."""
        resp = self.client.batch_execute_statement(WorkgroupName=self.workgroup, Database=self.database, Sqls=sqls)
        desc = self._wait(resp["Id"])
        return [round(sub.get("Duration", 0) / 1e6, 2) for sub in desc.get("SubStatements", [])]


def _value(field):
    if field.get("isNull"):
        return None
    for key in ("longValue", "doubleValue", "stringValue", "booleanValue"):
        if key in field:
            return field[key]
    return None
