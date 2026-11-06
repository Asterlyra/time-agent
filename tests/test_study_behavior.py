import unittest

from scripts.study_behavior import distribution, error_class, inspected_full_source_ids, next_action, collect, summarize


class BehaviorTests(unittest.TestCase):
    def test_quantiles_and_error_categories(self):
        self.assertEqual(distribution([])['n'],0)
        self.assertEqual(distribution([0,10,20])['p50'],10)
        self.assertEqual(distribution([0,10,20])['p95'],19)
        self.assertEqual(error_class({'deadline_success':False,'termination_reason':'submitted',
            'verifier_details':{'value_correct':True,'evidence_correct':False}}),'evidence_only_error')

    def test_source_summary_is_not_full_evidence_and_repeated_actions_are_explicit(self):
        action={'type':'tool','name':'search','arguments':{'query':'q'}}
        history=[{'action':action,'tool_result':{'results':[{'id':'D1'}]},'duration_s':2}]
        self.assertEqual(inspected_full_source_ids(history),set())
        event={'action':action,'visible_history':history}
        self.assertEqual(next_action(event,['D1'])['category'],'repeat_tool')
        self.assertFalse(next_action(event,['D1'])['all_required_sources_read'])
        history.append({'tool_result':{'document':{'id':'D1','text':'facts'}}})
        self.assertTrue(next_action(event,['D1'])['all_required_sources_read'])

    def test_completed_prediction_error_and_censoring_are_separate(self):
        action={'type':'tool','name':'search','arguments':{'query':'q'}}
        entry={'run_id':'one','model_id':'m','task_id':'t','task_family':'evidence','profile':'fast_to_slow','condition':'C','repeat':0}
        request=lambda step,start,end,history: {'event_type':'model_request','step_index':step,
            'request_start_offset_s':start,'response_end_offset_s':end,'action':action,
            'observation':{'duration_reference_s':{'search':2}},'visible_history':history,'attempts':[{}]}
        result={'budget_s':100,'shift_fraction':.2,'elapsed_s':100,'latency_profile':'fast_to_slow',
            'termination_reason':'timeout_tool','deadline_success':False,'service_error_flags':[],
            'events':[request(0,20,21,[]),{'event_type':'tool','step_index':0,'tool_name':'search',
                'tool_start_offset_s':21,'tool_end_offset_s':36,'observed_duration_s':15,'tool_result':{}},
                request(1,37,38,[{'action':action,'tool_result':{},'duration_s':15}]),
                {'event_type':'tool','step_index':1,'tool_name':'search','tool_start_offset_s':38,
                 'tool_end_offset_s':100,'is_censored':True}]}
        episodes,predictions,actions,_=collect([{'manifest':entry,'result':result}],{'t':{'private':{'evidence_ids':['D1']}}})
        self.assertEqual(len(predictions),2)
        self.assertEqual(predictions[0]['absolute_error_s'],13)
        self.assertIsNone(predictions[1]['absolute_error_s'])
        self.assertEqual(actions[0]['category'],'repeat_tool')
        summary=summarize(episodes,predictions,actions)
        reference=next(g for g in summary['reference_errors'] if g['profile']=='fast_to_slow' and g['condition']=='C' and g['new_phase'])
        self.assertEqual(reference['eligible_predictions'],2)
        self.assertEqual(reference['censored'],1)
        self.assertEqual(reference['absolute_error_s']['n'],1)
        self.assertEqual(summary['cells'][0]['attempts_without_reported_usage'],2)
        self.assertEqual(episodes[0]['model_request_span_s'],2)
        self.assertEqual(episodes[0]['tool_span_s'],77)
        self.assertEqual(episodes[0]['loop_and_logging_s'],21)


if __name__=='__main__':unittest.main()
