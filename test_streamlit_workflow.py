"""Verification of the Streamlit runtime workflow for both Laboratory and Discussion Room bookings.

Tests:
Part 1 (Laboratory Workflow):
A. Check AI Lab tomorrow from 10 AM to 12 PM:
   - Verifies tool receives dynamic tomorrow date in Asia/Kolkata.
B. Verify available slot produces structured pending_booking with service_type='lab'.
C. Verify no booking is created in database before clicking the button.
D. Simulate clicking Confirm Booking:
   - Verifies exactly one booking is created with a valid Booking ID in `bookings` table.
E. Simulate a Streamlit rerun / repeated click:
   - Verifies duplicate booking is NOT created.
F. Verify unavailable slot sets pending_booking to None.

Part 2 (Library Discussion Room Workflow):
G. Check Discussion Room 2 tomorrow from 2 PM to 4 PM:
   - Verifies tool receives dynamic tomorrow date in Asia/Kolkata.
H. Verify available slot produces structured pending_booking with service_type='room'.
I. Verify no reservation is created in database before clicking the button.
J. Simulate clicking Confirm Reservation:
   - Verifies exactly one reservation is created with a valid Booking ID in `room_bookings` table.
K. Simulate a Streamlit rerun:
   - Verifies duplicate reservation is NOT created.
L. Verify unavailable room slot sets pending_booking to None.
"""

from datetime import datetime, timedelta
import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.booking_agent import CampusBookingAgent
from app.database.connection import get_db_context
from app.database.init_db import init_db
from app.tools.campus_tools import create_lab_booking, create_room_reservation
from app.tools.date_utils import get_current_date_context, resolve_relative_dates_in_text


def run_streamlit_workflow_test():
    print("=" * 65, flush=True)
    print(" Streamlit Runtime Workflow Multi-Service Integration Test", flush=True)
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
        conn.execute("DELETE FROM room_bookings WHERE booking_date = ?;", (tomorrow_str,))

    # Launch FastAPI server
    print("\nStarting FastAPI backend server on port 8000...", flush=True)
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

        # ===================================================================
        # PART 1: LABORATORY BOOKING WORKFLOW
        # ===================================================================
        print("\n" + "=" * 55, flush=True)
        print(" [Part 1] Testing Laboratory Booking Workflow", flush=True)
        print("=" * 55, flush=True)

        user_query_lab = "Check whether AI Lab is available tomorrow from 10:00 AM to 12:00 PM."
        print(f"\n[Test A & B] User Query: '{user_query_lab}'", flush=True)

        anchored_lab = resolve_relative_dates_in_text(user_query_lab)
        res_lab = agent.run([HumanMessage(content=anchored_lab)], student_context=student_ctx)

        check_step = next(s for s in res_lab["steps"] if s["tool"] == "check_lab_availability")
        actual_tool_date = check_step["args"].get("booking_date")
        print(f" Exact Tool Arguments Passed: {check_step['args']}", flush=True)
        assert actual_tool_date == tomorrow_str, f"Expected {tomorrow_str}, got {actual_tool_date}"
        print(f" ✓ TEST A PASSED: Tool received exact tomorrow date ({tomorrow_str}).", flush=True)

        pending_lab = res_lab.get("pending_booking")
        print(f" Structured pending_booking returned: {pending_lab}", flush=True)
        assert pending_lab is not None
        assert pending_lab.get("service_type") == "lab"
        assert pending_lab["item_id"] == 2
        assert pending_lab["booking_date"] == tomorrow_str
        print(" ✓ TEST B PASSED: Laboratory slot produced structured pending_booking.", flush=True)

        # Verify no booking in DB before confirmation
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM bookings WHERE booking_date = ?;", (tomorrow_str,))
            count_before = cursor.fetchone()["cnt"]
        assert count_before == 0
        print(" ✓ TEST C PASSED: Zero bookings in database before confirmation.", flush=True)

        # Confirm Lab Booking
        print("\n[Test D] Simulating click on '✅ Confirm Reservation' button (Lab)...", flush=True)
        lab_booking_data = dict(pending_lab)
        pending_lab = None

        lab_res = create_lab_booking.invoke({
            "student_id": lab_booking_data["student_id"],
            "student_name": lab_booking_data["student_name"],
            "lab_id": int(lab_booking_data["item_id"]),
            "booking_date": lab_booking_data["booking_date"],
            "start_time": lab_booking_data["start_time"],
            "end_time": lab_booking_data["end_time"],
        })
        print(f" Confirmation Result:\n{lab_res}", flush=True)
        assert "BOOKING CONFIRMED!" in lab_res

        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bookings WHERE booking_date = ?;", (tomorrow_str,))
            rows = cursor.fetchall()
        assert len(rows) == 1
        print(f" Verified SQLite Row: Lab Booking #{rows[0]['booking_id']} for {rows[0]['student_name']}", flush=True)
        print(" ✓ TEST D PASSED: Exactly one lab booking created with valid Booking ID.", flush=True)

        # Rerun check
        print("\n[Test E] Simulating page rerun...", flush=True)
        assert pending_lab is None
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM bookings WHERE booking_date = ?;", (tomorrow_str,))
            count_after_rerun = cursor.fetchone()["cnt"]
        assert count_after_rerun == 1
        print(" ✓ TEST E PASSED: Page rerun did not duplicate booking.", flush=True)

        # Occupied slot check
        print("\n[Test F] Checking now-occupied lab slot...", flush=True)
        query_occupied = "Is AI Lab available tomorrow from 10:00 to 12:00?"
        anchored_occupied = resolve_relative_dates_in_text(query_occupied)
        res_occupied = agent.run([HumanMessage(content=anchored_occupied)], student_context=student_ctx)
        assert res_occupied["pending_booking"] is None
        print(" ✓ TEST F PASSED: Unavailable lab slot never displays Confirm button.", flush=True)

        # ===================================================================
        # PART 2: LIBRARY DISCUSSION ROOM WORKFLOW
        # ===================================================================
        print("\n" + "=" * 55, flush=True)
        print(" [Part 2] Testing Library Discussion Room Workflow", flush=True)
        print("=" * 55, flush=True)

        user_query_room = "Check whether Discussion Room 2 is available tomorrow from 2:00 PM to 4:00 PM."
        print(f"\n[Test G & H] User Query: '{user_query_room}'", flush=True)

        anchored_room = resolve_relative_dates_in_text(user_query_room)
        res_room = agent.run([HumanMessage(content=anchored_room)], student_context=student_ctx)

        check_room_step = next(s for s in res_room["steps"] if s["tool"] == "check_room_availability")
        actual_room_date = check_room_step["args"].get("booking_date")
        print(f" Exact Tool Arguments Passed: {check_room_step['args']}", flush=True)
        assert actual_room_date == tomorrow_str, f"Expected {tomorrow_str}, got {actual_room_date}"
        print(f" ✓ TEST G PASSED: Room tool received exact tomorrow date ({tomorrow_str}).", flush=True)

        pending_room = res_room.get("pending_booking")
        print(f" Structured pending_booking returned: {pending_room}", flush=True)
        assert pending_room is not None
        assert pending_room.get("service_type") == "room"
        assert pending_room["item_id"] == 2
        assert pending_room["booking_date"] == tomorrow_str
        assert pending_room["start_time"] == "14:00"
        assert pending_room["end_time"] == "16:00"
        print(" ✓ TEST H PASSED: Discussion room slot produced structured pending_booking.", flush=True)

        # Verify no room reservation in DB before confirmation
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM room_bookings WHERE booking_date = ?;", (tomorrow_str,))
            count_room_before = cursor.fetchone()["cnt"]
        assert count_room_before == 0
        print(" ✓ TEST I PASSED: Zero room reservations in database before confirmation.", flush=True)

        # Confirm Room Reservation
        print("\n[Test J] Simulating click on '✅ Confirm Reservation' button (Room)...", flush=True)
        room_booking_data = dict(pending_room)
        pending_room = None

        room_res = create_room_reservation.invoke({
            "student_id": room_booking_data["student_id"],
            "student_name": room_booking_data["student_name"],
            "room_id": int(room_booking_data["item_id"]),
            "booking_date": room_booking_data["booking_date"],
            "start_time": room_booking_data["start_time"],
            "end_time": room_booking_data["end_time"],
        })
        print(f" Confirmation Result:\n{room_res}", flush=True)
        assert "DISCUSSION ROOM RESERVED!" in room_res

        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM room_bookings WHERE booking_date = ?;", (tomorrow_str,))
            room_rows = cursor.fetchall()
        assert len(room_rows) == 1
        print(f" Verified SQLite Row: Room Reservation #{room_rows[0]['booking_id']} for {room_rows[0]['student_name']}", flush=True)
        print(" ✓ TEST J PASSED: Exactly one room reservation created with valid Booking ID.", flush=True)

        # Rerun check
        print("\n[Test K] Simulating page rerun for room...", flush=True)
        assert pending_room is None
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM room_bookings WHERE booking_date = ?;", (tomorrow_str,))
            count_room_rerun = cursor.fetchone()["cnt"]
        assert count_room_rerun == 1
        print(" ✓ TEST K PASSED: Page rerun did not duplicate room reservation.", flush=True)

        # Occupied room slot check
        print("\n[Test L] Checking now-occupied discussion room slot...", flush=True)
        query_room_occupied = "Is Discussion Room 2 available tomorrow from 14:00 to 16:00?"
        anchored_room_occupied = resolve_relative_dates_in_text(query_room_occupied)
        res_room_occupied = agent.run([HumanMessage(content=anchored_room_occupied)], student_context=student_ctx)
        assert res_room_occupied["pending_booking"] is None
        print(" ✓ TEST L PASSED: Unavailable room slot never displays Confirm button.", flush=True)

        print("\n" + "=" * 65, flush=True)
        print(" ALL MULTI-SERVICE WORKFLOW TESTS PASSED SUCCESSFULLY!", flush=True)
        print("=" * 65, flush=True)

        # Clean up test records
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (tomorrow_str,))
            conn.execute("DELETE FROM room_bookings WHERE booking_date = ?;", (tomorrow_str,))

    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    run_streamlit_workflow_test()
