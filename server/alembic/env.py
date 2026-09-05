"""Ambiente do Alembic.

A URL do banco NAO vem do alembic.ini: vem de `SHOGUN_DATABASE_URL`, a mesma
que o servidor usa. Duas fontes de verdade para o endereco do banco e como
migrar um banco e rodar contra outro.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# O servidor ainda nao e empacotado; torna `app` importavel a partir de server/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.models import Base  # noqa: E402

config = context.config
config.set_main_option("sqlalchemy.url", settings.shogun_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite nao faz ALTER TABLE completo; o batch mode recria a tabela
            # por baixo. Sem isso, a primeira migracao que altere coluna falha.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
