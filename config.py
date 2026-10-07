import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 5
LLM_TIMEOUT_SECONDS = (10, 90)  # (conexión, respuesta)

PDF_PAGE_SIZE = os.getenv("PDF_PAGE_SIZE", "A4")

MIN_PASSWORD_LENGTH = 8

SKILL_CATEGORIES = [
    "Herramientas y software",
    "Conocimientos del área",
    "Procesos y metodologías",
    "Idiomas",
    "Habilidades blandas",
    "Otros",
]

WORK_MODALITIES = ["Remoto", "Híbrido", "Presencial"]
