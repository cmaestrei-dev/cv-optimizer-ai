"""Navegador del bot: un perfil de Chrome propio y persistente (nunca el perfil personal de la persona).

La persona inicia sesión en LinkedIn una vez; la sesión queda en ese perfil (carpeta solo para el usuario).
No se usan herramientas para ocultar la automatización ni el puerto de depuración (que expondría la sesión).
"""

import os

from runner.config import DATA_DIR

PROFILE_DIR = DATA_DIR / "navegador"
LOGGED_IN = ("/feed", "/jobs", "/mynetwork", "/in/")
CHALLENGE = ("/checkpoint", "/authwall", "captcha")


def open_context(playwright):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR), channel="chrome", headless=False, viewport={"width": 1280, "height": 860}, locale="es-CO",
    )


def login() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = open_context(p)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        print("Inicia sesión en la ventana que se abrió (con tu correo y contraseña, o como siempre lo haces).")
        print("Si LinkedIn pide verificación, complétala tú. Esta ventana se cierra sola al entrar.")
        try:
            page.wait_for_url(lambda url: any(part in url for part in LOGGED_IN), timeout=10 * 60 * 1000)
        except Exception:  # noqa: BLE001  (tiempo agotado o ventana cerrada)
            print("No se detectó el inicio de sesión. Vuelve a intentarlo: python -m runner entrar")
            context.close()
            return 1
        print("Sesión guardada en el navegador del bot.")
        context.close()
    return 0
