import asyncio, json, os
from src.adapters.codex_cli import CodexCLI
async def main():
 m=CodexCLI(isolation='mxc',denied_roots=[os.getcwd()])
 try: print('action',json.dumps(await m.decide({'question':'Give a submit action with value 2 and empty evidence_ids.'},[])))
 except Exception as e: print('error',type(e).__name__)
 print('events',m.event_history)
asyncio.run(main())
