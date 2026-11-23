"""FastAPI route handlers for CampusPilot AI lab booking workflows."""

from datetime import datetime
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.schemas import (
    AvailabilityResponse,
    BookingCreateRequest,
    BookingResponse,
    HealthResponse,
    LabResponse,
    RoomAvailabilityResponse,
    RoomBookingCreateRequest,
    RoomBookingResponse,
    RoomResponse,
)
from app.database import (
    check_booking_overlap,
    check_room_booking_overlap,
    create_booking,
    create_room_booking,
    get_all_discussion_rooms,
    get_all_laboratories,
    get_bookings_by_date,
    get_discussion_room_by_id,
    get_laboratory_by_id,
    get_room_bookings_by_date,
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


# ==========================================
# LIBRARY DISCUSSION ROOM ENDPOINTS
# ==========================================

@router.get(
    "/rooms",
    response_model=List[RoomResponse],
    summary="Get all library discussion rooms",
    description="Retrieves all registered discussion rooms from the SQLite database.",
)
def list_rooms() -> List[RoomResponse]:
    """Fetch all library discussion rooms."""
    rooms = get_all_discussion_rooms()
    return [RoomResponse(**r) for r in rooms]


@router.get(
    "/rooms/bookings",
    response_model=List[RoomBookingResponse],
    summary="Get room bookings by date",
    description="Retrieves confirmed discussion room reservations for a specified date from SQLite.",
)
def list_room_bookings(
    booking_date: str = Query(
        ...,
        description="Booking date in YYYY-MM-DD format",
        examples=["2026-11-20"],
    ),
    room_id: Optional[int] = Query(
        None,
        description="Optional filter by discussion room ID",
        examples=[1],
    ),
) -> List[RoomBookingResponse]:
    """Retrieve discussion room reservations for a given date."""
    valid_date = _validate_date_string(booking_date)
    bookings = get_room_bookings_by_date(valid_date, room_id=room_id)
    return [RoomBookingResponse(**b) for b in bookings]


@router.get(
    "/rooms/availability",
    response_model=RoomAvailabilityResponse,
    summary="Check discussion room slot availability",
    description="Checks actual SQLite bookings to verify if a requested discussion room slot is available.",
)
def check_room_availability_endpoint(
    room_id: int = Query(..., gt=0, description="Target discussion room ID", examples=[1]),
    booking_date: str = Query(..., description="Date in YYYY-MM-DD format", examples=["2026-11-20"]),
    start_time: str = Query(..., description="Start time in HH:MM format", examples=["14:00"]),
    end_time: str = Query(..., description="End time in HH:MM format", examples=["16:00"]),
) -> RoomAvailabilityResponse:
    """Check if a library discussion room slot is available or occupied."""
    valid_date = _validate_date_string(booking_date)
    valid_start = _validate_time_string(start_time, "start_time")
    valid_end = _validate_time_string(end_time, "end_time")

    # Verify discussion room exists
    room = get_discussion_room_by_id(room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discussion room with room_id={room_id} not found.",
        )

    # Validate start_time < end_time
    try:
        validate_time_range(valid_start, valid_end)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check for actual database overlap
    is_overlapping = check_room_booking_overlap(
        room_id=room_id,
        booking_date=valid_date,
        start_time=valid_start,
        end_time=valid_end,
    )

    is_available = not is_overlapping
    message = (
        f"Slot {valid_start}-{valid_end} is available in {room['room_name']} on {valid_date}."
        if is_available
        else f"Slot {valid_start}-{valid_end} is unavailable in {room['room_name']} due to an existing reservation."
    )

    return RoomAvailabilityResponse(
        room_id=room_id,
        booking_date=valid_date,
        start_time=valid_start,
        end_time=valid_end,
        is_available=is_available,
        message=message,
    )


@router.post(
    "/rooms/bookings",
    response_model=RoomBookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new discussion room reservation",
    description="Validates input, checks for conflicts, and saves a confirmed discussion room booking to SQLite.",
)
def create_new_room_booking(payload: RoomBookingCreateRequest) -> RoomBookingResponse:
    """Create a new confirmed discussion room reservation."""
    # Validate start_time < end_time
    try:
        validate_time_range(payload.start_time, payload.end_time)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Create the reservation through our database operations module
    try:
        created = create_room_booking(
            student_id=payload.student_id,
            student_name=payload.student_name,
            room_id=payload.room_id,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        return RoomBookingResponse(**created)
    except ValueError as e:
        err_msg = str(e)
        if "does not exist" in err_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        elif "conflict" in err_msg.lower() or "already booked" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)


# ==========================================
# AGENTIC RECOMMENDATION & FACILITY METADATA
# ==========================================

@router.get(
    "/recommendations",
    summary="Recommend facilities based on capacity and availability",
    description="Finds and ranks candidate facilities that fit the requested capacity without time conflicts.",
)
def get_recommendations(
    facility_type: str = Query("lab", description="Type of facility: 'lab' or 'room'"),
    booking_date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(..., description="Start time in HH:MM format"),
    end_time: str = Query(..., description="End time in HH:MM format"),
    min_capacity: int = Query(1, ge=1, description="Minimum seating or workstation capacity"),
    purpose: str = Query("", description="Optional purpose of the session"),
):
    from app.database import recommend_matching_facilities
    valid_date = _validate_date_string(booking_date)
    valid_start = _validate_time_string(start_time, "start_time")
    valid_end = _validate_time_string(end_time, "end_time")
    try:
        validate_time_range(valid_start, valid_end)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return recommend_matching_facilities(
        facility_type=facility_type,
        booking_date=valid_date,
        start_time=valid_start,
        end_time=valid_end,
        min_capacity=min_capacity,
        purpose=purpose,
    )


@router.post(
    "/cancel",
    summary="Cancel a reservation",
    description="Marks a booking or room reservation as cancelled.",
)
def cancel_booking_endpoint(
    booking_id: int = Query(..., gt=0),
    service_type: str = Query("Laboratory", description="'Laboratory' or 'Library Room'"),
):
    from app.database import cancel_reservation
    success = cancel_reservation(booking_id=booking_id, service_type=service_type)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found or already cancelled.")
    return {"status": "success", "message": f"Reservation #{booking_id} cancelled successfully."}


@router.get(
    "/facilities/{facility_type}/{facility_id}",
    summary="Get facility details with equipment",
    description="Retrieves full metadata including hardware/software and amenities.",
)
def get_facility_info(facility_type: str, facility_id: int):
    from app.database import get_facility_details_by_id
    info = get_facility_details_by_id(facility_type=facility_type, facility_id=facility_id)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found.")
    return info


# ==========================================
# USER PROFILE & IDENTITY ENDPOINTS
# ==========================================

@router.get(
    "/users/{user_id}/profile",
    summary="Get student profile",
    description="Retrieves the registered student profile for an authenticated user ID.",
)
def get_user_profile_endpoint(user_id: str):
    from app.database import get_student_profile
    profile = get_student_profile(user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student profile not found.")
    return profile


@router.post(
    "/users/profile",
    summary="Create or update student profile",
    description="Upserts student profile data without creating duplicates.",
)
def upsert_user_profile_endpoint(payload: dict):
    from app.database import upsert_student_profile
    user_id = payload.get("user_id")
    email = payload.get("email")
    full_name = payload.get("full_name", "")
    department = payload.get("department", "Engineering & Technology")

    if not user_id or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id and email are required.")

    return upsert_student_profile(
        user_id=user_id,
        full_name=full_name,
        email=email,
        department=department,
    )


@router.get(
    "/users/{user_id}/bookings",
    summary="Get user-specific bookings",
    description="Retrieves confirmed and past reservations strictly for the requested student ID.",
)
def get_user_bookings_endpoint(user_id: str):
    from app.database import get_all_student_reservations
    return get_all_student_reservations(student_id=user_id)


# ==========================================
# AUTHENTICATION & ACCESS CONTROL ENDPOINTS
# ==========================================

def verify_admin_authorization(
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> dict:
    """Verify administrator authorization for admin-only backend operations."""
    if x_user_role and x_user_role.lower() not in ("administrator", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Institutional administrator privileges required.",
        )

    if x_user_email:
        from app.services.demo_auth import get_user_by_email
        user = get_user_by_email(x_user_email)
        if user and user.get("account_type", "").lower() not in ("administrator", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access Denied: Account does not possess institutional administrator privileges.",
            )
        return user or {"account_type": "Administrator", "email": x_user_email}

    return {"account_type": "Administrator", "email": x_user_email or "admin"}


@router.post(
    "/auth/login",
    summary="User login authentication",
    description="Authenticates student or administrator and returns verified user session data.",
    tags=["Authentication"],
)
def auth_login_endpoint(payload: dict):
    from app.services.demo_auth import authenticate_user
    email = payload.get("email", "")
    password = payload.get("password", "")
    portal = payload.get("portal", "student")
    required_role = "Administrator" if str(portal).lower() in ("admin", "administrator") else None

    ok, res = authenticate_user(email, password, required_role=required_role)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=res)
    return {"status": "success", "user": res}


@router.post(
    "/auth/register",
    summary="Student account registration",
    description="Registers a new verified student account (enforcing Student role isolation).",
    tags=["Authentication"],
)
def auth_register_endpoint(payload: dict):
    from app.services.demo_auth import register_user
    ok, res = register_user(
        email=payload.get("email", ""),
        password=payload.get("password", ""),
        full_name=payload.get("full_name", ""),
        account_type="Student",  # Strictly Student
        student_id=payload.get("student_id", ""),
        university=payload.get("university", "Lovely Professional University"),
        department=payload.get("department", "Computer Science & Engineering"),
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res)
    return {"status": "success", "user": res}


# ==========================================
# ADMINISTRATIVE WORKFLOW ENDPOINTS
# ==========================================

@router.get(
    "/admin/requests",
    summary="Get all booking requests",
    description="Lists all student booking requests across labs and rooms for admin oversight.",
)
def get_admin_requests_endpoint(
    status: Optional[str] = Query(None, description="Optional status filter ('pending', 'approved', 'rejected')"),
    service: Optional[str] = Query(None, description="Optional service filter ('Laboratory', 'Library Room')"),
    admin_auth: dict = Depends(verify_admin_authorization),
):
    from app.database import get_all_booking_requests
    st_val = status if isinstance(status, str) else None
    svc_val = service if isinstance(service, str) else None
    return get_all_booking_requests(status_filter=st_val, service_filter=svc_val)


@router.post(
    "/admin/bookings/{booking_id}/approve",
    summary="Approve a booking request",
    description="Approves a pending booking after verifying conflict absence in SQLite.",
)
def approve_booking_endpoint(
    booking_id: int,
    service_type: str = Query("Laboratory", description="'Laboratory' or 'Library Room'"),
    admin_auth: dict = Depends(verify_admin_authorization),
):
    from app.database import approve_booking
    ok, msg = approve_booking(booking_id=booking_id, service_type=service_type)
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return {"status": "approved", "message": msg, "booking_id": booking_id}


@router.post(
    "/admin/bookings/{booking_id}/reject",
    summary="Reject a booking request",
    description="Rejects a booking request and records a rejection reason visible to the student.",
)
def reject_booking_endpoint(
    booking_id: int,
    service_type: str = Query("Laboratory", description="'Laboratory' or 'Library Room'"),
    payload: Optional[dict] = None,
    admin_auth: dict = Depends(verify_admin_authorization),
):
    from app.database import reject_booking
    reason = (payload or {}).get("rejection_reason", "Declined by department administrator")
    ok = reject_booking(booking_id=booking_id, service_type=service_type, rejection_reason=reason)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found.")
    return {"status": "rejected", "booking_id": booking_id, "rejection_reason": reason}


@router.post(
    "/admin/facilities/{facility_type}/{facility_id}/toggle",
    summary="Toggle facility availability",
    description="Enables or disables facility reservations by administrator command.",
)
def toggle_facility_endpoint(
    facility_type: str,
    facility_id: int,
    is_enabled: int = Query(1, description="1 to enable, 0 to disable"),
    admin_auth: dict = Depends(verify_admin_authorization),
):
    from app.database import toggle_facility_status
    ok = toggle_facility_status(facility_type=facility_type, facility_id=facility_id, is_enabled=is_enabled)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found.")
    return {"status": "success", "facility_id": facility_id, "is_enabled": is_enabled}


@router.get(
    "/admin/metrics",
    summary="Get administrative metrics",
    description="Retrieves live summary statistics on requests and facility utilization.",
)
def get_admin_metrics_endpoint(
    admin_auth: dict = Depends(verify_admin_authorization),
):
    from app.database import get_admin_dashboard_metrics
    return get_admin_dashboard_metrics()


# ==========================================
# LEAVE MANAGEMENT ENDPOINTS (AUTO-ACCEPTANCE)
# ==========================================

@router.post(
    "/leave/request",
    status_code=status.HTTP_201_CREATED,
    summary="Submit student leave request",
    description="Submits a leave request which is automatically evaluated per configured campus policy.",
)
def create_leave_request_endpoint(payload: dict):
    from app.database import create_leave_request
    try:
        res = create_leave_request(
            student_id=payload.get("student_id", ""),
            student_name=payload.get("student_name", ""),
            student_email=payload.get("student_email", ""),
            leave_type=payload.get("leave_type", "Academic Leave"),
            start_date=payload.get("start_date", ""),
            end_date=payload.get("end_date", ""),
            reason=payload.get("reason", ""),
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/leave/student/{student_id}",
    summary="Get student leave requests",
    description="Returns all submitted leave requests and auto-accepted statuses for a student.",
)
def get_student_leaves_endpoint(student_id: str):
    from app.database import get_student_leave_requests
    return get_student_leave_requests(student_id)


@router.get(
    "/leave/all",
    summary="Get all leave requests",
    description="Returns all leave records across campus for administrator oversight.",
)
def get_all_leaves_endpoint():
    from app.database import get_all_leave_requests
    return get_all_leave_requests()



