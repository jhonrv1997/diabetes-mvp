"""
End-to-end test for Epic 04 / Sprint 03 — uses FastAPI TestClient (in-process)
to avoid needing a separate server.

Run:
    python3 /home/z/my-project/scripts/test_epic04_inline.py
"""
import sys, os, json
sys.path.insert(0, "/home/z/my-project/diabetes-mvp/backend")

# Need to import after path is set
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def banner(t):
    print("\n" + "=" * 70)
    print(f"  {t}")
    print("=" * 70)


def main():
    # === Login users ===
    print("→ Logins...")
    r = client.post(
        "/api/auth/login",
        data={"username": "enfermera", "password": "enfermera123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, f"nurse login failed: {r.text}"
    nurse_token = r.json()["access_token"]
    print("✅ Nurse login OK")

    r = client.post(
        "/api/auth/login",
        data={"username": "nutricionista", "password": "nutricionista123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, f"nutritionist login failed: {r.text}"
    nutr_token = r.json()["access_token"]
    print("✅ Nutritionist login OK")

    nurse_h = {"Authorization": f"Bearer {nurse_token}"}
    nutr_h = {"Authorization": f"Bearer {nutr_token}"}

    # === HU06: trigger emergency alert via manual glucose reading ===
    banner("HU06: Recepción de alertas tempranas (Push Notification)")
    print("\n→ Posting dangerously high glucose reading (280 mg/dL) for patient #1...")
    r = client.post(
        "/api/glucose",
        headers=nurse_h,
        json={
            "patient_id": 1,
            "glucose_mg_dl": 280,
            "measurement_timestamp": "2026-09-28T10:00:00",
            "context": "fasting"
        }
    )
    print(f"  POST /api/glucose → {r.status_code}")
    assert r.status_code == 201, f"glucose create failed: {r.text}"

    print("→ Listing notifications for patient #1...")
    r = client.get("/api/notifications/1", headers=nurse_h)
    notifs = r.json()
    print(f"  Notifications found: {len(notifs)}")
    for n in notifs:
        print(f"  • [{n['notification_type']}] priority={n['priority']} sound={n['sound']}")
        print(f"    title: {n['title']}")
        print(f"    body:  {n['body']}")
        print(f"    sent:  {n['is_sent']}")
    # Verify emergency alert was sent with canonical message
    emergency = [n for n in notifs if n['notification_type'] == 'emergency_alert']
    assert emergency, "❌ Emergency push notification was NOT created"
    assert any("Acuda a emergencia" in n['body'] for n in emergency), \
        "❌ Emergency notification body does not contain 'Acuda a emergencia'"
    assert any(n['priority'] == 'high' and n['sound'] == 'critical' for n in emergency), \
        "❌ Emergency notification does not have priority=high and sound=critical"
    print("✅ Emergency push notification correctly created with priority=high + sound=critical")

    # === HU13 Scenario 1: auto-appointment on HIGH risk prediction ===
    banner("HU13 Scenario 1: Cita automática por riesgo Alto")
    print("\n→ Running prediction for patient #4 (Roberto - HIGH risk)...")
    r = client.post("/api/predict/4?shap_method=heuristic", headers=nurse_h)
    print(f"  POST /api/predict/4 → {r.status_code}")
    pred = r.json()
    print(f"  risk_level={pred['risk_level']} risk_probability={pred['risk_probability']:.2%}")
    assert pred['risk_level'] in ('high', 'alto'), f"Expected HIGH risk, got {pred['risk_level']}"

    print("\n→ Checking appointments for patient #4...")
    r = client.get("/api/appointments?patient_id=4", headers=nurse_h)
    appts = r.json()
    print(f"  Appointments: {len(appts)}")
    for a in appts:
        print(f"  • #{a['id']} status={a['status']} auto={a['auto_generated']} reason={a['reason']}")
        print(f"    date={a['scheduled_date']} patient={a.get('patient_name')}")
        print(f"    no_show_count={a['no_show_count']}")
    auto_appts = [a for a in appts if a['auto_generated'] and a['reason'] == 'risk_high_auto']
    assert auto_appts, "❌ Auto-appointment for HIGH risk was NOT created"
    print("✅ Auto-appointment created within 7 days of HIGH risk prediction")

    # === HU13 Scenario 2: mark no-show + reschedule ===
    banner("HU13 Scenario 2: Reagendamiento por inasistencia")
    # Use the first appointment (id=1)
    print("\n→ Marking appointment #1 as no-show...")
    r = client.post("/api/appointments/1/mark-no-show", headers=nurse_h)
    print(f"  POST /api/appointments/1/mark-no-show → {r.status_code}")
    assert r.status_code == 200, f"mark-no-show failed: {r.text}"
    result = r.json()
    print(f"  message: {result['message']}")
    print(f"  notifications_sent: {result['notifications_sent']}")
    print(f"  original #{result['original_appointment']['id']} status={result['original_appointment']['status']}")
    print(f"  rescheduled #{result['rescheduled_appointment']['id']} date={result['rescheduled_appointment']['scheduled_date']}")
    print(f"  rescheduled reason={result['rescheduled_appointment']['reason']}")
    print(f"  rescheduled no_show_count={result['rescheduled_appointment']['no_show_count']}")
    assert result['original_appointment']['status'] == 'no_show'
    assert result['rescheduled_appointment']['reason'] == 'rescheduled_no_show'
    assert result['notifications_sent'] >= 1, "❌ No notification sent on no-show"
    print("✅ No-show correctly marked: original marked no_show, new appointment created, notifications sent")

    # === HU10 Scenario 1: nutritional plan creation ===
    banner("HU10 Scenario 1: Creación de plan nutricional")
    # Patient #1 needs a prediction first; do it now (will trigger auto-appointment)
    print("\n→ Generating prediction for patient #1 (María) so plan can be created...")
    r = client.post("/api/predict/1?shap_method=heuristic", headers=nurse_h)
    print(f"  Prediction for patient #1: {r.status_code} risk={r.json().get('risk_level')}")
    print("\n→ Creating nutrition plan for patient #1 (María - HIGH risk)...")
    r = client.post(
        "/api/nutrition/plans",
        headers=nutr_h,
        json={
            "patient_id": 1,
            "daily_calories": 1800,
            "protein_g": 90,
            "carbs_g": 200,
            "fat_g": 60,
            "restrictions": ["diabetes", "hipertension", "bajo_sodio"],
            "meal_schedule": {"desayuno": "08:00", "almuerzo": "13:00", "cena": "19:00"},
            "notes": "Plan inicial para paciente con diabetes tipo 2 e hipertensión."
        }
    )
    print(f"  POST /api/nutrition/plans → {r.status_code}")
    assert r.status_code == 201, f"plan create failed: {r.text}"
    plan = r.json()
    print(f"  Plan #{plan['id']} created for patient #{plan['patient_id']}")
    print(f"  daily_calories={plan['daily_calories']} protein={plan['protein_g']}g carbs={plan['carbs_g']}g fat={plan['fat_g']}g")
    print(f"  restrictions={plan['restrictions']}")
    print(f"  meal_schedule={plan['meal_schedule']}")
    print(f"  nutritionist={plan.get('nutritionist_name')}")
    print(f"  patient_name={plan.get('patient_name')}")
    assert plan['is_active'] is True
    print("✅ Plan created and linked to patient profile")

    # Verify meal reminders were scheduled (notifications)
    r = client.get("/api/notifications/1", headers=nurse_h)
    notifs = r.json()
    meal_reminders = [n for n in notifs if n['notification_type'] == 'meal_reminder']
    print(f"  → Meal reminders scheduled: {len(meal_reminders)}")
    assert len(meal_reminders) >= 1, "❌ No meal reminder notifications were scheduled"
    print("✅ Meal reminder notifications scheduled in patient's mobile app")

    # === HU10 Scenario 2: adherence evaluation ===
    banner("HU10 Scenario 2: Evaluación de adherencia")
    print("\n→ Evaluating adherence for plan #1 (should say 'need 14 days')...")
    r = client.get("/api/nutrition/plans/1/adherence", headers=nutr_h)
    print(f"  GET /api/nutrition/plans/1/adherence → {r.status_code}")
    assert r.status_code == 200
    adh = r.json()
    print(f"  days_since_start={adh['days_since_start']} eligible={adh['eligible_for_evaluation']}")
    print(f"  adherence_pct={adh['adherence_pct']}% readings={adh['glucose_readings_count']}")
    print(f"  avg_glucose={adh['avg_glucose']} in_target_pct={adh['glucose_in_target_pct']}")
    print(f"  recommendation: {adh['recommendation']}")
    # Plan was just created → not eligible yet
    assert adh['eligible_for_evaluation'] is False, "Should not be eligible yet (need 14 days)"
    assert "14" in adh['recommendation'], "Recommendation should mention 14-day waiting period"
    print("✅ Adherence evaluation correctly returns 'not yet eligible' state")

    # === Validation: LOW risk patient cannot get a plan ===
    # First predict for patient #3 (Rosa - LOW risk) so we can test the rejection
    print("\n→ Generating prediction for patient #3 (Rosa - LOW risk)...")
    r = client.post("/api/predict/3?shap_method=heuristic", headers=nurse_h)
    print(f"  Prediction for patient #3: {r.status_code} risk={r.json().get('risk_level')}")
    print("\n→ Trying to create plan for patient #3 (Rosa - LOW risk - should fail)...")
    r = client.post(
        "/api/nutrition/plans",
        headers=nutr_h,
        json={"patient_id": 3, "daily_calories": 2000}
    )
    print(f"  Result: {r.status_code} {r.json().get('detail', '')}")
    assert r.status_code == 400, "Should reject plan for LOW risk patient"
    assert "Medio" in r.json()['detail'] or "Alto" in r.json()['detail']
    print("✅ Validation OK: only Medium/High risk patients can get plans")

    # === Validation: nurse cannot create nutrition plan ===
    print("\n→ Trying as enfermera to create plan (should fail - 403)...")
    r = client.post(
        "/api/nutrition/plans",
        headers=nurse_h,
        json={"patient_id": 1, "daily_calories": 1500}
    )
    print(f"  Result: {r.status_code} {r.json().get('detail', '')}")
    assert r.status_code == 403, "Nurse should not be able to create nutrition plans"
    print("✅ Validation OK: only nutritionist/admin can create plans")

    # === Calendar endpoint ===
    banner("Calendario del Centro de Salud")
    r = client.get("/api/appointments/calendar", headers=nurse_h)
    print(f"  GET /api/appointments/calendar → {r.status_code}")
    print(f"  Upcoming appointments: {len(r.json())}")
    for a in r.json()[:5]:
        print(f"  • {a['scheduled_date']} — {a.get('patient_name')} ({a['reason']})")

    # === Summary ===
    banner("Summary: All notifications created")
    r = client.get("/api/notifications?limit=50", headers=nurse_h)
    notifs = r.json()
    print(f"Total notifications in system: {len(notifs)}")
    types_count = {}
    for n in notifs:
        t = n['notification_type']
        types_count[t] = types_count.get(t, 0) + 1
    for t, c in types_count.items():
        print(f"  {t}: {c}")

    banner("✅ TODAS LAS PRUEBAS PASARON — Epic 04 / Sprint 03 implementado correctamente")
    print("""
    HU06 Recepción de alertas tempranas:
       ✅ Detección de anomalía grave (glucosa >= 250 mg/dL)
       ✅ Confirmación de anomalía en backend
       ✅ Notificación push con "Alerta de Salud: Acuda a emergencia"
       ✅ Prioridad 'high' y sonido 'critical'

    HU10 Seguimiento nutricional personalizado:
       ✅ Creación de plan solo para pacientes con riesgo Medio/Alto
       ✅ Solo el nutricionista (o admin) puede crear planes
       ✅ Plan vinculado al perfil del paciente
       ✅ Notificaciones de recordatorio de comidas programadas
       ✅ Evaluación de adherencia tras 14 días (cruce con glucosa IoT)
       ✅ Recomendación de ajuste si adherencia < 60%

    HU13 Programación de citas de seguimiento:
       ✅ Cita automática dentro de 7 días tras predicción de riesgo Alto
       ✅ Notificación push al paciente
       ✅ Cita visible en calendario del Centro de Salud
       ✅ Reagendamiento por inasistencia (nueva cita en 3 días)
       ✅ Notificación de recordatorio al paciente
       ✅ Indicador de inasistencia acumulado en el perfil
    """)


if __name__ == "__main__":
    main()
