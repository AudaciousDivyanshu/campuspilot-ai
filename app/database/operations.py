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
            SELECT lab_id, lab_name, capacity, location, is_enabled
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
            SELECT lab_id, lab_name, capacity, location, is_enabled
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
                  AND status IN ('confirmed', 'approved')
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
                  AND status IN ('confirmed', 'approved')
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
    purpose: str = "",
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
        status: Initial status, default 'confirmed' (or 'pending').
        purpose: Academic purpose of the session.
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

        # Check for overlapping confirmed or approved bookings
        cursor.execute(
            """
            SELECT booking_id, student_name, start_time, end_time
            FROM bookings
            WHERE lab_id = ?
              AND booking_date = ?
              AND status IN ('confirmed', 'approved')
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
            INSERT INTO bookings (student_id, student_name, lab_id, booking_date, start_time, end_time, status, purpose)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (student_id.strip(), student_name.strip(), lab_id, booking_date.strip(), start_time.strip(), end_time.strip(), status.strip(), purpose.strip()),
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
            "purpose": purpose.strip(),
            "rejection_reason": "",
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
            SELECT room_id, room_name, capacity, location, is_enabled
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
            SELECT room_id, room_name, capacity, location, is_enabled
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
                  AND status IN ('confirmed', 'approved')
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
                  AND status IN ('confirmed', 'approved')
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
    purpose: str = "",
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
        status: Initial status, default 'confirmed' (or 'pending').
        purpose: Academic or collaborative study purpose.
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

        # Check for overlapping confirmed or approved reservations
        cursor.execute(
            """
            SELECT booking_id, student_name, start_time, end_time
            FROM room_bookings
            WHERE room_id = ?
              AND booking_date = ?
              AND status IN ('confirmed', 'approved')
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
            INSERT INTO room_bookings (student_id, student_name, room_id, booking_date, start_time, end_time, status, purpose)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (student_id.strip(), student_name.strip(), room_id, booking_date.strip(), start_time.strip(), end_time.strip(), status.strip(), purpose.strip()),
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
            "purpose": purpose.strip(),
            "rejection_reason": "",
        }


def get_all_student_reservations(student_id: str, student_name: str | None = None, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Retrieve all laboratory and library room reservations for a student strictly by their unique user/student ID."""
    clean_id = (student_id or "").strip()
    if not clean_id:
        return []

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()

        # Lab bookings strictly isolated by owner ID
        cursor.execute(
            """
            SELECT b.booking_id, b.student_id, b.student_name, b.lab_id as facility_id,
                   l.lab_name as facility_name, l.location as location, 'Laboratory' as service_type,
                   b.booking_date, b.start_time, b.end_time, b.status,
                   b.purpose, b.rejection_reason, b.created_at
            FROM bookings b
            JOIN labs l ON b.lab_id = l.lab_id
            WHERE b.student_id = ?
            ORDER BY b.booking_date DESC, b.start_time DESC;
            """,
            (clean_id,),
        )
        lab_rows = [dict(row) for row in cursor.fetchall()]

        # Room bookings strictly isolated by owner ID
        cursor.execute(
            """
            SELECT rb.booking_id, rb.student_id, rb.student_name, rb.room_id as facility_id,
                   r.room_name as facility_name, r.location as location, 'Library Room' as service_type,
                   rb.booking_date, rb.start_time, rb.end_time, rb.status,
                   rb.purpose, rb.rejection_reason, rb.created_at
            FROM room_bookings rb
            JOIN discussion_rooms r ON rb.room_id = r.room_id
            WHERE rb.student_id = ?
            ORDER BY rb.booking_date DESC, rb.start_time DESC;
            """,
            (clean_id,),
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


def get_user_account_by_email(email: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Retrieve user account record from SQLite user_accounts by email."""
    clean_email = (email or "").strip().lower()
    if not clean_email:
        return None
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, email, password_hash, full_name, display_name,
                   account_type, student_id, university, department, avatar, created_at, updated_at
            FROM user_accounts
            WHERE LOWER(email) = ?;
            """,
            (clean_email,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_user_account(user_dict: dict[str, Any], db_path: str | Path | None = None) -> bool:
    """Insert or update user account record in SQLite user_accounts table."""
    user_id = user_dict.get("user_id")
    email = (user_dict.get("email") or "").strip().lower()
    pwd_hash = user_dict.get("password_hash", "")
    full_name = user_dict.get("full_name", "")
    display_name = user_dict.get("display_name") or full_name
    account_type = user_dict.get("account_type", "Student")
    student_id = user_dict.get("student_id", "")
    university = user_dict.get("university", "Lovely Professional University")
    department = user_dict.get("department", "Engineering & Technology")
    avatar = user_dict.get("avatar", "👨‍🎓" if account_type != "Administrator" else "🛡️")

    if not user_id or not email or not pwd_hash:
        return False

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_accounts (
                user_id, email, password_hash, full_name, display_name,
                account_type, student_id, university, department, avatar, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                email = excluded.email,
                password_hash = excluded.password_hash,
                full_name = excluded.full_name,
                display_name = excluded.display_name,
                account_type = excluded.account_type,
                student_id = excluded.student_id,
                university = excluded.university,
                department = excluded.department,
                avatar = excluded.avatar,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (user_id, email, pwd_hash, full_name, display_name, account_type, student_id, university, department, avatar),
        )
        return True



def cancel_reservation(
    booking_id: int,
    service_type: str = "Laboratory",
    owner_id: str | None = None,
    is_admin: bool = False,
    db_path: str | Path | None = None,
) -> bool:
    """Cancel a booking by setting status = 'cancelled'. Enforces owner_id unless is_admin=True."""
    table = "bookings" if "lab" in (service_type or "").lower() else "room_bookings"
    clean_owner = (owner_id or "").strip()
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        if not is_admin and owner_id is not None:
            if not clean_owner:
                return False
            cursor.execute(
                f"UPDATE {table} SET status = 'cancelled' WHERE booking_id = ? AND student_id = ?;",
                (booking_id, clean_owner),
            )
        else:
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


# ==========================================
# ADMINISTRATIVE WORKFLOW OPERATIONS
# ==========================================

def get_all_booking_requests(
    status_filter: str | None = None,
    service_filter: str | None = None,
    include_rooms: bool = False,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Retrieve booking requests for administrator approval.

    Per CampusPilot AI policy:
    - Discussion-room reservations are self-service student bookings and do NOT appear in the administrator approval queue.
    - Only laboratory booking requests appear in the administrator's review queue by default.
    - Discussion rooms are only returned if include_rooms=True or service_filter specifies Library Room.
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()

        # Labs
        cursor.execute(
            """
            SELECT b.booking_id, b.student_id, b.student_name, b.lab_id as facility_id,
                   l.lab_name as facility_name, l.location as location, 'Laboratory' as service_type,
                   b.booking_date, b.start_time, b.end_time, b.status,
                   b.purpose, b.rejection_reason, b.created_at,
                   COALESCE(
                       (SELECT sp.department FROM student_profiles sp 
                        WHERE sp.user_id = b.student_id OR sp.full_name = b.student_name 
                        ORDER BY sp.updated_at DESC LIMIT 1),
                       'Computer Science & Engineering'
                   ) as department
            FROM bookings b
            JOIN labs l ON b.lab_id = l.lab_id
            ORDER BY b.booking_date DESC, b.start_time DESC;
            """
        )
        lab_requests = [dict(row) for row in cursor.fetchall()]

        # Rooms are strictly excluded from admin approval queue unless explicitly queried
        room_requests = []
        if include_rooms or (service_filter and "room" in service_filter.lower()):
            cursor.execute(
                """
                SELECT rb.booking_id, rb.student_id, rb.student_name, rb.room_id as facility_id,
                       r.room_name as facility_name, r.location as location, 'Library Room' as service_type,
                       rb.booking_date, rb.start_time, rb.end_time, rb.status,
                       rb.purpose, rb.rejection_reason, rb.created_at,
                       COALESCE(
                           (SELECT sp.department FROM student_profiles sp 
                            WHERE sp.user_id = rb.student_id OR sp.full_name = rb.student_name 
                            ORDER BY sp.updated_at DESC LIMIT 1),
                           'General Engineering'
                       ) as department
                FROM room_bookings rb
                JOIN discussion_rooms r ON rb.room_id = r.room_id
                ORDER BY rb.booking_date DESC, rb.start_time DESC;
                """
            )
            room_requests = [dict(row) for row in cursor.fetchall()]

        all_requests = lab_requests + room_requests

        # Ensure strict deduplication by (service_type, booking_id)
        seen_keys = set()
        deduped_requests = []
        for req in all_requests:
            key = (req.get("service_type"), req.get("booking_id"))
            if key not in seen_keys:
                seen_keys.add(key)
                deduped_requests.append(req)
        all_requests = deduped_requests

        if status_filter:
            sf = status_filter.strip().lower()
            all_requests = [r for r in all_requests if r.get("status", "").strip().lower() == sf]

        if service_filter:
            srv = service_filter.strip().lower()
            all_requests = [r for r in all_requests if srv in r.get("service_type", "").lower()]

        all_requests.sort(key=lambda x: (x.get("booking_date", ""), x.get("start_time", "")), reverse=True)
        return all_requests


def approve_booking(
    booking_id: int,
    service_type: str = "Laboratory",
    db_path: str | Path | None = None,
) -> tuple[bool, str]:
    """Approve a pending booking request after verifying no conflicting approved booking exists."""
    is_lab = "lab" in (service_type or "").lower()
    table = "bookings" if is_lab else "room_bookings"
    id_col = "lab_id" if is_lab else "room_id"

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT booking_id, {id_col}, booking_date, start_time, end_time, student_name, status FROM {table} WHERE booking_id = ?;",
            (booking_id,),
        )
        req = cursor.fetchone()
        if not req:
            return False, f"Request #{booking_id} does not exist in {table}."

        cur_status = (req["status"] or "").lower()
        if cur_status in ("approved", "confirmed"):
            return False, f"Request #{booking_id} has already been approved."
        if cur_status == "rejected":
            return False, f"Request #{booking_id} cannot be approved because it has already been rejected."

        target_facility_id = req[id_col]
        target_date = req["booking_date"]
        start_time = req["start_time"]
        end_time = req["end_time"]

        # Conflict verification against other confirmed or approved bookings
        if is_lab:
            has_conflict = check_booking_overlap(
                lab_id=target_facility_id,
                booking_date=target_date,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=booking_id,
                db_path=db_path,
            )
        else:
            has_conflict = check_room_booking_overlap(
                room_id=target_facility_id,
                booking_date=target_date,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=booking_id,
                db_path=db_path,
            )

        if has_conflict:
            return False, f"Cannot approve: A confirmed/approved booking already occupies {target_date} ({start_time} - {end_time})."

        cursor.execute(
            f"UPDATE {table} SET status = 'approved', rejection_reason = '' WHERE booking_id = ?;",
            (booking_id,),
        )
        return True, f"Request #{booking_id} successfully approved and confirmed in schedule."


def reject_booking(
    booking_id: int,
    service_type: str = "Laboratory",
    rejection_reason: str = "Declined by department administrator",
    db_path: str | Path | None = None,
) -> bool:
    """Reject a booking request and record the rejection reason for the student."""
    table = "bookings" if "lab" in (service_type or "").lower() else "room_bookings"
    reason = rejection_reason.strip() or "Declined by department administrator"
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT status FROM {table} WHERE booking_id = ?;", (booking_id,))
        row = cursor.fetchone()
        if not row:
            return False
        cur_st = (row["status"] or "").lower()
        if cur_st == "rejected" or cur_st in ("approved", "confirmed"):
            return False

        cursor.execute(
            f"UPDATE {table} SET status = 'rejected', rejection_reason = ? WHERE booking_id = ?;",
            (reason, booking_id),
        )
        return cursor.rowcount > 0


def toggle_facility_status(
    facility_type: str,
    facility_id: int,
    is_enabled: int,
    db_path: str | Path | None = None,
) -> bool:
    """Enable or disable facility booking by administrators."""
    table = "labs" if "lab" in (facility_type or "").lower() else "discussion_rooms"
    col = "lab_id" if "lab" in (facility_type or "").lower() else "room_id"
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE {table} SET is_enabled = ? WHERE {col} = ?;",
            (1 if is_enabled else 0, facility_id),
        )
        return cursor.rowcount > 0


def get_admin_dashboard_metrics(db_path: str | Path | None = None) -> dict[str, Any]:
    """Calculate administrative metrics based on actual SQLite database records."""
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()

        # Lab stats
        cursor.execute("SELECT status, count(*) as count FROM bookings GROUP BY status;")
        lab_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

        # Room stats
        cursor.execute("SELECT status, count(*) as count FROM room_bookings GROUP BY status;")
        room_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

        # Facilities
        cursor.execute("SELECT count(*) as total, sum(CASE WHEN is_enabled = 1 THEN 1 ELSE 0 END) as active FROM labs;")
        lab_fac = cursor.fetchone()

        cursor.execute("SELECT count(*) as total, sum(CASE WHEN is_enabled = 1 THEN 1 ELSE 0 END) as active FROM discussion_rooms;")
        room_fac = cursor.fetchone()

        # Leave stats
        cursor.execute("SELECT status, count(*) as count FROM leave_requests GROUP BY status;")
        leave_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
        pending_leaves_count = sum(c for st, c in leave_counts.items() if "pending" in (st or "").lower())
        approved_leaves_count = sum(c for st, c in leave_counts.items() if "approved" in (st or "").lower())
        rejected_leaves_count = sum(c for st, c in leave_counts.items() if "rejected" in (st or "").lower())

        total_pending = lab_counts.get("pending", 0) + room_counts.get("pending", 0)
        total_approved = (
            lab_counts.get("approved", 0) + lab_counts.get("confirmed", 0) +
            room_counts.get("approved", 0) + room_counts.get("confirmed", 0)
        )
        total_rejected = lab_counts.get("rejected", 0) + room_counts.get("rejected", 0)
        total_cancelled = lab_counts.get("cancelled", 0) + room_counts.get("cancelled", 0)
        total_all = total_pending + total_approved + total_rejected + total_cancelled

        return {
            "total_requests": total_all,
            "pending_requests": total_pending,
            "approved_requests": total_approved,
            "rejected_requests": total_rejected,
            "cancelled_requests": total_cancelled,
            "pending_leaves": pending_leaves_count,
            "approved_leaves": approved_leaves_count,
            "rejected_leaves": rejected_leaves_count,
            "total_laboratories": lab_fac["total"] if lab_fac else 0,
            "active_laboratories": lab_fac["active"] if (lab_fac and lab_fac["active"] is not None) else 0,
            "total_rooms": room_fac["total"] if room_fac else 0,
            "active_rooms": room_fac["active"] if (room_fac and room_fac["active"] is not None) else 0,
        }


# ==========================================
# LEAVE REQUEST OPERATIONS (ADMINISTRATOR REVIEW)
# ==========================================

def create_leave_request(
    student_id: str,
    student_name: str,
    student_email: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    reason: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Submit a student leave request. All leave requests require administrator review."""
    clean_id = student_id.strip()
    clean_name = student_name.strip()
    clean_email = student_email.strip().lower()
    clean_type = leave_type.strip()
    s_date = start_date.strip()
    e_date = end_date.strip()
    clean_reason = reason.strip()

    if not clean_id or not clean_name:
        raise ValueError("Student identity is required for leave submission.")
    if not s_date or not e_date or not clean_reason:
        raise ValueError("Start date, end date, and reason are required.")
    if s_date > e_date:
        raise ValueError(f"Start date '{s_date}' cannot be later than end date '{e_date}'.")

    # Critical requirement: Every student leave request must first be reviewed by the Administrator
    status = "Pending Approval"

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO leave_requests (student_id, student_name, student_email, leave_type, start_date, end_date, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (clean_id, clean_name, clean_email, clean_type, s_date, e_date, clean_reason, status),
        )
        leave_id = cursor.lastrowid
        return {
            "leave_id": leave_id,
            "student_id": clean_id,
            "student_name": clean_name,
            "student_email": clean_email,
            "leave_type": clean_type,
            "start_date": s_date,
            "end_date": e_date,
            "reason": clean_reason,
            "status": status,
        }


def update_leave_status(
    leave_id: int,
    status: str,
    rejection_reason: str = "",
    reviewed_by: str = "",
    db_path: str | Path | None = None,
) -> bool:
    """Update student leave request status in SQLite ('Approved', 'Rejected', etc.) with reviewer audit info."""
    clean_status = (status or "").strip()
    clean_reason = (rejection_reason or "").strip()
    clean_reviewer = (reviewed_by or "").strip()

    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM leave_requests WHERE leave_id = ?;", (leave_id,))
        row = cursor.fetchone()
        if not row:
            return False
        cur_st = (row["status"] or "").lower()
        if cur_st in ("approved", "rejected") and cur_st == clean_status.lower():
            return False

        cursor.execute(
            """
            UPDATE leave_requests
            SET status = ?,
                rejection_reason = ?,
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE leave_id = ?;
            """,
            (clean_status, clean_reason, clean_reviewer, leave_id),
        )
        return cursor.rowcount > 0


def get_student_leave_requests(student_id: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Retrieve all leave requests for a given student."""
    clean_id = (student_id or "").strip()
    if not clean_id:
        return []
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT leave_id, student_id, student_name, student_email, leave_type,
                   start_date, end_date, reason, status, rejection_reason, reviewed_by, reviewed_at, created_at
            FROM leave_requests
            WHERE student_id = ?
            ORDER BY created_at DESC;
            """,
            (clean_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_leave_requests(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Retrieve all leave requests for administrative oversight."""
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT leave_id, student_id, student_name, student_email, leave_type,
                   start_date, end_date, reason, status, rejection_reason, reviewed_by, reviewed_at, created_at
            FROM leave_requests
            ORDER BY created_at DESC;
            """
        )
        return [dict(row) for row in cursor.fetchall()]



