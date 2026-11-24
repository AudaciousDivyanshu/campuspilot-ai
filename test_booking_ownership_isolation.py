"""Tests for Strict User-Wise Booking Ownership, Privacy Isolation, and Admin Access."""

import os
import unittest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import get_db_context
from app.database.operations import (
    approve_booking,
    cancel_reservation,
    create_booking,
    create_room_booking,
    get_all_booking_requests,
    get_all_student_reservations,
    reject_booking,
)
from app.services.demo_auth import authenticate_user, register_user, _load_users, _save_users


class TestBookingOwnershipIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.email_a = "student_a_iso@campus.edu"
        cls.email_b = "student_b_iso@campus.edu"
        cls.pwd = "IsolationPass123"
        cls.shared_roll = "ROLL-999"  # Intentionally identical roll number for both students

        # Clean up any leftover test users/bookings
        users = _load_users()
        users.pop(cls.email_a, None)
        users.pop(cls.email_b, None)
        _save_users(users)

        ok_a, res_a = register_user(
            email=cls.email_a,
            password=cls.pwd,
            full_name="Same Name Student",
            account_type="Student",
            student_id=cls.shared_roll,
            department="Computer Science & Engineering",
        )
        assert ok_a, f"Failed to register Student A: {res_a}"
        cls.user_a = res_a

        ok_b, res_b = register_user(
            email=cls.email_b,
            password=cls.pwd,
            full_name="Same Name Student",  # Even with same name + same roll number!
            account_type="Student",
            student_id=cls.shared_roll,
            department="Artificial Intelligence",
        )
        assert ok_b, f"Failed to register Student B: {res_b}"
        cls.user_b = res_b

    @classmethod
    def tearDownClass(cls):
        uid_a = cls.user_a["user_id"]
        uid_b = cls.user_b["user_id"]
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookings WHERE student_id IN (?, ?);", (uid_a, uid_b))
            cur.execute("DELETE FROM room_bookings WHERE student_id IN (?, ?);", (uid_a, uid_b))
            cur.execute("DELETE FROM user_accounts WHERE user_id IN (?, ?);", (uid_a, uid_b))
            cur.execute("DELETE FROM student_profiles WHERE user_id IN (?, ?);", (uid_a, uid_b))
        users = _load_users()
        users.pop(cls.email_a, None)
        users.pop(cls.email_b, None)
        _save_users(users)

    def setUp(self):
        uid_a = self.user_a["user_id"]
        uid_b = self.user_b["user_id"]
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookings WHERE student_id IN (?, ?);", (uid_a, uid_b))
            cur.execute("DELETE FROM room_bookings WHERE student_id IN (?, ?);", (uid_a, uid_b))

    def test_01_distinct_user_ids_even_with_shared_roll_number_and_name(self):
        """1. Two students with identical roll number & name must receive distinct user_id keys."""
        self.assertNotEqual(self.user_a["user_id"], self.user_b["user_id"])
        self.assertEqual(self.user_a["student_id"], self.shared_roll)
        self.assertEqual(self.user_b["student_id"], self.shared_roll)

    def test_02_two_students_strict_booking_isolation_and_admin_access(self):
        """2. Student A & B bookings are strictly isolated in My Bookings, while Admin sees both lab queues."""
        d1 = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        d2 = (date.today() + timedelta(days=31)).strftime("%Y-%m-%d")

        # Student A logs in
        ok_a, auth_a = authenticate_user(self.email_a, self.pwd, required_role="Student")
        self.assertTrue(ok_a)
        uid_a = auth_a["user_id"]

        # Student A creates 1 Lab booking + 1 Discussion Room booking
        lab_a = create_booking(
            student_id=uid_a,
            student_name=auth_a["full_name"],
            lab_id=2,  # AI Lab
            booking_date=d1,
            start_time="10:00",
            end_time="12:00",
            status="pending",
            purpose="Student A AI Experiment",
        )
        room_a = create_room_booking(
            student_id=uid_a,
            student_name=auth_a["full_name"],
            room_id=1,
            booking_date=d1,
            start_time="13:00",
            end_time="14:00",
            status="confirmed",
            purpose="Student A Group Study",
        )

        # Student A My Bookings shows ONLY Student A's 2 reservations
        res_a = get_all_student_reservations(student_id=uid_a)
        self.assertEqual(len(res_a), 2)
        self.assertTrue(all(r["student_id"] == uid_a for r in res_a))

        # Student B logs in (separate session)
        ok_b, auth_b = authenticate_user(self.email_b, self.pwd, required_role="Student")
        self.assertTrue(ok_b)
        uid_b = auth_b["user_id"]

        # Student B sees ZERO bookings initially (never Student A's bookings!)
        res_b_initial = get_all_student_reservations(student_id=uid_b)
        self.assertEqual(len(res_b_initial), 0)

        # Student B creates a separate Computer Lab booking
        lab_b = create_booking(
            student_id=uid_b,
            student_name=auth_b["full_name"],
            lab_id=1,  # Computer Lab
            booking_date=d2,
            start_time="10:00",
            end_time="12:00",
            status="pending",
            purpose="Student B Systems Lab",
        )

        # Student B My Bookings shows ONLY Student B's 1 reservation
        res_b_after = get_all_student_reservations(student_id=uid_b)
        self.assertEqual(len(res_b_after), 1)
        self.assertEqual(res_b_after[0]["booking_id"], lab_b["booking_id"])
        self.assertEqual(res_b_after[0]["student_id"], uid_b)

        # Administrator logs in and views pending queue: sees BOTH Student A's and Student B's lab requests,
        # and does NOT see Student A's self-service discussion room booking
        admin_email = os.getenv("ADMIN_EMAIL", "admin@campus.edu")
        admin_pwd = os.getenv("ADMIN_PASSWORD", "AdminPass123")
        ok_adm, _ = authenticate_user(admin_email, admin_pwd, required_role="Administrator")
        self.assertTrue(ok_adm)

        admin_pending = get_all_booking_requests(status_filter="pending")
        pending_ids = {r["booking_id"] for r in admin_pending}
        self.assertIn(lab_a["booking_id"], pending_ids)
        self.assertIn(lab_b["booking_id"], pending_ids)
        self.assertFalse(any(r["service_type"] == "Library Room" for r in admin_pending))

        # Admin approves Student A's lab and rejects Student B's lab
        ok_appr, _ = approve_booking(lab_a["booking_id"], "Laboratory")
        self.assertTrue(ok_appr)
        ok_rej = reject_booking(lab_b["booking_id"], "Laboratory", rejection_reason="Slot reserved for practical exam")
        self.assertTrue(ok_rej)

        # Verify each student sees their own updated status
        final_a = get_all_student_reservations(student_id=uid_a)
        lab_a_final = next(r for r in final_a if r["booking_id"] == lab_a["booking_id"])
        self.assertEqual(lab_a_final["status"], "approved")

        final_b = get_all_student_reservations(student_id=uid_b)
        lab_b_final = next(r for r in final_b if r["booking_id"] == lab_b["booking_id"])
        self.assertEqual(lab_b_final["status"], "rejected")
        self.assertEqual(lab_b_final["rejection_reason"], "Slot reserved for practical exam")

    def test_03_ownership_security_cancel_and_api_isolation(self):
        """3. Students cannot view, spoof, or cancel another student's bookings via backend or API."""
        d3 = (date.today() + timedelta(days=32)).strftime("%Y-%m-%d")
        uid_a = self.user_a["user_id"]
        uid_b = self.user_b["user_id"]

        lab_a = create_booking(
            student_id=uid_a,
            student_name=self.user_a["full_name"],
            lab_id=2,
            booking_date=d3,
            start_time="15:00",
            end_time="17:00",
            status="pending",
            purpose="Protected Booking",
        )
        bid_a = lab_a["booking_id"]

        # 1. Empty student_id must return [] (no name-based leakage)
        self.assertEqual(get_all_student_reservations(student_id="", student_name="Same Name Student"), [])

        # 2. Student B cannot cancel Student A's booking in DB operations
        self.assertFalse(cancel_reservation(bid_a, "Laboratory", owner_id=uid_b))

        # 3. Student B cannot cancel Student A's booking via API /cancel
        r_cancel = self.client.post(
            "/cancel",
            params={"booking_id": bid_a, "service_type": "Laboratory"},
            headers={"X-User-Id": uid_b, "X-User-Role": "Student"},
        )
        self.assertEqual(r_cancel.status_code, 404)

        # 4. Student B cannot read Student A's bookings via API /users/{uid_a}/bookings
        r_get = self.client.get(
            f"/users/{uid_a}/bookings",
            headers={"X-User-Id": uid_b, "X-User-Role": "Student"},
        )
        self.assertEqual(r_get.status_code, 403)

        # 5. Student B cannot spoof Student A's ID on POST /bookings when X-User-Id is Student B
        r_spoof = self.client.post(
            "/bookings",
            json={
                "student_id": uid_a,  # Spoofed attempt
                "student_name": "Spoofer",
                "lab_id": 1,
                "booking_date": d3,
                "start_time": "15:00",
                "end_time": "17:00",
            },
            headers={"X-User-Id": uid_b, "X-User-Role": "Student"},
        )
        self.assertEqual(r_spoof.status_code, 201)
        self.assertEqual(r_spoof.json()["student_id"], uid_b)

        # 6. Student A CAN cancel their own booking
        self.assertTrue(cancel_reservation(bid_a, "Laboratory", owner_id=uid_a))


if __name__ == "__main__":
    unittest.main()
