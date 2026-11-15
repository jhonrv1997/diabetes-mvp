from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, AsyncSessionLocal, run_migrations
from app.models import User
from app.auth import get_password_hash
from app.audit_database import init_audit_db, audit_engine
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
    # Epic 05 — Sprint 04 (Reportes, usuarios y auditoría)
    users_router,
    reports_router,
    audit_router,
)
from app.audit_middleware import AuditMiddleware

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

    # Epic 05 — Sprint 04: usuarios por defecto (HU07/HU11/HU12)
    for username, password, full_name, role in [
        (
            "jefe",
            "jefe123",
            "Dr. Ricardo Mendoza — Jefe del Centro de Salud",
            "health_manager",
        ),
        (
            "medico",
            "medico123",
            "Dr. Alberto Ramírez — Médico Endocrinólogo",
            "doctor",
        ),
    ]:
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none() is None:
            db.add(
                User(
                    username=username,
                    hashed_password=get_password_hash(password),
                    full_name=full_name,
                    role=role,
                    is_active=True,
                )
            )
            await db.flush()
            print(f"✅ Default user created (username: {username}, password: {password}, role: {role})")
        else:
            print(f"ℹ️  User '{username}' already exists, skipping creation.")


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Startup: run migrations, create tables, and default admin
    await run_migrations()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created/verified.")

    # Epic 05 — HU12: tablas del registro de auditoría (BD dedicada)
    await init_audit_db()
    print("✅ Audit database tables created/verified.")

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
    await audit_engine.dispose()
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

# Epic 05 — HU12: middleware de auditoría de accesos a datos clínicos.
# Se registra después de CORS para ejecutarse en el orden correcto.
app.add_middleware(AuditMiddleware)

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
# Epic 05 — Sprint 04 (Reportes, usuarios y auditoría)
app.include_router(users_router.router)
app.include_router(reports_router.router)
app.include_router(audit_router.router)


@app.get("/api/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "Diabetes Detection MVP API",
        "version": "1.0.0",
    }
