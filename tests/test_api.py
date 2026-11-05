"""API endpoint and status code tests for FitTrack.

Uses standard requests library and uvicorn server in a background thread
to avoid external dependencies (e.g. httpx).
"""

import os
import socket
import tempfile
import threading
import time
from typing import Any, Dict, Optional
import pytest
import requests
import uvicorn

from backend.database import init_db
from backend.main import app


def get_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ApiClient:
    """Helper client using standard requests library."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def get(self, endpoint: str, **kwargs):
        return self.session.get(f"{self.base_url}{endpoint}", **kwargs)

    def post(self, endpoint: str, **kwargs):
        return self.session.post(f"{self.base_url}{endpoint}", **kwargs)

    def put(self, endpoint: str, **kwargs):
        return self.session.put(f"{self.base_url}{endpoint}", **kwargs)

    def delete(self, endpoint: str, **kwargs):
        return self.session.delete(f"{self.base_url}{endpoint}", **kwargs)


@pytest.fixture(scope="session")
def live_server():
    """Start uvicorn server on a background thread for the duration of the test session."""
    port = get_free_port()
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    # Wait for server to become responsive
    deadline = time.time() + 10
    started = False
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/health", timeout=1)
            if r.status_code == 200:
                started = True
                break
        except Exception:
            time.sleep(0.1)

    if not started:
        raise RuntimeError(f"Could not connect to live test server at {base_url}")

    yield base_url
    server.should_exit = True
    thread.join(timeout=2)


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    """Provide an isolated temporary database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    monkeypatch.setenv("FITTRACK_DB_PATH", db_path)
    init_db(db_path)
    yield db_path

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except PermissionError:
            pass


@pytest.fixture
def client(live_server):
    """Return an ApiClient pointing to the live server."""
    return ApiClient(live_server)


# ---------------------------------------------------------------------------
# Plans API & Status Codes (201, 400, 404, 409, 200)
# ---------------------------------------------------------------------------

def test_api_plans_crud_and_status_codes(client):
    """Test /plans status codes: 201 created, 409 conflict, 400 validation, 404 not found, 200 ok."""
    # 1. 201 Created
    res = client.post("/plans", json={"name": "Monthly Pass", "duration_days": 30, "price": 45.0})
    assert res.status_code == 201
    data = res.json()
    assert data["id"] == 1
    assert data["name"] == "Monthly Pass"
    assert data["duration_days"] == 30
    assert data["price"] == 45.0

    # 2. 409 Conflict: duplicate name
    res_dup = client.post("/plans", json={"name": "Monthly Pass", "duration_days": 60, "price": 80.0})
    assert res_dup.status_code == 409
    assert "already exists" in res_dup.json()["detail"]

    # 3. 400 Bad Request: validation error (invalid duration <= 0)
    res_bad_dur = client.post("/plans", json={"name": "Bad Duration", "duration_days": 0, "price": 50.0})
    assert res_bad_dur.status_code == 400

    # 4. 400 Bad Request: negative price
    res_bad_price = client.post("/plans", json={"name": "Negative Price", "duration_days": 30, "price": -5.0})
    assert res_bad_price.status_code == 400

    # 5. 200 OK: list plans
    res_list = client.get("/plans")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 6. 200 OK: get plan by ID
    res_get = client.get("/plans/1")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == 1

    # 7. 404 Not Found: get non-existent plan
    res_not_found = client.get("/plans/999")
    assert res_not_found.status_code == 404
    assert "not found" in res_not_found.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Trainers API
# ---------------------------------------------------------------------------

def test_api_trainers(client):
    """Test /trainers endpoints and status codes."""
    # Create trainer: 201
    res = client.post("/trainers", json={"name": "Coach Marcus", "phone": "555-1234", "specialty": "Boxing"})
    assert res.status_code == 201
    t_id = res.json()["id"]

    # List trainers: 200
    res_list = client.get("/trainers")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # Get trainer: 200
    res_get = client.get(f"/trainers/{t_id}")
    assert res_get.status_code == 200

    # Trainer not found: 404
    res_nf = client.get("/trainers/999")
    assert res_nf.status_code == 404


# ---------------------------------------------------------------------------
# Members Registration API
# ---------------------------------------------------------------------------

def test_api_member_registration(client):
    """Test /members registration, end_date calculation, and status codes."""
    # Seed a plan first
    p_res = client.post("/plans", json={"name": "Standard", "duration_days": 30, "price": 50.0})
    plan_id = p_res.json()["id"]

    # 1. 201 Created
    m_res = client.post(
        "/members",
        json={
            "name": "Jane Miller",
            "phone": "555-4321",
            "plan_id": plan_id,
            "start_date": "2026-03-01",
        },
    )
    assert m_res.status_code == 201
    m_data = m_res.json()
    assert m_data["id"] == 1
    assert m_data["start_date"] == "2026-03-01"
    # 2026-03-01 + 30 days - 1 = 2026-03-30
    assert m_data["end_date"] == "2026-03-30"

    # 2. 400 Bad Request: invalid date format
    bad_date_res = client.post(
        "/members",
        json={"name": "Bad Date", "phone": "555-0000", "plan_id": plan_id, "start_date": "03-01-2026"},
    )
    assert bad_date_res.status_code == 400

    # 3. 404 Not Found: non-existent plan
    bad_plan_res = client.post(
        "/members",
        json={"name": "Bad Plan", "phone": "555-0000", "plan_id": 9999, "start_date": "2026-03-01"},
    )
    assert bad_plan_res.status_code == 404


# ---------------------------------------------------------------------------
# Expiring Soon API
# ---------------------------------------------------------------------------

def test_api_expiring_soon(client):
    """Test /members/expiring-soon 7-day window via API."""
    p_res = client.post("/plans", json={"name": "One Day", "duration_days": 1, "price": 10.0})
    p_id = p_res.json()["id"]

    # Member 1: Expires today (2026-05-10)
    client.post("/members", json={"name": "Exp Today", "phone": "111", "plan_id": p_id, "start_date": "2026-05-10"})
    # Member 2: Expires in 7 days (2026-05-17)
    client.post("/members", json={"name": "Exp Day 7", "phone": "222", "plan_id": p_id, "start_date": "2026-05-17"})
    # Member 3: Expires in 8 days (2026-05-18) -> outside window
    client.post("/members", json={"name": "Exp Day 8", "phone": "333", "plan_id": p_id, "start_date": "2026-05-18"})

    res = client.get("/members/expiring-soon", params={"today": "2026-05-10"})
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    assert items[0]["days_left"] == 0
    assert items[1]["days_left"] == 7


# ---------------------------------------------------------------------------
# Check-Ins API
# ---------------------------------------------------------------------------

def test_api_check_ins(client):
    """Test /check-ins API behavior."""
    p_res = client.post("/plans", json={"name": "Pass", "duration_days": 10, "price": 20.0})
    p_id = p_res.json()["id"]

    m_res = client.post(
        "/members",
        json={"name": "CheckIn Guy", "phone": "555", "plan_id": p_id, "start_date": "2026-07-01"},
    )
    mid = m_res.json()["id"]

    # 1. Successful check-in: 201 Created with allowed=True
    chk1 = client.post("/check-ins", json={"member_id": mid, "check_in_date": "2026-07-01"})
    assert chk1.status_code == 201
    assert chk1.json()["allowed"] is True

    # 2. Duplicate check-in on same day: 201 Created with allowed=False
    chk2 = client.post("/check-ins", json={"member_id": mid, "check_in_date": "2026-07-01"})
    assert chk2.status_code == 201
    assert chk2.json()["allowed"] is False
    assert "Duplicate" in chk2.json()["reason"]

    # 3. Unknown member check-in: 201 Created with allowed=False
    chk_unk = client.post("/check-ins", json={"member_id": 8888, "check_in_date": "2026-07-01"})
    assert chk_unk.status_code == 201
    assert chk_unk.json()["allowed"] is False
    assert "Unknown member" in chk_unk.json()["reason"]

    # 4. Check-in history: 200 OK
    res_list = client.get("/check-ins")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 3


# ---------------------------------------------------------------------------
# Freeze & Renewal API
# ---------------------------------------------------------------------------

def test_api_freeze_and_renewal(client):
    """Test /members/{id}/freeze and /members/{id}/renew endpoints."""
    p_res = client.post("/plans", json={"name": "Pass 30", "duration_days": 30, "price": 40.0})
    pid = p_res.json()["id"]

    m_res = client.post(
        "/members",
        json={"name": "Freeze Renew Guy", "phone": "555", "plan_id": pid, "start_date": "2026-08-01"},
    )
    mid = m_res.json()["id"]
    # End date: 2026-08-30

    # 1. Freeze member for 10 days: 201 Created
    frz_res = client.post(
        f"/members/{mid}/freeze",
        json={"days": 10, "start_date": "2026-08-05", "reason": "Holiday"},
        params={"today": "2026-08-05"},
    )
    assert frz_res.status_code == 201
    assert frz_res.json()["days"] == 10
    # 2026-08-30 + 10 days = 2026-09-09
    assert frz_res.json()["new_membership_end_date"] == "2026-09-09"

    # 2. Over limit freeze: 400 Bad Request (> 30 days cap)
    frz_bad = client.post(
        f"/members/{mid}/freeze",
        json={"days": 25, "start_date": "2026-08-20"},
        params={"today": "2026-08-20"},
    )
    assert frz_bad.status_code == 400
    assert "cap of 30 days exceeded" in frz_bad.json()["detail"]

    # 3. Renew member: 201 Created
    ren_res = client.post(
        f"/members/{mid}/renew",
        json={"plan_id": pid, "renewal_date": "2026-08-15"},
        params={"today": "2026-08-15"},
    )
    assert ren_res.status_code == 201
    # Active renewal extends from old end_date 2026-09-09 + 30 = 2026-10-09
    assert ren_res.json()["new_end_date"] == "2026-10-09"


# ---------------------------------------------------------------------------
# Dashboard API & Demo Seed
# ---------------------------------------------------------------------------

def test_api_dashboard_and_seed(client):
    """Test /dashboard and /seed endpoints."""
    # Seed demo data: 200 OK
    seed_res = client.post("/seed", params={"today": "2026-11-05"})
    assert seed_res.status_code == 200
    assert seed_res.json()["members_count"] >= 5

    # Dashboard stats: 200 OK
    dash_res = client.get("/dashboard", params={"year": 2026, "month": 11, "today": "2026-11-05"})
    assert dash_res.status_code == 200
    data = dash_res.json()
    assert data["year"] == 2026
    assert data["month"] == 11
    assert data["total_members"] >= 5
    assert data["active_members"] >= 1
    assert "monthly_revenue" in data
    assert "today_checkins_total" in data
