"""Run: python -m unittest discover -s AI_tutor/tests -p test_extractor.py"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

spec = importlib.util.spec_from_file_location("extractor", Path(__file__).parents[1] / "pdf" / "extractor.py")
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data_dir = Path(directory.name) / "data"
        location = patch.object(extractor, "__file__", str(Path(directory.name) / "pdf" / "extractor.py"))
        location.start()
        self.addCleanup(location.stop)

    def test_bookmarks_counts_and_saved_json(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "book.pdf"
            with pymupdf.open() as document:
                page = document.new_page()
                for y, text, size in [(60, "Chapter 1", 20), (90, "First body", 11),
                                      (130, "1.1 Detail", 15), (160, "Detail body", 11),
                                      (200, "Chapter 2", 20), (230, "Last body", 11)]:
                    page.insert_text((72, y), text, fontsize=size)
                document.set_toc([[1, "Chapter 1", 1], [2, "1.1 Detail", 1], [1, "Chapter 2", 1]])
                document.save(source)
            result = extractor.extract_pdf_structure(source)
            self.assertEqual(result["detection_method"], "bookmarks")
            first, second = result["chapters"]
            self.assertEqual(first["character_count"], len("Chapter 1\nFirst body\n1.1 Detail\nDetail body\n"))
            self.assertEqual(first["sections"][0]["character_count"], len("1.1 Detail\nDetail body\n"))
            self.assertEqual(first["character_count"] + second["character_count"], result["total_characters"])
            self.assertEqual(json.loads((self.data_dir / "book.json").read_text(encoding="utf-8")), result)

    def test_numbered_heading_fallback(self):
        lines = [{"text": text, "size": size, "offset": index, "page": 1, "y": index}
                 for index, (text, size) in enumerate([
                     ("Chapter 1", 20), ("This is body text with many ordinary words.", 11),
                     ("1.1 Introduction", 14), ("1.1.1 Details", 12),
                     ("Chapter 2", 20)])]
        headings = extractor._inferred_headings(lines)
        self.assertEqual([item["level"] for item in headings], [1, 2, 3, 1])

    def test_no_heading_and_blank_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "plain.pdf"
            with pymupdf.open() as document:
                page = document.new_page()
                page.insert_text((72, 72), "Ordinary text without headings.")
                document.save(source)
            result = extractor.extract_pdf_structure(source)
            self.assertEqual(result["detection_method"], "whole_document")
            self.assertEqual(result["chapters"][0]["character_count"], result["total_characters"])
            blank = Path(directory) / "blank.pdf"
            with pymupdf.open() as document:
                document.new_page()
                document.save(blank)
            with self.assertRaisesRegex(ValueError, "OCR"):
                extractor.extract_pdf_structure(blank)


if __name__ == "__main__":
    unittest.main()
