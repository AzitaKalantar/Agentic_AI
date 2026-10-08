# The Little Break — React playground

A separate local UI for `../Simple_entertaining_agent`. The Python server serves
the React frontend and connects it to your actual `EntertainmentManager`.
No Node.js or frontend build step is needed. React and fonts load from CDNs,
so the browser needs internet access (system fonts are used if Google Fonts fails).

From the parent `AgenticAI` folder:

```powershell
python -m pip install -r Simple_entertaining_agent/requirements.txt
python Entertainment_UI/server.py
```

Open **http://localhost:8000**. Stop the server with Ctrl+C.
Your existing `Simple_entertaining_agent/.env` must contain a working
`OPENAI_API_KEY` and an `OPENAI_MODEL` supported by your account. The key stays
in Python; it is never sent to the frontend. Requests use your API account.

Choose an activity or type freely. During puzzles, guess, request hints, reveal
the answer, or go back to the menu. Images include source and license links.
Type `quit` to end, and use **New conversation** to start again.

Refreshing the page restores your chat, puzzle mode, and specialist context.
The tab stores only its conversation ID in sessionStorage; chat and specialist
histories live in server memory, including in-memory SQLite sessions. UI turns
are no longer written to the agent's history database.

Closing the tab/browser disconnects its live connection. The server clears
that conversation after a 30-second grace period, allowing refreshes to
reconnect. Network disconnections lasting longer than this also clear history.
Browsers that restore a closed tab within that grace period can resume it.
New conversation clears the previous conversation immediately. Stopping the
server discards all UI history, even if it is forcibly terminated. Refresh
after a restart to begin fresh. Individual Python/notebook agents retain their
normal persistent storage; pre-existing database histories are unaffected.
This is a local playground bound to loopback, limited to 100 active sessions.
It is not a public deployment server. Frontend files live in `public/`.

Run the HTTP bridge checks without paid model calls:

```powershell
python -m unittest discover -s Entertainment_UI/tests -v
```
# Behind the scenes

Each assistant reply includes a collapsible **Behind the scenes** panel. The
panel starts closed by default. Open a reply's panel
to see the routing decision, participating agents, tools called, elapsed time,
model response count, and input/output tokens. Surprise requests show the random
activity chosen; puzzle follow-ups explain why routing goes directly to the host.
Failed requests retain their recorded steps and error types. Details appear when
the turn finishes and stay with the conversation across a refresh.
The chat header includes a tracing banner. Replies from before tracing was added
show a note explaining that no trace is available; send a new message to see one.

The API attaches the finalized trace directly to each reply, without reading the
shared log file. Traces are excluded from the model's conversation history.
