"""Plan one chapter: python -m AI_tutor.lessons.planner book.pdf --chapter 1."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Awaitable, Callable

from dotenv import load_dotenv

from ..models import LessonDraft, PlannerResult, LessonPlan, ChapterPlan
from ..pdf.chapter_parser import parse_chapter
from ..pdf.chunker import chunk_chapter
from .prompts import PLANNER_PROMPT

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def validate_source_coverage(material: str, result: PlannerResult) -> None:
    reconstructed = "".join(lesson.source_text for lesson in result.completed_lessons) + result.remaining_material
    if reconstructed != material:
        raise ValueError("Planner must preserve source text exactly, in order, without loss or duplication.")


def validate_previous_knowledge(previous_lessons, result):
    known = {concept for lesson in previous_lessons for concept in lesson.concepts}
    for lesson in result.completed_lessons:
        if not set(lesson.previous_knowledge) <= known:
            raise ValueError("previous_knowledge must only reference concepts from earlier lessons.")
        known.update(lesson.concepts)


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
            "previous_lessons": [{"title": lesson.title, "concepts": lesson.concepts}
                                 for lesson in previous_lessons],
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
                validate_previous_knowledge(previous_lessons, result)
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
    """Return/save ChapterPlan; keep buffer/checkpoints in a .progress.json file.

    An injected async callback supports offline testing. Re-running starts a fresh
    plan and replaces this chapter's JSON. No cross-chapter buffering is done.
    """
    selected = parse_chapter(pdf_path, chapter, password=password)
    chunks = chunk_chapter(selected)
    planner = create_lesson_plans or make_lesson_planner(model)
    target = DATA_DIR / f"{Path(pdf_path).stem}.chapter-{selected.number}.lessons.json"
    progress_target = target.with_suffix(".progress.json")
    plan = ChapterPlan(chapter_number=selected.number, chapter_title=selected.title, lessons=[])
    lessons: list[LessonDraft] = []
    source_offset = 0
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
            validate_previous_knowledge(lessons, result)
            for draft in result.completed_lessons:
                end = source_offset + len(draft.source_text)
                plan.lessons.append(LessonPlan(
                    lesson_number=len(plan.lessons) + 1, title=draft.title,
                    concepts=draft.concepts, source_start=source_offset, source_end=end,
                    estimated_minutes=draft.estimated_minutes,
                    previous_knowledge=draft.previous_knowledge))
                source_offset = end
            lessons.extend(result.completed_lessons)
            buffer = result.remaining_material
            payload.update(completed_lessons=[lesson.model_dump() for lesson in lessons],
                           remaining_material=buffer, processed_chunks=index + 1)
            _save(progress_target, payload)
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
