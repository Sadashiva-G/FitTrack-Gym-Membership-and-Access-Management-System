"""Unit tests for FitTrack business logic and services."""

from datetime import date, timedelta
import sqlite3
import pytest

from backend.database import init_db
from backend.services import (
    ConflictError,
    FitTrackError,
    NotFoundError,
    ValidationError,
    calculate_end_date,
    create_plan,
    create_trainer,
    freeze_membership,
    get_dashboard_stats,
    get_expiring_soon_members,
    get_member,
    get_plan,
    get_trainer,
    get_trainer_members,
    list_check_ins,
    list_members,
    list_plans,
    list_trainers,
    record_check_in,
    register_member,
    renew_membership,
)


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database connection with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    # Apply tables
    conn.executescript(
        """
        CREATE TABLE plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            duration_days INTEGER NOT NULL CHECK(duration_days > 0),
            price REAL NOT NULL CHECK(price >= 0),
            created_at TEXT NOT NULL
        );
        CREATE TABLE trainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            specialty TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            plan_id INTEGER NOT NULL REFERENCES plans(id),
            trainer_id INTEGER REFERENCES trainers(id) ON DELETE SET NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            amount REAL NOT NULL CHECK(amount >= 0),
            payment_date TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE freezes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            days INTEGER NOT NULL CHECK(days > 0),
            reason TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE check_ins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER REFERENCES members(id) ON DELETE SET NULL,
            attempted_member_id INTEGER NOT NULL,
            check_in_date TEXT NOT NULL,
            check_in_time TEXT NOT NULL,
            allowed INTEGER NOT NULL CHECK(allowed IN (0, 1)),
            reason TEXT
        );
        """
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Test 1: Expiry Date Math
# ---------------------------------------------------------------------------

def test_calculate_end_date_math():
    """Verify inclusive end date calculation: start + duration - 1."""
    # 1 day plan: start and end on the same day
    assert calculate_end_date(date(2026, 1, 1), 1) == date(2026, 1, 1)

    # 30 days plan: 2026-01-01 to 2026-01-30 (30 days inclusive)
    assert calculate_end_date(date(2026, 1, 1), 30) == date(2026, 1, 30)

    # 7 days plan: 2026-02-01 to 2026-02-07
    assert calculate_end_date(date(2026, 2, 1), 7) == date(2026, 2, 7)

    # 365 days plan
    assert calculate_end_date(date(2026, 1, 1), 365) == date(2026, 12, 31)

    # Invalid duration must raise ValidationError
    with pytest.raises(ValidationError):
        calculate_end_date(date(2026, 1, 1), 0)
    with pytest.raises(ValidationError):
        calculate_end_date(date(2026, 1, 1), -5)


# ---------------------------------------------------------------------------
# Test 2: Plans Management
# ---------------------------------------------------------------------------

def test_plan_creation_and_uniqueness(db_conn):
    """Verify creating plans, validation, and uniqueness."""
    p1 = create_plan(db_conn, "Gold 30", 30, 49.99)
    assert p1["id"] == 1
    assert p1["name"] == "Gold 30"
    assert p1["duration_days"] == 30
    assert p1["price"] == 49.99

    # Duplicate name should raise ConflictError
    with pytest.raises(ConflictError):
        create_plan(db_conn, "Gold 30", 60, 89.99)
    with pytest.raises(ConflictError):
        create_plan(db_conn, "gold 30", 60, 89.99)

    # Validation errors
    with pytest.raises(ValidationError):
        create_plan(db_conn, "", 30, 49.99)
    with pytest.raises(ValidationError):
        create_plan(db_conn, "Bad Days", 0, 49.99)
    with pytest.raises(ValidationError):
        create_plan(db_conn, "Bad Price", 30, -10.0)


# ---------------------------------------------------------------------------
# Test 3: Member Registration & Payment Logging
# ---------------------------------------------------------------------------

def test_member_registration_and_payment(db_conn):
    """Verify registration calculates end_date and logs initial payment."""
    p = create_plan(db_conn, "Standard Monthly", 30, 50.0)
    t = create_trainer(db_conn, "Coach Bob", "555-1111", "Strength")

    start_d = date(2026, 5, 1)
    member = register_member(
        db_conn,
        name="Alice Smith",
        phone="555-9999",
        plan_id=p["id"],
        start_date=start_d,
        trainer_id=t["id"],
    )

    assert member["name"] == "Alice Smith"
    assert member["start_date"] == "2026-05-01"
    # 2026-05-01 + 30 days - 1 = 2026-05-30
    assert member["end_date"] == "2026-05-30"
    assert member["trainer_id"] == t["id"]
    assert member["trainer_name"] == "Coach Bob"

    # Verify payment recorded
    cur = db_conn.execute("SELECT * FROM payments WHERE member_id = ?", (member["id"],))
    payment = cur.fetchone()
    assert payment is not None
    assert payment["amount"] == 50.0
    assert payment["payment_date"] == "2026-05-01"
    assert payment["payment_type"] == "registration"


# ---------------------------------------------------------------------------
# Test 4: Expiring Soon 7-Day Window Edge Cases
# ---------------------------------------------------------------------------

def test_expiring_soon_7_day_window_edge_cases(db_conn):
    """Verify the 7-day expiring window edge cases:

    Window is [today, today + 7 days] inclusive.
    - end_date = today: INCLUDED (days_left = 0)
    - end_date = today + 7: INCLUDED (days_left = 7)
    - end_date = today + 8: EXCLUDED (not expiring soon enough)
    - end_date = today - 1: EXCLUDED (already expired)
    """
    plan = create_plan(db_conn, "Daily Pass", 1, 10.0)
    eval_today = date(2026, 6, 15)

    # 1. Expires TODAY (2026-06-15) -> should be included, days_left = 0
    m_today = register_member(db_conn, "Expires Today", "555-01", plan["id"], start_date=eval_today)

    # 2. Expires on Day 7 (2026-06-22) -> should be included, days_left = 7
    m_day7 = register_member(db_conn, "Expires Day 7", "555-07", plan["id"], start_date=eval_today + timedelta(days=7))

    # 3. Expires on Day 8 (2026-06-23) -> should be EXCLUDED
    register_member(db_conn, "Expires Day 8", "555-08", plan["id"], start_date=eval_today + timedelta(days=8))

    # 4. Expired yesterday (2026-06-14) -> should be EXCLUDED
    register_member(db_conn, "Expired Yesterday", "555-00", plan["id"], start_date=eval_today - timedelta(days=1))

    # 5. Expires on Day 3 (2026-06-18) -> should be included, days_left = 3
    m_day3 = register_member(db_conn, "Expires Day 3", "555-03", plan["id"], start_date=eval_today + timedelta(days=3))

    expiring = get_expiring_soon_members(db_conn, today=eval_today)
    assert len(expiring) == 3

    # Must be sorted by end_date ASC
    assert expiring[0]["id"] == m_today["id"]
    assert expiring[0]["days_left"] == 0

    assert expiring[1]["id"] == m_day3["id"]
    assert expiring[1]["days_left"] == 3

    assert expiring[2]["id"] == m_day7["id"]
    assert expiring[2]["days_left"] == 7


# ---------------------------------------------------------------------------
# Test 5: Check-In Rules (Expired, Frozen, Duplicate, Unknown, Valid)
# ---------------------------------------------------------------------------

def test_check_in_valid_and_duplicate(db_conn):
    """Test valid check-in and blocking duplicate allowed check-in on same day."""
    plan = create_plan(db_conn, "Monthly", 30, 40.0)
    today = date(2026, 4, 10)
    member = register_member(db_conn, "John Active", "555-1234", plan["id"], start_date=today)

    # First check-in: Allowed
    chk1 = record_check_in(db_conn, member["id"], check_in_date=today)
    assert chk1["allowed"] is True
    assert chk1["reason"] is None
    assert chk1["member_name"] == "John Active"

    # Second check-in on the SAME day: Blocked (Duplicate)
    chk2 = record_check_in(db_conn, member["id"], check_in_date=today)
    assert chk2["allowed"] is False
    assert "Duplicate check-in" in chk2["reason"]

    # Check-in on NEXT day: Allowed
    next_day = today + timedelta(days=1)
    chk3 = record_check_in(db_conn, member["id"], check_in_date=next_day)
    assert chk3["allowed"] is True


def test_check_in_unknown_member(db_conn):
    """Check-in for unknown member ID is blocked and logged."""
    chk = record_check_in(db_conn, member_id=9999, check_in_date=date(2026, 4, 10))
    assert chk["allowed"] is False
    assert "Unknown member" in chk["reason"]
    assert chk["attempted_member_id"] == 9999
    assert chk["member_id"] is None

    # Verify check_ins table has the record
    recent = list_check_ins(db_conn)
    assert len(recent) == 1
    assert recent[0]["allowed"] is False
    assert recent[0]["attempted_member_id"] == 9999


def test_check_in_not_started_and_expired(db_conn):
    """Check-in blocked when membership has not started or has expired."""
    plan = create_plan(db_conn, "Ten Days", 10, 25.0)
    start_d = date(2026, 5, 10)
    member = register_member(db_conn, "Tim Traveler", "555-7777", plan["id"], start_date=start_d)
    # End date is 2026-05-19

    # 1. Not started yet (check-in on 2026-05-09)
    chk_early = record_check_in(db_conn, member["id"], check_in_date=date(2026, 5, 9))
    assert chk_early["allowed"] is False
    assert "not started yet" in chk_early["reason"]

    # 2. Valid on end_date (2026-05-19)
    chk_valid = record_check_in(db_conn, member["id"], check_in_date=date(2026, 5, 19))
    assert chk_valid["allowed"] is True

    # 3. Expired on day after end_date (2026-05-20)
    chk_expired = record_check_in(db_conn, member["id"], check_in_date=date(2026, 5, 20))
    assert chk_expired["allowed"] is False
    assert "expired" in chk_expired["reason"]


def test_check_in_during_freeze(db_conn):
    """Check-in blocked during an active freeze period."""
    plan = create_plan(db_conn, "Monthly", 30, 40.0)
    start_d = date(2026, 6, 1)
    member = register_member(db_conn, "Frank Freezy", "555-8888", plan["id"], start_date=start_d)
    # Member end_date originally 2026-06-30

    # Freeze for 7 days starting 2026-06-10 (ends 2026-06-16)
    freeze_membership(
        db_conn,
        member_id=member["id"],
        days=7,
        start_date=date(2026, 6, 10),
        reason="Vacation",
        today=date(2026, 6, 10),
    )

    # Check-in before freeze: allowed
    chk_before = record_check_in(db_conn, member["id"], check_in_date=date(2026, 6, 9))
    assert chk_before["allowed"] is True

    # Check-in during freeze: blocked
    chk_frozen = record_check_in(db_conn, member["id"], check_in_date=date(2026, 6, 12))
    assert chk_frozen["allowed"] is False
    assert "currently frozen" in chk_frozen["reason"]

    # Check-in after freeze: allowed
    chk_after = record_check_in(db_conn, member["id"], check_in_date=date(2026, 6, 17))
    assert chk_after["allowed"] is True


# ---------------------------------------------------------------------------
# Test 6: Freeze Lifetime Cap (30 Days) and Expired Rejection
# ---------------------------------------------------------------------------

def test_freeze_cap_and_expired_membership(db_conn):
    """Verify freeze cap of 30 days total lifetime and rejection of expired memberships."""
    plan = create_plan(db_conn, "Standard 60", 60, 80.0)
    start_d = date(2026, 1, 1)
    member = register_member(db_conn, "Sara Freeze", "555-3210", plan["id"], start_date=start_d)
    # End date: 2026-03-01

    # First freeze: 15 days -> total used = 15
    f1 = freeze_membership(db_conn, member["id"], days=15, start_date=date(2026, 1, 10), today=date(2026, 1, 10))
    assert f1["days"] == 15
    # Original end: 2026-03-01 + 15 days = 2026-03-16
    assert f1["new_membership_end_date"] == "2026-03-16"

    # Second freeze: 15 days -> total used = 30 (Lifetime cap reached)
    f2 = freeze_membership(db_conn, member["id"], days=15, start_date=date(2026, 2, 1), today=date(2026, 2, 1))
    assert f2["days"] == 15
    assert f2["new_membership_end_date"] == "2026-03-31"

    # Third freeze: Attempting even 1 more day must be rejected
    with pytest.raises(ValidationError) as exc:
        freeze_membership(db_conn, member["id"], days=1, start_date=date(2026, 2, 20), today=date(2026, 2, 20))
    assert "cap of 30 days exceeded" in str(exc.value)

    # Freeze duration > 30 in single request rejected
    with pytest.raises(ValidationError):
        freeze_membership(db_conn, member["id"], days=31, today=date(2026, 1, 1))

    # Freeze 0 or negative days rejected
    with pytest.raises(ValidationError):
        freeze_membership(db_conn, member["id"], days=0, today=date(2026, 1, 1))

    # Reject freezing an expired membership
    m_exp = register_member(db_conn, "Old Member", "555-0000", plan["id"], start_date=date(2025, 1, 1))
    # Member ended in 2025
    with pytest.raises(ValidationError) as exc_exp:
        freeze_membership(db_conn, m_exp["id"], days=5, today=date(2026, 1, 1))
    assert "expired" in str(exc_exp.value)


# ---------------------------------------------------------------------------
# Test 7: Renewal Logic
# ---------------------------------------------------------------------------

def test_renewal_active_and_expired(db_conn):
    """Verify renewal extends from end_date if active, or from today if expired."""
    p30 = create_plan(db_conn, "Plan 30", 30, 40.0)
    p60 = create_plan(db_conn, "Plan 60", 60, 70.0)

    # 1. Member Still Active: renew extends from current end_date
    m_active = register_member(db_conn, "Active Renewer", "555-1111", p30["id"], start_date=date(2026, 5, 1))
    # m_active end_date is 2026-05-30
    ren_active = renew_membership(
        db_conn,
        member_id=m_active["id"],
        plan_id=p30["id"],
        renewal_date=date(2026, 5, 15),
        today=date(2026, 5, 15),
    )
    # 2026-05-30 + 30 days = 2026-06-29
    assert ren_active["new_end_date"] == "2026-06-29"
    assert ren_active["amount_paid"] == 40.0

    # 2. Member Expired: renew extends from renewal date (inclusive)
    m_expired = register_member(db_conn, "Expired Renewer", "555-2222", p30["id"], start_date=date(2026, 1, 1))
    # m_expired ended 2026-01-30. Renewing on 2026-05-15 with p60 (60 days)
    # Expected: 2026-05-15 + 60 days - 1 = 2026-07-13
    ren_expired = renew_membership(
        db_conn,
        member_id=m_expired["id"],
        plan_id=p60["id"],
        renewal_date=date(2026, 5, 15),
        today=date(2026, 5, 15),
    )
    assert ren_expired["new_end_date"] == "2026-07-13"
    assert ren_expired["amount_paid"] == 70.0

    # Verify both payments were recorded in payments table
    cur = db_conn.execute("SELECT * FROM payments WHERE payment_type = 'renewal'")
    renewals = cur.fetchall()
    assert len(renewals) == 2


# ---------------------------------------------------------------------------
# Test 8: Monthly Revenue Across Month Boundaries
# ---------------------------------------------------------------------------

def test_monthly_revenue_across_month_boundaries(db_conn):
    """Verify revenue calculation accurately isolates payments across month boundaries."""
    p_jan = create_plan(db_conn, "Plan Jan", 30, 100.0)
    p_feb = create_plan(db_conn, "Plan Feb", 30, 250.0)

    # Register member on Jan 31 -> payment $100 on 2026-01-31
    register_member(db_conn, "Jan Member", "555-0131", p_jan["id"], start_date=date(2026, 1, 31))

    # Register member on Feb 01 -> payment $250 on 2026-02-01
    register_member(db_conn, "Feb Member", "555-0201", p_feb["id"], start_date=date(2026, 2, 1))

    # Stats for January 2026
    stats_jan = get_dashboard_stats(db_conn, year=2026, month=1, today=date(2026, 2, 5))
    assert stats_jan["monthly_revenue"] == 100.0

    # Stats for February 2026
    stats_feb = get_dashboard_stats(db_conn, year=2026, month=2, today=date(2026, 2, 5))
    assert stats_feb["monthly_revenue"] == 250.0

    # Stats for March 2026 (0 revenue)
    stats_mar = get_dashboard_stats(db_conn, year=2026, month=3, today=date(2026, 2, 5))
    assert stats_mar["monthly_revenue"] == 0.0


# ---------------------------------------------------------------------------
# Test 9: Trainers and Assignment
# ---------------------------------------------------------------------------

def test_trainers_and_roster(db_conn):
    """Test trainer creation, member assignment, and member roster listing."""
    p = create_plan(db_conn, "Basic", 30, 30.0)
    t = create_trainer(db_conn, "Coach Anna", "555-4321", "Pilates")

    m1 = register_member(db_conn, "Client 1", "555-001", p["id"], start_date=date(2026, 1, 1), trainer_id=t["id"])
    m2 = register_member(db_conn, "Client 2", "555-002", p["id"], start_date=date(2026, 1, 1), trainer_id=t["id"])

    # Trainer member count
    trainers = list_trainers(db_conn)
    assert len(trainers) == 1
    assert trainers[0]["member_count"] == 2

    # Roster listing
    roster = get_trainer_members(db_conn, t["id"])
    assert len(roster) == 2
    names = [r["name"] for r in roster]
    assert "Client 1" in names and "Client 2" in names
