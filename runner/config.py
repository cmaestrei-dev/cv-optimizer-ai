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

# geoId de LinkedIn verificados (2026-11-16); cualquier otro lugar se puede dar como número.
GEO_IDS = {"colombia": "100876405", "bogota": "102361989", "bogotá": "102361989", "cartagena": "106336022"}
MODES = ("prueba", "auto")

TEMPLATE = """# Bot de postulación de CV Optimizer. Edita y guarda; luego: python -m runner buscar
api = "https://TU-SERVICIO.run.app/api"   # la dirección de tu app, terminada en /api
modo = "prueba"        # prueba: analiza y prepara el CV, NO envía. auto: postula (cuando exista)
tope_diario = 20       # vacantes por día como máximo
generar_cv = true      # hacer el CV a la medida de cada vacante (usa cupo de IA)

[[busqueda]]
palabras = "analista de operaciones"
lugar = "Colombia"     # Colombia, Bogotá, Cartagena o un geoId de LinkedIn
dias = 1               # 1 = últimas 24 horas, 7 = última semana
solicitud_sencilla = true

[excluir]
palabras = ["senior", "practicante"]   # en el cargo
empresas = []
"""


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
        if not search.geo_id:
            raise ConfigError(f"No conozco el lugar «{search.place}»: usa Colombia, Bogotá, Cartagena o un geoId.")
        if search.days not in (1, 7, 30):
            raise ConfigError("«dias» debe ser 1, 7 o 30.")
        searches.append(search)
    if not searches:
        raise ConfigError("Agrega al menos una [[busqueda]].")
    cap = int(raw.get("tope_diario", 20))
    if not 1 <= cap <= 50:
        raise ConfigError("«tope_diario» debe estar entre 1 y 50.")
    exclude = raw.get("excluir", {})
    return Config(
        api=api, token=_token(), mode=mode, daily_cap=cap, make_cv=bool(raw.get("generar_cv", True)), searches=searches,
        exclude_words=[str(w).lower() for w in exclude.get("palabras", [])],
        exclude_companies=[str(c).lower() for c in exclude.get("empresas", [])],
    )
