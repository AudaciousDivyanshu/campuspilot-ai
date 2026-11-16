"""Transactional Email Service using Resend for CampusPilot AI.

Sends booking confirmations to authenticated students' Gmail addresses.
Handles email dispatch gracefully without causing booking rollbacks or failures.
"""

import logging
import os
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("campuspilot.email")

# Resend Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "CampusPilot AI <onboarding@resend.dev>")


def is_email_service_configured() -> bool:
    """Check if Resend API key is configured."""
    key = os.getenv("RESEND_API_KEY")
    return bool(key and key.strip() and not key.startswith("re_your_"))


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
    """Send a transactional booking confirmation email via Resend.

    Args:
        recipient_email: The student's authenticated Gmail address.
        recipient_name: The student's full name.
        facility_name: Name of the booked lab or discussion room.
        booking_date: Booking date (YYYY-MM-DD).
        start_time: Start time (HH:MM).
        end_time: End time (HH:MM).
        booking_id: Database reservation reference ID.
        facility_type: 'Laboratory' or 'Library Discussion Room'.

    Returns:
        Dict with 'success' (bool), 'message' (str), and optional 'email_id' or 'error'.
    """
    if not recipient_email or "@" not in recipient_email:
        return {
            "success": False,
            "error": "Invalid recipient email address.",
            "message": "Confirmation email skipped: No valid student email provided.",
        }

    if not is_email_service_configured():
        msg = f"Email notification simulated (RESEND_API_KEY not configured). Intended recipient: {recipient_email}."
        logger.info(msg)
        return {
            "success": True,
            "simulated": True,
            "message": f"Booking confirmed! (Email delivery to {recipient_email} requires RESEND_API_KEY in .env)",
        }

    try:
        import resend

        resend.api_key = os.getenv("RESEND_API_KEY")

        subject = f"Confirmed: {facility_name} Reservation #{booking_id} - CampusPilot AI"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
            .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
            .header {{ background: #0f172a; padding: 24px 32px; color: #ffffff; }}
            .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
            .header p {{ margin: 4px 0 0 0; font-size: 13px; color: #94a3b8; }}
            .content {{ padding: 32px; }}
            .badge {{ display: inline-block; background: #ecfdf5; color: #047857; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; border: 1px solid #a7f3d0; margin-bottom: 16px; }}
            .grid {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 20px 0; }}
            .item {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #edf2f7; font-size: 14px; }}
            .item:last-child {{ border-bottom: none; }}
            .label {{ color: #64748b; font-weight: 500; }}
            .value {{ font-weight: 600; color: #0f172a; text-align: right; }}
            .footer {{ background: #f8fafc; padding: 16px 32px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>🎓 CampusPilot AI</h1>
              <p>Your Intelligent Campus Assistant</p>
            </div>
            <div class="content">
              <span class="badge">● Reservation Confirmed</span>
              <p>Hello <strong>{recipient_name}</strong>,</p>
              <p>Your reservation for <strong>{facility_name}</strong> has been successfully registered in the campus system.</p>
              
              <div class="grid">
                <div class="item">
                  <span class="label">Reference ID:</span>
                  <span class="value">#{booking_id}</span>
                </div>
                <div class="item">
                  <span class="label">Service Type:</span>
                  <span class="value">{facility_type}</span>
                </div>
                <div class="item">
                  <span class="label">Facility:</span>
                  <span class="value">{facility_name}</span>
                </div>
                <div class="item">
                  <span class="label">Date:</span>
                  <span class="value">{booking_date}</span>
                </div>
                <div class="item">
                  <span class="label">Time Interval:</span>
                  <span class="value">{start_time} to {end_time}</span>
                </div>
                <div class="item">
                  <span class="label">Status:</span>
                  <span class="value">Confirmed</span>
                </div>
              </div>

              <p style="font-size: 13px; color: #64748b;">
                Please present this reference number upon arrival at the facility.
                If you need to change your slot, please communicate with CampusPilot AI.
              </p>
            </div>
            <div class="footer">
              CampusPilot AI &bull; Autonomous Multi-Step Campus Workflow System
            </div>
          </div>
        </body>
        </html>
        """

        from_addr = os.getenv("RESEND_FROM_EMAIL", RESEND_FROM_EMAIL)
        params: resend.Emails.SendParams = {
            "from": from_addr,
            "to": [recipient_email],
            "subject": subject,
            "html": html_content,
        }

        response = resend.Emails.send(params)
        email_id = getattr(response, "id", None) or (response.get("id") if isinstance(response, dict) else str(response))

        return {
            "success": True,
            "simulated": False,
            "email_id": email_id,
            "message": f"Confirmation email successfully sent to {recipient_email}!",
        }

    except Exception as e:
        err_str = str(e)
        logger.error(f"Failed to dispatch email via Resend: {err_str}")
        return {
            "success": False,
            "error": err_str,
            "message": f"Booking confirmed, but email delivery to {recipient_email} encountered an issue: {err_str}",
        }
