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
EXTRA_ANSWERS_FILE = CONFIG_DIR / "respuestas_extra.json"  # las que das por Telegram (las escribe ese bot)

# geoId de LinkedIn verificados (2026-11-16). Cualquier otro lugar va por nombre («Medellín, Antioquia, Colombia»)
# o como geoId numérico.
GEO_IDS = {"colombia": "100876405", "bogota": "102361989", "bogotá": "102361989", "cartagena": "106336022"}
MODES = ("prueba", "auto")
PORTALS = {"linkedin": "LinkedIn", "computrabajo": "Computrabajo", "magneto": "Magneto", "elempleo": "elempleo"}
DAYS = {"linkedin": (1, 7, 30), "computrabajo": (1, 3, 7, 15, 30), "magneto": (1, 3, 7, 15, 30),
        "elempleo": (1, 7, 15, 30)}

TEMPLATE = """# Bot de postulación de CV Optimizer. Edita y guarda; luego: python -m runner buscar
api = "https://TU-SERVICIO.run.app/api"   # la dirección de tu app, terminada en /api
modo = "prueba"        # prueba: llega a la revisión y descarta, NO envía. auto: postula y lo registra
tope_diario = 20       # vacantes por día como máximo
generar_cv = true      # hacer el CV a la medida de cada vacante (usa cupo de IA)
sin_evidencia = "saltar"   # «¿tienes experiencia con X?» si tu perfil no muestra X: "saltar" la vacante, "cero" (No / 0) o "si"
experiencia_por_defecto = 2   # con sin_evidencia = "si": años que se responden si tu perfil no muestra más
pausa_entre_envios_seg = [120, 240]   # espera al azar entre dos envíos

[[busqueda]]
palabras = "analista de operaciones"
lugar = "Colombia"     # Colombia, Bogotá, Cartagena, «Medellín, Antioquia, Colombia» o un geoId
dias = 1               # 1 = últimas 24 horas, 7 = última semana
solicitud_sencilla = true

[[busqueda]]
portal = "computrabajo"   # linkedin (si no se dice), computrabajo, magneto o elempleo
palabras = "analista de operaciones"
lugar = "Colombia"        # Colombia, Remoto, Cartagena, Medellín, Bogotá…
dias = 1                  # 1, 3, 7, 15 o 30

[computrabajo]
tope_diario = 20             # aparte del de LinkedIn
compatibilidad_minima = 60   # debajo de esto la vacante se descarta en la app (con el motivo) y no se hace CV
cv_general = ""              # PDF que queda por defecto entre postulaciones (sin él, el bot no postula en Computrabajo)

[magneto]
tope_diario = 20             # aparte de los otros portales (Magneto envía tu perfil de Magneto, no un PDF)
compatibilidad_minima = 60

[elempleo]
tope_diario = 20             # elempleo envía tu hoja de vida de elempleo (con el CV que tengas adjunto allá)
compatibilidad_minima = 60   # en elempleo, «dias» es 1 (hoy y ayer), 7, 15 o 30

[excluir]
palabras = ["senior", "lead"]   # palabras completas del cargo que no te interesan
empresas = []
# solo_idiomas = ["es"]   # omite las vacantes escritas en otros idiomas…
# salvo_pais = "Colombia" # …salvo las de este país (antes de hacer el CV)

# Opcional: solo se analizan (con IA) las vacantes cuyo cargo tiene alguna de estas palabras. Una palabra corta
# («ti», «qa») cuenta completa; una larga, al comienzo de una palabra («desarroll» → «desarrollador»).
# [incluir]
# palabras = ["software", "desarroll", "sistemas", "tecnolog", "datos", "soporte", "ti", "qa"]

# Respuestas tuyas para las preguntas del formulario que tu perfil no responde. Clave: partes de la pregunta,
# separadas por «|», sin tildes ni mayúsculas. Lo que no esté aquí lo responde la app con tu perfil (verificado);
# si nadie lo sabe, la vacante se salta: nunca se responde al azar.
[respuestas]
"aspiracion salarial|salario|expectativa salarial|salary" = "3000000"
"cuando puedes empezar|cuando podrias empezar|fecha de inicio|disponibilidad de inicio|start date" = "Inmediata"
"trabajar presencial|modalidad presencial|disponibilidad de horario|disponibilidad horaria" = "Sí"
"""


GENERAL_KEYS = {"api", "modo", "tope_diario", "generar_cv", "sin_evidencia", "experiencia_por_defecto",
                "pausa_entre_envios_seg", "compatibilidad_minima"}


class ConfigError(ValueError):
    """La configuración falta o tiene un error: el mensaje dice qué corregir."""


@dataclass(frozen=True)
class Search:
    keywords: str
    place: str = "Colombia"
    days: int = 1
    easy_apply: bool = True  # solo LinkedIn
    portal: str = "linkedin"

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
    include_words: list[str] = field(default_factory=list)  # si hay, el cargo debe tener alguna (antes de gastar IA)
    languages: list[str] = field(default_factory=list)  # idiomas de vacante aceptados («es»); vacío = todos
    home_country: str = ""  # en este país se acepta cualquier idioma (p. ej. una vacante en inglés en Colombia)
    answers: dict[str, str] = field(default_factory=dict)  # banco: «patrón|patrón» → respuesta
    no_evidence: str = "saltar"  # experiencia que el perfil no muestra: "saltar" la vacante, "cero" o "si"
    default_years: int = 2  # con "si": años que se responden si el perfil no muestra más
    pause_seconds: tuple[int, int] = (120, 240)  # entre envíos
    portal_caps: dict[str, int] = field(default_factory=dict)  # tope diario de cada portal (LinkedIn: daily_cap)
    min_scores: dict[str, int] = field(default_factory=dict)  # compatibilidad mínima de cada portal (0 = sin mínimo)
    general_cvs: dict[str, str] = field(default_factory=dict)  # PDF general fijo de cada portal (Computrabajo)

    def cap(self, portal: str) -> int:
        return self.daily_cap if portal == "linkedin" else self.portal_caps.get(portal, 20)

    def min_score(self, portal: str) -> int:
        return self.min_scores.get(portal, 0)


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


def _extra_answers() -> dict[str, str]:
    import json

    try:
        data = json.loads(EXTRA_ANSWERS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def load(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        raise ConfigError(f"No hay configuración: python -m runner configurar (crea {path}).")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Error en {path}: {e}") from None
    # En TOML, lo que se escribe debajo de una tabla queda dentro de ella: «sin_evidencia» puesto tras [respuestas]
    # sería una «pregunta». Las opciones generales se suben a su lugar.
    for table in ("respuestas", "excluir", "incluir"):
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
        portal = str(item.get("portal", "linkedin")).strip().lower()
        if portal not in PORTALS:
            raise ConfigError(f"«portal» debe ser uno de: {', '.join(PORTALS)}.")
        search = Search(keywords=str(item.get("palabras", "")).strip(), place=str(item.get("lugar", "Colombia")),
                        days=int(item.get("dias", 1)), easy_apply=bool(item.get("solicitud_sencilla", True)),
                        portal=portal)
        if not search.keywords:
            raise ConfigError("Cada [[busqueda]] necesita «palabras».")
        if not search.place.strip():
            raise ConfigError("Cada [[busqueda]] necesita «lugar».")
        if search.days not in DAYS[portal]:
            raise ConfigError(f"En {PORTALS[portal]}, «dias» debe ser {', '.join(map(str, DAYS[portal]))}.")
        searches.append(search)
    if not searches:
        raise ConfigError("Agrega al menos una [[busqueda]].")
    cap = int(raw.get("tope_diario", 20))
    if not 1 <= cap <= 50:
        raise ConfigError("«tope_diario» debe estar entre 1 y 50.")
    portal_caps, min_scores, general_cvs = {}, {}, {}
    for portal, rules in ((p, raw.get(p, {})) for p in PORTALS if p != "linkedin"):
        portal_caps[portal] = int(rules.get("tope_diario", 20))
        min_scores[portal] = int(rules.get("compatibilidad_minima", 0))
        if general := str(rules.get("cv_general", "")).strip():
            general_cvs[portal] = str(Path(general).expanduser())
        if not 1 <= portal_caps[portal] <= 50:
            raise ConfigError(f"[{portal}] «tope_diario» debe estar entre 1 y 50.")
    min_scores["linkedin"] = int(raw.get("compatibilidad_minima", 0))
    if not all(0 <= m <= 100 for m in min_scores.values()):
        raise ConfigError("«compatibilidad_minima» debe estar entre 0 y 100.")
    exclude = raw.get("excluir", {})
    include = raw.get("incluir", {})
    no_evidence = str(raw.get("sin_evidencia", "saltar")).strip().lower()
    if no_evidence not in ("saltar", "cero", "si", "sí"):
        raise ConfigError("«sin_evidencia» debe ser \"saltar\", \"cero\" o \"si\".")
    default_years = int(raw.get("experiencia_por_defecto", 2))
    if not 0 <= default_years <= 10:
        raise ConfigError("«experiencia_por_defecto» debe estar entre 0 y 10 años.")
    pause = raw.get("pausa_entre_envios_seg", [120, 240])
    if not (isinstance(pause, list) and len(pause) == 2 and 30 <= int(pause[0]) <= int(pause[1])):
        raise ConfigError("«pausa_entre_envios_seg» debe ser [mínimo, máximo] en segundos, desde 30.")
    return Config(
        api=api, token=_token(), mode=mode, daily_cap=cap, make_cv=bool(raw.get("generar_cv", True)), searches=searches,
        exclude_words=[str(w).lower() for w in exclude.get("palabras", [])],
        exclude_companies=[str(c).lower() for c in exclude.get("empresas", [])],
        include_words=[str(w).strip().lower() for w in include.get("palabras", []) if str(w).strip()],
        languages=[str(x).strip().lower()[:2] for x in exclude.get("solo_idiomas", []) if str(x).strip()],
        home_country=str(exclude.get("salvo_pais", "")).strip(),
        answers={**{str(k): str(v) for k, v in raw.get("respuestas", {}).items()}, **_extra_answers()},
        no_evidence=no_evidence.replace("sí", "si"), default_years=default_years, pause_seconds=(int(pause[0]), int(pause[1])),
        portal_caps=portal_caps, min_scores=min_scores, general_cvs=general_cvs,
    )
