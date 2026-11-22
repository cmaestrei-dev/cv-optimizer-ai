"""Bot de postulación de CV Optimizer.

    python -m runner configurar      crea la configuración para editar
    python -m runner token           guarda el token del bot (se crea en la app: Perfil → Bot de LinkedIn)
    python -m runner entrar [portal] abre el navegador del bot para que inicies sesión (linkedin, computrabajo, magneto, elempleo, bancolombia)
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
from pathlib import Path
from types import SimpleNamespace

from runner import computrabajo, discover, elempleo, magneto
from runner import config as cfg
from runner.api import Api, ApiError
from runner.browser import LOGINS  # sin Playwright: solo direcciones y nombres de cookies
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


def cmd_entrar(args) -> int:
    from runner.browser import login  # Playwright solo hace falta para el navegador

    return login(args.portal)


def _not_included(title: str, conf: cfg.Config) -> str:
    """Motivo para no analizar una vacante cuyo cargo no tiene ninguna palabra de `[incluir]` (vacío si pasa)."""
    from runner import watch

    if not conf.include_words:
        return ""
    text = watch._norm(title)
    return "" if any(watch._has(w, text) for w in conf.include_words) else "el cargo no tiene ninguna palabra de [incluir]"


def _key(kind: str, portal: str) -> str:
    """Claves del estado por portal; las de LinkedIn conservan su nombre de antes."""
    return kind if portal == "linkedin" else f"{kind}_{portal}"


def _portal(name: str):
    return {"linkedin": discover, "computrabajo": computrabajo, "magneto": magneto, "elempleo": elempleo}[name]


PLATFORM_PORTAL = {"LinkedIn": "linkedin", "Computrabajo": "computrabajo", "Magneto": "magneto", "elempleo": "elempleo"}


def _job_id(portal: str, url: str) -> str:
    """El identificador de la vacante en el estado del bot, a partir de su enlace canónico."""
    if portal == "linkedin":
        match = re.search(r"/jobs/view/(\d+)", url)
        return match.group(1) if match else ""
    if portal in ("magneto", "elempleo"):  # el número final del enlace
        match = re.search(r"-(\d+)/?$", url.split("#")[0].split("?")[0])
        return (magneto.PREFIX if portal == "magneto" else elempleo.PREFIX) + match.group(1) if match else ""
    match = re.search(r"-([0-9A-Fa-f]{16,})/?$", url.split("#")[0].split("?")[0])
    return computrabajo.PREFIX + match.group(1).upper() if match else ""


def _discard(api: Api, app_id: int, note: str) -> None:
    try:
        api.post(f"/applications/{app_id}/status", {"status": "descartada", "note": note})
    except ApiError as e:
        print(f"        No se pudo descartar en la app: {e.detail}")


def _refresh_alerts(api: Api, *, wait_seconds: int = 300, poll_seconds: int = 15) -> None:
    """Pide a la app revisar el buzón de alertas por correo y espera a que analice lo nuevo (hasta `wait_seconds`).

    La app solo lo revisa sola una vez al día (temprano): sin esto, una alerta de la tarde esperaría al otro día.
    Lo que siga en análisis al terminar la espera se toma en la vuelta siguiente.
    """
    import time as _time

    try:
        status = api.post("/alerts/check", {})
        if not status.get("enabled") or not status.get("address"):
            return
        if problem := status.get("mailbox_problem"):
            from runner import telegram

            print(f"Alertas por correo: {problem}")
            telegram.notify(f"⚠ Alertas de LinkedIn: {problem} Renueva la contraseña de aplicación (deploy/README.md).")
            return
        deadline = _time.monotonic() + wait_seconds
        if status.get("analyzing"):
            print(f"Alertas por correo: {status['analyzing']} en análisis; espero a que terminen…")
        while status.get("analyzing") and _time.monotonic() < deadline:
            _time.sleep(poll_seconds)
            status = api.get("/alerts")
    except ApiError as e:
        print(f"No se pudo revisar el buzón de alertas: {e.detail}")


def _prepare(api: Api, conf: cfg.Config, state: State, args, *, portal: str, job_id: str, app_id: int,
             score: int | None, url: str) -> bool:
    """Descarta por compatibilidad o hace el CV y deja la vacante lista para postular. True si quedó preparada."""
    minimum = conf.min_score(portal)
    if minimum and (score is None or score < minimum):
        _discard(api, app_id, f"El bot la descartó: compatibilidad {score if score is not None else '—'} (mínimo {minimum}).")
        state.mark(job_id, "baja_compatibilidad", portal=portal, app=app_id, puntaje=score)
        print(f"        Menos de {minimum}: descartada, sin CV.")
        state.save()
        return False
    cv_path, cv_id = "", None
    if conf.make_cv and not args.sin_cv:
        try:
            cv = api.make_cv(app_id)
            # con su nombre real: es el que ve el reclutador en el portal
            cv_path = str(api.download_cv(cv["id"], cfg.DATA_DIR / "cvs" / str(app_id) / cv["filename"]))
            cv_id = cv["id"]
            print(f"        CV: {cv['filename']}")
        except ApiError as e:
            print(f"        CV no generado: {e.detail}")
    state.mark(job_id, "preparada", portal=portal, app=app_id, puntaje=score, cv=cv_path, cv_id=cv_id, url=url)
    state.count(_key("preparadas", portal))
    state.save()
    return True


def cmd_buscar(args) -> int:
    conf = cfg.load()
    api = Api(conf.api, conf.token)
    state = State(cfg.DATA_DIR / "estado.json")
    me = api.me()
    if not me.get("has_experience"):
        print("Tu perfil no tiene experiencia todavía: cárgalo en la app (Perfil → Importar CV) antes de usar el bot.")
        return 1
    print(f"Modo {conf.mode}.")
    prepared_now, told = 0, set()

    def full(portal: str) -> bool:
        return state.today(_key("preparadas", portal)) >= conf.cap(portal) or bool(args.max and prepared_now >= args.max)

    try:
        # Primero la bandeja de la app (p. ej. las alertas de LinkedIn por correo): ya vienen analizadas.
        _refresh_alerts(api)
        inbox = [x for x in api.get("/applications?view=bandeja") if x.get("platform") in PLATFORM_PORTAL]
        if inbox:
            print(f"\nBandeja de la app: {len(inbox)} vacantes de portales por revisar")
        for item in inbox:
            portal = PLATFORM_PORTAL[item["platform"]]
            job_id = _job_id(portal, item.get("url") or "")
            if (args.portal and portal != args.portal) or not job_id or state.seen(job_id) or full(portal):
                continue
            if item.get("closes_on") and date.fromisoformat(item["closes_on"]) < date.today():
                state.mark(job_id, "cerrada", portal=portal, app=item["id"])
                continue
            role, company = item.get("role") or "", item.get("company") or ""
            if reason := _excluded(SimpleNamespace(title=role, company=company), conf):
                _discard(api, item["id"], f"El bot la omitió: {reason}.")
                state.mark(job_id, "excluida", portal=portal, app=item["id"], motivo=reason)
                print(f"  · {role} — {company}: omitida ({reason})")
                continue
            score = item.get("match_score")
            print(f"  ✓ {score if score is not None else '—':>3}  {role}" + (f" — {company}" if company else "") + "  (bandeja)")
            if _prepare(api, conf, state, args, portal=portal, job_id=job_id, app_id=item["id"], score=score,
                        url=item["url"]):
                prepared_now += 1
        state.save()
        for search in conf.searches:
            if args.portal and search.portal != args.portal:
                continue
            portal, name = search.portal, cfg.PORTALS[search.portal]
            paused = _key("busqueda", portal)
            if (until := state.pause_until(paused)) and until > datetime.now(UTC):
                if portal not in told:  # una vez por portal, no por cada búsqueda
                    told.add(portal)
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
                    if reason := _excluded(card, conf) or _not_included(card.title, conf):
                        state.mark(card.job_id, "excluida", portal=portal, motivo=reason, cargo=card.title[:120])
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
                    line = f"  ✓ {vacancy.score if vacancy.score is not None else '—':>3}  {vacancy.role}"
                    line += f" — {vacancy.company}" if vacancy.company else ""
                    if vacancy.missing:
                        line += f"  (falta: {'; '.join(vacancy.missing[:2])})"
                    print(line)
                    if _prepare(api, conf, state, args, portal=portal, job_id=card.job_id, app_id=vacancy.id,
                                score=vacancy.score, url=card.url):
                        prepared_now += 1
            except discover.BlockedError as e:
                state.pause(6, str(e), kind=paused)
                print(f"\nParo la búsqueda en {name}: {e} Pausa de 6 horas (tu cuenta no se toca).")
    finally:
        state.save()
    today = ", ".join(f"{name} {state.today(_key('preparadas', p))} de {conf.cap(p)}" for p, name in cfg.PORTALS.items()
                      if any(s.portal == p for s in conf.searches))
    print(f"\nListo ({date.today()}): preparadas hoy — {today}. Revísalas en la app: Postulaciones.")
    return 0


def _answerer(api: Api, conf: cfg.Config, application_id: int, *, units: bool = False, quota: dict | None = None):
    """Respuestas: primero el banco de la persona; lo demás, el motor de la app con su perfil (verificado).

    - Si la verificación marca una respuesta (p. ej. una sigla que el perfil no usa), se pide una vez más.
    - `units`: en las preguntas abiertas de años se escribe «2 años» (Computrabajo); si no, solo el número, que es
      lo que validan los campos de LinkedIn.
    - Preguntas de experiencia que el perfil no respalda, según `sin_evidencia`: "saltar" la vacante; "cero"
      («No», «0», «Aún no tengo experiencia con eso»); o "si" (decisión del dueño: «Sí» y, en años, lo que muestre
      el perfil o al menos `experiencia_por_defecto`). Solo las de experiencia: el resto sigue igual.
    - `quota`: compartido entre vacantes. Si la app dice que se acabó el cupo diario de IA, queda `quota["agotado"]`
      y no se le vuelve a preguntar en esta vuelta (las vacantes con preguntas esperan a la siguiente).
    """
    from runner import answers

    quota = quota if quota is not None else {}

    def screening(questions: list) -> dict[str, dict]:
        if quota.get("agotado"):
            return {}
        try:
            replies = api.post(f"/applications/{application_id}/screening", {"questions": [q.label for q in questions]})
        except ApiError as e:
            if e.status == 429:
                quota["agotado"] = True
            print(f"        No se pudieron preparar respuestas: {e.detail}")
            return {}
        return {r["question"]: r for r in replies} if isinstance(replies, list) else {}

    def flagged(reply: dict) -> bool:  # la IA respondió, pero la verificación no lo respaldó
        return bool(reply.get("needs_you") and (reply.get("answer") or "").strip())

    def answer(questions) -> dict[str, str]:
        out, ask = {}, []
        for q in questions:
            value = answers.bank_answer(q.label, conf.answers)
            if value is not None:
                out[q.label] = value
            else:
                ask.append(q)
        if not ask:
            return out
        by_question = screening(ask)
        if retry := [q for q in ask if flagged(by_question.get(q.label, {}))]:
            again = screening(retry)
            by_question.update({k: v for k, v in again.items() if not v.get("needs_you")})
        for q in ask:
            reply = by_question.get(q.label, {})
            text = "" if reply.get("needs_you") else (reply.get("answer") or "")
            choice = q.kind in ("radio", "select")
            if answers.is_years(q.label) and not choice and not q.numeric and len(re.findall(r"[^\W\d_]{3,}", text)) >= 4:
                pass  # pregunta abierta («¿cuánto tiempo y en qué empresas?»): la respuesta del perfil dice más que un número
            elif answers.is_years(q.label):
                text = answers.to_integer(text) or ""
                if conf.no_evidence == "si":
                    least = conf.default_years * (12 if answers.asks_months(q.label) else 1)
                    text = str(max(int(text or 0), least))
                elif not text and conf.no_evidence == "cero":
                    text = "0"
                if text and choice and answers.asks_months(q.label):
                    text = str(int(text) // 12)  # las opciones («12 a 24 meses») se comparan en años
                elif text and units and not q.numeric:
                    text += " meses" if answers.asks_months(q.label) else (" año" if text == "1" else " años")
            elif q.numeric:
                text = answers.to_integer(text) or ""
            elif conf.no_evidence == "si" and answers.asks_experience(q.label):
                if choice:  # la opción del perfil si es afirmativa; si no, la favorable («Sí», «Intermedio»…)
                    picked = answers.pick_option(text, q.options) if text else None
                    text = picked if picked and not answers.negative(picked) else (answers.favorable_option(q.options) or "Sí")
                elif not text or answers.normalize(text).startswith(("no ", "aun no", "todavia no")):
                    text = "Sí, tengo experiencia con eso. Con gusto amplío los detalles en una entrevista."
            elif not text and not flagged(reply) and conf.no_evidence == "cero" and answers.asks_experience(q.label):
                text = "No" if choice else "Aún no tengo experiencia con eso."
            if text:
                out[q.label] = text
        return out

    return answer


def _retry_answered(state: State, conf: cfg.Config) -> int:
    """Las vacantes saltadas por preguntas que ahora sí tienen respuesta en el banco vuelven a «preparada»."""
    from runner import answers

    def answerable(q: str) -> bool:
        if answers.bank_answer(q, conf.answers) is not None:
            return True
        return conf.no_evidence == "si" and (answers.asks_experience(q) or answers.is_years(q))

    retried = 0
    for job_id, v in list(state.data["vistas"].items()):
        questions = v.get("preguntas") or []
        if v.get("estado") == "saltada" and questions and v.get("cv") and v.get("cv_id") \
                and all(answerable(q) for q in questions):
            state.mark(job_id, "preparada", **{k: v[k] for k in ("portal", "app", "cv", "cv_id", "url", "puntaje") if k in v})
            retried += 1
    return retried


def _pending(state: State, portal: str) -> list[tuple[str, dict]]:
    from pathlib import Path

    return [(job_id, v) for job_id, v in state.data["vistas"].items()
            if v.get("estado") == "preparada" and v.get("portal", "linkedin") == portal
            and v.get("cv") and Path(v["cv"]).is_file() and v.get("cv_id")]


EXTERNAL_MIN_SCORE = 60  # vacantes de LinkedIn sin «Solicitud sencilla» que se le pasan a la persona por Telegram


def _hand_over(api: Api, v: dict, name: str, note: str) -> None:
    """Lo que solo la persona puede hacer tras una postulación (p. ej. seguir en el sitio de la empresa): a Telegram."""
    from hashlib import sha256

    from runner import telegram

    try:
        app = api.get(f"/applications/{v['app']}")
    except ApiError:
        app = {}
    item = {"id": sha256(v["url"].encode()).hexdigest()[:12], "url": v["url"], "titulo": app.get("role") or f"Vacante de {name}",
            "empresa": app.get("company") or name, "cv": v.get("cv") or "", "nota": note, "motivo": "", "respuestas": "",
            "puntaje": v.get("puntaje")}
    sent = telegram.add_manual(item)
    print(f"    Para ti: {note}" + (" (te lo mandé por Telegram)" if sent else ""))


def _apply_portal(page, portal: str, pending, *, conf: cfg.Config, api: Api, state: State, submit: bool, limit: int) -> None:
    """Postula a las preparadas de un portal. Se detiene ante una verificación, el tope o una sesión perdida."""
    import importlib
    import random
    import time as _time
    from pathlib import Path

    name, sent_key = cfg.PORTALS[portal], _key("enviadas", portal)
    quota: dict = {}  # cupo diario de IA de la cuenta (para las preguntas de filtro)
    for n, (job_id, v) in enumerate(pending[: limit or len(pending)]):
        if submit and state.today(sent_key) >= conf.cap(portal):
            print("Tope diario de envíos alcanzado.")
            break
        print(f"\n· {v.get('url')}  (compatibilidad {v.get('puntaje')})")
        answerer = _answerer(api, conf, v["app"], units=portal != "linkedin", quota=quota)
        module = importlib.import_module("runner.linkedin" if portal == "linkedin" else f"runner.{portal}_apply")
        if portal == "linkedin":
            result = module.apply(page, v["url"], Path(v["cv"]), answerer, submit=submit, shots=cfg.DATA_DIR / "capturas")
        elif portal == "computrabajo":
            result = module.apply(page, v["url"], Path(v["cv"]), answerer, submit=submit,
                                  general=Path(conf.general_cvs[portal]), uploaded=state.data.setdefault(f"pdfs_{portal}", []))
        else:  # magneto, elempleo
            result = module.apply(page, v["url"], Path(v["cv"]), answerer, submit=submit)
        print(f"  → {result.status}{': ' + result.detail if result.detail else ''}")
        if result.unanswered:
            print("    Sin respuesta (agrégalas a [respuestas] o a tu perfil):", "; ".join(result.unanswered[:4]))
        if result.status in ("verificacion", "tope"):
            state.pause(24, f"{name}: {result.status} ({result.detail[:80]})", kind=_key("cuenta", portal))
            print(f"Paro {name} 24 horas. Si fue una verificación, entra tú a {name} y complétala.")
            break
        if (result.status == "externa" and portal == "linkedin" and not result.follow_up
                and (v.get("puntaje") or 0) >= EXTERNAL_MIN_SCORE):  # ya tiene su CV: que la persona la envíe
            result.follow_up = ("En LinkedIn esta vacante se postula en el sitio de la empresa: abre el enlace, pulsa "
                                "«Solicitar» y usa el CV adjunto.")
        if result.follow_up:
            _hand_over(api, v, name, result.follow_up)
        if result.status in ("sin_espacio", "perfil"):
            print(f"Paro {name}: {result.detail}")
            break
        if result.status == "sin_sesion":
            state.data.setdefault("sesion_perdida", []).append(portal)
            print(f"Sin sesión de {name}: python -m runner entrar {portal}")
            break
        if result.status == "enviada":
            try:
                api.post(f"/applications/{v['app']}/sent", {"cv_id": v["cv_id"], "platform": name})
            except ApiError as e:
                print(f"    Enviada en {name}, pero la app no la registró: {e.detail}")
            state.mark(job_id, "enviada", portal=portal, **{k: v[k] for k in ("app", "cv", "cv_id", "url", "puntaje")})
            state.count(sent_key)
        elif result.status == "saltada" and result.unanswered and quota.get("agotado"):
            print("    Sin cupo de IA para sus preguntas hoy: sigue preparada para la próxima vuelta.")
        elif result.status in ("saltada", "externa", "ya_postulada"):
            keep = {k: v[k] for k in ("cv", "cv_id", "puntaje") if k in v}  # para reintentarla si luego hay respuesta
            state.mark(job_id, result.status, portal=portal, app=v["app"], url=v["url"], **keep,
                       preguntas=result.unanswered[:6], detalle=result.detail[:200])
        state.save()
        if n < min(len(pending), limit or len(pending)) - 1:
            _time.sleep(random.uniform(*conf.pause_seconds) if result.status == "enviada" else random.uniform(8, 20))


def cmd_postular(args) -> int:
    from playwright.sync_api import sync_playwright

    from runner import browser

    conf = cfg.load()
    submit = conf.mode == "auto" and not args.prueba
    api = Api(conf.api, conf.token)
    state = State(cfg.DATA_DIR / "estado.json")
    state.data["sesion_perdida"] = []
    print("Modo AUTOMÁTICO: se envían." if submit else "Modo PRUEBA: no se envía nada.")
    if retried := _retry_answered(state, conf):
        print(f"{retried} vacantes saltadas ya tienen respuesta a sus preguntas: vuelven a la cola.")
    todo = []
    for portal, name in cfg.PORTALS.items():
        if args.portal and portal != args.portal:
            continue
        pending = _pending(state, portal)
        if not pending:
            continue
        paused = _key("cuenta", portal)
        if (until := state.pause_until(paused)) and until > datetime.now(UTC):
            print(f"{name}: postulación en pausa hasta {until:%Y-%m-%d %H:%M} UTC ({state.pause_reason(paused)}).")
            continue
        if portal == "linkedin" and not browser.has_session():
            print("El navegador del bot no tiene sesión de LinkedIn: python -m runner entrar")
            state.data["sesion_perdida"].append(portal)
            continue
        if portal == "computrabajo" and not conf.general_cvs.get(portal):
            print(f"{name}: falta «cv_general» en [{portal}] (el PDF que queda por defecto): no se postula.")
            continue
        print(f"{name}: {len(pending)} preparadas; hoy van {state.today(_key('enviadas', portal))} de {conf.cap(portal)} enviadas.")
        todo.append((portal, pending))
    if todo:
        with sync_playwright() as p:
            try:
                context = browser.open_context(p)
            except browser.BrowserUnavailableError as e:
                print(e)
                return 0
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(90_000)
            page.set_default_navigation_timeout(120_000)
            try:
                for portal, pending in todo:
                    _apply_portal(page, portal, pending, conf=conf, api=api, state=state, submit=submit, limit=args.max)
            finally:
                state.save()
                context.close()
    state.save()
    return 1 if state.data["sesion_perdida"] else 0


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
        from runner import telegram

        if until := telegram.paused_until():
            print(f"En pausa (pedida por Telegram) hasta {until.astimezone():%Y-%m-%d %H:%M}: no corro esta vuelta.")
            return 0
        try:
            cmd_buscar(argparse.Namespace(sin_cv=False, max=0, portal=None))
        except (cfg.ConfigError, ApiError):
            raise
        except Exception:  # noqa: BLE001 — si la búsqueda falla, igual se postula a lo ya preparado
            traceback.print_exc()
        try:
            watched = _watch_sites()
        except Exception:  # noqa: BLE001 — vigilar nunca tumba la vuelta
            traceback.print_exc()
            watched = []
        code = cmd_postular(argparse.Namespace(prueba=False, max=0, portal=None))
        state = State(cfg.DATA_DIR / "estado.json")
        notice = f"Hoy: {state.today('enviadas')} enviadas y {state.today('preparadas')} preparadas."
        for portal, name in cfg.PORTALS.items():
            if portal == "linkedin":
                continue
            sent, ready = state.today(_key("enviadas", portal)), state.today(_key("preparadas", portal))
            if sent or ready:
                notice += f" {name}: {sent} enviadas y {ready} preparadas."
        for portal, name in cfg.PORTALS.items():
            paused = _key("cuenta", portal)
            if (until := state.pause_until(paused)) and until > datetime.now(UTC):
                notice += f" Postulación en pausa: {state.pause_reason(paused)}. Entra tú a {name} y revisa."
        for portal in state.data.get("sesion_perdida", []):
            notice += f" El navegador del bot perdió la sesión de {cfg.PORTALS[portal]}: python -m runner entrar {portal}."
        print(notice)
        _notify(notice)
        questions = telegram.pending_questions(state)
        from runner import watch

        telegram.notify(notice + (f"\n\n{len(questions)} preguntas de filtro sin respuesta: /preguntas" if questions else "")
                        + ("\n\n" + watch.notice(watched) if watched else ""))
        return code


WATCH_PER_ROUND = 5  # ofertas de portales de empresas que la app analiza por vuelta (usan cupo de IA)


def _watch_sites(*, prepare: bool = True) -> list[dict]:
    """Revisa los portales de empresas de `[[vigilar]]` y devuelve las vacantes nuevas que encajan (no postula).

    Con `prepare`, las que encajan pasan a la app, que las analiza; las que llegan a la compatibilidad mínima reciben
    su CV y le llegan a la persona por Telegram, listas para postular."""
    from runner import watch

    sites = watch.load_sites()
    if not sites:
        return []
    state = State(cfg.DATA_DIR / "estado.json")
    new = watch.check(sites, state.data)
    state.save()
    if new:
        print("\n" + watch.notice(new))
    if prepare:
        conf = cfg.load()
        try:
            _prepare_watched(Api(conf.api, conf.token), state, sites)
        finally:
            state.save()
    return new


def _prepare_watched(api: Api, state: State, sites, *, limit: int = WATCH_PER_ROUND) -> int:
    """Las vigiladas que encajan y aún no pasan por la app: análisis, CV y Telegram. Devuelve cuántas se enviaron."""
    import urllib.error
    from hashlib import sha256

    from runner import telegram, watch

    by_name, handled, sent = {s.name: s for s in sites}, 0, 0
    for key, rec in state.data.get("vigiladas", {}).items():
        site = by_name.get(key.split(":", 1)[0])
        if not site or not rec.get("encaja") or "app" in rec or rec.get("listo"):
            continue
        if not watch.matches(site, rec.get("cargo", "")):  # anotada con reglas viejas
            rec["listo"] = "no_encaja"
            continue
        if handled >= limit:
            break
        handled += 1
        try:
            info = watch.posting(watch.fetch(rec["url"]))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  {site.name}: no se pudo abrir «{rec.get('cargo', '')}» ({str(e)[:80]})")
            continue
        if not info["text"] or (info["closes"] and info["closes"] < date.today()):
            rec["listo"] = "cerrada" if info["text"] else "sin_texto"
            continue
        header = f"{info['title'] or rec.get('cargo', '')}\n{site.name}\n{info['place']}\n\n"
        try:
            vacancy = api.add_vacancy(text=header + info["text"], url=rec["url"], posted=info["posted"])
        except ApiError as e:
            print(f"  {site.name}: la app no pudo analizar «{rec.get('cargo', '')}»: {e.detail}")
            if e.status == 429 or e.status >= 500:  # sin cupo de IA o servidor ocupado: se reintenta luego
                break
            rec["listo"] = "error"
            continue
        rec["app"], rec["puntaje"] = vacancy.id, vacancy.score
        if not vacancy.created and not vacancy.unfinished:
            continue  # ya estaba en la app
        if vacancy.score is None or vacancy.score < site.min_score:
            _discard(api, vacancy.id, f"El bot la descartó: compatibilidad {vacancy.score if vacancy.score is not None else '—'} "
                                      f"(mínimo {site.min_score}).")
            print(f"  · {site.name}: {vacancy.role} — compatibilidad {vacancy.score}: descartada")
            continue
        cv_path = ""
        try:
            cv = api.make_cv(vacancy.id)
            cv_path = str(api.download_cv(cv["id"], cfg.DATA_DIR / "cvs" / str(vacancy.id) / cv["filename"]))
        except ApiError as e:
            print(f"        CV no generado: {e.detail}")
        note = f"Postúlate en el portal de {site.name}: pide iniciar sesión (con captcha), así que el bot no puede."
        if info["closes"]:
            note += f" Cierra el {info['closes']:%d/%m/%Y}."
        item = {"id": sha256(rec["url"].encode()).hexdigest()[:12], "url": rec["url"], "titulo": vacancy.role or rec.get("cargo", ""),
                "empresa": site.name, "cv": cv_path, "nota": note, "motivo": "", "respuestas": "", "puntaje": vacancy.score}
        telegram.add_manual(item)
        sent += 1
        print(f"  ✓ {vacancy.score:>3}  {item['titulo']} — {site.name}: CV listo, enviado a Telegram")
    return sent


def cmd_vigilar(_args) -> int:
    from runner import telegram, watch

    if not watch.load_sites():
        print("No hay portales para vigilar: agrega [[vigilar]] a la configuración (ver runner/README.md).")
        return 0
    new = _watch_sites()
    if new:
        telegram.notify(watch.notice(new))
    else:
        print("Sin vacantes nuevas que encajen en los portales vigilados.")
    return 0


def cmd_manual(args) -> int:
    """Agrega una postulación que debe enviar la persona (captcha, cédula o cuenta propia) y se la manda por Telegram."""
    from hashlib import sha256

    from runner import telegram

    cv = str(Path(args.cv).expanduser().resolve()) if args.cv else ""
    if cv and not Path(cv).is_file():
        print(f"No existe el CV: {cv}")
        return 2
    item = {"id": sha256(args.url.encode()).hexdigest()[:12], "url": args.url, "titulo": args.titulo,
            "empresa": args.empresa, "cv": cv, "nota": args.nota or "", "motivo": args.motivo or "",
            "respuestas": str(Path(args.respuestas).expanduser().resolve()) if args.respuestas else "",
            "puntaje": args.puntaje}
    sent = telegram.add_manual(item)
    print(f"Agregada: {args.titulo} — {args.empresa}." + (" Enviada por Telegram." if sent else " (Telegram no configurado)"))
    return 0


def cmd_telegram(args) -> int:
    """Configura y corre el bot de Telegram del dueño (avisos y control desde el celular)."""
    import getpass

    from runner import schedule, telegram

    if args.accion == "configurar":
        print("1. En Telegram, habla con @BotFather, envía /newbot y sigue los pasos.")
        try:
            telegram.save_token(getpass.getpass("2. Pega aquí el token que te dio (no se verá): "))
            client = telegram.Client(telegram.token())
            me = client.call("getMe")
        except telegram.TelegramError as e:
            print(e)
            return 1
        code = telegram.pending_code() or telegram.new_code()
        telegram.save_code(code)
        print(f"3. Abre tu bot @{me.get('username')} en Telegram y escríbele exactamente:  /start {code}")
        print("   (solo ese chat podrá usar el bot; te espero 10 minutos aquí)")
        chat = telegram.pair(client, code)
        if not chat:
            print("No llegó todavía. Si ya instalaste el servicio (python -m runner telegram instalar), tu bot seguirá")
            print(f"esperando «/start {code}» sin límite de tiempo.")
            return 1
        client.send(chat, "¡Listo! Desde aquí te aviso lo que solo tú puedes hacer.\n\n" + telegram.HELP)
        print("Emparejado. Ahora deja el bot escuchando siempre: python -m runner telegram instalar")
        return 0
    if args.accion == "instalar":
        workdir = Path(__file__).resolve().parent.parent
        try:
            schedule.install_listener(sys.executable, workdir, cfg.DATA_DIR / "telegram.log")
        except schedule.ScheduleError as e:
            print(e, file=sys.stderr)
            return 2
        print("El bot de Telegram queda escuchando (también al encender el computador).")
        return 0
    if args.accion == "quitar":
        schedule.remove_listener()
        print("Listo: el bot de Telegram ya no escucha.")
        return 0
    tok, chat = telegram.token(), telegram.chat_id()
    if tok and not chat and args.accion == "escuchar" and (code := telegram.pending_code()):
        print(f"Esperando «/start {code}» en Telegram para emparejar…")
        client = telegram.Client(tok)
        chat = telegram.pair(client, code, minutes=60 * 24 * 365)
        if chat:
            client.send(chat, "¡Listo! Desde aquí te aviso lo que solo tú puedes hacer.\n\n" + telegram.HELP)
    if not tok or not chat:
        print("Falta configurarlo: python -m runner telegram configurar")
        return 1
    if args.accion == "probar":
        return 0 if telegram.notify("Prueba del bot: todo bien.") else 1
    print("Escuchando mensajes de Telegram… (Ctrl+C para salir)")
    telegram.serve(telegram.Client(tok), chat)
    return 0


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
    entrar = sub.add_parser("entrar")
    entrar.add_argument("portal", nargs="?", default="linkedin", choices=list(LOGINS),
                        help="linkedin (si no se dice), computrabajo, magneto, elempleo o bancolombia")
    entrar.set_defaults(fn=cmd_entrar)
    importar = sub.add_parser("importar")
    importar.add_argument("pdf", help="ruta del PDF (tu CV o «Guardar en PDF» de tu perfil de LinkedIn)")
    importar.set_defaults(fn=cmd_importar)
    buscar = sub.add_parser("buscar")
    buscar.add_argument("--sin-cv", action="store_true", help="solo analizar, sin generar el CV")
    buscar.add_argument("--max", type=int, default=0, help="preparar como mucho N vacantes en esta vuelta")
    buscar.add_argument("--portal", choices=list(cfg.PORTALS), help="solo este portal")
    buscar.set_defaults(fn=cmd_buscar)
    postular = sub.add_parser("postular")
    postular.add_argument("--prueba", action="store_true", help="llegar a la revisión y descartar, aunque el modo sea auto")
    postular.add_argument("--max", type=int, default=0, help="como mucho N vacantes en esta vuelta")
    postular.add_argument("--portal", choices=list(cfg.PORTALS), help="solo este portal")
    postular.set_defaults(fn=cmd_postular)
    sub.add_parser("diario").set_defaults(fn=cmd_diario)
    sub.add_parser("vigilar").set_defaults(fn=cmd_vigilar)
    manual = sub.add_parser("manual", help="una postulación que envías tú; te llega por Telegram con su CV")
    manual.add_argument("url")
    manual.add_argument("--titulo", required=True)
    manual.add_argument("--empresa", required=True)
    manual.add_argument("--cv", help="ruta del CV en PDF")
    manual.add_argument("--nota", help="qué te pide el formulario")
    manual.add_argument("--motivo", help="por qué encaja contigo")
    manual.add_argument("--respuestas", help="archivo con respuestas sugeridas")
    manual.add_argument("--puntaje", type=int)
    manual.set_defaults(fn=cmd_manual)
    tg = sub.add_parser("telegram")
    tg.add_argument("accion", nargs="?", default="escuchar", choices=["configurar", "instalar", "quitar", "probar", "escuchar"])
    tg.set_defaults(fn=cmd_telegram)
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
