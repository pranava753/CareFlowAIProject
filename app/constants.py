"""Canonical specialty keys shared across the app.

Keep in sync with the SPECIALTIES list in generate.py, which carries the
richer per-specialty data (procedures, prep instructions, etc.) used only for
corpus/mock-data generation.
"""

SPECIALTY_DISPLAY_NAMES: dict[str, str] = {
    "cardiology": "Cardiology",
    "orthopedics": "Orthopedics",
    "dermatology": "Dermatology",
    "ent": "Ear, Nose & Throat (ENT)",
    "gastroenterology": "Gastroenterology",
    "neurology": "Neurology",
    "endocrinology": "Endocrinology",
    "general_medicine": "General Medicine",
}

SPECIALTY_KEYS: list[str] = list(SPECIALTY_DISPLAY_NAMES.keys())
