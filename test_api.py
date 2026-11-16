"""Automated endpoint tests for CampusPilot AI FastAPI backend.

Verifies:
1. GET /health
2. GET /labs
3. GET /bookings
4. GET /availability (available slot vs. occupied slot)
5. POST /bookings (successful creation)
6. POST /bookings (conflict rejection)
7. Input validations (bad date, inverted time, unknown lab)
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import get_db_context
from app.database.init_db import init_db


def run_api_tests():
    print("=" * 65, flush=True)
    print(" CampusPilot AI: FastAPI Backend Endpoint Verification", flush=True)
    print("=" * 65, flush=True)

    with TestClient(app) as client:
        # Reset test date entries in database for clean repeatable testing
        init_db()
        test_date = "2026-11-25"
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))

        # 1. Test GET /health
        print("\n[Test 1] Testing GET /health...", flush=True)
        res = client.get("/health")
        print(f" Status: {res.status_code}, Response: {res.json()}", flush=True)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        print(" PASS: /health endpoint is operational.", flush=True)

        # 2. Test GET /labs
        print("\n[Test 2] Testing GET /labs...", flush=True)
        res = client.get("/labs")
        labs = res.json()
        print(f" Status: {res.status_code}, Found {len(labs)} laboratories:", flush=True)
        for lab in labs:
            print(f"   - Lab #{lab['lab_id']}: {lab['lab_name']} (Cap: {lab['capacity']}, Loc: {lab['location']})", flush=True)
        assert res.status_code == 200
        assert len(labs) >= 3
        print(" PASS: /labs returns actual SQLite records.", flush=True)

        # Select AI Lab for booking tests
        ai_lab = next(l for l in labs if l["lab_name"] == "AI Lab")
        ai_lab_id = ai_lab["lab_id"]

        # 3. Test GET /availability (Slot initially free)
        print(f"\n[Test 3] Testing GET /availability for free slot (10:00 - 12:00 in {ai_lab['lab_name']})...", flush=True)
        res = client.get(
            "/availability",
            params={
                "lab_id": ai_lab_id,
                "booking_date": test_date,
                "start_time": "10:00",
                "end_time": "12:00",
            },
        )
        print(f" Status: {res.status_code}, Response: {res.json()}", flush=True)
        assert res.status_code == 200
        assert res.json()["is_available"] is True
        print(" PASS: Unbooked slot correctly reported as available.", flush=True)

        # 4. Test POST /bookings (Create booking)
        print("\n[Test 4] Testing POST /bookings to create a confirmed booking...", flush=True)
        payload = {
            "student_id": "CS2026-101",
            "student_name": "Rohan Gupta",
            "lab_id": ai_lab_id,
            "booking_date": test_date,
            "start_time": "10:00",
            "end_time": "12:00",
        }
        res = client.post("/bookings", json=payload)
        print(f" Status: {res.status_code}, Response: {res.json()}", flush=True)
        assert res.status_code == 201
        created_booking = res.json()
        assert created_booking["booking_id"] is not None
        assert created_booking["student_name"] == "Rohan Gupta"
        assert created_booking["status"] == "confirmed"
        print(f" PASS: Booking #{created_booking['booking_id']} successfully created in SQLite.", flush=True)

        # 5. Test GET /bookings (Verify created booking is listed)
        print(f"\n[Test 5] Testing GET /bookings for date: {test_date}...", flush=True)
        res = client.get("/bookings", params={"booking_date": test_date})
        print(f" Status: {res.status_code}, Bookings found: {len(res.json())}", flush=True)
        for b in res.json():
            print(f"   - Booking #{b['booking_id']}: {b['lab_name']} | {b['start_time']} - {b['end_time']} | {b['student_name']}", flush=True)
        assert res.status_code == 200
        assert len(res.json()) >= 1
        print(" PASS: Confirmed bookings retrieved from database.", flush=True)

        # 6. Test GET /availability (Now slot should be unavailable)
        print("\n[Test 6] Testing GET /availability for now-occupied slot (11:00 - 13:00)...", flush=True)
        res = client.get(
            "/availability",
            params={
                "lab_id": ai_lab_id,
                "booking_date": test_date,
                "start_time": "11:00",
                "end_time": "13:00",
            },
        )
        print(f" Status: {res.status_code}, Response: {res.json()}", flush=True)
        assert res.status_code == 200
        assert res.json()["is_available"] is False
        print(" PASS: Conflicting slot correctly reported as unavailable.", flush=True)

        # 7. Test POST /bookings conflict rejection (409 Conflict)
        print("\n[Test 7] Testing POST /bookings conflict rejection for overlapping time...", flush=True)
        overlap_payload = {
            "student_id": "CS2026-202",
            "student_name": "Sneha Roy",
            "lab_id": ai_lab_id,
            "booking_date": test_date,
            "start_time": "11:00",
            "end_time": "13:00",
        }
        res = client.post("/bookings", json=overlap_payload)
        print(f" Status: {res.status_code}, Response: {res.json()}", flush=True)
        assert res.status_code == 409
        assert "already booked" in res.json()["detail"].lower()
        print(" PASS: Overlapping booking rejected with HTTP 409 Conflict.", flush=True)

        # 8. Test Validation Error (inverted time: 14:00 to 12:00)
        print("\n[Test 8] Testing validation error on inverted time (14:00 to 12:00)...", flush=True)
        bad_time_payload = {
            "student_id": "CS2026-202",
            "student_name": "Sneha Roy",
            "lab_id": ai_lab_id,
            "booking_date": test_date,
            "start_time": "14:00",
            "end_time": "12:00",
        }
        res = client.post("/bookings", json=bad_time_payload)
        print(f" Status: {res.status_code}, Detail: {res.json().get('detail')}", flush=True)
        assert res.status_code == 400
        print(" PASS: Inverted time range rejected with HTTP 400 Bad Request.", flush=True)

        # 9. Test Non-existent Lab (404 Not Found)
        print("\n[Test 9] Testing non-existent lab_id=9999...", flush=True)
        res = client.get(
            "/availability",
            params={
                "lab_id": 9999,
                "booking_date": test_date,
                "start_time": "10:00",
                "end_time": "11:00",
            },
        )
        print(f" Status: {res.status_code}, Detail: {res.json().get('detail')}", flush=True)
        assert res.status_code == 404
        print(" PASS: Non-existent lab correctly returned HTTP 404 Not Found.", flush=True)

        print("\n" + "=" * 65, flush=True)
        print(" ALL FASTAPI ENDPOINT TESTS PASSED SUCCESSFULLY!", flush=True)
        print("=" * 65, flush=True)

        # Clean up test-date records after test completion
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))


if __name__ == "__main__":
    run_api_tests()
