"""Postular en elempleo con la sesión de la persona (navegador del bot): el botón «Postularme a oferta».

Lo verificado leyendo su página y su código, sin postular (2026-11-21):
- La sesión es la cookie `.ELEMPLEO`, que dura lo que dura el navegador: el perfil del bot reabre la sesión
  anterior al arrancar y así se conserva. Con sesión, la página trae «Cerrar sesión» (`/co/Account/LogOff`).
- «Postularme a oferta» (`.js-apply-offer`) hace `POST /co/JobOffers/JobOfferDetail/Save?jobOfferId=<id>` solo con
  el token antifalsificación de la página: sin revisión ni preguntas de filtro. Responde JSON con `Response` y `Url`:
  2 = postulada y la empresa pide seguir en su sitio (`Url`; la página la abre en otra pestaña);
  3 = hoja de vida incompleta; 4 = ya postulada; 5 = la página lleva a otra dirección; lo demás = postulada.
  El bot hace esa misma petición desde la página (no abre el sitio de la empresa: se lo pasa a la persona).
- Las ofertas de «postulación rápida» (`data-is-quick-offer-application="True"`) abren un formulario con adjuntos.
  Ninguna de 58 ofertas de tecnología lo era: el bot no las hace y se las pasa a la persona.
- Ya postulada: `#hdnvars` trae `"offerapplied": true`. Si la empresa usa videocuestionario (Vprez), la página
  trae su dirección en `#vprezInputHidden`: eso lo hace la persona.
- elempleo envía la hoja de vida de elempleo (con el CV general adjunto), no un PDF por vacante: el CV de la
  vacante queda en la app como referencia.
- Ante una verificación (captcha) se detiene; nunca la resuelve.
"""

import json
import time
from collections.abc import Callable
from pathlib import Path

from runner.linkedin import ApplyResult, Question

SAVE = "/JobOffers/JobOfferDetail/Save"
LOGOFF = "a[href*='/Account/LogOff']"
BLOCKED = ("captcha", "challenge", "/iniciar-sesion", "/Account/Login")

Answerer = Callable[[list[Question]], dict[str, str]]

# La petición de la función de postular de la página (jQuery: POST con el primer token antifalsificación de la página).
# Se hace sin sus pasos siguientes (aviso de tratamiento de datos, abrir el sitio de la empresa, cambiar de página),
# que se llevarían la respuesta antes de poder leerla.
_POST = """async (url) => {
  const field = document.querySelector('input[name="__RequestVerificationToken"]');
  const body = new URLSearchParams({__RequestVerificationToken: field ? field.value : ''});
  const r = await fetch(url, {method: 'POST', body, credentials: 'same-origin',
    headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json, text/javascript, */*; q=0.01'}});
  return {status: r.status, text: await r.text()};
}"""


def _flags(page) -> dict:
    """Las banderas que la página deja en `#hdnvars` (p. ej. si ya se postuló)."""
    field = page.locator("#hdnvars")
    try:
        return json.loads(field.first.get_attribute("value") or "{}") if field.count() else {}
    except ValueError:
        return {}


def _attr(page, selector: str, name: str) -> str:
    found = page.locator(selector)
    return (found.first.get_attribute(name) or "").strip() if found.count() else ""


def _blocked(url: str) -> bool:
    return any(part.lower() in url.lower() for part in BLOCKED)


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool) -> ApplyResult:
    """Postula a una oferta de elempleo. `cv_pdf` no se envía (elempleo usa tu hoja de vida); queda en la app."""
    response = page.goto(offer_url, wait_until="domcontentloaded")
    time.sleep(3)
    if response is not None and response.status in (404, 410):
        return ApplyResult("saltada", "La oferta ya no está en elempleo")
    if "/ofertas-trabajo/" not in page.url:  # elempleo llevó a otra página
        if _blocked(page.url):
            if "captcha" in page.url.lower() or "challenge" in page.url.lower():
                return ApplyResult("verificacion", "elempleo pidió una verificación: entra tú y complétala")
            return ApplyResult("sin_sesion", "elempleo pidió iniciar sesión: python -m runner entrar elempleo")
        return ApplyResult("saltada", "La oferta ya no está en elempleo (llevó a otra página)")
    if not page.locator(LOGOFF).count():
        return ApplyResult("sin_sesion", "El navegador del bot no tiene sesión de elempleo: python -m runner entrar elempleo")
    if _flags(page).get("offerapplied"):
        return ApplyResult("ya_postulada")
    if not page.locator(".js-apply-offer").count():
        return ApplyResult("saltada", "La oferta no tiene «Postularme a oferta» (¿cerrada o con postulación especial?)")
    if _attr(page, "input.js-config", "data-is-quick-offer-application").lower() == "true":
        return ApplyResult("externa", "Oferta de «postulación rápida» con adjuntos: el bot no la hace",
                           follow_up="Postúlate tú en elempleo (postulación rápida con adjuntos).")
    video = _attr(page, "#vprezInputHidden", "data-vprez-url")
    if not submit:
        return ApplyResult("revisada", "Modo prueba: todo listo y no se envió" + (" (pide videocuestionario)" if video else ""))
    target = _attr(page, ".js-apply-offer", "data-url")
    if SAVE not in target:
        return ApplyResult("error", "No encontré la dirección de «Postularme a oferta» en la página")
    try:
        reply = page.evaluate(_POST, target)
    except Exception as e:  # noqa: BLE001 — sin respuesta no se sabe si se postuló: que lo revise la persona
        return ApplyResult("error", f"elempleo no respondió al postular ({str(e)[:80]})")
    try:
        data = json.loads(reply.get("text") or "")
    except ValueError:  # una página en vez de JSON: verificación o sesión vencida
        status = reply.get("status")
        return ApplyResult("verificacion" if status in (403, 429) else "error",
                           f"elempleo respondió {status} sin el resultado de la postulación")
    if not isinstance(data, dict) or data.get("ModelInvalid"):
        return ApplyResult("error", "elempleo no aceptó la postulación (datos inválidos)")
    code, where = data.get("Response"), str(data.get("Url") or "")
    if code == 3:
        return ApplyResult("perfil", "elempleo dice que tu hoja de vida está incompleta: complétala en elempleo")
    if code == 4:
        return ApplyResult("ya_postulada")
    if code == 5:
        if _blocked(where):
            return ApplyResult("sin_sesion", "elempleo pidió iniciar sesión: python -m runner entrar elempleo")
        return ApplyResult("error", f"elempleo llevó a otra página en vez de postular ({where.split('?')[0][:120]})")
    time.sleep(4)
    page.goto(offer_url, wait_until="domcontentloaded")
    time.sleep(2)
    confirmed = bool(_flags(page).get("offerapplied"))
    detail = "Confirmada en la oferta" if confirmed else "elempleo aceptó el envío, pero la oferta aún no sale como postulada: revísala tú"
    follow_up = ""
    if code == 2 and where:
        follow_up = f"La empresa pide completar la postulación en su sitio: {where}"
    elif video:
        follow_up = "La empresa pide un videocuestionario en elempleo (Vprez): hazlo tú desde la oferta."
    return ApplyResult("enviada", detail, follow_up=follow_up)
