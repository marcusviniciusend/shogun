"""Engine, sessão por request e criação de tabelas.

O acesso é síncrono. O SQLAlchemy async traria um driver a mais (`aiosqlite`) e
um estilo de código diferente do resto do servidor, para ganhar concorrência que
o SQLite serializa de qualquer jeito — um escritor por vez. Segue-se aqui o
mesmo padrão já usado com `PendenciasProvider`: chamada síncrona, executada em
threadpool pela rota, sem bloquear o event loop.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Base


def criar_engine(url: str) -> Engine:
    """Engine para `url`, com os ajustes que o SQLite exige."""
    kwargs: dict = {"future": True}

    if url.startswith("sqlite"):
        # O FastAPI atende cada request numa thread do pool; o default do
        # driver do SQLite recusa a conexao fora da thread que a criou.
        kwargs["connect_args"] = {"check_same_thread": False}

        if url in ("sqlite://", "sqlite:///:memory:"):
            # Banco em memoria (testes): cada conexao nova seria um banco vazio
            # diferente. StaticPool mantem uma so, entao o schema criado
            # continua la no acesso seguinte.
            kwargs["poolclass"] = StaticPool

    return create_engine(url, **kwargs)


def sessionmaker_do_engine(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = criar_engine(settings.shogun_database_url)
SessionLocal = sessionmaker_do_engine(engine)


def criar_tabelas(engine_alvo: Engine | None = None) -> None:
    """Cria o schema. Usado pelos testes; em produção quem cria é o Alembic."""
    Base.metadata.create_all(engine_alvo or engine)


def get_db() -> Iterator[DbSession]:
    """Uma sessão de banco por request, fechada ao final.

    Dependência síncrona: o FastAPI a executa na threadpool, então abrir e
    fechar conexão não bloqueia o event loop. Sobrescrita nos testes via
    `app.dependency_overrides`.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
