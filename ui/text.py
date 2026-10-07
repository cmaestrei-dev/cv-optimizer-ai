"""Texto de terceros (vacantes traídas de internet, respuestas de la IA) mostrado con st.markdown."""

import re

_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!|<>~$:])")


def md(text: str) -> str:
    """Escapa Markdown y directivas de Streamlit (:red[...]) para que se vea literal: sin enlaces,
    imágenes remotas ni formato inyectado por la página de la vacante."""
    return _SPECIAL.sub(r"\\\1", text or "")
