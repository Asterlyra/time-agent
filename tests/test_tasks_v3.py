import unittest
from tasks import data_v2, data_v3


class CandidateV3Tests(unittest.TestCase):
    def test_data_and_answer_unchanged(self):
        before = data_v2.generate('dev')
        after = data_v3.generate('dev')
        self.assertEqual(len(after), 8)
        for old, new in zip(before, after):
            self.assertEqual(old['public'], new['public'])
            self.assertEqual(old['private'], new['private'])

    def test_pagination_returns_complete_filtered_sets(self):
        for task in data_v3.generate('dev'):
            if task['task_family'] != 'table':
                continue
            for table, filt in [('products', {'category': 'active'}), ('batches', {'status': 'shipped'})]:
                expected = data_v2.call_tool(task['public'], 'lookup_rows', {'table': table, 'filters': filt})['rows']
                actual = []
                cursor = 0
                while cursor is not None:
                    page = data_v3.call_tool(task['public'], 'lookup_rows', {'table': table, 'filters': filt, 'cursor': cursor})
                    self.assertLessEqual(len(page['rows']), 2)
                    actual += page['rows']
                    cursor = page['next_cursor']
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), 4)

    def test_invalid_cursor_and_schema(self):
        task = next(t for t in data_v3.generate('dev') if t['task_family'] == 'table')
        for cursor in (-1, 1, True, 100, '2'):
            self.assertIn('error', data_v3.call_tool(task['public'], 'lookup_rows', {'table': 'products', 'cursor': cursor}))
        schema = data_v3.tool_schemas()['table']['lookup_rows']
        self.assertIn('cursor', schema['arguments'])
        self.assertIn('最多2行', schema['description'])
        self.assertNotIn('最多10行', schema['description'])

    def test_evidence_tool_unchanged(self):
        task = next(t for t in data_v3.generate('dev') if t['task_family'] == 'evidence')
        query = task['public']['documents'][0]['summary'].split()[-1]
        self.assertEqual(data_v3.call_tool(task['public'], 'search', {'query': query}),
                         data_v2.call_tool(task['public'], 'search', {'query': query}))
