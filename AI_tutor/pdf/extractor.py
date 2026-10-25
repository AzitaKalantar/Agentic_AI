"""Extract a PDF outline and character lengths with PyMuPDF.

Usage: python AI_tutor/pdf/extractor.py book.pdf
"""

import argparse
from bisect import bisect_right
from collections import Counter
import json
from pathlib import Path
import re

import pymupdf


def _normalise(text):
    return " ".join(text.casefold().split())


def _read_lines(document):
    """Use one canonical text stream so all offsets and counts agree."""
    lines, parts, page_starts = [], [], []
    offset = 0
    for page in document:
        page_starts.append(offset)
        data = page.get_text("dict", sort=True, flags=pymupdf.TEXTFLAGS_TEXT)
        for block in data["blocks"]:
            for line in block.get("lines", []):
                spans = line["spans"]
                text = "".join(span["text"] for span in spans).strip()
                if not text:
                    continue
                lines.append({
                    "text": text, "page": page.number + 1, "offset": offset,
                    "y": line["bbox"][1],
                    "size": round(max(span["size"] for span in spans), 1),
                })
                parts.append(text + "\n")
                offset += len(text) + 1
    return lines, "".join(parts), page_starts


def _bookmark_headings(document, lines, page_starts, warnings):
    headings = []
    for level, title, page, destination in document.get_toc(simple=False):
        if not 1 <= page <= len(page_starts):
            continue  # Ignore external bookmarks and bookmarks without a page.
        candidates = [line for line in lines if line["page"] == page]
        matches = [line for line in candidates
                   if _normalise(line["text"]) == _normalise(title)]
        point = destination.get("to")
        if matches:
            chosen = min(matches, key=lambda line: abs(line["y"] - point.y)) if point else matches[0]
            offset = chosen["offset"]
        elif candidates and point is not None:
            offset = min(candidates, key=lambda line: abs(line["y"] - point.y))["offset"]
            warnings.append(f"Bookmark {title!r}: used destination position; heading text did not match.")
        else:
            offset = page_starts[page - 1]
            warnings.append(f"Bookmark {title!r}: used page start; exact heading position unavailable.")
        headings.append({"title": title, "level": level, "start_char": offset})
    return sorted(headings, key=lambda item: item["start_char"])


def _inferred_headings(lines):
    """Best-effort numbered and larger-font headings; not semantic parsing."""
    weights = Counter()
    repetitions = Counter(_normalise(line["text"]) for line in lines)
    for line in lines:
        weights[line["size"]] += len(line["text"])
    if not weights:
        return []
    body_size = weights.most_common(1)[0][0]
    large_sizes = sorted({line["size"] for line in lines
                          if line["size"] >= body_size * 1.15}, reverse=True)
    headings = []
    for line in lines:
        title = line["text"]
        if len(title) > 180 or len(title.split()) > 24:
            continue
        if re.search(r"\.{3,}\s*\d+\s*$", title) or title.isdigit():
            continue
        # Repeated running headers are unlikely to be section boundaries.
        if repetitions[_normalise(title)] > 2:
            continue
        chapter = re.match(r"^(?:chapter|part)\s+(?:\d+|[IVXLCDM]+)\b", title, re.I)
        numbered = re.match(r"^(\d+(?:\.\d+)*)(?:\.?\s+)\S", title)
        if chapter:
            level = 1
        elif numbered:
            level = numbered.group(1).count(".") + 1
        elif line["size"] in large_sizes:
            level = large_sizes.index(line["size"]) + 1
        else:
            continue
        headings.append({"title": title, "level": level, "start_char": line["offset"]})
    return headings


def extract_pdf_structure(pdf_path, *, password=None):
    """Find chapters/sections, write UTF-8 JSON, and return its dictionary.

    Bookmarks take priority; otherwise numbered headings and font sizes are
    heuristics. Counts use Python Unicode characters, including heading text,
    spaces, and one newline per nonempty extracted line. A parent's count
    includes its descendants. start_char is inclusive, end_char exclusive.
    Page numbers are 1-based. Text preceding the first heading is retained as
    a Preamble node. Scanned PDFs require OCR before calling this function.
    Output is saved automatically to AI_tutor/data/<pdf stem>.json.
    """
    source = Path(pdf_path)
    target = Path(__file__).resolve().parents[1] / "data" / f"{source.stem}.json"
    if source.resolve() == target.resolve():
        raise ValueError("The JSON output path must differ from the input PDF.")
    warnings = []
    with pymupdf.open(source) as document:
        if not document.is_pdf:
            raise ValueError("The input must be a PDF document.")
        if document.needs_pass and not document.authenticate(password or ""):
            raise ValueError("The PDF is encrypted; supply a valid password.")
        lines, text, page_starts = _read_lines(document)
        if not text:
            raise ValueError("No extractable text found. Scanned PDFs need OCR first.")
        headings = _bookmark_headings(document, lines, page_starts, warnings)
        method = "bookmarks"
        if not headings:
            headings = _inferred_headings(lines)
            method = "heading_heuristics"
            warnings.append("Heading detection is heuristic; review the inferred hierarchy.")
        if not headings:
            method = "whole_document"
            headings = [{"title": source.stem, "level": 1, "start_char": 0}]
            warnings.append("No headings detected; retained the document as one chapter.")
        elif headings[0]["start_char"] > 0:
            headings.insert(0, {"title": "Preamble", "level": 1, "start_char": 0})
        empty_pages = sorted(set(range(1, len(document) + 1)) - {line["page"] for line in lines})
        if empty_pages:
            warnings.append(f"Pages without extractable text (possibly scanned or blank): {empty_pages}")
        chapters, stack = [], []
        for heading in headings:
            node = dict(heading, end_char=len(text), sections=[])
            while stack and stack[-1]["level"] >= node["level"]:
                stack.pop()["end_char"] = node["start_char"]
            (stack[-1]["sections"] if stack else chapters).append(node)
            stack.append(node)

        def add_counts(nodes):
            for node in nodes:
                node["character_count"] = node["end_char"] - node["start_char"]
                node["start_page"] = bisect_right(page_starts, node["start_char"])
                node["end_page"] = bisect_right(page_starts, max(node["start_char"], node["end_char"] - 1))
                add_counts(node["sections"])

        add_counts(chapters)
        result = {
            "source_pdf": str(source.resolve()), "page_count": len(document),
            "total_characters": len(text), "detection_method": method,
            "character_count_convention": "Unicode characters including headings, spaces, and one newline per nonempty extracted line; parent counts include subsections; end offsets are exclusive.",
            "warnings": warnings, "chapters": chapters,
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path)
    arguments = parser.parse_args()
    result = extract_pdf_structure(arguments.pdf_path)
    print(f"Extracted {len(result['chapters'])} chapters ({result['total_characters']} characters).")
