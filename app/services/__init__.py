"""CampusPilot AI Services Module."""

from app.services.supabase_auth import (
    get_demo_profiles as get_supabase_demo_profiles,
    is_supabase_configured,
    send_email_otp as send_supabase_otp,
    sign_out_student as sign_out_supabase,
    verify_email_otp as verify_supabase_otp,
)
from app.services.auth_service import (
    get_demo_profiles,
    get_resend_cooldown,
    is_auth_service_configured,
    request_email_otp,
    reset_auth_state,
    sign_out_student,
    verify_email_otp,
)
from app.services.email_service import (
    is_email_service_configured,
    is_smtp_configured,
    send_booking_confirmation_email,
    send_otp_email,
    send_smtp_email,
)
from app.services.demo_auth import (
    authenticate_user,
    get_all_demo_users,
    get_user_by_email,
    init_admin_account,
    is_password_valid,
    register_user,
    validate_password_strength,
)

__all__ = [
    "request_email_otp",
    "verify_email_otp",
    "get_demo_profiles",
    "get_resend_cooldown",
    "is_auth_service_configured",
    "reset_auth_state",
    "sign_out_student",
    "send_smtp_email",
    "send_otp_email",
    "send_booking_confirmation_email",
    "is_smtp_configured",
    "is_email_service_configured",
    "register_user",
    "authenticate_user",
    "init_admin_account",
    "get_user_by_email",
    "validate_password_strength",
    "is_password_valid",
    "get_all_demo_users",
]
