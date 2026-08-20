"""Milestone 2 -- flag-for-human tool.

Mock human-escalation queue: appends a ticket to human_queue.jsonl. A real
deployment would push this to a ticketing system; for this project the JSONL
file stands in for that outbox.
"""

import json
from datetime import datetime, timezone

from app.config import settings


def flag_for_human(reason: str, message_text: str, patient_id: str | None = None) -> dict:
    settings.human_queue_path.parent.mkdir(parents=True, exist_ok=True)
    ticket = {
        "flagged_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "message_text": message_text,
        "patient_id": patient_id,
    }
    with settings.human_queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ticket) + "\n")
    return {"success": True, "ticket": ticket}
