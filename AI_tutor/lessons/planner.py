"""Plan one chapter: python -m AI_tutor.lessons.planner book.pdf --chapter 1."""
import argparse
from dataclasses import asdict
import asyncio
import json
import os
from pathlib import Path
from typing import Awaitable, Callable

from dotenv import load_dotenv

from ..models import LessonDraft, PlannerResult, LessonPlan, ChapterLessonPlan
from ..pdf.chapter_parser import parse_chapter
from ..pdf.chunker import chunk_chapter
from .prompts import PLANNER_PROMPT

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def validate_source_coverage(material: str, result: PlannerResult) -> None:
    reconstructed = "".join(lesson.source_text for lesson in result.completed_lessons) + result.remaining_material
    if reconstructed != material:
        raise ValueError("Planner must preserve source text exactly, in order, without loss or duplication.")


def validate_dependencies(previous_lessons, result):
    for number, lesson in enumerate(result.completed_lessons, len(previous_lessons) + 1):
        if len(set(lesson.depends_on)) != len(lesson.depends_on) or any(
                dependency < 1 or dependency >= number for dependency in lesson.depends_on):
            raise ValueError("depends_on must contain distinct earlier lesson numbers.")


def make_lesson_planner(model=None, *, max_material_characters=60_000):
    """Build a stateless structured-output LLM callback; no API call until used."""
    from agents import Agent, Runner, RunConfig

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
    selected_model = model or os.getenv("OPENAI_MODEL", "gpt-6-luna")
    agent = Agent(name="Textbook lesson planner", model=selected_model,
                  instructions=PLANNER_PROMPT, output_type=PlannerResult)

    async def create_lesson_plans(material, *, previous_lessons, end_of_chapter):
        if len(material) > max_material_characters:
            raise ValueError("Subsection plus buffer exceeds the configured material limit. Use a larger-context configuration or review subsection boundaries.")
        payload = {
            "material": material, "end_of_chapter": end_of_chapter,
            "previous_lessons": [{"lesson_number": number, "title": lesson.title,
                                  "learning_objective": lesson.learning_objective,
                                  "concepts": lesson.concepts}
                                 for number, lesson in enumerate(previous_lessons, 1)],
        }
        error = None
        for _ in range(3):
            request = dict(payload)
            if error:
                request["validation_feedback"] = error
            response = await Runner.run(agent, json.dumps(request, ensure_ascii=False),
                                        run_config=RunConfig(tracing_disabled=True))
            try:
                result = PlannerResult.model_validate(response.final_output)
                validate_source_coverage(material, result)
                validate_dependencies(previous_lessons, result)
                return result
            except ValueError as exc:
                error = str(exc)
        raise ValueError(f"Planner returned invalid source coverage after 3 attempts: {error}")

    return create_lesson_plans


def _save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


async def plan_chapter(pdf_path, chapter: int | str, *, model=None, password=None,
                       create_lesson_plans: Callable[..., Awaitable[PlannerResult]] | None = None):
    """Return/save ChapterLessonPlan; keep buffer/checkpoints in a .progress.json file.

    An injected async callback supports offline testing. Re-running starts a fresh
    plan and replaces this chapter's JSON. No cross-chapter buffering is done.
    """
    selected = parse_chapter(pdf_path, chapter, password=password)
    chunks = chunk_chapter(selected)
    planner = create_lesson_plans or make_lesson_planner(model)
    target = DATA_DIR / f"{Path(pdf_path).stem}.chapter-{selected.number}.lessons.json"
    progress_target = target.with_suffix(".progress.json")
    plan = ChapterLessonPlan(chapter_title=selected.title, lessons=[])
    lessons: list[LessonDraft] = []
    source_offset = 0
    lesson_sources = []
    chapter_start = selected.outline["start_char"]
    sources_target = target.with_name(target.name.replace(".lessons.json", ".sources.json"))
    catalog = {"source_pdf": selected.source_pdf, "chapter_number": selected.number,
               "chapter_title": selected.title, "chunks": [asdict(chunk) for chunk in chunks],
               "lesson_sources": lesson_sources}
    _save(sources_target, catalog)
    buffer = ""
    payload = {"source_pdf": selected.source_pdf, "chapter_number": selected.number,
               "chapter_title": selected.title, "completed_lessons": [],
               "remaining_material": "", "processed_chunks": 0,
               "total_chunks": len(chunks), "status": "planning"}
    _save(progress_target, payload)
    try:
        for index, chunk in enumerate(chunks):
            material = buffer + chunk.text
            result = PlannerResult.model_validate(await planner(
                material, previous_lessons=lessons, end_of_chapter=index == len(chunks) - 1))
            validate_source_coverage(material, result)
            validate_dependencies(lessons, result)
            for draft in result.completed_lessons:
                end = source_offset + len(draft.source_text)
                ranges = []
                for source_chunk in chunks:
                    left = max(chapter_start + source_offset, source_chunk.start_char)
                    right = min(chapter_start + end, source_chunk.end_char)
                    if left < right:
                        ranges.append({"chunk_id": source_chunk.chunk_id,
                                       "start_char": left - source_chunk.start_char,
                                       "end_char": right - source_chunk.start_char})
                plan.lessons.append(LessonPlan(
                    lesson_number=len(plan.lessons) + 1, title=draft.title,
                    learning_objective=draft.learning_objective, concepts=draft.concepts,
                    source_chunks=[item["chunk_id"] for item in ranges],
                    source_scope=draft.source_scope, estimated_minutes=draft.estimated_minutes,
                    depends_on=draft.depends_on))
                lesson_sources.append({"lesson_number": len(plan.lessons), "ranges": ranges})
                source_offset = end
            lessons.extend(result.completed_lessons)
            buffer = result.remaining_material
            payload.update(completed_lessons=[lesson.model_dump() for lesson in lessons],
                           remaining_material=buffer, processed_chunks=index + 1)
            _save(progress_target, payload)
            _save(sources_target, catalog)
    except Exception:
        payload["status"] = "failed"
        _save(progress_target, payload)
        raise
    payload["status"] = "needs_review" if buffer else "complete"
    _save(progress_target, payload)
    _save(target, plan.model_dump())
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--chapter", required=True, help="1-based outline index (including Preamble), or exact title")
    parser.add_argument("--model", help="Overrides OPENAI_MODEL")
    args = parser.parse_args()
    chapter = int(args.chapter) if args.chapter.isdecimal() else args.chapter
    result = asyncio.run(plan_chapter(args.pdf_path, chapter, model=args.model))
    print(f"Saved {len(result.lessons)} lessons for {result.chapter_title}. Check the progress JSON for unfinished material.")
