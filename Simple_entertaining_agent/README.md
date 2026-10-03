# Entertainment agents

Joke, fun fact, and puzzle agents share persistent SQLite storage. Python modules
and the notebook live together for straightforward imports; local data lives in
`db/`.

The agent gives a riddle with a one-word answer and holds a conversation about
that puzzle. You can guess, ask for hints in natural language, or ask for the
answer. Wrong guesses and hints keep the game going; a correct guess or a
request to reveal the answer ends the round. Type `quit` to leave early.

Install dependencies if needed:

```powershell
python -m pip install -r Simple_entertaining_agent/requirements.txt
```

Copy `.env.example` to `.env` in this folder and set `OPENAI_API_KEY`.
The model defaults to the same
`gpt-6-astra` used in the existing notebook; optionally set `OPENAI_MODEL` in
`.env` to use another model your account supports.

From the project root, run:

```powershell
python Simple_entertaining_agent/puzzle_agent.py
```

Or run the import cell and final cell in `EntertainingAgent.ipynb`:

```python
from puzzle_agent import Puzzle
await Puzzle(user_id="alice")
```

Run `await Puzzle(user_id="alice")` again for a new round. The same user ID reuses
the same SQLite session in `db/entertainment_history.db`, including after kernel restarts.
Use another ID, such as `bob`, for a separate user's history. `await Puzzle()`
uses the default user ID `user-1`.

The agent sees the user's previous puzzles, guesses and hints and is instructed
to avoid repeats, including reworded puzzles. This is best effort, rather than a
guarantee. Each invocation starts a new round, even if the last one was unfinished.
Older rounds saved using random session IDs are not part of these new sessions.

## Shared history database

Jokes, puzzles, and facts use `db/entertainment_history.db`, with the SDK's
`agent_sessions` and `agent_messages` tables. Each base user/session ID has
separate histories such as `alice:jokes`, `alice:puzzles`, and `alice:facts`.

In the notebook:

```python
from handle_database import display_db_contents, empty_history

display_db_contents(session_id="alice", task="jokes")
empty_history(session_id="alice", task="puzzles")
```

From the project root, import from `Simple_entertaining_agent.handle_database`.
Pass the base ID (`alice`), without the task suffix. Valid tasks are `jokes`,
`puzzles`, and `facts`. The helpers return results without printing or displaying them.
`display_db_contents` returns a pandas DataFrame with all messages;
empty returns the number of messages removed and deletes only that session's
metadata and messages. Both accept an optional `db_path` and require an existing
SDK database. `empty_history` replaces the former `empty_jokes_history` helper.

The `db/` folder is created automatically if missing. Running an agent creates
the database and SDK tables. Database files, SQLite sidecars, `.env`, Python
caches, virtual environments, and notebook checkpoints are ignored by the root
`.gitignore`. The tracked `db/.gitkeep` keeps the empty folder in fresh checkouts.

To retrieve both complete tables or return history as a JSON string:

```python
from handle_database import print_db_tables, export_history_json

tables = print_db_tables()
history_json = export_history_json(session_id="alice", task="puzzles")
```

Restart your notebook kernel and rerun imports after updating the code.
