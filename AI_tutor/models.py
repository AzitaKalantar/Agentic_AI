"""Public lesson plans and internal buffered-planning output."""
from pydantic import BaseModel, ConfigDict, Field


class LessonPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lesson_number: int
    title: str
    learning_objective: str
    concepts: list[str]
    source_chunks: list[str]
    source_scope: str
    estimated_minutes: int
    depends_on: list[int]


class ChapterLessonPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_title: str
    lessons: list[LessonPlan]


class LessonDraft(BaseModel):
    """Internal source text allows exact coverage checks and chunk mapping."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    learning_objective: str = Field(min_length=1)
    concepts: list[str] = Field(min_length=1)
    source_text: str = Field(min_length=1)
    source_scope: str = Field(min_length=1)
    estimated_minutes: int = Field(gt=0)
    depends_on: list[int]


class PlannerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed_lessons: list[LessonDraft]
    remaining_material: str
