"""Pydantic schemas for FastAPI request validation and response serialization."""

from datetime import datetime
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok", examples=["ok"])
    service: str = Field(default="CampusPilot AI Backend", examples=["CampusPilot AI Backend"])


class LabResponse(BaseModel):
    """Laboratory details response."""
    lab_id: int
    lab_name: str
    capacity: int
    location: Optional[str] = None


class BookingResponse(BaseModel):
    """Booking confirmation and details response."""
    booking_id: int
    student_id: str
    student_name: str
    lab_id: int
    lab_name: str
    booking_date: str
    start_time: str
    end_time: str
    status: str


class AvailabilityResponse(BaseModel):
    """Slot availability check response."""
    lab_id: int
    booking_date: str
    start_time: str
    end_time: str
    is_available: bool
    message: str


class BookingCreateRequest(BaseModel):
    """Request payload for creating a new lab booking."""
    student_id: str = Field(..., min_length=1, description="Student ID/Roll number", examples=["CS2026-042"])
    student_name: str = Field(..., min_length=1, description="Student full name", examples=["Aarav Sharma"])
    lab_id: int = Field(..., gt=0, description="Target laboratory ID", examples=[2])
    booking_date: str = Field(..., description="Date in YYYY-MM-DD format", examples=["2026-11-20"])
    start_time: str = Field(..., description="Start time in HH:MM format (24-hour)", examples=["10:00"])
    end_time: str = Field(..., description="End time in HH:MM format (24-hour)", examples=["12:00"])

    @field_validator("booking_date")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        value = value.strip()
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("booking_date must be in YYYY-MM-DD format (e.g., 2026-11-20).")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        value = value.strip()
        if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", value):
            raise ValueError("Time must be in 24-hour HH:MM format (e.g., 09:30, 14:00).")
        return value

