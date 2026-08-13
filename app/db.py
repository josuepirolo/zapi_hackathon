"""Engine/sessao SQLAlchemy 2.0 (async) + SQLite.

Sem Alembic: `init_models()` roda `Base.metadata.create_all()` no startup
do FastAPI (`app/main.py`) - decisao explicita para o prazo do hackathon,
ver `.sdds/specs/consentimento-grupo.spec.md` secao 7.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
