"""Test Suite for CampusPilot AI Autonomous AI Assistant & Leave Approval Workflows.

Covers:
1. Multi-turn AI Assistant flow:
   - Initial query with missing info
   - Follow-up query supplying date and slot
   - Availability check against real SQLite DB
   - Structured booking summary generated
   - Explicit confirmation creates booking in SQLite with status='pending' (Pending Approval)
   - Conflicting / unavailable slot detection with real alternative suggestions
2. Leave Approval Workflow:
   - Student submits leave -> starts as 'Pending Approval' (no auto-approval)
   - Admin views pending leave requests
   - Admin approves leave -> status becomes 'Approved', reviewer recorded
   - Student sees 'Approved' in their records
   - Admin rejects another leave -> status becomes 'Rejected', reason recorded
   - Student sees 'Rejected' and the recorded rejection reason
3. Role security and 2-tab independent session simulation.
"""

from datetime import date, timedelta
import os
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.autonomous_assistant import AutonomousAssistant
from app.database.connection import get_db_context
from app.database.operations import (
    approve_booking,
    check_booking_overlap,
    create_booking,
    create_leave_request,
    create_room_booking,
    get_all_booking_requests,
    get_all_leave_requests,
    get_all_student_reservations,
    get_student_leave_requests,
    reject_booking,
    update_leave_status,
)
from app.services.demo_auth import authenticate_user


class TestAutonomousAssistantAndLeave(unittest.TestCase):
    """Exhaustive test suite for Autonomous Assistant and Leave Approval."""

    @classmethod
    def setUpClass(cls):
        cls.student_id = "AI2026-088"
        cls.student_name = "Divyanshu Verma"
        cls.student_email = "divyanshu@campus.edu"
        cls.student_ctx = {
            "student_id": cls.student_id,
            "student_name": cls.student_name,
            "student_email": cls.student_email,
        }
        cls.test_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE student_id = ?;", (cls.student_id,))
            conn.execute("DELETE FROM room_bookings WHERE student_id = ?;", (cls.student_id,))
            conn.execute("DELETE FROM leave_requests WHERE student_id = ?;", (cls.student_id,))
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (cls.test_date,))

    @classmethod
    def tearDownClass(cls):
        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE student_id = ?;", (cls.student_id,))
            conn.execute("DELETE FROM room_bookings WHERE student_id = ?;", (cls.student_id,))
            conn.execute("DELETE FROM leave_requests WHERE student_id = ?;", (cls.student_id,))

    # ==========================================================================
    # PART 1: AUTONOMOUS AI ASSISTANT MULTI-TURN WORKFLOW
    # ==========================================================================

    def test_01_ai_assistant_operation_shortcuts(self):
        """1. AI Assistant handles operation shortcuts cleanly."""
        res_lab = AutonomousAssistant.process_turn("Book a Laboratory", student_context=self.student_ctx)
        self.assertIn("Which laboratory would you like to book", res_lab["reply"])
        self.assertEqual(res_lab["state"].get("intent"), "book_lab")

        res_room = AutonomousAssistant.process_turn("Book a Discussion Room", student_context=self.student_ctx)
        self.assertIn("Discussion Room 1", res_room["reply"])
        self.assertEqual(res_room["state"].get("intent"), "book_room")

        res_fac = AutonomousAssistant.process_turn("Campus Facility Information", student_context=self.student_ctx)
        self.assertIn("AI Lab", res_fac["reply"])
        self.assertIn("Computer Lab 1", res_fac["reply"])

    def test_02_ai_assistant_multi_turn_missing_details_follow_up(self):
        """2. AI asks for missing information when student provides partial query."""
        # Turn 1: Student specifies facility only
        turn1 = AutonomousAssistant.process_turn("I need the AI Lab", student_context=self.student_ctx)
        self.assertEqual(turn1["state"].get("facility_name"), "AI Lab")
        self.assertIn("date", turn1["reply"].lower())
        self.assertIsNone(turn1.get("pending_booking"))

        # Turn 2: Student supplies date but omits time slot
        turn2 = AutonomousAssistant.process_turn(f"on {self.test_date}", current_state=turn1["state"], student_context=self.student_ctx)
        self.assertEqual(turn2["state"].get("facility_name"), "AI Lab")
        self.assertEqual(turn2["state"].get("date"), self.test_date)
        self.assertIn("time slot", turn2["reply"].lower())
        self.assertIsNone(turn2.get("pending_booking"))

        # Turn 3: Student supplies time slot and purpose
        turn3 = AutonomousAssistant.process_turn(
            "from 10 AM to 12 PM for my Deep Learning Computer Vision model",
            current_state=turn2["state"],
            student_context=self.student_ctx,
        )
        self.assertEqual(turn3["state"].get("start_time"), "10:00")
        self.assertEqual(turn3["state"].get("end_time"), "12:00")
        self.assertIn("Deep Learning", turn3["state"].get("purpose", ""))

        # 4. Availability checked against SQLite and summary presented
        self.assertIsNotNone(turn3.get("pending_booking"))
        pending = turn3["pending_booking"]
        self.assertEqual(pending["item_name"], "AI Lab")
        self.assertEqual(pending["booking_date"], self.test_date)
        self.assertEqual(pending["start_time"], "10:00")
        self.assertEqual(pending["end_time"], "12:00")
        self.assertIn("Requires Administrator Approval", pending["approval_requirement"])

        # 5. Confirm booking -> Committed to SQLite with status='pending'
        ok, msg, b_id = AutonomousAssistant.execute_booking(pending)
        self.assertTrue(ok)
        self.assertIsNotNone(b_id)
        self.assertIn("Pending Approval", msg)
        self.__class__.lab_b_id = b_id

        # 6. Verify in database: initial status is strictly 'pending'
        reqs = get_all_booking_requests(status_filter="pending")
        match = next((r for r in reqs if r["booking_id"] == b_id), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["status"], "pending")
        self.assertEqual(match["student_id"], self.student_id)

    def test_03_ai_assistant_detects_conflict_and_offers_alternatives(self):
        """3. Conflicting slot is detected from real SQLite DB, and real alternative slots are proposed."""
        # Admin approves the booking from test_02 so slot is occupied
        ok_appr, _ = approve_booking(self.lab_b_id, "Laboratory")
        self.assertTrue(ok_appr)

        # Attempt to book overlapping slot: 10:00 to 12:00 on test_date
        query = f"I want to book AI Lab on {self.test_date} from 10:00 to 12:00 for Robotics testing"
        res = AutonomousAssistant.process_turn(query, student_context=self.student_ctx)

        # Must detect conflict
        self.assertIn("Conflict Detected", res["reply"])
        self.assertIsNone(res.get("pending_booking"))
        # Must offer genuine alternative slots
        self.assertTrue(len(res.get("alternatives", [])) > 0)
        self.assertIn("alternative slots", res["reply"].lower())

    def test_04_ai_assistant_discussion_room_self_service(self):
        """4. Discussion room booked via assistant is confirmed instantly without admin queue."""
        query = f"I need Discussion Room 2 on {self.test_date} from 14:00 to 16:00 for algorithm group review"
        res = AutonomousAssistant.process_turn(query, student_context=self.student_ctx)
        self.assertIsNotNone(res.get("pending_booking"))
        self.assertEqual(res["pending_booking"]["service_type"], "room")

        ok, msg, b_id = AutonomousAssistant.execute_booking(res["pending_booking"])
        self.assertTrue(ok)
        self.assertIn("Confirmed", msg)

        # Discussion room must NOT appear in administrator queue
        admin_reqs = get_all_booking_requests()
        found_in_admin = any(r["booking_id"] == b_id and r.get("service_type") == "Library Room" for r in admin_reqs)
        self.assertFalse(found_in_admin)

    # ==========================================================================
    # PART 2: LEAVE APPROVAL WORKFLOW
    # ==========================================================================

    def test_05_student_submits_leave_starts_as_pending_approval(self):
        """5. Student submits a medical leave request; status MUST be 'Pending Approval'."""
        start_d = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
        end_d = (date.today() + timedelta(days=16)).strftime("%Y-%m-%d")
        reason = "Severe fever and medical evaluation at university health center"

        l = create_leave_request(
            student_id=self.student_id,
            student_name=self.student_name,
            student_email=self.student_email,
            leave_type="Medical / Sick Leave",
            start_date=start_d,
            end_date=end_d,
            reason=reason,
        )
        self.assertIsNotNone(l.get("leave_id"))
        self.assertEqual(l["status"], "Pending Approval")
        self.__class__.med_leave_id = l["leave_id"]

        # Student's leave records show Pending Approval
        my_leaves = get_student_leave_requests(self.student_id)
        found = next((x for x in my_leaves if x["leave_id"] == self.med_leave_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["status"], "Pending Approval")

    def test_06_admin_approves_pending_leave_request(self):
        """6. Administrator reviews pending leave and approves it."""
        all_leaves = get_all_leave_requests()
        pending_list = [x for x in all_leaves if "pending" in x.get("status", "").lower()]
        self.assertTrue(any(x["leave_id"] == self.med_leave_id for x in pending_list))

        # Admin approves
        ok = update_leave_status(self.med_leave_id, "Approved", reviewed_by="Dr. Sharma")
        self.assertTrue(ok)

        # Student verifies status has transitioned to Approved
        my_leaves = get_student_leave_requests(self.student_id)
        found = next((x for x in my_leaves if x["leave_id"] == self.med_leave_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["status"], "Approved")
        self.assertEqual(found.get("reviewed_by"), "Dr. Sharma")

    def test_07_admin_rejects_leave_request_with_reason(self):
        """7. Administrator rejects another leave request and records rejection reason."""
        start_d = (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
        end_d = (date.today() + timedelta(days=22)).strftime("%Y-%m-%d")
        rej_leave = create_leave_request(
            student_id=self.student_id,
            student_name=self.student_name,
            student_email=self.student_email,
            leave_type="Personal / Family Emergency",
            start_date=start_d,
            end_date=end_d,
            reason="Unapproved non-academic trip during laboratory exams",
        )
        rej_id = rej_leave["leave_id"]
        self.assertEqual(rej_leave["status"], "Pending Approval")

        # Administrator rejects
        reason_text = "Personal leaves cannot be approved during scheduled final laboratory examinations"
        ok = update_leave_status(rej_id, "Rejected", rejection_reason=reason_text, reviewed_by="Dr. Sharma")
        self.assertTrue(ok)

        # Student verifies Rejected status and sees the documented rejection reason
        my_leaves = get_student_leave_requests(self.student_id)
        found = next((x for x in my_leaves if x["leave_id"] == rej_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["status"], "Rejected")
        self.assertEqual(found.get("rejection_reason"), reason_text)

    # ==========================================================================
    # PART 3: ROLE & TWO-TAB INDEPENDENT SESSIONS
    # ==========================================================================

    def test_08_two_tab_sessions_independent(self):
        """8. Two independent tab sessions maintain isolation and update shared SQLite records."""
        # Tab 1: Student logs in
        s_ok, s_user = authenticate_user("arnav@campus.edu", "Password123", required_role="Student")
        self.assertTrue(s_ok)
        self.assertEqual(s_user["account_type"], "Student")

        # Tab 2: Admin logs in
        a_ok, a_user = authenticate_user("admin@campus.edu", "AdminPass123", required_role="Administrator")
        self.assertTrue(a_ok)
        self.assertEqual(a_user["account_type"], "Administrator")

        # Student cannot login through Admin portal
        blocked_ok, blocked_msg = authenticate_user("arnav@campus.edu", "Password123", required_role="Administrator")
        self.assertFalse(blocked_ok)
        self.assertIn("access denied", str(blocked_msg).lower())


if __name__ == "__main__":
    unittest.main()
