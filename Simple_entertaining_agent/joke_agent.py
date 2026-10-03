"""Generate jokes using a persistent conversation session for each user."""

import os
from pathlib import Path

from agents import Agent, Runner, SQLiteSession
from dotenv import load_dotenv

if __package__:
    from .session_storage import DB_PATH, task_session_id
else:
    from session_storage import DB_PATH, task_session_id


def create_joke_agent() -> Agent:
    return Agent(
        name="Joke generator",
        instructions=(
            "Tell one joke. Avoid jokes you have already told in this conversation. "
            "When possible, choose a different joke style or topic."
        ),
        model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),
    )


async def Joke(user_id: str = "user-1") -> None:
    """Print one joke, remembering jokes previously given to this user."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id must be a nonempty string.")
    load_dotenv(Path(__file__).with_name(".env"), override=True)
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY in Simple_entertaining_agent/.env.")
    session = SQLiteSession(
        task_session_id(user_id, "jokes"), DB_PATH
    )
    try:
        result = await Runner.run(create_joke_agent(), "Tell me a joke.", session=session)
        print(result.final_output)
    finally:
        session.close()
