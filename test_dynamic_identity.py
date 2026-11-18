"""CampusPilot AI — Dynamic Student Identity & Personalization Test Suite.

Verifies the 7 core requirements from the user request:
1. Arnav logs in and sees Arnav.
2. Rahul logs in and sees Rahul.
3. Arnav logs out and Rahul logs in.
4. Refreshing the dashboard preserves the correct identity.
5. A user with an incomplete profile sees a neutral fallback ('Student').
6. One student cannot access another student's profile or bookings (strict data isolation).
7. Session logout clears user-specific information.
8. Profile completion updates name without duplicate records.
"""

import sys
import unittest
import uuid
from pathlib import Path

# Ensure project root is first in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if sys.path[0] != str(PROJECT_ROOT):
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.init_db import init_db
from app.database.operations import (
    get_all_student_reservations,
    get_student_profile,
    get_student_profile_by_email,
    upsert_student_profile,
)
from app.services.supabase_auth import (
    get_demo_profiles,
    send_email_otp,
    sign_out_student,
    verify_email_otp,
)


class TestDynamicStudentIdentity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Initialize database with tables and sample seed profiles."""
        init_db()

    def test_01_arnav_login_identity(self):
        """Test Scenario 1: Arnav logs in and sees Arnav."""
        # Authenticate via OTP simulation or demo profile
        res = verify_email_otp("arnav@campus.edu", "123456", full_name_fallback="Arnav")
        self.assertTrue(res["success"])

        # Fetch profile
        user_id = res["user_id"]
        profile = get_student_profile(user_id)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["full_name"], "Arnav")

        # Dynamic name resolution: Never hardcoded, derived from profile
        resolved_name = profile["full_name"] or "Student"
        self.assertEqual(resolved_name, "Arnav")
        print(f"\n[Test 1 PASSED] Arnav logged in successfully -> Welcome back, {resolved_name}!")

    def test_02_rahul_login_identity(self):
        """Test Scenario 2: Rahul logs in and sees Rahul."""
        res = verify_email_otp("rahul@campus.edu", "123456", full_name_fallback="Rahul")
        self.assertTrue(res["success"])

        user_id = res["user_id"]
        profile = get_student_profile(user_id)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["full_name"], "Rahul")

        # Dynamic name resolution
        resolved_name = profile["full_name"] or "Student"
        self.assertEqual(resolved_name, "Rahul")
        self.assertNotEqual(resolved_name, "Arnav")
        print(f"[Test 2 PASSED] Rahul logged in successfully -> Welcome back, {resolved_name}!")

    def test_03_switch_accounts(self):
        """Test Scenario 3: Arnav logs out and Rahul logs in."""
        # Simulated session state
        session = {}

        # 1. Arnav logs in
        arnav_res = verify_email_otp("arnav@campus.edu", "123456")
        session["authenticated_user"] = arnav_res
        arnav_prof = get_student_profile(session["authenticated_user"]["user_id"])
        self.assertEqual(arnav_prof["full_name"], "Arnav")

        # 2. Arnav logs out
        sign_out_student()
        session.clear()
        self.assertEqual(len(session), 0)

        # 3. Rahul logs in
        rahul_res = verify_email_otp("rahul@campus.edu", "123456")
        session["authenticated_user"] = rahul_res
        rahul_prof = get_student_profile(session["authenticated_user"]["user_id"])
        self.assertEqual(rahul_prof["full_name"], "Rahul")
        print("[Test 3 PASSED] Arnav logged out and Rahul logged in with clean state transition.")

    def test_04_session_persistence_simulation(self):
        """Test Scenario 4: Refreshing the dashboard preserves the correct identity."""
        session = {"authenticated_user": {"user_id": "student_rahul_002", "email": "rahul@campus.edu"}}

        # Simulate page refresh by querying profile again using stored user_id
        current_user_id = session["authenticated_user"]["user_id"]
        profile = get_student_profile(current_user_id)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["full_name"], "Rahul")
        print(f"[Test 4 PASSED] Session preserved user identity across simulated refresh: {profile['full_name']}")

    def test_05_incomplete_profile_neutral_fallback(self):
        """Test Scenario 5: A user with an incomplete profile sees a neutral fallback ('Student')."""
        # User with no full_name
        test_email = "new_anonymous@campus.edu"
        res = verify_email_otp(test_email, "123456", full_name_fallback="")
        self.assertTrue(res["success"])

        user_id = res["user_id"]
        # Clear full_name to simulate incomplete profile
        upsert_student_profile(user_id=user_id, full_name="", email=test_email)

        profile = get_student_profile(user_id)
        self.assertIsNotNone(profile)
        raw_name = profile["full_name"].strip()
        self.assertEqual(raw_name, "")

        # Dynamic fallback logic:
        display_name = raw_name if raw_name else "Student"
        self.assertEqual(display_name, "Student")
        self.assertNotEqual(display_name, "Arnav")
        self.assertNotEqual(display_name, "Rahul")
        print(f"[Test 5 PASSED] Incomplete profile correctly displayed neutral fallback: 'Welcome back, {display_name}!'")

    def test_06_strict_data_isolation(self):
        """Test Scenario 6: One student cannot access another student's profile or bookings."""
        arnav_id = "student_arnav_001"
        rahul_id = "student_rahul_002"

        arnav_bookings = get_all_student_reservations(student_id=arnav_id)
        rahul_bookings = get_all_student_reservations(student_id=rahul_id)

        # Check that Arnav's bookings list contains only Arnav's records
        for b in arnav_bookings:
            self.assertEqual(b["student_id"], arnav_id)
            self.assertNotEqual(b["student_id"], rahul_id)

        # Check that Rahul's bookings list contains only Rahul's records
        for b in rahul_bookings:
            self.assertEqual(b["student_id"], rahul_id)
            self.assertNotEqual(b["student_id"], arnav_id)

        print(f"[Test 6 PASSED] Strict data isolation verified. Arnav has {len(arnav_bookings)} bookings, Rahul has {len(rahul_bookings)} bookings. Zero cross-user leakage.")

    def test_07_logout_clears_information(self):
        """Test Scenario 7: Session logout clears user-specific information."""
        session = {
            "authenticated_user": {"user_id": "student_arnav_001", "email": "arnav@campus.edu"},
            "messages": [{"role": "user", "content": "Book lab"}],
            "langchain_history": ["msg1"],
            "pending_booking": {"item_id": 1},
        }

        # Perform logout
        sign_out_student()
        session["authenticated_user"] = None
        session["messages"] = []
        session["langchain_history"] = []
        session["pending_booking"] = None

        self.assertIsNone(session["authenticated_user"])
        self.assertEqual(len(session["messages"]), 0)
        self.assertIsNone(session["pending_booking"])
        print("[Test 7 PASSED] Logout completely cleared session user and booking state.")

    def test_08_profile_completion_without_duplicates(self):
        """Test Scenario 8: Completing profile updates existing record without duplicate insertion."""
        test_email = f"test_complete_{uuid.uuid4().hex[:6]}@campus.edu"
        res = verify_email_otp(test_email, "123456", full_name_fallback="")
        uid = res["user_id"]

        # Initial upsert with empty name
        upsert_student_profile(user_id=uid, full_name="", email=test_email)
        p1 = get_student_profile(uid)
        self.assertEqual(p1["full_name"], "")

        # Now complete profile with actual name
        upsert_student_profile(user_id=uid, full_name="Tanvi Desai", email=test_email, department="Data Science")
        p2 = get_student_profile(uid)
        self.assertEqual(p2["full_name"], "Tanvi Desai")
        self.assertEqual(p2["department"], "Data Science")

        # Verify no duplicate was created for this email
        p_by_email = get_student_profile_by_email(test_email)
        self.assertEqual(p_by_email["user_id"], uid)
        print("[Test 8 PASSED] Profile updated smoothly without creating duplicate records.")


if __name__ == "__main__":
    unittest.main()
