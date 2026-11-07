from __future__ import annotations
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
import ai.tests.bootstrap_pc  # noqa: F401
from ai.mcp import host

class Stream:
  def __init__(self):
    self.n = 0
  async def readline(self):
    self.n += 1
    return (f'{"{"}jsonrpc":"2.0","id":{self.n},"result":{ "{"}tools":[] if self.n == 2 else {"ok":true}{"}" if False else "}"}\n').encode()

class Proc:
  def __init__(self):
    self.returncode = None
    self.stdin = Mock()
    self.stdin.write = Mock()
    self.stdin.drain = AsyncMock()
    self.stdout = AsyncMock()
    self.stdout.readline.side_effect = [b'{"jsonrpc":"2.0","id":1,"result":{}}\n', b'{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n', b'{"jsonrpc":"2.0","id":3,"result":{"ok":true}}\n']
  def kill(self): self.returncode = -9
  async def wait(self): self.returncode = -9

class LifecycleTests(unittest.TestCase):
  def setUp(self):
    host._clients.clear(); host._session_locks.clear(); host._session_configs.clear()
  def test_reuse_initialize_and_discover(self):
    proc = Proc()
    with patch('ai.mcp.host.asyncio.create_subprocess_exec', new=AsyncMock(return_value=proc)) as spawn:
      async def run():
        c = host._client_for('s','x','cmd',[],{})
        await c.request('tools/list', {})
        await c.request('tools/call', {'name':'x'})
        self.assertIs(c, host._client_for('s','x','cmd',[],{}))
      asyncio.run(run()); self.assertEqual(spawn.await_count, 1)
      writes = [x.args[0].decode() for x in proc.stdin.write.call_args_list]
      self.assertIn('initialize', writes[0]); self.assertIn('notifications/initialized', writes[1])
  def test_isolation_and_config_close(self):
    p1,p2=Proc(),Proc()
    with patch('ai.mcp.host.asyncio.create_subprocess_exec', new=AsyncMock(side_effect=[p1,p2])) as spawn:
      async def run():
        a=host._client_for('s','a','cmd',[],{}); b=host._client_for('s','b','cmd',[],{})
        await a.request('tools/list',{}); await b.request('tools/list',{})
        self.assertIsNot(a,b); host.close_mcp_session('s','a'); await asyncio.sleep(0)
      asyncio.run(run()); self.assertEqual(spawn.await_count,2)
    old=host._client_for('s','x','cmd',[],{}); new=host._client_for('s','x','cmd2',[],{}); self.assertIsNot(old,new)
  def test_batch_close_keeps_other_session(self):
    async def run():
      first = host._client_for("server-a", "sess", "cmd", [], {})
      second = host._client_for("server-b", "sess", "cmd", [], {})
      other = host._client_for("server-a", "other", "cmd", [], {})
      await host.close_mcp_sessions_for_session("sess")
      for key in (("server-a", "sess"), ("server-b", "sess")):
        self.assertNotIn(key, host._clients)
        self.assertNotIn(key, host._session_configs)
        self.assertNotIn(key, host._session_locks)
      self.assertIn(("server-a", "other"), host._clients)
      self.assertIs(other.proc, None)
      await host.close_mcp_sessions_for_session("sess")
    asyncio.run(run())

  def test_timeout_eof_cleanup_and_denied(self):
    p=Proc(); p.stdout.readline=AsyncMock(side_effect=asyncio.TimeoutError())
    with patch('ai.mcp.host.asyncio.create_subprocess_exec', new=AsyncMock(return_value=p)):
      async def run():
        # D-P0.2: request() retries then surfaces a RuntimeError whose cause is
        # the underlying timeout; the client is still cleaned up (proc is None).
        with self.assertRaises(RuntimeError) as ctx:
          await host._client_for('s','x','cmd',[],{}).request('tools/list',{})
        self.assertIsInstance(ctx.exception.__cause__, asyncio.TimeoutError)
        self.assertIsNone(host._clients[('s','x')].proc)
      asyncio.run(run())
    class P:
      def get(self,k): return '[]'
    self.assertFalse(asyncio.run(host.call_mcp_tool(P(),server_id='none',tool_name='x'))['ok'])

if __name__ == '__main__': unittest.main()
