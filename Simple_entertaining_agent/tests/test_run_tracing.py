"""Check trace persistence, partial usage, and evaluation scoring offline."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from Simple_entertaining_agent.run_tracing import TraceHooks, record_route, trace_turn, tool_error
from Simple_entertaining_agent.evaluate_routing import CASES, summarize


class TraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_usage_and_route_survive_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.jsonl"
            with self.assertRaises(RuntimeError):
                with trace_turn(path):
                    record_route("image", "model")
                    hooks = TraceHooks()
                    await hooks.on_llm_end(None, None, SimpleNamespace(usage=SimpleNamespace(
                        input_tokens=10, output_tokens=4, total_tokens=14)))
                    tool = SimpleNamespace(name="search_cute_images")
                    context = SimpleNamespace(tool_call_id="call-1")
                    await hooks.on_tool_start(context, None, tool)
                    tool_error(context, ValueError("private content"))
                    await hooks.on_tool_end(context, None, tool, "failed")
                    raise RuntimeError("private content")
            trace = json.loads(path.read_text())
            self.assertEqual(trace["routing_decision"], "image")
            self.assertEqual(trace["usage"]["total_tokens"], 14)
            self.assertEqual(trace["status"], "error")
            self.assertEqual(len(trace["tool_calls"]), 1)
            self.assertEqual(len(trace["errors"]), 2)
            self.assertNotIn("private content", path.read_text())
            self.assertGreaterEqual(trace["latency_ms"], 0)

    def test_local_turn_and_context_reset(self):
        with trace_turn(None) as first:
            record_route("quit", "local")
        with trace_turn(None) as second:
            self.assertIsNone(second["routing_decision"])
        self.assertEqual(first["usage"]["total_tokens"], 0)
        self.assertNotEqual(first["run_id"], second["run_id"])

    def test_evaluation_counts_errors_as_incorrect(self):
        rows = [{"category": "typo", "correct": True},
                {"category": "typo", "correct": False, "error": "ConnectionError"}]
        self.assertEqual(summarize(rows)["accuracy"], 0.5)
        self.assertEqual({case[0] for case in CASES},
                         {"standard", "typo", "ambiguous", "multiple"})
