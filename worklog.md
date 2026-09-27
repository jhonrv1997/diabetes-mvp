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
