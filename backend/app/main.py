from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, AsyncSessionLocal, run_migrations
from app.models import User
from app.auth import get_password_hash
from app.routers import (
    auth_router,
    patients_router,
    clinical_data_router,
    predictions_router,
    devices_router,
    glucose_router,
    alerts_router,
    notifications_router,
    nutrition_router,
    appointments_router,
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_default_admin(db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.username == "admin"))
    admin = result.scalar_one_or_none()
    if admin is None:
        admin_user = User(
            username="admin",
            hashed_password=get_password_hash("admin123"),
            full_name="System Administrator",
            role="admin",
            is_active=True,
        )
        db.add(admin_user)
        await db.flush()
        print("✅ Default admin user created (username: admin, password: admin123)")
    else:
        print("ℹ️  Admin user already exists, skipping creation.")

    # Epic 04 — Sprint 03: default nutritionist user
    result = await db.execute(select(User).where(User.username == "nutricionista"))
    nutritionist = result.scalar_one_or_none()
    if nutritionist is None:
        nutritionist_user = User(
            username="nutricionista",
            hashed_password=get_password_hash("nutricionista123"),
            full_name="Nutricionista Laura Pérez",
            role="nutritionist",
            is_active=True,
        )
        db.add(nutritionist_user)
        await db.flush()
        print("✅ Default nutritionist user created (username: nutricionista, password: nutricionista123)")
    else:
        print("ℹ️  Nutritionist user already exists, skipping creation.")


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Startup: run migrations, create tables, and default admin
    await run_migrations()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created/verified.")

    async with AsyncSessionLocal() as session:
        try:
            await _create_default_admin(session)
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"⚠️  Error creating default admin: {e}")

    yield

    # Shutdown
    await engine.dispose()
    print("🔌 Database connection closed.")


app = FastAPI(
    title="Diabetes Detection MVP API",
    version="1.0.0",
    description="Early detection system for Type 2 Diabetes with BLE glucose monitoring and ML-based risk prediction",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router)
app.include_router(patients_router.router)
app.include_router(clinical_data_router.router)
app.include_router(predictions_router.router)
app.include_router(devices_router.router)
app.include_router(glucose_router.router)
app.include_router(alerts_router.router)
# Epic 04 — Sprint 03 (Monitoreo y seguimiento)
app.include_router(notifications_router.router)
app.include_router(nutrition_router.router)
app.include_router(appointments_router.router)


@app.get("/api/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "Diabetes Detection MVP API",
        "version": "1.0.0",
    }
