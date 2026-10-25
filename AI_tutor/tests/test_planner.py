import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

import pymupdf

from AI_tutor.models import LessonDraft, PlannerResult, ChapterLessonPlan
from AI_tutor.pdf.chapter_parser import Chapter, parse_chapter
from AI_tutor.lessons import planner


def lesson(text):
    return LessonDraft(title="Topic", concepts=["Concept"], source_text=text, estimated_minutes=10,
                       learning_objective="Understand the concept", source_scope="Assigned passage", depends_on=[])


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_buffer_can_join_sections_and_emit_multiple_lessons(self):
        chapter = Chapter(1, "Chapter", "abcdefghij", {"start_char": 0, "end_char": 10,
            "sections": [{"title": "Second", "start_char": 3, "sections": []}]}, "book.pdf")
        callback = AsyncMock(side_effect=[
            PlannerResult(completed_lessons=[], remaining_material="abc"),
            PlannerResult(completed_lessons=[lesson("abcd"), lesson("efghij")], remaining_material="")])
        with tempfile.TemporaryDirectory() as directory, patch.object(planner, "DATA_DIR", Path(directory)), patch.object(planner, "parse_chapter", return_value=chapter):
            result = await planner.plan_chapter("book.pdf", 1, create_lesson_plans=callback)
            self.assertEqual(callback.call_args_list[1].args[0], "abcdefghij")
            self.assertTrue(callback.call_args_list[1].kwargs["end_of_chapter"])
            self.assertIsInstance(result, ChapterLessonPlan)
            self.assertEqual(len(result.lessons), 2)
            saved = json.loads((Path(directory) / "book.chapter-1.lessons.json").read_text())
            self.assertEqual(saved, result.model_dump())
            sources = json.loads((Path(directory) / "book.chapter-1.sources.json").read_text())
            by_id = {chunk["chunk_id"]: chunk["text"] for chunk in sources["chunks"]}
            recovered = ["".join(by_id[item["chunk_id"]][item["start_char"]:item["end_char"]]
                                 for item in entry["ranges"]) for entry in sources["lesson_sources"]]
            self.assertEqual(recovered, ["abcd", "efghij"])
            self.assertEqual(result.lessons[0].source_chunks, ["chapter-1-chunk-1", "chapter-1-chunk-2"])
            self.assertEqual([item.lesson_number for item in result.lessons], [1, 2])


    async def test_tail_is_saved_for_review(self):
        chapter = Chapter(1, "Chapter", "abc", {"start_char": 0, "end_char": 3, "sections": []}, "book.pdf")
        callback = AsyncMock(return_value=PlannerResult(completed_lessons=[], remaining_material="abc"))
        with tempfile.TemporaryDirectory() as directory, patch.object(planner, "DATA_DIR", Path(directory)), patch.object(planner, "parse_chapter", return_value=chapter):
            result = await planner.plan_chapter("book.pdf", 1, create_lesson_plans=callback)
            progress = json.loads((Path(directory) / "book.chapter-1.lessons.progress.json").read_text())
            self.assertEqual(progress["status"], "needs_review")
            self.assertEqual(progress["remaining_material"], "abc")
            self.assertEqual(result.lessons, [])

    async def test_invalid_source_is_rejected_and_failure_saved(self):
        chapter = Chapter(1, "Chapter", "abc", {"start_char": 0, "end_char": 3, "sections": []}, "book.pdf")
        callback = AsyncMock(return_value=PlannerResult(completed_lessons=[lesson("invented")], remaining_material=""))
        with tempfile.TemporaryDirectory() as directory, patch.object(planner, "DATA_DIR", Path(directory)), patch.object(planner, "parse_chapter", return_value=chapter):
            with self.assertRaisesRegex(ValueError, "preserve"):
                await planner.plan_chapter("book.pdf", 1, create_lesson_plans=callback)
            saved = json.loads((Path(directory) / "book.chapter-1.lessons.progress.json").read_text())
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["processed_chunks"], 0)

    def test_select_chapter_from_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "book.pdf"
            with pymupdf.open() as document:
                for title in ["Chapter One", "Chapter Two"]:
                    page = document.new_page()
                    page.insert_text((72, 72), title)
                    page.insert_text((72, 100), "Some body text.")
                document.set_toc([[1, "Chapter One", 1], [1, "Chapter Two", 2]])
                document.save(source)
            with patch("AI_tutor.pdf.extractor.__file__", str(Path(directory) / "pdf" / "extractor.py")):
                selected = parse_chapter(source, "chapter two")
                self.assertEqual(selected.number, 2)
                self.assertIn("Chapter Two", selected.text)
                self.assertNotIn("Chapter One", selected.text)
                with self.assertRaises(ValueError):
                    parse_chapter(source, 99)

    async def test_llm_retries_bad_coverage(self):
        from types import SimpleNamespace
        with patch("agents.Runner.run", new_callable=AsyncMock) as run:
            run.side_effect = [SimpleNamespace(final_output=PlannerResult(completed_lessons=[], remaining_material="wrong")),
                               SimpleNamespace(final_output=PlannerResult(completed_lessons=[lesson("abc")], remaining_material=""))]
            create = planner.make_lesson_planner(model="test-model")
            result = await create("abc", previous_lessons=[], end_of_chapter=True)
            self.assertEqual(run.await_count, 2)
            self.assertEqual(result.remaining_material, "")

    def test_dependencies_only_reference_earlier_lessons(self):
        first = lesson("abc")
        second = lesson("def")
        second.depends_on = [1]
        planner.validate_dependencies([], PlannerResult(completed_lessons=[first, second], remaining_material=""))
        with self.assertRaisesRegex(ValueError, "earlier lesson"):
            planner.validate_dependencies([], PlannerResult(completed_lessons=[second], remaining_material=""))

    async def test_source_ranges_account_for_nonzero_chapter_offset(self):
        chapter = Chapter(2, "Chapter Two", "abcdef", {"start_char": 100, "end_char": 106,
            "sections": [{"title": "Second", "start_char": 103, "sections": []}]}, "book.pdf")
        second = lesson("cdef")
        second.depends_on = [1]
        callback = AsyncMock(side_effect=[
            PlannerResult(completed_lessons=[lesson("ab")], remaining_material="c"),
            PlannerResult(completed_lessons=[second], remaining_material="")])
        with tempfile.TemporaryDirectory() as directory, patch.object(planner, "DATA_DIR", Path(directory)), patch.object(planner, "parse_chapter", return_value=chapter):
            result = await planner.plan_chapter("book.pdf", 2, create_lesson_plans=callback)
            sources = json.loads((Path(directory) / "book.chapter-2.sources.json").read_text())
            self.assertEqual(sources["lesson_sources"][1]["ranges"], [
                {"chunk_id": "chapter-2-chunk-1", "start_char": 2, "end_char": 3},
                {"chunk_id": "chapter-2-chunk-2", "start_char": 0, "end_char": 3}])
            self.assertEqual(result.lessons[1].depends_on, [1])
