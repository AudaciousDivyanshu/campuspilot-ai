"""Test script for CampusPilot AI campus tools (Laboratory & Discussion Room).

Verifies:
1. list_laboratories tool
2. list_discussion_rooms tool
3. check_lab_availability tool
4. check_room_availability tool
5. create_lab_booking tool
6. create_room_reservation tool
7. Conflict detection through tools
8. Relative date resolution through tools
"""

from pathlib import Path
import os
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

TEST_PORT = 8009
os.environ["BACKEND_URL"] = f"http://127.0.0.1:{TEST_PORT}"

import app.tools.campus_tools as ct
from app.database.connection import get_db_context
from app.database.init_db import init_db
from app.tools.date_utils import get_current_date_context


def run_tool_tests():
    print("=" * 65, flush=True)
    print(" CampusPilot AI: Campus Tools Multi-Service Verification", flush=True)
    print("=" * 65, flush=True)

    init_db()
    date_ctx = get_current_date_context()
    tomorrow_str = date_ctx["tomorrow"]
    test_date = tomorrow_str

    # Clean up test date records
    with get_db_context() as conn:
        conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))
        conn.execute("DELETE FROM room_bookings WHERE booking_date = ?;", (test_date,))

    # Launch isolated Uvicorn server instance
    print(f"Launching FastAPI backend on port {TEST_PORT}...", flush=True)
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(TEST_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)

    try:
        # Update BASE_URL in campus_tools
        ct.BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

        # 1. list_laboratories
        print("\n[Tool 1] list_laboratories", flush=True)
        labs_out = ct.list_laboratories.invoke({})
        print(labs_out, flush=True)
        assert "Computer Lab 1" in labs_out
        assert "AI Lab" in labs_out
        assert "Networking Lab" in labs_out
        print("   ✓ list_laboratories passed", flush=True)

        # 2. list_discussion_rooms
        print("\n[Tool 2] list_discussion_rooms", flush=True)
        rooms_out = ct.list_discussion_rooms.invoke({})
        print(rooms_out, flush=True)
        assert "Discussion Room 1" in rooms_out
        assert "Discussion Room 2" in rooms_out
        assert "Discussion Room 3" in rooms_out
        print("   ✓ list_discussion_rooms passed", flush=True)

        # 3. check_lab_availability (using relative term 'tomorrow')
        print("\n[Tool 3] check_lab_availability with 'tomorrow'", flush=True)
        avail_lab = ct.check_lab_availability.invoke({
            "lab_id": 2,
            "booking_date": "tomorrow",
            "start_time": "10:00",
            "end_time": "12:00",
        })
        print(f"   Output: {avail_lab}", flush=True)
        assert avail_lab.startswith("AVAILABLE:")
        assert tomorrow_str in avail_lab
        print("   ✓ check_lab_availability resolved 'tomorrow' to", tomorrow_str, flush=True)

        # 4. create_lab_booking
        print("\n[Tool 4] create_lab_booking", flush=True)
        book_lab = ct.create_lab_booking.invoke({
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
            "lab_id": 2,
            "booking_date": "tomorrow",
            "start_time": "10:00",
            "end_time": "12:00",
        })
        print(f"   Output:\n{book_lab}", flush=True)
        assert "BOOKING CONFIRMED!" in book_lab
        assert "Booking ID:" in book_lab
        print("   ✓ create_lab_booking confirmed booking", flush=True)

        # 5. check_lab_availability (now unavailable)
        print("\n[Tool 5] check_lab_availability (conflict check)", flush=True)
        unavail_lab = ct.check_lab_availability.invoke({
            "lab_id": 2,
            "booking_date": tomorrow_str,
            "start_time": "11:00",
            "end_time": "13:00",
        })
        print(f"   Output: {unavail_lab}", flush=True)
        assert unavail_lab.startswith("UNAVAILABLE:")
        print("   ✓ check_lab_availability detected conflict", flush=True)

        # 6. check_room_availability (using relative term 'tomorrow')
        print("\n[Tool 6] check_room_availability with 'tomorrow'", flush=True)
        avail_room = ct.check_room_availability.invoke({
            "room_id": 1,
            "booking_date": "tomorrow",
            "start_time": "14:00",
            "end_time": "16:00",
        })
        print(f"   Output: {avail_room}", flush=True)
        assert avail_room.startswith("AVAILABLE:")
        assert tomorrow_str in avail_room
        print("   ✓ check_room_availability resolved 'tomorrow' to", tomorrow_str, flush=True)

        # 7. create_room_reservation
        print("\n[Tool 7] create_room_reservation", flush=True)
        book_room = ct.create_room_reservation.invoke({
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
            "room_id": 1,
            "booking_date": "tomorrow",
            "start_time": "14:00",
            "end_time": "16:00",
        })
        print(f"   Output:\n{book_room}", flush=True)
        assert "DISCUSSION ROOM RESERVED!" in book_room
        assert "Booking ID:" in book_room
        print("   ✓ create_room_reservation confirmed reservation", flush=True)

        # 8. check_room_availability (now unavailable)
        print("\n[Tool 8] check_room_availability (conflict check)", flush=True)
        unavail_room = ct.check_room_availability.invoke({
            "room_id": 1,
            "booking_date": tomorrow_str,
            "start_time": "15:00",
            "end_time": "17:00",
        })
        print(f"   Output: {unavail_room}", flush=True)
        assert unavail_room.startswith("UNAVAILABLE:")
        print("   ✓ check_room_availability detected conflict", flush=True)

        print("\n" + "=" * 65, flush=True)
        print(" ALL Campus Tools tests PASSED successfully!", flush=True)
        print("=" * 65, flush=True)

    finally:
        server_process.terminate()
        server_process.wait()
        # Clean up test-date records
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))
            conn.execute("DELETE FROM room_bookings WHERE booking_date = ?;", (test_date,))


if __name__ == "__main__":
    run_tool_tests()
