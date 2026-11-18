"""CampusPilot AI Native Email Authentication Service.

Handles secure passwordless student authentication using Gmail SMTP:
1. Generates cryptographically secure 6-digit numeric OTPs.
2. Salts and hashes OTPs in memory (never stored in plain text).
3. Enforces 5-minute OTP expiration.
4. Enforces single-use invalidation upon successful verification.
5. Limits verification attempts (max 5 incorrect attempts before revocation).
6. Enforces a 60-second resend cooldown per email address.
7. Dispatches OTP emails via Gmail SMTP (app.services.email_service).
8. Provides instant verified demo profiles for offline evaluation and presentations.
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from app.services.email_service import is_smtp_configured, send_otp_email

load_dotenv()

logger = logging.getLogger("campuspilot.auth")

# Configuration Constants
OTP_EXPIRY_SECONDS = 300  # 5 minutes
OTP_COOLDOWN_SECONDS = 60  # 60 seconds between resends
MAX_VERIFY_ATTEMPTS = 5   # Max invalid attempts allowed

# Thread-safe storage for active OTP sessions
# Structure: email -> {
#   "hash": str,
#   "salt": str,
#   "expires_at": float,
#   "attempts_left": int,
#   "created_at": float,
#   "full_name": str,
# }
_otp_store: Dict[str, Dict[str, Any]] = {}

# Cooldown tracking: email -> timestamp of last dispatch
_cooldown_store: Dict[str, float] = {}

_lock = threading.Lock()


def _hash_otp(otp_code: str, salt: str) -> str:
    """Compute sha256 hash of salt + OTP."""
    payload = f"{salt}:{otp_code}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def reset_auth_state() -> None:
    """Clear in-memory OTP and cooldown state (used for testing)."""
    with _lock:
        _otp_store.clear()
        _cooldown_store.clear()


def is_auth_service_configured() -> bool:
    """Check if the underlying Gmail SMTP service is ready for OTP dispatch."""
    return is_smtp_configured()


def get_resend_cooldown(email: str) -> int:
    """Return remaining cooldown seconds before a new OTP can be requested."""
    clean_email = (email or "").strip().lower()
    with _lock:
        last_sent = _cooldown_store.get(clean_email)
        if not last_sent:
            return 0
        elapsed = time.time() - last_sent
        remaining = int(OTP_COOLDOWN_SECONDS - elapsed)
        return max(0, remaining)


def request_email_otp(email: str, full_name: Optional[str] = None) -> Dict[str, Any]:
    """Generate and dispatch a secure 6-digit OTP to the student's email.

    Args:
        email: Student email address.
        full_name: Optional student full name.

    Returns:
        Dict with 'success' (bool), 'message' (str), and optional 'cooldown' or 'error'.
    """
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return {
            "success": False,
            "error": "Please enter a valid email address.",
            "message": "Invalid email address format.",
        }

    derived_name = (full_name or "").strip() or clean_email.split("@")[0].replace(".", " ").title()

    # 1. Enforce Resend Cooldown
    cooldown_left = get_resend_cooldown(clean_email)
    if cooldown_left > 0:
        return {
            "success": False,
            "error": f"Please wait {cooldown_left}s before requesting a new verification code.",
            "message": f"Resend cooldown active ({cooldown_left}s remaining).",
            "cooldown": cooldown_left,
        }

    # 2. Generate cryptographically secure 6-digit numeric OTP
    otp_int = secrets.randbelow(900000) + 100000
    otp_code = str(otp_int)

    # 3. Salt and Hash the OTP
    salt = secrets.token_hex(16)
    otp_hash = _hash_otp(otp_code, salt)
    now = time.time()

    # 4. Store in thread-safe memory
    with _lock:
        _otp_store[clean_email] = {
            "hash": otp_hash,
            "salt": salt,
            "expires_at": now + OTP_EXPIRY_SECONDS,
            "attempts_left": MAX_VERIFY_ATTEMPTS,
            "created_at": now,
            "full_name": derived_name,
        }
        _cooldown_store[clean_email] = now

    # 5. Dispatch via Gmail SMTP
    email_res = send_otp_email(clean_email, derived_name, otp_code)

    if email_res.get("success"):
        logger.info(f"Verification OTP successfully dispatched to {clean_email}")
        return {
            "success": True,
            "message": f"Verification code sent to {clean_email}! Please check your email inbox and spam folder.",
            "cooldown": OTP_COOLDOWN_SECONDS,
        }
    else:
        # If SMTP is not yet configured, provide clear instructional notice
        err_msg = email_res.get("message") or email_res.get("error", "SMTP error")
        logger.warning(f"OTP dispatch failed for {clean_email}: {err_msg}")
        return {
            "success": False,
            "error": err_msg,
            "message": f"Could not send email: {err_msg}",
        }


def verify_email_otp(
    email: str,
    token: str,
    full_name_fallback: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify the 6-digit OTP code entered by the student.

    Guarantees:
    - Rejects expired OTPs (> 5 minutes).
    - Decrements attempt counter on invalid code (revokes on 0).
    - Single-use: invalidates OTP immediately upon successful verification.
    - Constant-time comparison using hmac.compare_digest.

    Args:
        email: Student email address.
        token: 6-digit numeric string entered by student.
        full_name_fallback: Optional student name.

    Returns:
        Dict with 'success' (bool), 'user_id', 'email', 'full_name', and 'auth_type'.
    """
    clean_email = (email or "").strip().lower()
    clean_token = re.sub(r"\s+", "", str(token or "")).strip()

    if not clean_token or not clean_token.isdigit() or len(clean_token) != 6:
        return {
            "success": False,
            "error": "Please enter a valid 6-digit numeric verification code.",
        }

    now = time.time()

    with _lock:
        session = _otp_store.get(clean_email)
        if not session:
            return {
                "success": False,
                "error": "No active verification request found for this email. Please request a new code.",
            }

        # Check Expiration
        if now > session["expires_at"]:
            del _otp_store[clean_email]
            return {
                "success": False,
                "error": "Your verification code has expired (5-minute limit). Please request a new code.",
            }

        # Check Remaining Attempts
        if session["attempts_left"] <= 0:
            del _otp_store[clean_email]
            return {
                "success": False,
                "error": "Too many invalid attempts. For your security, this code has been revoked. Please request a new code.",
            }

        # Compute hash and compare in constant time
        computed_hash = _hash_otp(clean_token, session["salt"])
        is_valid = hmac.compare_digest(computed_hash, session["hash"])

        if not is_valid:
            session["attempts_left"] -= 1
            attempts_left = session["attempts_left"]
            if attempts_left <= 0:
                del _otp_store[clean_email]
                return {
                    "success": False,
                    "error": "Incorrect code. Maximum attempts exceeded. Please request a new code.",
                }
            return {
                "success": False,
                "error": f"Invalid verification code. {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining.",
            }

        # Verification Success: Single-Use Invalidation
        student_name = session.get("full_name") or full_name_fallback or clean_email.split("@")[0].title()
        del _otp_store[clean_email]

    user_id = clean_email.split("@")[0]
    logger.info(f"Student identity successfully verified: {clean_email} ({student_name})")

    return {
        "success": True,
        "user_id": user_id,
        "email": clean_email,
        "full_name": student_name,
        "auth_type": "gmail_otp",
    }


def get_demo_profiles() -> List[Dict[str, str]]:
    """Return pre-verified demo profiles for immediate presentation testing."""
    return [
        {
            "user_id": "CS2026-042",
            "email": "aarav.sharma.campus@gmail.com",
            "full_name": "Aarav Sharma",
            "roll_no": "CS2026-042",
            "department": "Computer Science & Engineering",
            "auth_type": "demo_profile",
        },
        {
            "user_id": "CS2026-088",
            "email": "priya.patel.campus@gmail.com",
            "full_name": "Priya Patel",
            "roll_no": "CS2026-088",
            "department": "Artificial Intelligence & Data Science",
            "auth_type": "demo_profile",
        },
    ]


def sign_out_student() -> None:
    """Clear active student session references."""
    pass
