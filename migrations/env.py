from logging.config import fileConfig

from alembic import context

import core.profile.models  # noqa: F401  (registra las tablas en Base.metadata)
import core.tracking.models  # noqa: F401
from core.db import Base, get_engine

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_engine().url), target_metadata=target_metadata, literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # El modo batch recrea tablas (crea la nueva, copia y BORRA la vieja). Con las llaves
            # foráneas activas, ese borrado eliminaría en cascada todo lo que cuelga de la tabla.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        try:
            # render_as_batch: permite ALTER TABLE en SQLite (local/tests) con el mismo script.
            context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            if sqlite:  # la conexión vuelve al pool: debe quedar como las demás
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
