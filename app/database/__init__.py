"""SQLite database module for CampusPilot AI.

Exports connection helpers, initialization, and core query/mutation operations.
"""

from app.database.connection import get_db_connection, get_db_context, get_db_path
from app.database.init_db import init_db
from app.database.operations import (
    check_booking_overlap,
    create_booking,
    get_all_laboratories,
    get_bookings_by_date,
    get_laboratory_by_id,
    validate_time_range,
)

__all__ = [
    "get_db_connection",
    "get_db_context",
    "get_db_path",
    "init_db",
    "get_all_laboratories",
    "get_laboratory_by_id",
    "get_bookings_by_date",
    "check_booking_overlap",
    "create_booking",
    "validate_time_range",
]
