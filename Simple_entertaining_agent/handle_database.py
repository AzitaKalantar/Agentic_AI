"""Retrieve, export, or clear stored conversation history without displaying it."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import pandas as pd

if __package__:
    from .session_storage import DB_PATH, Task, task_session_id
else:
    from session_storage import DB_PATH, Task, task_session_id


def get_db_tables(db_path: str | Path = DB_PATH) -> dict[str, pd.DataFrame]:
    """Return all rows in both shared SDK tables as DataFrames."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        tables = {
            "agent_sessions": pd.read_sql_query(
                "SELECT * FROM agent_sessions ORDER BY session_id", conn
            ),
            "agent_messages": pd.read_sql_query(
                "SELECT * FROM agent_messages ORDER BY id", conn
            ),
        }
    return tables


def get_db_contents(
    session_id: str, task: Task, db_path: str | Path = DB_PATH
) -> pd.DataFrame:
    """Return all messages chronologically for a base ID/task as a DataFrame."""
    stored_id = task_session_id(session_id, task)
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        history = pd.read_sql_query(
            "SELECT id, session_id, message_data, created_at FROM agent_messages "
            "WHERE session_id = ? ORDER BY id", conn, params=(stored_id,),
        )
    return history


def get_history_json(
    session_id: str,
    task: Task,
    db_path: str | Path = DB_PATH,
) -> str:
    """Return one base ID/task's history as a readable JSON string.

    Includes SQLite row IDs and timestamps, with message_data decoded into
    JSON objects. An empty history exports an empty messages list.
    """
    stored_id = task_session_id(session_id, task)
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        rows = conn.execute(
            "SELECT id, message_data, created_at FROM agent_messages "
            "WHERE session_id = ? ORDER BY id", (stored_id,),
        ).fetchall()
    messages = []
    for row_id, message_data, created_at in rows:
        try:
            item = json.loads(message_data)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Invalid message JSON in database row {row_id}.") from exc
        messages.append({"id": row_id, "created_at": created_at, "message_data": item})
    payload = {"session_id": stored_id, "task": task, "messages": messages}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def empty_history(
    session_id: str, task: Task, db_path: str | Path = DB_PATH
) -> int:
    """Delete only selected messages and metadata; return the message count."""
    stored_id = task_session_id(session_id, task)
    uri = Path(db_path).resolve().as_uri() + "?mode=rw"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        with conn:
            count = conn.execute(
                "DELETE FROM agent_messages WHERE session_id = ?", (stored_id,)
            ).rowcount
            conn.execute(
                "DELETE FROM agent_sessions WHERE session_id = ?", (stored_id,)
            )
    return count
