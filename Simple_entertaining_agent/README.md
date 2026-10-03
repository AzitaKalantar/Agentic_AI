# Entertainment agents

A Python project using the OpenAI Agents SDK for jokes, fun facts, conversational
one-word puzzles, and cute images from Wikimedia Commons. The entertainment
manager offers these activities in a notebook or terminal. Specialist agents
keep separate persistent histories for each user in SQLite.

## Setup and model version

From the repository root, install dependencies:

```powershell
python -m pip install -r Simple_entertaining_agent/requirements.txt
```

Copy `Simple_entertaining_agent/.env.example` to `.env` in the same folder
if you do not already have one, then set your API key:

```dotenv
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-6-luna
```

**The project's default model is `gpt-6-luna`.** All five agents use it:
the entertainment manager, joke generator, fun fact generator, puzzle host,
and cute image finder. Set `OPENAI_MODEL` to override the model for all agents
with one your account supports. When the variable is unset, the code defaults
to `gpt-6-luna`; do not leave an active `OPENAI_MODEL=` entry empty.

Each activity loads this folder's `.env` with `override=True`, so its values
take precedence over existing environment variables. Internet access and an
OpenAI API key are required. Wikimedia Commons search needs no extra API key.
Optionally set `WIKIMEDIA_CONTACT` to a contact email or URL for the image
search request's User-Agent.

Dependencies in `requirements.txt` are `openai-agents`, `httpx`, `python-dotenv`,
`pandas`, `ipython`, and `ipykernel`.

## Entertainment manager

From the repository root:

```powershell
python Simple_entertaining_agent/entertainment_manager.py
```

In a notebook running from the repository root:

```python
from Simple_entertaining_agent.entertainment_manager import EntertainmentManager

await EntertainmentManager(user_id="alice")
```

Inside this folder's notebook, import from `entertainment_manager` instead.
Use natural language such as "tell me a joke", "show me a kitten", or
"surprise me". Surprise choices are selected randomly by Python.

Type `quit`, `exit`, `bye`, or `stop` to end the conversation, including during
a puzzle. During a puzzle, `menu` or `back` returns to the options. Solving a
puzzle, revealing its answer, or finishing another activity returns to the menu.

The manager displays images inline in notebooks and prints image URLs in a
terminal. It does not launch a browser. Specialist histories persist in SQLite;
the manager's menu conversation stays in memory for the current invocation.

## Individual agents

In a notebook running from the repository root:

```python
from Simple_entertaining_agent.joke_agent import Joke
from Simple_entertaining_agent.funfact_agent import FunFact
from Simple_entertaining_agent.puzzle_agent import Puzzle

await Joke(user_id="alice")     # Print one joke.
await FunFact(user_id="alice")  # Print one fun fact.
await Puzzle(user_id="alice")   # Start an interactive puzzle round.
```

Inside `EntertainingAgent.ipynb` in this folder, omit the
`Simple_entertaining_agent.` prefix. All activity functions default to
`user_id="user-1"`; use another ID for a separate user's history. In a regular
Python script, use `asyncio.run(...)` instead of top-level `await`.

### One-word puzzles

From a terminal:

```powershell
python Simple_entertaining_agent/puzzle_agent.py
```

The agent gives a riddle with a one-word answer. Guess, ask for hints in natural
language, or ask for the answer. Wrong guesses and hints keep the round going;
a correct guess or a request to reveal the answer ends it. In the standalone
puzzle agent, type `quit` or `exit` to leave early.

Each invocation starts a new round, even if the previous one was unfinished.
The agent sees the user's previous puzzles, guesses, and hints and is instructed
to avoid repeats, including reworded puzzles. Repeat avoidance is best effort
for puzzles, jokes, facts, and image selections.

### Cute image search

The cute-image agent searches Wikimedia Commons and returns an `ImageResult`.
It selects an existing image and writes a caption; it does not generate images
or visually inspect search results. The caller decides how to display it.

```python
from Simple_entertaining_agent.cute_image_agent import CuteImage
from IPython.display import Image, display

image = await CuteImage(user_id="alice", subject="cute kitten")
if image is not None:
    print(image.caption)
    print(f"Source and license: {image.source_url}")
    display(Image(url=image.image_url, width=640))
```

Inside this folder's notebook, use `from cute_image_agent import CuteImage`.
The result contains `title`, `image_url`, `source_url`, and `caption`, or is
`None` if no suitable image is selected. The source page provides attribution
and license details. Search or API errors may propagate to the caller.

Run `python Simple_entertaining_agent/cute_image_agent.py` to print result
details as JSON using the default subject, `"cute image"`. The manager uses
`"cute baby animal"` when no subject is supplied.

## Shared history database

All four specialist agents use `db/entertainment_history.db` relative to this
folder, with the SDK's `agent_sessions` and `agent_messages` tables. Each base
user ID has separate histories: `alice:jokes`, `alice:puzzles`, `alice:facts`,
and `alice:images`. Reusing an ID preserves history across runs and notebook
kernel restarts. Older histories saved with random session IDs are separate.

From the repository root:

```python
from Simple_entertaining_agent.handle_database import (
    get_db_contents,
    get_db_tables,
    get_history_json,
    empty_history,
)

messages = get_db_contents(session_id="alice", task="jokes")
tables = get_db_tables()
history_json = get_history_json(session_id="alice", task="images")

# Delete only Alice's puzzle messages and session metadata.
removed_count = empty_history(session_id="alice", task="puzzles")
```

Inside this folder's notebook, import from `handle_database` instead.
Pass the base ID (`alice`) without a task suffix. Valid tasks are `jokes`,
`puzzles`, `facts`, and `images`.

- `get_db_contents` returns one user's task history as a pandas DataFrame,
  ordered by message ID.
- `get_db_tables` returns a dictionary of DataFrames for both complete tables.
- `get_history_json` returns a JSON string with decoded messages, row IDs,
  and timestamps for one user's task history.
- `empty_history` deletes the selected history and returns the number of
  messages removed.

These helpers return results without printing or displaying them. All accept
an optional `db_path` and require an existing SDK database and tables. Running
an activity creates the database and tables. The `db/` folder is created
automatically when the storage module is imported.

Database files, SQLite sidecars, `.env`, Python caches, virtual environments,
and notebook checkpoints are ignored by the root `.gitignore`. The tracked
`db/.gitkeep` preserves the empty data folder in fresh checkouts.

Restart the notebook kernel and rerun imports after updating Python modules.
If a notebook cell uses the old `display_db_contents`, `print_db_tables`, or
`export_history_json` names, replace them with `get_db_contents`,
`get_db_tables`, or `get_history_json`, respectively.
