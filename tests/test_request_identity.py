import unittest
from scripts.study_behavior import same_tool_request,next_action
from scripts.probe_request_report import query_category


class RequestIdentityTests(unittest.TestCase):
    def test_ignored_outer_fields_do_not_make_the_same_request_new(self):
        original={'type':'tool','name':'lookup_rows','arguments':{'table':'products','filters':{}},'cursor':0}
        repeated={'type':'tool','name':'lookup_rows','arguments':{'filters':{},'table':'products'}}
        self.assertTrue(same_tool_request(original,repeated))
        prefix={'history':[{'action':original,'tool_result':{'rows':[]}}]}
        self.assertEqual(next_action({'action':repeated,'visible_history':prefix['history']},[])['category'],'repeat_tool')
        sample={'category':'tool_new','action':repeated}
        self.assertEqual(query_category(sample,prefix),'tool_repeat')
        self.assertEqual(sample['category'],'tool_new')

    def test_actual_argument_changes_and_failure_categories_are_preserved(self):
        original={'type':'tool','name':'lookup_rows','arguments':{'table':'products','cursor':0}}
        changed={'type':'tool','name':'lookup_rows','arguments':{'table':'products','cursor':2}}
        self.assertFalse(same_tool_request(original,changed))
        prefix={'history':[{'action':original,'tool_result':{}}]}
        self.assertEqual(query_category({'category':'tool_new','action':changed},prefix),'tool_new')
        self.assertEqual(query_category({'category':'timeout_model'},prefix),'timeout_model')
        self.assertFalse(same_tool_request(None,None))


if __name__=='__main__':unittest.main()
