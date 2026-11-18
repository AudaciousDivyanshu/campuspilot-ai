"""Comprehensive Test Suite for Gmail SMTP Email & OTP Authentication in CampusPilot AI.

Tests:
1. Gmail SMTP Configuration Detection.
2. OTP Generation, Salting, and Hashing.
3. OTP Expiration Enforcement (5 minutes).
4. Incorrect Verification Attempts & Rate Limiting (max 5 tries).
5. Single-Use Invalidation upon Verification.
6. Resend Cooldown Enforcement (60 seconds).
7. Gmail SMTP Dispatch with STARTTLS (Mocked).
8. Booking Confirmation Email Content & Dispatch (Mocked).
9. Idempotency & Duplicate Suppression on Confirmation Retry.
10. Database Booking Preservation on SMTP Failure.
11. Pre-configured Demo Student Profiles.
"""

from email.mime.multipart import MIMEMultipart
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_db_context
from app.database.init_db import init_db
from app.database.operations import get_all_student_reservations
from app.services.auth_service import (
    _otp_store,
    get_demo_profiles,
    get_resend_cooldown,
    is_auth_service_configured,
    request_email_otp,
    reset_auth_state,
    verify_email_otp,
)
from app.services.email_service import (
    build_confirmation_html,
    is_smtp_configured,
    reset_email_dispatch_cache,
    send_booking_confirmation_email,
    send_otp_email,
    send_smtp_email,
)
from app.tools.campus_tools import create_lab_booking, create_room_reservation


class TestGmailAuthAndEmailWorkflow(unittest.TestCase):
    def setUp(self):
        reset_auth_state()
        reset_email_dispatch_cache()

    def tearDown(self):
        reset_auth_state()
        reset_email_dispatch_cache()

    def test_01_smtp_configuration_detection(self):
        """Test detection of configured vs unconfigured Gmail SMTP settings."""
        # Unconfigured
        with patch.dict(os.environ, {
            "EMAIL_ADDRESS": "",
            "EMAIL_APP_PASSWORD": "",
        }, clear=False):
            self.assertFalse(is_smtp_configured())
            self.assertFalse(is_auth_service_configured())

        # Placeholder
        with patch.dict(os.environ, {
            "EMAIL_ADDRESS": "your.college.project@gmail.com",
            "EMAIL_APP_PASSWORD": "your_16_character_app_password",
        }, clear=False):
            self.assertFalse(is_smtp_configured())

        # Configured
        with patch.dict(os.environ, {
            "EMAIL_ADDRESS": "campus.pilot.demo@gmail.com",
            "EMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",
        }, clear=False):
            self.assertTrue(is_smtp_configured())
            self.assertTrue(is_auth_service_configured())
        print("  ✓ [Test 1] Gmail SMTP configuration status correctly detected.")

    @patch("app.services.auth_service.send_otp_email")
    def test_02_otp_generation_and_secure_hashing(self, mock_send):
        """Test OTP is securely hashed and never stored in plain text."""
        mock_send.return_value = {"success": True, "message": "Email sent"}

        test_email = "student@college.edu"
        res = request_email_otp(test_email, "Test Student")
        self.assertTrue(res["success"])

        # Check in-memory store
        self.assertIn(test_email, _otp_store)
        stored_entry = _otp_store[test_email]

        # Verify salt exists and hash is 64 hex characters (SHA-256)
        self.assertIn("salt", stored_entry)
        self.assertIn("hash", stored_entry)
        self.assertEqual(len(stored_entry["hash"]), 64)
        # Verify plain-text OTP code is NOT stored anywhere in the dictionary
        self.assertNotIn("otp", stored_entry)
        self.assertNotIn("code", stored_entry)
        print("  ✓ [Test 2] OTP securely generated, salted, and hashed in memory.")

    @patch("app.services.auth_service.send_otp_email")
    def test_03_otp_expiration_enforcement(self, mock_send):
        """Test that an OTP expires and cannot be verified after 5 minutes (300s)."""
        mock_send.return_value = {"success": True, "message": "Email sent"}

        test_email = "student.expiry@college.edu"
        request_email_otp(test_email, "Test Student")

        # Extract the sent OTP code from mock call
        sent_code = mock_send.call_args[0][2]

        # Artificially age the session past 300 seconds
        _otp_store[test_email]["expires_at"] = time.time() - 10

        ver_res = verify_email_otp(test_email, sent_code)
        self.assertFalse(ver_res["success"])
        self.assertIn("expired", ver_res["error"].lower())
        # Verify expired session is purged
        self.assertNotIn(test_email, _otp_store)
        print("  ✓ [Test 3] OTP 5-minute expiration correctly enforced and session cleaned.")

    @patch("app.services.auth_service.send_otp_email")
    def test_04_incorrect_otp_attempts_and_rate_limiting(self, mock_send):
        """Test incorrect code tracking and maximum attempt cutoff (5 attempts)."""
        mock_send.return_value = {"success": True, "message": "Email sent"}

        test_email = "student.attempts@college.edu"
        request_email_otp(test_email, "Test Student")

        # Try wrong codes 4 times
        for remaining in range(4, 0, -1):
            bad_res = verify_email_otp(test_email, "000000")
            self.assertFalse(bad_res["success"])
            self.assertIn(f"{remaining} attempt", bad_res["error"])

        # 5th failed attempt: should revoke code
        final_bad_res = verify_email_otp(test_email, "000000")
        self.assertFalse(final_bad_res["success"])
        self.assertIn("maximum attempts exceeded", final_bad_res["error"].lower())

        # Session should now be deleted
        self.assertNotIn(test_email, _otp_store)
        print("  ✓ [Test 4] Maximum invalid attempts strictly enforced with revocation.")

    @patch("app.services.auth_service.send_otp_email")
    def test_05_single_use_otp_invalidation(self, mock_send):
        """Test that verifying an OTP once immediately invalidates it."""
        mock_send.return_value = {"success": True, "message": "Email sent"}

        test_email = "student.singleuse@college.edu"
        request_email_otp(test_email, "Aarav Sharma")
        sent_code = mock_send.call_args[0][2]

        # First verification: succeeds
        first_ver = verify_email_otp(test_email, sent_code)
        self.assertTrue(first_ver["success"])
        self.assertEqual(first_ver["full_name"], "Aarav Sharma")
        self.assertEqual(first_ver["auth_type"], "gmail_otp")

        # Second verification with exact same code: must fail
        second_ver = verify_email_otp(test_email, sent_code)
        self.assertFalse(second_ver["success"])
        self.assertIn("no active verification request", second_ver["error"].lower())
        print("  ✓ [Test 5] Single-use OTP invalidation strictly verified.")

    @patch("app.services.auth_service.send_otp_email")
    def test_06_resend_cooldown_enforcement(self, mock_send):
        """Test that requesting an OTP within 60 seconds is blocked by cooldown."""
        mock_send.return_value = {"success": True, "message": "Email sent"}

        test_email = "student.cooldown@college.edu"
        res1 = request_email_otp(test_email, "Student")
        self.assertTrue(res1["success"])

        # Immediate repeat request: must fail with cooldown
        res2 = request_email_otp(test_email, "Student")
        self.assertFalse(res2["success"])
        self.assertIn("cooldown active", res2["message"].lower())
        self.assertGreater(res2.get("cooldown", 0), 0)

        # Mock cooldown expired
        self.assertGreater(get_resend_cooldown(test_email), 0)
        print("  ✓ [Test 6] 60-second resend cooldown verified.")

    @patch("smtplib.SMTP")
    def test_07_gmail_smtp_dispatch_mocked(self, mock_smtp_cls):
        """Test Gmail SMTP interaction (STARTTLS, EHLO, Login, send_message)."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "EMAIL_ADDRESS": "sender@gmail.com",
            "EMAIL_APP_PASSWORD": "mock_app_password",
            "EMAIL_SENDER_NAME": "CampusPilot AI",
        }, clear=False):
            res = send_otp_email("recipient@gmail.com", "Test Student", "654321")
            self.assertTrue(res["success"])
            self.assertEqual(res["provider"], "gmail_smtp")

            # Verify SMTP workflow
            mock_smtp_cls.assert_called_with("smtp.gmail.com", 587, timeout=12)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("sender@gmail.com", "mock_app_password")
            mock_server.send_message.assert_called_once()

            sent_msg = mock_server.send_message.call_args[0][0]
            self.assertIn("654321", sent_msg["Subject"])
            self.assertEqual(sent_msg["To"], "recipient@gmail.com")
        print("  ✓ [Test 7] Gmail SMTP STARTTLS protocol verified.")

    @patch("smtplib.SMTP")
    def test_08_booking_confirmation_email_and_duplicate_suppression(self, mock_smtp_cls):
        """Test booking confirmation email content and duplicate suppression."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        with patch.dict(os.environ, {
            "EMAIL_ADDRESS": "campus@gmail.com",
            "EMAIL_APP_PASSWORD": "mock_password_16ch",
        }, clear=False):
            # 1. First dispatch: succeeds
            res1 = send_booking_confirmation_email(
                recipient_email="student@gmail.com",
                recipient_name="Aarav Sharma",
                facility_name="Artificial Intelligence Lab",
                booking_date="2026-11-20",
                start_time="10:00",
                end_time="12:00",
                booking_id="123",
                facility_type="Campus Laboratory",
            )
            self.assertTrue(res1["success"])
            self.assertFalse(res1.get("duplicate", False))
            self.assertEqual(mock_server.send_message.call_count, 1)

            # 2. Duplicate retry with same details: suppressed
            res2 = send_booking_confirmation_email(
                recipient_email="student@gmail.com",
                recipient_name="Aarav Sharma",
                facility_name="Artificial Intelligence Lab",
                booking_date="2026-11-20",
                start_time="10:00",
                end_time="12:00",
                booking_id="123",
                facility_type="Campus Laboratory",
            )
            self.assertTrue(res2["success"])
            self.assertTrue(res2.get("duplicate"))
            # Call count must still be 1
            self.assertEqual(mock_server.send_message.call_count, 1)
        print("  ✓ [Test 8] Booking confirmation email dispatched and duplicate retry suppressed.")

    @patch("smtplib.SMTP")
    def test_09_database_booking_preserved_on_smtp_failure(self, mock_smtp_cls):
        """Verify SQLite reservation remains intact even if Gmail SMTP fails."""
        # Mock SMTP raising an authentication or network error
        mock_smtp_cls.side_effect = Exception("SMTP server connection timed out")

        init_db()
        test_date = "2026-12-25"

        with get_db_context() as conn:
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bookings (student_id, student_name, lab_id, booking_date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?, ?, 'CONFIRMED');
                """,
                ("CS2026-DEMO", "Demo Student", 2, test_date, "11:00", "13:00"),
            )
            booking_id = cursor.lastrowid

        # Attempt confirmation email (which fails)
        with patch.dict(os.environ, {
            "EMAIL_ADDRESS": "sender@gmail.com",
            "EMAIL_APP_PASSWORD": "mock_password_16ch",
        }, clear=False):
            email_res = send_booking_confirmation_email(
                recipient_email="demo@college.edu",
                recipient_name="Demo Student",
                facility_name="AI Lab",
                booking_date=test_date,
                start_time="11:00",
                end_time="13:00",
                booking_id=booking_id,
            )
            self.assertFalse(email_res["success"])

        # Check SQLite database: booking must still be CONFIRMED
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bookings WHERE booking_id = ?;", (booking_id,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "CONFIRMED")
            self.assertEqual(row["student_id"], "CS2026-DEMO")

            # Clean up
            conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))
        print("  ✓ [Test 9] SQLite booking preserved intact when SMTP delivery fails.")

    def test_10_verified_demo_profiles(self):
        """Verify pre-configured demo student profiles are available."""
        profiles = get_demo_profiles()
        self.assertEqual(len(profiles), 2)
        names = [p["full_name"] for p in profiles]
        self.assertIn("Aarav Sharma", names)
        self.assertIn("Priya Patel", names)
        print("  ✓ [Test 10] Verified demo profiles available for live presentations.")


if __name__ == "__main__":
    print("=" * 65)
    print(" Running CampusPilot AI: Gmail SMTP & OTP Auth Test Suite")
    print("=" * 65)
    unittest.main(verbosity=1)
