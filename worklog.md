# Worklog — Diabetes MVP

---
Task ID: epic04-sprint03
Agent: Main agent (GLM)
Task: Implementar Epic 04 Monitoreo y seguimiento - Sprint 03
       HU06 Recepción de alertas tempranas (notificaciones push)
       HU10 Seguimiento nutricional personalizado (planes + adherencia)
       HU13 Programación de citas de seguimiento (auto + reagendamiento)

Work Log:
- Clonado repositorio desde https://github.com/jhonrv1997/diabetes-mvp.git
- Análisis completo de la arquitectura existente (FastAPI + React + SQLite + ML/Shap)
- Backend: 4 nuevos modelos SQLAlchemy (NotificationToken, PushNotification, NutritionPlan, Appointment)
- Backend: Nuevos esquemas Pydantic (~130 líneas en schemas.py)
- Backend: 4 nuevos servicios:
    * NotificationService: simula envío push a FCM/APNs con persistencia
    * NutritionService: gestión de planes + cálculo de adherencia (cruce con datos IoT)
    * AppointmentService: auto-creación por riesgo + reagendamiento por inasistencia
    * GlucoseAnomalyDetector: detecta lecturas peligrosas (≥ 250 mg/dL o patrón 2h)
- Backend: 3 nuevos routers: notifications_router, nutrition_router, appointments_router
- Backend: Integración con glucose_router (detecta anomalías tras cada lectura)
- Backend: Integración con predictions_router (crea cita auto tras predicción Alto)
- Backend: Integración con alert_service (envía push "Alerta de Salud" en riesgo Alto)
- Backend: Nuevo rol "nutritionist" añadido a User y auth.py
- Backend: init_db.py actualizado con usuario nutricionista + tokens push simulados
- Backend: main.py registra los 3 nuevos routers + crea el nutricionista por defecto
- Frontend: 3 nuevos componentes:
    * NotificationsPanel: historial push con filtros por tipo y badge de no-leídas
    * NutritionPanel: form completo de plan + adherencia + recordatorios de comidas
    * AppointmentsPanel: calendario con stats, acciones Completar/Inasistencia
- Frontend: App.jsx añade rutas /notifications, /nutrition, /appointments
- Frontend: Layout.jsx con navegación basada en rol (admin/nurse/nutritionist)
- Frontend: Build verificado con `vite build` (sin errores)
- Backend: Pruebas end-to-end con FastAPI TestClient — TODAS LAS PRUEBAS PASAN

Stage Summary:
- 3 Historias de Usuario implementadas y verificadas end-to-end.
- Usuarios por defecto: admin/admin123, enfermera/enfermera123, nutricionista/nutricionista123
- Script de pruebas persistente: /home/z/my-project/scripts/test_epic04_inline.py
- Frontend compila correctamente (build de producción exitoso).
- Sin dependencias externas adicionales (FCM/APNs simulados en capa de servicio).
- Patrones de diseño: deduplicación de alertas, validación de riesgo antes de crear plan,
  prevención de citas duplicadas, acumulación de no_show_count.
- Código documentado en español (mensajes) e inglés (logs técnicos), siguiendo
  el estilo del repositorio original.

---

Task ID: epic05-sprint04
Agent: Main agent (GLM)
Task: Implementar Epic 05 — Reportes, control de acceso y auditoría - Sprint 04
       HU07  Dashboard de Monitoreo Poblacional (Jefe del Centro de Salud)
       HU11  Generación de Reportes para Autoridades de Salud (DIRESA)
       HU12  Control de Acceso y Privacidad de Datos (roles + auditoría)

Work Log:
- Análisis del repositorio clonado (FastAPI + React/Vite + SQLite + ML/SHAP)
- Backend: BD de auditoría DEDICADA (audit_logs.db, modo WAL) con modelo
  AuditLog desnormalizado (app/audit_models.py + app/audit_database.py);
  separada de la operacional para evitar bloqueos de SQLite entre la
  transacción del endpoint y la escritura del middleware.
- Backend: middleware de auditoría (app/audit_middleware.py) que registra
  automáticamente cada acceso a datos de pacientes: fecha, hora, usuario
  (desde el JWT, ahora con "uid"), acción (consulta/creación/edición/
  eliminación/exportación), recurso y estado. Filtra rutas ruidosas.
- Backend: 2 roles nuevos — "health_manager" (Jefe del Centro de Salud) y
  "doctor" (Médico); UserCreate/UserUpdate ampliado + matriz de permisos
  documental en users_router.
- Backend: users_router (CRUD de personal, cambio de rol, activar/desactivar,
  restablecer contraseña, protección de auto-degradación).
- Backend: report_service (resumen poblacional + reporte mensual con filtros
  de edad/fechas, distribución por riesgo, grupos etarios, tasa de aciertos
  con base documentada) y pdf_report_builder (ReportLab: KPIs, gráfico de
  torta, barras por grupo etario, tablas, logotipo, área de firma DIRESA).
- Backend: reports_router con 4 endpoints (JSON + PDF) restringidos a
  admin/health_manager; audit_router con logs por paciente, filtros y
  exportación CSV (BOM UTF-8 para Excel).
- Backend: control de acceso aplicado en routers existentes según HU12
  (nutricionista SOLO nutrición; médico → predicciones/historial/alertas;
  enfermera → triaje; jefe → reportes; auditoría y usuarios → admin).
- Backend: init_db.py con jefe/medico por defecto, predicciones de muestra
  (para que los reportes tengan datos al primer arranque) y 10 entradas
  de auditoría sembradas en la BD dedicada.
- Backend: main.py registra 3 routers nuevos + middleware + init de la BD
  de auditoría; requirements.txt añade reportlab y pillow.
- Backend: logo institucional generado (assets/logo_centro_salud.png).
- Frontend: ReportsPanel (pestañas HU07/HU11: filtros de fechas y edad,
  gráficos de torta/barras con recharts, KPIs, tablas, descarga de PDFs
  vía blob con Authorization Bearer).
- Frontend: UsersPanel (tabla de personal, cambio de rol inline, alta de
  cuentas, matriz de permisos visual) y AuditPanel (selector de paciente,
  filtro por acción, tabla cronológica, exportación CSV).
- Frontend: App.jsx con RoleRoute (rutas protegidas por rol + redirect por
  rol), HomeRedirect (nutricionista → /nutrition) y ErrorBoundary global.
- Frontend: Layout.jsx con navegación por rol (5 roles), badges, sondeos
  condicionales; Login.jsx con cuentas de demostración; Dashboard.jsx
  oculta "Nuevo Paciente" a roles sin permiso.
- Frontend: utils/download.js para descargas autenticadas (PDF/CSV).
- Fix: import BarChart faltante en ReportsPanel (detectado con navegador
  headless + ErrorBoundary).
- Pruebas: scripts/test_epic05_inline.py — 67 verificaciones E2E, TODAS PASAN
  (HU07 resumen+torta+PDF, HU11 indicadores+filtros 40-60+<10s+PDF,
  HU12 roles/matriz/403s/auditoría/CSV, regresión de flujos previos).
- UI verificada end-to-end con navegador headless: login de los 5 roles,
  navegación restringida, generación de reportes, exportaciones.

Stage Summary:
- 3 Historias de Usuario implementadas y verificadas end-to-end (67 checks).
- Usuarios: admin/admin123, jefe/jefe123, medico/medico123,
  enfermera/enfermera123, nutricionista/nutricionista123.
- BD de auditoría separada (audit_logs.db) — patrón audit trail append-only.
- Los PDF incluyen logotipo, gráfico de torta (HU07) y barras etarias (HU11).
- Frontend compila (vite build OK) y probado en navegador real.
