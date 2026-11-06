import unittest
from scripts.mechanism_probe import conditions


class PrefixTests(unittest.TestCase):
    def test_only_references_change_and_future_metadata_is_not_added(self):
        observation={'question':'public','tools':{'search':{}},'calibration_samples_s':{'search':[2,2,2]},
            'time_status':{'budget_s':150,'elapsed_s':40,'remaining_s':110},'duration_reference_s':{'search':999},
            'duration_reference_description':'old'}
        history=[{'action':{'type':'tool','name':'search','arguments':{'query':str(i)}},'tool_result':{},'duration_s':v} for i,v in enumerate((2,2,15))]
        result=conditions(observation,history)
        self.assertNotIn('duration_reference_s',result['A'])
        self.assertEqual(result['B']['duration_reference_s'],{'search':2})
        self.assertAlmostEqual(result['C']['duration_reference_s']['search'],19/3)
        for value in result.values():
            self.assertEqual(value['time_status'],{'budget_s':180,'elapsed_s':120,'remaining_s':60})
            self.assertEqual(value['question'],'public')
            self.assertNotIn('profile',value)
        self.assertEqual(observation['duration_reference_s'],{'search':999})

    def test_invalid_history_does_not_become_a_completed_duration(self):
        observation={'question':'q','tools':{'search':{}},'calibration_samples_s':{'search':[2]*3}}
        history=[{'action':{'type':'tool','name':'search'},'error':'invalid','duration_s':999}]
        self.assertEqual(conditions(observation,history)['C']['duration_reference_s'],{'search':2})


if __name__=='__main__':unittest.main()
