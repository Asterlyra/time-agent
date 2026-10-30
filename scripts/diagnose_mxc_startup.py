"""Classify CLI startup failures without emitting stderr, secrets, or environment."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import re

from src.adapters.codex_mxc import _DISABLED_FEATURES
from src.adapters.codex_mxc_v2 import CodexMXCV2, minimal_environment


def classify(text):
    text = text.lower()
    categories = {
        'auth': ('unauthorized', 'authentication', 'not logged in', 'please log in', 'invalid api key', '401'),
        'permission': ('access is denied', 'permission denied', 'os error 5', '拒绝访问'),
        'network': ('connection refused', 'connection reset', 'dns', 'network error', 'timed out', 'failed to connect'),
        'rate_limit': ('rate limit', 'too many requests', '429'),
        'config': ('invalid configuration', 'invalid config', 'failed to parse', 'unknown field', 'unknown feature'),
        'model': ('model not found', 'unsupported model', 'model does not exist'),
        'environment': ('environment variable', 'userprofile', 'home directory', 'home not set', 'path not found'),
        'sandbox': ('sandbox', 'mxc', '沙箱'),
        'generic_error': ('error', 'failed', 'exception', '错误', '失败'),
        'executable': ('executable', 'command not found', 'no such file', '找不到'),
        'proxy': ('proxy', 'certificate', 'tls', 'ssl'),
        'sandbox_init': ('sandbox initialization', 'sandbox setup', 'initialize sandbox', 'failed to initialize', 'failed to create sandbox'),
        'missing_path': ('no such file', 'not found', 'cannot find', 'does not exist', '找不到', '系统找不到'),
        'bad_profile': ('permissions.', 'permission profile', 'default_permissions', 'profile not found', 'profile is invalid'),
        'runtime': ('runtime', 'executable', 'spawn', 'process'),
        'windows_user': ('appcontainer', 'sid', 'user token', 'logon', 'user profile', '用户配置文件'),
        'policy': ('policy', 'policies', '权限', '策略'),
        'invalid': ('invalid', 'unsupported', 'unknown', 'incompatible', 'not supported', '无效', '不支持'),
        'required': ('required', 'must', 'missing', 'require', '必须', '缺少'),
        'sandbox_exec': ('sandbox-exec', 'sandbox exec', 'codex sandbox', 'command sandbox'),
        'capability': ('capability', 'capabilities', 'feature flag', '功能'),
        'config_file': ('config.toml', 'configuration', 'config file', '配置'),
        'authentication': ('auth.json', 'credential', 'token', '凭据', '认证'),
        'windows_sandbox': ('windows.sandbox', 'windows sandbox', 'windows_sandbox'),
        'sandbox_permission': ('sandbox permission', 'sandbox_permissions', 'sandbox permissions'),
        'managed': ('managed', 'admin', 'administrator', '管理员'),
        'process_start': ('start process', 'launch', 'starting', 'startup'),
        'execution': ('execute', 'execution', 'exec'),
        'network_access': ('network', 'internet', 'firewall', '网络'),
        'home': ('home', 'homedir', 'userprofile'),
        'stderr_io': ('stderr', 'stdout', 'stdio', 'stdin'),
    }
    return [name for name, markers in categories.items() if any(term in text for term in markers)]


def required_subjects(text):
    text = text.lower()
    subjects = {
        'profile': r'profile|permissions', 'elevated': r'elevated|administrator|admin',
        'package': r'package|appcontainer', 'environment': r'environment|variable',
        'network': r'network|internet|proxy', 'authentication': r'auth|credential|login|token',
        'sandbox': r'sandbox|mxc', 'platform': r'windows|operating system|platform',
        'permission': r'permission|approv|access', 'runtime': r'runtime|executable|process',
    }
    requirement = r'required|requires|require|must|needs|necessary'
    return [name for name, pattern in subjects.items()
            if re.search(rf'(?:{requirement}).{{0,80}}(?:{pattern})|(?:{pattern}).{{0,80}}(?:{requirement})', text)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-runtime-package', action='store_true')
    opts = parser.parse_args()
    model = CodexMXCV2(denied_roots=[str(Path.cwd())])
    env = minimal_environment()
    if opts.include_runtime_package and 'CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY' in os.environ:
        env['CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY'] = os.environ['CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY']
    with tempfile.TemporaryDirectory(prefix='codex-startup-diagnostic-') as root:
        args = [model.executable, 'exec', '--model', model.model, *model._sandbox_args(root),
                '--skip-git-repo-check', '--ephemeral', '--ignore-user-config',
                *[arg for feature in _DISABLED_FEATURES for arg in ('--disable', feature)],
                '-c', 'web_search="disabled"', '--json', '--cd', root, '-']
        try:
            proc = subprocess.run(args, input=b'Return exactly {"type":"submit","answer":{}}. Do not use tools.',
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=45,
                                  cwd=root, check=False)
        except subprocess.TimeoutExpired:
            print(json.dumps({'timeout': True, 'stderr_categories': None, 'json_event_types': []}))
            return
        event_types = []
        for line in proc.stdout.splitlines():
            try:
                e = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                event_types.append('unparseable'); continue
            # Never print event bodies, item contents, request IDs or messages.
            t = e.get('type') if isinstance(e, dict) else None
            allowed = {'thread.started', 'turn.started', 'turn.completed', 'turn.failed', 'error',
                       'item.started', 'item.completed', 'item.updated'}
            event_types.append(t if t in allowed else 'other')
        error = proc.stderr.decode('utf-8', errors='replace')
        print(json.dumps({'exit_code': proc.returncode, 'stderr_length': len(proc.stderr), 'stdout_length': len(proc.stdout),
                          'stderr_categories': classify(error), 'required_subjects': required_subjects(error),
                          'json_event_types': event_types}, ensure_ascii=False))


if __name__ == '__main__':
    main()
