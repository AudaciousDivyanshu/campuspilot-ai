"""CampusPilot AI - FastAPI Application Entry Point.

Serves RESTful endpoints connected directly to the local SQLite campus database.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database tables and sample laboratories exist when application starts."""
    init_db()
    yield


app = FastAPI(
    title="CampusPilot AI API",
    version="1.0.0",
    description="Agentic AI Assistant Backend - Lab Booking & Multi-Step Campus Services",
    lifespan=lifespan,
)

# Enable CORS for local Streamlit frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_router)


@app.get("/", tags=["Root"])
def root():
    """Root endpoint welcoming users and directing to interactive documentation."""
    return {
        "message": "Welcome to CampusPilot AI API",
        "documentation": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

