from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, inspect
from typing import AsyncGenerator

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Auto-migration for SQLite ──────────────────────────────────────────────
# SQLAlchemy's create_all() only creates tables that don't exist yet.
# It does NOT add new columns to existing tables. This function detects
# missing columns and adds them via ALTER TABLE so the DB stays in sync
# with the models without requiring Alembic or manual migrations.


# Define expected columns per table that may have been added after the
# initial schema. Format: {table_name: {column_name: "SQL column definition"}}
_MIGRATIONS = {
    "predictions": {
        "shap_explanation_json": "TEXT DEFAULT NULL",
        "shap_base_value": "FLOAT DEFAULT NULL",
        "shap_method": "VARCHAR DEFAULT NULL",
    },
}


async def run_migrations() -> None:
    """Check for missing columns and add them with ALTER TABLE."""
    async with engine.begin() as conn:
        for table_name, expected_columns in _MIGRATIONS.items():
            # Check if the table exists at all
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table_name},
            )
            if result.scalar_one_or_none() is None:
                # Table doesn't exist yet — create_all will handle it
                continue

            # Get existing column names
            result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing_columns = {row[1] for row in result.fetchall()}

            # Add any missing columns
            for col_name, col_def in expected_columns.items():
                if col_name not in existing_columns:
                    await conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
                        )
                    )
                    print(f"✅ Migration: added column '{col_name}' to table '{table_name}'")