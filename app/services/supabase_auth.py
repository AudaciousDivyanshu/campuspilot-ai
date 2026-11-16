"""Supabase Native Email OTP & Magic Link Authentication Service.

Provides passwordless email verification via Supabase Auth without any Google Cloud OAuth
or paid cloud dependencies.
Extracts verified student identity (name, email address, Supabase user ID).
"""

import logging
import os
from typing import Any, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("campuspilot.auth")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_client = None


def is_supabase_configured() -> bool:
    """Check whether valid Supabase credentials are configured in environment."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return bool(
        url
        and key
        and "your-project" not in url
        and not key.startswith("your_supabase")
        and url.startswith("https://")
    )


def get_supabase_client():
    """Retrieve or initialize the Supabase client."""
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
    """Send an email verification code (OTP) or magic link using Supabase Auth.

    Args:
        email: The student's email/Gmail address.
        full_name: Optional student full name to store in user metadata.

    Returns:
        Dict with 'success' (bool) and 'message' (str) or 'error' (str).
    """
    clean_email = email.strip()
    if not clean_email or "@" not in clean_email:
        return {"success": False, "error": "Please enter a valid email address."}

    client = get_supabase_client()
    if not client:
        # Graceful demo mode if SUPABASE_URL / SUPABASE_KEY are not yet populated in .env
        return {
            "success": True,
            "simulated": True,
            "message": f"Verification code simulated for {clean_email}. (To enable real inbox delivery, add SUPABASE_URL and SUPABASE_KEY to .env)",
        }

    try:
        credentials: Dict[str, Any] = {"email": clean_email}
        if full_name:
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
        full_name_fallback: Optional full name if user metadata doesn't contain it.

    Returns:
        Dict with 'success' (bool), 'user_id', 'email', 'full_name', and optional 'session'.
    """
    clean_email = email.strip().lower()
    clean_token = token.strip()

    if not clean_token:
        return {"success": False, "error": "Please enter the verification code received in your email."}

    client = get_supabase_client()
    if not client:
        # Demo verification fallback when Supabase keys are pending
        derived_name = full_name_fallback or clean_email.split("@")[0].replace(".", " ").title()
        return {
            "success": True,
            "user_id": clean_email.split("@")[0],
            "email": clean_email,
            "full_name": derived_name,
            "auth_type": "email_otp",
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

        metadata = getattr(user, "user_metadata", {}) or {}
        derived_name = (
            metadata.get("full_name")
            or metadata.get("name")
            or full_name_fallback
            or clean_email.split("@")[0].replace(".", " ").title()
        )

        return {
            "success": True,
            "user_id": str(getattr(user, "id", clean_email.split("@")[0])),
            "email": str(getattr(user, "email", clean_email)),
            "full_name": derived_name,
            "session": res.session,
            "auth_type": "email_otp",
        }
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"Supabase verify_otp failed for {clean_email}: {err_msg}")
        return {"success": False, "error": f"Verification failed: {err_msg}"}


def sign_out_student() -> None:
    """Sign out the active student from Supabase Auth."""
    client = get_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception as e:
            logger.debug(f"Error during sign_out: {e}")


def parse_session_from_token(access_token: str) -> Optional[Dict[str, Any]]:
    """Verify and retrieve user from an access token."""
    client = get_supabase_client()
    if not client or not access_token:
        return None

    try:
        res = client.auth.get_user(access_token)
        user = res.user
        if not user:
            return None
        metadata = getattr(user, "user_metadata", {}) or {}
        full_name = metadata.get("full_name") or metadata.get("name") or user.email.split("@")[0].title()
        return {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": full_name,
            "auth_type": "email_otp",
        }
    except Exception as e:
        logger.warning(f"Error verifying token: {e}")
        return None
