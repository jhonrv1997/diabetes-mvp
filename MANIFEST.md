# Epic 04 — Sprint 03 · Diabetes MVP
## Archivos modificados / creados

### Backend — NUEVOS (7)
| Ruta | Propósito |
|---|---|
| `backend/app/services/notification_service.py` | Servicio de notificaciones push (FCM/APNs simulado) — HU06 |
| `backend/app/services/glucose_anomaly_detector.py` | Detector de anomalías graves de glucosa (≥ 250 mg/dL) — HU06 |
| `backend/app/services/nutrition_service.py` | Gestión de planes nutricionales + adherencia — HU10 |
| `backend/app/services/appointment_service.py` | Citas automáticas + reagendamiento — HU13 |
| `backend/app/routers/notifications_router.py` | Router de notificaciones push |
| `backend/app/routers/nutrition_router.py` | Router de planes nutricionales |
| `backend/app/routers/appointments_router.py` | Router de citas de seguimiento |

### Backend — MODIFICADOS (8)
| Ruta | Cambios |
|---|---|
| `backend/app/models.py` | 4 modelos nuevos + rol "nutritionist" |
| `backend/app/schemas.py` | ~130 líneas de esquemas Pydantic nuevos |
| `backend/app/main.py` | Registra 3 routers nuevos + crea nutricionista por defecto |
| `backend/app/database.py` | Comentario de migración para nuevas tablas |
| `backend/app/services/alert_service.py` | Envía push "Alerta de Salud" en riesgo Alto |
| `backend/app/routers/glucose_router.py` | Detecta anomalía tras cada lectura |
| `backend/app/routers/predictions_router.py` | Crea cita automática tras predicción Alto |
| `backend/init_db.py` | Usuario nutricionista + tokens push simulados |

### Frontend — NUEVOS (3)
| Ruta | Propósito |
|---|---|
| `frontend/src/components/NotificationsPanel.jsx` | Vista de notificaciones push |
| `frontend/src/components/NutritionPanel.jsx` | Vista de planes nutricionales |
| `frontend/src/components/AppointmentsPanel.jsx` | Vista de calendario de citas |

### Frontend — MODIFICADOS (2)
| Ruta | Cambios |
|---|---|
| `frontend/src/App.jsx` | 3 nuevas rutas: /notifications, /nutrition, /appointments |
| `frontend/src/components/Layout.jsx` | Navegación por rol + badge de notificaciones |

### Otros (3)
| Ruta | Propósito |
|---|---|
| `Leeme.txt` | Documentación actualizada con credenciales y endpoints |
| `scripts/test_epic04.py` | Pruebas E2E con servidor externo |
| `scripts/test_epic04_inline.py` | Pruebas E2E con FastAPI TestClient (in-process) |
| `worklog.md` | Bitácora de cambios del agente |

## Credenciales por defecto
- **Admin:** admin / admin123
- **Enfermera:** enfermera / enfermera123
- **Nutricionista:** nutricionista / nutricionista123 *(nuevo)*

## Pruebas
```bash
cd /home/z/my-project/diabetes-mvp/backend
rm -f diabetes_mvp.db && python3 init_db.py
python3 /home/z/my-project/scripts/test_epic04_inline.py
```
Salida esperada: `✅ TODAS LAS PRUEBAS PASARON`

---

# Epic 05 — Sprint 04 · Diabetes MVP
## Reportes, Control de Acceso y Auditoría (HU07 / HU11 / HU12)

### Backend — NUEVOS (8)
| Ruta | Propósito |
|---|---|
| `backend/app/audit_models.py` | Modelo AuditLog (BD dedicada, desnormalizado) — HU12 |
| `backend/app/audit_database.py` | Motor/BD de auditoría separada (WAL) + get_audit_db |
| `backend/app/audit_middleware.py` | Registro automático de accesos (middleware) — HU12 Esc. 2 |
| `backend/app/routers/users_router.py` | Gestión de usuarios/roles + matriz de permisos — HU12 Esc. 1 |
| `backend/app/routers/reports_router.py` | Endpoints de reportes JSON/PDF — HU07/HU11 |
| `backend/app/routers/audit_router.py` | Consulta de auditoría + exportación CSV — HU12 Esc. 2 |
| `backend/app/services/report_service.py` | Cálculo de resumen poblacional y reporte mensual |
| `backend/app/services/pdf_report_builder.py` | PDFs institucionales (torta, barras, logotipo) |
| `backend/app/assets/logo_centro_salud.png` | Logotipo del Centro de Salud para los PDF |

### Backend — MODIFICADOS (11)
| Ruta | Cambios |
|---|---|
| `backend/app/models.py` | Roles doctor/health_manager documentados (AuditLog → audit_models) |
| `backend/app/schemas.py` | UserUpdate, RolePermissions, AuditLog*, PopulationSummary, MonthlyReport |
| `backend/app/config.py` | AUDIT_DATABASE_URL |
| `backend/app/main.py` | 3 routers + middleware de auditoría + init BD auditoría + usuarios jefe/medico |
| `backend/app/routers/auth_router.py` | JWT con "uid" para auditoría sin tocar BD principal |
| `backend/app/routers/predictions_router.py` | Predicciones: admin/nurse/doctor (+health_manager lectura) |
| `backend/app/routers/glucose_router.py` | Lectura IoT: sin nutricionista |
| `backend/app/routers/clinical_data_router.py` | Triaje: admin/nurse/doctor |
| `backend/app/routers/alerts_router.py` | Alertas: admin/nurse/doctor/health_manager |
| `backend/app/routers/notifications_router.py` | Notificaciones: admin/nurse/doctor |
| `backend/app/routers/nutrition_router.py` | Nutrición: solo admin/nutritionist |
| `backend/init_db.py` | Usuarios jefe/medico + predicciones + auditoría de muestra |
| `backend/requirements.txt` | + reportlab, pillow |

### Frontend — NUEVOS (4)
| Ruta | Propósito |
|---|---|
| `frontend/src/components/ReportsPanel.jsx` | Módulo de reportes (pestañas HU07/HU11) |
| `frontend/src/components/UsersPanel.jsx` | Gestión de usuarios y roles (HU12 Esc. 1) |
| `frontend/src/components/AuditPanel.jsx` | Auditoría por paciente + CSV (HU12 Esc. 2) |
| `frontend/src/utils/download.js` | Descargas autenticadas (PDF/CSV blob) |

### Frontend — MODIFICADOS (5)
| Ruta | Cambios |
|---|---|
| `frontend/src/App.jsx` | RoleRoute + rutas /reports /users /audit + ErrorBoundary |
| `frontend/src/components/Layout.jsx` | Navegación por rol (5 roles) + badges + sondeos condicionales |
| `frontend/src/components/Login.jsx` | Cuentas de demostración (5 roles) |
| `frontend/src/components/Dashboard.jsx` | "Nuevo Paciente" solo para admin/nurse |
| `frontend/package.json` | (sin cambios de dependencias; recharts ya existía) |

### Otros (2)
| Ruta | Propósito |
|---|---|
| `scripts/test_epic05_inline.py` | Pruebas E2E (67 verificaciones) con TestClient |
| `Leeme.txt` / `worklog.md` | Documentación actualizada |

## Pruebas
```bash
cd backend
rm -f diabetes_mvp.db audit_logs.db*
python3 init_db.py
python3 ../scripts/test_epic05_inline.py
```
Salida esperada: `✅ TODAS LAS PRUEBAS PASARON (67 verificaciones)`
