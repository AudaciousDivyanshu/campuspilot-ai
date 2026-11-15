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
                return f"AVAILABLE: Slot {start_time}-{end_time} on {booking_date} for Lab ID {lab_id} is free."
            else:
                return f"UNAVAILABLE: Slot {start_time}-{end_time} on {booking_date} for Lab ID {lab_id} is already booked."
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


# Export tools list
ALL_CAMPUS_TOOLS = [list_laboratories, check_lab_availability, create_lab_booking]
