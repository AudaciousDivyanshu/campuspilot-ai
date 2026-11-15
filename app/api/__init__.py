"""FastAPI API routes and schemas."""

from app.api.routes import router
from app.api.schemas import (
    AvailabilityResponse,
    BookingCreateRequest,
    BookingResponse,
    HealthResponse,
    LabResponse,
)

__all__ = [
    "router",
    "HealthResponse",
    "LabResponse",
    "BookingResponse",
    "AvailabilityResponse",
    "BookingCreateRequest",
]
