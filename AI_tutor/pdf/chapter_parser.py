"""Select a chapter and recover text using the extractor's exact text stream."""
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .extractor import _read_lines, extract_pdf_structure


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    text: str
    outline: dict
    source_pdf: str


def parse_chapter(pdf_path, chapter: int | str, *, password=None) -> Chapter:
    """Select by 1-based top-level outline index or exact title (case-insensitive).

    Indexes include Preamble when present. A fresh outline avoids stale offsets.
    """
    outline = extract_pdf_structure(pdf_path, password=password)
    chapters = outline["chapters"]
    if isinstance(chapter, int):
        if not 1 <= chapter <= len(chapters):
            raise ValueError(f"Chapter index must be between 1 and {len(chapters)}.")
        number = chapter
    else:
        matches = [i for i, item in enumerate(chapters, 1)
                   if item["title"].casefold().strip() == chapter.casefold().strip()]
        if len(matches) != 1:
            choices = ", ".join(f"{i}: {item['title']}" for i, item in enumerate(chapters, 1))
            raise ValueError(f"Chapter title must match exactly one chapter. Available: {choices}")
        number = matches[0]
    selected = chapters[number - 1]
    with pymupdf.open(pdf_path) as document:
        if document.needs_pass and not document.authenticate(password or ""):
            raise ValueError("Supply a valid PDF password.")
        _, text, _ = _read_lines(document)
    return Chapter(number, selected["title"],
                   text[selected["start_char"]:selected["end_char"]],
                   selected, str(Path(pdf_path).resolve()))
