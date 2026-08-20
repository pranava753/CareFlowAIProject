from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.constants import SPECIALTY_KEYS


class Channel(str, Enum):
    PHONE_TRANSCRIPT = "phone_transcript"
    WEB_FORM = "web_form"
    EMAIL = "email"
    SMS = "sms"


class Urgency(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class ExtractedIntake(BaseModel):
    """Raw structured-extraction output from the LLM, before post-processing.

    Kept separate from PatientRequest so the LLM's null/empty answers (fields
    truly not stated in the message) are never confused with app-computed
    fields like `missing_fields`.
    """

    patient_name: str | None = None
    specialty: str | None = Field(
        default=None,
        description="One of: " + ", ".join(SPECIALTY_KEYS) + ". Null if not stated or not recognized.",
    )
    symptoms: list[str] = Field(default_factory=list, description="Symptoms/complaints in the patient's own words.")
    urgency: Urgency = Urgency.ROUTINE
    insurance_id: str | None = None
    seeks_clinical_advice: bool = Field(
        default=False,
        description="True if the message asks for a diagnosis, symptom interpretation, or medication/dosing advice.",
    )

    @field_validator("specialty")
    @classmethod
    def _normalize_specialty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().replace(" ", "_")
        return normalized if normalized in SPECIALTY_KEYS else None


class PatientRequest(BaseModel):
    """Validated intake record produced by the Intake Agent (Milestone 1)."""

    channel: Channel
    raw_text: str
    patient_name: str | None = None
    specialty: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    urgency: Urgency = Urgency.ROUTINE
    insurance_id: str | None = None
    seeks_clinical_advice: bool = False
    missing_fields: list[str] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields
