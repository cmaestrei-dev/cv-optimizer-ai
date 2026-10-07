import re
import unicodedata
from dataclasses import dataclass
from datetime import date

_MONTHS = {
    "enero": 1, "ene": 1, "january": 1, "jan": 1,
    "febrero": 2, "feb": 2, "february": 2,
    "marzo": 3, "mar": 3, "march": 3,
    "abril": 4, "abr": 4, "april": 4, "apr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6, "june": 6,
    "julio": 7, "jul": 7, "july": 7,
    "agosto": 8, "ago": 8, "august": 8, "aug": 8,
    "septiembre": 9, "setiembre": 9, "sep": 9, "sept": 9, "september": 9,
    "octubre": 10, "oct": 10, "october": 10,
    "noviembre": 11, "nov": 11, "november": 11,
    "diciembre": 12, "dic": 12, "december": 12, "dec": 12,
}
_CURRENT_WORDS = ("presente", "actual", "actualidad", "hoy", "fecha", "present", "current", "now", "date")
_RANGE_SEPARATOR = re.compile(r"\s+(?:-|–|—|a|al|hasta|to)\s+|(?<=\d)\s*[-–—]\s*(?=\d|[a-z])")


@dataclass(frozen=True)
class Period:
    start_year: int | None = None
    start_month: int | None = None
    end_year: int | None = None
    end_month: int | None = None
    is_current: bool = False

    def months(self, today: date | None = None) -> int | None:
        """Duración aproximada en meses (inclusiva); None si faltan fechas."""
        if self.start_year is None:
            return None
        today = today or date.today()
        end_year, end_month = (
            (today.year, today.month) if self.is_current else (self.end_year, self.end_month)
        )
        if end_year is None:
            end_year, end_month = self.start_year, self.start_month
        start_month = self.start_month or 1
        end_month = end_month or 12
        return max(0, (end_year - self.start_year) * 12 + end_month - start_month + 1)

    @property
    def sort_key(self) -> tuple[int, int]:
        """Para ordenar de más reciente a más antiguo: (fin, inicio) como AAAAMM."""
        end = 999999 if self.is_current else (self.end_year or self.start_year or 0) * 100 + (
            self.end_month or 12
        )
        start = (self.start_year or 0) * 100 + (self.start_month or 1)
        return end, start


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).strip(" ()[].")


def _parse_point(text: str) -> tuple[int | None, int | None]:
    text = _normalize(text)
    numeric = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{4})", text)
    if numeric:
        return int(numeric.group(2)), int(numeric.group(1))
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    year = int(year_match.group(0)) if year_match else None
    month = next(
        (num for word in re.findall(r"[a-z]+", text) if (num := _MONTHS.get(word))), None
    )
    return year, month


def parse_period(text: str) -> Period:
    """'Febrero 2024 - Presente', '2022-2027', '01/2020 – 06/2021', '(2025-2026)'..."""
    cleaned = _normalize(text)
    if not cleaned:
        return Period()
    parts = _RANGE_SEPARATOR.split(cleaned, maxsplit=1)
    start_year, start_month = _parse_point(parts[0])
    if len(parts) == 1:
        return Period(start_year, start_month, start_year, start_month)
    end_text = parts[1]
    if any(word in end_text for word in _CURRENT_WORDS):
        return Period(start_year, start_month, is_current=True)
    end_year, end_month = _parse_point(end_text)
    return Period(start_year, start_month, end_year, end_month)
