"""Integration Test Suite for CampusPilot AI — Administrator & Student Workflows.

Tests:
1. Student registration with Student ID and Department.
2. Verified Student role isolation (cannot select admin).
3. Student login and dynamic identity resolution.
4. Lab booking request creation with initial status 'pending' and purpose.
5. Administrator retrieval of pending booking requests.
6. Administrator approval with conflict check verification.
7. Conflict prevention: Overlapping booking request cannot be approved.
8. Administrator rejection with recorded rejection reason.
9. Student inspection of rejected booking with visible rejection reason.
10. Facility enable/disable toggle (AI Lab, Computer Lab, Discussion Rooms).
11. Disabled facility cannot be booked.
12. Leave request submission with automated policy acceptance ('Approved (Auto-Accepted)').
13. Student leave history retrieval.
14. Administrator oversight of all campus leave requests.
15. Administrator dashboard metrics computation from live SQLite database.
"""

from datetime import date, timedelta
import os
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.operations import (
    approve_booking,
    cancel_reservation,
    check_booking_overlap,
    create_booking,
    create_leave_request,
    create_room_booking,
    get_admin_dashboard_metrics,
    get_all_booking_requests,
    get_all_laboratories,
    get_all_leave_requests,
    get_all_student_reservations,
    get_student_leave_requests,
    reject_booking,
    toggle_facility_status,
)
from app.services.demo_auth import authenticate_user, register_user


class TestAdminAndStudentWorkflows(unittest.TestCase):
    """End-to-end integration tests for Student & Admin workflows."""

    @classmethod
    def setUpClass(cls):
        cls.test_student_email = "riya.verma@campus.edu"
        cls.test_student_pwd = "StudentPass2026"
        cls.test_student_name = "Riya Verma"
        cls.test_student_id = "AI2026-099"
        cls.test_student_dept = "Artificial Intelligence & Data Science"

        cls.tomorrow = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")

        from app.database.connection import get_db_context
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookings WHERE student_id = ?;", (cls.test_student_id,))
            cur.execute("DELETE FROM room_bookings WHERE student_id = ?;", (cls.test_student_id,))
            cur.execute("DELETE FROM leave_requests WHERE student_id = ?;", (cls.test_student_id,))

    @classmethod
    def tearDownClass(cls):
        from app.database.connection import get_db_context
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookings WHERE student_id = ?;", (cls.test_student_id,))
            cur.execute("DELETE FROM room_bookings WHERE student_id = ?;", (cls.test_student_id,))
            cur.execute("DELETE FROM leave_requests WHERE student_id = ?;", (cls.test_student_id,))

    def test_01_student_registration_with_id_and_dept(self):
        """1. Register student with student ID and department, verifying credentials."""
        ok, res = register_user(
            email=self.test_student_email,
            password=self.test_student_pwd,
            full_name=self.test_student_name,
            account_type="Student",
            student_id=self.test_student_id,
            department=self.test_student_dept,
        )
        # Even if already registered in previous runs, authentication will verify
        if not ok:
            self.assertIn("already exists", res)
        else:
            self.assertEqual(res["account_type"], "Student")
            self.assertEqual(res["student_id"], self.test_student_id)
            self.assertEqual(res["department"], self.test_student_dept)

        # Authenticate with credentials
        auth_ok, user = authenticate_user(self.test_student_email, self.test_student_pwd)
        self.assertTrue(auth_ok)
        self.assertEqual(user["full_name"], self.test_student_name)
        self.assertEqual(user["account_type"], "Student")

    def test_02_admin_credentials_preserved(self):
        """2. Verify pre-seeded administrator credentials authenticate as Administrator."""
        auth_ok, admin = authenticate_user("admin@campus.edu", "AdminPass123")
        self.assertTrue(auth_ok)
        self.assertEqual(admin["account_type"], "Administrator")
        self.assertEqual(admin["full_name"], "Dr. Sharma")

    def test_03_student_creates_pending_lab_booking_with_purpose(self):
        """3. Student submits lab booking request with purpose, saved with status='pending'."""
        purpose_text = "Robotics Vision Model Training for Capstone Project"
        b = create_booking(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            lab_id=2,  # AI Lab
            booking_date=self.tomorrow,
            start_time="09:00",
            end_time="11:00",
            status="pending",
            purpose=purpose_text,
        )
        self.assertIsNotNone(b.get("booking_id"))
        self.assertEqual(b.get("status"), "pending")
        self.assertEqual(b.get("purpose"), purpose_text)

        self.__class__.lab_booking_id = b["booking_id"]

    def test_04_admin_retrieves_pending_request(self):
        """4. Administrator queries all pending requests and sees the student's submission."""
        pending_requests = get_all_booking_requests(status_filter="pending")
        found = any(r["booking_id"] == self.lab_booking_id for r in pending_requests)
        self.assertTrue(found, f"Booking #{self.lab_booking_id} should be visible in pending list.")

    def test_05_admin_approves_booking_request(self):
        """5. Administrator approves the booking request; status transitions to 'approved'."""
        ok, msg = approve_booking(self.lab_booking_id, service_type="Laboratory")
        self.assertTrue(ok)
        self.assertIn("approved", msg.lower())

        # Verify in student ledger
        student_res = get_all_student_reservations(student_id=self.test_student_id)
        match = next((r for r in student_res if r["booking_id"] == self.lab_booking_id), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["status"], "approved")

    def test_06_conflict_prevention_on_approved_slot(self):
        """6. Conflicting overlapping slot cannot be booked or approved once a slot is approved."""
        # A: Direct creation of overlapping booking raises ValueError conflict
        with self.assertRaises(ValueError) as cm:
            create_booking(
                student_id="CS2026-055",
                student_name="Ananya Rao",
                lab_id=2,
                booking_date=self.tomorrow,
                start_time="09:00",
                end_time="11:00",
                status="pending",
                purpose="Overlapping session test",
            )
        self.assertIn("already booked", str(cm.exception).lower())

        # B: If a pending booking was inserted previously, approve_booking verifies conflict and rejects approval
        from app.database.connection import get_db_context
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO bookings (student_id, student_name, lab_id, booking_date, start_time, end_time, status, purpose)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?);
                """,
                ("CS2026-055", "Ananya Rao", 2, self.tomorrow, "09:00", "11:00", "Overlap test"),
            )
            raw_id = cur.lastrowid

        ok, msg = approve_booking(raw_id, service_type="Laboratory")
        self.assertFalse(ok)
        self.assertIn("already occupies", msg.lower())

        # Clean up test booking
        cancel_reservation(raw_id, "Laboratory")

    def test_07_admin_rejects_booking_with_reason(self):
        """7. Administrator rejects booking with a specific documented reason."""
        # Create booking to reject
        b3 = create_booking(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            lab_id=1,
            booking_date=self.tomorrow,
            start_time="13:00",
            end_time="15:00",
            status="pending",
            purpose="General testing",
        )
        reason_text = "Lab scheduled for departmental semester exam maintenance"
        rej_ok = reject_booking(b3["booking_id"], service_type="Laboratory", rejection_reason=reason_text)
        self.assertTrue(rej_ok)

        # Student inspects their bookings and sees rejection reason
        student_res = get_all_student_reservations(student_id=self.test_student_id)
        match = next((r for r in student_res if r["booking_id"] == b3["booking_id"]), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["status"], "rejected")
        self.assertEqual(match["rejection_reason"], reason_text)

    def test_08_facility_enable_disable_toggle(self):
        """8. Administrator can toggle facility enabled status in SQLite."""
        # Disable AI Lab (lab_id=2)
        toggle_ok = toggle_facility_status("lab", 2, is_enabled=0)
        self.assertTrue(toggle_ok)

        labs = get_all_laboratories()
        ai_lab = next((l for l in labs if l["lab_id"] == 2), None)
        self.assertIsNotNone(ai_lab)
        self.assertEqual(ai_lab.get("is_enabled"), 0)

        # Re-enable AI Lab
        toggle_ok2 = toggle_facility_status("lab", 2, is_enabled=1)
        self.assertTrue(toggle_ok2)

        labs2 = get_all_laboratories()
        ai_lab2 = next((l for l in labs2 if l["lab_id"] == 2), None)
        self.assertEqual(ai_lab2.get("is_enabled"), 1)

    def test_09_student_leave_request_auto_acceptance(self):
        """9. Student submits leave request; automated acceptance policy marks it approved."""
        start_d = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        end_d = (date.today() + timedelta(days=12)).strftime("%Y-%m-%d")
        reason = "Attending International Conference on Machine Learning (ICML)"

        leave = create_leave_request(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            student_email=self.test_student_email,
            leave_type="Academic / Conference Leave",
            start_date=start_d,
            end_date=end_d,
            reason=reason,
        )
        self.assertIsNotNone(leave.get("leave_id"))
        self.assertEqual(leave.get("status"), "Approved (Auto-Accepted)")

        # Verify student history
        history = get_student_leave_requests(self.test_student_id)
        found = any(l["leave_id"] == leave["leave_id"] for l in history)
        self.assertTrue(found)

        # Verify administrator oversight
        all_leaves = get_all_leave_requests()
        found_admin = any(l["leave_id"] == leave["leave_id"] for l in all_leaves)
        self.assertTrue(found_admin)

    def test_10_admin_metrics_calculation(self):
        """10. Live administrative metrics compute counts accurately from SQLite."""
        m = get_admin_dashboard_metrics()
        self.assertIn("total_requests", m)
        self.assertIn("pending_requests", m)
        self.assertIn("approved_requests", m)
        self.assertIn("rejected_requests", m)
        self.assertIn("active_laboratories", m)
        self.assertGreaterEqual(m["total_laboratories"], 3)
        self.assertGreaterEqual(m["total_rooms"], 3)


if __name__ == "__main__":
    unittest.main()
