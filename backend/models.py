"""Pydantic schemas and validation models for FitTrack."""

from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_iso_date_str(value: Optional[str]) -> Optional[str]:
    """Validate that a string conforms to ISO YYYY-MM-DD date format."""
    if value is None:
        return None
    try:
        date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid date format '{value}'. Expected ISO format YYYY-MM-DD.") from exc
    return value


class PlanBase(BaseModel):
    """Base plan model."""
    name: str = Field(..., min_length=1, description="Plan name must be non-empty")
    duration_days: int = Field(..., gt=0, description="Duration in days must be greater than 0")
    price: float = Field(..., ge=0.0, description="Price must be non-negative")

    @field_validator("name")
    @classmethod
    def strip_and_validate_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Plan name cannot be blank")
        return clean


class PlanCreate(PlanBase):
    """Request schema for creating a plan."""
    pass


class PlanResponse(PlanBase):
    """Response schema for a plan."""
    id: int
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class TrainerBase(BaseModel):
    """Base trainer model."""
    name: str = Field(..., min_length=1, description="Trainer name")
    phone: str = Field(..., min_length=1, description="Trainer phone number")
    specialty: str = Field(..., min_length=1, description="Specialty or certification")

    @field_validator("name", "phone", "specialty")
    @classmethod
    def strip_fields(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Field cannot be blank")
        return clean


class TrainerCreate(TrainerBase):
    """Request schema for creating a trainer."""
    pass


class TrainerResponse(TrainerBase):
    """Response schema for a trainer."""
    id: int
    created_at: str
    member_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class MemberCreate(BaseModel):
    """Request schema for registering a member."""
    name: str = Field(..., min_length=1, description="Member full name")
    phone: str = Field(..., min_length=1, description="Member phone number")
    plan_id: int = Field(..., gt=0, description="Membership plan ID")
    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    trainer_id: Optional[int] = Field(None, gt=0, description="Optional trainer ID")

    @field_validator("name", "phone")
    @classmethod
    def strip_name_phone(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Field cannot be blank")
        return clean

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: str) -> str:
        res = validate_iso_date_str(v)
        assert res is not None
        return res


class MemberResponse(BaseModel):
    """Response schema for a member."""
    id: int
    name: str
    phone: str
    plan_id: int
    plan_name: Optional[str] = None
    trainer_id: Optional[int] = None
    trainer_name: Optional[str] = None
    start_date: str
    end_date: str
    is_active: bool
    is_frozen: bool
    total_frozen_days: int = 0
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class ExpiringMemberResponse(BaseModel):
    """Response schema for members expiring in the next 7 days."""
    id: int
    name: str
    phone: str
    plan_name: Optional[str] = None
    end_date: str
    days_left: int

    model_config = ConfigDict(from_attributes=True)


class AssignTrainerCreate(BaseModel):
    """Request schema for assigning/unassigning a trainer to a member."""
    trainer_id: Optional[int] = Field(None, gt=0, description="Trainer ID or null to unassign")


class CheckInCreate(BaseModel):
    """Request schema for a member check-in attempt."""
    member_id: int = Field(..., gt=0, description="Member ID attempting check-in")
    check_in_date: Optional[str] = Field(None, description="Check-in date (YYYY-MM-DD), defaults to today")

    @field_validator("check_in_date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        return validate_iso_date_str(v)


class CheckInResponse(BaseModel):
    """Response schema for check-in evaluation and logging."""
    id: Optional[int] = None
    member_id: Optional[int] = None
    attempted_member_id: int
    member_name: Optional[str] = None
    check_in_date: str
    check_in_time: str
    allowed: bool
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FreezeCreate(BaseModel):
    """Request schema for freezing a membership."""
    days: int = Field(..., ge=1, le=30, description="Number of days to freeze (1-30)")
    start_date: Optional[str] = Field(None, description="Freeze start date (YYYY-MM-DD), defaults to today")
    reason: Optional[str] = Field(None, description="Reason for freeze")

    @field_validator("start_date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        return validate_iso_date_str(v)


class FreezeResponse(BaseModel):
    """Response schema for a membership freeze."""
    id: int
    member_id: int
    start_date: str
    end_date: str
    days: int
    reason: Optional[str] = None
    new_membership_end_date: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class RenewCreate(BaseModel):
    """Request schema for renewing a membership."""
    plan_id: Optional[int] = Field(None, gt=0, description="Plan ID to renew with (defaults to current plan)")
    renewal_date: Optional[str] = Field(None, description="Renewal date (YYYY-MM-DD), defaults to today")

    @field_validator("renewal_date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        return validate_iso_date_str(v)


class RenewResponse(BaseModel):
    """Response schema for membership renewal."""
    member_id: int
    plan_id: int
    plan_name: str
    old_end_date: str
    new_end_date: str
    amount_paid: float
    payment_date: str

    model_config = ConfigDict(from_attributes=True)


class DashboardStats(BaseModel):
    """Response schema for dashboard statistics."""
    year: int
    month: int
    monthly_revenue: float
    active_members: int
    frozen_members: int
    total_members: int
    today_checkins_total: int
    today_checkins_allowed: int
    today_checkins_denied: int

    model_config = ConfigDict(from_attributes=True)
