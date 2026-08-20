"""Milestone 3 -- session (short-term) memory.

One JSON file per conversation session under
data/careflow/memory/sessions/{session_id}.json. Purely local/synthetic --
see the Data Handling Standard for the 30-day retention policy this is meant
to model (not enforced here; a scheduled purge job would do that in production).
"""

import json
from datetime import datetime, timezone

from app.config import settings


class SessionMemory:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.path = settings.session_memory_dir / f"{session_id}.json"
        self.turns: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return []

    def add_turn(self, role: str, content: str) -> None:
        self.turns.append(
            {"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.turns, indent=2), encoding="utf-8")

    def as_messages(self) -> list[dict]:
        return [{"role": t["role"], "content": t["content"]} for t in self.turns]
