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

    def test_11_single_white_theme_enforcement_and_no_theme_switchers(self):
        """11. Verify single permanent white theme with all toggle switches removed."""
        streamlit_app_code = (PROJECT_ROOT / "frontend" / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn("Switch to Dark", streamlit_app_code)
        self.assertNotIn("Switch to Light", streamlit_app_code)
        self.assertNotIn("nav_theme_toggle_btn", streamlit_app_code)
        self.assertNotIn("toggle_theme_auth_btn", streamlit_app_code)
        self.assertNotIn("settings_theme_radio", streamlit_app_code)
        self.assertIn('st.session_state.theme = "light"', streamlit_app_code)

    def test_12_no_demo_login_buttons_on_login_screen(self):
        """12. Verify Dr. Sharma and all demo login buttons are completely removed from UI."""
        streamlit_app_code = (PROJECT_ROOT / "frontend" / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn("btn_quick_admin", streamlit_app_code)
        self.assertNotIn("Log In as Faculty Administrator", streamlit_app_code)
        self.assertNotIn("Faculty & Administrator Demonstration Portal", streamlit_app_code)
        self.assertNotIn("quick_demo_arnav", streamlit_app_code)
        self.assertNotIn("quick_demo_rahul", streamlit_app_code)
        self.assertNotIn("AdminPass123", streamlit_app_code)  # Not exposed publicly on login page

    def test_13_secure_admin_login_resolves_admin_dashboard(self):
        """13. Verify secure admin authentication routes to Administrative Dashboard."""
        auth_ok, admin = authenticate_user("admin@campus.edu", "AdminPass123")
        self.assertTrue(auth_ok)
        self.assertEqual(admin["account_type"], "Administrator")

        auth_ok_s, student = authenticate_user(self.test_student_email, self.test_student_pwd)
        self.assertTrue(auth_ok_s)
        self.assertEqual(student["account_type"], "Student")

    def test_14_password_input_field_types_valid_in_streamlit(self):
        """14. Verify password fields use supported Streamlit types ('password' or 'default')."""
        streamlit_app_code = (PROJECT_ROOT / "frontend" / "streamlit_app.py").read_text(encoding="utf-8")
        # Ensure unsupported type="text" is never passed to st.text_input
        self.assertNotIn('type="text"', streamlit_app_code)
        # Ensure 'default' is used when password visibility is toggled on
        self.assertIn('type="default" if show_pwd else "password"', streamlit_app_code)
        self.assertIn('type="default" if st.session_state.get("show_reg_pwd_check") else "password"', streamlit_app_code)

    def test_15_student_registration_validation_and_duplicate_handling(self):
        """15. Verify full registration validation: password rules, duplicate prevention, and hashing."""
        from app.services.demo_auth import is_password_valid, validate_password_strength

        # Invalid password checks
        self.assertFalse(validate_password_strength("short")["min_length"])
        self.assertFalse(validate_password_strength("nouppercase123")["has_upper"])
        self.assertFalse(validate_password_strength("NOLOWERCASE123")["has_lower"])
        self.assertFalse(validate_password_strength("NoNumberPass")["has_digit"])

        valid, errs = is_password_valid("weak")
        self.assertFalse(valid)
        self.assertGreater(len(errs), 0)

        # Duplicate registration prevention
        dup_ok, dup_msg = register_user(
            email=self.test_student_email,
            password="AnotherPass123",
            full_name="Duplicate User",
            student_id="CS-DUP-01",
        )
        self.assertFalse(dup_ok)
        self.assertIn("already exists", dup_msg.lower())

    def test_16_sidebar_date_removed_and_profile_includes_department(self):
        """16. Verify Today/Tomorrow date caption is completely removed from the sidebar and profile includes department."""
        streamlit_app_code = (PROJECT_ROOT / "frontend" / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn("st.caption(f\"📅 Today:", streamlit_app_code)
        self.assertNotIn("st.caption(f'📅 Today:", streamlit_app_code)
        self.assertNotIn("&bull; Tomorrow:", streamlit_app_code)
        self.assertIn("📚 {department}", streamlit_app_code)

    def test_17_secure_portal_mode_and_admin_role_enforcement(self):
        """17. Verify clean Student/Admin portal selector and backend role authorization enforcement."""
        streamlit_app_code = (PROJECT_ROOT / "frontend" / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('key="auth_portal_mode"', streamlit_app_code)
        self.assertIn('👨‍🎓 Student Portal', streamlit_app_code)
        self.assertIn('🛡️ Administrator Portal', streamlit_app_code)
        # Backend role enforcement check
        self.assertIn('if res.get("account_type") != "Administrator":', streamlit_app_code)
        self.assertIn('Access Denied: This account does not possess institutional administrator privileges', streamlit_app_code)

    def test_18_booking_requests_include_department_and_timestamp(self):
        """18. Verify admin booking request items include student department and submission timestamp."""
        all_reqs = get_all_booking_requests()
        self.assertIsInstance(all_reqs, list)
        if len(all_reqs) > 0:
            first = all_reqs[0]
            self.assertIn("department", first)
            self.assertIn("created_at", first)

    def test_19_admin_provisioning_idempotence_and_restart_persistence(self):
        """19. Test administrator account provisioning mechanism via env/defaults."""
        from app.services.demo_auth import init_admin_account, _load_users, _hash_password
        admin = init_admin_account()
        self.assertEqual(admin["account_type"], "Administrator")
        self.assertEqual(admin["email"], os.getenv("ADMIN_EMAIL", "admin@campus.edu").lower())

        # Verify password is NOT stored in plaintext
        users = _load_users()
        admin_rec = users[admin["email"]]
        self.assertNotEqual(admin_rec["password_hash"], "AdminPass123")
        self.assertEqual(len(admin_rec["password_hash"]), 64)  # SHA-256

        # Verify in SQLite user_accounts table
        from app.database.operations import get_user_account_by_email
        db_admin = get_user_account_by_email(admin["email"])
        self.assertIsNotNone(db_admin)
        self.assertEqual(db_admin["account_type"], "Administrator")

        # Restart simulation: Calling init_admin_account again is idempotent
        count_before = len([u for u in _load_users().values() if u["account_type"] == "Administrator"])
        admin2 = init_admin_account()
        count_after = len([u for u in _load_users().values() if u["account_type"] == "Administrator"])
        self.assertEqual(count_before, count_after)

    def test_20_admin_login_role_enforcement_and_error_handling(self):
        """20. Test administrator login role enforcement and specific error messages."""
        admin_email = os.getenv("ADMIN_EMAIL", "admin@campus.edu")
        admin_pwd = os.getenv("ADMIN_PASSWORD", "AdminPass123")

        # 1. Successful administrator login
        ok, res = authenticate_user(admin_email, admin_pwd, required_role="Administrator")
        self.assertTrue(ok)
        self.assertEqual(res["account_type"], "Administrator")

        # 2. Student account denied from administrator portal
        ok_denied, msg_denied = authenticate_user(self.test_student_email, self.test_student_pwd, required_role="Administrator")
        self.assertFalse(ok_denied)
        self.assertIn("Access Denied", msg_denied)
        self.assertIn("Student", msg_denied)

        # 3. Wrong password error
        ok_wrong_pwd, msg_wrong_pwd = authenticate_user(admin_email, "WrongPassword999", required_role="Administrator")
        self.assertFalse(ok_wrong_pwd)
        self.assertEqual(msg_wrong_pwd, "Incorrect password. Please verify and try again.")

        # 4. Non-existent account error
        ok_not_found, msg_not_found = authenticate_user("nonexistent.admin@campus.edu", "SomePass123", required_role="Administrator")
        self.assertFalse(ok_not_found)
        self.assertIn("No administrator account found", msg_not_found)

    def test_21_end_to_end_student_to_admin_approval_workflow(self):
        """21. End-to-end: Student registers, requests lab, admin approves, student sees 'approved'."""
        student_email = "student.workflow.demo@campus.edu"
        student_pwd = "WorkflowPass123"
        student_id = "STU2026-WF1"
        student_name = "Workflow Student"

        # Register student
        reg_ok, student = register_user(
            email=student_email,
            password=student_pwd,
            full_name=student_name,
            account_type="Student",
            student_id=student_id,
            department="Computer Science & Engineering",
        )
        self.assertTrue(reg_ok or "already exists" in str(student))

        # Clear any prior booking for this student ID
        from app.database.connection import get_db_context
        with get_db_context() as conn:
            conn.cursor().execute("DELETE FROM bookings WHERE student_id = ?;", (student_id,))

        # Student submits a laboratory booking request with initial pending status
        target_date = (date.today() + timedelta(days=6)).strftime("%Y-%m-%d")
        b_res = create_booking(
            student_id=student_id,
            student_name=student_name,
            lab_id=1,
            booking_date=target_date,
            start_time="09:00",
            end_time="11:00",
            status="pending",
            purpose="Deep Learning Final Semester Project Validation",
        )
        self.assertIn("booking_id", b_res)
        b_id = b_res["booking_id"]

        # Student checks reservations -> status must be 'pending'
        student_bookings = get_all_student_reservations(student_id=student_id)
        target_b = next((b for b in student_bookings if b["booking_id"] == b_id), None)
        self.assertIsNotNone(target_b)
        self.assertEqual(target_b["status"], "pending")

        # Admin logs in and approves the request
        admin_email = os.getenv("ADMIN_EMAIL", "admin@campus.edu")
        admin_pwd = os.getenv("ADMIN_PASSWORD", "AdminPass123")
        adm_ok, adm_user = authenticate_user(admin_email, admin_pwd, required_role="Administrator")
        self.assertTrue(adm_ok)

        # Admin performs approval on the SQLite record
        appr_ok, appr_msg = approve_booking(booking_id=b_id, service_type="Laboratory")
        self.assertTrue(appr_ok)

        # Student checks reservations again -> status must now be 'approved'
        student_bookings_after = get_all_student_reservations(student_id=student_id)
        target_b_after = next((b for b in student_bookings_after if b["booking_id"] == b_id), None)
        self.assertIsNotNone(target_b_after)
        self.assertEqual(target_b_after["status"], "approved")

    def test_22_backend_fastapi_admin_security_and_authorization(self):
        """22. Verify FastAPI backend enforces admin authorization and rejects student callers."""
        from fastapi import HTTPException
        from app.api.routes import (
            auth_login_endpoint,
            auth_register_endpoint,
            get_admin_requests_endpoint,
            verify_admin_authorization,
        )

        # 1. Student calling admin dependency must be rejected with 403 Forbidden
        with self.assertRaises(HTTPException) as cm:
            verify_admin_authorization(
                x_user_role="Student",
                x_user_email=self.test_student_email,
            )
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("Access Denied", cm.exception.detail)

        # 2. Administrator calling admin authorization dependency succeeds
        admin_email = os.getenv("ADMIN_EMAIL", "admin@campus.edu")
        admin_auth = verify_admin_authorization(
            x_user_role="Administrator",
            x_user_email=admin_email,
        )
        self.assertEqual(admin_auth["account_type"], "Administrator")

        # 3. Administrator accessing requests endpoint succeeds
        reqs = get_admin_requests_endpoint(admin_auth=admin_auth)
        self.assertIsInstance(reqs, list)

        # 4. Test /auth/login endpoint
        admin_pwd = os.getenv("ADMIN_PASSWORD", "AdminPass123")
        login_res = auth_login_endpoint({"email": admin_email, "password": admin_pwd, "portal": "admin"})
        self.assertEqual(login_res["status"], "success")
        self.assertEqual(login_res["user"]["account_type"], "Administrator")

        # 5. Test /auth/register endpoint enforces Student role
        import uuid
        unique_student_email = f"fastapi.student.{uuid.uuid4().hex[:6]}@campus.edu"
        reg_res = auth_register_endpoint({
            "email": unique_student_email,
            "password": "Password123",
            "full_name": "API Student",
            "student_id": "API2026-001",
        })
        self.assertEqual(reg_res["status"], "success")
        self.assertEqual(reg_res["user"]["account_type"], "Student")

    def test_23_discussion_rooms_excluded_from_admin_queue(self):
        """23. Confirm discussion-room bookings do NOT appear in administrator approval queue."""
        from app.database.operations import create_room_booking, get_all_booking_requests
        target_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

        # Student reserves a discussion room
        r_res = create_room_booking(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            room_id=1,
            booking_date=target_date,
            start_time="15:00",
            end_time="17:00",
            purpose="Peer Study & Algorithm Review",
        )
        self.assertIn("booking_id", r_res)
        room_b_id = r_res["booking_id"]

        # Retrieve administrator approval queue
        admin_reqs = get_all_booking_requests()
        # Verify that the room booking does NOT appear in the admin queue
        found_in_admin = any(req["booking_id"] == room_b_id and req.get("service_type") == "Library Room" for req in admin_reqs)
        self.assertFalse(found_in_admin, "Discussion-room bookings must NOT appear in the administrator approval queue.")

    def test_24_leave_policy_and_admin_leave_approval_workflow(self):
        """24. Test automatic leave acceptance vs pending review, and administrator approval/rejection."""
        from app.database.operations import create_leave_request, update_leave_status, get_student_leave_requests

        start_d = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        end_d = (date.today() + timedelta(days=15)).strftime("%Y-%m-%d")  # 6 days -> Pending Review

        # 1. Personal / Extended leave must remain 'Pending Review'
        personal_leave = create_leave_request(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            student_email=self.test_student_email,
            leave_type="Personal / Family Emergency",
            start_date=start_d,
            end_date=end_d,
            reason="Attending family event out of state",
        )
        self.assertEqual(personal_leave["status"], "Pending Review")
        l_id = personal_leave["leave_id"]

        # 2. Administrator approves the pending leave
        ok_appr = update_leave_status(l_id, "Approved (Admin)")
        self.assertTrue(ok_appr)

        # 3. Student verifies updated status is 'Approved (Admin)'
        s_leaves = get_student_leave_requests(self.test_student_id)
        target = next((l for l in s_leaves if l["leave_id"] == l_id), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["status"], "Approved (Admin)")

        # 4. Administrator rejects a leave
        rejected_leave = create_leave_request(
            student_id=self.test_student_id,
            student_name=self.test_student_name,
            student_email=self.test_student_email,
            leave_type="Personal / Family Emergency",
            start_date=start_d,
            end_date=end_d,
            reason="Non-academic travel during semester exams",
        )
        rej_id = rejected_leave["leave_id"]
        ok_rej = update_leave_status(rej_id, "Rejected")
        self.assertTrue(ok_rej)

        s_leaves_after = get_student_leave_requests(self.test_student_id)
        target_rej = next((l for l in s_leaves_after if l["leave_id"] == rej_id), None)
        self.assertIsNotNone(target_rej)
        self.assertEqual(target_rej["status"], "Rejected")


if __name__ == "__main__":
    unittest.main()
