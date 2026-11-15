"""
Middleware de auditoría de accesos — Epic 05, HU12 Escenario 2.

Registra automáticamente en la base de datos de auditoría (audit_logs.db)
cada operación sobre los datos clínicos de los pacientes: quién (usuario),
cuándo (fecha y hora), qué (recurso y endpoint) y qué acción realizó
(consulta, creación, edición, eliminación o exportación).

Diseño:
  * Escribe en una BD SEPARADA de la operacional: nunca compite por el
    candado de escritura de SQLite con la transacción del endpoint.
  * Identifica al usuario decodificando el JWT (sub/uid/role) sin
    consultar la BD principal.
  * Nunca rompe la petición: si falla el registro, se loguea el error y
    la respuesta original se devuelve intacta.
  * Ignora rutas ruidosas o ajenas a datos clínicos (login, health, docs,
    sondeos periódicos de alertas/notificaciones del frontend).
"""

import logging
import re
from datetime import datetime

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.audit_database import AuditSessionLocal
from app.audit_models import AuditLog

logger = logging.getLogger(__name__)

# Rutas que NO se auditan: autenticación (pre-sesión), salud del servicio,
# documentación y sondeos periódicos del frontend (alertas/notificaciones
# globales) para no saturar el registro con consultas sin datos de paciente.
_EXCLUDED_PATHS = (
    "/api/auth",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# Sondeos del Layout (polling cada 60 s) — listados globales sin patient_id.
_EXCLUDED_EXACT = {
    "GET /api/alerts",
    "GET /api/notifications",
}

# Extracción de patient_id desde la ruta: /api/patients/3, /api/predictions/3,
# /api/glucose/3, /api/clinical-data/3, /api/notifications/3, ...
_PATIENT_PATH_RE = re.compile(
    r"^/api/(patients|predictions|glucose|clinical-data|notifications|"
    r"nutrition/patients)/(\d+)"
)

# Recurso auditado según el prefijo de la ruta.
_RESOURCE_MAP = [
    ("patients", "pacientes"),
    ("predictions", "predicciones"),
    ("predict", "predicciones"),
    ("clinical-data", "datos_clinicos"),
    ("glucose", "glucosa"),
    ("devices", "dispositivos"),
    ("alerts", "alertas"),
    ("notifications", "notificaciones"),
    ("nutrition", "nutricion"),
    ("appointments", "citas"),
    ("reports", "reportes"),
    ("users", "usuarios"),
    ("audit", "auditoria"),
]

_ACTION_LABEL = {
    "consulta": "Consulta",
    "creacion": "Creación",
    "edicion": "Edición",
    "eliminacion": "Eliminación",
    "exportacion": "Exportación",
}


def _resolve_resource(path: str) -> str | None:
    for prefix, resource in _RESOURCE_MAP:
        if path.startswith(f"/api/{prefix}"):
            return resource
    return None


def _resolve_action(method: str, path: str) -> str | None:
    """Mapea método+ruta → acción de auditoría (HU12: consulta/edición/exportación)."""
    method = method.upper()
    # Exportaciones de datos: PDF de reportes, CSV de auditoría, etc.
    if path.endswith("/pdf") or path.endswith("/csv") or "/export" in path:
        return "exportacion"
    if method == "GET":
        return "consulta"
    if method == "POST":
        return "creacion"
    if method in ("PUT", "PATCH"):
        return "edicion"
    if method == "DELETE":
        return "eliminacion"
    return None


def _extract_patient_id(path: str, query_params) -> int | None:
    """Obtiene el paciente afectado desde la ruta o el query string."""
    match = _PATIENT_PATH_RE.match(path)
    if match:
        try:
            return int(match.group(2))
        except ValueError:
            pass
    # /api/appointments?patient_id=5, /api/audit?patient_id=5, ...
    raw = query_params.get("patient_id")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return None


class AuditMiddleware(BaseHTTPMiddleware):
    """Registra los accesos a datos clínicos en el log de auditoría."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Filtrar rutas no auditables
        if (
            not path.startswith("/api")
            or method == "OPTIONS"
            or any(path.startswith(p) for p in _EXCLUDED_PATHS)
            or f"{method} {path}" in _EXCLUDED_EXACT
        ):
            return await call_next(request)

        # Ejecutar la petición original
        response = await call_next(request)

        # Identificar al usuario desde el token JWT (sin tocar la BD principal)
        username = None
        user_role = None
        user_id = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
                )
                username = payload.get("sub")
                user_role = payload.get("role")
                uid = payload.get("uid")
                if uid is not None:
                    try:
                        user_id = int(uid)
                    except (TypeError, ValueError):
                        user_id = None
            except JWTError:
                # Token inválido/expirado: los endpoints protegidos ya
                # habrán respondido 401/403. No auditar usuarios anónimos.
                return response

        action = _resolve_action(method, path)
        if action is None:
            return response

        resource = _resolve_resource(path)
        patient_id = _extract_patient_id(path, request.query_params)

        # Persistir el registro de auditoría (mejor-effort: nunca falla la API)
        try:
            async with AuditSessionLocal() as session:
                session.add(
                    AuditLog(
                        user_id=user_id,
                        username=username,
                        user_role=user_role,
                        patient_id=patient_id,
                        action=action,
                        resource=resource,
                        method=method,
                        endpoint=path,
                        status_code=response.status_code,
                        ip_address=request.client.host if request.client else None,
                        details=(
                            f"{_ACTION_LABEL.get(action, action)} de "
                            f"{resource or 'recurso'} ({method} {path})"
                        ),
                        created_at=datetime.utcnow(),
                    )
                )
                await session.commit()
        except Exception as exc:  # pragma: no cover — robustez del middleware
            logger.warning("No se pudo registrar la auditoría de %s %s: %s", method, path, exc)

        return response
