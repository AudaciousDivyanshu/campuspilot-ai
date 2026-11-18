"""End-to-End Verification of Enhanced Streamlit Application & Booking Functionality.

Verifies:
1. Facilities Directory: Confirms 3 laboratories and 3 discussion rooms with attributes.
2. Laboratory Booking Page Workflow: Direct availability check and SQLite commit.
3. Discussion Room Booking Page Workflow: Direct availability check and SQLite commit.
4. Conflict Detection: Overlap prevention across both service types.
5. Reservation Ledger: get_all_student_reservations returns accurate multi-service history.
"""

from datetime import date, timedelta
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

TEST_PORT = 8012
import app.tools.campus_tools as ct
ct.BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

from app.database.connection import get_db_context
from app.database.init_db import init_db
from app.database.operations import (
    get_all_discussion_rooms,
    get_all_laboratories,
    get_all_student_reservations,
    get_bookings_by_date,
    get_room_bookings_by_date,
)
from app.tools.campus_tools import (
    check_lab_availability,
    check_room_availability,
    create_lab_booking,
    create_room_reservation,
)
from app.tools.date_utils import get_current_date_context


class TestUIAndBookingWorkflow(unittest.TestCase):
    server_process = None

    @classmethod
    def setUpClass(cls):
        init_db()
        print(f"Launching test FastAPI backend on port {TEST_PORT}...", flush=True)
        cls.server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(TEST_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)

    @classmethod
    def tearDownClass(cls):
        if cls.server_process:
            cls.server_process.terminate()
            cls.server_process.wait()

    def test_01_facilities_directory(self):
        """Test that laboratories and discussion rooms are loaded with proper attributes."""
        labs = get_all_laboratories()
        rooms = get_all_discussion_rooms()

        self.assertEqual(len(labs), 3)
        self.assertEqual(len(rooms), 3)

        lab_names = [l["lab_name"] for l in labs]
        self.assertIn("Computer Lab 1", lab_names)
        self.assertIn("AI Lab", lab_names)
        self.assertIn("Networking Lab", lab_names)

        room_names = [r["room_name"] for r in rooms]
        self.assertIn("Discussion Room 1", room_names)
        self.assertIn("Discussion Room 2", room_names)
        self.assertIn("Discussion Room 3", room_names)
        print("  ✓ [Test 1] 3 Laboratories and 3 Library Discussion Rooms verified.")

    def test_02_direct_lab_booking_workflow(self):
        """Test direct laboratory availability check and booking commit."""
        date_ctx = get_current_date_context()
        test_date = date_ctx["tomorrow"]

        # 1. Clean test slot
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ? AND lab_id = 2;", (test_date,))

        # 2. Check availability
        avail_res = check_lab_availability.invoke({
            "lab_id": 2,
            "booking_date": test_date,
            "start_time": "13:00",
            "end_time": "15:00",
        })
        self.assertTrue(avail_res.startswith("AVAILABLE:"))

        # 3. Create booking
        booking_res = create_lab_booking.invoke({
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
            "lab_id": 2,
            "booking_date": test_date,
            "start_time": "13:00",
            "end_time": "15:00",
        })
        self.assertIn("BOOKING CONFIRMED!", booking_res)
        id_match = re.search(r"Booking ID:\s*(\d+)", booking_res)
        self.assertIsNotNone(id_match)
        booking_id = int(id_match.group(1))

        # 4. Conflict check (overlap prevention)
        conflict_res = check_lab_availability.invoke({
            "lab_id": 2,
            "booking_date": test_date,
            "start_time": "14:00",
            "end_time": "16:00",
        })
        self.assertTrue(conflict_res.startswith("UNAVAILABLE:"))
        print(f"  ✓ [Test 2] Direct Lab Booking #{booking_id} confirmed and conflict prevented.")

    def test_03_direct_room_reservation_workflow(self):
        """Test direct library discussion room availability check and reservation."""
        date_ctx = get_current_date_context()
        test_date = date_ctx["tomorrow"]

        # 1. Clean test slot
        with get_db_context() as conn:
            conn.execute("DELETE FROM room_bookings WHERE booking_date = ? AND room_id = 1;", (test_date,))

        # 2. Check availability
        avail_res = check_room_availability.invoke({
            "room_id": 1,
            "booking_date": test_date,
            "start_time": "10:00",
            "end_time": "12:00",
        })
        self.assertTrue(avail_res.startswith("AVAILABLE:"))

        # 3. Create reservation
        room_res = create_room_reservation.invoke({
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
            "room_id": 1,
            "booking_date": test_date,
            "start_time": "10:00",
            "end_time": "12:00",
        })
        self.assertIn("DISCUSSION ROOM RESERVED!", room_res)
        id_match = re.search(r"Booking ID:\s*(\d+)", room_res)
        self.assertIsNotNone(id_match)
        room_booking_id = int(id_match.group(1))

        # 4. Conflict check
        conflict_res = check_room_availability.invoke({
            "room_id": 1,
            "booking_date": test_date,
            "start_time": "11:00",
            "end_time": "13:00",
        })
        self.assertTrue(conflict_res.startswith("UNAVAILABLE:"))
        print(f"  ✓ [Test 3] Discussion Room Reservation #{room_booking_id} confirmed and conflict prevented.")

    def test_04_student_reservation_ledger(self):
        """Test that get_all_student_reservations returns unified history for the student."""
        records = get_all_student_reservations(student_id="CS2026-042", student_name="Aarav Sharma")
        self.assertGreaterEqual(len(records), 2)

        service_types = {r["service_type"] for r in records}
        self.assertIn("Laboratory", service_types)
        self.assertIn("Library Room", service_types)

        for r in records:
            self.assertIn("booking_id", r)
            self.assertIn("facility_name", r)
            self.assertIn("booking_date", r)
            self.assertIn("start_time", r)
            self.assertIn("end_time", r)
            self.assertEqual(r["status"].lower(), "confirmed")
        print(f"  ✓ [Test 4] Unified reservation ledger returned {len(records)} records for Aarav Sharma.")


if __name__ == "__main__":
    print("=" * 65)
    print(" Running CampusPilot AI: UI & Booking Workflow Tests")
    print("=" * 65)
    unittest.main(verbosity=1)
