"""Engine/sessao SQLAlchemy 2.0 (async) + SQLite.

Sem Alembic: `init_models()` roda `Base.metadata.create_all()` no startup
do FastAPI (`app/main.py`) - decisao explicita para o prazo do hackathon,
ver `.sdds/specs/consentimento-grupo.spec.md` secao 7.

`create_all()` sozinho so cria tabelas que nao existem - nunca adiciona
coluna nova numa tabela ja existente. Isso ja forcou apagar o banco em
producao 2x (trigger_keyword, removal_pending). `_add_missing_columns()`
cobre esse caso: pra cada coluna do modelo que nao existe na tabela real,
roda `ALTER TABLE ADD COLUMN` (SQLite suporta isso). So aditivo - nunca
remove/renomeia coluna, nunca precisa apagar dado.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _existing_columns(sync_conn: Connection, table_name: str) -> set[str]:
    return {c["name"] for c in inspect(sync_conn).get_columns(table_name)}


async def _add_missing_columns(conn: AsyncConnection) -> None:
    for table in Base.metadata.sorted_tables:
        existing = await conn.run_sync(_existing_columns, table.name)
        for column in table.columns:
            if column.name in existing:
                continue
            ddl_type = column.type.compile(dialect=conn.dialect)
            await conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'))


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
