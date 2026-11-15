"""
Modelo del registro de auditoría — Epic 05, HU12 Escenario 2.

Vive en una base de datos SEPARADA (audit_logs.db) de la operacional por dos
motivos:
  1. Un audit trail debe ser append-only e independiente del ciclo de vida
     de los datos clínicos (rendición de cuentas / Ley de Protección de
     Datos Personales).
  2. Evita bloqueos de SQLite: el middleware escribe el registro justo
     cuando la respuesta se genera, mientras la transacción del endpoint
     aún puede estar abierta en la BD principal.

Por eso no usa claves foráneas físicas: `user_id` y `patient_id` son
referencias lógicas (desnormalizadas con username/patient para conservar
el histórico aunque el usuario o paciente se eliminen).
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.audit_database import AuditBase


class AuditLog(AuditBase):
    """Registro cronológico de accesos: fecha, hora, usuario y acción
    (consulta, creación, edición, eliminación, exportación)."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String, nullable=True)   # desnormalizado
    user_role = Column(String, nullable=True)
    patient_id = Column(Integer, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    # "consulta" / "creacion" / "edicion" / "eliminacion" / "exportacion"
    resource = Column(String, nullable=True)   # "pacientes" / "predicciones" / ...
    method = Column(String, nullable=True)     # GET / POST / PUT / PATCH / DELETE
    endpoint = Column(String, nullable=True)   # ruta solicitada
    status_code = Column(Integer, nullable=True)
    ip_address = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
