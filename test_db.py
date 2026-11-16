"""Demonstration and test script for CampusPilot AI SQLite database layer.

Tests:
1. Safe database initialization & sample lab seeding.
2. Querying all available laboratories.
3. Successful creation of a sample booking.
4. Detection and prevention of overlapping bookings.
5. Successful creation of a non-overlapping booking.
6. Validation of start_time < end_time.
7. Querying bookings by date.
"""

import sys
from pathlib import Path

# Add project root to sys.path so app module is importable
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import (
    check_booking_overlap,
    create_booking,
    get_all_laboratories,
    get_bookings_by_date,
    init_db,
    validate_time_range,
)


def run_tests() -> None:
    print("=" * 65)
    print(" CampusPilot AI: SQLite Database Verification & Test Script")
    print("=" * 65)

    # 1. Initialize Database
    print("\n[Step 1] Initializing SQLite database...")
    db_path = init_db()
    print(f" Database successfully initialized at: {db_path}")

    # Re-run initialization to prove idempotency (no duplicate entries)
    init_db()
    print(" Verified: Re-running init_db() is safe and idempotent.")

    # 2. Query Laboratories
    print("\n[Step 2] Fetching all laboratories:")
    labs = get_all_laboratories()
    for lab in labs:
        print(f"   - [ID {lab['lab_id']}] {lab['lab_name']} (Capacity: {lab['capacity']}, Location: {lab['location']})")

    if len(labs) != 3:
        print(f" Error: Expected 3 laboratories, found {len(labs)}")
        sys.exit(1)

    ai_lab = next(l for l in labs if l["lab_name"] == "AI Lab")
    test_date = "2026-11-20"

    # Clean up test-date bookings if present from a prior test run so the demo is repeatable
    from app.database.connection import get_db_context
    with get_db_context() as conn:
        conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))

    # 3. Create a Sample Booking
    print(f"\n[Step 3] Creating sample booking in '{ai_lab['lab_name']}'...")
    sample_booking = create_booking(
        student_id="CS2026-042",
        student_name="Aarav Sharma",
        lab_id=ai_lab["lab_id"],
        booking_date=test_date,
        start_time="10:00",
        end_time="12:00",
    )
    print(" Sample booking created successfully:")
    print(f"   Booking ID   : {sample_booking['booking_id']}")
    print(f"   Student      : {sample_booking['student_name']} ({sample_booking['student_id']})")
    print(f"   Lab          : {sample_booking['lab_name']}")
    print(f"   Date & Time  : {sample_booking['booking_date']} from {sample_booking['start_time']} to {sample_booking['end_time']}")
    print(f"   Status       : {sample_booking['status']}")

    # 4. Check for Overlapping Bookings
    print("\n[Step 4] Testing booking overlap detection:")
    overlap_scenarios = [
        ("11:00", "13:00", "Partial overlap at end (11:00-12:00)"),
        ("09:30", "10:30", "Partial overlap at start (10:00-10:30)"),
        ("10:15", "11:45", "Complete interior overlap"),
        ("09:00", "13:00", "Complete enclosing overlap"),
    ]

    for start_t, end_t, desc in overlap_scenarios:
        is_overlapping = check_booking_overlap(
            lab_id=ai_lab["lab_id"],
            booking_date=test_date,
            start_time=start_t,
            end_time=end_t,
        )
        print(f"   - Checking {start_t} - {end_t} ({desc}): Overlap Detected = {is_overlapping}")
        assert is_overlapping is True, f"Expected overlap for {start_t}-{end_t}"

    # Try creating an overlapping booking to verify enforcement
    print("\n   Testing create_booking conflict prevention:")
    try:
        create_booking(
            student_id="CS2026-088",
            student_name="Priya Patel",
            lab_id=ai_lab["lab_id"],
            booking_date=test_date,
            start_time="11:00",
            end_time="12:30",
        )
        print("   ❌ Error: Overlapping booking was improperly allowed!")
        sys.exit(1)
    except ValueError as e:
        print(f"   Confirmed: Overlap rejected with error -> {e}")

    # 5. Non-overlapping Booking
    print("\n[Step 5] Creating non-overlapping booking:")
    non_overlap_slot = ("13:00", "14:30")
    is_overlapping = check_booking_overlap(
        lab_id=ai_lab["lab_id"],
        booking_date=test_date,
        start_time=non_overlap_slot[0],
        end_time=non_overlap_slot[1],
    )
    print(f"   - Checking {non_overlap_slot[0]} - {non_overlap_slot[1]}: Overlap Detected = {is_overlapping}")
    assert is_overlapping is False

    booking2 = create_booking(
        student_id="CS2026-088",
        student_name="Priya Patel",
        lab_id=ai_lab["lab_id"],
        booking_date=test_date,
        start_time=non_overlap_slot[0],
        end_time=non_overlap_slot[1],
    )
    print(f"    Booking ID {booking2['booking_id']} successfully confirmed for {booking2['student_name']}.")

    # 6. Time Range Validation Check (start_time >= end_time)
    print("\n[Step 6] Testing invalid time range validation (15:00 to 14:00):")
    try:
        validate_time_range("15:00", "14:00")
        print("   ❌ Error: Inverted time range was improperly allowed!")
        sys.exit(1)
    except ValueError as e:
        print(f"   Confirmed: Invalid time range rejected with error -> {e}")

    # 7. Query All Bookings for Date
    print(f"\n[Step 7] Querying all bookings for date: {test_date}")
    all_bookings = get_bookings_by_date(test_date)
    for b in all_bookings:
        print(f"   - [Booking #{b['booking_id']}] {b['lab_name']} | {b['start_time']} - {b['end_time']} | Student: {b['student_name']} ({b['student_id']}) | Status: {b['status']}")

    print("\n" + "=" * 65)
    print(" All database tests and verifications PASSED successfully!")
    print("=" * 65)

    # Clean up test-date records after test completion
    with get_db_context() as conn:
        conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))


if __name__ == "__main__":
    run_tests()
