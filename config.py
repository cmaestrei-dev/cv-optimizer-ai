import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_API_VERSION = "v1beta"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 5

PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v3")

PDF_PAGE_SIZE = os.getenv("PDF_PAGE_SIZE", "A4")
PDF_ENCODING = "UTF-8"

MIN_PASSWORD_LENGTH = 6

SKILL_CATEGORIES = [
    "Lenguajes de Programación",
    "Frameworks / Librerías",
    "Bases de Datos",
    "Herramientas / DevOps",
    "Metodologías / Soft Skills",
    "Otros",
]

WORK_MODALITIES = ["Remoto", "Híbrido", "Presencial"]
