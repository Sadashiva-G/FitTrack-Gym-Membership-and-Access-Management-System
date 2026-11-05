"""FastAPI application for FitTrack: Gym Membership and Access Management System."""

from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database import get_db, init_db
from backend.models import (
    AssignTrainerCreate,
    CheckInCreate,
    CheckInResponse,
    DashboardStats,
    ExpiringMemberResponse,
    FreezeCreate,
    FreezeResponse,
    MemberCreate,
    MemberResponse,
    PlanCreate,
    PlanResponse,
    RenewCreate,
    RenewResponse,
    TrainerCreate,
    TrainerResponse,
)
from backend.services import (
    ConflictError,
    FitTrackError,
    NotFoundError,
    ValidationError,
    assign_trainer_to_member,
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
    seed_demo_data,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifespan events. Auto-creates tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="FitTrack API",
    description="Gym Membership and Access Management System Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Standardize validation error responses into {"detail": "..."}
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = " -> ".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = first.get("msg", "Invalid input")
        detail = f"{loc}: {msg}" if loc else msg
    else:
        detail = "Validation error"
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": detail})


@app.exception_handler(FitTrackError)
async def fittrack_error_handler(request: Request, exc: FitTrackError):
    if isinstance(exc, NotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, ValidationError):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Helper to parse an optional ISO date string."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.",
        ) from exc


# ---------------------------------------------------------------------------
# Health & Demo Seeding
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": "FitTrack"}


@app.post("/seed", tags=["Demo Data"])
def seed_data(
    today: Optional[str] = Query(None, description="Reference date YYYY-MM-DD"),
) -> Dict[str, Any]:
    """Seed demo data for quick testing and demonstration."""
    ref_date = parse_date(today)
    with get_db() as conn:
        return seed_demo_data(conn, today=ref_date)


# ---------------------------------------------------------------------------
# Membership Plans
# ---------------------------------------------------------------------------

@app.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED, tags=["Plans"])
def api_create_plan(plan: PlanCreate):
    """Create a new membership plan."""
    with get_db() as conn:
        return create_plan(conn, plan.name, plan.duration_days, plan.price)


@app.get("/plans", response_model=List[PlanResponse], tags=["Plans"])
def api_list_plans():
    """List all membership plans."""
    with get_db() as conn:
        return list_plans(conn)


@app.get("/plans/{plan_id}", response_model=PlanResponse, tags=["Plans"])
def api_get_plan(plan_id: int):
    """Get a membership plan by ID."""
    with get_db() as conn:
        return get_plan(conn, plan_id)


# ---------------------------------------------------------------------------
# Trainers
# ---------------------------------------------------------------------------

@app.post("/trainers", response_model=TrainerResponse, status_code=status.HTTP_201_CREATED, tags=["Trainers"])
def api_create_trainer(trainer: TrainerCreate):
    """Create a new personal trainer."""
    with get_db() as conn:
        return create_trainer(conn, trainer.name, trainer.phone, trainer.specialty)


@app.get("/trainers", response_model=List[TrainerResponse], tags=["Trainers"])
def api_list_trainers():
    """List all trainers with member counts."""
    with get_db() as conn:
        return list_trainers(conn)


@app.get("/trainers/{trainer_id}", response_model=TrainerResponse, tags=["Trainers"])
def api_get_trainer(trainer_id: int):
    """Get a trainer by ID."""
    with get_db() as conn:
        return get_trainer(conn, trainer_id)


@app.get("/trainers/{trainer_id}/members", response_model=List[MemberResponse], tags=["Trainers"])
def api_get_trainer_members(
    trainer_id: int,
    today: Optional[str] = Query(None, description="Evaluation date YYYY-MM-DD"),
):
    """List all members assigned to a trainer."""
    ref_date = parse_date(today)
    with get_db() as conn:
        return get_trainer_members(conn, trainer_id, today=ref_date)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@app.post("/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED, tags=["Members"])
def api_register_member(member: MemberCreate):
    """Register a new member, calculate end date, and record initial payment."""
    start_d = date.fromisoformat(member.start_date)
    with get_db() as conn:
        return register_member(
            conn,
            member.name,
            member.phone,
            member.plan_id,
            start_date=start_d,
            trainer_id=member.trainer_id,
        )


@app.get("/members/expiring-soon", response_model=List[ExpiringMemberResponse], tags=["Members"])
def api_expiring_soon(
    today: Optional[str] = Query(None, description="Evaluation date YYYY-MM-DD"),
):
    """List members whose end_date is between today and today+7 days (inclusive)."""
    ref_date = parse_date(today)
    with get_db() as conn:
        return get_expiring_soon_members(conn, today=ref_date)


@app.get("/members", response_model=List[MemberResponse], tags=["Members"])
def api_list_members(
    today: Optional[str] = Query(None, description="Evaluation date YYYY-MM-DD"),
):
    """List all members with computed active and frozen status."""
    ref_date = parse_date(today)
    with get_db() as conn:
        return list_members(conn, today=ref_date)


@app.get("/members/{member_id}", response_model=MemberResponse, tags=["Members"])
def api_get_member(
    member_id: int,
    today: Optional[str] = Query(None, description="Evaluation date YYYY-MM-DD"),
):
    """Get a specific member by ID."""
    ref_date = parse_date(today)
    with get_db() as conn:
        return get_member(conn, member_id, today=ref_date)


@app.put("/members/{member_id}/trainer", response_model=MemberResponse, tags=["Members"])
def api_assign_trainer(member_id: int, payload: AssignTrainerCreate):
    """Assign or unassign a trainer to a member."""
    with get_db() as conn:
        return assign_trainer_to_member(conn, member_id, payload.trainer_id)


@app.post(
    "/members/{member_id}/freeze",
    response_model=FreezeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Members"],
)
def api_freeze_member(
    member_id: int,
    payload: FreezeCreate,
    today: Optional[str] = Query(None, description="Evaluation date YYYY-MM-DD"),
):
    """Freeze a membership for 1-30 days total (lifetime cap). Extends end date."""
    ref_date = parse_date(today)
    start_d = parse_date(payload.start_date)
    with get_db() as conn:
        return freeze_membership(
            conn,
            member_id=member_id,
            days=payload.days,
            start_date=start_d,
            reason=payload.reason,
            today=ref_date,
        )


@app.post(
    "/members/{member_id}/renew",
    response_model=RenewResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Members"],
)
def api_renew_member(
    member_id: int,
    payload: RenewCreate,
    today: Optional[str] = Query(None, description="Evaluation date YYYY-MM-DD"),
):
    """Renew a member, extending from end_date if active or today if expired, and log payment."""
    ref_date = parse_date(today)
    ren_d = parse_date(payload.renewal_date)
    with get_db() as conn:
        return renew_membership(
            conn,
            member_id=member_id,
            plan_id=payload.plan_id,
            renewal_date=ren_d,
            today=ref_date,
        )


# ---------------------------------------------------------------------------
# Check-Ins
# ---------------------------------------------------------------------------

@app.post("/check-ins", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED, tags=["Check-Ins"])
def api_record_check_in(payload: CheckInCreate):
    """Attempt a member check-in. Evaluates rules and logs result (allowed or blocked with reason)."""
    chk_date = parse_date(payload.check_in_date)
    with get_db() as conn:
        return record_check_in(conn, member_id=payload.member_id, check_in_date=chk_date)


@app.get("/check-ins", response_model=List[CheckInResponse], tags=["Check-Ins"])
def api_list_check_ins(
    limit: int = Query(50, ge=1, le=500),
    member_id: Optional[int] = Query(None, gt=0),
):
    """List recent check-ins."""
    with get_db() as conn:
        return list_check_ins(conn, limit=limit, member_id=member_id)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_model=DashboardStats, tags=["Dashboard"])
def api_get_dashboard(
    year: Optional[int] = Query(None, description="Year for monthly revenue"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month for monthly revenue"),
    today: Optional[str] = Query(None, description="Evaluation date YYYY-MM-DD"),
):
    """Get dashboard stats: monthly revenue, active members, total members, today's check-ins."""
    ref_date = parse_date(today) or date.today()
    target_year = year or ref_date.year
    target_month = month or ref_date.month

    with get_db() as conn:
        return get_dashboard_stats(conn, year=target_year, month=target_month, today=ref_date)
