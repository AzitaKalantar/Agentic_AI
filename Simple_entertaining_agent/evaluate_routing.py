"""Evaluate the actual router without running costly specialist activities.

Run from the repository root: python -m Simple_entertaining_agent.evaluate_routing
"""

import asyncio
import json
from collections import defaultdict
from pathlib import Path

from agents import Runner

from .entertainment_manager import EntertainmentManager
from .run_tracing import TraceHooks, record_route, trace_turn

CASES = [
    ("standard", "Tell me a joke", "joke"),
    ("standard", "Give me a one-word puzzle", "puzzle"),
    ("standard", "Share a fun fact", "fact"),
    ("standard", "Show me a cute kitten picture", "image"),
    ("standard", "Surprise me", "surprise"),
    ("standard", "I would like to leave now", "quit"),
    ("typo", "tell me a joek", "joke"),
    ("typo", "a puzzel please", "puzzle"),
    ("typo", "fun facct plese", "fact"),
    ("typo", "show a cute immage", "image"),
    ("ambiguous", "Entertain me", "chat"),
    ("ambiguous", "Something interesting please", "chat"),
    ("ambiguous", "Hello", "chat"),
    ("multiple", "Tell me a joke and a fact", "chat"),
    ("multiple", "A puzzle and a kitten image please", "chat"),
    ("multiple", "Give me all four activities", "chat"),
]


def summarize(rows):
    """Errors count as incorrect so failures cannot inflate accuracy."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    return {
        "total": len(rows),
        "correct": sum(row["correct"] for row in rows),
        "accuracy": sum(row["correct"] for row in rows) / len(rows) if rows else 0,
        "by_category": {
            name: {"total": len(group), "correct": sum(r["correct"] for r in group),
                   "accuracy": sum(r["correct"] for r in group) / len(group)}
            for name, group in groups.items()
        },
        "cases": rows,
    }


async def evaluate():
    manager = EntertainmentManager("routing-evaluation", temporary=True)
    rows = []
    try:
        for category, prompt, expected in CASES:
            row = {"category": category, "prompt": prompt, "expected": expected,
                   "actual": None, "correct": False}
            with trace_turn() as trace:
                try:
                    # Every case starts with empty context for a fair comparison.
                    result = await Runner.run(manager._agent,
                                              [{"role": "user", "content": prompt}],
                                              hooks=TraceHooks())
                    row["actual"] = result.final_output.action
                    row["correct"] = row["actual"] == expected
                    record_route(row["actual"], "evaluation")
                except Exception as error:
                    row["error"] = type(error).__name__
                    trace["status"] = "error"
                    trace["errors"].append({"type": type(error).__name__})
            row["run_id"] = trace["run_id"]
            row["latency_ms"] = trace["latency_ms"]
            row["usage"] = trace["usage"]
            rows.append(row)
    finally:
        await manager.close()
    report = summarize(rows)
    report["model"] = manager._agent.model
    destination = Path(__file__).with_name("db") / "routing_evaluation.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, indent=2))
    print(f"Per-prompt results: {destination}")


if __name__ == "__main__":
    asyncio.run(evaluate())
