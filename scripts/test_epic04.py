"""
End-to-end test script for Epic 04 / Sprint 03 user stories.

Run while the backend is up:
    python3 /home/z/my-project/scripts/test_epic04.py
"""
import requests, json, time, sys

BASE = "http://localhost:8000/api"


def banner(t):
    print("\n" + "=" * 70)
    print(f"  {t}")
    print("=" * 70)


def main():
    # === Login users ===
    print("→ Logins...")
    r = requests.post(f"{BASE}/auth/login", data={"username": "enfermera", "password": "enfermera123"})
    assert r.status_code == 200, f"nurse login failed: {r.text}"
    nurse_token = r.json()["access_token"]
    print(f"✅ Nurse login OK")

    r = requests.post(f"{BASE}/auth/login", data={"username": "nutricionista", "password": "nutricionista123"})
    assert r.status_code == 200, f"nutritionist login failed: {r.text}"
    nutr_token = r.json()["access_token"]
    print(f"✅ Nutritionist login OK")

    # === HU06: trigger emergency alert via manual glucose reading ===
    banner("HU06: Recepción de alertas tempranas (Push Notification)")
    print("\n→ Posting dangerously high glucose reading (280 mg/dL) for patient #1...")
    r = requests.post(
        f"{BASE}/glucose",
        headers={"Authorization": f"Bearer {nurse_token}"},
        json={
            "patient_id": 1,
            "glucose_mg_dl": 280,
            "measurement_timestamp": "2026-09-28T10:00:00",
            "context": "fasting"
        }
    )
    print(f"  POST /api/glucose → {r.status_code}")
    time.sleep(1)

    print("→ Listing notifications for patient #1...")
    r = requests.get(f"{BASE}/notifications/1", headers={"Authorization": f"Bearer {nurse_token}"})
    notifs = r.json()
    print(f"  Notifications found: {len(notifs)}")
    for n in notifs:
        print(f"  • [{n['notification_type']}] priority={n['priority']} sound={n['sound']}")
        print(f"    title: {n['title']}")
        print(f"    body:  {n['body']}")
        print(f"    sent:  {n['is_sent']}")

    # === HU13: auto-appointment on high risk prediction ===
    banner("HU13 Scenario 1: Cita automática por riesgo Alto")
    print("\n→ Running prediction for patient #4 (Roberto - HIGH risk)...")
    r = requests.post(
        f"{BASE}/predict/4?shap_method=heuristic",
        headers={"Authorization": f"Bearer {nurse_token}"},
    )
    print(f"  POST /api/predict/4 → {r.status_code}")
    if r.status_code == 200:
        pred = r.json()
        print(f"  risk_level={pred['risk_level']} risk_probability={pred['risk_probability']:.2%}")
    else:
        print(f"  ERROR: {r.text[:500]}")

    print("\n→ Checking appointments for patient #4...")
    r = requests.get(f"{BASE}/appointments?patient_id=4", headers={"Authorization": f"Bearer {nurse_token}"})
    appts = r.json()
    print(f"  Appointments: {len(appts)}")
    for a in appts:
        print(f"  • #{a['id']} status={a['status']} auto={a['auto_generated']} reason={a['reason']}")
        print(f"    date={a['scheduled_date']} patient={a.get('patient_name')}")
        print(f"    no_show_count={a['no_show_count']}")

    # === HU13 Scenario 2: mark no-show + reschedule ===
    banner("HU13 Scenario 2: Reagendamiento por inasistencia")
    print("\n→ Marking appointment #1 as no-show...")
    r = requests.post(
        f"{BASE}/appointments/1/mark-no-show",
        headers={"Authorization": f"Bearer {nurse_token}"},
    )
    print(f"  POST /api/appointments/1/mark-no-show → {r.status_code}")
    if r.status_code == 200:
        result = r.json()
        print(f"  message: {result['message']}")
        print(f"  notifications_sent: {result['notifications_sent']}")
        print(f"  original #{result['original_appointment']['id']} status={result['original_appointment']['status']}")
        print(f"  rescheduled #{result['rescheduled_appointment']['id']} date={result['rescheduled_appointment']['scheduled_date']}")
        print(f"  rescheduled reason={result['rescheduled_appointment']['reason']}")
        print(f"  rescheduled no_show_count={result['rescheduled_appointment']['no_show_count']}")
    else:
        print(f"  ERROR: {r.text[:400]}")

    # === HU10: nutritional plan creation ===
    banner("HU10 Scenario 1: Creación de plan nutricional")
    print("\n→ Creating nutrition plan for patient #1 (María - HIGH risk)...")
    r = requests.post(
        f"{BASE}/nutrition/plans",
        headers={"Authorization": f"Bearer {nutr_token}"},
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
    if r.status_code == 201:
        plan = r.json()
        print(f"  Plan #{plan['id']} created for patient #{plan['patient_id']}")
        print(f"  daily_calories={plan['daily_calories']} protein={plan['protein_g']}g carbs={plan['carbs_g']}g fat={plan['fat_g']}g")
        print(f"  restrictions={plan['restrictions']}")
        print(f"  meal_schedule={plan['meal_schedule']}")
        print(f"  nutritionist={plan.get('nutritionist_name')}")
        print(f"  patient_name={plan.get('patient_name')}")
    else:
        print(f"  ERROR: {r.text[:500]}")

    # === HU10 Scenario 2: adherence evaluation ===
    banner("HU10 Scenario 2: Evaluación de adherencia")
    print("\n→ Evaluating adherence for plan #1 (will say 'need 14 days')...")
    r = requests.get(f"{BASE}/nutrition/plans/1/adherence", headers={"Authorization": f"Bearer {nutr_token}"})
    print(f"  GET /api/nutrition/plans/1/adherence → {r.status_code}")
    if r.status_code == 200:
        adh = r.json()
        print(f"  days_since_start={adh['days_since_start']} eligible={adh['eligible_for_evaluation']}")
        print(f"  adherence_pct={adh['adherence_pct']}% readings={adh['glucose_readings_count']}")
        print(f"  avg_glucose={adh['avg_glucose']} in_target_pct={adh['glucose_in_target_pct']}")
        print(f"  recommendation: {adh['recommendation']}")

    # === Validation: LOW risk patient cannot get a plan ===
    print("\n→ Trying to create plan for patient #3 (Rosa - LOW risk - should fail)...")
    r = requests.post(
        f"{BASE}/nutrition/plans",
        headers={"Authorization": f"Bearer {nutr_token}"},
        json={"patient_id": 3, "daily_calories": 2000}
    )
    print(f"  Result: {r.status_code} {r.json().get('detail', r.text[:200])}")

    # === Validation: nurse cannot create nutrition plan ===
    print("\n→ Trying as enfermera to create plan (should fail - 403)...")
    r = requests.post(
        f"{BASE}/nutrition/plans",
        headers={"Authorization": f"Bearer {nurse_token}"},
        json={"patient_id": 1, "daily_calories": 1500}
    )
    print(f"  Result: {r.status_code} {r.json().get('detail', r.text[:200])}")

    # Final list of all notifications in the system
    banner("Summary: All notifications created")
    r = requests.get(f"{BASE}/notifications?limit=50", headers={"Authorization": f"Bearer {nurse_token}"})
    notifs = r.json()
    print(f"Total notifications in system: {len(notifs)}")
    types_count = {}
    for n in notifs:
        t = n['notification_type']
        types_count[t] = types_count.get(t, 0) + 1
    for t, c in types_count.items():
        print(f"  {t}: {c}")

    print("\n✅ All end-to-end tests completed successfully!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Test failed: {e}", file=sys.stderr)
        sys.exit(1)
