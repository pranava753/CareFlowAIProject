from pydantic import BaseModel, Field


class GroundednessResult(BaseModel):
    is_grounded: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class RAGAnswer(BaseModel):
    question: str
    answer: str
    citations: list[str] = Field(default_factory=list)
    is_grounded: bool
    flagged: bool = False
