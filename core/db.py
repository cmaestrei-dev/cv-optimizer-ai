import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import config


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_engine_url: str | None = None
_lock = threading.Lock()


def database_url() -> str:
    """DATABASE_URL (Postgres en producción) o un SQLite local separado del legado."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        return f"sqlite:///{os.path.join(config.DATA_DIR, 'cv_core.db')}"
    # Neon y otros proveedores entregan postgres:// o postgresql://; usamos el driver psycopg 3.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    global _engine, _engine_url
    url = database_url()
    with _lock:
        if _engine is None or _engine_url != url:
            if _engine is not None:
                _engine.dispose()
            if url.startswith("sqlite"):
                _engine = create_engine(url, connect_args={"check_same_thread": False})
                event.listen(_engine, "connect", _enable_sqlite_foreign_keys)
            else:
                # pool_pre_ping: Neon suspende el cómputo tras inactividad y corta conexiones.
                # prepare_threshold=None: sin sentencias preparadas, seguras tras el pooler (PgBouncer).
                _engine = create_engine(
                    url, pool_pre_ping=True, pool_size=3, max_overflow=2,
                    connect_args={"prepare_threshold": None},
                )
            _engine_url = url
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upgrade_schema() -> None:
    """Aplica las migraciones de Alembic pendientes (idempotente).

    Streamlit y la API comparten la base. Si la base ya está en una revisión que este código no
    conoce (la otra app se desplegó con una migración más nueva), no se toca ni se cae: las
    migraciones son aditivas y el código viejo sigue funcionando con columnas o tablas de más.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(root, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    alembic_cfg.attributes["skip_logging_config"] = True  # no pisar el logging de la app
    known = {rev.revision for rev in ScriptDirectory.from_config(alembic_cfg).walk_revisions()}
    with get_engine().connect() as connection:
        current = MigrationContext.configure(connection).get_current_heads()
    if any(rev not in known for rev in current):
        logging.getLogger(__name__).warning(
            "La base está en una revisión más nueva que este código (%s): no se migra. Despliega la versión actual.",
            ", ".join(current),
        )
        return
    command.upgrade(alembic_cfg, "head")
