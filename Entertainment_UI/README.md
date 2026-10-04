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

Each conversation gets a unique ID and a persistent manager instance. New
conversations have separate specialist histories. Restarting the server loses
active conversation state; existing SQLite histories remain in the agent folder.
This is a local playground bound to loopback, limited to 100 active sessions.
It is not a public deployment server. Frontend files live in `public/`.

Run the HTTP bridge checks without paid model calls:

```powershell
python -m unittest discover -s Entertainment_UI/tests -v
```
