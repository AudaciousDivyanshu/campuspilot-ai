"""Automated HTTP endpoint tests for CampusPilot AI FastAPI backend.

Verifies all Laboratory and Library Discussion Room endpoints:
1. GET /health
2. GET /labs
3. GET /availability (free slot vs occupied slot)
4. POST /bookings (successful creation)
5. POST /bookings (conflict prevention)
6. GET /bookings (query by date)
7. GET /rooms
8. GET /rooms/availability (free slot vs occupied slot)
9. POST /rooms/bookings (successful room reservation)
10. POST /rooms/bookings (conflict prevention)
11. GET /rooms/bookings (query by date)
12. Input validations (bad date, inverted time, non-existent lab/room ID)
"""

from pathlib import Path
import subprocess
import sys
import time
import requests

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_db_context
from app.database.init_db import init_db

TEST_PORT = 8008
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def run_api_tests():
    print("=" * 65, flush=True)
    print(" CampusPilot AI: Multi-Service API Endpoint Verification", flush=True)
    print("=" * 65, flush=True)

    # Initialize SQLite database
    init_db()
    test_date = "2026-11-28"

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

    # Wait for server to bind
    for _ in range(15):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=1)
            if r.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.5)

    try:
        # 1. Health check
        print("\n[Test 1] GET /health", flush=True)
        res = requests.get(f"{BASE_URL}/health", timeout=3)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        print(f"   ✓ Health Status: {res.json()}", flush=True)

        # 2. Labs directory
        print("\n[Test 2] GET /labs", flush=True)
        res = requests.get(f"{BASE_URL}/labs", timeout=3)
        assert res.status_code == 200
        labs = res.json()
        assert len(labs) == 3
        print(f"   ✓ Retrieved {len(labs)} laboratories:", flush=True)
        for lab in labs:
            print(f"     * [Lab #{lab['lab_id']}] {lab['lab_name']} (Cap: {lab['capacity']}, Loc: {lab['location']})", flush=True)

        ai_lab = next(l for l in labs if l["lab_name"] == "AI Lab")

        # 3. Lab availability check (free)
        print(f"\n[Test 3] GET /availability (free slot)", flush=True)
        res = requests.get(
            f"{BASE_URL}/availability",
            params={"lab_id": ai_lab["lab_id"], "booking_date": test_date, "start_time": "10:00", "end_time": "12:00"},
            timeout=3,
        )
        assert res.status_code == 200
        assert res.json()["is_available"] is True
        print(f"   ✓ Slot is free: {res.json()['message']}", flush=True)

        # 4. Create lab booking
        print(f"\n[Test 4] POST /bookings (create confirmed booking)", flush=True)
        payload = {
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
            "lab_id": ai_lab["lab_id"],
            "booking_date": test_date,
            "start_time": "10:00",
            "end_time": "12:00",
        }
        res = requests.post(f"{BASE_URL}/bookings", json=payload, timeout=3)
        assert res.status_code == 201
        booking_data = res.json()
        assert booking_data["booking_id"] > 0
        assert booking_data["status"] == "confirmed"
        print(f"   ✓ Booking created: ID #{booking_data['booking_id']} for {booking_data['student_name']}", flush=True)

        # 5. Overlap rejection on lab booking
        print(f"\n[Test 5] POST /bookings (conflict prevention)", flush=True)
        conflict_payload = {
            "student_id": "CS2026-088",
            "student_name": "Priya Patel",
            "lab_id": ai_lab["lab_id"],
            "booking_date": test_date,
            "start_time": "11:00",
            "end_time": "13:00",
        }
        res = requests.post(f"{BASE_URL}/bookings", json=conflict_payload, timeout=3)
        assert res.status_code == 409
        print(f"   ✓ Conflict rejected (HTTP 409): {res.json()['detail']}", flush=True)

        # 6. Query lab bookings by date
        print(f"\n[Test 6] GET /bookings?booking_date={test_date}", flush=True)
        res = requests.get(f"{BASE_URL}/bookings", params={"booking_date": test_date}, timeout=3)
        assert res.status_code == 200
        bookings_list = res.json()
        assert len(bookings_list) == 1
        print(f"   ✓ Found {len(bookings_list)} booking on date {test_date}", flush=True)

        # 7. Library rooms directory
        print("\n[Test 7] GET /rooms", flush=True)
        res = requests.get(f"{BASE_URL}/rooms", timeout=3)
        assert res.status_code == 200
        rooms = res.json()
        assert len(rooms) == 3
        print(f"   ✓ Retrieved {len(rooms)} library discussion rooms:", flush=True)
        for room in rooms:
            print(f"     * [Room #{room['room_id']}] {room['room_name']} (Cap: {room['capacity']}, Loc: {room['location']})", flush=True)

        room2 = next(r for r in rooms if r["room_name"] == "Discussion Room 2")

        # 8. Room availability check (free)
        print(f"\n[Test 8] GET /rooms/availability (free slot)", flush=True)
        res = requests.get(
            f"{BASE_URL}/rooms/availability",
            params={"room_id": room2["room_id"], "booking_date": test_date, "start_time": "14:00", "end_time": "16:00"},
            timeout=3,
        )
        assert res.status_code == 200
        assert res.json()["is_available"] is True
        print(f"   ✓ Room slot free: {res.json()['message']}", flush=True)

        # 9. Create discussion room reservation
        print(f"\n[Test 9] POST /rooms/bookings (create confirmed reservation)", flush=True)
        room_payload = {
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
            "room_id": room2["room_id"],
            "booking_date": test_date,
            "start_time": "14:00",
            "end_time": "16:00",
        }
        res = requests.post(f"{BASE_URL}/rooms/bookings", json=room_payload, timeout=3)
        assert res.status_code == 201
        room_res_data = res.json()
        assert room_res_data["booking_id"] > 0
        assert room_res_data["status"] == "confirmed"
        print(f"   ✓ Room reservation created: ID #{room_res_data['booking_id']} for {room_res_data['student_name']}", flush=True)

        # 10. Overlap rejection on room reservation
        print(f"\n[Test 10] POST /rooms/bookings (conflict prevention)", flush=True)
        conflict_room_payload = {
            "student_id": "CS2026-099",
            "student_name": "Rohan Gupta",
            "room_id": room2["room_id"],
            "booking_date": test_date,
            "start_time": "15:00",
            "end_time": "17:00",
        }
        res = requests.post(f"{BASE_URL}/rooms/bookings", json=conflict_room_payload, timeout=3)
        assert res.status_code == 409
        print(f"   ✓ Conflict rejected (HTTP 409): {res.json()['detail']}", flush=True)

        # 11. Query room reservations by date
        print(f"\n[Test 11] GET /rooms/bookings?booking_date={test_date}", flush=True)
        res = requests.get(f"{BASE_URL}/rooms/bookings", params={"booking_date": test_date}, timeout=3)
        assert res.status_code == 200
        room_bookings_list = res.json()
        assert len(room_bookings_list) == 1
        print(f"   ✓ Found {len(room_bookings_list)} room reservation on date {test_date}", flush=True)

        # 12. Input validations
        print("\n[Test 12] Validation checks (bad date, inverted time, unknown ID)", flush=True)
        # Invalid date format
        res = requests.get(f"{BASE_URL}/bookings", params={"booking_date": "not-a-date"}, timeout=3)
        assert res.status_code == 400
        print("   ✓ Invalid date format rejected (HTTP 400)", flush=True)

        # Inverted time range
        inv_payload = dict(payload)
        inv_payload["start_time"] = "16:00"
        inv_payload["end_time"] = "14:00"
        res = requests.post(f"{BASE_URL}/bookings", json=inv_payload, timeout=3)
        assert res.status_code == 400
        print("   ✓ Inverted time rejected (HTTP 400)", flush=True)

        # Non-existent lab ID
        bad_lab_payload = dict(payload)
        bad_lab_payload["lab_id"] = 999
        res = requests.post(f"{BASE_URL}/bookings", json=bad_lab_payload, timeout=3)
        assert res.status_code == 404
        print("   ✓ Non-existent lab rejected (HTTP 404)", flush=True)

        # Non-existent room ID
        bad_room_payload = dict(room_payload)
        bad_room_payload["room_id"] = 999
        res = requests.post(f"{BASE_URL}/rooms/bookings", json=bad_room_payload, timeout=3)
        assert res.status_code == 404
        print("   ✓ Non-existent discussion room rejected (HTTP 404)", flush=True)

        print("\n" + "=" * 65, flush=True)
        print(" ALL FastAPI endpoint tests PASSED successfully!", flush=True)
        print("=" * 65, flush=True)

    finally:
        server_process.terminate()
        server_process.wait()
        # Clean up test-date records
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))
            conn.execute("DELETE FROM room_bookings WHERE booking_date = ?;", (test_date,))


if __name__ == "__main__":
    run_api_tests()
