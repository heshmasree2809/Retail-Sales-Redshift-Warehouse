import json
import re
import unittest

import yaml

import _paths  # noqa: F401
from _paths import read
import handler as runnerr


def load_template():
    class Loader(yaml.SafeLoader):
        pass

    def construct(loader, suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return {"Fn::" + suffix: loader.construct_scalar(node)}
        if isinstance(node, yaml.SequenceNode):
            return {"Fn::" + suffix: loader.construct_sequence(node)}
        return {"Fn::" + suffix: loader.construct_mapping(node)}

    Loader.add_multi_constructor("!", construct)
    return yaml.load(read("infra", "template.yaml"), Loader=Loader)


class TemplateTest(unittest.TestCase):
    def test_template_parses_and_has_core_resources(self):
        t = load_template()
        types = {r["Type"] for r in t["Resources"].values()}
        for expected in ("AWS::S3::Bucket", "AWS::RedshiftServerless::Namespace", "AWS::RedshiftServerless::Workgroup",
                         "AWS::Lambda::Function", "AWS::StepFunctions::StateMachine"):
            self.assertIn(expected, types)

    def test_state_machine_definition_is_valid_json_and_wired(self):
        t = load_template()
        body = t["Resources"]["PipelineStateMachine"]["Properties"]["DefinitionString"]["Fn::Sub"]
        d = json.loads(re.sub(r"\$\{[^}]+\}", "arn:placeholder", body))
        states = d["States"]
        self.assertIn(d["StartAt"], states)
        for name, s in states.items():
            targets = [s.get("Next"), s.get("Default")] + [c["Next"] for c in s.get("Choices", [])] \
                      + [c["Next"] for c in s.get("Catch", [])]
            for target in filter(None, targets):
                self.assertIn(target, states, "%s -> %s" % (name, target))
            self.assertTrue(s.get("Next") or s.get("End") or s["Type"] in ("Fail", "Choice"), name)

    def test_every_packaged_sql_file_referenced_by_the_state_machine_exists(self):
        body = read("infra", "template.yaml")
        for path in set(re.findall(r'"sql_file": "(sql/[\w.]+)"', body)):
            self.assertTrue(read(*path.split("/")), path)


class FakeApi:
    def __init__(self, rows=None):
        self.executed, self.rows = [], rows or []

    def execute(self, sql):
        self.executed.append(sql)

    def query(self, sql):
        self.executed.append(sql)
        return self.rows


class LambdaHandlerTest(unittest.TestCase):
    def setUp(self):
        import os
        os.environ.update(BUCKET="my-bucket", IAM_ROLE_ARN="arn:aws:iam::1:role/r", WORKGROUP="wg", DATABASE="dev")

    def test_run_mode_executes_every_statement_with_placeholders_filled(self):
        api = FakeApi()
        out = runner.handler({"sql_file": "sql/02_load.sql", "batch_id": "b1"}, api=api)
        self.assertEqual(out["statements_run"], len(api.executed))
        joined = "\n".join(api.executed)
        self.assertIn("s3://my-bucket/curated/sales/", joined)
        self.assertIn("arn:aws:iam::1:role/r", joined)
        self.assertNotIn("{{", joined)

    def test_batch_id_reaches_the_transform(self):
        api = FakeApi()
        runner.handler({"sql_file": "sql/03_transform.sql", "batch_id": "exec-42"}, api=api)
        self.assertTrue(any("exec-42" in s for s in api.executed))

    def test_checks_mode_passes_when_all_counts_are_zero(self):
        api = FakeApi([{"check_name": "a", "failed_count": 0}, {"check_name": "b", "failed_count": 0}])
        out = runner.handler({"sql_file": "sql/05_quality_checks.sql", "mode": "checks"}, api=api)
        self.assertEqual(out["checks_passed"], 2)

    def test_checks_mode_raises_data_quality_error(self):
        api = FakeApi([{"check_name": "fact_duplicate_lines", "failed_count": 3}])
        with self.assertRaises(runner.DataQualityError) as cm:
            runner.handler({"sql_file": "sql/05_quality_checks.sql", "mode": "checks"}, api=api)
        self.assertIn("fact_duplicate_lines", str(cm.exception))

    def test_path_traversal_is_rejected(self):
        for bad in ("../secrets.sql", "sql/../handler.py", "/etc/passwd", "sql/x.txt"):
            with self.assertRaises(ValueError):
                runner.handler({"sql_file": bad}, api=FakeApi())


class DataApiTest(unittest.TestCase):
    def test_query_pages_and_converts_values(self):
        from rdw.redshift_data import DataApi

        class Client:
            def __init__(self):
                self.pages = [
                    {"ColumnMetadata": [{"name": "a"}, {"name": "b"}],
                     "Records": [[{"longValue": 1}, {"stringValue": "x"}]], "NextToken": "t"},
                    {"ColumnMetadata": [{"name": "a"}, {"name": "b"}],
                     "Records": [[{"isNull": True}, {"doubleValue": 2.5}]]},
                ]

            def execute_statement(self, **kw):
                return {"Id": "1"}

            def describe_statement(self, Id):
                return {"Status": "FINISHED"}

            def get_statement_result(self, **kw):
                return self.pages.pop(0)

        rows = DataApi("wg", "dev", client=Client(), poll_seconds=0).query("select 1")
        self.assertEqual(rows, [{"a": 1, "b": "x"}, {"a": None, "b": 2.5}])

    def test_failed_statement_raises_with_error_text(self):
        from rdw.redshift_data import DataApi, QueryError

        class Client:
            def execute_statement(self, **kw):
                return {"Id": "9"}

            def describe_statement(self, Id):
                return {"Status": "FAILED", "Error": "relation does not exist"}

        with self.assertRaises(QueryError) as cm:
            DataApi("wg", "dev", client=Client(), poll_seconds=0).execute("select * from nope")
        self.assertIn("relation does not exist", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
