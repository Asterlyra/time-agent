import unittest
from scripts.go_study import tasks_for,make_manifest,observations,block_queues,take_entries
from src.adapters.opencode_go import MODELS


class StudyTests(unittest.TestCase):
    def test_matrices_and_split_boundary(self):
        for stage,count in (('diagnostic',18),('development',216),('formal',1080)):
            tasks=tasks_for(stage);manifest=make_manifest(tasks,stage,123)
            self.assertEqual(len(manifest),count)
            self.assertEqual({e['model_id'] for e in manifest},set(MODELS))
            self.assertTrue(all(t['task_id'].startswith('test-' if stage=='formal' else 'dev-') for t in tasks))
            self.assertEqual(len({e['run_id'] for e in manifest}),count)
        self.assertEqual({e['condition'] for e in make_manifest(tasks_for('diagnostic'),'diagnostic',123)},{'A'})

    def test_exposure_is_not_assumed_from_late_start_or_calibration(self):
        result={'budget_s':100,'shift_fraction':.2,'events':[
            {'event_type':'tool','tool_name':'search','step_index':0,'tool_start_offset_s':21,
             'tool_end_offset_s':36,'observed_duration_s':15},
            {'event_type':'model_request','step_index':1,'request_start_offset_s':37,
             'action':{'type':'submit','answer':{'value':1,'evidence_ids':[]}}}],
            'valid_submission':True,'final_answer':{'value':1,'evidence_ids':[]}}
        self.assertEqual(observations(result),(True,False,True))
        result['events'].insert(0,{'event_type':'tool','tool_name':'search','tool_start_offset_s':1,
            'tool_end_offset_s':3,'observed_duration_s':2})
        self.assertEqual(observations(result),(True,True,True))
        result['events'][1]['is_censored']=True
        self.assertEqual(observations(result),(False,False,False))

    def test_two_workers_own_separate_whole_paired_blocks(self):
        manifest=make_manifest(tasks_for('development'),'development',123)
        queues=block_queues(manifest);model=MODELS[0]
        one,two=take_entries(queues,model),take_entries(queues,model)
        a,b=next(one),next(two)
        key=lambda e:(e['task_id'],e['profile'],e['repeat'])
        self.assertNotEqual(key(a),key(b))
        a_block=[a,next(one),next(one)];b_block=[b,next(two),next(two)]
        self.assertEqual({key(e) for e in a_block},{key(a)})
        self.assertEqual({e['condition'] for e in a_block},set('ABC'))
        rest=list(one)+list(two)
        all_entries=a_block+b_block+rest
        self.assertEqual(len(all_entries),72)
        self.assertEqual(len({e['run_id'] for e in all_entries}),72)


if __name__=='__main__': unittest.main()
