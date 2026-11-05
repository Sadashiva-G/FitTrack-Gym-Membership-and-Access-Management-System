"""Business logic, date calculations, and service functions for FitTrack.

All date calculations reside in this module and accept an optional 'today' parameter
for full testability.
"""

from datetime import date, datetime, timedelta
import sqlite3
from typing import Any, Dict, List, Optional


class FitTrackError(Exception):
    """Base error for FitTrack business domain."""
    pass


class NotFoundError(FitTrackError):
    """Raised when an entity is not found."""
    pass


class ConflictError(FitTrackError):
    """Raised when an entity conflicts with an existing one (e.g. unique constraint)."""
    pass


class ValidationError(FitTrackError):
    """Raised when business logic validation fails."""
    pass


def calculate_end_date(start_date: date, duration_days: int) -> date:
    """Calculate inclusive membership end date: start_date + duration_days - 1.

    For example, a 1-day membership starting on 2026-01-01 ends on 2026-01-01.
    A 30-day membership starting on 2026-01-01 ends on 2026-01-30.
    """
    if duration_days <= 0:
        raise ValidationError("Duration in days must be greater than 0.")
    return start_date + timedelta(days=duration_days - 1)


# ---------------------------------------------------------------------------
# Membership Plans
# ---------------------------------------------------------------------------

def create_plan(
    conn: sqlite3.Connection,
    name: str,
    duration_days: int,
    price: float,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Create a new membership plan with a unique name."""
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError("Plan name cannot be blank.")
    if duration_days <= 0:
        raise ValidationError("Duration days must be greater than 0.")
    if price < 0:
        raise ValidationError("Price cannot be negative.")

    # Check for existing plan name
    cur = conn.execute("SELECT id FROM plans WHERE LOWER(name) = LOWER(?)", (clean_name,))
    if cur.fetchone():
        raise ConflictError(f"Plan with name '{clean_name}' already exists.")

    created_at = (now or datetime.now()).isoformat()
    cur = conn.execute(
        "INSERT INTO plans (name, duration_days, price, created_at) VALUES (?, ?, ?, ?)",
        (clean_name, duration_days, float(price), created_at),
    )
    plan_id = cur.lastrowid
    return {
        "id": plan_id,
        "name": clean_name,
        "duration_days": duration_days,
        "price": float(price),
        "created_at": created_at,
    }


def list_plans(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """List all membership plans ordered by ID."""
    cur = conn.execute("SELECT id, name, duration_days, price, created_at FROM plans ORDER BY id ASC")
    return [dict(row) for row in cur.fetchall()]


def get_plan(conn: sqlite3.Connection, plan_id: int) -> Dict[str, Any]:
    """Get a membership plan by ID or raise NotFoundError."""
    cur = conn.execute(
        "SELECT id, name, duration_days, price, created_at FROM plans WHERE id = ?",
        (plan_id,),
    )
    row = cur.fetchone()
    if not row:
        raise NotFoundError(f"Plan with ID {plan_id} not found.")
    return dict(row)


# ---------------------------------------------------------------------------
# Trainers
# ---------------------------------------------------------------------------

def create_trainer(
    conn: sqlite3.Connection,
    name: str,
    phone: str,
    specialty: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Create a new trainer."""
    clean_name = name.strip()
    clean_phone = phone.strip()
    clean_specialty = specialty.strip()
    if not clean_name or not clean_phone or not clean_specialty:
        raise ValidationError("Trainer name, phone, and specialty are required.")

    created_at = (now or datetime.now()).isoformat()
    cur = conn.execute(
        "INSERT INTO trainers (name, phone, specialty, created_at) VALUES (?, ?, ?, ?)",
        (clean_name, clean_phone, clean_specialty, created_at),
    )
    trainer_id = cur.lastrowid
    return {
        "id": trainer_id,
        "name": clean_name,
        "phone": clean_phone,
        "specialty": clean_specialty,
        "created_at": created_at,
        "member_count": 0,
    }


def list_trainers(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """List all trainers with their count of assigned members."""
    query = """
        SELECT t.id, t.name, t.phone, t.specialty, t.created_at,
               COUNT(m.id) AS member_count
        FROM trainers t
        LEFT JOIN members m ON t.id = m.trainer_id
        GROUP BY t.id
        ORDER BY t.name ASC
    """
    cur = conn.execute(query)
    return [dict(row) for row in cur.fetchall()]


def get_trainer(conn: sqlite3.Connection, trainer_id: int) -> Dict[str, Any]:
    """Get trainer details by ID or raise NotFoundError."""
    query = """
        SELECT t.id, t.name, t.phone, t.specialty, t.created_at,
               COUNT(m.id) AS member_count
        FROM trainers t
        LEFT JOIN members m ON t.id = m.trainer_id
        WHERE t.id = ?
        GROUP BY t.id
    """
    cur = conn.execute(query, (trainer_id,))
    row = cur.fetchone()
    if not row:
        raise NotFoundError(f"Trainer with ID {trainer_id} not found.")
    return dict(row)


def get_trainer_members(
    conn: sqlite3.Connection,
    trainer_id: int,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Return all members assigned to a specific trainer with active/frozen status."""
    get_trainer(conn, trainer_id)  # Validate existence
    ref_date = today or date.today()
    query = """
        SELECT m.id, m.name, m.phone, m.plan_id, p.name AS plan_name,
               m.trainer_id, t.name AS trainer_name,
               m.start_date, m.end_date, m.created_at,
               COALESCE((SELECT SUM(days) FROM freezes WHERE member_id = m.id), 0) AS total_frozen_days,
               EXISTS(
                   SELECT 1 FROM freezes f
                   WHERE f.member_id = m.id AND f.start_date <= ? AND f.end_date >= ?
               ) AS is_frozen_int
        FROM members m
        JOIN plans p ON m.plan_id = p.id
        LEFT JOIN trainers t ON m.trainer_id = t.id
        WHERE m.trainer_id = ?
        ORDER BY m.name ASC
    """
    cur = conn.execute(query, (ref_date.isoformat(), ref_date.isoformat(), trainer_id))
    members = []
    for row in cur.fetchall():
        item = dict(row)
        is_frozen = bool(item.pop("is_frozen_int"))
        m_start = date.fromisoformat(item["start_date"])
        m_end = date.fromisoformat(item["end_date"])
        item["is_frozen"] = is_frozen
        item["is_active"] = (m_start <= ref_date <= m_end) and not is_frozen
        members.append(item)
    return members


# ---------------------------------------------------------------------------
# Members Registration & Querying
# ---------------------------------------------------------------------------

def register_member(
    conn: sqlite3.Connection,
    name: str,
    phone: str,
    plan_id: int,
    start_date: date,
    trainer_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Register a new member, calculate inclusive end date, and record initial payment."""
    clean_name = name.strip()
    clean_phone = phone.strip()
    if not clean_name or not clean_phone:
        raise ValidationError("Member name and phone are required.")

    plan = get_plan(conn, plan_id)

    if trainer_id is not None:
        get_trainer(conn, trainer_id)

    end_date = calculate_end_date(start_date, plan["duration_days"])
    current_ts = (now or datetime.now()).isoformat()

    cur = conn.execute(
        """
        INSERT INTO members (name, phone, plan_id, trainer_id, start_date, end_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_name,
            clean_phone,
            plan_id,
            trainer_id,
            start_date.isoformat(),
            end_date.isoformat(),
            current_ts,
        ),
    )
    member_id = cur.lastrowid

    # Record initial payment on start date
    conn.execute(
        """
        INSERT INTO payments (member_id, amount, payment_date, payment_type, created_at)
        VALUES (?, ?, ?, 'registration', ?)
        """,
        (member_id, plan["price"], start_date.isoformat(), current_ts),
    )

    return get_member(conn, member_id, today=start_date)


def get_member(
    conn: sqlite3.Connection,
    member_id: int,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Get member details with active and frozen status evaluated against 'today'."""
    ref_date = today or date.today()
    query = """
        SELECT m.id, m.name, m.phone, m.plan_id, p.name AS plan_name,
               m.trainer_id, t.name AS trainer_name,
               m.start_date, m.end_date, m.created_at,
               COALESCE((SELECT SUM(days) FROM freezes WHERE member_id = m.id), 0) AS total_frozen_days
        FROM members m
        JOIN plans p ON m.plan_id = p.id
        LEFT JOIN trainers t ON m.trainer_id = t.id
        WHERE m.id = ?
    """
    cur = conn.execute(query, (member_id,))
    row = cur.fetchone()
    if not row:
        raise NotFoundError(f"Member with ID {member_id} not found.")

    res = dict(row)
    m_start = date.fromisoformat(res["start_date"])
    m_end = date.fromisoformat(res["end_date"])

    # Check active freeze covering today
    cur_freeze = conn.execute(
        "SELECT 1 FROM freezes WHERE member_id = ? AND start_date <= ? AND end_date >= ? LIMIT 1",
        (member_id, ref_date.isoformat(), ref_date.isoformat()),
    )
    is_frozen = cur_freeze.fetchone() is not None

    # Membership is active if within date range and not frozen
    is_active = (m_start <= ref_date <= m_end) and not is_frozen

    res["is_active"] = is_active
    res["is_frozen"] = is_frozen
    return res


def list_members(
    conn: sqlite3.Connection,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """List all members with computed active and frozen status."""
    ref_date = today or date.today()
    query = """
        SELECT m.id, m.name, m.phone, m.plan_id, p.name AS plan_name,
               m.trainer_id, t.name AS trainer_name,
               m.start_date, m.end_date, m.created_at,
               COALESCE((SELECT SUM(days) FROM freezes WHERE member_id = m.id), 0) AS total_frozen_days,
               EXISTS(
                   SELECT 1 FROM freezes f
                   WHERE f.member_id = m.id AND f.start_date <= ? AND f.end_date >= ?
               ) AS is_frozen_int
        FROM members m
        JOIN plans p ON m.plan_id = p.id
        LEFT JOIN trainers t ON m.trainer_id = t.id
        ORDER BY m.id DESC
    """
    cur = conn.execute(query, (ref_date.isoformat(), ref_date.isoformat()))
    members = []
    for row in cur.fetchall():
        item = dict(row)
        is_frozen = bool(item.pop("is_frozen_int"))
        m_start = date.fromisoformat(item["start_date"])
        m_end = date.fromisoformat(item["end_date"])
        item["is_frozen"] = is_frozen
        item["is_active"] = (m_start <= ref_date <= m_end) and not is_frozen
        members.append(item)
    return members


def assign_trainer_to_member(
    conn: sqlite3.Connection,
    member_id: int,
    trainer_id: Optional[int],
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Assign or unassign a trainer for a member."""
    # Ensure member exists
    get_member(conn, member_id, today=today)
    if trainer_id is not None:
        get_trainer(conn, trainer_id)

    conn.execute(
        "UPDATE members SET trainer_id = ? WHERE id = ?",
        (trainer_id, member_id),
    )
    return get_member(conn, member_id, today=today)


# ---------------------------------------------------------------------------
# Expiring Soon Members
# ---------------------------------------------------------------------------

def get_expiring_soon_members(
    conn: sqlite3.Connection,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Return members whose end_date is between today and today + 7 days (inclusive).

    Sorted by end_date ascending. Shows name, phone, plan, end_date, days_left.
    """
    ref_date = today or date.today()
    max_date = ref_date + timedelta(days=7)

    query = """
        SELECT m.id, m.name, m.phone, p.name AS plan_name, m.end_date
        FROM members m
        JOIN plans p ON m.plan_id = p.id
        WHERE m.end_date >= ? AND m.end_date <= ?
        ORDER BY m.end_date ASC, m.name ASC
    """
    cur = conn.execute(query, (ref_date.isoformat(), max_date.isoformat()))
    results = []
    for row in cur.fetchall():
        item = dict(row)
        m_end = date.fromisoformat(item["end_date"])
        item["days_left"] = (m_end - ref_date).days
        results.append(item)
    return results


# ---------------------------------------------------------------------------
# Daily Check-Ins
# ---------------------------------------------------------------------------

def record_check_in(
    conn: sqlite3.Connection,
    member_id: int,
    check_in_date: Optional[date] = None,
    check_in_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Evaluate and record a check-in attempt.

    Rules:
    - BLOCK and log if member is unknown (member_id not found).
    - BLOCK and log if membership is not started yet (today < start_date).
    - BLOCK and log if membership is expired (today > end_date).
    - BLOCK and log if membership is currently frozen.
    - BLOCK and log duplicate allowed check-ins on the same day.
    - Otherwise allow and log.
    """
    ref_date = check_in_date or date.today()
    current_dt = check_in_time or datetime.now()
    ref_date_str = ref_date.isoformat()
    current_time_str = current_dt.isoformat()

    # Check if member exists
    cur_m = conn.execute(
        "SELECT m.id, m.name, m.start_date, m.end_date FROM members m WHERE m.id = ?",
        (member_id,),
    )
    member = cur_m.fetchone()

    if not member:
        # Unknown member
        allowed = False
        reason = f"Unknown member: ID {member_id} does not exist"
        cur = conn.execute(
            """
            INSERT INTO check_ins (member_id, attempted_member_id, check_in_date, check_in_time, allowed, reason)
            VALUES (NULL, ?, ?, ?, 0, ?)
            """,
            (member_id, ref_date_str, current_time_str, reason),
        )
        return {
            "id": cur.lastrowid,
            "member_id": None,
            "attempted_member_id": member_id,
            "member_name": None,
            "check_in_date": ref_date_str,
            "check_in_time": current_time_str,
            "allowed": allowed,
            "reason": reason,
        }

    # Member exists, check membership status
    member_name = member["name"]
    start_d = date.fromisoformat(member["start_date"])
    end_d = date.fromisoformat(member["end_date"])

    if ref_date < start_d:
        allowed = False
        reason = f"Membership has not started yet (starts on {start_d.isoformat()})"
    elif ref_date > end_d:
        allowed = False
        reason = f"Membership has expired (expired on {end_d.isoformat()})"
    else:
        # Check active freeze
        cur_f = conn.execute(
            """
            SELECT start_date, end_date FROM freezes
            WHERE member_id = ? AND start_date <= ? AND end_date >= ?
            LIMIT 1
            """,
            (member_id, ref_date_str, ref_date_str),
        )
        active_freeze = cur_f.fetchone()
        if active_freeze:
            allowed = False
            reason = f"Membership is currently frozen until {active_freeze['end_date']}"
        else:
            # Check duplicate allowed check-in today
            cur_dup = conn.execute(
                """
                SELECT 1 FROM check_ins
                WHERE member_id = ? AND check_in_date = ? AND allowed = 1
                LIMIT 1
                """,
                (member_id, ref_date_str),
            )
            if cur_dup.fetchone():
                allowed = False
                reason = "Duplicate check-in: Member has already checked in today"
            else:
                allowed = True
                reason = None

    # Log the check-in
    cur = conn.execute(
        """
        INSERT INTO check_ins (member_id, attempted_member_id, check_in_date, check_in_time, allowed, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            member_id,
            member_id,
            ref_date_str,
            current_time_str,
            1 if allowed else 0,
            reason,
        ),
    )

    return {
        "id": cur.lastrowid,
        "member_id": member_id,
        "attempted_member_id": member_id,
        "member_name": member_name,
        "check_in_date": ref_date_str,
        "check_in_time": current_time_str,
        "allowed": allowed,
        "reason": reason,
    }


def list_check_ins(
    conn: sqlite3.Connection,
    limit: int = 50,
    member_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List recent check-ins ordered by newest first."""
    if member_id is not None:
        query = """
            SELECT c.id, c.member_id, c.attempted_member_id, m.name AS member_name,
                   c.check_in_date, c.check_in_time, (c.allowed = 1) AS allowed, c.reason
            FROM check_ins c
            LEFT JOIN members m ON c.member_id = m.id
            WHERE c.attempted_member_id = ?
            ORDER BY c.id DESC
            LIMIT ?
        """
        cur = conn.execute(query, (member_id, limit))
    else:
        query = """
            SELECT c.id, c.member_id, c.attempted_member_id, m.name AS member_name,
                   c.check_in_date, c.check_in_time, (c.allowed = 1) AS allowed, c.reason
            FROM check_ins c
            LEFT JOIN members m ON c.member_id = m.id
            ORDER BY c.id DESC
            LIMIT ?
        """
        cur = conn.execute(query, (limit,))

    results = []
    for row in cur.fetchall():
        item = dict(row)
        item["allowed"] = bool(item["allowed"])
        results.append(item)
    return results


# ---------------------------------------------------------------------------
# Membership Freeze
# ---------------------------------------------------------------------------

def freeze_membership(
    conn: sqlite3.Connection,
    member_id: int,
    days: int,
    start_date: Optional[date] = None,
    reason: Optional[str] = None,
    today: Optional[date] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Freeze a membership for 1 to 30 days total (lifetime cap).

    Rules:
    - Days must be 1 <= days <= 30.
    - Lifetime cap: Member's lifetime total frozen days cannot exceed 30.
    - Reject if membership is expired (today > end_date).
    - Extends member end_date by the frozen days.
    - Blocks check-ins during the freeze period.
    """
    ref_today = today or date.today()
    freeze_start = start_date or ref_today

    if days < 1 or days > 30:
        raise ValidationError("Freeze duration must be between 1 and 30 days.")

    # Check member exists
    member = get_member(conn, member_id, today=ref_today)
    member_end = date.fromisoformat(member["end_date"])

    # Reject if membership is already expired
    if ref_today > member_end:
        raise ValidationError("Cannot freeze an expired membership.")

    # Check lifetime cap
    cur_used = conn.execute(
        "SELECT COALESCE(SUM(days), 0) FROM freezes WHERE member_id = ?",
        (member_id,),
    )
    used_days = cur_used.fetchone()[0]
    if used_days + days > 30:
        remaining = max(0, 30 - used_days)
        raise ValidationError(
            f"Lifetime freeze cap of 30 days exceeded. Member has already used {used_days} days. "
            f"Maximum remaining freeze allowance is {remaining} days."
        )

    # Calculate freeze range and new membership end date
    freeze_end = freeze_start + timedelta(days=days - 1)

    # Check overlapping freeze
    cur_overlap = conn.execute(
        """
        SELECT 1 FROM freezes
        WHERE member_id = ? AND NOT (end_date < ? OR start_date > ?)
        LIMIT 1
        """,
        (member_id, freeze_start.isoformat(), freeze_end.isoformat()),
    )
    if cur_overlap.fetchone():
        raise ValidationError("Requested freeze dates overlap with an existing freeze period.")

    # Extend membership end_date by the frozen days
    new_member_end = member_end + timedelta(days=days)

    conn.execute(
        "UPDATE members SET end_date = ? WHERE id = ?",
        (new_member_end.isoformat(), member_id),
    )

    created_at = (now or datetime.now()).isoformat()
    cur_f = conn.execute(
        """
        INSERT INTO freezes (member_id, start_date, end_date, days, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            member_id,
            freeze_start.isoformat(),
            freeze_end.isoformat(),
            days,
            reason.strip() if reason else None,
            created_at,
        ),
    )

    return {
        "id": cur_f.lastrowid,
        "member_id": member_id,
        "start_date": freeze_start.isoformat(),
        "end_date": freeze_end.isoformat(),
        "days": days,
        "reason": reason,
        "new_membership_end_date": new_member_end.isoformat(),
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Membership Renewal
# ---------------------------------------------------------------------------

def renew_membership(
    conn: sqlite3.Connection,
    member_id: int,
    plan_id: Optional[int] = None,
    renewal_date: Optional[date] = None,
    today: Optional[date] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Renew a membership.

    Extends from end_date if still active, otherwise from renewal_date (today).
    Logs a new payment for revenue accuracy.
    """
    ref_today = today or date.today()
    ref_renewal_date = renewal_date or ref_today

    member = get_member(conn, member_id, today=ref_today)
    target_plan_id = plan_id if plan_id is not None else member["plan_id"]
    plan = get_plan(conn, target_plan_id)

    old_end = date.fromisoformat(member["end_date"])

    if old_end >= ref_renewal_date:
        # Still active: extend from current end date
        new_end = old_end + timedelta(days=plan["duration_days"])
    else:
        # Already expired: extend from renewal date (inclusive)
        new_end = ref_renewal_date + timedelta(days=plan["duration_days"] - 1)

    current_ts = (now or datetime.now()).isoformat()

    conn.execute(
        "UPDATE members SET plan_id = ?, end_date = ? WHERE id = ?",
        (target_plan_id, new_end.isoformat(), member_id),
    )

    # Record renewal payment
    conn.execute(
        """
        INSERT INTO payments (member_id, amount, payment_date, payment_type, created_at)
        VALUES (?, ?, ?, 'renewal', ?)
        """,
        (member_id, plan["price"], ref_renewal_date.isoformat(), current_ts),
    )

    return {
        "member_id": member_id,
        "plan_id": target_plan_id,
        "plan_name": plan["name"],
        "old_end_date": old_end.isoformat(),
        "new_end_date": new_end.isoformat(),
        "amount_paid": plan["price"],
        "payment_date": ref_renewal_date.isoformat(),
    }


# ---------------------------------------------------------------------------
# Dashboard & Analytics
# ---------------------------------------------------------------------------

def get_dashboard_stats(
    conn: sqlite3.Connection,
    year: int,
    month: int,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Return dashboard analytics.

    - Monthly revenue: sum of all payments in given year and month.
    - Active members: valid on 'today' and not currently frozen.
    - Frozen members: currently in an active freeze on 'today'.
    - Total members: count of all members.
    - Today's check-ins: total, allowed, denied.
    """
    ref_today = today or date.today()
    ref_today_str = ref_today.isoformat()

    if month < 1 or month > 12:
        raise ValidationError(f"Invalid month {month}. Must be between 1 and 12.")

    # Calculate month prefix for payments (e.g. '2026-11%')
    month_pattern = f"{year:04d}-{month:02d}%"
    cur_rev = conn.execute(
        "SELECT COALESCE(SUM(amount), 0.0) FROM payments WHERE payment_date LIKE ?",
        (month_pattern,),
    )
    monthly_revenue = float(cur_rev.fetchone()[0])

    # Total members count
    cur_total = conn.execute("SELECT COUNT(*) FROM members")
    total_members = cur_total.fetchone()[0]

    # Active members: start_date <= today <= end_date and not frozen today
    cur_active = conn.execute(
        """
        SELECT COUNT(*) FROM members m
        WHERE m.start_date <= ? AND m.end_date >= ?
        AND NOT EXISTS (
            SELECT 1 FROM freezes f
            WHERE f.member_id = m.id AND f.start_date <= ? AND f.end_date >= ?
        )
        """,
        (ref_today_str, ref_today_str, ref_today_str, ref_today_str),
    )
    active_members = cur_active.fetchone()[0]

    # Frozen members today
    cur_frozen = conn.execute(
        """
        SELECT COUNT(DISTINCT member_id) FROM freezes
        WHERE start_date <= ? AND end_date >= ?
        """,
        (ref_today_str, ref_today_str),
    )
    frozen_members = cur_frozen.fetchone()[0]

    # Today's check-ins
    cur_chk_tot = conn.execute(
        "SELECT COUNT(*) FROM check_ins WHERE check_in_date = ?",
        (ref_today_str,),
    )
    today_checkins_total = cur_chk_tot.fetchone()[0]

    cur_chk_allow = conn.execute(
        "SELECT COUNT(*) FROM check_ins WHERE check_in_date = ? AND allowed = 1",
        (ref_today_str,),
    )
    today_checkins_allowed = cur_chk_allow.fetchone()[0]

    today_checkins_denied = today_checkins_total - today_checkins_allowed

    return {
        "year": year,
        "month": month,
        "monthly_revenue": monthly_revenue,
        "active_members": active_members,
        "frozen_members": frozen_members,
        "total_members": total_members,
        "today_checkins_total": today_checkins_total,
        "today_checkins_allowed": today_checkins_allowed,
        "today_checkins_denied": today_checkins_denied,
    }


# ---------------------------------------------------------------------------
# Demo Data Seeder
# ---------------------------------------------------------------------------

def seed_demo_data(conn: sqlite3.Connection, today: Optional[date] = None) -> Dict[str, Any]:
    """Seed comprehensive sample data for demonstration and testing."""
    ref_today = today or date.today()

    # 1. Plans
    plans = [
        {"name": "Monthly Basic", "duration_days": 30, "price": 49.99},
        {"name": "Quarterly Pro", "duration_days": 90, "price": 129.99},
        {"name": "Annual VIP", "duration_days": 365, "price": 449.99},
    ]
    created_plans = []
    for p in plans:
        try:
            created_plans.append(create_plan(conn, p["name"], p["duration_days"], p["price"]))
        except ConflictError:
            cur = conn.execute("SELECT id, name, duration_days, price, created_at FROM plans WHERE name = ?", (p["name"],))
            created_plans.append(dict(cur.fetchone()))

    # 2. Trainers
    trainers = [
        {"name": "Marcus Vance", "phone": "555-0101", "specialty": "Strength & Conditioning"},
        {"name": "Elena Rostova", "phone": "555-0102", "specialty": "HIIT & Functional Fitness"},
        {"name": "David Kim", "phone": "555-0103", "specialty": "Mobility & Injury Rehab"},
    ]
    created_trainers = []
    cur_t_count = conn.execute("SELECT COUNT(*) FROM trainers").fetchone()[0]
    if cur_t_count == 0:
        for t in trainers:
            created_trainers.append(create_trainer(conn, t["name"], t["phone"], t["specialty"]))
    else:
        created_trainers = list_trainers(conn)

    # 3. Members
    cur_m_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    if cur_m_count == 0:
        p_basic = created_plans[0]["id"]
        p_pro = created_plans[1]["id"]
        p_vip = created_plans[2]["id"]

        t1 = created_trainers[0]["id"] if created_trainers else None
        t2 = created_trainers[1]["id"] if len(created_trainers) > 1 else None

        # Member 1: Active VIP member
        m1 = register_member(
            conn, "Sarah Connor", "555-1111", p_vip,
            start_date=ref_today - timedelta(days=60),
            trainer_id=t1,
        )

        # Member 2: Expiring Soon (3 days left)
        m2 = register_member(
            conn, "John Wick", "555-2222", p_basic,
            start_date=ref_today - timedelta(days=26),
            trainer_id=t2,
        )

        # Member 3: Expired Member (expired 10 days ago)
        m3 = register_member(
            conn, "Bruce Wayne", "555-3333", p_basic,
            start_date=ref_today - timedelta(days=40),
        )

        # Member 4: Future Member (starts in 5 days)
        m4 = register_member(
            conn, "Diana Prince", "555-4444", p_pro,
            start_date=ref_today + timedelta(days=5),
            trainer_id=t1,
        )

        # Member 5: Active Member with a Freeze
        m5 = register_member(
            conn, "Peter Parker", "555-5555", p_basic,
            start_date=ref_today - timedelta(days=10),
        )
        # Apply 7-day freeze starting 2 days ago
        freeze_membership(
            conn, m5["id"], days=7,
            start_date=ref_today - timedelta(days=2),
            reason="Knee injury recovery",
            today=ref_today,
        )

        # 4. Check-Ins
        # Sarah check-in today (Allowed)
        record_check_in(conn, m1["id"], check_in_date=ref_today)
        # Bruce check-in today (Denied: Expired)
        record_check_in(conn, m3["id"], check_in_date=ref_today)
        # Peter check-in today (Denied: Frozen)
        record_check_in(conn, m5["id"], check_in_date=ref_today)
        # Unknown member check-in (Denied: Unknown)
        record_check_in(conn, 9999, check_in_date=ref_today)

    return {
        "detail": "Demo data successfully seeded.",
        "plans_count": len(list_plans(conn)),
        "trainers_count": len(list_trainers(conn)),
        "members_count": len(list_members(conn, today=ref_today)),
    }
