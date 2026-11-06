import unittest
from scripts.advance_go_study import calibration_revision


class CalibrationPolicyTests(unittest.TestCase):
    def report(self,gate):
        return {'completed':216,'planned':216,'missing':[],'service_or_protocol_failures':0,
                'service_flagged_episodes':0,'gates':[{**gate,'pass':False}],'cells':object()}

    def config(self):return {'budget_s':180,'shift_fraction':1/15}

    def test_pooled_ceiling_reduces_budget_without_condition_scores(self):
        r=self.report({'check':'primary_outcome_variability','n':24,'success':24})
        revision,reason=calibration_revision(r,self.config())
        self.assertEqual(revision['budget'],150)
        self.assertAlmostEqual(revision['budget']*revision['shift'],12)

    def test_pooled_floor_increases_common_budget(self):
        r=self.report({'check':'primary_outcome_variability','n':24,'success':0})
        self.assertEqual(calibration_revision(r,self.config())[0]['budget'],210)

    def test_missing_phase_feedback_moves_change_without_using_both_phase_count(self):
        r=self.report({'check':'change_opportunity','n':12,'exposed':8,'post_shift_valid_action':8,'same_tool_both_phases':0})
        revision,_=calibration_revision(r,self.config())
        self.assertEqual(revision['budget'],180)
        self.assertAlmostEqual(revision['budget']*revision['shift'],6)

    def test_conflicting_models_do_not_trigger_parameter_sweep(self):
        r=self.report({'check':'primary_outcome_variability','n':24,'success':24})
        r['gates'].append({'check':'primary_outcome_variability','n':24,'success':0,'pass':False})
        self.assertEqual(calibration_revision(r,self.config()),(None,'conflicting_cross_model_budget_requirements'))

    def test_correctness_failure_does_not_get_treated_as_a_time_problem(self):
        r=self.report({'check':'basic_solvability','n':12,'success':2})
        self.assertEqual(calibration_revision(r,self.config())[0],None)

    def test_incomplete_or_service_failure_never_restarts(self):
        r=self.report({'check':'primary_outcome_variability','n':24,'success':24})
        r['missing']=['pending']
        self.assertEqual(calibration_revision(r,self.config())[0],None)
        r['missing']=[];r['service_or_protocol_failures']=1
        self.assertEqual(calibration_revision(r,self.config())[0],None)


if __name__=='__main__':unittest.main()
