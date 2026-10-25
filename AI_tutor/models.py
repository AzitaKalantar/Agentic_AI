"""Structured lesson planner output."""
from pydantic import BaseModel, ConfigDict, Field


class LessonDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    concepts: list[str] = Field(min_length=1, max_length=3)
    source_text: str = Field(min_length=1)
    estimated_minutes: int = Field(ge=10, le=20)
    previous_knowledge: list[str] = Field(default_factory=list)


class PlannerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed_lessons: list[LessonDraft]
    remaining_material: str


class LessonPlan(BaseModel):
    """Source offsets are chapter-relative; start inclusive, end exclusive."""
    model_config = ConfigDict(extra="forbid")
    lesson_number: int = Field(ge=1)
    title: str = Field(min_length=1)
    concepts: list[str] = Field(min_length=1, max_length=3)
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    estimated_minutes: int = Field(ge=10, le=20)
    previous_knowledge: list[str]


class ChapterPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_number: int = Field(ge=1)
    chapter_title: str
    lessons: list[LessonPlan]
