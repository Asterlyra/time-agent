import os, subprocess, tempfile
from pathlib import Path
exe=os.environ['CODEX_APP_RUNTIME_CLI_PATH']
root=Path('runs').resolve()
with tempfile.TemporaryDirectory(prefix='mxc_canary_',dir=root) as tmp:
 f=Path(tmp)/'marker.txt'
 f.write_text('MXC_CANARY_123',encoding='utf-8')
 target=f.as_posix()
 for label,fs in [('control','{":root"="read"}'), ('deny', '{":root"="read", "'+target+'"="deny"}')]:
  cmd=[exe,'-c','windows.sandbox="mxc"','-c','model_reasoning_effort="medium"','-c','permissions.canary.filesystem='+fs,'sandbox','--permission-profile','canary','--','cmd.exe','/d','/c','type',str(f)]
  try:
   p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='gbk',errors='replace',timeout=30)
   print(label,'exit',p.returncode,'marker_visible', 'MXC_CANARY_123' in p.stdout,'stderr',ascii(p.stderr[-500:]))
  except Exception as e: print(label,'error',type(e).__name__)


