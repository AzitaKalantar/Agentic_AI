"""Shared database path and task-specific conversation IDs."""
from pathlib import Path
from typing import Literal

Task = Literal["jokes", "puzzles", "facts"]
DB_DIR = Path(__file__).resolve().parent / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "entertainment_history.db"


def task_session_id(session_id: str, task: Task) -> str:
    """Combine a base user/session ID and a task."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a nonempty string.")
    if task not in ("jokes", "puzzles", "facts"):
        raise ValueError("task must be 'jokes', 'puzzles', or 'facts'.")
    return f"{session_id.strip()}:{task}"
