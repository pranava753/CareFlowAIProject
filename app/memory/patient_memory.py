"""Milestone 3 -- long-term patient memory.

Keyed by synthetic patient_id (from data/careflow/mock_ehr/patients.csv --
never a real person). Stores discrete operational facts plus a rolling
LLM-condensed summary, in SQLite via the stdlib sqlite3 module.
"""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.config import settings
from app.llm import chat

_SCHEMA = """
CREATE TABLE IF NOT EXISTS patient_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    fact TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patient_summary (
    patient_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_SUMMARY_PROMPT = """\
Summarize these care-coordination interaction notes for one patient into 2-4 concise sentences a \
scheduling/insurance assistant could use as context next time. Only include operational facts \
(specialties seen, insurance/plan notes, scheduling preferences, open referrals) -- do not add any \
clinical interpretation.

Notes:
{facts}
"""


def _connect() -> sqlite3.Connection:
    settings.careflow_patient_memory_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.careflow_patient_memory_db)
    conn.executescript(_SCHEMA)
    return conn


def add_fact(patient_id: str, fact: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO patient_facts (patient_id, fact, created_at) VALUES (?, ?, ?)",
            (patient_id, fact, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_facts(patient_id: str) -> list[str]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT fact FROM patient_facts WHERE patient_id = ? ORDER BY id", (patient_id,)
        ).fetchall()
    return [r[0] for r in rows]


def get_summary(patient_id: str) -> str | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT summary FROM patient_summary WHERE patient_id = ?", (patient_id,)
        ).fetchone()
    return row[0] if row else None


def resummarize(patient_id: str, model: str | None = None) -> str:
    """Condense all stored facts for a patient into a fresh rolling summary."""
    facts = get_facts(patient_id)
    if not facts:
        return ""
    summary = chat(
        [{"role": "user", "content": _SUMMARY_PROMPT.format(facts="\n".join(f"- {f}" for f in facts))}],
        model=model,
    ).strip()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO patient_summary (patient_id, summary, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(patient_id) DO UPDATE SET summary = excluded.summary, updated_at = excluded.updated_at",
            (patient_id, summary, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    return summary
