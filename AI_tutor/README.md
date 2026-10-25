# AI tutor

Install dependencies from the repository root:

~~~powershell
python -m pip install -r AI_tutor/requirements.txt
~~~

Set OPENAI_API_KEY in your environment or in AI_tutor/.env. Optionally set
OPENAI_MODEL (default: gpt-6-luna). The other project's .env is not loaded.

Plan one chapter from the repository root:

~~~powershell
python -m AI_tutor.lessons.planner "path/to/book.pdf" --chapter 1
python -m AI_tutor.lessons.planner "path/to/book.pdf" --chapter "Chapter 2"
~~~

The chapter argument is either a 1-based top-level outline index (including
Preamble if present) or an exact, case-insensitive title. The PDF outline is
refreshed automatically and saved as data/<book>.json. Plans are saved as
data/<book>.chapter-<index>.lessons.json, relative to AI_tutor regardless of the
working directory. Re-running replaces that chapter's previous plan.

Chapter parsing and chunking live in pdf/chapter_parser.py and pdf/chunker.py.
Chunks follow subsection boundaries, including nested headings and parent
introductions. Their concatenation exactly equals the chapter text. LLM calls
and the buffer loop live in lessons/planner.py; instructions are in
lessons/prompts.py and Pydantic schemas in models.py.

Each call receives buffer + next subsection, previous lesson titles/concepts,
and an end-of-chapter flag. It may produce zero, one, or multiple 10-20 minute
lesson drafts, targeting about 10 minutes and 1-3 concepts. Source excerpts
must reproduce the input exactly and in order, with unused text as a suffix.
Invalid LLM source coverage is retried twice, then rejected. No textbook text
is included in SDK traces. Material is sent to the configured OpenAI model.

Plans now use ChapterPlan with a lessons list of LessonPlan objects. Lesson
numbers start at 1 within each chapter. source_start is inclusive and source_end
is exclusive, in Unicode characters relative to the extracted chapter text.
Recover source with chapter.text[lesson.source_start:lesson.source_end].
Offsets and numbering are computed in Python, not guessed by the LLM.
previous_knowledge lists model-selected prerequisites from earlier lessons.

The lessons JSON contains exactly the ChapterPlan fields. Buffer, source
metadata, status, and completed draft checkpoints are stored separately in
data/<book>.chapter-<index>.lessons.progress.json. plan_chapter returns a
ChapterPlan model.

Progress is checkpointed after each successful chunk. A final tail is saved as
remaining_material with status needs_review; it is never silently discarded or
forced into an incomplete lesson. A failed run retains the last successful
checkpoint with status failed and processed_chunks, but restarting currently
replans the chapter rather than resuming. A 60,000-character per-call guard
prevents unbounded buffers; adjust make_lesson_planner's limit for your model.
Subsections are never silently truncated or split at arbitrary character counts.

Lesson drafts describe the curriculum and retain source text; generating the
actual teaching content is a later step. Learning-time estimates and conceptual
completeness are model judgments and need human review. PDF headings without
bookmarks are also heuristic. Scanned books require OCR first.

Run offline tests (no API calls):

~~~powershell
python -m unittest discover -s AI_tutor/tests -v
~~~
