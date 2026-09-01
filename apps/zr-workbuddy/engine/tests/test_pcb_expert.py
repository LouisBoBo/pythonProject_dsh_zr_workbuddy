"""PCB 专家问答单元测试（不依赖外网 LLM）。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)

from app.pcb_expert import is_pcb_question, pcb_ask


class PcbExpertTests(unittest.TestCase):
    def test_empty_question(self):
        out = asyncio.run(pcb_ask(""))
        self.assertFalse(out.get("ok"))
        self.assertIn("不能为空", out.get("detail") or "")

    def test_is_pcb_question(self):
        self.assertTrue(is_pcb_question("PCB有哪些工序"))
        self.assertTrue(is_pcb_question("飞针和 AOI 在短路检测上怎么分工？"))
        self.assertFalse(is_pcb_question("今天完工工单有多少个"))
        self.assertFalse(is_pcb_question("最近7天各产线产量对比"))

    def test_split_marked(self):
        from app.pcb_expert import _split_marked, resolve_thinking_reply, split_thinking_reply

        th, rep = _split_marked("<<<思考>>>\n1. 焦点\n<<<回答>>>\n正式答复")
        self.assertIn("焦点", th)
        self.assertIn("正式", rep)
        self.assertNotIn("<<<", th)
        self.assertNotIn("<<<", rep)

        # 流式：只有思考标记时 reply 为空
        th2, rep2 = split_thinking_reply("<<<思考>>>\n1. 焦点\n2. 展开", streaming=True)
        self.assertIn("焦点", th2)
        self.assertEqual(rep2, "")

        # 无标记：整段当回答（新协议：正文即答复）
        th3, rep3 = split_thinking_reply("半截正文", streaming=True)
        self.assertEqual(th3, "")
        self.assertEqual(rep3, "半截正文")

        # 碎片标记不得残留
        th4, rep4 = _split_marked("<<<思考>>>\na\n<<<回答>>>\nb<<<")
        self.assertNotIn("<<<", th4 + rep4)

        # 有原生 reasoning 时，不得被协议思考覆盖
        th5, rep5 = resolve_thinking_reply(
            "<<<思考>>>\n协议思考\n<<<回答>>>\n正式正文",
            "原生推理过程",
            streaming=False,
        )
        self.assertEqual(th5, "原生推理过程")
        self.assertIn("正式", rep5)
        self.assertNotIn("协议", th5)

    def test_pcb_ask_stream_splits_content(self):
        """模拟 LLM 按 token 吐出含标记正文，SSE 不得漏出 <<<…>>>。"""
        from unittest import mock

        from app import pcb_expert

        async def fake_stream(*_a, **_k):
            chunks = [
                "<<<思",
                "考>>>\n1. 焦点\n",
                "<<<回",
                "答>>>\n正式答复正文",
            ]
            for c in chunks:
                yield {"type": "content", "delta": c}
            yield {"type": "done"}

        async def _run():
            events = []
            with mock.patch.object(pcb_expert, "feature_enabled", return_value=True):
                with mock.patch.object(pcb_expert, "load_config", return_value={"deepseek": {"provider": "deepseek", "api_key": "x", "model": "m"}}):
                    with mock.patch.object(pcb_expert, "llm_ready", return_value=True):
                        with mock.patch.object(pcb_expert, "check_net", return_value=True):
                            with mock.patch.object(pcb_expert, "llm_freeform_stream", fake_stream):
                                async for ev in pcb_expert.pcb_ask_stream("PCB有哪些工序"):
                                    events.append(ev)
            return events

        events = asyncio.run(_run())
        blob = ""
        for ev in events:
            if ev.get("type") in ("thinking", "reply"):
                blob += ev.get("text") or ev.get("delta") or ""
            if ev.get("type") == "done":
                blob += (ev.get("thinking") or "") + (ev.get("reply") or "")
                self.assertIn("正式", ev.get("reply") or "")
                self.assertIn("焦点", ev.get("thinking") or "")
                self.assertNotIn("<<<", ev.get("reply") or "")
                self.assertNotIn("<<<", ev.get("thinking") or "")
        self.assertNotIn("<<<", blob)
        self.assertNotIn("思考>>>", blob)
        self.assertNotIn("回答>>>", blob)

    def test_pcb_ask_stream_prefers_native_reasoning(self):
        """原生 reasoning + 协议正文并存时，思考区不得被协议覆盖。"""
        from unittest import mock

        from app import pcb_expert

        async def fake_stream(*_a, **_k):
            yield {"type": "reasoning", "delta": "用户在问工序。"}
            yield {"type": "reasoning", "delta": "按多层板流程答。"}
            for c in ["<<<思考>>>\n1. 协议焦点\n", "<<<回答>>>\n### 一、内层制作\n开料…"]:
                yield {"type": "content", "delta": c}
            yield {"type": "done"}

        async def _run():
            events = []
            with mock.patch.object(pcb_expert, "feature_enabled", return_value=True):
                with mock.patch.object(pcb_expert, "load_config", return_value={"deepseek": {"provider": "deepseek", "api_key": "x", "model": "m"}}):
                    with mock.patch.object(pcb_expert, "llm_ready", return_value=True):
                        with mock.patch.object(pcb_expert, "check_net", return_value=True):
                            with mock.patch.object(pcb_expert, "llm_freeform_stream", fake_stream):
                                async for ev in pcb_expert.pcb_ask_stream("PCB有哪些工序"):
                                    events.append(ev)
            return events

        events = asyncio.run(_run())
        think_texts = [ev.get("text") or "" for ev in events if ev.get("type") == "thinking"]
        self.assertTrue(think_texts)
        # 全程思考应保持原生推理，不被「协议焦点」替换
        for t in think_texts:
            self.assertIn("用户在问工序", t)
            self.assertNotIn("协议焦点", t)
        done = next(ev for ev in events if ev.get("type") == "done")
        self.assertIn("用户在问工序", done.get("thinking") or "")
        self.assertNotIn("协议焦点", done.get("thinking") or "")
        self.assertIn("内层制作", done.get("reply") or "")
        self.assertNotIn("<<<", done.get("reply") or "")

    def test_disabled_feature_blocks_expert(self):
        from unittest import mock

        from app import pcb_expert

        with mock.patch.object(pcb_expert, "feature_enabled", return_value=False):
            out = asyncio.run(pcb_expert.pcb_ask("PCB有哪些工序"))
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("source"), "disabled")
        self.assertIn("已停用", out.get("reply") or "")

    def test_chat_routes_pcb_not_mes(self):
        from app.cli_ops import chat

        async def _run():
            from unittest import mock
            from app import pcb_expert

            fake = {
                "ok": True,
                "reply": "这是 PCB 专家回复",
                "thinking": "先理清工序",
                "source": "llm",
                "domain": "pcb",
            }
            with mock.patch.object(pcb_expert, "pcb_ask", return_value=fake):
                return await chat("PCB有哪些工序")

        out = asyncio.run(_run())
        self.assertEqual(out.get("data_source"), "pcb_expert")
        self.assertIn("PCB 专家", out.get("reply") or "")

    def test_offline_without_llm(self):
        from unittest import mock

        from app import pcb_expert

        with mock.patch.object(pcb_expert, "feature_enabled", return_value=True):
            with mock.patch.object(pcb_expert, "load_config", return_value={"deepseek": {"provider": "none"}}):
                with mock.patch.object(pcb_expert, "llm_ready", return_value=False):
                    out = asyncio.run(pcb_expert.pcb_ask("什么是 IPC-6012？"))
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("source"), "offline")
        self.assertIn("大语言模型", out.get("reply") or "")

    def test_cli_command_registered(self):
        from app.cli_ops import run_async

        out = asyncio.run(run_async("pcb-ask", []))
        self.assertFalse(out.get("ok"))


if __name__ == "__main__":
    unittest.main()
