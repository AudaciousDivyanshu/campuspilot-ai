"""CampusPilot AI — Lightweight Demo Authentication Service.

Provides session and demonstration authentication for students and faculty administrators.
Supports:
1. User registration with input validation (email format, password strength, duplicate prevention).
2. User login with hashed password verification.
3. Pre-seeded demo accounts (Arnav, Rahul, Dr. Sharma).
4. Synchronization with SQLite student_profiles table for dynamic identity.
5. Persistent storage in data/demo_users.json across Streamlit reruns.
"""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from app.database.operations import upsert_student_profile

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
USERS_FILE = DATA_DIR / "demo_users.json"
PASSWORD_SALT = "campuspilot_auth_salt_2026"


def _hash_password(password: str) -> str:
    """Hash password with salt using SHA-256."""
    return hashlib.sha256((PASSWORD_SALT + password).encode("utf-8")).hexdigest()


def _get_default_seed_users() -> Dict[str, Dict[str, Any]]:
    """Return default seed accounts for demonstration."""
    return {
        "arnav@campus.edu": {
            "user_id": "student_arnav_001",
            "full_name": "Arnav",
            "display_name": "Arnav",
            "email": "arnav@campus.edu",
            "password_hash": _hash_password("Password123"),
            "account_type": "Student",
            "student_id": "CS2026-001",
            "university": "Lovely Professional University",
            "department": "Computer Science & Engineering",
            "avatar": "👨‍🎓",
            "created_at": "2026-01-01T00:00:00",
        },
        "rahul@campus.edu": {
            "user_id": "student_rahul_002",
            "full_name": "Rahul",
            "display_name": "Rahul",
            "email": "rahul@campus.edu",
            "password_hash": _hash_password("Password123"),
            "account_type": "Student",
            "student_id": "AI2026-002",
            "university": "Lovely Professional University",
            "department": "AI & Data Science",
            "avatar": "👨‍🎓",
            "created_at": "2026-01-01T00:00:00",
        },
        "admin@campus.edu": {
            "user_id": "admin_sharma_101",
            "full_name": "Dr. Sharma",
            "display_name": "Dr. Sharma",
            "email": "admin@campus.edu",
            "password_hash": _hash_password("AdminPass123"),
            "account_type": "Administrator",
            "student_id": "FAC2026-101",
            "university": "Lovely Professional University",
            "department": "Campus Administration & Operations",
            "avatar": "🛡️",
            "created_at": "2026-01-01T00:00:00",
        },
    }


def _load_users() -> Dict[str, Dict[str, Any]]:
    """Load users from JSON storage or initialize with seed accounts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    # Ensure default seed users exist
                    defaults = _get_default_seed_users()
                    for k, v in defaults.items():
                        if k not in data:
                            data[k] = v
                    return data
        except Exception:
            pass

    users = _get_default_seed_users()
    _save_users(users)
    return users


def _save_users(users: Dict[str, Dict[str, Any]]) -> None:
    """Save users dictionary to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        print(f"[demo_auth] Error persisting users: {e}")


def validate_password_strength(password: str) -> Dict[str, bool]:
    """Validate password against requirements:

    1. Min 8 characters
    2. At least one uppercase letter
    3. At least one lowercase letter
    4. At least one number
    """
    return {
        "min_length": len(password) >= 8,
        "has_upper": bool(re.search(r"[A-Z]", password)),
        "has_lower": bool(re.search(r"[a-z]", password)),
        "has_digit": bool(re.search(r"[0-9]", password)),
    }


def is_password_valid(password: str) -> Tuple[bool, List[str]]:
    """Check if password passes all rules and return failed reasons."""
    strength = validate_password_strength(password)
    errors = []
    if not strength["min_length"]:
        errors.append("At least 8 characters long")
    if not strength["has_upper"]:
        errors.append("At least one uppercase letter (A-Z)")
    if not strength["has_lower"]:
        errors.append("At least one lowercase letter (a-z)")
    if not strength["has_digit"]:
        errors.append("At least one number (0-9)")
    return len(errors) == 0, errors


def register_user(
    email: str,
    password: str,
    full_name: str,
    account_type: str = "Student",
    student_id: str = "",
    university: str = "Lovely Professional University",
    display_name: str = "",
    department: str = "Computer Science & Engineering",
) -> Tuple[bool, Any]:
    """Register a new student or administrator in the demo auth system.

    Validates inputs, prevents duplicate emails, hashes password,
    and updates SQLite student profile.
    """
    clean_email = email.strip().lower()
    clean_name = full_name.strip()
    clean_display = display_name.strip() or clean_name

    # Validate email
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return False, "Please enter a valid university email address."

    # Validate name
    if not clean_name or len(clean_name) < 2:
        return False, "Please provide your full legal name (minimum 2 characters)."

    # Validate password
    valid, errors = is_password_valid(password)
    if not valid:
        return False, f"Password does not meet requirements: {', '.join(errors)}."

    users = _load_users()

    # Duplicate check
    if clean_email in users:
        return False, f"An account with email '{clean_email}' already exists. Please log in."

    # Generate student/admin ID if not provided
    generated_id = student_id.strip()
    if not generated_id:
        prefix = "ADM" if account_type == "Administrator" else "STU"
        count = len(users) + 1
        generated_id = f"{prefix}2026-{count:03d}"

    user_id = f"{account_type.lower()}_{clean_name.lower().replace(' ', '_')}_{generated_id.replace('-', '_')}"
    avatar = "🛡️" if account_type == "Administrator" else "👨‍🎓"

    user_record = {
        "user_id": user_id,
        "full_name": clean_name,
        "display_name": clean_display,
        "email": clean_email,
        "password_hash": _hash_password(password),
        "account_type": account_type,
        "student_id": generated_id,
        "university": university or "Lovely Professional University",
        "department": department or "General Sciences",
        "avatar": avatar,
        "created_at": datetime.now().isoformat(),
    }

    users[clean_email] = user_record
    _save_users(users)

    # Sync with SQLite profile table
    try:
        upsert_student_profile(
            user_id=user_id,
            full_name=clean_name,
            email=clean_email,
            department=department or "General Sciences",
        )
    except Exception as e:
        print(f"[demo_auth] Note: SQLite profile sync error: {e}")

    # Return safe user record (without password hash)
    safe_user = {k: v for k, v in user_record.items() if k != "password_hash"}
    return True, safe_user


def authenticate_user(email: str, password: str) -> Tuple[bool, Any]:
    """Authenticate student or admin with email and password."""
    clean_email = email.strip().lower()
    if not clean_email or not password:
        return False, "Email and password are required."

    users = _load_users()
    user_record = users.get(clean_email)

    if not user_record:
        return False, "No account found with this email. Please check your credentials or register."

    target_hash = _hash_password(password)
    if user_record.get("password_hash") != target_hash:
        return False, "Incorrect password. Please verify and try again."

    # Sync/ensure SQLite profile exists
    try:
        upsert_student_profile(
            user_id=user_record["user_id"],
            full_name=user_record["full_name"],
            email=user_record["email"],
            department=user_record.get("department", "Engineering & Technology"),
        )
    except Exception:
        pass

    safe_user = {k: v for k, v in user_record.items() if k != "password_hash"}
    return True, safe_user


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve user dictionary by email (without password hash)."""
    users = _load_users()
    user = users.get(email.strip().lower())
    if user:
        return {k: v for k, v in user.items() if k != "password_hash"}
    return None


def get_all_demo_users() -> List[Dict[str, Any]]:
    """Return all demo users for quick demonstration selection."""
    users = _load_users()
    return [{k: v for k, v in u.items() if k != "password_hash"} for u in users.values()]
