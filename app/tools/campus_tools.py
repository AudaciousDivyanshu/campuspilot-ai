"""Campus service tools for CampusPilot AI.

These tools interact with the running FastAPI backend over HTTP,
ensuring strict separation of concerns without duplicating database logic.
"""

import os
from typing import Any, Dict
from dotenv import load_dotenv
from langchain_core.tools import tool
import requests

from app.tools.date_utils import resolve_date_string

load_dotenv()

# Backend configuration from environment or defaults
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BASE_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")


@tool
def list_laboratories() -> str:
    """Retrieve all available campus laboratories, their IDs, capacity, and location.

    Use this tool whenever the student asks what labs exist or when you need to find
    a lab's ID based on its name (e.g. AI Lab, Computer Lab 1, Networking Lab).
    """
    try:
        response = requests.get(f"{BASE_URL}/labs", timeout=5)
        if response.status_code == 200:
            labs = response.json()
            if not labs:
                return "No laboratories found in the campus system."
            formatted = ["Available Campus Laboratories:"]
            for lab in labs:
                formatted.append(
                    f"- Lab ID {lab['lab_id']}: '{lab['lab_name']}' | Capacity: {lab['capacity']} | Location: {lab.get('location', 'N/A')}"
                )
            return "\n".join(formatted)
        return f"Error fetching laboratories: HTTP {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to backend server at {BASE_URL}. Is FastAPI running? Error: {str(e)}"


@tool
def check_lab_availability(lab_id: int, booking_date: str, start_time: str, end_time: str) -> str:
    """Check if a specific laboratory is available for a given date and time range.

    Args:
        lab_id: The integer ID of the laboratory (e.g., 1, 2, 3).
        booking_date: The date in 'YYYY-MM-DD' format (e.g., '2026-11-20').
        start_time: The start time in 24-hour 'HH:MM' format (e.g., '10:00').
        end_time: The end time in 24-hour 'HH:MM' format (e.g., '12:00').

    Returns:
        A message indicating whether the slot is available or occupied.
    """
    try:
        resolved_date = resolve_date_string(booking_date)
        params = {
            "lab_id": lab_id,
            "booking_date": resolved_date,
            "start_time": start_time.strip(),
            "end_time": end_time.strip(),
        }
        response = requests.get(f"{BASE_URL}/availability", params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("is_available"):
                return f"AVAILABLE: Slot {start_time}-{end_time} on {resolved_date} for Lab ID {lab_id} is free."
            else:
                return f"UNAVAILABLE: Slot {start_time}-{end_time} on {resolved_date} for Lab ID {lab_id} is already booked."
        elif response.status_code == 404:
            return f"Lab ID {lab_id} not found. Use list_laboratories to verify valid lab IDs."
        elif response.status_code == 400:
            return f"Invalid request: {response.json().get('detail', response.text)}"
        return f"Error checking availability: HTTP {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to backend server at {BASE_URL}. Error: {str(e)}"


@tool
def create_lab_booking(
    student_id: str,
    student_name: str,
    lab_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
) -> str:
    """Create a confirmed lab booking in the system.

    CRITICAL RULE: Call this tool ONLY after the student has explicitly confirmed
    the booking details (date, time, lab, student ID, and student name).

    Args:
        student_id: The student's ID/Roll number (e.g., 'CS2026-042').
        student_name: The student's full name (e.g., 'Aarav Sharma').
        lab_id: The integer ID of the laboratory (e.g., 2).
        booking_date: The date in 'YYYY-MM-DD' format (e.g., '2026-11-20').
        start_time: The start time in 24-hour 'HH:MM' format (e.g., '10:00').
        end_time: The end time in 24-hour 'HH:MM' format (e.g., '12:00').

    Returns:
        Confirmation details with booking ID or conflict error message.
    """
    try:
        resolved_date = resolve_date_string(booking_date)
        payload = {
            "student_id": student_id.strip(),
            "student_name": student_name.strip(),
            "lab_id": int(lab_id),
            "booking_date": resolved_date,
            "start_time": start_time.strip(),
            "end_time": end_time.strip(),
        }
        response = requests.post(f"{BASE_URL}/bookings", json=payload, timeout=5)
        if response.status_code == 201:
            data = response.json()
            return (
                f"BOOKING CONFIRMED!\n"
                f"- Booking ID: {data.get('booking_id')}\n"
                f"- Student: {data.get('student_name')} ({data.get('student_id')})\n"
                f"- Lab: {data.get('lab_name')} (ID: {data.get('lab_id')})\n"
                f"- Date: {data.get('booking_date')}\n"
                f"- Time: {data.get('start_time')} to {data.get('end_time')}\n"
                f"- Status: {data.get('status')}"
            )
        elif response.status_code == 409:
            detail = response.json().get("detail", "Time slot conflict.")
            return f"BOOKING REJECTED (CONFLICT): {detail}"
        elif response.status_code == 400:
            detail = response.json().get("detail", "Invalid input.")
            return f"BOOKING FAILED: {detail}"
        elif response.status_code == 404:
            return f"BOOKING FAILED: Lab ID {lab_id} does not exist."
        return f"Error creating booking: HTTP {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to backend server at {BASE_URL}. Error: {str(e)}"


# ==========================================
# LIBRARY DISCUSSION ROOM TOOLS
# ==========================================

@tool
def list_discussion_rooms() -> str:
    """Retrieve all available library discussion rooms, their IDs, capacity, and location.

    Use this tool whenever the student asks what library discussion rooms exist or
    needs to find a discussion room ID based on its name (e.g. Discussion Room 1, Discussion Room 2).
    """
    try:
        response = requests.get(f"{BASE_URL}/rooms", timeout=5)
        if response.status_code == 200:
            rooms = response.json()
            if not rooms:
                return "No library discussion rooms found in the campus system."
            formatted = ["Available Library Discussion Rooms:"]
            for room in rooms:
                formatted.append(
                    f"- Room ID {room['room_id']}: '{room['room_name']}' | Capacity: {room['capacity']} seats | Location: {room.get('location', 'N/A')}"
                )
            return "\n".join(formatted)
        return f"Error fetching discussion rooms: HTTP {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to backend server at {BASE_URL}. Is FastAPI running? Error: {str(e)}"


@tool
def check_room_availability(room_id: int, booking_date: str, start_time: str, end_time: str) -> str:
    """Check if a specific library discussion room is available for a given date and time range.

    Args:
        room_id: The integer ID of the discussion room (e.g., 1, 2, 3).
        booking_date: The date in 'YYYY-MM-DD' format (e.g., '2026-11-20').
        start_time: The start time in 24-hour 'HH:MM' format (e.g., '14:00').
        end_time: The end time in 24-hour 'HH:MM' format (e.g., '16:00').

    Returns:
        A message indicating whether the room slot is available or occupied.
    """
    try:
        resolved_date = resolve_date_string(booking_date)
        params = {
            "room_id": room_id,
            "booking_date": resolved_date,
            "start_time": start_time.strip(),
            "end_time": end_time.strip(),
        }
        response = requests.get(f"{BASE_URL}/rooms/availability", params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("is_available"):
                return f"AVAILABLE: Slot {start_time}-{end_time} on {resolved_date} for Room ID {room_id} is free."
            else:
                return f"UNAVAILABLE: Slot {start_time}-{end_time} on {resolved_date} for Room ID {room_id} is already booked."
        elif response.status_code == 404:
            return f"Room ID {room_id} not found. Use list_discussion_rooms to verify valid room IDs."
        elif response.status_code == 400:
            return f"Invalid request: {response.json().get('detail', response.text)}"
        return f"Error checking room availability: HTTP {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to backend server at {BASE_URL}. Error: {str(e)}"


@tool
def create_room_reservation(
    student_id: str,
    student_name: str,
    room_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
) -> str:
    """Create a confirmed library discussion room reservation in the system.

    CRITICAL RULE: Call this tool ONLY after the student has explicitly confirmed
    the reservation details (date, time, discussion room, student ID, and student name).

    Args:
        student_id: The student's ID/Roll number (e.g., 'CS2026-042').
        student_name: The student's full name (e.g., 'Aarav Sharma').
        room_id: The integer ID of the discussion room (e.g., 1, 2, 3).
        booking_date: The date in 'YYYY-MM-DD' format (e.g., '2026-11-20').
        start_time: The start time in 24-hour 'HH:MM' format (e.g., '14:00').
        end_time: The end time in 24-hour 'HH:MM' format (e.g., '16:00').

    Returns:
        Confirmation details with booking ID or conflict error message.
    """
    try:
        resolved_date = resolve_date_string(booking_date)
        payload = {
            "student_id": student_id.strip(),
            "student_name": student_name.strip(),
            "room_id": int(room_id),
            "booking_date": resolved_date,
            "start_time": start_time.strip(),
            "end_time": end_time.strip(),
        }
        response = requests.post(f"{BASE_URL}/rooms/bookings", json=payload, timeout=5)
        if response.status_code == 201:
            data = response.json()
            return (
                f"DISCUSSION ROOM RESERVED!\n"
                f"- Booking ID: {data.get('booking_id')}\n"
                f"- Student: {data.get('student_name')} ({data.get('student_id')})\n"
                f"- Discussion Room: {data.get('room_name')} (ID: {data.get('room_id')})\n"
                f"- Date: {data.get('booking_date')}\n"
                f"- Time: {data.get('start_time')} to {data.get('end_time')}\n"
                f"- Status: {data.get('status')}"
            )
        elif response.status_code == 409:
            detail = response.json().get("detail", "Time slot conflict.")
            return f"RESERVATION REJECTED (CONFLICT): {detail}"
        elif response.status_code == 400:
            detail = response.json().get("detail", "Invalid input.")
            return f"RESERVATION FAILED: {detail}"
        elif response.status_code == 404:
            return f"RESERVATION FAILED: Room ID {room_id} does not exist."
        return f"Error creating room reservation: HTTP {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as e:
        return f"Failed to connect to backend server at {BASE_URL}. Error: {str(e)}"


# ==========================================
# AGENTIC RECOMMENDATION & DISCOVERY TOOLS
# ==========================================

@tool
def recommend_facilities(
    facility_type: str,
    booking_date: str,
    start_time: str,
    end_time: str,
    min_capacity: int = 1,
    purpose: str = "",
) -> str:
    """Search, filter, and rank campus facilities based on capacity, time, and conflict-free availability.

    Use this tool whenever a student provides capacity requirements (e.g. 'for 30 students',
    'team of 4', 'for 6 people') or asks for facility recommendations.

    Args:
        facility_type: 'lab' for laboratories or 'room' for library discussion rooms.
        booking_date: The date in 'YYYY-MM-DD' format (e.g., '2026-11-20').
        start_time: The start time in 24-hour 'HH:MM' format (e.g., '10:00').
        end_time: The end time in 24-hour 'HH:MM' format (e.g., '12:00').
        min_capacity: Required capacity or student count (integer, e.g. 30).
        purpose: Optional purpose of booking (e.g. 'Python practical', 'Group study').
    """
    resolved_date = resolve_date_string(booking_date)
    params = {
        "facility_type": facility_type,
        "booking_date": resolved_date,
        "start_time": start_time.strip(),
        "end_time": end_time.strip(),
        "min_capacity": int(min_capacity),
        "purpose": purpose or "",
    }

    try:
        response = requests.get(f"{BASE_URL}/recommendations", params=params, timeout=5)
        if response.status_code == 200:
            recommendations = response.json()
        else:
            from app.database import recommend_matching_facilities
            recommendations = recommend_matching_facilities(**params)
    except Exception:
        from app.database import recommend_matching_facilities
        recommendations = recommend_matching_facilities(**params)

    if not recommendations:
        return f"No {facility_type} facilities found matching your criteria."

    lines = [f"Facility Recommendations for {resolved_date} ({start_time} - {end_time}, Capacity >= {min_capacity}):"]
    import json
    for idx, rec in enumerate(recommendations, 1):
        status_tag = "AVAILABLE" if rec.get("is_available") and rec.get("is_capacity_sufficient") else "UNAVAILABLE"
        lines.append(
            f"{idx}. [{rec.get('match_badge', 'Option')}] {rec.get('facility_name')} (ID: {rec.get('facility_id')}) "
            f"| Capacity: {rec.get('capacity')} | Status: {status_tag} | Reason: {rec.get('match_reason')}"
        )

    # Embed machine-readable JSON metadata block for UI recommendation card rendering
    lines.append("\nRECOMMENDATION_DATA:")
    lines.append(json.dumps(recommendations))
    return "\n".join(lines)


@tool
def get_facility_details(facility_type: str, facility_id: int) -> str:
    """Retrieve full specifications, equipment, and location details for a lab or discussion room.

    Args:
        facility_type: 'lab' or 'room'.
        facility_id: The integer ID of the facility.
    """
    try:
        response = requests.get(f"{BASE_URL}/facilities/{facility_type}/{facility_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
        else:
            from app.database import get_facility_details_by_id
            data = get_facility_details_by_id(facility_type, facility_id)
    except Exception:
        from app.database import get_facility_details_by_id
        data = get_facility_details_by_id(facility_type, facility_id)

    if not data:
        return f"Facility ({facility_type} ID {facility_id}) not found."

    equipment_str = ", ".join(data.get("equipment", []))
    name_key = "lab_name" if "lab" in facility_type.lower() else "room_name"
    return (
        f"Facility: {data.get(name_key)} (ID: {facility_id})\n"
        f"- Type: {data.get('service_type')}\n"
        f"- Capacity: {data.get('capacity')}\n"
        f"- Location: {data.get('location')}\n"
        f"- Installed Equipment & Amenities: {equipment_str}"
    )


@tool
def get_student_bookings(student_id: str) -> str:
    """Look up all confirmed and past bookings for a specific student ID.

    Args:
        student_id: The student ID or roll number (e.g. 'CS2026-042').
    """
    from app.database import get_all_student_reservations
    reservations = get_all_student_reservations(student_id=student_id)
    if not reservations:
        return f"No reservations found for student {student_id}."

    lines = [f"Found {len(reservations)} reservations for student {student_id}:"]
    for r in reservations:
        lines.append(
            f"- Ref #{r.get('booking_id')}: {r.get('facility_name')} ({r.get('service_type')}) on {r.get('booking_date')} "
            f"from {r.get('start_time')} to {r.get('end_time')} [Status: {r.get('status')}]"
        )
    return "\n".join(lines)


@tool
def search_available_facilities(facility_type: str, booking_date: str, start_time: str, end_time: str) -> str:
    """Search for all facilities of the given type that are available at the requested date and time.

    Args:
        facility_type: 'lab' or 'room'.
        booking_date: Date in 'YYYY-MM-DD' format.
        start_time: Start time in 'HH:MM' format.
        end_time: End time in 'HH:MM' format.
    """
    return recommend_facilities.invoke({
        "facility_type": facility_type,
        "booking_date": booking_date,
        "start_time": start_time,
        "end_time": end_time,
        "min_capacity": 1,
    })


@tool
def check_facility_capacity(facility_type: str, facility_id: int, required_capacity: int) -> str:
    """Verify if a specific facility can accommodate the required number of people.

    Args:
        facility_type: 'lab' or 'room'.
        facility_id: Integer ID of the facility.
        required_capacity: Number of students or seats needed.
    """
    from app.database import get_laboratory_by_id, get_discussion_room_by_id
    if "lab" in facility_type.lower():
        fac = get_laboratory_by_id(facility_id)
        name = fac["lab_name"] if fac else f"Lab {facility_id}"
    else:
        fac = get_discussion_room_by_id(facility_id)
        name = fac["room_name"] if fac else f"Room {facility_id}"

    if not fac:
        return f"Facility ({facility_type} ID {facility_id}) not found."

    cap = fac["capacity"]
    if cap >= required_capacity:
        return f"CAPACITY SUFFICIENT: {name} has capacity {cap}, accommodating requested {required_capacity}."
    else:
        return f"CAPACITY INSUFFICIENT: {name} only has capacity {cap}, which is less than requested {required_capacity}."


@tool
def check_booking_conflicts(facility_type: str, facility_id: int, booking_date: str, start_time: str, end_time: str) -> str:
    """Check if there is a scheduling conflict for a specific facility at the given date and time.

    Args:
        facility_type: 'lab' or 'room'.
        facility_id: Integer ID of the facility.
        booking_date: Date in 'YYYY-MM-DD' format.
        start_time: Start time in 'HH:MM' format.
        end_time: End time in 'HH:MM' format.
    """
    resolved_date = resolve_date_string(booking_date)
    if "lab" in facility_type.lower():
        return check_lab_availability.invoke({
            "lab_id": facility_id,
            "booking_date": resolved_date,
            "start_time": start_time,
            "end_time": end_time,
        })
    else:
        return check_room_availability.invoke({
            "room_id": facility_id,
            "booking_date": resolved_date,
            "start_time": start_time,
            "end_time": end_time,
        })


@tool
def create_booking(
    facility_type: str,
    student_id: str,
    student_name: str,
    facility_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
) -> str:
    """Unified booking creation tool for both labs and discussion rooms.

    CRITICAL RULE: Call this tool ONLY after the student has explicitly confirmed!

    Args:
        facility_type: 'lab' or 'room'.
        student_id: Student ID / roll number.
        student_name: Student full name.
        facility_id: Integer ID of the facility.
        booking_date: Date in 'YYYY-MM-DD' format.
        start_time: Start time in 'HH:MM' format.
        end_time: End time in 'HH:MM' format.
    """
    if "lab" in facility_type.lower():
        return create_lab_booking.invoke({
            "student_id": student_id,
            "student_name": student_name,
            "lab_id": facility_id,
            "booking_date": booking_date,
            "start_time": start_time,
            "end_time": end_time,
        })
    else:
        return create_room_reservation.invoke({
            "student_id": student_id,
            "student_name": student_name,
            "room_id": facility_id,
            "booking_date": booking_date,
            "start_time": start_time,
            "end_time": end_time,
        })


@tool
def get_booking_status(booking_id: int, facility_type: str = "lab") -> str:
    """Check the status of an existing booking reference.

    Args:
        booking_id: Integer booking ID.
        facility_type: 'lab' or 'room'.
    """
    from app.database import get_db_context
    table = "bookings" if "lab" in facility_type.lower() else "room_bookings"
    fac_table = "labs" if "lab" in facility_type.lower() else "discussion_rooms"
    fac_id_col = "lab_id" if "lab" in facility_type.lower() else "room_id"
    fac_name_col = "lab_name" if "lab" in facility_type.lower() else "room_name"

    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT b.booking_id, b.student_id, b.student_name, b.{fac_id_col},
                   f.{fac_name_col} as facility_name, b.booking_date, b.start_time, b.end_time, b.status
            FROM {table} b
            JOIN {fac_table} f ON b.{fac_id_col} = f.{fac_id_col}
            WHERE b.booking_id = ?;
            """,
            (booking_id,),
        )
        row = cursor.fetchone()
        if not row:
            return f"Booking #{booking_id} not found."
        data = dict(row)
        return (
            f"Booking Status for #{booking_id}:\n"
            f"- Status: {data.get('status').upper()}\n"
            f"- Facility: {data.get('facility_name')}\n"
            f"- Date: {data.get('booking_date')}\n"
            f"- Time: {data.get('start_time')} to {data.get('end_time')}\n"
            f"- Student: {data.get('student_name')} ({data.get('student_id')})"
        )


# Export tools list
ALL_CAMPUS_TOOLS = [
    list_laboratories,
    check_lab_availability,
    create_lab_booking,
    list_discussion_rooms,
    check_room_availability,
    create_room_reservation,
    recommend_facilities,
    get_facility_details,
    get_student_bookings,
    search_available_facilities,
    check_facility_capacity,
    check_booking_conflicts,
    create_booking,
    get_booking_status,
]
