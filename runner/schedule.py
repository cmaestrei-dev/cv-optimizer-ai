"""Programar el bot con un temporizador de systemd del usuario (sin root): cada hora elegida corre
`python -m runner diario`. La ventana del bot se abre en la sesión gráfica de la persona, así que el computador
debe estar encendido y con la sesión iniciada; si estaba apagado a la hora, la vuelta corre al encender.
"""

import re
import shutil
import subprocess
from pathlib import Path

NAME = "cv-optimizer-bot"
UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
DEFAULT_TIMES = ["09:17", "15:47"]
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    """No se puede programar: el mensaje dice qué corregir."""


def normalize_times(times: list[str]) -> list[str]:
    out = []
    for raw in times:
        match = _TIME.match(raw.strip())
        if not match:
            raise ScheduleError(f"«{raw}» no es una hora válida (usa HH:MM, p. ej. 9:17 o 15:47).")
        out.append(f"{int(match.group(1)):02d}:{match.group(2)}")
    if not out:
        raise ScheduleError("Indica al menos una hora.")
    return sorted(set(out))


def _check_path(path: Path) -> None:
    # systemd interpreta «%» y separa por espacios: se exigen rutas simples
    if re.search(r"[\s%\"'\\]", str(path)):
        raise ScheduleError(f"La ruta «{path}» tiene espacios o símbolos que systemd no admite; usa otra carpeta.")


def unit_files(python: str, workdir: Path, times: list[str], log: Path) -> dict[str, str]:
    for path in (Path(python), workdir, log):
        _check_path(path)
    if "/.claude/worktrees/" in f"{workdir}/":
        raise ScheduleError("Ese código está en una carpeta temporal de trabajo; programa desde una copia estable.")
    calendars = "\n".join(f"OnCalendar=*-*-* {t}:00" for t in normalize_times(times))
    service = f"""[Unit]
Description=Bot de postulación de CV Optimizer (una vuelta: buscar y postular)

[Service]
Type=oneshot
WorkingDirectory={workdir}
ExecStart={python} -m runner diario
Environment=PYTHONUNBUFFERED=1
StandardOutput=append:{log}
StandardError=append:{log}
TimeoutStartSec=4h
"""
    timer = f"""[Unit]
Description=Vueltas diarias del bot de CV Optimizer

[Timer]
{calendars}
Persistent=true

[Install]
WantedBy=timers.target
"""
    return {f"{NAME}.service": service, f"{NAME}.timer": timer}


def _systemctl(*args: str) -> str:
    if not shutil.which("systemctl"):
        raise ScheduleError("Este sistema no tiene systemd: programa `python -m runner diario` con cron.")
    done = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=30, check=False)
    if done.returncode != 0:
        raise ScheduleError(f"systemctl {' '.join(args)}: {(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout


def install(python: str, workdir: Path, times: list[str], log: Path) -> str:
    """Escribe el servicio y el temporizador, los activa y devuelve la próxima vuelta (texto de systemd)."""
    files = unit_files(python, workdir, times, log)
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (UNIT_DIR / name).write_text(text, encoding="utf-8")
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", f"{NAME}.timer")
    return status()


def status() -> str:
    lines = _systemctl("list-timers", f"{NAME}.timer", "--no-pager").splitlines()
    return lines[1].strip() if len(lines) > 1 and NAME in lines[1] else ""


def remove() -> None:
    if (UNIT_DIR / f"{NAME}.timer").exists():
        _systemctl("disable", "--now", f"{NAME}.timer")
    for name in (f"{NAME}.service", f"{NAME}.timer"):
        (UNIT_DIR / name).unlink(missing_ok=True)
    _systemctl("daemon-reload")
