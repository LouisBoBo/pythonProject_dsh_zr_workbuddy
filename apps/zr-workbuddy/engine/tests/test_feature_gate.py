"""feature 启停门闸：面板 chat / CLI ask 须尊重 plugins.json。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest import mock

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class FeatureGateTests(unittest.TestCase):
    def test_chat_blocks_when_mes_ask_disabled(self):
        from app import cli_ops
        from app import plugins_store

        async def _run():
            with mock.patch.object(plugins_store, "is_enabled", side_effect=lambda fid: fid != "mes-ask"):
                # PCB 仍可用时，非 PCB 问题不得查数
                return await cli_ops.chat("今天正在生产的工单有多少个")

        out = asyncio.run(_run())
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("source"), "disabled")
        self.assertIn("mes-ask", out.get("reply") or "")
        self.assertNotIn("工单", (out.get("reply") or "")[:20])  # 不是查数结果开头

    def test_ask_cli_blocks_when_disabled(self):
        from app import cli_ops
        from app import plugins_store

        async def _run():
            with mock.patch.object(plugins_store, "is_enabled", return_value=False):
                return await cli_ops.run_async("ask", ["今天产量多少"])

        out = asyncio.run(_run())
        self.assertEqual(out.get("source"), "disabled")
        self.assertIn("mes-ask", (out.get("reply") or out.get("detail") or ""))

    def test_config_cli_blocks_when_disabled(self):
        from app import cli_ops
        from app import plugins_store

        async def _run():
            with mock.patch.object(plugins_store, "is_enabled", return_value=False):
                return await cli_ops.run_async("status", [])

        out = asyncio.run(_run())
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("source"), "disabled")
        self.assertIn("mes-config", out.get("detail") or "")

    def test_chat_stream_blocks_mes_ask(self):
        from app import cli_ops
        from app import plugins_store

        async def _run():
            events = []
            with mock.patch.object(plugins_store, "is_enabled", side_effect=lambda fid: fid == "mes-pcb"):
                async for ev in cli_ops.chat_stream("最近7天各产线产量对比"):
                    events.append(ev)
            return events

        events = asyncio.run(_run())
        types = [e.get("type") for e in events]
        self.assertIn("done", types)
        done = next(e for e in events if e.get("type") == "done")
        self.assertEqual(done.get("source"), "disabled")
        self.assertIn("mes-ask", done.get("reply") or "")


if __name__ == "__main__":
    unittest.main()
