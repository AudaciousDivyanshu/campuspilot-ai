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

from app.database.operations import (
    get_user_account_by_email,
    upsert_student_profile,
    upsert_user_account,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
USERS_FILE = DATA_DIR / "demo_users.json"
PASSWORD_SALT = "campuspilot_auth_salt_2026"


def _hash_password(password: str) -> str:
    """Hash password with salt using SHA-256."""
    return hashlib.sha256((PASSWORD_SALT + password).encode("utf-8")).hexdigest()


def init_admin_account() -> Dict[str, Any]:
    """Ensure an authorized administrator account exists based on environment variables or defaults.

    Reads configuration:
    - ADMIN_EMAIL (default: 'admin@campus.edu')
    - ADMIN_PASSWORD (default: 'AdminPass123')
    - ADMIN_NAME (default: 'Dr. Sharma')

    Idempotent: Provisions or updates the authorized administrator in both
    data/demo_users.json and SQLite without creating duplicate records.
    """
    admin_email = os.getenv("ADMIN_EMAIL", "admin@campus.edu").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "AdminPass123")
    admin_name = os.getenv("ADMIN_NAME", "Dr. Sharma").strip()
    admin_pwd_hash = _hash_password(admin_password)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    users = {}
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)
        except Exception:
            users = {}

    admin_record = users.get(admin_email)
    if admin_record:
        # Existing account for this email: ensure Administrator privileges and update hash if changed
        admin_record["account_type"] = "Administrator"
        admin_record["password_hash"] = admin_pwd_hash
        admin_record["full_name"] = admin_record.get("full_name") or admin_name
        admin_record["display_name"] = admin_record.get("display_name") or admin_name
        admin_record["avatar"] = "🛡️"
        users[admin_email] = admin_record
    else:
        # Check if an administrator already exists with a different email when ADMIN_EMAIL wasn't explicitly set
        existing_admin = next((u for u in users.values() if u.get("account_type") == "Administrator"), None)
        if existing_admin and not os.getenv("ADMIN_EMAIL"):
            admin_record = existing_admin
            # Ensure password hash matches default
            admin_record["password_hash"] = admin_pwd_hash
            users[existing_admin["email"]] = admin_record
        else:
            clean_name_slug = re.sub(r"[^a-zA-Z0-9]", "_", admin_name.lower()).strip("_")
            user_id = f"admin_{clean_name_slug}_101"
            admin_record = {
                "user_id": user_id,
                "full_name": admin_name,
                "display_name": admin_name,
                "email": admin_email,
                "password_hash": admin_pwd_hash,
                "account_type": "Administrator",
                "student_id": "FAC2026-101",
                "university": "Lovely Professional University",
                "department": "Campus Administration & Operations",
                "avatar": "🛡️",
                "created_at": datetime.now().isoformat(),
            }
            users[admin_email] = admin_record

    _save_users(users)

    # Synchronize with SQLite user_accounts and student_profiles
    try:
        upsert_user_account(admin_record)
        upsert_student_profile(
            user_id=admin_record["user_id"],
            full_name=admin_record["full_name"],
            email=admin_record["email"],
            department=admin_record.get("department", "Campus Administration & Operations"),
        )
    except Exception as e:
        print(f"[demo_auth] SQLite admin sync note: {e}")

    return {k: v for k, v in admin_record.items() if k != "password_hash"}


def _get_default_seed_users() -> Dict[str, Dict[str, Any]]:
    """Return default seed accounts for demonstration."""
    admin_email = os.getenv("ADMIN_EMAIL", "admin@campus.edu").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "AdminPass123")
    admin_name = os.getenv("ADMIN_NAME", "Dr. Sharma").strip()

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
        admin_email: {
            "user_id": "admin_sharma_101",
            "full_name": admin_name,
            "display_name": admin_name,
            "email": admin_email,
            "password_hash": _hash_password(admin_password),
            "account_type": "Administrator",
            "student_id": "FAC2026-101",
            "university": "Lovely Professional University",
            "department": "Campus Administration & Operations",
            "avatar": "🛡️",
            "created_at": "2026-01-01T00:00:00",
        },
    }


def _load_users(auto_init_admin: bool = True) -> Dict[str, Dict[str, Any]]:
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
                    if auto_init_admin:
                        # Ensure administrator matches environment variables
                        init_admin_account()
                        with open(USERS_FILE, "r", encoding="utf-8") as rf:
                            return json.load(rf)
                    return data
        except Exception:
            pass

    users = _get_default_seed_users()
    _save_users(users)
    if auto_init_admin:
        init_admin_account()
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
    allow_admin: bool = False,
) -> Tuple[bool, Any]:
    """Register a new student account in the authentication system.

    Validates inputs, prevents duplicate emails, hashes password,
    enforces Student role isolation, and updates SQLite storage.
    """
    clean_email = email.strip().lower()
    clean_name = full_name.strip()
    clean_display = display_name.strip() or clean_name

    # Security requirement: Public registrations can NEVER self-assign Administrator
    enforced_role = "Student" if not allow_admin else account_type

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
        prefix = "ADM" if enforced_role == "Administrator" else "STU"
        count = len(users) + 1
        generated_id = f"{prefix}2026-{count:03d}"

    user_id = f"{enforced_role.lower()}_{clean_name.lower().replace(' ', '_')}_{generated_id.replace('-', '_')}"
    avatar = "🛡️" if enforced_role == "Administrator" else "👨‍🎓"

    user_record = {
        "user_id": user_id,
        "full_name": clean_name,
        "display_name": clean_display,
        "email": clean_email,
        "password_hash": _hash_password(password),
        "account_type": enforced_role,
        "student_id": generated_id,
        "university": university or "Lovely Professional University",
        "department": department or "Computer Science & Engineering",
        "avatar": avatar,
        "created_at": datetime.now().isoformat(),
    }

    users[clean_email] = user_record
    _save_users(users)

    # Sync with SQLite user_accounts and student_profiles table
    try:
        upsert_user_account(user_record)
        upsert_student_profile(
            user_id=user_id,
            full_name=clean_name,
            email=clean_email,
            department=department or "Computer Science & Engineering",
        )
    except Exception as e:
        print(f"[demo_auth] Note: SQLite profile sync error: {e}")

    # Return safe user record (without password hash)
    safe_user = {k: v for k, v in user_record.items() if k != "password_hash"}
    return True, safe_user


def authenticate_user(
    email: str,
    password: str,
    required_role: Optional[str] = None,
    *args,
    **kwargs,
) -> Tuple[bool, Any]:
    """Authenticate student or administrator with email, password, and optional role requirement."""
    clean_email = email.strip().lower()
    if not clean_email or not password:
        return False, "Email and password are required."

    role_to_check = required_role or kwargs.get("required_role") or kwargs.get("role")

    users = _load_users()
    user_record = users.get(clean_email)

    if not user_record:
        # Also check SQLite user_accounts table directly
        try:
            db_user = get_user_account_by_email(clean_email)
            if db_user:
                users[clean_email] = db_user
                user_record = db_user
        except Exception:
            pass

    if not user_record:
        if role_to_check == "Administrator":
            return False, f"No administrator account found with email '{clean_email}'. Please verify your credentials or check ADMIN_EMAIL in .env."
        return False, "No account found with this email. Please check your credentials or register."

    target_hash = _hash_password(password)
    if user_record.get("password_hash") != target_hash:
        return False, "Incorrect password. Please verify and try again."

    # Verify role authorization
    if role_to_check and user_record.get("account_type") != role_to_check:
        return False, f"Access Denied: Account '{clean_email}' is registered as a {user_record.get('account_type')} and does not possess institutional {role_to_check.lower()} privileges."

    # Sync/ensure SQLite user_accounts and student_profiles exist
    try:
        upsert_user_account(user_record)
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
