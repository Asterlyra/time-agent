import json,os,subprocess,tempfile,sys
from src.adapters.codex_mxc_v2 import minimal_environment
cli=os.environ['CODEX_APP_RUNTIME_CLI_PATH']
env=minimal_environment()
if '--without-system-drive' not in sys.argv and 'SystemDrive' in os.environ: env['SystemDrive']=os.environ['SystemDrive']
with tempfile.TemporaryDirectory(prefix='sandbox-check-') as folder:
    p=subprocess.run([cli,'-c','windows.sandbox="mxc"','-c','permissions.sample.filesystem={":root"="read"}','sandbox','--permission-profile','sample','--cd',folder,'--','cmd.exe','/d','/c','echo SANDBOX_OK'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    print(json.dumps({'system_drive_present': 'SystemDrive' in env, 'exit_code':p.returncode,'success_marker':b'SANDBOX_OK' in p.stdout}))
