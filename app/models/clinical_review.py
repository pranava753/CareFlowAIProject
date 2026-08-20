from pydantic import BaseModel, Field


class ClinicalReviewVerdict(BaseModel):
    """Structured output of the Clinical Safety Reviewer agent (Milestone 6)."""

    requires_human_review: bool
    rationale: str = ""
    matched_signals: list[str] = Field(default_factory=list)
