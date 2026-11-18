"""Bot de postulación de CV Optimizer.

    python -m runner configurar      crea la configuración para editar
    python -m runner token           guarda el token del bot (se crea en la app: Perfil → Bot de LinkedIn)
    python -m runner entrar          abre el navegador del bot para que inicies sesión en LinkedIn (una vez)
    python -m runner importar CV.pdf carga tu CV o el PDF de tu LinkedIn en tu perfil de la app (solo lo nuevo)
    python -m runner buscar          busca vacantes, las analiza con tu perfil y prepara el CV de cada una
    python -m runner postular        postula a las preparadas con «Solicitud sencilla» (--prueba: sin enviar)
    python -m runner diario          una vuelta completa: buscar y luego postular (la que corre la programación)
    python -m runner programar       lo programa cada día (temporizador de systemd del usuario; --quitar lo quita)
"""

import argparse
import getpass
import re
import sys
from datetime import UTC, date, datetime

from runner import config as cfg
from runner import discover
from runner.api import Api, ApiError
from runner.state import State


def _excluded(card, conf: cfg.Config) -> str:  # tarjeta de cualquier portal
    title, company = card.title.lower(), card.company.lower()
    words = set(re.findall(r"\w+", title))  # palabras completas: «sr» no descarta «SRE»
    if word := next((w for w in conf.exclude_words if w and (w in words if " " not in w else w in title)), ""):
        return f"el cargo contiene «{word}»"
    if company and any(c and c in company for c in conf.exclude_companies):
        return "empresa excluida"
    return ""


def cmd_configurar(_args) -> int:
    path = cfg.write_template()
    print(f"Configuración en {path}. Edítala (dirección de la app, búsquedas) y luego: python -m runner token")
    return 0


def cmd_token(_args) -> int:
    path = cfg.save_token(getpass.getpass("Pega el token del bot (no se muestra): "))
    print(f"Token guardado en {path} (solo tú puedes leerlo).")
    return 0


def cmd_importar(args) -> int:
    from pathlib import Path

    pdf = Path(args.pdf).expanduser()
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        print(f"No encuentro el PDF «{pdf}».", file=sys.stderr)
        return 2
    conf = cfg.load()
    print("Leyendo tu PDF con la app (puede tardar un minuto)…")
    result, applied = Api(conf.api, conf.token).import_profile(pdf)
    c = applied["counts"]
    print(f"Guardado: {c.get('experiencias', 0)} experiencias, {c.get('logros', 0)} logros, "
          f"{c.get('habilidades', 0)} habilidades y {c.get('estudios', 0)} estudios.")
    if result.get("duplicate_experiences"):
        print(f"Ya estaban en tu perfil: {len(result['duplicate_experiences'])} experiencias (no se repitieron).")
    if result.get("discarded"):
        print(f"No se importó (no aparece tal cual en el PDF): {len(result['discarded'])} elementos.")
    print("Revísalo en la app: Perfil.")
    return 0


def cmd_entrar(_args) -> int:
    from runner.browser import login  # Playwright solo hace falta para el navegador

    return login()


def _key(kind: str, portal: str) -> str:
    """Claves del estado por portal; las de LinkedIn conservan su nombre de antes."""
    return kind if portal == "linkedin" else f"{kind}_{portal}"


def _portal(name: str):
    from runner import computrabajo

    return {"linkedin": discover, "computrabajo": computrabajo}[name]


def cmd_buscar(args) -> int:
    conf = cfg.load()
    api = Api(conf.api, conf.token)
    state = State(cfg.DATA_DIR / "estado.json")
    me = api.me()
    if not me.get("has_experience"):
        print("Tu perfil no tiene experiencia todavía: cárgalo en la app (Perfil → Importar CV) antes de usar el bot.")
        return 1
    print(f"Modo {conf.mode}.")
    prepared_now = 0

    def full(portal: str) -> bool:
        return state.today(_key("preparadas", portal)) >= conf.cap(portal) or bool(args.max and prepared_now >= args.max)

    try:
        for search in conf.searches:
            portal, name = search.portal, cfg.PORTALS[search.portal]
            paused = _key("busqueda", portal)
            if (until := state.pause_until(paused)) and until > datetime.now(UTC):
                print(f"\n{name}: búsqueda en pausa hasta {until:%Y-%m-%d %H:%M} UTC ({state.pause_reason(paused)}).")
                continue
            if full(portal):
                continue
            source = _portal(portal)
            try:
                cards = source.discover(search)
                print(f"\n{name} · «{search.keywords}» en {search.place}: {len(cards)} vacantes")
                for card in cards:
                    if full(portal):
                        print("Tope alcanzado.")
                        break
                    if state.seen(card.job_id):
                        continue
                    if reason := _excluded(card, conf):
                        state.mark(card.job_id, "excluida", portal=portal, motivo=reason)
                        print(f"  · {card.title} — {card.company}: omitida ({reason})")
                        continue
                    discover.pause()
                    text = source.posting_text(card)
                    if not text:
                        state.mark(card.job_id, "sin_texto", portal=portal)
                        continue
                    header = f"{card.title}\n{card.company}\n{card.place}\n\n"
                    try:
                        vacancy = api.add_vacancy(text=header + text, url=card.url, posted=card.posted)
                    except ApiError as e:
                        if e.status == 429:  # cupo diario de IA de la cuenta
                            print(f"Cupo de IA agotado por hoy: {e.detail}")
                            return 0
                        if e.status >= 500:  # corte o servidor ocupado: se reintenta en la próxima vuelta
                            print(f"  ✗ {card.title}: {e.detail} (se reintenta en la próxima vuelta)")
                            continue
                        state.mark(card.job_id, "error", portal=portal, detalle=e.detail[:200])
                        print(f"  ✗ {card.title}: {e.detail}")
                        continue
                    if not vacancy.created and not vacancy.unfinished:
                        state.mark(card.job_id, "repetida", portal=portal, app=vacancy.id)
                        continue
                    line = f"  ✓ {vacancy.score if vacancy.score is not None else '—':>3}  {vacancy.role} — {vacancy.company}"
                    if vacancy.missing:
                        line += f"  (falta: {'; '.join(vacancy.missing[:2])})"
                    print(line)
                    minimum = conf.min_score(portal)
                    if minimum and (vacancy.score is None or vacancy.score < minimum):
                        note = f"El bot la descartó: compatibilidad {vacancy.score if vacancy.score is not None else '—'} (mínimo {minimum})."
                        try:
                            api.post(f"/applications/{vacancy.id}/status", {"status": "descartada", "note": note})
                        except ApiError as e:
                            print(f"        No se pudo descartar en la app: {e.detail}")
                        state.mark(card.job_id, "baja_compatibilidad", portal=portal, app=vacancy.id, puntaje=vacancy.score)
                        print(f"        Menos de {minimum}: descartada, sin CV.")
                        state.save()
                        continue
                    cv_path, cv_id = "", None
                    if conf.make_cv and not args.sin_cv:
                        try:
                            cv = api.make_cv(vacancy.id)
                            # con su nombre real: es el que ve el reclutador en el portal
                            cv_path = str(api.download_cv(cv["id"], cfg.DATA_DIR / "cvs" / str(vacancy.id) / cv["filename"]))
                            cv_id = cv["id"]
                            print(f"        CV: {cv['filename']}")
                        except ApiError as e:
                            print(f"        CV no generado: {e.detail}")
                    state.mark(card.job_id, "preparada", portal=portal, app=vacancy.id, puntaje=vacancy.score, cv=cv_path,
                               cv_id=cv_id, url=card.url)
                    state.count(_key("preparadas", portal))
                    prepared_now += 1
                    state.save()
            except discover.BlockedError as e:
                state.pause(6, str(e), kind=paused)
                print(f"\nParo la búsqueda en {name}: {e} Pausa de 6 horas (tu cuenta no se toca).")
    finally:
        state.save()
    today = ", ".join(f"{name} {state.today(_key('preparadas', p))} de {conf.cap(p)}" for p, name in cfg.PORTALS.items()
                      if any(s.portal == p for s in conf.searches))
    print(f"\nListo ({date.today()}): preparadas hoy — {today}. Revísalas en la app: Postulaciones.")
    return 0


def _answerer(api: Api, conf: cfg.Config, application_id: int):
    """Respuestas: primero el banco de la persona; lo demás, el motor de la app con su perfil (verificado)."""
    from runner import answers

    def answer(questions) -> dict[str, str]:
        out, ask = {}, []
        for q in questions:
            value = answers.bank_answer(q.label, conf.answers)
            if value is not None:
                out[q.label] = value
            else:
                ask.append(q)
        if ask:
            try:
                replies = api.post(f"/applications/{application_id}/screening", {"questions": [q.label for q in ask]})
            except ApiError as e:
                print(f"        No se pudieron preparar respuestas: {e.detail}")
                replies = []
            by_question = {r["question"]: r for r in replies} if isinstance(replies, list) else {}
            for q in ask:
                reply = by_question.get(q.label, {})
                text = "" if reply.get("needs_you") else (reply.get("answer") or "")
                if q.numeric or answers.is_years(q.label):
                    text = answers.to_integer(text) or ("0" if answers.is_years(q.label) and conf.no_evidence == "cero" else "")
                if text:
                    out[q.label] = text
        return out

    return answer


def cmd_postular(args) -> int:
    import random
    import time as _time
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from runner import browser, linkedin

    conf = cfg.load()
    submit = conf.mode == "auto" and not args.prueba
    api = Api(conf.api, conf.token)
    state = State(cfg.DATA_DIR / "estado.json")
    if (until := state.pause_until("cuenta")) and until > datetime.now(UTC):
        print(f"Postulación en pausa hasta {until:%Y-%m-%d %H:%M} UTC: {state.pause_reason('cuenta')}")
        return 0
    if not browser.has_session():
        print("El navegador del bot no tiene sesión de LinkedIn: python -m runner entrar")
        return 1
    pending = [(job_id, v) for job_id, v in state.data["vistas"].items()
               if v.get("estado") == "preparada" and v.get("portal", "linkedin") == "linkedin"
               and v.get("cv") and Path(v["cv"]).is_file() and v.get("cv_id")]
    sent_today = state.today("enviadas")
    print(f"{'Modo AUTOMÁTICO: se envían' if submit else 'Modo PRUEBA: se llega a la revisión y se descarta'}. "
          f"{len(pending)} preparadas; hoy van {sent_today} de {conf.daily_cap} enviadas.")
    if not pending:
        return 0
    with sync_playwright() as p:
        context = browser.open_context(p)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(90_000)
        page.set_default_navigation_timeout(120_000)
        try:
            for n, (job_id, v) in enumerate(pending[: args.max or len(pending)]):
                if submit and sent_today >= conf.daily_cap:
                    print("Tope diario de envíos alcanzado.")
                    break
                print(f"\n· {v.get('url')}  (compatibilidad {v.get('puntaje')})")
                result = linkedin.apply(page, v["url"], Path(v["cv"]), _answerer(api, conf, v["app"]), submit=submit,
                                        shots=cfg.DATA_DIR / "capturas")
                print(f"  → {result.status}{': ' + result.detail if result.detail else ''}")
                if result.unanswered:
                    print("    Sin respuesta (agrégalas a [respuestas] o a tu perfil):", "; ".join(result.unanswered[:4]))
                if result.status in ("verificacion", "tope"):
                    state.pause(24, f"LinkedIn: {result.status} ({result.detail[:80]})", kind="cuenta")
                    print("Paro todo 24 horas. Si fue una verificación, entra tú a LinkedIn y complétala.")
                    break
                if result.status == "enviada":
                    try:
                        api.post(f"/applications/{v['app']}/sent", {"cv_id": v["cv_id"], "platform": "LinkedIn"})
                    except ApiError as e:
                        print(f"    Enviada en LinkedIn, pero la app no la registró: {e.detail}")
                    state.mark(job_id, "enviada", **{k: v[k] for k in ("app", "cv", "cv_id", "url", "puntaje")})
                    state.count("enviadas")
                    sent_today += 1
                elif result.status in ("saltada", "externa", "ya_postulada"):
                    state.mark(job_id, result.status, app=v["app"], url=v["url"], preguntas=result.unanswered[:6],
                               detalle=result.detail[:200])
                state.save()
                if n < len(pending) - 1:
                    wait = random.uniform(*conf.pause_seconds) if result.status == "enviada" else random.uniform(8, 20)
                    _time.sleep(wait)
        finally:
            state.save()
            context.close()
    return 0


def _notify(text: str) -> None:
    """Aviso de escritorio al terminar una vuelta programada (si el sistema lo permite; nunca falla la vuelta)."""
    import contextlib
    import shutil
    import subprocess

    if shutil.which("notify-send"):
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(["notify-send", "--app-name=CV Optimizer", "Bot de LinkedIn", text], timeout=10, check=False)


def cmd_diario(_args) -> int:
    """Una vuelta completa: buscar y luego postular. Nunca corren dos vueltas a la vez."""
    import fcntl
    import traceback

    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(cfg.DATA_DIR / "vuelta.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Ya hay una vuelta del bot corriendo: esta se omite.")
            return 0
        print(f"\n===== Vuelta del {datetime.now():%Y-%m-%d %H:%M} =====")
        try:
            cmd_buscar(argparse.Namespace(sin_cv=False, max=0))
        except (cfg.ConfigError, ApiError):
            raise
        except Exception:  # noqa: BLE001 — si la búsqueda falla, igual se postula a lo ya preparado
            traceback.print_exc()
        code = cmd_postular(argparse.Namespace(prueba=False, max=0))
        state = State(cfg.DATA_DIR / "estado.json")
        notice = f"Hoy: {state.today('enviadas')} enviadas y {state.today('preparadas')} preparadas."
        if ct := state.today(_key("preparadas", "computrabajo")):
            notice += f" Computrabajo: {ct} preparadas."
        if (until := state.pause_until("cuenta")) and until > datetime.now(UTC):
            notice += f" Postulación en pausa: {state.pause_reason('cuenta')}. Entra tú a LinkedIn y revisa."
        elif code == 1:
            notice += " El navegador del bot perdió la sesión de LinkedIn: python -m runner entrar."
        print(notice)
        _notify(notice)
        return code


def cmd_programar(args) -> int:
    from pathlib import Path

    from runner import schedule

    if args.quitar:
        schedule.remove()
        print("Listo: el bot ya no corre solo.")
        return 0
    cfg.load()  # la configuración y el token deben estar bien antes de programar
    workdir = Path(__file__).resolve().parent.parent
    log = cfg.DATA_DIR / "registro.log"
    try:
        nxt = schedule.install(sys.executable, workdir, args.horas, log)
    except schedule.ScheduleError as e:
        print(e, file=sys.stderr)
        return 2
    print(f"Programado a las {', '.join(schedule.normalize_times(args.horas))} cada día, con el código de {workdir}.")
    print(f"Próxima vuelta: {nxt or '(systemd no la informó)'}")
    print(f"Lo que hace cada vuelta queda en {log}. Quitarlo: python -m runner programar --quitar")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runner", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("configurar").set_defaults(fn=cmd_configurar)
    sub.add_parser("token").set_defaults(fn=cmd_token)
    sub.add_parser("entrar").set_defaults(fn=cmd_entrar)
    importar = sub.add_parser("importar")
    importar.add_argument("pdf", help="ruta del PDF (tu CV o «Guardar en PDF» de tu perfil de LinkedIn)")
    importar.set_defaults(fn=cmd_importar)
    buscar = sub.add_parser("buscar")
    buscar.add_argument("--sin-cv", action="store_true", help="solo analizar, sin generar el CV")
    buscar.add_argument("--max", type=int, default=0, help="preparar como mucho N vacantes en esta vuelta")
    buscar.set_defaults(fn=cmd_buscar)
    postular = sub.add_parser("postular")
    postular.add_argument("--prueba", action="store_true", help="llegar a la revisión y descartar, aunque el modo sea auto")
    postular.add_argument("--max", type=int, default=0, help="como mucho N vacantes en esta vuelta")
    postular.set_defaults(fn=cmd_postular)
    sub.add_parser("diario").set_defaults(fn=cmd_diario)
    programar = sub.add_parser("programar")
    programar.add_argument("--horas", nargs="+", default=["09:17", "15:47"], help="horas del día (HH:MM)")
    programar.add_argument("--quitar", action="store_true", help="dejar de correrlo solo")
    programar.set_defaults(fn=cmd_programar)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except cfg.ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    except ApiError as e:
        if e.status == 401:
            print("La app rechazó el token del bot (¿revocado?). Crea otro: Perfil → Bot de LinkedIn.", file=sys.stderr)
        else:
            print(f"La app respondió con un error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
