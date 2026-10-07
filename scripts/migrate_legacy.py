"""Migra los perfiles del almacenamiento anterior (Turso o SQLite local) al perfil estructurado.

Uso:
  python scripts/migrate_legacy.py                     # simulación: muestra el reporte, no guarda
  python scripts/migrate_legacy.py --apply             # guarda en DATABASE_URL
  python scripts/migrate_legacy.py --legacy-dir RUTA   # lee un SQLite legado de otra carpeta

Las tablas anteriores no se modifican. Los usuarios que ya existen en el destino se omiten.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import storage  # noqa: E402
from core.db import database_url, session_scope, upgrade_schema  # noqa: E402
from core.profile.migration import migrate_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="guardar (por defecto solo simula)")
    parser.add_argument("--legacy-dir", help="carpeta que contiene cv_optimizer.db (sin Turso)")
    args = parser.parse_args()

    if args.legacy_dir:
        config.DATA_DIR = os.path.abspath(args.legacy_dir)
    target = database_url().split("@")[-1]  # sin credenciales
    print(f"Origen: {storage.get_storage_info()['mode']} | Destino: {target} | "
          f"{'APLICAR' if args.apply else 'SIMULACIÓN'}")

    upgrade_schema()
    with session_scope() as session:
        reports = migrate_all(session, storage.list_profiles(), storage.export_profile_rows)
        if not args.apply:
            session.rollback()

    for r in reports:
        if r.skipped:
            print(f"- {r.username}: ya existe en el destino, omitido")
            continue
        print(f"- {r.username}: {r.experiences} experiencias, {r.achievements} logros, "
              f"{r.skills} habilidades ({r.duplicate_skills} duplicadas), {r.education} estudios, "
              f"{len(r.warnings)} advertencias")
        for warning in r.warnings:
            print(f"    ! {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
