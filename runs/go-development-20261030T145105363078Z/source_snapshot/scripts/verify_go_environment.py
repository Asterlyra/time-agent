"""Run offline verification and persist exact code/test hashes without secrets."""
import datetime
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

from scripts.go_study import CODE_PATHS
from scripts.matrix import code_hash,write_new


def main():
    command=[sys.executable,'-m','unittest','discover','-s','tests','-q']
    result=subprocess.run(command,capture_output=True,text=True)
    text=result.stdout+result.stderr
    print(text,end='')
    if result.returncode:raise SystemExit(result.returncode)
    match=re.search(r'Ran (\d+) tests',text)
    if not match or 'OK' not in text:raise SystemExit('unrecognized verification result')
    report={'recorded_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'python':platform.python_version(),'command':command,'tests_run':int(match.group(1)),
        'failures':0,'errors':0,'skipped':int(re.search(r'skipped=(\d+)',text).group(1)) if 'skipped=' in text else 0,
        'code_hash':code_hash(CODE_PATHS),'test_sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('tests').glob('test_*.py'))},
        'method':'actual unittest subprocess; mocked HTTP boundary and cancellation; independent public-answer oracle; paired statistics tests',
        'limitations':['Does not claim Windows CLI OS isolation or control over provider internals','HTTP cancellation is client-side; remote discarded generation may still consume allowance']}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=Path('reports')/('go_verification-'+stamp+'.json');write_new(output,report);print(output)


if __name__=='__main__':main()
