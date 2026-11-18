"""Navegador del bot: un perfil de Chrome propio y persistente (nunca el perfil personal de la persona).

- La persona inicia sesión UNA vez en un Chrome normal (sin automatización) con ese perfil: LinkedIn rechaza
  el inicio de sesión en una ventana controlada por Playwright. La sesión queda guardada en la carpeta del perfil.
- El bot abre después ese mismo perfil con Playwright, con el aislamiento normal de Chrome (sin --no-sandbox) y
  el llavero del sistema: Playwright usa por defecto otra llave (--password-store=basic) y no podría leer las
  cookies que guardó el Chrome normal.
- No se usan herramientas para ocultar la automatización ni el puerto de depuración (que expondría la sesión).
"""

import os
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from runner.config import DATA_DIR

PROFILE_DIR = DATA_DIR / "navegador"
CHALLENGE = ("/checkpoint", "/authwall", "captcha", "/uas/login", "/login")
SESSION_COOKIE = "li_at"
# Portal → (dominio de sus cookies, cookie de sesión o None si aún no se conoce, página de inicio de sesión)
LOGINS = {
    "linkedin": ("linkedin.com", SESSION_COOKIE, "https://www.linkedin.com/login"),
    "computrabajo": ("computrabajo.com", None, "https://candidato.co.computrabajo.com/acceso/"),
}


def _cookie_names(domain: str, profile: Path = PROFILE_DIR) -> set[str]:
    """Nombres (nunca valores) de las cookies de un dominio guardadas en el perfil."""
    cookies = profile / "Default" / "Cookies"
    if not cookies.exists():
        return set()
    fd, tmp = tempfile.mkstemp()
    os.close(fd)
    try:
        shutil.copy(cookies, tmp)  # Chrome puede tener la base abierta: se lee una copia
        with sqlite3.connect(tmp) as db:
            return {row[0] for row in db.execute("select name from cookies where host_key like ?", (f"%{domain}",))}
    except sqlite3.Error:
        return set()
    finally:
        os.remove(tmp)


def has_session(profile: Path = PROFILE_DIR, portal: str = "linkedin") -> bool:
    """¿Hay sesión guardada en el perfil? Solo se mira el NOMBRE de la cookie, nunca su valor."""
    domain, cookie, _ = LOGINS[portal]
    return cookie is not None and cookie in _cookie_names(domain, profile)


def _prepare_profile() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)


def open_context(playwright, *, headless: bool = False):
    _prepare_profile()
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR), channel="chrome", headless=headless, chromium_sandbox=True,
        ignore_default_args=["--password-store=basic"], viewport={"width": 1280, "height": 860}, locale="es-CO",
    )


def login(portal: str = "linkedin", *, timeout_minutes: int = 25) -> int:
    """Abre un Chrome normal con el perfil del bot y espera a que la persona inicie sesión."""
    _prepare_profile()
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome:
        print("No encuentro Google Chrome instalado.")
        return 1
    domain, cookie, page = LOGINS[portal]
    if os.path.lexists(PROFILE_DIR / "SingletonLock"):  # otro Chrome tiene el perfil: el nuevo se cerraría al instante
        print("El navegador del bot ya está abierto (¿hay una vuelta corriendo?). Ciérralo o espera a que termine.")
        return 1
    if has_session(portal=portal):
        print(f"Ya hay una sesión de {portal.capitalize()} guardada en el navegador del bot.")
        return 0
    process = subprocess.Popen([chrome, f"--user-data-dir={PROFILE_DIR}", "--no-first-run", page],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if cookie is None:  # aún no se sabe qué cookie marca la sesión: la persona cierra la ventana al terminar
        before = _cookie_names(domain)
        print("1. En la ventana que se abrió, entra a Computrabajo con tu correo y tu contraseña.")
        print("   Si quieres, actualiza ahí mismo tu hoja de vida.")
        print("2. Cuando hayas entrado, cierra la ventana.\n")
        try:
            process.wait(timeout=timeout_minutes * 60)
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGTERM)
            print(f"Pasaron {timeout_minutes} minutos: cerré la ventana.")
        time.sleep(2)
        new = len(_cookie_names(domain) - before)
        print(f"Ventana cerrada. Quedaron {new} cookies nuevas de Computrabajo en el navegador del bot.")
        return 0
    print("1. En la ventana que se abrió, entra con tu correo y tu contraseña de LinkedIn («Email or phone»).")
    print("   Si tu LinkedIn no está ligado a esa cuenta de Google, el botón «Continuar con Google» crea una cuenta nueva.")
    print("2. Si LinkedIn te pide un código, escríbelo.")
    print("3. No cierres la ventana: te aviso aquí cuando la sesión quede guardada y la cierro sola.\n")
    deadline = time.monotonic() + timeout_minutes * 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            time.sleep(2)
            saved = has_session()
            print("La ventana se cerró. " + ("La sesión quedó guardada." if saved else "La sesión NO quedó guardada: vuelve a intentarlo."))
            return 0 if saved else 1
        if has_session():
            print("¡Listo! Sesión guardada. Cierro la ventana en 5 segundos…")
            time.sleep(5)
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=30)
            return 0
        time.sleep(3)
    process.send_signal(signal.SIGTERM)
    print(f"Pasaron {timeout_minutes} minutos sin iniciar sesión.")
    return 1
