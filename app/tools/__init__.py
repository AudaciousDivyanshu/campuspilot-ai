"""Campus service tools executing FastAPI HTTP requests."""

from app.tools.campus_tools import (
    ALL_CAMPUS_TOOLS,
    check_lab_availability,
    create_lab_booking,
    list_laboratories,
)

__all__ = [
    "ALL_CAMPUS_TOOLS",
    "list_laboratories",
    "check_lab_availability",
    "create_lab_booking",
]
