# Entertainment agents

A Python project using the OpenAI Agents SDK for jokes, fun facts, conversational
one-word puzzles, and cute images from Wikimedia Commons. The entertainment
manager exposes these activities through a message-based interface for a UI backend. Specialist agents
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

The manager is a stateful class. Create one instance per conversation, then
pass each incoming chat message to `send_message`:

```python
from Simple_entertaining_agent.entertainment_manager import EntertainmentManager

manager = EntertainmentManager(user_id="alice")
response = await manager.send_message("Give me a puzzle")
print(response.message)

response = await manager.send_message("Can I have a hint?")
print(response.message)

# Return this dictionary from a future HTTP API endpoint.
payload = response.model_dump(mode="json")
```

Inside this folder's notebook, import from `entertainment_manager` instead.
The manager does not read terminal input, print replies, display images, or
run an interactive loop when its module is executed.

Each response contains:

- `message`: text to show in the chat.
- `action`: `chat`, `puzzle`, `image`, `joke`, `fact`, or `quit`.
- `mode`: `menu`, `puzzle`, or `closed`.
- `image`: image details (`title`, `image_url`, `source_url`, `caption`) or null.
- `puzzle_status`: `playing`, `solved`, `revealed`, or null.

Use natural language such as "tell me a joke", "show me a kitten", or
"surprise me". Surprise choices are selected randomly by Python. During a
puzzle, subsequent messages go to the puzzle host. Solving the puzzle or asking
for its answer returns the mode to `menu`. Send `menu` or `back` to leave a
puzzle, or `quit`, `exit`, `bye`, or `stop` to close the conversation.
Empty messages return guidance without making an API call.

Keep the same manager instance across requests; recreating it loses menu
context and the active puzzle mode. Use distinct user IDs for conversations
that must have separate specialist histories. Calls on the same instance are
serialized. Conversations sharing a user ID also share SQLite histories, so
avoid running them concurrently. Menu context and mode live in memory;
specialist histories persist in SQLite. Restarting the backend or creating a
new instance starts in menu mode. After quitting, create a new instance to
start another conversation.

The UI is responsible for rendering replies, images, source links, and menu
controls. API and network errors propagate to the caller for error handling.
This refactor does not add an HTTP server or frontend.

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

## Tracing and routing evaluation

Every manager turn appends one JSON record to `db/runs.jsonl`, including local
commands, empty input, and errors. `run_id` identifies the turn; records contain
UTC start time, routing decision/source, selected action, total latency in
milliseconds, tool names/call IDs/status, exception types, and input/output/total
model tokens. A surprise decision remains `surprise` while `selected_action`
records the random activity. Puzzle follow-ups have source `active_puzzle`.
Latency starts after acquiring the conversation lock, so it excludes queue time.

SDK hooks accumulate usage after each model response, including responses before
a later failure. Tokens for requests that fail before returning usage are unknown
and are not counted; `model_responses` shows how many responses were measured.
Tool status `completed` means the tool returned, including an SDK error response;
check `errors` for failures. A tool left `started` was interrupted before returning.
No prompts, tool arguments/results, user IDs, or exception messages are saved in
these local traces. The SDK's own remote tracing is separate. Local files are
ignored by Git. Pass `trace_path=None` to disable local recording, or a custom path
to `EntertainmentManager`. File write failures are logged without breaking replies.

Run the offline regression checks from the repository root:

```powershell
python -m unittest discover -s Simple_entertaining_agent/tests -v
python -m unittest discover -s Entertainment_UI/tests -v
```

Measure actual model routing (requires the configured API key and network access):

```powershell
python -m Simple_entertaining_agent.evaluate_routing
```

The 16 labeled prompts cover standard choices, spelling mistakes, ambiguous
requests, and requests for multiple activities. Ambiguous and multiple requests
expect `chat`, so the host asks for clarification. Each prompt uses empty context
and only runs the router, avoiding specialist calls and saved activity history.
The report prints overall/per-category accuracy and saves per-prompt expected and
actual routes, errors, latency, usage, and trace IDs in `db/routing_evaluation.json`.
Errors count as incorrect. Edit `CASES` in `evaluate_routing.py` to grow the set.
Reports contain the test prompts; normal run traces do not. Accuracy describes
this small menu-routing sample, not conversational follow-ups or output quality.
