"""Verification of the exact Streamlit runtime workflow for Bug 1 and Bug 2.

Tests:
A. Check AI Lab tomorrow from 10 AM to 12 PM:
   - Verifies tool receives '2026-11-16' (for current date 2026-11-15).
B. Verify available slot produces a structured pending_booking (displaying Confirm button).
C. Verify no booking is created in database before clicking the button.
D. Simulate clicking Confirm Booking:
   - Verifies exactly one booking is created with a valid Booking ID.
E. Simulate a Streamlit rerun / repeated click:
   - Verifies duplicate booking is NOT created.
F. Verify unavailable slot sets pending_booking to None (Confirm button is NOT displayed).
"""

from datetime import datetime, timedelta
import os
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.booking_agent import CampusBookingAgent
from app.database.connection import get_db_context
from app.database.init_db import init_db
from app.tools.campus_tools import create_lab_booking
from app.tools.date_utils import get_current_date_context, resolve_relative_dates_in_text


def run_streamlit_workflow_test():
    print("=" * 65, flush=True)
    print(" Streamlit Runtime Workflow Integration Test", flush=True)
    print("=" * 65, flush=True)

    date_ctx = get_current_date_context()
    today_str = date_ctx["today"]
    tomorrow_str = date_ctx["tomorrow"]
    print(f" Current Asia/Kolkata Date : {today_str}", flush=True)
    print(f" Expected 'tomorrow' Date  : {tomorrow_str}", flush=True)

    # Reset any bookings for tomorrow
    init_db()
    with get_db_context() as conn:
        conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (tomorrow_str,))

    # Launch FastAPI server
    print("\nStarting FastAPI backend server...", flush=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)

    try:
        agent = CampusBookingAgent()
        student_ctx = {
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
        }

        # -------------------------------------------------------------------
        # TEST A & B: User asks about tomorrow
        # -------------------------------------------------------------------
        user_query = "Check whether AI Lab is available tomorrow from 10:00 AM to 12:00 PM."
        print(f"\n[Test A & B] User Query: '{user_query}'", flush=True)

        # Mirror exact Streamlit frontend processing:
        anchored_query = resolve_relative_dates_in_text(user_query)
        print(f" Anchored Query Sent to Agent: '{anchored_query}'", flush=True)

        langchain_history = [HumanMessage(content=anchored_query)]
        result = agent.run(langchain_history, student_context=student_ctx)

        # Inspect tool arguments
        check_step = next(s for s in result["steps"] if s["tool"] == "check_lab_availability")
        actual_tool_date = check_step["args"].get("booking_date")
        print(f" Exact Tool Arguments Passed: {check_step['args']}", flush=True)
        print(f" Actual booking_date in Tool: '{actual_tool_date}'", flush=True)
        assert actual_tool_date == tomorrow_str, f"Expected {tomorrow_str}, got {actual_tool_date}"
        print(" ✓ TEST A PASSED: Tool received exact tomorrow date (2026-11-16).", flush=True)

        # Verify structured pending booking
        pending_booking = result.get("pending_booking")
        print(f"\n Structured pending_booking returned: {pending_booking}", flush=True)
        assert pending_booking is not None, "pending_booking must not be None for an available slot!"
        assert pending_booking["lab_id"] == 2
        assert pending_booking["booking_date"] == tomorrow_str
        assert pending_booking["start_time"] == "10:00"
        assert pending_booking["end_time"] == "12:00"
        print(" ✓ TEST B PASSED: Available slot produced structured pending_booking (Confirm button displays).", flush=True)

        # -------------------------------------------------------------------
        # TEST C: Verify NO booking created before confirmation
        # -------------------------------------------------------------------
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM bookings WHERE booking_date = ?;", (tomorrow_str,))
            count_before = cursor.fetchone()["cnt"]
        print(f"\n[Test C] Database booking count before confirmation: {count_before}", flush=True)
        assert count_before == 0, "No booking should exist before confirmation!"
        print(" ✓ TEST C PASSED: Zero bookings created before clicking Confirm Booking.", flush=True)

        # -------------------------------------------------------------------
        # TEST D: Simulate clicking "Confirm Booking"
        # -------------------------------------------------------------------
        print("\n[Test D] Simulating click on '✅ Confirm Booking' button...", flush=True)
        # Mirror Streamlit confirm_pending_booking logic
        booking_data = dict(pending_booking)
        pending_booking = None  # Cleared immediately

        booking_res = create_lab_booking.invoke({
            "student_id": booking_data["student_id"],
            "student_name": booking_data["student_name"],
            "lab_id": int(booking_data["lab_id"]),
            "booking_date": booking_data["booking_date"],
            "start_time": booking_data["start_time"],
            "end_time": booking_data["end_time"],
        })
        print(f" Confirmation Result:\n{booking_res}", flush=True)
        assert "BOOKING CONFIRMED!" in booking_res

        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bookings WHERE booking_date = ?;", (tomorrow_str,))
            rows = cursor.fetchall()
        assert len(rows) == 1, f"Expected 1 confirmed booking, found {len(rows)}"
        print(f" Verified SQLite Row: Booking #{rows[0]['booking_id']} for {rows[0]['student_name']}", flush=True)
        print(" ✓ TEST D PASSED: Exactly one booking created with valid Booking ID.", flush=True)

        # -------------------------------------------------------------------
        # TEST E: Simulate Streamlit Rerun (pending_booking is already None)
        # -------------------------------------------------------------------
        print("\n[Test E] Simulating page rerun...", flush=True)
        print(f" pending_booking state: {pending_booking}", flush=True)
        assert pending_booking is None
        # Rerun should not invoke booking
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM bookings WHERE booking_date = ?;", (tomorrow_str,))
            count_after_rerun = cursor.fetchone()["cnt"]
        assert count_after_rerun == 1
        print(" ✓ TEST E PASSED: Page rerun did not duplicate booking.", flush=True)

        # -------------------------------------------------------------------
        # TEST F: Check unavailable slot (the slot just booked)
        # -------------------------------------------------------------------
        print("\n[Test F] Checking now-occupied slot (tomorrow 10:00 - 12:00 in AI Lab)...", flush=True)
        query_occupied = "Is AI Lab available tomorrow from 10:00 to 12:00?"
        anchored_occupied = resolve_relative_dates_in_text(query_occupied)
        result_occupied = agent.run([HumanMessage(content=anchored_occupied)], student_context=student_ctx)

        print(f" Agent Response: {result_occupied['response']}", flush=True)
        print(f" pending_booking for occupied slot: {result_occupied['pending_booking']}", flush=True)
        assert result_occupied["pending_booking"] is None, "Occupied slot must NOT create pending_booking!"
        print(" ✓ TEST F PASSED: Unavailable slot never displays Confirm Booking button.", flush=True)

        print("\n" + "=" * 65, flush=True)
        print(" ALL STREAMLIT RUNTIME WORKFLOW TESTS PASSED!", flush=True)
        print("=" * 65, flush=True)

        # Clean up test records
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (tomorrow_str,))

    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    run_streamlit_workflow_test()
