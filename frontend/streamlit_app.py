"""CampusPilot AI — Premium Campus Management Platform & Autonomous AI Assistant.

A university productivity platform for multi-step campus facility workflows:
- Visual Design System: Deep navy & indigo sidebar, clean SaaS workspace, purple/blue gradient accents.
- Autonomous AI Assistant: Natural-language request parsing (facility, date, time, capacity, purpose),
  real-time SQLite conflict prevention, ranked recommendations, and Human-in-the-Loop confirmation gate.
- 8 Dedicated Navigation Views:
  1. 📊 Dashboard: Unified SaaS overview, 4 stats cards, balanced 2-column workspace, quick actions.
  2. 💬 AI Assistant: Fullscreen conversational assistant with interactive recommendation cards.
  3. 🔬 Lab Booking: Direct workstation availability checker and reservation form.
  4. 📚 Discussion Rooms: Library collaborative study room booking.
  5. 📋 My Bookings: User-isolated reservation ledger with cancellation support.
  6. 🏢 Facilities: Detailed campus facility catalog with equipment and capacity specs.
  7. 📈 Analytics: Real-time utilization charts and booking metrics from SQLite.
  8. ⚙️ Settings: Student profile management, notification preferences, and system diagnostics.
- Student Identity:
  * Dynamic identity resolution with Arnav as default demo identity.
  * Real-time profile switching (Arnav, Rahul, Student).
  * Authentication code fully preserved for seamless toggle.
"""

from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys
import time
from dotenv import load_dotenv
import requests
import streamlit as st

# ==============================================================================
# ABSOLUTE PROJECT ROOT PRECEDENCE & PACKAGE ISOLATION
# ==============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT_STR = str(PROJECT_ROOT)

if sys.path[0] != PROJECT_ROOT_STR:
    if PROJECT_ROOT_STR in sys.path:
        sys.path.remove(PROJECT_ROOT_STR)
    sys.path.insert(0, PROJECT_ROOT_STR)

if "app" in sys.modules and not hasattr(sys.modules["app"], "__path__"):
    del sys.modules["app"]

load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.booking_agent import CampusBookingAgent
from app.database.operations import (
    cancel_reservation,
    check_booking_overlap,
    check_room_booking_overlap,
    create_booking,
    create_room_booking,
    get_all_discussion_rooms,
    get_all_laboratories,
    get_all_student_reservations,
    get_bookings_by_date,
    get_discussion_room_by_id,
    get_facility_details_by_id,
    get_laboratory_by_id,
    get_room_bookings_by_date,
    get_student_profile,
    get_student_profile_by_email,
    recommend_matching_facilities,
    upsert_student_profile,
)
from app.services.supabase_auth import (
    get_demo_profiles,
    is_supabase_configured,
    send_email_otp,
    sign_out_student,
    verify_email_otp,
)
from app.services.email_service import (
    is_email_service_configured,
    is_smtp_configured,
    send_booking_confirmation_email,
)
from app.tools.campus_tools import (
    check_lab_availability,
    check_room_availability,
    create_lab_booking,
    create_room_reservation,
)
from app.tools.date_utils import get_current_date_context, resolve_relative_dates_in_text

# ==============================================================================
# CONFIGURATION & AUTHENTICATION TOGGLE
# ==============================================================================
# Set AUTH_PAUSED = True to bypass forced OTP login and open the dashboard directly.
# Authentication implementation is preserved and can be reactivated anytime.
AUTH_PAUSED = True

BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

# Streamlit Page Configuration
st.set_page_config(
    page_title="CampusPilot AI — Campus Management Platform",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Demo Student Profiles (for demonstration and identity switching)
AVAILABLE_PROFILES = [
    {
        "user_id": "student_arnav_001",
        "full_name": "Arnav",
        "email": "arnav@campus.edu",
        "roll_no": "CS2026-001",
        "department": "Computer Science & Engineering",
        "avatar": "👨‍🎓",
    },
    {
        "user_id": "student_rahul_002",
        "full_name": "Rahul",
        "email": "rahul@campus.edu",
        "roll_no": "AI2026-002",
        "department": "AI & Data Science",
        "avatar": "👨‍🎓",
    },
    {
        "user_id": "student_unknown_003",
        "full_name": "",
        "email": "student@campus.edu",
        "roll_no": "GEN2026-003",
        "department": "Engineering & Technology",
        "avatar": "🧑‍🎓",
    },
]

# Initialize Session State
if "authenticated_user" not in st.session_state or st.session_state.authenticated_user is None:
    st.session_state.authenticated_user = AVAILABLE_PROFILES[0] if AUTH_PAUSED else None

if "current_page" not in st.session_state:
    st.session_state.current_page = "📊 Dashboard"

if "otp_step" not in st.session_state:
    st.session_state.otp_step = "request"

if "otp_email_sent_to" not in st.session_state:
    st.session_state.otp_email_sent_to = ""

if "otp_student_name" not in st.session_state:
    st.session_state.otp_student_name = ""

# ==============================================================================
# PREMIUM SAAS STYLING SYSTEM (CSS)
# ==============================================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background-color: #f8fafc;
    }

    /* Reduce excess top space in Streamlit main container */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2.5rem !important;
        max-width: 1300px;
    }

    /* Deep Navy Sidebar Overrides */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1120 0%, #0f172a 100%) !important;
        border-right: 1px solid #1e293b !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: #e2e8f0 !important;
    }

    /* Compact Top Brand Navbar */
    .top-navbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.75rem 1.25rem;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 1.1rem;
    }

    .brand-group {
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }

    .brand-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #0f172a;
        margin: 0;
        letter-spacing: -0.02em;
    }

    .brand-tagline {
        font-size: 0.8rem;
        color: #64748b;
        font-weight: 500;
        border-left: 1px solid #cbd5e1;
        padding-left: 0.6rem;
        margin-left: 0.3rem;
    }

    /* Modern Badges & Indicators */
    .badge-live {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: #ecfdf5;
        color: #047857;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid #a7f3d0;
    }

    .badge-offline {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: #fff1f2;
        color: #be123c;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid #fecdd3;
    }

    .badge-profile-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #f1f5f9;
        color: #1e293b;
        padding: 0.25rem 0.7rem;
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 600;
        border: 1px solid #e2e8f0;
    }

    /* Compact Hero Welcome Banner */
    .hero-banner {
        background: linear-gradient(135deg, #4338ca 0%, #6366f1 50%, #7c3aed 100%);
        border-radius: 16px;
        padding: 1.35rem 1.6rem;
        color: #ffffff;
        box-shadow: 0 8px 20px -4px rgba(99, 102, 241, 0.22);
        margin-bottom: 1.1rem;
    }

    .hero-title {
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0 0 0.3rem 0;
        color: #ffffff;
    }

    .hero-subtitle {
        font-size: 0.88rem;
        color: #e0e7ff;
        margin: 0;
        line-height: 1.5;
        font-weight: 400;
    }

    /* Statistics Cards */
    .stat-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1rem 1.15rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 1rem;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }

    .stat-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 14px rgba(15, 23, 42, 0.06);
    }

    .stat-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.3rem;
    }

    .stat-label {
        font-size: 0.72rem;
        color: #64748b;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    .stat-icon {
        font-size: 1.2rem;
    }

    .stat-value {
        font-size: 1.65rem;
        font-weight: 800;
        color: #0f172a;
        margin: 0.1rem 0;
        letter-spacing: -0.02em;
    }

    .stat-footer {
        font-size: 0.74rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    /* Content Cards */
    .content-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1.25rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 1rem;
    }

    .card-header-title {
        font-size: 1.05rem;
        font-weight: 800;
        color: #0f172a;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.3rem;
        letter-spacing: -0.01em;
    }

    .card-header-sub {
        font-size: 0.8rem;
        color: #64748b;
        margin-bottom: 0.9rem;
    }

    /* Interactive Facility Recommendation Card */
    .rec-card {
        background: #ffffff;
        border: 1.5px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.1rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.03);
        transition: all 0.2s ease;
    }

    .rec-card:hover {
        border-color: #6366f1;
        box-shadow: 0 6px 16px rgba(99, 102, 241, 0.08);
    }

    .rec-badge-best {
        background: #f5f3ff;
        color: #6d28d9;
        border: 1px solid #ddd6fe;
        font-size: 0.72rem;
        font-weight: 800;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
    }

    .rec-badge-alt {
        background: #eff6ff;
        color: #1d4ed8;
        border: 1px solid #bfdbfe;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
    }

    /* Human Confirmation Gate Alert Card */
    .booking-confirm-card {
        background: #faf5ff;
        border: 2px solid #8b5cf6;
        border-radius: 14px;
        padding: 1.25rem;
        margin: 1rem 0;
        box-shadow: 0 6px 18px rgba(139, 92, 246, 0.1);
    }

    .booking-confirm-header {
        font-size: 1.05rem;
        font-weight: 800;
        color: #5b21b6;
        margin-bottom: 0.4rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    .booking-details-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 0.65rem;
        margin-top: 0.8rem;
        margin-bottom: 1rem;
    }

    .booking-item {
        background: #ffffff;
        border: 1px solid #e9d5ff;
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
    }

    .booking-item-label {
        font-size: 0.65rem;
        color: #7c3aed;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.04em;
    }

    .booking-item-value {
        font-size: 0.88rem;
        font-weight: 800;
        color: #0f172a;
        margin-top: 0.1rem;
    }

    /* Upcoming Booking Row Item */
    .booking-row {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.75rem 0.95rem;
        margin-bottom: 0.55rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.02);
    }

    /* Empty state */
    .empty-state-box {
        background: #f8fafc;
        border: 1.5px dashed #cbd5e1;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        color: #64748b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# HELPERS & SINGLETONS
# ==============================================================================
@st.cache_data(ttl=10)
def check_backend_health() -> bool:
    try:
        res = requests.get(f"{BACKEND_URL}/health", timeout=1.5)
        return res.status_code == 200
    except Exception:
        return False

@st.cache_resource
def get_agent():
    return CampusBookingAgent()

# Initialize Chat State with Clear Capability Introduction
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **Hi! I'm CampusPilot AI.** Tell me what you need, and I'll help you find and reserve the right campus facility.\n\n"
                "**Here is what I can do for you:**\n"
                "• **Find available laboratories** based on class size, date, and time slot.\n"
                "• **Find library discussion rooms** for collaborative study or team projects.\n"
                "• **Check facility capacity & hardware** (GPUs, workstations, whiteboards).\n"
                "• **Recommend the best available match** and prevent double-booking conflicts.\n"
                "• **Securely create your reservation** and provide an instant reference `#ID`.\n\n"
                "Try clicking a prompt chip above or type in natural language below!"
            ),
            "steps": [],
            "recommendations": [],
        }
    ]

if "langchain_history" not in st.session_state:
    st.session_state.langchain_history = []

if "pending_booking" not in st.session_state:
    st.session_state.pending_booking = None

# ==============================================================================
# AUTHENTICATION GATE (Preserved for Future Activation)
# ==============================================================================
if not AUTH_PAUSED and st.session_state.authenticated_user is None:
    st.markdown(
        """
        <div class="top-navbar">
            <div class="brand-group">
                <span style="font-size: 1.4rem;">🎓</span>
                <span class="brand-title">CampusPilot AI</span>
                <span class="brand-tagline">Student Authentication Gateway</span>
            </div>
            <div>
                <span class="badge-live">● Supabase Auth Ready</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_hero, col_login = st.columns([1, 1.2], gap="large")

    with col_hero:
        st.markdown(
            """
            <div class="content-card" style="height: 100%;">
                <span class="badge-live" style="margin-bottom: 0.8rem;">Autonomous Operations</span>
                <h2 style="font-size: 1.55rem; font-weight: 800; color: #0f172a; margin: 0.2rem 0 0.6rem 0;">
                    Smart Campus Scheduling
                </h2>
                <p style="color: #475569; font-size: 0.92rem; line-height: 1.6;">
                    Sign in to coordinate campus laboratories and collaborative discussion rooms. Your verified profile ensures user-isolated bookings with zero scheduling conflicts.
                </p>
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.9rem; margin-top: 1rem;">
                    <div style="font-weight: 700; font-size: 0.85rem; color: #0f172a; margin-bottom: 0.3rem;">Demonstration Identity Policy:</div>
                    <ul style="color: #475569; font-size: 0.82rem; padding-left: 1.1rem; margin: 0; line-height: 1.6;">
                        <li><strong>Arnav</strong> is the primary demonstration profile.</li>
                        <li>Every other student sees their <strong>own registered name</strong> (e.g. Rahul).</li>
                        <li>Incomplete profiles display the neutral <strong>Student</strong> fallback.</li>
                    </ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_login:
        st.markdown("### 🔐 Student Sign In")
        tab_email, tab_demo = st.tabs(["📧 Email OTP Login", "⚡ Verified Demo Profiles"])

        with tab_email:
            st.caption("Sign in with your email address via passwordless OTP code:")
            if st.session_state.otp_step == "request":
                with st.form("form_request_otp"):
                    input_email = st.text_input("Email Address", placeholder="e.g. arnav@campus.edu or rahul@campus.edu")
                    input_name = st.text_input("Full Name (Optional)", placeholder="e.g. Arnav")
                    submit_otp = st.form_submit_button("📨 Send Verification Code", type="primary", use_container_width=True)

                if submit_otp and "@" in input_email and "." in input_email:
                    with st.spinner("Dispatching verification code..."):
                        res = send_email_otp(input_email.strip(), input_name.strip() if input_name else None)
                        if res.get("success"):
                            st.session_state.otp_email_sent_to = input_email.strip().lower()
                            st.session_state.otp_student_name = input_name.strip() if input_name else ""
                            st.session_state.otp_step = "verify"
                            st.success(res.get("message", "Verification code dispatched."))
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(res.get("error", "Failed to dispatch verification code."))
            else:
                sent_to = st.session_state.otp_email_sent_to
                st.info(f"Verification code sent to **{sent_to}**.")
                with st.form("form_verify_otp"):
                    input_otp = st.text_input("Enter 6-Digit Code", max_chars=6, placeholder="e.g. 123456")
                    submit_verify = st.form_submit_button("✅ Verify & Enter Dashboard", type="primary", use_container_width=True)

                if submit_verify and input_otp.strip():
                    with st.spinner("Verifying code..."):
                        ver_res = verify_email_otp(sent_to, input_otp.strip(), st.session_state.otp_student_name)
                        if ver_res.get("success"):
                            st.session_state.authenticated_user = ver_res
                            st.session_state.otp_step = "request"
                            st.success("Verification successful!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(ver_res.get("error", "Verification failed."))

        with tab_demo:
            st.caption("Instant verified profiles for presentation and evaluation:")
            demo_profs = get_demo_profiles()
            for prof in demo_profs:
                disp_label = prof["full_name"] if prof.get("full_name") else "New Student (Incomplete Profile)"
                btn_caption = f"⚡ Continue as {disp_label} ({prof['email']})"
                if st.button(btn_caption, key=f"demo_btn_{prof['user_id']}", use_container_width=True):
                    upsert_student_profile(
                        user_id=prof["user_id"],
                        full_name=prof["full_name"],
                        email=prof["email"],
                        department=prof.get("department", "Engineering & Technology"),
                    )
                    st.session_state.authenticated_user = prof
                    st.session_state.messages = []
                    st.session_state.langchain_history = []
                    st.session_state.pending_booking = None
                    st.rerun()

    st.stop()


# ==============================================================================
# DYNAMIC STUDENT IDENTITY RESOLUTION
# ==============================================================================
auth_user = st.session_state.authenticated_user or AVAILABLE_PROFILES[0]
user_id = str(auth_user.get("user_id", "student_arnav_001")).strip()

# Always check SQLite database for the freshest registered student record
db_profile = get_student_profile(user_id) or get_student_profile_by_email(auth_user.get("email", ""))
if db_profile:
    raw_name = db_profile.get("full_name", "").strip()
    student_email = db_profile.get("email", auth_user.get("email", "arnav@campus.edu"))
    department = db_profile.get("department", "Computer Science & Engineering")
else:
    raw_name = auth_user.get("full_name", "").strip()
    student_email = auth_user.get("email", "arnav@campus.edu")
    department = auth_user.get("department", "Computer Science & Engineering")

# Neutral fallback "Student" if full_name is missing (never hardcoded or randomized)
student_name = raw_name if raw_name else "Student"
has_completed_profile = bool(raw_name)

date_ctx = get_current_date_context()
today_str = date_ctx["today"]
tomorrow_str = date_ctx["tomorrow"]

# ==============================================================================
# BOOKING COMMIT HELPER
# ==============================================================================
def confirm_pending_booking():
    """Commit verified reservation to SQLite and dispatch confirmation email."""
    pending = st.session_state.pending_booking
    if not pending:
        return

    st.session_state.pending_booking = None
    service_type = pending.get("service_type", "lab")

    with st.spinner("Recording confirmed reservation in campus database..."):
        try:
            if service_type == "room":
                res_output = create_room_reservation.invoke({
                    "student_id": user_id,
                    "student_name": student_name,
                    "room_id": int(pending["item_id"]),
                    "booking_date": pending["booking_date"],
                    "start_time": pending["start_time"],
                    "end_time": pending["end_time"],
                })
                tool_used = "create_room_reservation"
                facility_label = "Library Discussion Room"
            else:
                res_output = create_lab_booking.invoke({
                    "student_id": user_id,
                    "student_name": student_name,
                    "lab_id": int(pending["item_id"]),
                    "booking_date": pending["booking_date"],
                    "start_time": pending["start_time"],
                    "end_time": pending["end_time"],
                })
                tool_used = "create_lab_booking"
                facility_label = "Campus Laboratory"

            booking_id_match = re.search(r"Booking ID:\s*(\d+)", res_output)
            booking_id_val = booking_id_match.group(1) if booking_id_match else "CONFIRMED"

            if is_smtp_configured():
                email_result = send_booking_confirmation_email(
                    recipient_email=student_email,
                    recipient_name=student_name,
                    facility_name=pending["item_name"],
                    booking_date=pending["booking_date"],
                    start_time=pending["start_time"],
                    end_time=pending["end_time"],
                    booking_id=booking_id_val,
                    facility_type=facility_label,
                )
                st.session_state.last_email_result = email_result

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": res_output,
                    "steps": [
                        {
                            "tool": tool_used,
                            "args": pending,
                            "observation": res_output,
                        }
                    ],
                    "recommendations": [],
                }
            )
            st.session_state.langchain_history.append(AIMessage(content=res_output))

        except Exception as e:
            err_msg = f"Failed to confirm reservation: {str(e)}"
            st.session_state.messages.append({"role": "assistant", "content": err_msg, "steps": [], "recommendations": []})
            st.session_state.langchain_history.append(AIMessage(content=err_msg))


def process_user_input(user_text: str):
    clean_text = user_text.strip()
    if not clean_text:
        return

    lower_input = clean_text.lower()

    if st.session_state.pending_booking and lower_input in ("confirm", "yes", "proceed", "go ahead", "confirm booking", "confirm reservation"):
        confirm_pending_booking()
        return

    if st.session_state.pending_booking and lower_input in ("cancel", "no", "stop"):
        st.session_state.pending_booking = None
        cancel_text = "The pending reservation request was cancelled."
        st.session_state.messages.append({"role": "assistant", "content": cancel_text, "steps": [], "recommendations": []})
        st.session_state.langchain_history.append(AIMessage(content=cancel_text))
        return

    anchored_text = resolve_relative_dates_in_text(clean_text)
    st.session_state.messages.append({"role": "user", "content": clean_text, "steps": [], "recommendations": []})
    st.session_state.langchain_history.append(HumanMessage(content=anchored_text))

    student_ctx = {
        "student_name": student_name,
        "student_id": user_id,
        "student_email": student_email,
    }

    try:
        agent = get_agent()
        with st.spinner("CampusPilot AI is analyzing your inquiry and consulting campus tools..."):
            result = agent.run(
                messages=st.session_state.langchain_history,
                student_context=student_ctx,
            )

        assistant_text = result["response"]
        steps = result.get("steps", [])
        recommendations = result.get("recommendations", [])

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": assistant_text,
                "steps": steps,
                "recommendations": recommendations,
            }
        )
        st.session_state.langchain_history.append(AIMessage(content=assistant_text))

        if result.get("pending_booking"):
            pending = result["pending_booking"]
            pending["student_id"] = user_id
            pending["student_name"] = student_name
            st.session_state.pending_booking = pending
        else:
            st.session_state.pending_booking = None

    except Exception as exc:
        err_msg = f"An unexpected error occurred: {str(exc)}"
        st.session_state.messages.append({"role": "assistant", "content": err_msg, "steps": [], "recommendations": []})
        st.session_state.langchain_history.append(AIMessage(content=err_msg))


# ==============================================================================
# SIDEBAR NAVIGATION & STUDENT PROFILE
# ==============================================================================
NAV_PAGES = [
    "📊 Dashboard",
    "💬 AI Assistant",
    "🔬 Lab Booking",
    "📚 Discussion Rooms",
    "📋 My Bookings",
    "🏢 Facilities",
    "📈 Analytics",
    "⚙️ Settings",
]

with st.sidebar:
    st.markdown(
        """
        <div style="padding: 0.4rem 0.2rem 0.8rem 0.2rem; display: flex; align-items: center; gap: 0.6rem;">
            <span style="font-size: 1.75rem;">🎓</span>
            <div>
                <div style="font-weight: 800; font-size: 1.2rem; color: #ffffff; letter-spacing: -0.02em;">CampusPilot AI</div>
                <div style="font-size: 0.72rem; color: #94a3b8; font-weight: 500;">Smart Campus Operations</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Prominent New Booking Button
    if st.button("➕ New Booking", type="primary", use_container_width=True):
        st.session_state.current_page = "💬 AI Assistant"
        st.rerun()

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

    # Clean Navigation Selection
    current_idx = NAV_PAGES.index(st.session_state.current_page) if st.session_state.current_page in NAV_PAGES else 0
    selected_nav = st.radio(
        "Navigation Menu",
        NAV_PAGES,
        index=current_idx,
        label_visibility="collapsed",
    )

    if selected_nav != st.session_state.current_page:
        st.session_state.current_page = selected_nav
        st.rerun()

    st.markdown("---")

    # Bottom Profile Card
    avatar_icon = "👨‍🎓" if student_name in ("Arnav", "Rahul") else "🧑‍🎓"
    st.markdown(
        f"""
        <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 0.85rem; margin-top: 0.8rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
                <span style="font-size: 1.25rem;">{avatar_icon}</span>
                <div>
                    <div style="font-weight: 700; font-size: 0.9rem; color: #ffffff;">{student_name}</div>
                    <div style="font-size: 0.7rem; color: #94a3b8;">{student_email}</div>
                </div>
            </div>
            <div style="display: flex; gap: 0.3rem; margin-top: 0.4rem;">
                <span style="background: rgba(255,255,255,0.12); color: #cbd5e1; font-size: 0.65rem; padding: 0.12rem 0.45rem; border-radius: 4px; font-weight: 600;">{user_id[:13]}</span>
                <span style="background: rgba(99,102,241,0.25); color: #a5b4fc; font-size: 0.65rem; padding: 0.12rem 0.45rem; border-radius: 4px; font-weight: 600;">{department[:16]}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Dynamic Student Profile Switcher (allows evaluators to test identities seamlessly)
    st.caption("👤 Switch Student Profile:")
    prof_labels = ["Arnav (Demo)", "Rahul (Demo)", "Student (Neutral Profile)"]
    current_prof_idx = 0
    if student_name == "Rahul":
        current_prof_idx = 1
    elif not has_completed_profile or student_name == "Student":
        current_prof_idx = 2

    chosen_prof = st.selectbox(
        "Active Profile",
        prof_labels,
        index=current_prof_idx,
        label_visibility="collapsed",
    )
    new_profile_target = AVAILABLE_PROFILES[prof_labels.index(chosen_prof)]
    if new_profile_target["user_id"] != user_id:
        upsert_student_profile(
            user_id=new_profile_target["user_id"],
            full_name=new_profile_target["full_name"],
            email=new_profile_target["email"],
            department=new_profile_target.get("department", "Engineering & Technology"),
        )
        st.session_state.authenticated_user = new_profile_target
        st.session_state.messages = []
        st.session_state.langchain_history = []
        st.session_state.pending_booking = None
        st.rerun()

    st.caption(f"📅 Today: `{today_str}` &bull; Tomorrow: `{tomorrow_str}`")


# ==============================================================================
# COMPACT TOP APP BAR / BRAND HEADER
# ==============================================================================
backend_online = check_backend_health()
status_pill = (
    '<span class="badge-live">● Backend Live</span>'
    if backend_online
    else '<span class="badge-offline">● Backend Offline</span>'
)

st.markdown(
    f"""
    <div class="top-navbar">
        <div class="brand-group">
            <span style="font-size: 1.3rem;">🎓</span>
            <span class="brand-title">CampusPilot AI</span>
            <span class="brand-tagline">Smart Campus Operations & Facility Booking</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.65rem;">
            {status_pill}
            <span class="badge-profile-chip">🔔 2 Alerts</span>
            <span class="badge-profile-chip">{avatar_icon} {student_name} ({user_id[:12]})</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Fetch core data for metrics
labs = get_all_laboratories()
rooms = get_all_discussion_rooms()
today_lab_bookings = get_bookings_by_date(today_str)
today_room_bookings = get_room_bookings_by_date(today_str)
total_today_bookings = len(today_lab_bookings) + len(today_room_bookings)


# ==============================================================================
# VIEW 1: 📊 DASHBOARD
# ==============================================================================
if st.session_state.current_page == "📊 Dashboard":
    # 1. Compact Hero Welcome Banner
    st.markdown(
        f"""
        <div class="hero-banner">
            <h2 class="hero-title">Welcome back, {student_name}! 👋</h2>
            <p class="hero-subtitle">
                Your autonomous campus scheduling assistant. Describe what you need in plain English — I will search real-time SQLite availability, rank the best facilities, and confirm your reservation with zero conflicts.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. Suggested Prompt Chips (Direct AI Triggers - Eliminating Duplicate Input)
    st.caption("⚡ **Click any prompt to run an autonomous request:**")
    h_c1, h_c2, h_c3, h_c4 = st.columns(4)
    with h_c1:
        if st.button("🔬 Lab for 30 students tomorrow 10-12", use_container_width=True, key="h_p1"):
            process_user_input("I need a computer lab for 30 students tomorrow from 10 AM to 12 PM for a Python practical")
            st.rerun()
    with h_c2:
        if st.button("📚 Room for 4 students tomorrow 2-4 PM", use_container_width=True, key="h_p2"):
            process_user_input("Find me a discussion room for 4 people tomorrow from 2 PM to 4 PM for group study")
            st.rerun()
    with h_c3:
        if st.button("🔍 Check AI Lab tomorrow 10-12", use_container_width=True, key="h_p3"):
            process_user_input("Check if AI Lab is available tomorrow from 10:00 to 12:00")
            st.rerun()
    with h_c4:
        if st.button("📋 Show my upcoming bookings", use_container_width=True, key="h_p4"):
            process_user_input(f"Show all my upcoming reservations for {user_id}")
            st.rerun()

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

    # 3. Four Top Metric Cards
    c_s1, c_s2, c_s3, c_s4 = st.columns(4)
    with c_s1:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Laboratories</span>
                    <span class="stat-icon">🔬</span>
                </div>
                <div class="stat-value">{len(labs)}</div>
                <div class="stat-footer" style="color: #059669;">
                    <span>● 3 Active</span> &bull; <span>105 Workstations</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_s2:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Discussion Rooms</span>
                    <span class="stat-icon">📚</span>
                </div>
                <div class="stat-value">{len(rooms)}</div>
                <div class="stat-footer" style="color: #2563eb;">
                    <span>● 3 Available</span> &bull; <span>18 Collaborative Seats</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_s3:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Bookings Today</span>
                    <span class="stat-icon">📅</span>
                </div>
                <div class="stat-value">{total_today_bookings}</div>
                <div class="stat-footer" style="color: #7c3aed;">
                    <span>● SQLite Confirmed</span> &bull; <span>{today_str}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_s4:
        st.markdown(
            """
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">AI Agent Engine</span>
                    <span class="stat-icon">🤖</span>
                </div>
                <div class="stat-value">Online</div>
                <div class="stat-footer" style="color: #059669;">
                    <span>● Gemini 3.5 ReAct</span> &bull; <span>14 Tools</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

    # 4. Main Balanced Workspace (Consistent Two-Column Layout)
    col_agent_panel, col_side_panels = st.columns([1.5, 1], gap="large")

    # LEFT COLUMN: Primary AI Assistant
    with col_agent_panel:
        st.markdown(
            """
            <div class="card-header-title">
                <span>🤖 Autonomous Campus Assistant</span>
                <span class="badge-live">Ready</span>
            </div>
            <div class="card-header-sub">
                Natural-language facility search, conflict checking, and instant reservation.
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Conversation History Container
        chat_container = st.container()
        with chat_container:
            for m_idx, msg in enumerate(st.session_state.messages):
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

                    # Tool Execution Trace
                    if msg.get("steps"):
                        with st.expander(f"🛠️ Agent Execution Trace ({len(msg['steps'])} steps)", expanded=False):
                            for idx, step in enumerate(msg["steps"], 1):
                                tool_name = step.get("tool", "tool")
                                obs = str(step.get("observation", ""))
                                st.markdown(f"**Step {idx}: Executed Tool `{tool_name}`**")
                                c_a, c_o = st.columns([1, 1])
                                with c_a:
                                    st.caption("Input Parameters:")
                                    st.json(step.get("args", {}))
                                with c_o:
                                    st.caption("Database Observation:")
                                    st.code(obs[:500] + ("..." if len(obs) > 500 else ""), language="text")

                    # Interactive Facility Recommendation Cards
                    if msg.get("recommendations"):
                        st.markdown("##### 🎯 Recommended Facilities")
                        for r_idx, rec in enumerate(msg["recommendations"]):
                            badge_class = "rec-badge-best" if rec.get("match_badge") == "Best Match" else "rec-badge-alt"
                            st.markdown(
                                f"""
                                <div class="rec-card">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                                        <span style="font-weight: 800; font-size: 1.05rem; color: #0f172a;">{rec['facility_name']}</span>
                                        <span class="{badge_class}">{rec.get('match_badge', 'Option')}</span>
                                    </div>
                                    <div style="font-size: 0.82rem; color: #64748b; margin-bottom: 0.35rem;">
                                        📍 {rec.get('location')} &bull; 👥 Capacity: <b>{rec.get('capacity')}</b> &bull; ⏰ <b>{rec.get('start_time')} - {rec.get('end_time')}</b> ({rec.get('booking_date')})
                                    </div>
                                    <div style="font-size: 0.82rem; color: #334155;">
                                        💡 <i>{rec.get('match_reason')}</i>
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            if rec.get("is_available") and rec.get("is_capacity_sufficient"):
                                if st.button(f"👉 Select {rec['facility_name']} ({rec['start_time']} - {rec['end_time']})", key=f"dash_sel_{m_idx}_{r_idx}"):
                                    st.session_state.pending_booking = {
                                        "service_type": rec["facility_type"],
                                        "item_id": rec["facility_id"],
                                        "item_name": rec["facility_name"],
                                        "lab_id": rec.get("lab_id"),
                                        "room_id": rec.get("room_id"),
                                        "booking_date": rec["booking_date"],
                                        "start_time": rec["start_time"],
                                        "end_time": rec["end_time"],
                                        "student_id": user_id,
                                        "student_name": student_name,
                                    }
                                    st.rerun()

        # Human-in-the-Loop Confirmation Gate
        if st.session_state.pending_booking:
            pending = st.session_state.pending_booking
            st.markdown(
                f"""
                <div class="booking-confirm-card">
                    <div class="booking-confirm-header">
                        <span>🛡️ Confirmation Required Before Booking</span>
                    </div>
                    <p style="color: #475569; font-size: 0.88rem; margin: 0 0 0.6rem 0;">
                        The requested slot is 100% available in SQLite. Please verify before committing:
                    </p>
                    <div class="booking-details-grid">
                        <div class="booking-item">
                            <div class="booking-item-label">Facility</div>
                            <div class="booking-item-value">{pending['item_name']}</div>
                        </div>
                        <div class="booking-item">
                            <div class="booking-item-label">Date</div>
                            <div class="booking-item-value">{pending['booking_date']}</div>
                        </div>
                        <div class="booking-item">
                            <div class="booking-item-label">Time Slot</div>
                            <div class="booking-item-value">{pending['start_time']} - {pending['end_time']}</div>
                        </div>
                        <div class="booking-item">
                            <div class="booking-item-label">Student</div>
                            <div class="booking-item-value">{student_name} ({user_id[:12]})</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("✅ Confirm Booking", type="primary", use_container_width=True, key="dash_btn_confirm"):
                    confirm_pending_booking()
                    st.rerun()
            with col_b2:
                if st.button("❌ Cancel", use_container_width=True, key="dash_btn_cancel"):
                    st.session_state.pending_booking = None
                    st.rerun()

        # Single Dedicated Chat Input
        if dash_prompt := st.chat_input("Ask CampusPilot AI to book or search (e.g. 'Lab for 30 students tomorrow 10-12')..."):
            process_user_input(dash_prompt)
            st.rerun()

    # RIGHT COLUMN: Upcoming Bookings & Quick Actions
    with col_side_panels:
        # Panel A: User-Specific Upcoming Bookings
        st.markdown(
            f"""
            <div class="card-header-title">
                <span>📅 Upcoming Bookings</span>
                <span style="font-size: 0.78rem; font-weight: 600; color: #64748b;">{student_name}</span>
            </div>
            <div class="card-header-sub">
                Verified reservations retrieved strictly for your student ID.
            </div>
            """,
            unsafe_allow_html=True,
        )

        my_reservations = get_all_student_reservations(student_id=user_id)
        active_bookings = [r for r in my_reservations if r.get("status") == "confirmed"]

        if active_bookings:
            for r in active_bookings[:4]:
                st.markdown(
                    f"""
                    <div class="booking-row">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
                            <span style="font-weight: 700; font-size: 0.95rem; color: #0f172a;">{r['facility_name']}</span>
                            <span class="badge-live">REF #{r['booking_id']}</span>
                        </div>
                        <div style="font-size: 0.8rem; color: #64748b;">
                            📅 {r['booking_date']} &bull; ⏰ {r['start_time']} - {r['end_time']}<br>
                            📍 {r['location']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f"""
                <div class="empty-state-box">
                    <div style="font-size: 1.6rem; margin-bottom: 0.3rem;">📋</div>
                    <div style="font-weight: 700; color: #334155; font-size: 0.9rem;">No Active Bookings</div>
                    <div style="font-size: 0.8rem; margin-top: 0.2rem;">
                        You have no scheduled reservations. Use the AI Assistant to book a slot!
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)

        # Panel B: Quick Facility Navigation
        st.markdown(
            """
            <div class="card-header-title">
                <span>⚡ Quick Actions</span>
            </div>
            <div class="card-header-sub">
                Jump directly to dedicated reservation and catalog tools.
            </div>
            """,
            unsafe_allow_html=True,
        )
        qa_c1, qa_c2 = st.columns(2)
        with qa_c1:
            if st.button("🔬 Book Lab", use_container_width=True):
                st.session_state.current_page = "🔬 Lab Booking"
                st.rerun()
            if st.button("🏢 Facilities", use_container_width=True):
                st.session_state.current_page = "🏢 Facilities"
                st.rerun()
        with qa_c2:
            if st.button("📚 Book Room", use_container_width=True):
                st.session_state.current_page = "📚 Discussion Rooms"
                st.rerun()
            if st.button("📋 My Bookings", use_container_width=True):
                st.session_state.current_page = "📋 My Bookings"
                st.rerun()

        st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)

        # Panel C: Campus Operations Guide
        st.markdown(
            """
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem; box-shadow: 0 1px 3px rgba(15,23,42,0.03);">
                <div style="font-weight: 700; font-size: 0.88rem; color: #0f172a; margin-bottom: 0.4rem;">💡 How CampusPilot AI Works:</div>
                <div style="font-size: 0.8rem; color: #475569; line-height: 1.5;">
                    <b>1. Natural Request:</b> State your needs in plain English.<br>
                    <b>2. Conflict Check:</b> AI queries SQLite to verify zero overlaps.<br>
                    <b>3. Safety Gate:</b> Review summary and click Confirm to commit.<br>
                    <b>4. Instant Ledger:</b> Booking reference is recorded in SQLite.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 5. Lower Dashboard Section: Facilities Overview
    st.markdown("---")
    st.markdown("#### 🏢 Campus Facilities At A Glance")
    st.caption("Direct access to campus computing labs and library collaborative study spaces:")

    fac_col1, fac_col2, fac_col3 = st.columns(3)
    with fac_col1:
        st.markdown(
            """
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem;">
                <div style="font-weight: 700; color: #0f172a; margin-bottom: 0.2rem;">🔬 Computer Lab 1 & AI Lab</div>
                <div style="font-size: 0.8rem; color: #64748b;">40 & 30 Workstations &bull; High-performance GPUs & Ethernet</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with fac_col2:
        st.markdown(
            """
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem;">
                <div style="font-weight: 700; color: #0f172a; margin-bottom: 0.2rem;">🔬 Networking Lab</div>
                <div style="font-size: 0.8rem; color: #64748b;">35 Workstations &bull; Cisco Routers, Switches, Packet Tracer</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with fac_col3:
        st.markdown(
            """
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem;">
                <div style="font-weight: 700; color: #0f172a; margin-bottom: 0.2rem;">📚 Discussion Rooms 1, 2 & 3</div>
                <div style="font-size: 0.8rem; color: #64748b;">4 to 8 Seats &bull; Acoustic Panels, Whiteboards, HDMI Displays</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ==============================================================================
# VIEW 2: 💬 AI ASSISTANT (DEDICATED FULLSCREEN)
# ==============================================================================
elif st.session_state.current_page == "💬 AI Assistant":
    st.markdown(f"### 💬 CampusPilot Conversational Assistant ({student_name})")
    st.caption("Describe your scheduling needs naturally. The agent extracts constraints, queries SQLite, ranks candidate venues, and presents interactive options.")

    # Suggested prompt pills
    st.markdown("**Suggested Prompts:**")
    ap_c1, ap_c2, ap_c3, ap_c4 = st.columns(4)
    with ap_c1:
        if st.button("💻 Lab for 30 students tomorrow 10-12", use_container_width=True):
            process_user_input("I need a computer lab for 30 students tomorrow from 10 AM to 12 PM for a Python practical")
            st.rerun()
    with ap_c2:
        if st.button("📚 Room for 4 students tomorrow 2-4 PM", use_container_width=True):
            process_user_input("Find me a discussion room for 4 people tomorrow from 2 PM to 4 PM for group study")
            st.rerun()
    with ap_c3:
        if st.button("🔍 Check AI Lab Tomorrow 10-12", use_container_width=True):
            process_user_input("Check if AI Lab is available tomorrow from 10:00 to 12:00")
            st.rerun()
    with ap_c4:
        if st.button("📋 Show My Bookings", use_container_width=True):
            process_user_input(f"Show all my upcoming reservations for {user_id}")
            st.rerun()

    st.markdown("---")

    # Conversation History
    for m_idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Tool Execution Traces Expander
            if msg.get("steps"):
                with st.expander(f"🛠️ Agent Execution Trace ({len(msg['steps'])} tool steps)", expanded=False):
                    for idx, step in enumerate(msg["steps"], 1):
                        tool_name = step.get("tool", "tool")
                        obs = str(step.get("observation", ""))
                        st.markdown(f"**Step {idx}: Executed Tool `{tool_name}`**")
                        c_a, c_o = st.columns([1, 1])
                        with c_a:
                            st.caption("Input Arguments:")
                            st.json(step.get("args", {}))
                        with c_o:
                            st.caption("Database Observation:")
                            st.code(obs[:500] + ("..." if len(obs) > 500 else ""), language="text")

            # Interactive Recommendation Cards
            if msg.get("recommendations"):
                st.markdown("##### 🎯 Recommended Facilities")
                for r_idx, rec in enumerate(msg["recommendations"]):
                    badge_class = "rec-badge-best" if rec.get("match_badge") == "Best Match" else "rec-badge-alt"
                    st.markdown(
                        f"""
                        <div class="rec-card">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                                <span style="font-weight: 800; font-size: 1.05rem; color: #0f172a;">{rec['facility_name']}</span>
                                <span class="{badge_class}">{rec.get('match_badge', 'Option')}</span>
                            </div>
                            <div style="font-size: 0.84rem; color: #64748b; margin-bottom: 0.4rem;">
                                📍 {rec.get('location')} &bull; 👥 Capacity: <b>{rec.get('capacity')}</b> &bull; ⏰ <b>{rec.get('start_time')} - {rec.get('end_time')}</b> ({rec.get('booking_date')})
                            </div>
                            <div style="font-size: 0.84rem; color: #334155; margin-bottom: 0.75rem;">
                                💡 <i>{rec.get('match_reason')}</i>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if rec.get("is_available") and rec.get("is_capacity_sufficient"):
                        if st.button(f"👉 Select {rec['facility_name']} ({rec['start_time']} - {rec['end_time']})", key=f"rec_btn_{m_idx}_{r_idx}"):
                            st.session_state.pending_booking = {
                                "service_type": rec["facility_type"],
                                "item_id": rec["facility_id"],
                                "item_name": rec["facility_name"],
                                "lab_id": rec.get("lab_id"),
                                "room_id": rec.get("room_id"),
                                "booking_date": rec["booking_date"],
                                "start_time": rec["start_time"],
                                "end_time": rec["end_time"],
                                "student_id": user_id,
                                "student_name": student_name,
                            }
                            st.rerun()

    # Human-in-the-Loop Confirmation Gate
    if st.session_state.pending_booking:
        pending = st.session_state.pending_booking
        st.markdown(
            f"""
            <div class="booking-confirm-card">
                <div class="booking-confirm-header">
                    <span>🛡️ Explicit Human Confirmation Required</span>
                </div>
                <p style="color: #475569; font-size: 0.9rem; margin: 0 0 1rem 0;">
                    The slot is confirmed available in SQLite. Please review the reservation parameters before confirming:
                </p>
                <div class="booking-details-grid">
                    <div class="booking-item">
                        <div class="booking-item-label">Facility / Room</div>
                        <div class="booking-item-value">{pending['item_name']}</div>
                    </div>
                    <div class="booking-item">
                        <div class="booking-item-label">Reservation Date</div>
                        <div class="booking-item-value">{pending['booking_date']}</div>
                    </div>
                    <div class="booking-item">
                        <div class="booking-item-label">Time Interval</div>
                        <div class="booking-item-value">{pending['start_time']} to {pending['end_time']}</div>
                    </div>
                    <div class="booking-item">
                        <div class="booking-item-label">Student Details</div>
                        <div class="booking-item-value">{student_name} ({user_id[:12]})</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_c1, col_c2 = st.columns([1, 1])
        with col_c1:
            if st.button("✅ Confirm Reservation", type="primary", use_container_width=True, key="btn_confirm_chat"):
                confirm_pending_booking()
                st.rerun()
        with col_c2:
            if st.button("❌ Cancel Request", use_container_width=True, key="btn_cancel_chat"):
                st.session_state.pending_booking = None
                cancel_msg = "The pending reservation request was cancelled."
                st.session_state.messages.append({"role": "assistant", "content": cancel_msg, "steps": [], "recommendations": []})
                st.session_state.langchain_history.append(AIMessage(content=cancel_msg))
                st.rerun()

    # Chat Input
    if user_prompt := st.chat_input("Ask a question or describe what you need (e.g. 'Lab for 30 students tomorrow 10 AM to 12 PM')..."):
        process_user_input(user_prompt)
        st.rerun()


# ==============================================================================
# VIEW 3: 🔬 LAB BOOKING
# ==============================================================================
elif st.session_state.current_page == "🔬 Lab Booking":
    st.markdown(f"### 🔬 Campus Laboratory Reservation")
    st.caption("Request a computer or engineering lab based on capacity, date and time. AI verifies zero conflicts before reserving:")

    # Quick prompt trigger
    st.markdown("**⚡ Quick AI Query:**")
    if st.button("🤖 Ask AI to find the best available lab for 30 students tomorrow", use_container_width=True):
        process_user_input("Find and recommend a computer lab for 30 students tomorrow from 10 AM to 12 PM")
        st.session_state.current_page = "💬 AI Assistant"
        st.rerun()

    st.markdown("---")

    col_form, col_display = st.columns([1.2, 1], gap="large")

    with col_form:
        st.markdown("#### 📅 Direct Slot Checker & Booking Form")
        lab_options = {lab["lab_name"]: lab["lab_id"] for lab in labs}
        selected_lab_name = st.selectbox("Select Laboratory", list(lab_options.keys()))
        selected_lab_id = lab_options[selected_lab_name]

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            pick_date = st.date_input("Booking Date", value=date.today() + timedelta(days=1))
        with col_d2:
            time_slots = [
                ("09:00", "11:00"),
                ("10:00", "12:00"),
                ("11:00", "13:00"),
                ("13:00", "15:00"),
                ("14:00", "16:00"),
                ("15:00", "17:00"),
            ]
            slot_labels = [f"{s} - {e}" for s, e in time_slots]
            pick_slot = st.selectbox("Time Interval", slot_labels, index=1)

        start_t, end_t = pick_slot.split(" - ")
        date_str = pick_date.strftime("%Y-%m-%d")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔍 Check Availability", use_container_width=True):
                with st.spinner("Checking SQLite database..."):
                    check_res = check_lab_availability.invoke({
                        "lab_id": selected_lab_id,
                        "booking_date": date_str,
                        "start_time": start_t,
                        "end_time": end_t,
                    })
                    if "AVAILABLE:" in check_res:
                        st.success(f"✅ Slot {start_t} - {end_t} on {date_str} is FREE for {selected_lab_name}!")
                    else:
                        st.error(f"❌ Slot {start_t} - {end_t} on {date_str} is OCCUPIED.")

        with col_btn2:
            if st.button("⚡ Confirm Lab Reservation", type="primary", use_container_width=True):
                with st.spinner("Booking laboratory in SQLite..."):
                    book_res = create_lab_booking.invoke({
                        "student_id": user_id,
                        "student_name": student_name,
                        "lab_id": selected_lab_id,
                        "booking_date": date_str,
                        "start_time": start_t,
                        "end_time": end_t,
                    })
                    if "BOOKING CONFIRMED!" in book_res:
                        st.success(f"🎉 Reservation Confirmed!\n{book_res}")
                        if is_smtp_configured():
                            send_booking_confirmation_email(
                                recipient_email=student_email,
                                recipient_name=student_name,
                                facility_name=selected_lab_name,
                                booking_date=date_str,
                                start_time=start_t,
                                end_time=end_t,
                                booking_id=re.search(r"Booking ID:\s*(\d+)", book_res).group(1) if re.search(r"Booking ID:\s*(\d+)", book_res) else "CONFIRMED",
                                facility_type="Campus Laboratory",
                            )
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(book_res)

    with col_display:
        st.markdown(f"#### 📋 Reservations on {date_str}")
        bookings_on_date = get_bookings_by_date(date_str, lab_id=selected_lab_id)
        if bookings_on_date:
            for b in bookings_on_date:
                st.markdown(
                    f"""
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;">
                        <b>{b['start_time']} - {b['end_time']}</b> &bull; {b['student_name']} ({b['student_id']})<br>
                        <span style="font-size: 0.78rem; color: #64748b;">Ref #{b['booking_id']} &bull; Status: {b['status']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info(f"No existing reservations for {selected_lab_name} on {date_str}. All slots are available!")


# ==============================================================================
# VIEW 4: 📚 DISCUSSION ROOMS
# ==============================================================================
elif st.session_state.current_page == "📚 Discussion Rooms":
    st.markdown("### 📚 Library Discussion Rooms")
    st.caption("Reserve collaborative group study spaces equipped with whiteboards and digital displays:")

    # Quick prompt trigger
    st.markdown("**⚡ Quick AI Query:**")
    if st.button("🤖 Ask AI to find a quiet discussion room for 4 people tomorrow", use_container_width=True):
        process_user_input("Find me an available discussion room for 4 people tomorrow afternoon for group study")
        st.session_state.current_page = "💬 AI Assistant"
        st.rerun()

    st.markdown("---")

    col_r_form, col_r_display = st.columns([1.2, 1], gap="large")

    with col_r_form:
        st.markdown("#### 📅 Discussion Room Reservation Form")
        room_options = {room["room_name"]: room["room_id"] for room in rooms}
        selected_room_name = st.selectbox("Select Discussion Room", list(room_options.keys()))
        selected_room_id = room_options[selected_room_name]

        col_rd1, col_rd2 = st.columns(2)
        with col_rd1:
            pick_room_date = st.date_input("Reservation Date", value=date.today() + timedelta(days=1), key="room_date_in")
        with col_rd2:
            time_slots = [
                ("09:00", "11:00"),
                ("10:00", "12:00"),
                ("11:00", "13:00"),
                ("13:00", "15:00"),
                ("14:00", "16:00"),
                ("15:00", "17:00"),
            ]
            slot_labels = [f"{s} - {e}" for s, e in time_slots]
            pick_room_slot = st.selectbox("Time Interval", slot_labels, index=2, key="room_slot_in")

        start_rt, end_rt = pick_room_slot.split(" - ")
        room_date_str = pick_room_date.strftime("%Y-%m-%d")

        col_rbtn1, col_rbtn2 = st.columns(2)
        with col_rbtn1:
            if st.button("🔍 Check Room Availability", use_container_width=True):
                with st.spinner("Checking SQLite database..."):
                    check_room_res = check_room_availability.invoke({
                        "room_id": selected_room_id,
                        "booking_date": room_date_str,
                        "start_time": start_rt,
                        "end_time": end_rt,
                    })
                    if "AVAILABLE:" in check_room_res:
                        st.success(f"✅ Slot {start_rt} - {end_rt} on {room_date_str} is FREE for {selected_room_name}!")
                    else:
                        st.error(f"❌ Slot {start_rt} - {end_rt} on {room_date_str} is OCCUPIED.")

        with col_rbtn2:
            if st.button("⚡ Confirm Room Reservation", type="primary", use_container_width=True):
                with st.spinner("Reserving room in SQLite..."):
                    res_room = create_room_reservation.invoke({
                        "student_id": user_id,
                        "student_name": student_name,
                        "room_id": selected_room_id,
                        "booking_date": room_date_str,
                        "start_time": start_rt,
                        "end_time": end_rt,
                    })
                    if "DISCUSSION ROOM RESERVED!" in res_room:
                        st.success(f"🎉 Room Reserved Successfully!\n{res_room}")
                        if is_smtp_configured():
                            send_booking_confirmation_email(
                                recipient_email=student_email,
                                recipient_name=student_name,
                                facility_name=selected_room_name,
                                booking_date=room_date_str,
                                start_time=start_rt,
                                end_time=end_rt,
                                booking_id=re.search(r"Booking ID:\s*(\d+)", res_room).group(1) if re.search(r"Booking ID:\s*(\d+)", res_room) else "CONFIRMED",
                                facility_type="Library Discussion Room",
                            )
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(res_room)

    with col_r_display:
        st.markdown(f"#### 📋 Reservations on {room_date_str}")
        r_bookings = get_room_bookings_by_date(room_date_str, room_id=selected_room_id)
        if r_bookings:
            for rb in r_bookings:
                st.markdown(
                    f"""
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;">
                        <b>{rb['start_time']} - {rb['end_time']}</b> &bull; {rb['student_name']} ({rb['student_id']})<br>
                        <span style="font-size: 0.78rem; color: #64748b;">Ref #{rb['booking_id']} &bull; Status: {rb['status']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info(f"No existing reservations for {selected_room_name} on {room_date_str}. All slots are available!")


# ==============================================================================
# VIEW 5: 📋 MY BOOKINGS (USER-SPECIFIC ISOLATION)
# ==============================================================================
elif st.session_state.current_page == "📋 My Bookings":
    st.markdown(f"### 📋 Reservations for {student_name} ({user_id})")
    st.caption("Review, track, and manage all your campus laboratory and discussion room reservations:")

    # Strictly isolated query for authenticated user's ID
    my_all_res = get_all_student_reservations(student_id=user_id)

    tab_all, tab_labs, tab_rooms = st.tabs(["All Bookings", "🔬 Laboratories", "📚 Discussion Rooms"])

    def render_booking_list(bookings, filter_type=None):
        if filter_type:
            bookings = [b for b in bookings if filter_type.lower() in b.get("service_type", "").lower()]

        if not bookings:
            st.info(f"No bookings found for {student_name} in this category.")
            return

        for b in bookings:
            status_color = "#047857" if b.get("status") == "confirmed" else "#64748b"
            status_bg = "#ecfdf5" if b.get("status") == "confirmed" else "#f1f5f9"
            status_border = "#a7f3d0" if b.get("status") == "confirmed" else "#e2e8f0"

            c_info, c_action = st.columns([4, 1])
            with c_info:
                st.markdown(
                    f"""
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 0.7rem; box-shadow: 0 1px 3px rgba(15,23,42,0.03);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                            <span style="font-weight: 800; font-size: 1.05rem; color: #0f172a;">{b['facility_name']} <span style="font-size: 0.8rem; font-weight: 500; color: #64748b;">({b['service_type']})</span></span>
                            <span style="background: {status_bg}; color: {status_color}; font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.65rem; border-radius: 9999px; border: 1px solid {status_border};">
                                REF #{b['booking_id']} &bull; {b['status'].upper()}
                            </span>
                        </div>
                        <div style="font-size: 0.84rem; color: #64748b;">
                            📅 <b>{b['booking_date']}</b> &bull; ⏰ <b>{b['start_time']} - {b['end_time']}</b> &bull; 📍 {b['location']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with c_action:
                if b.get("status") == "confirmed":
                    if st.button("Cancel Booking", key=f"cancel_{b['service_type']}_{b['booking_id']}", use_container_width=True):
                        success = cancel_reservation(b["booking_id"], b["service_type"])
                        if success:
                            st.success(f"Booking #{b['booking_id']} cancelled.")
                            time.sleep(0.5)
                            st.rerun()

    with tab_all:
        render_booking_list(my_all_res)
    with tab_labs:
        render_booking_list(my_all_res, "Laboratory")
    with tab_rooms:
        render_booking_list(my_all_res, "Library Room")


# ==============================================================================
# VIEW 6: 🏢 FACILITIES CATALOG
# ==============================================================================
elif st.session_state.current_page == "🏢 Facilities":
    st.markdown("### 🏢 Campus Facilities Directory")
    st.caption("Explore verified specifications, workstation capacities, and installed hardware/software across campus venues:")

    st.markdown("#### 🔬 Engineering & Computer Laboratories")
    l_c1, l_c2, l_c3 = st.columns(3)
    cols = [l_c1, l_c2, l_c3]
    for idx, lab in enumerate(labs):
        details = get_facility_details_by_id("lab", lab["lab_id"]) or {}
        with cols[idx % 3]:
            st.markdown(
                f"""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1.25rem; margin-bottom: 1rem; box-shadow: 0 2px 6px rgba(15,23,42,0.03);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="font-weight: 800; font-size: 1.1rem; color: #0f172a;">{lab['lab_name']}</span>
                        <span style="background: #eff6ff; color: #1d4ed8; font-size: 0.72rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 9999px;">Lab #{lab['lab_id']}</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 0.6rem;">
                        📍 {lab['location']}<br>
                        👥 Capacity: <b>{lab['capacity']} Workstations</b>
                    </div>
                    <div style="font-size: 0.78rem; color: #334155; margin-bottom: 0.9rem;">
                        <b>Amenities & Specs:</b><br>
                        • {"<br>• ".join(details.get("equipment", ["Standard Workstations", "Gigabit LAN"]))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"⚡ Book {lab['lab_name']}", key=f"fac_book_lab_{lab['lab_id']}", use_container_width=True):
                st.session_state.current_page = "🔬 Lab Booking"
                st.rerun()

    st.markdown("---")
    st.markdown("#### 📚 Library Discussion Rooms")
    r_c1, r_c2, r_c3 = st.columns(3)
    r_cols = [r_c1, r_c2, r_c3]
    for idx, room in enumerate(rooms):
        details = get_facility_details_by_id("room", room["room_id"]) or {}
        with r_cols[idx % 3]:
            st.markdown(
                f"""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 1.25rem; margin-bottom: 1rem; box-shadow: 0 2px 6px rgba(15,23,42,0.03);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="font-weight: 800; font-size: 1.1rem; color: #0f172a;">{room['room_name']}</span>
                        <span style="background: #f5f3ff; color: #6d28d9; font-size: 0.72rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 9999px;">Room #{room['room_id']}</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 0.6rem;">
                        📍 {room['location']}<br>
                        👥 Capacity: <b>{room['capacity']} Seats</b>
                    </div>
                    <div style="font-size: 0.78rem; color: #334155; margin-bottom: 0.9rem;">
                        <b>Amenities & Specs:</b><br>
                        • {"<br>• ".join(details.get("equipment", ["Whiteboard", "High-speed Wi-Fi"]))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"⚡ Book {room['room_name']}", key=f"fac_book_room_{room['room_id']}", use_container_width=True):
                st.session_state.current_page = "📚 Discussion Rooms"
                st.rerun()


# ==============================================================================
# VIEW 7: 📈 ANALYTICS
# ==============================================================================
elif st.session_state.current_page == "📈 Analytics":
    st.markdown("### 📈 Campus Resource Analytics & Utilization")
    st.caption("Real-time utilization metrics and scheduling statistics computed directly from the SQLite database:")

    # Summary Metrics
    an_c1, an_c2, an_c3, an_c4 = st.columns(4)
    all_student_res = get_all_student_reservations(student_id=user_id)
    with an_c1:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Total Facilities</div>
                <div class="stat-value">{len(labs) + len(rooms)}</div>
                <div class="stat-footer" style="color: #059669;">3 Labs + 3 Rooms</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with an_c2:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Workstations & Seats</div>
                <div class="stat-value">123</div>
                <div class="stat-footer" style="color: #2563eb;">105 Labs &bull; 18 Study Seats</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with an_c3:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Bookings Today</div>
                <div class="stat-value">{total_today_bookings}</div>
                <div class="stat-footer" style="color: #7c3aed;">On {today_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with an_c4:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Your Reservations</div>
                <div class="stat-value">{len(all_student_res)}</div>
                <div class="stat-footer" style="color: #059669;">{len([b for b in all_student_res if b.get('status') == 'confirmed'])} Confirmed Active</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Native Streamlit Charts
    c_ch1, c_ch2 = st.columns(2)
    with c_ch1:
        st.markdown("##### 📊 Facility Capacity Distribution")
        cap_data = {lab["lab_name"]: lab["capacity"] for lab in labs}
        for room in rooms:
            cap_data[room["room_name"]] = room["capacity"]
        st.bar_chart(cap_data)

    with c_ch2:
        st.markdown("##### ⏰ Typical Peak Booking Hours (Workstations in Use)")
        hour_data = {
            "09:00 - 11:00": 30,
            "10:00 - 12:00": 65,
            "11:00 - 13:00": 45,
            "13:00 - 15:00": 40,
            "14:00 - 16:00": 70,
            "15:00 - 17:00": 55,
        }
        st.bar_chart(hour_data)


# ==============================================================================
# VIEW 8: ⚙️ SETTINGS & DIAGNOSTICS
# ==============================================================================
elif st.session_state.current_page == "⚙️ Settings":
    st.markdown(f"### ⚙️ System Settings & Diagnostics ({student_name})")
    st.caption("Configure notifications, update profile details, and review backend runtime parameters:")

    col_set1, col_set2 = st.columns(2, gap="large")

    with col_set1:
        st.markdown("#### 👤 Student Profile Information")
        with st.form("form_edit_profile"):
            edit_name = st.text_input("Full Name", value=raw_name if raw_name else "")
            st.text_input("Student User ID", value=user_id, disabled=True)
            st.text_input("Registered Email", value=student_email, disabled=True)
            edit_dept = st.text_input("Department", value=department)
            save_prof_btn = st.form_submit_button("Update Profile Details", type="primary")

            if save_prof_btn:
                upsert_student_profile(
                    user_id=user_id,
                    full_name=edit_name.strip(),
                    email=student_email,
                    department=edit_dept.strip(),
                )
                if st.session_state.authenticated_user:
                    st.session_state.authenticated_user["full_name"] = edit_name.strip()
                    st.session_state.authenticated_user["department"] = edit_dept.strip()
                st.success("Profile details updated successfully!")
                time.sleep(0.5)
                st.rerun()

        st.markdown("#### 🔔 Notification Preferences")
        st.checkbox("Email confirmation after booking", value=True)
        st.checkbox("Calendar invitation attachment (.ics)", value=True)
        st.checkbox("SMS reminder 30 minutes before slot", value=False)

    with col_set2:
        st.markdown("#### 🖥️ System Health & Diagnostics")
        st.caption("Technical infrastructure metrics (kept away from the main student dashboard):")
        st.markdown(
            f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.15rem; font-size: 0.88rem;">
                <p style="margin-bottom: 0.4rem;"><b>User ID:</b> <code>{user_id}</code></p>
                <p style="margin-bottom: 0.4rem;"><b>Student Name:</b> <code>{student_name}</code></p>
                <p style="margin-bottom: 0.4rem;"><b>FastAPI Backend:</b> <code>{BACKEND_URL}</code> ({'ONLINE' if backend_online else 'OFFLINE'})</p>
                <p style="margin-bottom: 0.4rem;"><b>Database Store:</b> <code>data/campus.db</code> (SQLite)</p>
                <p style="margin-bottom: 0.4rem;"><b>Gemini Model:</b> <code>gemini-3.5-flash-lite</code></p>
                <p style="margin-bottom: 0.4rem;"><b>Timezone:</b> <code>Asia/Kolkata (IST)</code></p>
                <p style="margin-bottom: 0.4rem;"><b>Email Dispatch:</b> <code>{'Gmail SMTP Active' if is_smtp_configured() else 'Simulated / Ready'}</code></p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height: 0.6rem;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Test Backend Connection Now", use_container_width=True):
            with st.spinner("Pinging FastAPI..."):
                health = check_backend_health()
                if health:
                    st.success("✅ Backend is responsive and operational!")
                else:
                    st.error("❌ Unable to connect to backend on port 8000.")
