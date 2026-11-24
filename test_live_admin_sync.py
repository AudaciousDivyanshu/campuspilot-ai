"""Tests for Automatic Live Admin Dashboard Polling & Student Synchronization."""

import unittest
from datetime import date, timedelta
from pathlib import Path

from app.database.connection import get_db_context
from app.database.operations import (
    approve_booking,
    cancel_reservation,
    create_booking,
    create_leave_request,
    get_admin_dashboard_metrics,
    get_all_booking_requests,
    get_all_leave_requests,
    get_all_student_reservations,
    get_student_leave_requests,
    reject_booking,
    update_leave_status,
)


class TestLiveAdminAndStudentSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.student_id = "STU_LIVE_SYNC_2026"
        cls.student_name = "Live Sync Student"
        cls.student_email = "livesync@campus.edu"

    def setUp(self):
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookings WHERE student_id = ?;", (self.student_id,))
            cur.execute("DELETE FROM leave_requests WHERE student_id = ?;", (self.student_id,))

    def tearDown(self):
        with get_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookings WHERE student_id = ?;", (self.student_id,))
            cur.execute("DELETE FROM leave_requests WHERE student_id = ?;", (self.student_id,))

    def test_01_streamlit_fragments_configured_for_5s_polling(self):
        """Verify @st.fragment(run_every='5s') is present on Admin and Student live views."""
        code = Path("frontend/streamlit_app.py").read_text(encoding="utf-8")
        self.assertEqual(code.count('@st.fragment(run_every="5s")'), 6)
        self.assertIn("def render_live_admin_dashboard():", code)
        self.assertIn("def render_live_booking_requests_panel():", code)
        self.assertIn("def render_live_leave_oversight_panel():", code)
        self.assertIn("def render_live_student_overview():", code)
        self.assertIn("def render_live_student_bookings():", code)
        self.assertIn("def render_live_student_leave_history():", code)
        # Ensure live timestamp and notification elements exist
        self.assertIn("Live Auto-Sync Active", code)
        self.assertIn("admin_known_pending_bids", code)
        self.assertIn("admin_known_pending_lids", code)
        # Ensure page navigation inside fragments uses scope="app"
        self.assertIn("st.rerun(scope=\"app\")", code)

    def test_02_fresh_sqlite_polling_ai_lab_and_computer_lab(self):
        """Verify fresh SQLite polling detects new AI Lab and Computer Lab submissions and reflects approvals."""
        base_metrics = get_admin_dashboard_metrics()
        d1 = (date.today() + timedelta(days=25)).strftime("%Y-%m-%d")
        d2 = (date.today() + timedelta(days=26)).strftime("%Y-%m-%d")

        # 1. Student submits AI Lab request
        ai_req = create_booking(
            student_id=self.student_id,
            student_name=self.student_name,
            lab_id=2,  # AI Lab
            booking_date=d1,
            start_time="10:00",
            end_time="12:00",
            status="pending",
            purpose="Live Sync AI Lab Test",
        )
        ai_id = ai_req["booking_id"]

        # 2. Student submits Computer Lab request
        pc_req = create_booking(
            student_id=self.student_id,
            student_name=self.student_name,
            lab_id=1,  # Computer Lab
            booking_date=d2,
            start_time="14:00",
            end_time="16:00",
            status="pending",
            purpose="Live Sync Computer Lab Test",
        )
        pc_id = pc_req["booking_id"]

        # 3. Admin poll reads fresh SQLite data: pending count increased by 2, both appear once
        after_metrics = get_admin_dashboard_metrics()
        self.assertEqual(after_metrics["pending_requests"], base_metrics["pending_requests"] + 2)

        pending_list = get_all_booking_requests(status_filter="pending")
        ai_matches = [r for r in pending_list if r["booking_id"] == ai_id]
        pc_matches = [r for r in pending_list if r["booking_id"] == pc_id]
        self.assertEqual(len(ai_matches), 1)
        self.assertEqual(len(pc_matches), 1)

        # 4. Admin approves AI Lab request and rejects Computer Lab request
        ok_ai, _ = approve_booking(ai_id, "Laboratory")
        self.assertTrue(ok_ai)
        ok_pc = reject_booking(pc_id, "Laboratory", rejection_reason="Scheduled maintenance")
        self.assertTrue(ok_pc)

        # 5. Next poll shows both removed from pending and moved to approved/rejected
        pending_after = get_all_booking_requests(status_filter="pending")
        self.assertFalse(any(r["booking_id"] in (ai_id, pc_id) for r in pending_after))

        final_metrics = get_admin_dashboard_metrics()
        self.assertEqual(final_metrics["pending_requests"], base_metrics["pending_requests"])
        self.assertEqual(final_metrics["approved_requests"], base_metrics["approved_requests"] + 1)
        self.assertEqual(final_metrics["rejected_requests"], base_metrics["rejected_requests"] + 1)

        # 6. Student sync reads fresh SQLite statuses
        s_res = get_all_student_reservations(self.student_id)
        s_ai = next(r for r in s_res if r["booking_id"] == ai_id)
        s_pc = next(r for r in s_res if r["booking_id"] == pc_id)
        self.assertEqual(s_ai["status"], "approved")
        self.assertEqual(s_pc["status"], "rejected")
        self.assertEqual(s_pc["rejection_reason"], "Scheduled maintenance")

    def test_03_fresh_sqlite_polling_leave_request_lifecycle(self):
        """Verify leave request remains pending until admin action and syncs to student."""
        base_metrics = get_admin_dashboard_metrics()
        d_start = (date.today() + timedelta(days=8)).strftime("%Y-%m-%d")
        d_end = (date.today() + timedelta(days=9)).strftime("%Y-%m-%d")

        leave_rec = create_leave_request(
            student_id=self.student_id,
            student_name=self.student_name,
            student_email=self.student_email,
            leave_type="Academic / Conference Leave",
            start_date=d_start,
            end_date=d_end,
            reason="National Hackathon Finals",
        )
        l_id = leave_rec["leave_id"]
        self.assertEqual(leave_rec["status"], "Pending Approval")

        # Admin poll detects new pending leave
        mid_metrics = get_admin_dashboard_metrics()
        self.assertEqual(mid_metrics["pending_leaves"], base_metrics["pending_leaves"] + 1)
        all_leaves = get_all_leave_requests()
        self.assertEqual(len([l for l in all_leaves if l["leave_id"] == l_id]), 1)

        # Admin approves leave
        self.assertTrue(update_leave_status(l_id, "Approved", reviewed_by="Dr. Sharma"))

        # Admin poll reflects updated leave metrics
        end_metrics = get_admin_dashboard_metrics()
        self.assertEqual(end_metrics["pending_leaves"], base_metrics["pending_leaves"])
        self.assertEqual(end_metrics["approved_leaves"], base_metrics["approved_leaves"] + 1)

        # Student poll sees Approved
        s_leaves = get_student_leave_requests(self.student_id)
        target = next(l for l in s_leaves if l["leave_id"] == l_id)
        self.assertEqual(target["status"], "Approved")
        self.assertEqual(target["reviewed_by"], "Dr. Sharma")


if __name__ == "__main__":
    unittest.main()
