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


def has_session(profile: Path = PROFILE_DIR) -> bool:
    """¿Hay sesión de LinkedIn guardada en el perfil? Solo se mira el NOMBRE de la cookie, nunca su valor."""
    cookies = profile / "Default" / "Cookies"
    if not cookies.exists():
        return False
    fd, tmp = tempfile.mkstemp()
    os.close(fd)
    try:
        shutil.copy(cookies, tmp)  # Chrome puede tener la base abierta: se lee una copia
        with sqlite3.connect(tmp) as db:
            return db.execute("select 1 from cookies where host_key like '%linkedin.com' and name = ?",
                              (SESSION_COOKIE,)).fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        os.remove(tmp)


def _prepare_profile() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)


def open_context(playwright, *, headless: bool = False):
    _prepare_profile()
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR), channel="chrome", headless=headless, chromium_sandbox=True,
        ignore_default_args=["--password-store=basic"], viewport={"width": 1280, "height": 860}, locale="es-CO",
    )


def login(*, timeout_minutes: int = 25) -> int:
    """Abre un Chrome normal con el perfil del bot, espera a que la persona inicie sesión y lo cierra solo."""
    _prepare_profile()
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome:
        print("No encuentro Google Chrome instalado.")
        return 1
    if has_session():
        print("Ya hay una sesión de LinkedIn guardada en el navegador del bot.")
        return 0
    process = subprocess.Popen([chrome, f"--user-data-dir={PROFILE_DIR}", "--no-first-run", "https://www.linkedin.com/login"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
