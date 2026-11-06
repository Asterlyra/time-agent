import unittest
from scripts.study_statistics import primary_statistics


class StatisticsTests(unittest.TestCase):
    def fixture(self):
        manifest=[];rows=[]
        for model in ('one','two','three'):
            for task in range(4):
                for repeat in range(2):
                    for condition in 'ABC':
                        e={'model_id':model,'task_id':str(task),'task_family':'evidence' if task<2 else 'table',
                           'repeat':repeat,'condition':condition,'profile':'fast_to_slow','run_id':f'{model}-{task}-{repeat}-{condition}'}
                        manifest.append(e);rows.append({'manifest':e,'result':{'deadline_success':condition=='C'}})
        return manifest,rows

    def test_pairing_and_fixed_model_mean(self):
        manifest,rows=self.fixture();result=primary_statistics(manifest,rows,iterations=100)
        self.assertEqual(result['point']['equal_model_mean'],1)
        self.assertEqual(result['bootstrap_95_percentile']['equal_model_mean'],[1,1])
        self.assertEqual(result['task_clusters'],4)
        self.assertEqual(result['task_strata'],{'evidence':2,'table':2})

    def test_no_selected_complete_case_primary_estimate(self):
        manifest,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'complete planned matrix'):primary_statistics(manifest,rows[:-1])


if __name__=='__main__':unittest.main()
