"""Configuración del bot: un TOML en ~/.config/cv-optimizer-bot/config.toml y el token aparte (0600)."""

import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("CVO_BOT_CONFIG_DIR", Path.home() / ".config" / "cv-optimizer-bot"))
DATA_DIR = Path(os.environ.get("CVO_BOT_DATA_DIR", Path.home() / ".local" / "share" / "cv-optimizer-bot"))
CONFIG_FILE = CONFIG_DIR / "config.toml"
TOKEN_FILE = CONFIG_DIR / "token"

# geoId de LinkedIn verificados (2026-11-16). Cualquier otro lugar va por nombre («Medellín, Antioquia, Colombia»)
# o como geoId numérico.
GEO_IDS = {"colombia": "100876405", "bogota": "102361989", "bogotá": "102361989", "cartagena": "106336022"}
MODES = ("prueba", "auto")

TEMPLATE = """# Bot de postulación de CV Optimizer. Edita y guarda; luego: python -m runner buscar
api = "https://TU-SERVICIO.run.app/api"   # la dirección de tu app, terminada en /api
modo = "prueba"        # prueba: llega a la revisión y descarta, NO envía. auto: postula y lo registra
tope_diario = 20       # vacantes por día como máximo
generar_cv = true      # hacer el CV a la medida de cada vacante (usa cupo de IA)
sin_evidencia = "saltar"   # «¿cuántos años con X?» si tu perfil no muestra X: "saltar" la vacante o responder "cero"
pausa_entre_envios_seg = [120, 240]   # espera al azar entre dos envíos

[[busqueda]]
palabras = "analista de operaciones"
lugar = "Colombia"     # Colombia, Bogotá, Cartagena, «Medellín, Antioquia, Colombia» o un geoId
dias = 1               # 1 = últimas 24 horas, 7 = última semana
solicitud_sencilla = true

[excluir]
palabras = ["senior", "lead"]   # palabras completas del cargo que no te interesan
empresas = []

# Respuestas tuyas para las preguntas del formulario que tu perfil no responde. Clave: partes de la pregunta,
# separadas por «|», sin tildes ni mayúsculas. Lo que no esté aquí lo responde la app con tu perfil (verificado);
# si nadie lo sabe, la vacante se salta: nunca se responde al azar.
[respuestas]
"aspiracion salarial|salario|expectativa salarial|salary" = "3000000"
"disponibilidad|cuando puedes empezar|fecha de inicio|start date" = "Inmediata"
"""


GENERAL_KEYS = {"api", "modo", "tope_diario", "generar_cv", "sin_evidencia", "pausa_entre_envios_seg"}


class ConfigError(ValueError):
    """La configuración falta o tiene un error: el mensaje dice qué corregir."""


@dataclass(frozen=True)
class Search:
    keywords: str
    place: str = "Colombia"
    days: int = 1
    easy_apply: bool = True

    @property
    def geo_id(self) -> str:
        key = self.place.strip().lower()
        return key if key.isdigit() else GEO_IDS.get(key, "")


@dataclass(frozen=True)
class Config:
    api: str
    token: str
    mode: str = "prueba"
    daily_cap: int = 20
    make_cv: bool = True
    searches: list[Search] = field(default_factory=list)
    exclude_words: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)  # banco: «patrón|patrón» → respuesta
    no_evidence: str = "saltar"  # años con una tecnología que el perfil no muestra: "saltar" la vacante o "cero"
    pause_seconds: tuple[int, int] = (120, 240)  # entre envíos


def write_template() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(TEMPLATE, encoding="utf-8")
    return CONFIG_FILE


def save_token(token: str) -> Path:
    token = token.strip()
    if not token.startswith("cvb_"):
        raise ConfigError("Ese no parece un token del bot (empieza por cvb_). Créalo en la app: Perfil → Bot de LinkedIn.")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token + "\n")
    os.chmod(TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)
    return TOKEN_FILE


def _token() -> str:
    if token := os.environ.get("CVO_BOT_TOKEN", "").strip():
        return token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    raise ConfigError("Falta el token del bot: python -m runner token (créalo en la app: Perfil → Bot de LinkedIn).")


def load(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        raise ConfigError(f"No hay configuración: python -m runner configurar (crea {path}).")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Error en {path}: {e}") from None
    # En TOML, lo que se escribe debajo de una tabla queda dentro de ella: «sin_evidencia» puesto tras [respuestas]
    # sería una «pregunta». Las opciones generales se suben a su lugar.
    for table in ("respuestas", "excluir"):
        if isinstance(raw.get(table), dict):
            for key in GENERAL_KEYS & raw[table].keys():
                raw.setdefault(key, raw[table].pop(key))
    api = str(raw.get("api", "")).strip().rstrip("/")
    if not api.startswith("https://") and not api.startswith("http://localhost"):
        raise ConfigError("«api» debe ser la dirección https de tu app, terminada en /api.")
    if "TU-SERVICIO" in api:
        raise ConfigError("Cambia «api» en la configuración por la dirección de tu app.")
    mode = str(raw.get("modo", "prueba")).strip().lower()
    if mode not in MODES:
        raise ConfigError(f"«modo» debe ser uno de: {', '.join(MODES)}.")
    searches = []
    for item in raw.get("busqueda", []):
        search = Search(keywords=str(item.get("palabras", "")).strip(), place=str(item.get("lugar", "Colombia")),
                        days=int(item.get("dias", 1)), easy_apply=bool(item.get("solicitud_sencilla", True)))
        if not search.keywords:
            raise ConfigError("Cada [[busqueda]] necesita «palabras».")
        if not search.place.strip():
            raise ConfigError("Cada [[busqueda]] necesita «lugar».")
        if search.days not in (1, 7, 30):
            raise ConfigError("«dias» debe ser 1, 7 o 30.")
        searches.append(search)
    if not searches:
        raise ConfigError("Agrega al menos una [[busqueda]].")
    cap = int(raw.get("tope_diario", 20))
    if not 1 <= cap <= 50:
        raise ConfigError("«tope_diario» debe estar entre 1 y 50.")
    exclude = raw.get("excluir", {})
    no_evidence = str(raw.get("sin_evidencia", "saltar")).strip().lower()
    if no_evidence not in ("saltar", "cero"):
        raise ConfigError("«sin_evidencia» debe ser \"saltar\" o \"cero\".")
    pause = raw.get("pausa_entre_envios_seg", [120, 240])
    if not (isinstance(pause, list) and len(pause) == 2 and 30 <= int(pause[0]) <= int(pause[1])):
        raise ConfigError("«pausa_entre_envios_seg» debe ser [mínimo, máximo] en segundos, desde 30.")
    return Config(
        api=api, token=_token(), mode=mode, daily_cap=cap, make_cv=bool(raw.get("generar_cv", True)), searches=searches,
        exclude_words=[str(w).lower() for w in exclude.get("palabras", [])],
        exclude_companies=[str(c).lower() for c in exclude.get("empresas", [])],
        answers={str(k): str(v) for k, v in raw.get("respuestas", {}).items()},
        no_evidence=no_evidence, pause_seconds=(int(pause[0]), int(pause[1])),
    )
