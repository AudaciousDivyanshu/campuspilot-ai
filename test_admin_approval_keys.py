"""Comprehensive unit and integration test suite for Administrator Approval Workflows,
button key stability, deduplication, and student-side status persistence.
"""

import os
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.database.connection import get_db_context
from app.database.operations import (
    create_booking,
    approve_booking,
    reject_booking,
    cancel_reservation,
    get_all_booking_requests,
    get_all_student_reservations,
    create_leave_request,
    update_leave_status,
    get_student_leave_requests,
)


class TestAdminApprovalWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_student_id = "STU_ADMIN_TEST_2026"
        cls.test_student_name = "Approval Test Student"
        cls.test_student_email = "approval_test_student@campus.edu"
        cls.tomorrow = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")

    def setUp(self):
        # Clean up any leftover test data
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookings WHERE student_id = ?;", (self.test_student_id,))
            cur.execute("DELETE FROM leave_requests WHERE student_id = ?;", (self.test_student_id,))

    def test_01_button_key_conventions_in_streamlit_app(self):
        """Verify that frontend/streamlit_app.py uses stable, unique keys matching specifications."""
        frontend_path = Path("frontend/streamlit_app.py")
        self.assertTrue(frontend_path.exists())
        code = frontend_path.read_text(encoding="utf-8")

        # Verify required key patterns exist
        self.assertIn('key=f"approve_ai_lab_{b_id}"', code)
        self.assertIn('key=f"reject_ai_lab_{b_id}"', code)
        self.assertIn('key=f"rejection_reason_ai_lab_{b_id}"', code)

        self.assertIn('key=f"approve_computer_lab_{b_id}"', code)
        self.assertIn('key=f"reject_computer_lab_{b_id}"', code)
        self.assertIn('key=f"rejection_reason_computer_lab_{b_id}"', code)

        self.assertIn('key=f"approve_leave_{l_id}"', code)
        self.assertIn('key=f"reject_leave_{l_id}"', code)
        self.assertIn('key=f"rejection_reason_leave_{l_id}"', code)

        # Verify old buggy keys are completely removed
        self.assertNotIn('appr_dash_ai_', code)
        self.assertNotIn('appr_dash_pc_', code)
        self.assertNotIn('appr_dash_l_', code)

    def test_02_database_join_does_not_duplicate_bookings(self):
        """Verify that get_all_booking_requests does not return duplicate rows for a booking,
        even if a student has multiple entries in student_profiles."""
        # Insert multiple duplicate profiles for a dummy student to simulate legacy duplicate profile rows
        dup_name = "MultiProfile User"
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM student_profiles WHERE full_name = ?;", (dup_name,))
            cur.execute(
                "INSERT INTO student_profiles (user_id, full_name, email, department) VALUES (?, ?, ?, ?);",
                ("mp_user_1", dup_name, "mp1@campus.edu", "Computer Science & Engineering"),
            )
            cur.execute(
                "INSERT INTO student_profiles (user_id, full_name, email, department) VALUES (?, ?, ?, ?);",
                ("mp_user_2", dup_name, "mp2@campus.edu", "Artificial Intelligence & Data Science"),
            )
            cur.execute(
                "INSERT INTO student_profiles (user_id, full_name, email, department) VALUES (?, ?, ?, ?);",
                ("mp_user_3", dup_name, "mp3@campus.edu", "Information Technology"),
            )

        # Create 1 lab booking for this user
        test_d = (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
        b = create_booking(
            student_id="mp_user_1",
            student_name=dup_name,
            lab_id=2,  # AI Lab
            booking_date=test_d,
            start_time="10:00",
            end_time="12:00",
            status="pending",
            purpose="Deduplication Verification Practical",
        )
        b_id = b["booking_id"]

        try:
            # Query all pending requests
            all_pending = get_all_booking_requests(status_filter="pending")
            matching = [r for r in all_pending if r["booking_id"] == b_id]

            # MUST return exactly 1 record, NOT 3
            self.assertEqual(len(matching), 1, f"Expected 1 row for booking #{b_id}, got {len(matching)}")
            self.assertEqual(matching[0]["booking_id"], b_id)
            self.assertEqual(matching[0]["student_name"], dup_name)
        finally:
            # Cleanup
            cancel_reservation(b_id, "Laboratory")
            with get_db_context() as conn:
                conn.cursor().execute("DELETE FROM student_profiles WHERE full_name = ?;", (dup_name,))

    def test_03_ai_lab_approval_workflow_and_student_refresh(self):
        """3. End-to-end: AI Lab request created as pending, approved by admin, verified in SQLite and student view."""
        test_d = (date.today() + timedelta(days=12)).strftime("%Y-%m-%d")
        b = create_booking(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            lab_id=2,  # AI Lab
            booking_date=test_d,
            start_time="14:00",
            end_time="16:00",
            status="pending",
            purpose="Autonomous Reinforcement Learning Model Training",
        )
        b_id = b["booking_id"]

        # 1. Verify pending in student reservations
        s_res = get_all_student_reservations(self.test_student_id)
        match = next((x for x in s_res if x["booking_id"] == b_id), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["status"], "pending")

        # 2. Administrator approves the AI Lab booking
        ok, msg = approve_booking(b_id, service_type="Laboratory")
        self.assertTrue(ok, f"Approval failed: {msg}")
        self.assertIn("approved", msg.lower())

        # 3. Verify status changed to 'approved' in SQLite student view
        s_res_after = get_all_student_reservations(self.test_student_id)
        match_after = next((x for x in s_res_after if x["booking_id"] == b_id), None)
        self.assertIsNotNone(match_after)
        self.assertEqual(match_after["status"], "approved")

        # 4. Cannot be approved twice
        ok_dup, msg_dup = approve_booking(b_id, service_type="Laboratory")
        self.assertFalse(ok_dup)
        self.assertIn("already been approved", msg_dup)

        # 5. Cannot be rejected after approval
        rej_after_appr = reject_booking(b_id, service_type="Laboratory", rejection_reason="Too late")
        self.assertFalse(rej_after_appr)

    def test_04_computer_lab_rejection_workflow_with_reason(self):
        """4. End-to-end: Computer Lab request created as pending, rejected by admin with reason, verified in student ledger."""
        test_d = (date.today() + timedelta(days=13)).strftime("%Y-%m-%d")
        b = create_booking(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            lab_id=1,  # Computer Lab
            booking_date=test_d,
            start_time="10:00",
            end_time="12:00",
            status="pending",
            purpose="Web Development Framework Practical",
        )
        b_id = b["booking_id"]

        # Administrator rejects the request with documented reason
        doc_reason = "Laboratory reserved for University End-Term Practical Examinations"
        ok = reject_booking(b_id, service_type="Laboratory", rejection_reason=doc_reason)
        self.assertTrue(ok)

        # Student verifies rejection and reason in reservations
        s_res = get_all_student_reservations(self.test_student_id)
        match = next((x for x in s_res if x["booking_id"] == b_id), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["status"], "rejected")
        self.assertEqual(match["rejection_reason"], doc_reason)

        # Cannot be approved after rejection
        ok_appr, msg_appr = approve_booking(b_id, service_type="Laboratory")
        self.assertFalse(ok_appr)
        self.assertIn("already been rejected", msg_appr)

        # Cannot be rejected twice
        ok_rej2 = reject_booking(b_id, service_type="Laboratory", rejection_reason="Second reject")
        self.assertFalse(ok_rej2)

    def test_05_leave_request_approval_and_rejection_persistence(self):
        """5. End-to-end: Student submits leave request, admin approves, student sees Approved.
        Then second leave request submitted, admin rejects with reason, student sees Rejected."""
        d_start = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        d_end = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

        # Request 1: Approval flow
        leave_1 = create_leave_request(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            student_email=self.test_student_email,
            leave_type="Academic / Conference Leave",
            start_date=d_start,
            end_date=d_end,
            reason="Presenting paper at IEEE International Conference",
        )
        l_id_1 = leave_1["leave_id"]
        self.assertEqual(leave_1["status"], "Pending Approval")

        # Admin approves
        ok_appr = update_leave_status(l_id_1, "Approved", reviewed_by="Dr. Sharma")
        self.assertTrue(ok_appr)

        # Verify student sees Approved
        leaves = get_student_leave_requests(self.test_student_id)
        match_1 = next((l for l in leaves if l["leave_id"] == l_id_1), None)
        self.assertIsNotNone(match_1)
        self.assertEqual(match_1["status"], "Approved")
        self.assertEqual(match_1["reviewed_by"], "Dr. Sharma")

        # Cannot re-approve with same status
        self.assertFalse(update_leave_status(l_id_1, "Approved", reviewed_by="Dr. Sharma"))

        # Request 2: Rejection flow
        leave_2 = create_leave_request(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            student_email=self.test_student_email,
            leave_type="Personal / Family Emergency",
            start_date=d_start,
            end_date=d_end,
            reason="Attending family reunion during midterms",
        )
        l_id_2 = leave_2["leave_id"]
        rej_note = "Leave declined due to mandatory practical evaluations during this timeframe"

        # Admin rejects
        ok_rej = update_leave_status(l_id_2, "Rejected", rejection_reason=rej_note, reviewed_by="Dr. Sharma")
        self.assertTrue(ok_rej)

        # Verify student sees Rejected and reason
        leaves_after = get_student_leave_requests(self.test_student_id)
        match_2 = next((l for l in leaves_after if l["leave_id"] == l_id_2), None)
        self.assertIsNotNone(match_2)
        self.assertEqual(match_2["status"], "Rejected")
        self.assertEqual(match_2["rejection_reason"], rej_note)


if __name__ == "__main__":
    unittest.main()
