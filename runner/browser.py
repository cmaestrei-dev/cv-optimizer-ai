"""Navegador del bot: un perfil de Chrome propio y persistente (nunca el perfil personal de la persona).

- La persona inicia sesión UNA vez en un Chrome normal (sin automatización) con ese perfil: LinkedIn rechaza
  el inicio de sesión en una ventana controlada por Playwright. La sesión queda guardada en la carpeta del perfil.
- El bot abre después ese mismo perfil con Playwright, con el aislamiento normal de Chrome (sin --no-sandbox) y
  el llavero del sistema: Playwright usa por defecto otra llave (--password-store=basic) y no podría leer las
  cookies que guardó el Chrome normal.
- No se usan herramientas para ocultar la automatización ni el puerto de depuración (que expondría la sesión).
"""

import json
import os
import shutil
import signal
import socket
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
    "magneto": ("magneto365.com", None, "https://web.magneto365.com/sign-in"),
    "elempleo": ("elempleo.com", None, "https://www.elempleo.com/co/iniciar-sesion"),
    # SuccessFactors: «Iniciar sesión | Ir a mi perfil» arriba a la derecha (o «Únete a la comunidad de talentos»)
    "bancolombia": ("grupobancolombia.com", None, "https://empleo.grupobancolombia.com/bancolombia/"),
    # Gupy (Stefanini): su acceso tiene el captcha de Cloudflare, que rechaza la ventana que maneja el bot; en un Chrome
    # normal pasa. Una cuenta sirve para todas las empresas que usan Gupy.
    "gupy": ("gupy.io", None, "https://stefaninilatam.gupy.io/"),
    # Teamtailor de Periferia IT: entra con un enlace que llega al correo (ábrelo en esta misma ventana)
    "periferia": ("periferiaitgroup.com", None, "https://jobs.periferiaitgroup.com/connect/login"),
    # AIRA (Grupo Falabella): correo y contraseña de AIRA («Ya tengo cuenta»), sin captcha
    "aira": ("airavirtual.com", None, "https://falabella.airavirtual.com/"),
}
NAMES = {"linkedin": "LinkedIn", "computrabajo": "Computrabajo", "magneto": "Magneto", "elempleo": "elempleo",
         "bancolombia": "Bancolombia", "gupy": "Gupy (Stefanini)", "periferia": "Periferia IT", "aira": "AIRA (Falabella)"}


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


def _keep_sessions(profile: Path = PROFILE_DIR) -> None:
    """Que Chrome reabra la sesión anterior al arrancar: si no, al cerrarse borra las cookies «de sesión», y así
    guarda elempleo la suya (habría que entrar cada vez). Solo con Chrome cerrado: el archivo es suyo."""
    prefs = profile / "Default" / "Preferences"
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return  # perfil nuevo: Chrome crea el archivo al abrirse y se ajusta la vez siguiente
    if not isinstance(data, dict) or data.get("session", {}).get("restore_on_startup") == 1:
        return
    data.setdefault("session", {})["restore_on_startup"] = 1
    tmp = prefs.with_name("Preferences.cvo")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, prefs)


def _prepare_profile() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)
    if owner_pid(PROFILE_DIR) is None:
        _keep_sessions(PROFILE_DIR)


class BrowserUnavailableError(RuntimeError):
    """No se puede abrir el navegador del bot ahora: la próxima vuelta lo intenta."""


class NoDisplayError(BrowserUnavailableError):
    """No hay sesión gráfica donde abrir la ventana del bot."""


class ProfileBusyError(BrowserUnavailableError):
    """Otro Chrome (una vuelta anterior o una ventana abierta a mano) tiene el perfil del bot."""


def owner_pid(profile: Path = PROFILE_DIR) -> int | None:
    """El proceso de Chrome que tiene abierto el perfil según su candado, o None si está libre.

    Un candado de un proceso que ya no existe en este equipo no cuenta: Chrome lo reemplaza solo. El de otro equipo
    no se puede comprobar y cuenta como ocupado (Chrome tampoco abriría el perfil)."""
    try:
        target = os.readlink(profile / "SingletonLock")  # «<equipo>-<pid>»
    except OSError:
        return None
    host, _, pid = target.rpartition("-")
    if not pid.isdigit():
        return None
    if host != socket.gethostname():
        return int(pid)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass  # existe, pero es de otro usuario
    return int(pid)


def wait_free(wait_seconds: int = 1800, poll_seconds: int = 15) -> None:
    """Espera a que nadie más tenga abierto el perfil (p. ej. una vuelta que aún no termina). Si no, el Chrome nuevo
    se uniría al abierto («Se está abriendo en una sesión de navegador existente») y la vuelta fallaría."""
    deadline = time.monotonic() + wait_seconds
    told = False
    while owner_pid(PROFILE_DIR) is not None:
        if time.monotonic() >= deadline:
            raise ProfileBusyError("El navegador del bot sigue abierto por otro programa: la próxima vuelta lo intenta.")
        if not told:
            print("El navegador del bot está abierto (otra vuelta o una ventana): espero a que se cierre…")
            told = True
        time.sleep(poll_seconds)


def ensure_display(wait_seconds: int = 600) -> None:
    """Una vuelta programada puede arrancar al encender el computador, antes que la sesión gráfica: se espera a que
    systemd del usuario conozca la pantalla y se toman de ahí DISPLAY, WAYLAND_DISPLAY y XAUTHORITY."""
    deadline = time.monotonic() + wait_seconds
    while not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        try:
            env = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True,
                                 timeout=10, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            env = ""
        for line in env.splitlines():
            key, _, value = line.partition("=")
            if key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY") and value:
                os.environ[key] = value
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            return
        if time.monotonic() > deadline:
            raise NoDisplayError("No hay sesión gráfica para abrir el navegador del bot: la próxima vuelta lo intenta.")
        time.sleep(15)


def open_context(playwright, *, headless: bool = False, wait_seconds: int = 1800):
    if not headless:
        ensure_display()
    wait_free(wait_seconds)
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
    if owner_pid(PROFILE_DIR) is not None:  # otro Chrome tiene el perfil: el nuevo se cerraría al instante
        print("El navegador del bot ya está abierto (¿hay una vuelta corriendo?). Ciérralo o espera a que termine.")
        return 1
    if has_session(portal=portal):
        print(f"Ya hay una sesión de {NAMES[portal]} guardada en el navegador del bot.")
        return 0
    process = subprocess.Popen([chrome, f"--user-data-dir={PROFILE_DIR}", "--no-first-run", page],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if cookie is None:  # aún no se sabe qué cookie marca la sesión: la persona cierra la ventana al terminar
        before = _cookie_names(domain)
        print(f"1. En la ventana que se abrió, entra a {NAMES[portal]} con tu correo y tu contraseña.")
        if portal == "periferia":
            print("   Te llega un enlace al correo: cópialo y ábrelo en ESTA ventana (si lo abres en otro navegador,")
            print("   la sesión queda allá y no en el bot). Si no llega, revisa spam y la carpeta «Promociones».")
        print("   Si quieres, actualiza ahí mismo tu hoja de vida.")
        print("2. Cuando hayas entrado, cierra la ventana.\n")
        try:
            process.wait(timeout=timeout_minutes * 60)
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGTERM)
            print(f"Pasaron {timeout_minutes} minutos: cerré la ventana.")
        time.sleep(2)
        new = len(_cookie_names(domain) - before)
        print(f"Ventana cerrada. Quedaron {new} cookies nuevas de {NAMES[portal]} en el navegador del bot.")
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
