import unittest
from tasks.data import call_tool, generate, verify


class TaskTests(unittest.TestCase):
    def test_generation_and_separation(self):
        self.assertEqual(generate("dev"), generate("dev"))
        self.assertEqual(len(generate("dev")), 8)
        test = generate("test")
        self.assertEqual(len(test), 20)
        for family in ("evidence", "table"):
            self.assertEqual(len({t["template_id"] for t in test if t["task_family"] == family}), 5)
        self.assertFalse(set(t["task_id"] for t in test) & set(t["task_id"] for t in generate("dev")))
        for t in test:
            self.assertNotIn("private", t["public"])
            self.assertTrue(verify(t["private"], {"value": t["private"]["value"], "evidence_ids": t["private"]["evidence_ids"]})["correct"])

    def test_verifier_rejects_wrong_missing_and_fake_evidence(self):
        p = generate("dev")[0]["private"]
        good = {"value": p["value"], "evidence_ids": list(reversed(p["evidence_ids"]))}
        self.assertTrue(verify(p, good)["correct"])
        self.assertFalse(verify(p, {**good, "value": p["value"] + 1})["correct"])
        self.assertFalse(verify(p, {"value": p["value"]})["correct"])
        self.assertFalse(verify(p, {**good, "evidence_ids": ["fake"]})["correct"])
        self.assertTrue(verify(p, {**good, "value": p["value"] + .004})["correct"])
        self.assertFalse(verify(p, {**good, "value": p["value"] + .006})["correct"])

    def test_tools_and_calculator_sandbox(self):
        evidence = generate("dev")[0]["public"]
        results = call_tool(evidence, "search", {"query": "记录"})["results"]
        self.assertEqual(len(results), 3)
        self.assertNotIn("测量值为", str(results))
        self.assertIn("document", call_tool(evidence, "read_document", {"id": "D1"}))
        table = generate("dev")[4]["public"]
        self.assertEqual(len(call_tool(table, "lookup_rows", {"table": "products", "filters": {}})["rows"]), 6)
        self.assertEqual(len(call_tool(table, "lookup_rows", {"table": "products", "filters": {"category": "active"}})["rows"]), 4)
        self.assertEqual(call_tool(table, "calculate", {"expression": "(3+4)*2"})["value"], 14)
        self.assertIn("error", call_tool(table, "calculate", {"expression": "__import__('os')"}))
        self.assertIn("error", call_tool(table, "calculate", {"expression": "2**999999"}))

    def test_table_join_excludes_distractors_and_evidence(self):
        for t in (t for t in generate('test') if t['task_family'] == 'table'):
            products = call_tool(t['public'], 'lookup_rows', {'table': 'products', 'filters': {'category': 'active'}})['rows']
            batches = call_tool(t['public'], 'lookup_rows', {'table': 'batches', 'filters': {'status': 'shipped'}})['rows']
            pairs = [(p, b) for p in products for b in batches if p['product'] == b['product']]
            self.assertEqual(len(pairs), 3)
            self.assertEqual(set(t['private']['evidence_ids']), {r['id'] for pair in pairs for r in pair})
            self.assertFalse(verify(t['private'], {'value': t['private']['value'], 'evidence_ids': t['private']['evidence_ids'] + ['P4']})['correct'])

    def test_public_tool_results_contain_no_private_metadata(self):
        for t in generate('test'):
            pub = t['public']
            if t['task_family'] == 'evidence':
                out = [call_tool(pub, 'search', {'query': '记录'})] + [call_tool(pub, 'read_document', {'id': d['id']}) for d in pub['documents']]
            else:
                out = [call_tool(pub, 'lookup_rows', {'table': table, 'filters': {}}) for table in ('products', 'batches')]
            self.assertNotIn('private', repr(out))
            self.assertNotIn('evidence_ids', repr(out))
            self.assertNotIn('tolerance', repr(out))


if __name__ == "__main__": unittest.main()
