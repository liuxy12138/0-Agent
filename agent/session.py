import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, root: str = "data/sessions") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        if not path.exists():
            return {
                "session_id": session_id,
                "messages": [],
                "tasks": {},
                "trace": [],
                "created_at": self._now(),
                "updated_at": self._now(),
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, session: dict[str, Any]) -> None:
        session["updated_at"] = self._now()
        self._path(session["session_id"]).write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in session_id)
        return self.root / f"{safe}.json"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
