"""Bot de postulación de CV Optimizer.

    python -m runner configurar      crea la configuración para editar
    python -m runner token           guarda el token del bot (se crea en la app: Perfil → Bot de LinkedIn)
    python -m runner entrar          abre el navegador del bot para que inicies sesión en LinkedIn (una vez)
    python -m runner buscar          busca vacantes, las analiza con tu perfil y prepara el CV de cada una
"""

import argparse
import getpass
import sys
from datetime import UTC, date, datetime

from runner import config as cfg
from runner import discover
from runner.api import Api, ApiError
from runner.state import State


def _excluded(card: discover.Card, conf: cfg.Config) -> str:
    title, company = card.title.lower(), card.company.lower()
    if word := next((w for w in conf.exclude_words if w and w in title), ""):
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


def cmd_entrar(_args) -> int:
    from runner.browser import login  # Playwright solo hace falta para el navegador

    return login()


def cmd_buscar(args) -> int:
    conf = cfg.load()
    api = Api(conf.api, conf.token)
    state = State(cfg.DATA_DIR / "estado.json")
    if (until := state.pause_until()) and until > datetime.now(UTC):
        print(f"En pausa hasta {until:%Y-%m-%d %H:%M} UTC: {state.data.get('pausa_motivo', '')}")
        return 0
    me = api.me()
    if not me.get("has_experience"):
        print("Tu perfil no tiene experiencia todavía: cárgalo en la app (Perfil → Importar CV) antes de usar el bot.")
        return 1
    done = state.today("preparadas")
    print(f"Modo {conf.mode}. Hoy van {done} de {conf.daily_cap}.")
    try:
        for search in conf.searches:
            if done >= conf.daily_cap:
                break
            cards = discover.discover(search)
            print(f"\n«{search.keywords}» en {search.place}: {len(cards)} vacantes")
            for card in cards:
                if done >= conf.daily_cap:
                    print("Tope diario alcanzado.")
                    break
                if state.seen(card.job_id):
                    continue
                if reason := _excluded(card, conf):
                    state.mark(card.job_id, "excluida", motivo=reason)
                    print(f"  · {card.title} — {card.company}: omitida ({reason})")
                    continue
                discover.pause()
                text = discover.parse_posting(discover.fetch(discover.posting_url(card.job_id)))
                if not text:
                    state.mark(card.job_id, "sin_texto")
                    continue
                header = f"{card.title}\n{card.company}\n{card.place}\n\n"
                try:
                    vacancy = api.add_vacancy(text=header + text, url=card.url, posted=card.posted)
                except ApiError as e:
                    if e.status == 429:  # cupo diario de IA de la cuenta
                        print(f"Cupo de IA agotado por hoy: {e.detail}")
                        return 0
                    state.mark(card.job_id, "error", detalle=e.detail[:200])
                    print(f"  ✗ {card.title}: {e.detail}")
                    continue
                if not vacancy.created:
                    state.mark(card.job_id, "repetida", app=vacancy.id)
                    continue
                line = f"  ✓ {vacancy.score if vacancy.score is not None else '—':>3}  {vacancy.role} — {vacancy.company}"
                if vacancy.missing:
                    line += f"  (falta: {'; '.join(vacancy.missing[:2])})"
                print(line)
                cv_path = ""
                if conf.make_cv and not args.sin_cv:
                    try:
                        cv = api.make_cv(vacancy.id)
                        cv_path = str(api.download_cv(cv["id"], cfg.DATA_DIR / "cvs" / f"{vacancy.id}.pdf"))
                        print(f"        CV: {cv['filename']}")
                    except ApiError as e:
                        print(f"        CV no generado: {e.detail}")
                state.mark(card.job_id, "preparada", app=vacancy.id, puntaje=vacancy.score, cv=cv_path, url=card.url)
                state.count("preparadas")
                done += 1
                state.save()
    except discover.BlockedError as e:
        state.pause(24, str(e))
        print(f"\nParo: {e} Pausa de 24 horas.")
    finally:
        state.save()
    print(f"\nListo: {done} de {conf.daily_cap} hoy ({date.today()}). Revísalas en la app: Postulaciones.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runner", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("configurar").set_defaults(fn=cmd_configurar)
    sub.add_parser("token").set_defaults(fn=cmd_token)
    sub.add_parser("entrar").set_defaults(fn=cmd_entrar)
    buscar = sub.add_parser("buscar")
    buscar.add_argument("--sin-cv", action="store_true", help="solo analizar, sin generar el CV")
    buscar.set_defaults(fn=cmd_buscar)
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
