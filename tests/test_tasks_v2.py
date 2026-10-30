import re
import unittest
from tasks import data_v2 as v2
from tasks import data


class CandidateV2Tests(unittest.TestCase):
    def test_determinism_separation_and_counts(self):
        self.assertEqual(v2.generate('dev'), v2.generate('dev'))
        self.assertEqual(len(v2.generate('dev')), 8)
        test = v2.generate('test')
        self.assertEqual(len(test), 20)
        for family in ('evidence', 'table'):
            self.assertEqual(len({t['template_id'] for t in test if t['task_family'] == family}), 5)
        ids = [tuple(t['private']['evidence_ids']) for t in test]
        self.assertEqual(len(set(ids)), 20)
        self.assertFalse(set(ids) & {tuple(t['private']['evidence_ids']) for t in v2.generate('dev')})

    def test_randomized_table_join_and_verifier_compatibility(self):
        test = [t for t in v2.generate('test') if t['task_family'] == 'table']
        placements = set()
        for task in test:
            products = v2.call_tool(task['public'], 'lookup_rows', {'table': 'products', 'filters': {}})['rows']
            batches = v2.call_tool(task['public'], 'lookup_rows', {'table': 'batches', 'filters': {}})['rows']
            paired = [(p, b) for p in products for b in batches if p['product'] == b['product'] and p['category'] == 'active' and b['status'] == 'shipped']
            self.assertEqual(len(paired), 3)
            self.assertEqual({row['id'] for pair in paired for row in pair}, set(task['private']['evidence_ids']))
            positions = tuple(i for i, p in enumerate(products) if p['id'] in task['private']['evidence_ids'])
            placements.add(positions)
            good = {'value': task['private']['value'], 'evidence_ids': task['private']['evidence_ids'][::-1]}
            self.assertTrue(data.verify(task['private'], good)['correct'])
            self.assertFalse(data.verify(task['private'], {**good, 'evidence_ids': good['evidence_ids'][:-1]})['correct'])
        self.assertGreater(len(placements), 1)

    def test_evidence_search_hides_values_and_read_exposes_only_document(self):
        for task in (t for t in v2.generate('test') if t['task_family'] == 'evidence'):
            for doc in task['public']['documents']:
                name = doc['summary'].split(' ')[1]
                result = v2.call_tool(task['public'], 'search', {'query': name})
                match = [x for x in result['results'] if x['id'] == doc['id']]
                self.assertEqual(len(match), 1)
                self.assertEqual(match[0]['summary'], doc['summary'])
                self.assertNotIn('text', match[0])
                self.assertEqual(v2.call_tool(task['public'], 'read_document', {'id': doc['id']})['document'], doc)
                self.assertNotIn('evidence_ids', str(result))

    def test_linked_route_requires_three_records(self):
        task = next(t for t in v2.generate('test') if t['template_id'] == 'evidence-linked_route')
        name = re.search(r'从 (实体\d+) 出发', task['public']['question']).group(1)
        read_ids, terms = [], []
        while name:
            result = v2.call_tool(task['public'], 'search', {'query': name})['results']
            match = next(x for x in result if x['summary'] == '档案 ' + name)
            doc = v2.call_tool(task['public'], 'read_document', {'id': match['id']})['document']
            read_ids.append(doc['id'])
            terms.append(int(re.search(r'(?:长度|费用)为 (\d+)', doc['text']).group(1)))
            m = re.search(r'下一节点为 (实体\d+)', doc['text'])
            name = m.group(1) if m else None
        self.assertEqual(len(read_ids), 3)
        self.assertTrue(v2.verify(task['private'], {'value': sum(terms), 'evidence_ids': read_ids})['correct'])

if __name__ == '__main__': unittest.main()
