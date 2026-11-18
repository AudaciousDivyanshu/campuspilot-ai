"""Gmail SMTP Transactional Email Service for CampusPilot AI.

Uses Python standard library smtplib and email.mime for reliable, zero-external-SDK
delivery through Gmail SMTP (smtp.gmail.com:587) with TLS encryption.

Capabilities:
1. Student login OTP emails (with 5-minute expiry warning and security notices).
2. Booking confirmation emails (including reference ID, student details, facility name,
   date, and time interval).
3. Failure isolation (email failures never rollback or cancel successful SQLite bookings).
4. Idempotency protection (suppresses duplicate dispatches on UI reruns).
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import os
import smtplib
from typing import Any, Dict, Optional, Set
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("campuspilot.email")

# Gmail SMTP Configuration from environment variables
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip() or "587")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "").strip()
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "").strip()
EMAIL_SENDER_NAME = os.getenv("EMAIL_SENDER_NAME", "CampusPilot AI").strip() or "CampusPilot AI"

# In-memory idempotency cache to prevent repeat email dispatches for the same reservation
_dispatched_confirmations: Set[str] = set()


def reset_email_dispatch_cache() -> None:
    """Reset the duplicate-dispatch cache (used for unit testing)."""
    global _dispatched_confirmations
    _dispatched_confirmations.clear()


def is_smtp_configured() -> bool:
    """Check whether valid Gmail SMTP credentials are configured in the environment."""
    addr = os.getenv("EMAIL_ADDRESS", "").strip()
    pwd = os.getenv("EMAIL_APP_PASSWORD", "").strip()
    return bool(
        addr
        and "@" in addr
        and not addr.startswith("your_")
        and not addr.endswith("@example.com")
        and pwd
        and len(pwd) >= 8
        and not pwd.startswith("your_")
    )


def is_email_service_configured() -> bool:
    """Public helper for UI to check if email service is active."""
    return is_smtp_configured()


def _sanitize_error_msg(error: Exception | str) -> str:
    """Ensure error messages never expose passwords, keys, or sensitive credentials."""
    raw = str(error)
    pwd = os.getenv("EMAIL_APP_PASSWORD", "").strip()
    if pwd and pwd in raw:
        raw = raw.replace(pwd, "********")
    return raw


def send_smtp_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an email using Gmail SMTP with STARTTLS encryption.

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        html_content: HTML body content.
        text_content: Optional plain-text fallback content.

    Returns:
        Dict with 'success' (bool), 'message' (str), and optional 'error' (str).
    """
    clean_to = (to_email or "").strip().lower()
    if not clean_to or "@" not in clean_to:
        return {"success": False, "error": "Invalid recipient email address.", "message": "Email skipped: invalid address."}

    if not is_smtp_configured():
        msg = (
            f"Gmail SMTP is not configured. (To enable real inbox delivery, "
            f"set EMAIL_ADDRESS and EMAIL_APP_PASSWORD in .env)"
        )
        logger.warning(msg)
        return {
            "success": False,
            "error": "SMTP_NOT_CONFIGURED",
            "message": msg,
        }

    host = os.getenv("SMTP_HOST", SMTP_HOST).strip() or "smtp.gmail.com"
    port = int(os.getenv("SMTP_PORT", str(SMTP_PORT)).strip() or "587")
    sender_addr = os.getenv("EMAIL_ADDRESS", EMAIL_ADDRESS).strip()
    sender_pwd = os.getenv("EMAIL_APP_PASSWORD", EMAIL_APP_PASSWORD).strip()
    sender_name = os.getenv("EMAIL_SENDER_NAME", EMAIL_SENDER_NAME).strip() or "CampusPilot AI"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_addr}>"
    msg["To"] = clean_to

    # Attach text fallback if available
    if text_content:
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=12) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_addr, sender_pwd)
            server.send_message(msg)

        logger.info(f"Email successfully dispatched to {clean_to} via Gmail SMTP.")
        return {
            "success": True,
            "provider": "gmail_smtp",
            "message": f"Email successfully sent to {clean_to}!",
        }

    except smtplib.SMTPAuthenticationError as exc:
        safe_err = _sanitize_error_msg(exc)
        logger.error(f"Gmail SMTP authentication failed: {safe_err}")
        return {
            "success": False,
            "provider": "gmail_smtp",
            "error": "Authentication failed",
            "message": "Gmail SMTP authentication failed. Please verify your 16-character App Password in .env.",
        }
    except Exception as exc:
        safe_err = _sanitize_error_msg(exc)
        logger.error(f"Gmail SMTP dispatch error for {clean_to}: {safe_err}")
        return {
            "success": False,
            "provider": "gmail_smtp",
            "error": safe_err,
            "message": f"Email delivery encountered an error: {safe_err}",
        }


def send_otp_email(
    to_email: str,
    recipient_name: str,
    otp_code: str,
) -> Dict[str, Any]:
    """Send a secure 6-digit login verification OTP to a student's email.

    Args:
        to_email: Student email address.
        recipient_name: Student name or derived greeting.
        otp_code: 6-digit numeric OTP string.

    Returns:
        Dict with 'success' (bool) and 'message' (str).
    """
    clean_name = (recipient_name or "").strip() or "Student"
    subject = f"Your CampusPilot AI Verification Code: {otp_code}"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verification Code - CampusPilot AI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .container {{ max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    .header {{ background: #0f172a; padding: 28px 32px; color: #ffffff; text-align: left; }}
    .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
    .header p {{ margin: 6px 0 0 0; font-size: 13px; color: #94a3b8; }}
    .content {{ padding: 32px; }}
    .otp-card {{ background: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 10px; padding: 20px; text-align: center; margin: 24px 0; }}
    .otp-digits {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #1e40af; font-family: monospace; }}
    .badge {{ display: inline-block; background: #eff6ff; color: #1d4ed8; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; border: 1px solid #bfdbfe; margin-bottom: 14px; }}
    .warning {{ background: #fffbeb; border-left: 3px solid #f59e0b; padding: 12px 16px; border-radius: 4px; font-size: 13px; color: #92400e; margin-top: 20px; line-height: 1.5; }}
    .footer {{ background: #f8fafc; padding: 18px 32px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🎓 CampusPilot AI</h1>
      <p>Intelligent Multi-Service Campus Assistant</p>
    </div>
    <div class="content">
      <span class="badge">Student Identity Verification</span>
      <p style="margin: 0 0 12px 0; font-size: 15px;">Hello <strong>{clean_name}</strong>,</p>
      <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.5;">
        Use the following one-time verification code (OTP) to securely access the CampusPilot AI student dashboard:
      </p>

      <div class="otp-card">
        <div style="font-size: 12px; color: #64748b; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 1px;">Your Verification Code</div>
        <div class="otp-digits">{otp_code}</div>
      </div>

      <div class="warning">
        ⏳ <strong>Security Notice:</strong> This verification code expires in <strong>5 minutes</strong> and can only be used once. Never share this code with anyone.
      </div>
    </div>
    <div class="footer">
      CampusPilot AI &bull; Autonomous Multi-Step Campus Workflow System<br>
      If you did not request this code, you can safely ignore this email.
    </div>
  </div>
</body>
</html>"""

    text_fallback = (
        f"CampusPilot AI Verification Code\n\n"
        f"Hello {clean_name},\n\n"
        f"Your verification code is: {otp_code}\n\n"
        f"This code will expire in 5 minutes. Do not share it with anyone."
    )

    return send_smtp_email(to_email, subject, html_content, text_fallback)


def build_confirmation_html(
    recipient_name: str,
    facility_name: str,
    booking_date: str,
    start_time: str,
    end_time: str,
    booking_id: int | str,
    facility_type: str = "Campus Facility",
) -> str:
    """Render the responsive HTML confirmation email template."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Booking Confirmation - CampusPilot AI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    .header {{ background: #0f172a; padding: 28px 32px; color: #ffffff; text-align: left; }}
    .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }}
    .header p {{ margin: 6px 0 0 0; font-size: 13px; color: #94a3b8; }}
    .content {{ padding: 32px; }}
    .badge {{ display: inline-block; background: #ecfdf5; color: #047857; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; border: 1px solid #a7f3d0; margin-bottom: 16px; }}
    .grid {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; }}
    .item {{ display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #edf2f7; font-size: 14px; }}
    .item:last-child {{ border-bottom: none; }}
    .label {{ color: #64748b; font-weight: 500; }}
    .value {{ font-weight: 600; color: #0f172a; text-align: right; }}
    .footer {{ background: #f8fafc; padding: 20px 32px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; line-height: 1.5; }}
    .notice {{ background: #eff6ff; border-left: 3px solid #3b82f6; padding: 12px 16px; border-radius: 4px; font-size: 13px; color: #1e40af; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🎓 CampusPilot AI</h1>
      <p>Autonomous Multi-Step Campus Workflow Assistant</p>
    </div>
    <div class="content">
      <span class="badge">● Reservation Confirmed</span>
      <p style="margin: 0 0 12px 0; font-size: 15px;">Hello <strong>{recipient_name}</strong>,</p>
      <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.5;">
        Your reservation for <strong>{facility_name}</strong> has been successfully registered in the campus database.
      </p>

      <div class="grid">
        <div class="item">
          <span class="label">Reference ID:</span>
          <span class="value">#{booking_id}</span>
        </div>
        <div class="item">
          <span class="label">Service Category:</span>
          <span class="value">{facility_type}</span>
        </div>
        <div class="item">
          <span class="label">Facility / Room:</span>
          <span class="value">{facility_name}</span>
        </div>
        <div class="item">
          <span class="label">Reservation Date:</span>
          <span class="value">{booking_date}</span>
        </div>
        <div class="item">
          <span class="label">Time Interval:</span>
          <span class="value">{start_time} to {end_time}</span>
        </div>
        <div class="item">
          <span class="label">Database Status:</span>
          <span class="value">Confirmed (Active)</span>
        </div>
      </div>

      <div class="notice">
        <strong>Campus Guidelines:</strong> Please present Reference <strong>#{booking_id}</strong> at the faculty/lab desk upon check-in. If you need to cancel or modify your reservation, please communicate with CampusPilot AI.
      </div>
    </div>
    <div class="footer">
      CampusPilot AI &bull; Intelligent Multi-Service Campus Assistant<br>
      This is an automated operational notification.
    </div>
  </div>
</body>
</html>"""


def send_booking_confirmation_email(
    recipient_email: str,
    recipient_name: str,
    facility_name: str,
    booking_date: str,
    start_time: str,
    end_time: str,
    booking_id: int | str,
    facility_type: str = "Campus Facility",
) -> Dict[str, Any]:
    """Send a transactional booking confirmation email via Gmail SMTP.

    Guarantees:
    - Never cancels or compromises a successfully saved SQLite booking.
    - Suppresses duplicate email dispatch if retried with identical booking credentials.
    - Captures SMTP errors gracefully and alerts the UI without failing the reservation.

    Args:
        recipient_email: The student's email address.
        recipient_name: The student's full name.
        facility_name: Name of the booked lab or discussion room.
        booking_date: Booking date (YYYY-MM-DD).
        start_time: Start time (HH:MM).
        end_time: End time (HH:MM).
        booking_id: Database reservation reference ID.
        facility_type: 'Campus Laboratory' or 'Library Discussion Room'.

    Returns:
        Dict with 'success' (bool), 'message' (str), and optional 'error' (str).
    """
    clean_email = (recipient_email or "").strip().lower()
    clean_name = (recipient_name or "").strip() or "Student"
    clean_booking_id = str(booking_id).strip()

    if not clean_email or "@" not in clean_email:
        return {
            "success": False,
            "error": "Invalid recipient email address.",
            "message": "Confirmation email skipped: No valid student email provided.",
        }

    # Idempotency check: prevent duplicate dispatch for the exact same reservation
    dispatch_key = f"{facility_type}:{clean_booking_id}:{booking_date}:{start_time}"
    if dispatch_key in _dispatched_confirmations:
        msg = f"Confirmation email already dispatched for {facility_type} #{clean_booking_id} (duplicate suppressed)."
        logger.info(msg)
        return {
            "success": True,
            "duplicate": True,
            "message": msg,
        }

    subject = f"Confirmed: {facility_name} Reservation #{clean_booking_id} - CampusPilot AI"
    html_content = build_confirmation_html(
        recipient_name=clean_name,
        facility_name=facility_name,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        booking_id=clean_booking_id,
        facility_type=facility_type,
    )

    text_fallback = (
        f"Confirmed: {facility_name} Reservation #{clean_booking_id}\n\n"
        f"Hello {clean_name},\n\n"
        f"Your reservation for {facility_name} on {booking_date} from {start_time} to {end_time} "
        f"has been confirmed (Reference ID: #{clean_booking_id})."
    )

    result = send_smtp_email(clean_email, subject, html_content, text_fallback)
    if result.get("success"):
        _dispatched_confirmations.add(dispatch_key)
    return result
