import unittest
from AI_tutor.pdf.chapter_parser import Chapter
from AI_tutor.pdf.chunker import chunk_chapter


class ChunkerTests(unittest.TestCase):
    def test_nested_sections_retain_introductions_without_overlap(self):
        outline = {"start_char": 10, "end_char": 22, "sections": [
            {"title": "Section", "start_char": 13, "sections": [
                {"title": "Detail", "start_char": 17, "sections": []}]}]}
        chapter = Chapter(1, "Chapter", "abcdefghijkl", outline, "book.pdf")
        chunks = chunk_chapter(chapter)
        self.assertEqual([chunk.text for chunk in chunks], ["abc", "defg", "hijkl"])
        self.assertEqual("".join(chunk.text for chunk in chunks), chapter.text)

    def test_no_sections_is_one_chunk(self):
        chapter = Chapter(1, "Chapter", "abc", {"start_char": 0, "end_char": 3, "sections": []}, "book.pdf")
        self.assertEqual([chunk.text for chunk in chunk_chapter(chapter)], ["abc"])
