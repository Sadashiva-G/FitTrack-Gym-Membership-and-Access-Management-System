"""End-to-End verification script for all FitTrack core and stretch features."""

from datetime import date, timedelta
import sys
import time
import requests

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8000"


def test_feature(name: str):
    print(f"\n--- Testing: {name} ---")


def main():
    print("=" * 60)
    print("🚀 Running FitTrack End-to-End Verification")
    print("=" * 60)

    # Health check
    test_feature("0. Health Check")
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    print("✅ Health check passed:", r.json())

    run_id = str(time.time_ns())[-6:]

    # 1. Membership Plans
    test_feature("1. Membership Plans (Create, List, Unique Constraint)")
    # Create Plan 1
    p1_name = f"Starter_{run_id}"
    r_p1 = requests.post(f"{BASE_URL}/plans", json={"name": p1_name, "duration_days": 30, "price": 49.99})
    assert r_p1.status_code == 201, f"Create plan failed: {r_p1.text}"
    p1 = r_p1.json()
    print("✅ Created Plan 1:", p1)

    # Create Plan 2
    p2_name = f"Annual_{run_id}"
    r_p2 = requests.post(f"{BASE_URL}/plans", json={"name": p2_name, "duration_days": 365, "price": 399.99})
    assert r_p2.status_code == 201
    p2 = r_p2.json()
    print("✅ Created Plan 2:", p2)

    # Test Duplicate Plan Name (Must return 409 Conflict)
    r_dup = requests.post(f"{BASE_URL}/plans", json={"name": p1_name, "duration_days": 15, "price": 20.0})
    assert r_dup.status_code == 409, f"Expected 409 Conflict on duplicate, got {r_dup.status_code}"
    print("✅ Duplicate plan properly rejected with 409 Conflict:", r_dup.json()["detail"])

    # Test Validation (duration <= 0, price < 0)
    r_bad = requests.post(f"{BASE_URL}/plans", json={"name": "Bad Plan", "duration_days": 0, "price": -5.0})
    assert r_bad.status_code == 400
    print("✅ Invalid plan rejected with 400 Bad Request")

    # List Plans
    r_list = requests.get(f"{BASE_URL}/plans")
    assert r_list.status_code == 200
    assert len(r_list.json()) >= 2
    print(f"✅ Listed {len(r_list.json())} plans")

    # 2. Trainers (Stretch Feature 1)
    test_feature("2. Stretch: Trainers (Create, Assign, Show Roster)")
    r_t = requests.post(f"{BASE_URL}/trainers", json={"name": "Jordan Hayes", "phone": "555-8888", "specialty": "Functional Fitness"})
    assert r_t.status_code == 201
    trainer = r_t.json()
    t_id = trainer["id"]
    print("✅ Created Trainer:", trainer)

    # 3. Register Members
    test_feature("3. Register Members & Payment Logging")
    today = date(2026, 11, 5)
    today_str = today.isoformat()

    # Active Member
    r_m1 = requests.post(
        f"{BASE_URL}/members",
        json={
            "name": "Bruce Banner",
            "phone": "555-0111",
            "plan_id": p1["id"],
            "start_date": (today - timedelta(days=10)).isoformat(),
            "trainer_id": t_id,
        },
    )
    assert r_m1.status_code == 201
    m_active = r_m1.json()
    # Expected end_date = (today - 10) + 30 - 1 = today + 19
    expected_end = (today - timedelta(days=10) + timedelta(days=29)).isoformat()
    assert m_active["end_date"] == expected_end
    print(f"✅ Member 1 Registered (Active). End date: {m_active['end_date']}, Trainer: {m_active['trainer_name']}")

    # Expiring Soon Member (expires in 4 days)
    # Start date = today + 4 - 30 + 1 = today - 25 days
    r_m2 = requests.post(
        f"{BASE_URL}/members",
        json={
            "name": "Tony Stark",
            "phone": "555-0222",
            "plan_id": p1["id"],
            "start_date": (today - timedelta(days=25)).isoformat(),
        },
    )
    assert r_m2.status_code == 201
    m_expiring = r_m2.json()
    print(f"✅ Member 2 Registered (Expiring Soon). End date: {m_expiring['end_date']}")

    # Expired Member (expired 5 days ago)
    r_m3 = requests.post(
        f"{BASE_URL}/members",
        json={
            "name": "Steve Rogers",
            "phone": "555-0333",
            "plan_id": p1["id"],
            "start_date": (today - timedelta(days=40)).isoformat(),
        },
    )
    assert r_m3.status_code == 201
    m_expired = r_m3.json()
    print(f"✅ Member 3 Registered (Expired). End date: {m_expired['end_date']}")

    # Future Member (starts in 3 days)
    r_m4 = requests.post(
        f"{BASE_URL}/members",
        json={
            "name": "Natasha Romanoff",
            "phone": "555-0444",
            "plan_id": p1["id"],
            "start_date": (today + timedelta(days=3)).isoformat(),
        },
    )
    assert r_m4.status_code == 201
    m_future = r_m4.json()
    print(f"✅ Member 4 Registered (Future). Start date: {m_future['start_date']}")

    # Check trainer's roster
    r_roster = requests.get(f"{BASE_URL}/trainers/{t_id}/members")
    assert r_roster.status_code == 200
    roster = r_roster.json()
    assert len(roster) >= 1
    assert any(m["id"] == m_active["id"] for m in roster)
    print(f"✅ Trainer roster verified: {len(roster)} member(s) assigned")

    # 4. Expiring Soon (7-Day Window)
    test_feature("4. Expiring Soon: 7-Day Window Evaluation")
    r_exp = requests.get(f"{BASE_URL}/members/expiring-soon", params={"today": today_str})
    assert r_exp.status_code == 200
    exp_list = r_exp.json()
    assert any(m["id"] == m_expiring["id"] for m in exp_list)
    assert not any(m["id"] == m_expired["id"] for m in exp_list)
    for item in exp_list:
        assert 0 <= item["days_left"] <= 7
    print(f"✅ Expiring soon verified: {len(exp_list)} member(s) found in 7-day window")

    # 5. Daily Check-Ins & Access Control
    test_feature("5. Daily Check-Ins: Granted & Blocked Scenarios")

    # 5.1 Granted: Active Member
    r_c1 = requests.post(f"{BASE_URL}/check-ins", json={"member_id": m_active["id"], "check_in_date": today_str})
    assert r_c1.status_code == 201
    c1 = r_c1.json()
    assert c1["allowed"] is True
    assert c1["reason"] is None
    print(f"✅ Active member check-in GRANTED: {c1['member_name']}")

    # 5.2 Denied: Duplicate check-in on the same day
    r_c_dup = requests.post(f"{BASE_URL}/check-ins", json={"member_id": m_active["id"], "check_in_date": today_str})
    assert r_c_dup.status_code == 201
    c_dup = r_c_dup.json()
    assert c_dup["allowed"] is False
    assert "Duplicate" in c_dup["reason"]
    print(f"✅ Duplicate check-in BLOCKED: {c_dup['reason']}")

    # 5.3 Denied: Expired Member
    r_c_exp = requests.post(f"{BASE_URL}/check-ins", json={"member_id": m_expired["id"], "check_in_date": today_str})
    assert r_c_exp.status_code == 201
    c_exp = r_c_exp.json()
    assert c_exp["allowed"] is False
    assert "expired" in c_exp["reason"].lower()
    print(f"✅ Expired member check-in BLOCKED: {c_exp['reason']}")

    # 5.4 Denied: Future Member (not started yet)
    r_c_fut = requests.post(f"{BASE_URL}/check-ins", json={"member_id": m_future["id"], "check_in_date": today_str})
    assert r_c_fut.status_code == 201
    c_fut = r_c_fut.json()
    assert c_fut["allowed"] is False
    assert "not started yet" in c_fut["reason"].lower()
    print(f"✅ Future member check-in BLOCKED: {c_fut['reason']}")

    # 5.5 Denied: Unknown Member
    r_c_unk = requests.post(f"{BASE_URL}/check-ins", json={"member_id": 99999, "check_in_date": today_str})
    assert r_c_unk.status_code == 201
    c_unk = r_c_unk.json()
    assert c_unk["allowed"] is False
    assert "Unknown member" in c_unk["reason"]
    print(f"✅ Unknown member check-in BLOCKED & LOGGED: {c_unk['reason']}")

    # 6. Freeze (Stretch Feature 2)
    test_feature("6. Stretch: Freeze Membership (Cap, Extension, Block Check-In)")
    # Freeze Tony Stark for 7 days
    r_frz = requests.post(
        f"{BASE_URL}/members/{m_expiring['id']}/freeze",
        json={"days": 7, "start_date": today_str, "reason": "Business Trip"},
        params={"today": today_str},
    )
    assert r_frz.status_code == 201
    frz_data = r_frz.json()
    print(f"✅ Applied 7-day freeze. New end date: {frz_data['new_membership_end_date']}")

    # Check-in blocked during freeze
    r_c_frz = requests.post(f"{BASE_URL}/check-ins", json={"member_id": m_expiring["id"], "check_in_date": today_str})
    assert r_c_frz.status_code == 201
    c_frz = r_c_frz.json()
    assert c_frz["allowed"] is False
    assert "currently frozen" in c_frz["reason"].lower()
    print(f"✅ Frozen member check-in BLOCKED: {c_frz['reason']}")

    # Test Freeze Cap: Tony Stark used 7 days. Requesting 24 more days (7 + 24 = 31 > 30) should fail
    r_frz_cap = requests.post(
        f"{BASE_URL}/members/{m_expiring['id']}/freeze",
        json={"days": 24, "start_date": (today + timedelta(days=10)).isoformat()},
        params={"today": today_str},
    )
    assert r_frz_cap.status_code == 400
    assert "cap of 30 days exceeded" in r_frz_cap.json()["detail"]
    print(f"✅ Freeze lifetime cap enforced (30-day limit): {r_frz_cap.json()['detail']}")

    # Test Freeze Expired Member should fail
    r_frz_exp = requests.post(
        f"{BASE_URL}/members/{m_expired['id']}/freeze",
        json={"days": 5},
        params={"today": today_str},
    )
    assert r_frz_exp.status_code == 400
    assert "expired" in r_frz_exp.json()["detail"].lower()
    print(f"✅ Freezing expired membership rejected: {r_frz_exp.json()['detail']}")

    # 7. Renewal (Stretch Feature 3)
    test_feature("7. Stretch: Renewal (Active & Expired Extension, Payment Logging)")
    # Renew active member (Tony Stark)
    r_ren_active = requests.post(
        f"{BASE_URL}/members/{m_expiring['id']}/renew",
        json={"plan_id": p1["id"], "renewal_date": today_str},
        params={"today": today_str},
    )
    assert r_ren_active.status_code == 201
    ren_act = r_ren_active.json()
    print(f"✅ Active renewal succeeded. Extended to: {ren_act['new_end_date']}, Paid: ${ren_act['amount_paid']}")

    # Renew expired member (Steve Rogers)
    r_ren_exp = requests.post(
        f"{BASE_URL}/members/{m_expired['id']}/renew",
        json={"plan_id": p1["id"], "renewal_date": today_str},
        params={"today": today_str},
    )
    assert r_ren_exp.status_code == 201
    ren_exp = r_ren_exp.json()
    # Expired member renewal extends from today: today + 30 - 1
    expected_ren_end = (today + timedelta(days=29)).isoformat()
    assert ren_exp["new_end_date"] == expected_ren_end
    print(f"✅ Expired renewal succeeded. Extended from today to: {ren_exp['new_end_date']}, Paid: ${ren_exp['amount_paid']}")

    # 8. Dashboard
    test_feature("8. Dashboard Metrics & Revenue")
    r_dash = requests.get(
        f"{BASE_URL}/dashboard",
        params={"year": today.year, "month": today.month, "today": today_str},
    )
    assert r_dash.status_code == 200
    dash = r_dash.json()
    print("✅ Dashboard stats:", dash)
    assert dash["monthly_revenue"] > 0
    assert dash["total_members"] >= 4
    assert dash["today_checkins_total"] >= 5
    assert dash["today_checkins_allowed"] >= 1
    assert dash["today_checkins_denied"] >= 4

    print("\n" + "=" * 60)
    print("🎉 ALL END-TO-END VERIFICATION CHECKS PASSED PERFECTLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()
