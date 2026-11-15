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

