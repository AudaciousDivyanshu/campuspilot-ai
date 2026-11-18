"""Supabase Native Email OTP & Student Identity Authentication Service.

Handles passwordless email verification via Supabase Auth:
1. Connects to Supabase Auth API using SUPABASE_URL and SUPABASE_KEY.
2. Dispatches OTP verification emails to students.
3. Verifies OTP codes and extracts the authenticated user's unique Supabase User ID (UUID).
4. Synchronizes verified identities with the SQLite student_profiles table.
5. Provides safe offline simulation / demonstration profiles for local testing.
"""

import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from app.database.operations import (
    get_student_profile,
    get_student_profile_by_email,
    upsert_student_profile,
)

load_dotenv()

logger = logging.getLogger("campuspilot.supabase_auth")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_client = None


def is_supabase_configured() -> bool:
    """Check whether valid Supabase credentials are configured in environment."""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    return bool(
        url
        and key
        and "your-project" not in url
        and not key.startswith("your_supabase")
        and url.startswith("https://")
    )


def get_supabase_client():
    """Retrieve or lazily initialize the Supabase client."""
    global _client
    if _client is not None:
        return _client

    if not is_supabase_configured():
        return None

    try:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        _client = create_client(url, key)
        return _client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


def send_email_otp(email: str, full_name: Optional[str] = None) -> Dict[str, Any]:
    """Send an email verification code (OTP) using Supabase Auth.

    Args:
        email: The student's email/Gmail address.
        full_name: Optional student full name to store in user metadata.

    Returns:
        Dict with 'success' (bool) and 'message' (str) or 'error' (str).
    """
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return {"success": False, "error": "Please enter a valid email address."}

    client = get_supabase_client()
    if not client:
        # Offline demonstration mode when Supabase keys are not populated
        logger.info(f"Supabase credentials not active; simulating OTP dispatch for {clean_email}")
        return {
            "success": True,
            "simulated": True,
            "message": f"Verification code simulated for {clean_email}. Enter any 6-digit code (e.g. 123456) to proceed.",
        }

    try:
        credentials: Dict[str, Any] = {"email": clean_email}
        if full_name and full_name.strip():
            credentials["options"] = {"data": {"full_name": full_name.strip()}}

        client.auth.sign_in_with_otp(credentials)
        return {
            "success": True,
            "simulated": False,
            "message": f"Verification code sent to {clean_email}! Please check your email inbox and spam folder.",
        }
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Supabase send_email_otp failed for {clean_email}: {err_msg}")
        return {"success": False, "error": err_msg}


def verify_email_otp(email: str, token: str, full_name_fallback: Optional[str] = None) -> Dict[str, Any]:
    """Verify the 6-digit OTP code received by the student via Supabase Auth.

    Args:
        email: Student email address.
        token: 6-digit code or OTP token from email.
        full_name_fallback: Optional name entered during login form.

    Returns:
        Dict with 'success' (bool), 'user_id', 'email', 'full_name', 'department', and 'auth_type'.
    """
    clean_email = (email or "").strip().lower()
    clean_token = re.sub(r"\s+", "", str(token or "")).strip()

    if not clean_token or len(clean_token) < 4:
        return {"success": False, "error": "Please enter the verification code received in your email."}

    client = get_supabase_client()
    if not client:
        # Offline demonstration verification
        # 1. Look up existing profile in SQLite to retrieve their actual registered name
        existing_profile = get_student_profile_by_email(clean_email)
        if existing_profile:
            user_id = existing_profile["user_id"]
            reg_name = existing_profile["full_name"]
            dept = existing_profile.get("department", "Engineering & Technology")
        else:
            # Generate stable deterministic user_id from email hash
            hash_id = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:12]
            user_id = f"usr_{hash_id}"
            reg_name = (full_name_fallback or "").strip()
            dept = "Engineering & Technology"
            # Upsert into database
            upsert_student_profile(user_id=user_id, full_name=reg_name, email=clean_email, department=dept)

        return {
            "success": True,
            "user_id": user_id,
            "email": clean_email,
            "full_name": reg_name,
            "department": dept,
            "auth_type": "supabase_otp_simulated",
        }

    try:
        res = client.auth.verify_otp(
            {
                "email": clean_email,
                "token": clean_token,
                "type": "email",
            }
        )
        user = res.user
        if not user:
            return {"success": False, "error": "Invalid or expired verification code."}

        supabase_user_id = str(user.id)
        metadata = getattr(user, "user_metadata", {}) or {}
        user_meta_name = metadata.get("full_name") or metadata.get("name")

        # Check existing profile in SQLite
        existing_prof = get_student_profile(supabase_user_id) or get_student_profile_by_email(clean_email)
        if existing_prof and existing_prof.get("full_name"):
            reg_name = existing_prof["full_name"]
            dept = existing_prof.get("department", "Engineering & Technology")
        elif user_meta_name:
            reg_name = user_meta_name
            dept = "Engineering & Technology"
        elif full_name_fallback and full_name_fallback.strip():
            reg_name = full_name_fallback.strip()
            dept = "Engineering & Technology"
        else:
            reg_name = ""
            dept = "Engineering & Technology"

        # Sync with SQLite profile store
        saved_prof = upsert_student_profile(
            user_id=supabase_user_id,
            full_name=reg_name,
            email=clean_email,
            department=dept,
        )

        return {
            "success": True,
            "user_id": supabase_user_id,
            "email": clean_email,
            "full_name": saved_prof.get("full_name", ""),
            "department": saved_prof.get("department", "Engineering & Technology"),
            "session": res.session,
            "auth_type": "supabase_otp",
        }
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"Supabase verify_otp failed for {clean_email}: {err_msg}")
        return {"success": False, "error": f"Verification failed: {err_msg}"}


def get_demo_profiles() -> List[Dict[str, Any]]:
    """Return verified demonstration profiles for instant offline presentation and testing."""
    return [
        {
            "user_id": "student_arnav_001",
            "full_name": "Arnav",
            "email": "arnav@campus.edu",
            "roll_no": "CS2026-001",
            "department": "Computer Science & Engineering",
            "avatar": "👨‍🎓",
            "auth_type": "demo_profile",
        },
        {
            "user_id": "student_rahul_002",
            "full_name": "Rahul",
            "email": "rahul@campus.edu",
            "roll_no": "AI2026-002",
            "department": "AI & Data Science",
            "avatar": "👨‍🎓",
            "auth_type": "demo_profile",
        },
        {
            "user_id": "student_unknown_003",
            "full_name": "",
            "email": "new.student@campus.edu",
            "roll_no": "GEN2026-003",
            "department": "Engineering & Technology",
            "avatar": "🧑‍🎓",
            "auth_type": "demo_profile",
        },
    ]


def sign_out_student() -> None:
    """Sign out the active student from Supabase Auth and reset credentials."""
    client = get_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception as e:
            logger.debug(f"Error during Supabase sign_out: {e}")
