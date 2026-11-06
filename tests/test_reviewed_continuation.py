import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import go_study
from scripts import resume_go_after_suspend as resume
from scripts.matrix import digest


class ReviewedContinuationTests(unittest.TestCase):
    def test_sampling_logic_matches_frozen_driver_except_review_and_provenance(self):
        original=ast.parse(inspect.getsource(go_study.execute)).body[0]
        revised=ast.parse(inspect.getsource(resume.execute_reviewed)).body[0]
        revised.name=original.name;revised.args=copy.deepcopy(original.args)
        class Normalize(ast.NodeTransformer):
            def visit_If(self,node):
                if (isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Subscript)
                        and ast.unparse(node.test.left)=="r['termination_reason']"):
                    return ast.copy_location(ast.Pass(),node)
                return self.generic_visit(node)
            def visit_Dict(self,node):
                pairs=[(k,v) for k,v in zip(node.keys,node.values) if not (isinstance(k,ast.Constant)
                    and k.value in ('continuation_driver_sha256','continuation_review_sha256'))]
                node.keys=[k for k,v in pairs];node.values=[v for k,v in pairs]
                return self.generic_visit(node)
        self.assertEqual(ast.dump(Normalize().visit(original),include_attributes=False),
                         ast.dump(Normalize().visit(revised),include_attributes=False))

    def fixture(self,root):
        config={'stage':'formal','readiness_evidence':{'development_batch':'dev','diagnostic_batch':'diag',
            'verification':{'path':'verification'}}}
        entry={'run_id':'one'};result={'metadata':{'config_hash':digest(config)},
            'termination_reason':'environment_interruption','deadline_success':False,'valid_submission':False,
            'suspend_gap_s':10,'infrastructure_error_flags':[{'type':'host_suspend'}]}
        (root/'episodes').mkdir();path=root/'episodes/one.json';path.write_text(json.dumps({'manifest':entry,'result':result}))
        (root/'runtime_state.json').write_text(json.dumps({'pid':999999,'state':'halted'}))
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        review={'config_hash':digest(config),'source_sha256':hashlib.sha256(Path(resume.__file__).read_bytes()).hexdigest(),
            'resolved_environment_ids':['one'],'result_hashes':{'one':sha},'original_completed':1,
            'immutable_file_hashes':{'episodes/one.json':sha}}
        return config,entry,path,review

    def test_only_reviewed_immutable_environment_records_can_be_continued(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config,entry,path,review=self.fixture(root)
            with patch.object(resume,'load_batch',return_value=(root,config,[entry])), \
                 patch.object(resume.os,'kill',side_effect=ProcessLookupError), \
                 patch.object(resume,'check_formal_readiness',return_value=config['readiness_evidence']):
                self.assertEqual(resume.validate_review(root,review),root)
                row=json.loads(path.read_text());row['result']['deadline_success']=True
                path.write_text(json.dumps(row))
                with self.assertRaises(ValueError):resume.validate_review(root,review)

    def test_service_fault_and_live_pid_are_not_waived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config,entry,path,review=self.fixture(root)
            with patch.object(resume,'load_batch',return_value=(root,config,[entry])):
                with patch.object(resume.os,'kill',return_value=None):
                    with self.assertRaises(ValueError):resume.validate_review(root,review)
                row=json.loads(path.read_text());row['result']['termination_reason']='service_error'
                path.write_text(json.dumps(row));sha=hashlib.sha256(path.read_bytes()).hexdigest()
                review['result_hashes']['one']=sha;review['immutable_file_hashes']['episodes/one.json']=sha
                with patch.object(resume.os,'kill',side_effect=ProcessLookupError):
                    with self.assertRaises(ValueError):resume.validate_review(root,review)


if __name__=='__main__':unittest.main()
