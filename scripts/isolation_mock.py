"""Local, credential-free environment minimization demonstration.

This does not invoke Codex, any model, any network service, or OS sandbox.
It intentionally demonstrates that sanitized variables do not isolate files.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def minimal_environment(source):
    # Windows needs SystemRoot for loading system components. No other inherited
    # variables, credentials, app-control pipes, PATH or proxies are passed.
    allowed = {'SYSTEMROOT', 'WINDIR'} if os.name == 'nt' else set()
    return {k: v for k, v in source.items() if k.upper() in allowed}


def check():
    parent = dict(os.environ)
    parent['CODEX_ISOLATION_FAKE_SECRET'] = 'synthetic-not-a-credential'
    env = minimal_environment(parent)
    child = ('import json,os,pathlib,sys; '
             'p=pathlib.Path(sys.argv[1]); '
             'print(json.dumps({"fake_secret_absent": "CODEX_ISOLATION_FAKE_SECRET" not in os.environ, '
             '"canary_readable_without_os_isolation": p.read_text(encoding="utf8") == "public-fake-canary"}))')
    scratch = Path(__file__).resolve().parent.parent / 'runs'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='isolated-env-mock-', dir=scratch) as root:
        canary = Path(root) / 'fake-canary.txt'
        canary.write_text('public-fake-canary', encoding='utf8')
        run = subprocess.run([sys.executable, '-I', '-c', child, str(canary)], cwd=root, env=env,
                             capture_output=True, text=True, check=True, timeout=10)
        result = json.loads(run.stdout)
    if result != {'fake_secret_absent': True, 'canary_readable_without_os_isolation': True}:
        raise AssertionError('local simulation failed')
    return result


if __name__ == '__main__':
    print(json.dumps(check(), sort_keys=True))
