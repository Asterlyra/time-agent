import unittest
from tasks import data_v3, data_v4


class CandidateV4Tests(unittest.TestCase):
    def test_public_data_and_private_answers_unchanged(self):
        for old, new in zip(data_v3.generate('dev'), data_v4.generate('dev')):
            self.assertEqual(old['public'], new['public'])
            self.assertEqual(old['private'], new['private'])

    def test_browse_summaries_never_contains_document_contents(self):
        for task in data_v4.generate('dev'):
            if task['task_family'] != 'evidence': continue
            docs = task['public']['documents']
            result = data_v4.call_tool(task['public'], 'search', {'query': '档案'})
            self.assertEqual(result['results'], [{'id': d['id'], 'summary': d['summary']} for d in docs])
            self.assertTrue(all(set(x) == {'id', 'summary'} for x in result['results']))
            self.assertEqual(data_v4.call_tool(task['public'], 'search', {'query': '销量为'})['results'], [])

    def test_names_match_and_read_still_needed(self):
        task = next(t for t in data_v4.generate('dev') if t['task_id'] == 'dev-evidence-00')
        public = task['public']
        for doc in public['documents']:
            name = doc['summary'].split()[-1]
            results = data_v4.call_tool(public, 'search', {'query': name})['results']
            self.assertEqual(results, [{'id': doc['id'], 'summary': doc['summary']}])
            self.assertEqual(data_v4.call_tool(public, 'read_document', {'id': doc['id']})['document'], doc)

    def test_table_pagination_unchanged(self):
        task = next(t for t in data_v4.generate('dev') if t['task_family'] == 'table')
        args = {'table': 'products', 'filters': {}, 'cursor': 0}
        self.assertEqual(data_v4.call_tool(task['public'], 'lookup_rows', args),
                         data_v3.call_tool(task['public'], 'lookup_rows', args))
        self.assertIn('档案', data_v4.tool_schemas()['evidence']['search']['description'])


if __name__ == '__main__': unittest.main()
