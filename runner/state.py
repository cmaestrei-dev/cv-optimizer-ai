"""Lo que el bot recuerda entre vueltas: vacantes ya vistas, conteo del día y pausa obligatoria."""

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}
        self.data.setdefault("vistas", {})
        self.data.setdefault("dias", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def seen(self, job_id: str) -> bool:
        return job_id in self.data["vistas"]

    def mark(self, job_id: str, status: str, **extra) -> None:
        self.data["vistas"][job_id] = {"estado": status, "cuando": datetime.now(UTC).isoformat(timespec="seconds"), **extra}

    def today(self, kind: str, on: date | None = None) -> int:
        return self.data["dias"].get((on or date.today()).isoformat(), {}).get(kind, 0)

    def count(self, kind: str, on: date | None = None) -> None:
        day = self.data["dias"].setdefault((on or date.today()).isoformat(), {})
        day[kind] = day.get(kind, 0) + 1

    def pause_until(self) -> datetime | None:
        raw = self.data.get("pausa_hasta")
        return datetime.fromisoformat(raw) if raw else None

    def pause(self, hours: int, reason: str) -> None:
        self.data["pausa_hasta"] = (datetime.now(UTC) + timedelta(hours=hours)).isoformat(timespec="seconds")
        self.data["pausa_motivo"] = reason
