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
