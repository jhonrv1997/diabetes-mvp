"""
Base de datos dedicada al registro de auditoría (HU12).

Separada de la BD operacional (diabetes_mvp.db) para:
  * evitar bloqueos de SQLite entre la transacción del endpoint y la
    escritura del middleware de auditoría;
  * mantener el audit trail aislado, append-only e independiente.

Usa modo WAL para permitir escrituras concurrentes sin bloqueos largos.
"""

from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class AuditBase(DeclarativeBase):
    """Metadata independiente para los modelos de la BD de auditoría."""


# Motor dedicado con busy timeout generoso: los registros de auditoría
# nunca deben romper la respuesta al usuario.
audit_engine = create_async_engine(
    settings.AUDIT_DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
)

AuditSessionLocal = async_sessionmaker(
    audit_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@event.listens_for(audit_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Activa WAL para concurrencia de escritura sin bloqueos largos."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


async def init_audit_db() -> None:
    """Crea las tablas de auditoría si no existen."""
    async with audit_engine.begin() as conn:
        await conn.run_sync(AuditBase.metadata.create_all)


async def get_audit_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI para consultar el registro de auditoría."""
    async with AuditSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
