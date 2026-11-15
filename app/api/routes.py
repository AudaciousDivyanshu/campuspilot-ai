"""FastAPI route handlers for CampusPilot AI lab booking workflows."""

from datetime import datetime
import re
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import (
    AvailabilityResponse,
    BookingCreateRequest,
    BookingResponse,
    HealthResponse,
    LabResponse,
)
from app.database import (
    check_booking_overlap,
    create_booking,
    get_all_laboratories,
    get_bookings_by_date,
    get_laboratory_by_id,
    validate_time_range,
)

router = APIRouter()


def _validate_date_string(date_str: str) -> str:
    """Helper to validate date format (YYYY-MM-DD)."""
    trimmed = date_str.strip()
    try:
        datetime.strptime(trimmed, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="booking_date must be in YYYY-MM-DD format (e.g. 2026-11-20).",
        )
    return trimmed


def _validate_time_string(time_str: str, field_name: str) -> str:
    """Helper to validate 24-hour time format (HH:MM)."""
    trimmed = time_str.strip()
    if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", trimmed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be in 24-hour HH:MM format (e.g. 09:30, 14:00).",
        )
    return trimmed


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns simple backend operational status.",
)
def get_health() -> HealthResponse:
    """Check backend operational health."""
    return HealthResponse(status="ok", service="CampusPilot AI Backend")


@router.get(
    "/labs",
    response_model=List[LabResponse],
    summary="Get all laboratories",
    description="Retrieves all registered laboratories from the SQLite database.",
)
def list_labs() -> List[LabResponse]:
    """Fetch all laboratories."""
    labs = get_all_laboratories()
    return [LabResponse(**lab) for lab in labs]


@router.get(
    "/bookings",
    response_model=List[BookingResponse],
    summary="Get bookings by date",
    description="Retrieves confirmed bookings for a specified date from SQLite.",
)
def list_bookings(
    booking_date: str = Query(
        ...,
        description="Booking date in YYYY-MM-DD format",
        examples=["2026-11-20"],
    ),
    lab_id: Optional[int] = Query(
        None,
        description="Optional filter by laboratory ID",
        examples=[2],
    ),
) -> List[BookingResponse]:
    """Retrieve bookings for a given date."""
    valid_date = _validate_date_string(booking_date)
    bookings = get_bookings_by_date(valid_date, lab_id=lab_id)
    return [BookingResponse(**b) for b in bookings]


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    summary="Check slot availability",
    description="Checks actual SQLite bookings to verify if a requested time slot is available.",
)
def check_availability(
    lab_id: int = Query(..., gt=0, description="Target laboratory ID", examples=[2]),
    booking_date: str = Query(..., description="Date in YYYY-MM-DD format", examples=["2026-11-20"]),
    start_time: str = Query(..., description="Start time in HH:MM format", examples=["10:00"]),
    end_time: str = Query(..., description="End time in HH:MM format", examples=["12:00"]),
) -> AvailabilityResponse:
    """Check if a lab slot is available or occupied."""
    valid_date = _validate_date_string(booking_date)
    valid_start = _validate_time_string(start_time, "start_time")
    valid_end = _validate_time_string(end_time, "end_time")

    # Verify lab exists
    lab = get_laboratory_by_id(lab_id)
    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Laboratory with lab_id={lab_id} not found.",
        )

    # Validate start_time < end_time
    try:
        validate_time_range(valid_start, valid_end)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check for actual database overlap
    is_overlapping = check_booking_overlap(
        lab_id=lab_id,
        booking_date=valid_date,
        start_time=valid_start,
        end_time=valid_end,
    )

    is_available = not is_overlapping
    message = (
        f"Slot {valid_start}-{valid_end} is available in {lab['lab_name']} on {valid_date}."
        if is_available
        else f"Slot {valid_start}-{valid_end} is unavailable in {lab['lab_name']} due to an existing booking."
    )

    return AvailabilityResponse(
        lab_id=lab_id,
        booking_date=valid_date,
        start_time=valid_start,
        end_time=valid_end,
        is_available=is_available,
        message=message,
    )


@router.post(
    "/bookings",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new lab booking",
    description="Validates input, checks for conflicts, and saves a confirmed booking to SQLite.",
)
def create_new_booking(payload: BookingCreateRequest) -> BookingResponse:
    """Create a new confirmed lab booking."""
    # Validate start_time < end_time
    try:
        validate_time_range(payload.start_time, payload.end_time)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Create the booking through our database operations module
    try:
        created = create_booking(
            student_id=payload.student_id,
            student_name=payload.student_name,
            lab_id=payload.lab_id,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        return BookingResponse(**created)
    except ValueError as e:
        err_msg = str(e)
        if "does not exist" in err_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        elif "conflict" in err_msg.lower() or "already booked" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

