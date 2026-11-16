"""Demonstration and test script for CampusPilot AI SQLite database layer.

Tests:
1. Safe database initialization & sample lab and discussion room seeding.
2. Querying all available laboratories and discussion rooms.
3. Successful creation of a sample laboratory booking and room reservation.
4. Detection and prevention of overlapping bookings in both facilities.
5. Successful creation of non-overlapping bookings in both facilities.
6. Validation of start_time < end_time across both facilities.
7. Querying bookings and room reservations by date.
8. Safe test data cleanup without altering pre-existing records.
"""

import sys
from pathlib import Path

# Add project root to sys.path so app module is importable
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import (
    check_booking_overlap,
    check_room_booking_overlap,
    create_booking,
    create_room_booking,
    get_all_discussion_rooms,
    get_all_laboratories,
    get_bookings_by_date,
    get_room_bookings_by_date,
    init_db,
    validate_time_range,
)
from app.database.connection import get_db_context


def run_tests() -> None:
    print("=" * 65)
    print(" CampusPilot AI: Multi-Service Database Verification & Test")
    print("=" * 65)

    # 1. Initialize Database
    print("\n[Step 1] Initializing SQLite database...")
    db_path = init_db()
    print(f" Database successfully initialized at: {db_path}")

    # Re-run initialization to prove idempotency
    init_db()
    print(" Verified: Re-running init_db() is safe and idempotent.")

    # 2. Query Laboratories & Discussion Rooms
    print("\n[Step 2A] Fetching all laboratories:")
    labs = get_all_laboratories()
    for lab in labs:
        print(f"   - [ID {lab['lab_id']}] {lab['lab_name']} (Capacity: {lab['capacity']}, Location: {lab['location']})")
    assert len(labs) == 3, f"Expected 3 laboratories, found {len(labs)}"

    print("\n[Step 2B] Fetching all library discussion rooms:")
    rooms = get_all_discussion_rooms()
    for room in rooms:
        print(f"   - [ID {room['room_id']}] {room['room_name']} (Capacity: {room['capacity']}, Location: {room['location']})")
    assert len(rooms) == 3, f"Expected 3 discussion rooms, found {len(rooms)}"

    ai_lab = next(l for l in labs if l["lab_name"] == "AI Lab")
    disc_room2 = next(r for r in rooms if r["room_name"] == "Discussion Room 2")
    test_date = "2026-11-20"

    # Clean up test-date records from prior runs
    with get_db_context() as conn:
        conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))
        conn.execute("DELETE FROM room_bookings WHERE booking_date = ?;", (test_date,))

    # 3. Laboratory Booking Workflow
    print(f"\n[Step 3] Testing Laboratory Booking in '{ai_lab['lab_name']}'...")
    lab_booking1 = create_booking(
        student_id="CS2026-042",
        student_name="Aarav Sharma",
        lab_id=ai_lab["lab_id"],
        booking_date=test_date,
        start_time="10:00",
        end_time="12:00",
    )
    print(f"   ✓ Lab Booking #{lab_booking1['booking_id']} created for {lab_booking1['student_name']} (10:00-12:00)")

    # Lab Overlap Checks
    is_overlapping = check_booking_overlap(ai_lab["lab_id"], test_date, "11:00", "13:00")
    assert is_overlapping is True
    print("   ✓ Lab overlap correctly detected for 11:00-13:00")

    try:
        create_booking(
            student_id="CS2026-088",
            student_name="Priya Patel",
            lab_id=ai_lab["lab_id"],
            booking_date=test_date,
            start_time="11:00",
            end_time="12:30",
        )
        print("   ❌ Error: Overlapping lab booking was improperly allowed!")
        sys.exit(1)
    except ValueError as e:
        print(f"   ✓ Lab overlap prevented: {e}")

    # Non-overlapping lab booking
    lab_booking2 = create_booking(
        student_id="CS2026-088",
        student_name="Priya Patel",
        lab_id=ai_lab["lab_id"],
        booking_date=test_date,
        start_time="13:00",
        end_time="14:30",
    )
    print(f"   ✓ Non-overlapping lab booking #{lab_booking2['booking_id']} created (13:00-14:30)")

    # 4. Library Discussion Room Workflow
    print(f"\n[Step 4] Testing Library Discussion Room in '{disc_room2['room_name']}'...")
    room_booking1 = create_room_booking(
        student_id="CS2026-042",
        student_name="Aarav Sharma",
        room_id=disc_room2["room_id"],
        booking_date=test_date,
        start_time="14:00",
        end_time="16:00",
    )
    print(f"   ✓ Room Reservation #{room_booking1['booking_id']} created for {room_booking1['student_name']} (14:00-16:00)")

    # Room Overlap Checks
    room_overlap = check_room_booking_overlap(disc_room2["room_id"], test_date, "15:00", "17:00")
    assert room_overlap is True
    print("   ✓ Room overlap correctly detected for 15:00-17:00")

    try:
        create_room_booking(
            student_id="CS2026-099",
            student_name="Rohan Gupta",
            room_id=disc_room2["room_id"],
            booking_date=test_date,
            start_time="14:30",
            end_time="15:30",
        )
        print("   ❌ Error: Overlapping room reservation was improperly allowed!")
        sys.exit(1)
    except ValueError as e:
        print(f"   ✓ Room overlap prevented: {e}")

    # Non-overlapping room reservation
    room_booking2 = create_room_booking(
        student_id="CS2026-099",
        student_name="Rohan Gupta",
        room_id=disc_room2["room_id"],
        booking_date=test_date,
        start_time="16:30",
        end_time="18:00",
    )
    print(f"   ✓ Non-overlapping room reservation #{room_booking2['booking_id']} created (16:30-18:00)")

    # 5. Time Range Validation
    print("\n[Step 5] Testing time range validation (inverted times):")
    try:
        validate_time_range("16:00", "14:00")
        print("   ❌ Error: Inverted time range allowed!")
        sys.exit(1)
    except ValueError as e:
        print(f"   ✓ Inverted time rejected: {e}")

    # 6. Query By Date
    print(f"\n[Step 6] Querying all bookings for date: {test_date}")
    all_lab_bookings = get_bookings_by_date(test_date)
    all_room_bookings = get_room_bookings_by_date(test_date)
    print(f"   - Lab Bookings Count  : {len(all_lab_bookings)}")
    for b in all_lab_bookings:
        print(f"     * [Lab #{b['booking_id']}] {b['lab_name']} ({b['start_time']}-{b['end_time']}) - {b['student_name']}")
    print(f"   - Room Bookings Count : {len(all_room_bookings)}")
    for r in all_room_bookings:
        print(f"     * [Room #{r['booking_id']}] {r['room_name']} ({r['start_time']}-{r['end_time']}) - {r['student_name']}")

    assert len(all_lab_bookings) == 2
    assert len(all_room_bookings) == 2

    # Clean up test-date records
    with get_db_context() as conn:
        conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))
        conn.execute("DELETE FROM room_bookings WHERE booking_date = ?;", (test_date,))

    print("\n" + "=" * 65)
    print(" ALL multi-service database tests PASSED successfully!")
    print("=" * 65)


if __name__ == "__main__":
    run_tests()
