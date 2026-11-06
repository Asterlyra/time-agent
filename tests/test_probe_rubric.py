import copy
import unittest

from scripts.mechanism_probe import prefix_rubric, assess, classify
from tasks import data_v4


class ProbeRubricTests(unittest.TestCase):
    def threshold_prefix(self):
        task=next(t for t in data_v4.generate('dev') if t['task_id']=='dev-evidence-02')
        prefix={'prefix_id':'p','observation':{'tools':data_v4.tool_schemas()['evidence']},'history':[]}
        return prefix,task

    def test_public_rubric_keeps_negative_count_inputs_and_ignores_private_ids(self):
        prefix,task=self.threshold_prefix()
        original=prefix_rubric(prefix,task)
        self.assertEqual(len(original['required_source_ids']),3)
        poisoned=copy.deepcopy(task);poisoned['private']={'value':-9,'evidence_ids':['invented']}
        self.assertEqual(prefix_rubric(prefix,poisoned),original)

    def test_search_navigation_is_not_a_full_fact(self):
        prefix,task=self.threshold_prefix();rubric=prefix_rubric(prefix,task)
        action={'type':'tool','name':'search','arguments':{'query':'档案'}}
        result=assess(action,prefix,task,rubric)
        self.assertEqual(result['new_required_navigation_ids'],3)
        self.assertEqual(result['new_required_full_facts'],0)
        prefix['history'].append({'action':action,'tool_result':data_v4.call_tool(task['public'],action['name'],action['arguments'])})
        rubric=prefix_rubric(prefix,task)
        result=assess(action,prefix,task,rubric)
        self.assertTrue(result['exact_query_repeat'])
        self.assertEqual(result['new_required_navigation_ids'],0)
        self.assertEqual(len(rubric['missing_required_facts']),3)

    def test_correct_submission_and_fact_availability_are_separate(self):
        prefix,task=self.threshold_prefix();rubric=prefix_rubric(prefix,task)
        action={'type':'submit','answer':{'value':task['private']['value'],'evidence_ids':task['private']['evidence_ids']}}
        result=assess(action,prefix,task,rubric)
        self.assertEqual(result['category'],'submit_correct')
        self.assertFalse(result['all_required_facts_read_before_action'])
        self.assertEqual(classify({'type':'submit','answer':None},prefix,task),'invalid')
        self.assertEqual(classify({'type':'submit','answer':{'value':10**400,'evidence_ids':[]}},prefix,task),'invalid')


if __name__=='__main__':unittest.main()
