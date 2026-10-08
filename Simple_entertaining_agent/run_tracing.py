"""Local JSONL traces; context variables isolate concurrent conversations."""

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from agents import RunHooks

TRACE_PATH = Path(__file__).with_name("db") / "runs.jsonl"
_active = ContextVar("entertainment_trace", default=None)


def record_route(decision, source):
    trace = _active.get()
    if trace is not None:
        trace["routing_decision"] = decision
        trace["routing_source"] = source


def record_selected_action(action):
    trace = _active.get()
    if trace is not None:
        trace["selected_action"] = action


def tool_error(context, error):
    """Record errors that the SDK converts to a tool response for the model."""
    trace = _active.get()
    if trace is not None:
        trace["errors"].append({"type": type(error).__name__, "source": "tool"})
    return "Image search failed. Try another search or return no image."


class TraceHooks(RunHooks):
    """Capture usage as responses arrive, even if a later tool fails."""

    async def on_agent_start(self, context, agent):
        trace = _active.get()
        if trace is not None:
            trace["agent_steps"].append({"name": agent.name, "status": "started"})

    async def on_agent_end(self, context, agent, output):
        trace = _active.get()
        if trace is not None:
            for step in reversed(trace["agent_steps"]):
                if step["name"] == agent.name and step["status"] == "started":
                    step["status"] = "completed"
                    break

    async def on_llm_end(self, context, agent, response):
        trace = _active.get()
        if trace is not None:
            for name in trace["usage"]:
                trace["usage"][name] += getattr(response.usage, name, 0) or 0
            trace["model_responses"] += 1

    async def on_tool_start(self, context, agent, tool):
        trace = _active.get()
        if trace is not None:
            trace["tool_calls"].append({
                "name": tool.name,
                "call_id": getattr(context, "tool_call_id", None),
                "status": "started",
            })

    async def on_tool_end(self, context, agent, tool, result):
        trace = _active.get()
        if trace is not None:
            call_id = getattr(context, "tool_call_id", None)
            for call in reversed(trace["tool_calls"]):
                if call["name"] == tool.name and call["call_id"] == call_id:
                    call["status"] = "completed"
                    break


@contextmanager
def trace_turn(path=TRACE_PATH):
    """Write one record in finally; logging failures never replace a reply."""
    trace = {
        "run_id": uuid4().hex,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "routing_decision": None,
        "routing_source": None,
        "selected_action": None,
        "agent_steps": [],
        "tool_calls": [],
        "errors": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "model_responses": 0, "status": "ok",
    }
    token = _active.set(trace)
    started = perf_counter()
    try:
        yield trace
    except BaseException as error:
        trace["status"] = "error"
        # Exception messages can contain credentials or user content.
        trace["errors"].append({"type": type(error).__name__})
        raise
    finally:
        trace["latency_ms"] = round((perf_counter() - started) * 1000, 3)
        _active.reset(token)
        if path is not None:
            try:
                destination = Path(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(trace) + "\n")
            except OSError:
                logging.getLogger(__name__).exception("Could not write run trace")
