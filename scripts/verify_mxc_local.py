"""Local canary checks only: no model, network request, or secret disclosure.

This checks one standalone MXC sandbox command, not Codex's model execution
chain. It passes an explicit environment allowlist, not the full environment.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

SAFE_ENV = {'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'PATH',
            'USERPROFILE', 'LOCALAPPDATA', 'APPDATA'}


def main():
    env = {k: v for k, v in os.environ.items() if k.upper() in SAFE_ENV}
    cli = os.environ['CODEX_APP_RUNTIME_CLI_PATH']
    with tempfile.TemporaryDirectory(prefix='mxc-local-canary-', dir='runs') as root:
        path = Path(root).resolve() / 'canary.txt'
        marker = b'LOCAL_NON_SECRET_CANARY'
        path.write_bytes(marker)
        results = {}
        for label in ('control', 'denied'):
            deny = ',' + json.dumps(path.as_posix()) + '="deny"' if label == 'denied' else ''
            setting = 'permissions.localprobe.filesystem={":root"="read"' + deny + '}'
            args = [cli, '-c', 'windows.sandbox="mxc"', '-c', setting,
                    'sandbox', '--include-managed-config', '--permission-profile', 'localprobe',
                    '--', str(Path(env['SYSTEMROOT'])/'System32'/'cmd.exe'), '/d', '/c', 'type', str(path)]
            try:
                proc = subprocess.run(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                output = (proc.stdout + proc.stderr).lower()
                denial = any(token in output for token in (b'access is denied', b'permission denied',
                             '拒绝访问'.encode('utf-8'), '拒绝访问'.encode('gbk')))
                results[label] = {'exit_code': proc.returncode, 'marker_visible': marker in proc.stdout,
                                  'stderr_has_sandbox': b'sandbox' in proc.stderr.lower(),
                                  'denial_message': denial}
            except subprocess.TimeoutExpired:
                results[label] = {'timeout': True}
        results['contrast_pass'] = (results['control'].get('exit_code') == 0
                                    and results['control'].get('marker_visible') is True
                                    and results['denied'].get('exit_code') not in (None, 0)
                                    and results['denied'].get('marker_visible') is False
                                    and results['denied'].get('denial_message') is True)
        results['scope'] = 'standalone sandbox only; not model or end-to-end isolation'
        print(json.dumps(results))


if __name__ == '__main__':
    main()
