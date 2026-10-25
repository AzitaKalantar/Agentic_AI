"""Partition chapter text at subsection boundaries without loss or overlap."""
from dataclasses import dataclass

from .chapter_parser import Chapter


@dataclass(frozen=True)
class SubsectionChunk:
    title: str
    text: str
    start_char: int
    end_char: int


def chunk_chapter(chapter: Chapter) -> list[SubsectionChunk]:
    """Use every nested heading as a boundary; retain parent introductions.

    A chapter without sections becomes one chunk. Large sections are left intact
    so an arbitrary character limit cannot split a concept.
    """
    start = chapter.outline["start_char"]
    end = chapter.outline["end_char"]
    boundaries = {start: chapter.title}

    def collect(nodes):
        for node in nodes:
            if start <= node["start_char"] < end:
                boundaries[node["start_char"]] = node["title"]
            collect(node["sections"])

    collect(chapter.outline["sections"])
    offsets = sorted(boundaries)
    chunks = []
    for left, right in zip(offsets, offsets[1:] + [end]):
        if right > left:
            chunks.append(SubsectionChunk(boundaries[left], chapter.text[left-start:right-start], left, right))
    if "".join(chunk.text for chunk in chunks) != chapter.text:
        raise ValueError("Chapter offsets do not match extracted text.")
    return chunks
