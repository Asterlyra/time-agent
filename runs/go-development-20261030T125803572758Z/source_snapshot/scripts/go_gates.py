"""Evidence-based readiness checks for the API study; never force a CLI gate."""
import hashlib
import json
from pathlib import Path

from scripts.matrix import digest


def check_verification(evidence_path, code_paths):
    from scripts.matrix import code_hash
    evidence_path=Path(evidence_path).resolve()
    evidence=json.loads(evidence_path.read_text())
    if evidence.get('failures')!=0 or evidence.get('errors')!=0 or evidence.get('tests_run',0)<80:
        raise ValueError('offline verification did not pass')
    if evidence.get('code_hash')!=code_hash(code_paths):raise ValueError('verification source changed')
    for file,expected in evidence.get('test_sources',{}).items():
        path=Path(file)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('verified test source changed')
    required={'tests/test_opencode_go.py','tests/test_go_study.py','tests/test_public_answer_audit.py','tests/test_study_statistics.py'}
    if not required<=set(evidence.get('test_sources',{})):raise ValueError('required boundary/statistical tests missing')
    return {'path':str(evidence_path),'sha256':hashlib.sha256(evidence_path.read_bytes()).hexdigest()}


def check_diagnostic(diagnostic):
    from scripts.go_study import analyze,tasks_for,ROOT
    # A completed diagnostic may precede orchestration/reporting changes. Its
    # exact archived source must match its frozen hash, and all decision/runtime
    # components must still match the current study. Never resume with old code.
    diag_path=Path(diagnostic).resolve()
    diag_config=json.loads((diag_path/'config.json').read_text())
    diag_manifest=json.loads((diag_path/'manifest.json').read_text())
    archived=json.loads((diag_path/'source_snapshot_hashes.json').read_text())
    for source,expected in archived.items():
        file=diag_path/'source_snapshot'/Path(source).relative_to(ROOT)
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:raise ValueError('diagnostic source snapshot changed')
    if (digest(archived)!=diag_config['code_hash'] or digest(diag_config)!=json.loads((diag_path/'config_hash.json').read_text())['sha256']
            or digest(diag_manifest)!=diag_config['manifest_hash'] or digest(tasks_for('diagnostic'))!=diag_config['task_hash']):
        raise ValueError('historical diagnostic integrity mismatch')
    for source,expected in archived.items():
        rel=Path(source).relative_to(ROOT).as_posix()
        if rel.startswith(('src/','tasks/')) or rel=='scripts/run_diagnostic.py':
            if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=expected:raise ValueError('diagnostic runtime differs from study')
    diag=analyze(diag_path,verify=False)
    if diag_config['stage']!='diagnostic' or not diag['ready_for_next_stage']:
        raise ValueError('three-model diagnostic has not passed')
    return diag_path,diag_config


def check_formal_readiness(development,diagnostic,verification,code_paths):
    from scripts.go_study import analyze,load_batch
    from scripts.audit_public_answers import audit
    boundary=check_verification(verification,code_paths)
    dev_path,dev_config,_=load_batch(development)
    diag_path,diag_config=check_diagnostic(diagnostic)
    dev=analyze(dev_path)
    if dev_config['stage']!='development' or not dev['ready_for_next_stage']:
        raise ValueError('complete development matrix has not passed all quality gates')
    if dev_config['model_settings']!=diag_config['model_settings']:
        raise ValueError('diagnostic and development model settings differ')
    answers=audit()
    if not answers['pass']:raise ValueError('independent public answer audit failed')
    return {'verification':boundary,'diagnostic_batch':str(diag_path),'diagnostic_config_hash':digest(diag_config),
        'development_batch':str(dev_path),'development_config_hash':digest(dev_config),
        'public_answer_audit':{'pass':True,'dev':answers['splits']['dev']['n'],'test':answers['splits']['test']['n'],
                               'method':answers['method'],'human_review':False},
        'primary':'fast_to_slow C-B deadline success, paired task-cluster bootstrap',
        'preserve_failures':True,'no_cli_gate_bypass':True}
