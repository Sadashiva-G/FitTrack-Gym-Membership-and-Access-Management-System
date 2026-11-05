# FitTrack: Gym Membership and Access Management System

FitTrack is a gym membership and facility access management system built using **100% pure Python** (no HTML, CSS, JavaScript, React, or Node files).

---

## 🛠️ Tech Stack

- **Backend:** FastAPI + SQLite (`stdlib sqlite3`) + Pydantic v2
- **Frontend:** Streamlit (communicates with the backend via `requests`)
- **Language & Runtime:** Python 3.10+
- **Testing:** pytest
- **Dependencies:** `fastapi`, `uvicorn`, `streamlit`, `requests`, `pytest`, `pandas`

---

## 📁 Project Structure

```
FitTrack1/
├── backend/
│   ├── __init__.py
│   ├── database.py       # SQLite connection, schema initialization & indexes
│   ├── models.py         # Pydantic schemas and validation
│   ├── services.py       # Business domain logic, calculations, and date rules
│   └── main.py           # FastAPI REST API endpoints, CORS, exception handlers
├── frontend/
│   ├── __init__.py
│   └── app.py            # Streamlit multi-page dashboard UI
├── tests/
│   ├── __init__.py
│   ├── test_services.py  # Unit tests for date math, edge cases, cap & revenue
│   └── test_api.py       # API integration tests & HTTP status code tests
├── requirements.txt      # Pinned dependency versions
├── run.py                # Unified launcher for backend and frontend
└── README.md             # Documentation and setup instructions
```

---

## 🚀 Setup & Run Instructions

### 1. Prerequisites
Ensure Python 3.10 or higher is installed on your system.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the App (One Command)
Launch both the FastAPI backend and Streamlit frontend together:
```bash
python run.py
```

Once running, access the services:
- **Streamlit Web App:** [http://127.0.0.1:8501](http://127.0.0.1:8501)
- **Interactive API Docs (Swagger):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **API Health Endpoint:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 4. Running Backend and Frontend Separately (Optional)

**Terminal 1 (Backend):**
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 (Frontend):**
```bash
python -m streamlit run frontend/app.py --server.port 8501
```

---

## 🧪 Running Tests

FitTrack includes a pytest suite covering all business logic, date calculations, edge cases, and API status codes:

```bash
pytest -v
```

### Test Coverage Highlights:
- **Expiry Date Math:** Inclusive end date calculation (`start_date + duration_days - 1`).
- **7-Day Expiring Window Edge Cases:** Exact evaluation for `today`, `today + 7 days`, `today + 8 days` (excluded), and `today - 1 day` (expired).
- **Check-In Access Control:** Blocks and logs expired, not started yet, frozen, duplicate, and unknown member attempts.
- **Freeze Rules & Lifetime Cap:** Enforces 1–30 days per freeze, 30 days total lifetime cap per membership, rejects expired memberships, and extends end dates.
- **Renewal Logic:** Correctly extends active memberships from `end_date` and expired memberships from `renewal_date`, recording payments for revenue accuracy.
- **Monthly Revenue Across Month Boundaries:** Isolates payments (e.g., Jan 31 vs. Feb 1) to their respective months.
- **REST Status Codes:** Verifies `201 Created`, `400 Bad Request`, `404 Not Found`, `409 Conflict`, and `200 OK`.

---

## ✨ Features Overview

### 1. Membership Plans
- Create and list plans with unique names, duration in days (`> 0`), and price (`>= 0`).
- Enforces uniqueness with `409 Conflict` on duplicates.

### 2. Member Registration & Payment Logging
- Register members with name, phone, plan, start date, and optional personal trainer.
- Automatically calculates `end_date = start_date + duration_days - 1` (inclusive).
- Immediately logs an initial payment equal to the plan price on the start date.

### 3. Expiring Soon (7-Day Window)
- Lists members whose access expires between `today` and `today + 7 days` (inclusive).
- Sorted by expiration date ascending, showing days left and offering one-click renewal.

### 4. Daily Check-In & Facility Access Control
- Validates membership status on entry.
- **ACCESS GRANTED (Green):** Active member checked in for the day.
- **ACCESS BLOCKED (Red):** Blocks and logs the exact reason if:
  - Member is unknown (ID not found)
  - Membership has not started yet
  - Membership has expired
  - Membership is currently frozen
  - Duplicate check-in attempted on the same calendar day

### 5. Performance Dashboard
- **Monthly Revenue:** Filter by year and month to inspect fee collections.
- **Active Members:** Count of members currently valid and not frozen.
- **Total Members:** Overall enrolled members.
- **Today's Check-Ins:** Real-time counter of total attempts, granted accesses, and blocked attempts.

### 6. Personal Trainers (Stretch Feature)
- Register trainers with specialty and contact info.
- Assign trainers to members.
- View roster of members assigned to each trainer.

### 7. Membership Freeze (Stretch Feature)
- Freeze membership between 1 and 30 days.
- Strict lifetime cap of **30 cumulative days** per membership.
- Extends member `end_date` by frozen days, blocks check-ins during the freeze, and rejects expired memberships.

### 8. Membership Renewal (Stretch Feature)
- Seamless renewal extending from current `end_date` if active, or from today if expired.
- Automatically records a new payment in the payments ledger for revenue auditing.

### 9. Quick Demo Data Seeding
- One-click "Seed Demo Data" button in Streamlit or `POST /seed` API to populate sample plans, trainers, active members, expiring members, frozen members, and check-in logs.

---

## 📡 REST API Reference

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `GET` | `/health` | Service health check | `200 OK` |
| `POST` | `/seed` | Seed demo data | `200 OK` |
| `POST` | `/plans` | Create a membership plan | `201 Created` / `409 Conflict` |
| `GET` | `/plans` | List all plans | `200 OK` |
| `GET` | `/plans/{id}` | Get plan by ID | `200 OK` / `404 Not Found` |
| `POST` | `/trainers` | Create a trainer | `201 Created` |
| `GET` | `/trainers` | List trainers with member counts | `200 OK` |
| `GET` | `/trainers/{id}/members` | List members assigned to trainer | `200 OK` |
| `POST` | `/members` | Register member & record payment | `201 Created` |
| `GET` | `/members` | List all members with computed status | `200 OK` |
| `GET` | `/members/expiring-soon` | List members expiring in 7 days | `200 OK` |
| `GET` | `/members/{id}` | Get member by ID | `200 OK` / `404 Not Found` |
| `PUT` | `/members/{id}/trainer` | Assign / unassign trainer | `200 OK` |
| `POST` | `/members/{id}/freeze` | Freeze membership (1-30 days) | `201 Created` / `400 Bad Request` |
| `POST` | `/members/{id}/renew` | Renew membership & log payment | `201 Created` |
| `POST` | `/check-ins` | Evaluate and log check-in attempt | `201 Created` |
| `GET` | `/check-ins` | Check-in activity history | `200 OK` |
| `GET` | `/dashboard` | Monthly revenue and active stats | `200 OK` |
