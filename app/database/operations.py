"""Database operations for CampusPilot AI lab bookings.

Contains pure SQLite query and mutation functions using parameterized SQL statements,
safe connection handling, and input validation.
"""

from pathlib import Path
import sqlite3
from typing import Any

from app.database.connection import get_db_context, get_db_path


def validate_time_range(start_time: str, end_time: str) -> None:
    """Validate that start_time is strictly earlier than end_time.

    Assumes standard 24-hour 'HH:MM' format (e.g., '09:00' to '11:00').
    """
    if not start_time or not end_time:
        raise ValueError("Both start_time and end_time must be provided.")
    if start_time.strip() >= end_time.strip():
        raise ValueError(
            f"Invalid time range: start_time '{start_time}' must be earlier than end_time '{end_time}'."
        )


def get_all_laboratories(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Retrieve all available laboratories.

    Returns:
        List of dictionaries containing lab_id, lab_name, capacity, and location.
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT lab_id, lab_name, capacity, location
            FROM labs
            ORDER BY lab_id ASC;
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_laboratory_by_id(lab_id: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Retrieve a single laboratory by its primary key ID."""
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT lab_id, lab_name, capacity, location
            FROM labs
            WHERE lab_id = ?;
            """,
            (lab_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_bookings_by_date(
    booking_date: str,
    lab_id: int | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Retrieve confirmed bookings for a specific date, optionally filtered by lab_id.

    Args:
        booking_date: Date string in 'YYYY-MM-DD' format.
        lab_id: Optional laboratory ID filter.
        db_path: Optional path to SQLite database.

    Returns:
        List of booking dictionaries including lab_name.
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        if lab_id is not None:
            cursor.execute(
                """
                SELECT b.booking_id, b.student_id, b.student_name, b.lab_id,
                       l.lab_name, b.booking_date, b.start_time, b.end_time, b.status
                FROM bookings b
                JOIN labs l ON b.lab_id = l.lab_id
                WHERE b.booking_date = ? AND b.lab_id = ? AND b.status = 'confirmed'
                ORDER BY b.start_time ASC;
                """,
                (booking_date, lab_id),
            )
        else:
            cursor.execute(
                """
                SELECT b.booking_id, b.student_id, b.student_name, b.lab_id,
                       l.lab_name, b.booking_date, b.start_time, b.end_time, b.status
                FROM bookings b
                JOIN labs l ON b.lab_id = l.lab_id
                WHERE b.booking_date = ? AND b.status = 'confirmed'
                ORDER BY b.lab_id ASC, b.start_time ASC;
                """,
                (booking_date,),
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def check_booking_overlap(
    lab_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
    exclude_booking_id: int | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Check whether a requested time interval overlaps with an existing confirmed booking for the same lab.

    Two intervals [start_req, end_req) and [start_exist, end_exist) overlap if:
        start_req < end_exist AND end_req > start_exist

    Args:
        lab_id: The target laboratory ID.
        booking_date: Date string ('YYYY-MM-DD').
        start_time: Start time string ('HH:MM').
        end_time: End time string ('HH:MM').
        exclude_booking_id: Optional booking ID to exclude (useful during updates).
        db_path: Optional database path.

    Returns:
        True if an overlapping confirmed booking exists; False otherwise.
    """
    validate_time_range(start_time, end_time)

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        if exclude_booking_id is not None:
            cursor.execute(
                """
                SELECT booking_id
                FROM bookings
                WHERE lab_id = ?
                  AND booking_date = ?
                  AND status = 'confirmed'
                  AND booking_id != ?
                  AND ? < end_time
                  AND ? > start_time
                LIMIT 1;
                """,
                (lab_id, booking_date, exclude_booking_id, start_time, end_time),
            )
        else:
            cursor.execute(
                """
                SELECT booking_id
                FROM bookings
                WHERE lab_id = ?
                  AND booking_date = ?
                  AND status = 'confirmed'
                  AND ? < end_time
                  AND ? > start_time
                LIMIT 1;
                """,
                (lab_id, booking_date, start_time, end_time),
            )
        return cursor.fetchone() is not None


def create_booking(
    student_id: str,
    student_name: str,
    lab_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
    status: str = "confirmed",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a new lab booking after verifying laboratory existence and slot availability.

    Args:
        student_id: Student roll/ID number.
        student_name: Full name of the student.
        lab_id: ID of the laboratory being booked.
        booking_date: Date of booking ('YYYY-MM-DD').
        start_time: Start time ('HH:MM').
        end_time: End time ('HH:MM').
        status: Initial status, default 'confirmed'.
        db_path: Optional path to the SQLite database.

    Returns:
        Dictionary containing all details of the newly created booking.

    Raises:
        ValueError: If parameters are invalid, lab does not exist, or slot overlaps an existing booking.
    """
    validate_time_range(start_time, end_time)

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()

        # Verify laboratory exists
        cursor.execute("SELECT lab_id, lab_name FROM labs WHERE lab_id = ?;", (lab_id,))
        lab = cursor.fetchone()
        if not lab:
            raise ValueError(f"Laboratory with lab_id={lab_id} does not exist.")

        # Check for overlapping confirmed bookings
        cursor.execute(
            """
            SELECT booking_id, student_name, start_time, end_time
            FROM bookings
            WHERE lab_id = ?
              AND booking_date = ?
              AND status = 'confirmed'
              AND ? < end_time
              AND ? > start_time
            LIMIT 1;
            """,
            (lab_id, booking_date, start_time, end_time),
        )
        conflict = cursor.fetchone()
        if conflict:
            raise ValueError(
                f"Booking conflict: Laboratory '{lab['lab_name']}' is already booked by "
                f"{conflict['student_name']} from {conflict['start_time']} to {conflict['end_time']}."
            )

        # Insert new booking
        cursor.execute(
            """
            INSERT INTO bookings (student_id, student_name, lab_id, booking_date, start_time, end_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (student_id.strip(), student_name.strip(), lab_id, booking_date.strip(), start_time.strip(), end_time.strip(), status.strip()),
        )
        new_booking_id = cursor.lastrowid

        return {
            "booking_id": new_booking_id,
            "student_id": student_id.strip(),
            "student_name": student_name.strip(),
            "lab_id": lab_id,
            "lab_name": lab["lab_name"],
            "booking_date": booking_date.strip(),
            "start_time": start_time.strip(),
            "end_time": end_time.strip(),
            "status": status.strip(),
        }


# ==========================================
# LIBRARY DISCUSSION ROOM OPERATIONS
# ==========================================

def get_all_discussion_rooms(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Retrieve all library discussion rooms.

    Returns:
        List of dictionaries containing room_id, room_name, capacity, and location.
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT room_id, room_name, capacity, location
            FROM discussion_rooms
            ORDER BY room_id ASC;
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_discussion_room_by_id(room_id: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Retrieve a single discussion room by its primary key ID."""
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT room_id, room_name, capacity, location
            FROM discussion_rooms
            WHERE room_id = ?;
            """,
            (room_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_room_bookings_by_date(
    booking_date: str,
    room_id: int | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Retrieve confirmed discussion room bookings for a specific date, optionally filtered by room_id.

    Args:
        booking_date: Date string in 'YYYY-MM-DD' format.
        room_id: Optional room ID filter.
        db_path: Optional path to SQLite database.

    Returns:
        List of booking dictionaries including room_name.
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        if room_id is not None:
            cursor.execute(
                """
                SELECT b.booking_id, b.student_id, b.student_name, b.room_id,
                       r.room_name, b.booking_date, b.start_time, b.end_time, b.status
                FROM room_bookings b
                JOIN discussion_rooms r ON b.room_id = r.room_id
                WHERE b.booking_date = ? AND b.room_id = ? AND b.status = 'confirmed'
                ORDER BY b.start_time ASC;
                """,
                (booking_date, room_id),
            )
        else:
            cursor.execute(
                """
                SELECT b.booking_id, b.student_id, b.student_name, b.room_id,
                       r.room_name, b.booking_date, b.start_time, b.end_time, b.status
                FROM room_bookings b
                JOIN discussion_rooms r ON b.room_id = r.room_id
                WHERE b.booking_date = ? AND b.status = 'confirmed'
                ORDER BY b.room_id ASC, b.start_time ASC;
                """,
                (booking_date,),
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def check_room_booking_overlap(
    room_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
    exclude_booking_id: int | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Check whether a requested time interval overlaps with an existing confirmed room booking.

    Interval overlap condition:
        start_req < end_exist AND end_req > start_exist

    Args:
        room_id: Target discussion room ID.
        booking_date: Date string ('YYYY-MM-DD').
        start_time: Start time string ('HH:MM').
        end_time: End time string ('HH:MM').
        exclude_booking_id: Optional booking ID to exclude.
        db_path: Optional database path.

    Returns:
        True if an overlapping confirmed booking exists; False otherwise.
    """
    validate_time_range(start_time, end_time)

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        if exclude_booking_id is not None:
            cursor.execute(
                """
                SELECT booking_id
                FROM room_bookings
                WHERE room_id = ?
                  AND booking_date = ?
                  AND status = 'confirmed'
                  AND booking_id != ?
                  AND ? < end_time
                  AND ? > start_time
                LIMIT 1;
                """,
                (room_id, booking_date, exclude_booking_id, start_time, end_time),
            )
        else:
            cursor.execute(
                """
                SELECT booking_id
                FROM room_bookings
                WHERE room_id = ?
                  AND booking_date = ?
                  AND status = 'confirmed'
                  AND ? < end_time
                  AND ? > start_time
                LIMIT 1;
                """,
                (room_id, booking_date, start_time, end_time),
            )
        return cursor.fetchone() is not None


def create_room_booking(
    student_id: str,
    student_name: str,
    room_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
    status: str = "confirmed",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a new library discussion room reservation after verifying room existence and slot availability.

    Args:
        student_id: Student roll/ID number.
        student_name: Full name of the student.
        room_id: ID of the discussion room being booked.
        booking_date: Date of booking ('YYYY-MM-DD').
        start_time: Start time ('HH:MM').
        end_time: End time ('HH:MM').
        status: Initial status, default 'confirmed'.
        db_path: Optional path to SQLite database.

    Returns:
        Dictionary containing all details of the newly created room reservation.

    Raises:
        ValueError: If parameters are invalid, room does not exist, or slot conflicts with an existing booking.
    """
    validate_time_range(start_time, end_time)

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()

        # Verify discussion room exists
        cursor.execute("SELECT room_id, room_name FROM discussion_rooms WHERE room_id = ?;", (room_id,))
        room = cursor.fetchone()
        if not room:
            raise ValueError(f"Discussion room with room_id={room_id} does not exist.")

        # Check for overlapping confirmed reservations
        cursor.execute(
            """
            SELECT booking_id, student_name, start_time, end_time
            FROM room_bookings
            WHERE room_id = ?
              AND booking_date = ?
              AND status = 'confirmed'
              AND ? < end_time
              AND ? > start_time
            LIMIT 1;
            """,
            (room_id, booking_date, start_time, end_time),
        )
        conflict = cursor.fetchone()
        if conflict:
            raise ValueError(
                f"Booking conflict: Room '{room['room_name']}' is already booked by "
                f"{conflict['student_name']} from {conflict['start_time']} to {conflict['end_time']}."
            )

        # Insert new room booking
        cursor.execute(
            """
            INSERT INTO room_bookings (student_id, student_name, room_id, booking_date, start_time, end_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (student_id.strip(), student_name.strip(), room_id, booking_date.strip(), start_time.strip(), end_time.strip(), status.strip()),
        )
        new_booking_id = cursor.lastrowid

        return {
            "booking_id": new_booking_id,
            "student_id": student_id.strip(),
            "student_name": student_name.strip(),
            "room_id": room_id,
            "room_name": room["room_name"],
            "booking_date": booking_date.strip(),
            "start_time": start_time.strip(),
            "end_time": end_time.strip(),
            "status": status.strip(),
        }


def get_all_student_reservations(student_id: str, student_name: str | None = None, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Retrieve all laboratory and library room reservations for a student strictly by their unique student_id."""
    clean_id = (student_id or "").strip()
    clean_name = (student_name or "").strip()
    
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        
        # Lab bookings
        if clean_id:
            cursor.execute(
                """
                SELECT b.booking_id, b.student_id, b.student_name, b.lab_id as facility_id,
                       l.lab_name as facility_name, l.location as location, 'Laboratory' as service_type,
                       b.booking_date, b.start_time, b.end_time, b.status
                FROM bookings b
                JOIN labs l ON b.lab_id = l.lab_id
                WHERE b.student_id = ?
                ORDER BY b.booking_date DESC, b.start_time DESC;
                """,
                (clean_id,),
            )
        else:
            cursor.execute(
                """
                SELECT b.booking_id, b.student_id, b.student_name, b.lab_id as facility_id,
                       l.lab_name as facility_name, l.location as location, 'Laboratory' as service_type,
                       b.booking_date, b.start_time, b.end_time, b.status
                FROM bookings b
                JOIN labs l ON b.lab_id = l.lab_id
                WHERE b.student_name = ?
                ORDER BY b.booking_date DESC, b.start_time DESC;
                """,
                (clean_name,),
            )
        lab_rows = [dict(row) for row in cursor.fetchall()]

        # Room bookings
        if clean_id:
            cursor.execute(
                """
                SELECT rb.booking_id, rb.student_id, rb.student_name, rb.room_id as facility_id,
                       r.room_name as facility_name, r.location as location, 'Library Room' as service_type,
                       rb.booking_date, rb.start_time, rb.end_time, rb.status
                FROM room_bookings rb
                JOIN discussion_rooms r ON rb.room_id = r.room_id
                WHERE rb.student_id = ?
                ORDER BY rb.booking_date DESC, rb.start_time DESC;
                """,
                (clean_id,),
            )
        else:
            cursor.execute(
                """
                SELECT rb.booking_id, rb.student_id, rb.student_name, rb.room_id as facility_id,
                       r.room_name as facility_name, r.location as location, 'Library Room' as service_type,
                       rb.booking_date, rb.start_time, rb.end_time, rb.status
                FROM room_bookings rb
                JOIN discussion_rooms r ON rb.room_id = r.room_id
                WHERE rb.student_name = ?
                ORDER BY rb.booking_date DESC, rb.start_time DESC;
                """,
                (clean_name,),
            )
        room_rows = [dict(row) for row in cursor.fetchall()]

        combined = lab_rows + room_rows
        combined.sort(key=lambda x: (x.get("booking_date", ""), x.get("start_time", "")), reverse=True)
        return combined


def get_student_profile(user_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Retrieve student profile by unique user_id."""
    clean_id = (user_id or "").strip()
    if not clean_id:
        return None
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, full_name, email, department, created_at, updated_at
            FROM student_profiles
            WHERE user_id = ?;
            """,
            (clean_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_student_profile_by_email(email: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Retrieve student profile by email address."""
    clean_email = (email or "").strip().lower()
    if not clean_email:
        return None
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, full_name, email, department, created_at, updated_at
            FROM student_profiles
            WHERE LOWER(email) = ?;
            """,
            (clean_email,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_student_profile(
    user_id: str,
    full_name: str,
    email: str,
    department: str = "Engineering & Technology",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Insert or update a student profile ensuring no duplicates during repeated sessions."""
    clean_id = (user_id or "").strip()
    clean_email = (email or "").strip().lower()
    clean_name = (full_name or "").strip()
    clean_dept = (department or "Engineering & Technology").strip()

    if not clean_id or not clean_email:
        raise ValueError("Both user_id and email are required for student profile.")

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, full_name, email, department
            FROM student_profiles
            WHERE user_id = ? OR LOWER(email) = ?;
            """,
            (clean_id, clean_email),
        )
        existing = cursor.fetchone()
        if existing:
            target_id = existing["user_id"]
            updated_name = clean_name if clean_name else existing["full_name"]
            cursor.execute(
                """
                UPDATE student_profiles
                SET full_name = ?,
                    email = ?,
                    department = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?;
                """,
                (updated_name, clean_email, clean_dept, target_id),
            )
            return {
                "user_id": target_id,
                "full_name": updated_name,
                "email": clean_email,
                "department": clean_dept,
            }
        else:
            cursor.execute(
                """
                INSERT INTO student_profiles (user_id, full_name, email, department)
                VALUES (?, ?, ?, ?);
                """,
                (clean_id, clean_name, clean_email, clean_dept),
            )
            return {
                "user_id": clean_id,
                "full_name": clean_name,
                "email": clean_email,
                "department": clean_dept,
            }



def cancel_reservation(booking_id: int, service_type: str = "Laboratory", db_path: str | Path | None = None) -> bool:
    """Cancel a booking by setting status = 'cancelled'."""
    table = "bookings" if "lab" in (service_type or "").lower() else "room_bookings"
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {table} SET status = 'cancelled' WHERE booking_id = ?;", (booking_id,))
        return cursor.rowcount > 0


def get_facility_details_by_id(facility_type: str, facility_id: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Retrieve detailed metadata for a lab or discussion room."""
    if "lab" in facility_type.lower():
        lab = get_laboratory_by_id(facility_id, db_path=db_path)
        if lab:
            lab["service_type"] = "Laboratory"
            equip_map = {
                1: ["40x Workstations", "Gigabit Ethernet", "Visual Studio Code", "Python 3.12", "Dual Projectors"],
                2: ["30x High-Perf GPUs", "NVIDIA RTX 4090", "PyTorch / TensorFlow", "JupyterHub", "Interactive Display"],
                3: ["35x Cisco Routers & Switches", "Packet Tracer", "Wireshark Workstations", "Fiber Patch Panels"],
            }
            lab["equipment"] = equip_map.get(facility_id, ["Standard Campus Computing Workstations", "LAN / Wi-Fi"])
            return lab
    else:
        room = get_discussion_room_by_id(facility_id, db_path=db_path)
        if room:
            room["service_type"] = "Library Room"
            amen_map = {
                1: ["Acoustic Wall Panels", "Whiteboard & Markers", "4x Ergonomic Chairs", "Power Outlets", "Campus Wi-Fi"],
                2: ["Acoustic Wall Panels", "55-inch Ultra-HD Screen", "Whiteboard", "6x Ergonomic Chairs", "HDMI / Type-C"],
                3: ["Conference Table", "Conference Web Camera", "8x Ergonomic Chairs", "Dual Whiteboards", "Presentation Screen"],
            }
            room["equipment"] = amen_map.get(facility_id, ["Whiteboard", "High-speed Wi-Fi", "Power Outlets"])
            return room
    return None


def recommend_matching_facilities(
    facility_type: str,
    booking_date: str,
    start_time: str,
    end_time: str,
    min_capacity: int = 1,
    purpose: str = "",
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Search and rank available facilities matching capacity and time requirements."""
    is_lab = "lab" in facility_type.lower() or "comp" in facility_type.lower() or "ai" in facility_type.lower()
    
    results = []
    if is_lab:
        labs = get_all_laboratories(db_path=db_path)
        for lab in labs:
            cap = lab["capacity"]
            has_conflict = check_booking_overlap(
                lab_id=lab["lab_id"],
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                db_path=db_path,
            )
            is_avail = not has_conflict
            is_cap_ok = cap >= min_capacity
            cap_diff = cap - min_capacity if is_cap_ok else min_capacity - cap
            
            if is_avail and is_cap_ok:
                badge = "Best Match" if cap_diff <= 10 else "Alternative"
                reason = f"Comfortably accommodates {min_capacity} students (Capacity: {cap}) and slot {start_time}-{end_time} on {booking_date} is 100% free."
            elif is_avail and not is_cap_ok:
                badge = "Insufficient Capacity"
                reason = f"Slot is available, but capacity is {cap} (less than requested {min_capacity})."
            else:
                badge = "Conflict"
                reason = f"Time slot {start_time}-{end_time} on {booking_date} is already booked."
                
            results.append({
                "facility_type": "lab",
                "service_type": "Laboratory",
                "facility_id": lab["lab_id"],
                "lab_id": lab["lab_id"],
                "room_id": None,
                "facility_name": lab["lab_name"],
                "capacity": cap,
                "location": lab.get("location", "Campus Building"),
                "booking_date": booking_date,
                "start_time": start_time,
                "end_time": end_time,
                "is_available": is_avail,
                "is_capacity_sufficient": is_cap_ok,
                "match_badge": badge,
                "match_reason": reason,
                "cap_diff": cap_diff if (is_avail and is_cap_ok) else 9999,
            })
    else:
        rooms = get_all_discussion_rooms(db_path=db_path)
        for room in rooms:
            cap = room["capacity"]
            has_conflict = check_room_booking_overlap(
                room_id=room["room_id"],
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                db_path=db_path,
            )
            is_avail = not has_conflict
            is_cap_ok = cap >= min_capacity
            cap_diff = cap - min_capacity if is_cap_ok else min_capacity - cap
            
            if is_avail and is_cap_ok:
                badge = "Best Match" if cap_diff <= 2 else "Alternative"
                reason = f"Accommodates {min_capacity} people (Capacity: {cap} seats) and slot {start_time}-{end_time} on {booking_date} is free."
            elif is_avail and not is_cap_ok:
                badge = "Insufficient Capacity"
                reason = f"Slot is available, but capacity is {cap} seats (less than requested {min_capacity})."
            else:
                badge = "Conflict"
                reason = f"Time slot {start_time}-{end_time} on {booking_date} is already reserved."
                
            results.append({
                "facility_type": "room",
                "service_type": "Library Room",
                "facility_id": room["room_id"],
                "lab_id": None,
                "room_id": room["room_id"],
                "facility_name": room["room_name"],
                "capacity": cap,
                "location": room.get("location", "Library Building"),
                "booking_date": booking_date,
                "start_time": start_time,
                "end_time": end_time,
                "is_available": is_avail,
                "is_capacity_sufficient": is_cap_ok,
                "match_badge": badge,
                "match_reason": reason,
                "cap_diff": cap_diff if (is_avail and is_cap_ok) else 9999,
            })
            
    # Sort results: available and sufficient capacity first, ordered by closest capacity fit
    results.sort(key=lambda x: (not (x["is_available"] and x["is_capacity_sufficient"]), x["cap_diff"]))
    return results



