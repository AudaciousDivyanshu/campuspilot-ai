"""CampusPilot AI — Premium Campus Management Platform & Autonomous AI Assistant.

A university productivity platform for multi-step campus facility workflows:
- Visual Design System: Permanent Single White/Light Theme (#F8FAFC / #FFFFFF / #E50914) with soft shadows and crisp typography.
- Streamlined Authentication: Email/Password login, student registration with Student ID & Department.
  No demo shortcut buttons on the login page; authorized administrators sign in securely with their credentials.
- Role-Based Experience:
  * Student: Personalized Dashboard, AI Assistant, Lab Booking (pending admin approval), Discussion Rooms,
    My Bookings (tracking pending/approved/rejected with rejection reasons), and Leave Requests (auto-accepted).
  * Administrator: Administrative Dashboard, Booking Request Approvals/Rejections (with reasons),
    Facility Enable/Disable Management, and Campus Leave Oversight.
- Autonomous AI Assistant: Gemini-powered multi-step facility tool execution, conflict prevention,
  and human-in-the-loop confirmation gates.
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
    approve_booking,
    cancel_reservation,
    check_booking_overlap,
    check_room_booking_overlap,
    create_booking,
    create_leave_request,
    create_room_booking,
    get_admin_dashboard_metrics,
    get_all_booking_requests,
    get_all_discussion_rooms,
    get_all_laboratories,
    get_all_leave_requests,
    get_all_student_reservations,
    get_bookings_by_date,
    get_discussion_room_by_id,
    get_facility_details_by_id,
    get_laboratory_by_id,
    get_room_bookings_by_date,
    get_student_leave_requests,
    get_student_profile,
    get_student_profile_by_email,
    recommend_matching_facilities,
    reject_booking,
    toggle_facility_status,
    update_leave_status,
    upsert_student_profile,
)
from app.services.demo_auth import (
    authenticate_user,
    get_all_demo_users,
    get_user_by_email,
    is_password_valid,
    register_user,
    validate_password_strength,
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
# CONFIGURATION & STREAMLIT PAGE CONFIG
# ==============================================================================
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

st.set_page_config(
    page_title="CampusPilot AI — Smart Campus Operations",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Application Theme: Permanent Single White / Light Theme Only
st.session_state.theme = "light"

if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None

if "current_page" not in st.session_state:
    st.session_state.current_page = None  # Will default dynamically based on role

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
                "• **Securely submit your reservation request** with instant tracking `#ID`.\n\n"
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
# HTML STRING SANITIZER (ELIMINATES 4-SPACE MARKDOWN CODE-BLOCK BUG)
# ==============================================================================
def clean_html(html_str: str) -> str:
    """Strip all leading and trailing whitespace from each line so Markdown never renders code blocks."""
    return "\n".join(line.strip() for line in html_str.strip().splitlines())


# ==============================================================================
# PERMANENT SINGLE WHITE / LIGHT THEME STYLING SYSTEM
# ==============================================================================
def inject_theme_css():
    bg_color = "#F8FAFC"
    card_bg = "#FFFFFF"
    secondary_card_bg = "#F8FAFC"
    input_bg = "#FFFFFF"
    text_primary = "#0F172A"
    text_secondary = "#64748B"
    border_color = "#E2E8F0"
    hover_bg = "#F1F5F9"
    placeholder_color = "#94A3B8"

    # Refined Crimson Accent
    accent_crimson = "#E50914"
    accent_crimson_hover = "#DC2626"

    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    /* Global Typography & Background */
    html, body, [class*="css"], .stApp {{
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: {bg_color} !important;
        color: {text_primary} !important;
    }}

    /* Clean Streamlit Header Area */
    header[data-testid="stHeader"],
    [data-testid="stHeader"] {{
        background: transparent !important;
        background-color: transparent !important;
        height: 1.8rem !important;
    }}
    .stDeployButton,
    [data-testid="stToolbarActions"],
    [data-testid="stDecoration"],
    #MainMenu,
    footer {{
        display: none !important;
        visibility: hidden !important;
    }}

    /* Main Container Padding & Width */
    .block-container {{
        padding-top: 1rem !important;
        padding-bottom: 2.5rem !important;
        max-width: 1240px !important;
        margin: 0 auto !important;
    }}

    /* Polished White Sidebar */
    section[data-testid="stSidebar"] {{
        background: #FFFFFF !important;
        border-right: 1px solid {border_color} !important;
    }}
    section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {{
        color: {text_primary} !important;
    }}

    /* Top Brand Navbar */
    .top-navbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.75rem 1.25rem;
        background: {card_bg};
        border: 1px solid {border_color};
        border-radius: 14px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 1.1rem;
    }}

    .brand-title {{
        font-size: 1.25rem;
        font-weight: 800;
        color: {text_primary};
        margin: 0;
        letter-spacing: -0.02em;
    }}

    .brand-tagline {{
        font-size: 0.82rem;
        color: {text_secondary};
        font-weight: 500;
        border-left: 1px solid {border_color};
        padding-left: 0.65rem;
        margin-left: 0.4rem;
    }}

    /* Badges & Status Indicators */
    .badge-live {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: rgba(16, 185, 129, 0.1);
        color: #059669;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .badge-offline {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: rgba(229, 9, 20, 0.1);
        color: #DC2626;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid rgba(229, 9, 20, 0.3);
    }}

    .badge-pending {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: rgba(245, 158, 11, 0.12);
        color: #D97706;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .badge-rejected {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: rgba(229, 9, 20, 0.1);
        color: #DC2626;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid rgba(229, 9, 20, 0.3);
    }}

    .badge-profile-chip {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #F1F5F9;
        color: {text_primary};
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 600;
        border: 1px solid {border_color};
    }}

    /* Hero Banner */
    .hero-banner {{
        background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
        border: 1px solid {border_color};
        border-left: 4px solid {accent_crimson};
        border-radius: 14px;
        padding: 1.35rem 1.6rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        margin-bottom: 1.15rem;
    }}

    .hero-title {{
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0 0 0.35rem 0;
        color: {text_primary};
    }}

    .hero-subtitle {{
        font-size: 0.88rem;
        color: {text_secondary};
        margin: 0;
        line-height: 1.55;
        font-weight: 400;
    }}

    /* Stat Cards */
    .stat-card {{
        background: {card_bg};
        border: 1px solid {border_color};
        border-radius: 14px;
        padding: 1rem 1.15rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 1rem;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }}

    .stat-card:hover {{
        transform: translateY(-2px);
        border-color: {accent_crimson};
        box-shadow: 0 4px 12px rgba(229, 9, 20, 0.08);
    }}

    .stat-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.3rem;
    }}

    .stat-label {{
        font-size: 0.72rem;
        color: {text_secondary};
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}

    .stat-icon {{
        font-size: 1.2rem;
    }}

    .stat-value {{
        font-size: 1.65rem;
        font-weight: 800;
        color: {text_primary};
        margin: 0.1rem 0;
        letter-spacing: -0.02em;
    }}

    .stat-footer {{
        font-size: 0.74rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }}

    /* Content Cards */
    .content-card {{
        background: {card_bg};
        border: 1px solid {border_color};
        border-radius: 14px;
        padding: 1.35rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 1rem;
    }}

    .card-header-title {{
        font-size: 1.05rem;
        font-weight: 800;
        color: {text_primary};
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.3rem;
        letter-spacing: -0.01em;
    }}

    .card-header-sub {{
        font-size: 0.82rem;
        color: {text_secondary};
        margin-bottom: 0.9rem;
    }}

    /* Recommendation Card */
    .rec-card {{
        background: {card_bg};
        border: 1.5px solid {border_color};
        border-radius: 12px;
        padding: 1.1rem;
        margin-bottom: 0.8rem;
        transition: all 0.2s ease;
    }}

    .rec-card:hover {{
        border-color: {accent_crimson};
        box-shadow: 0 4px 12px rgba(229, 9, 20, 0.08);
    }}

    .rec-badge-best {{
        background: rgba(229, 9, 20, 0.1);
        color: #DC2626;
        border: 1px solid rgba(229, 9, 20, 0.3);
        font-size: 0.72rem;
        font-weight: 800;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
    }}

    .rec-badge-alt {{
        background: {secondary_card_bg};
        color: {text_primary};
        border: 1px solid {border_color};
        font-size: 0.72rem;
        font-weight: 700;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
    }}

    /* Booking Confirmation Alert Card */
    .booking-confirm-card {{
        background: #FFF5F5;
        border: 2px solid {accent_crimson};
        border-radius: 14px;
        padding: 1.25rem;
        margin: 1rem 0;
        box-shadow: 0 4px 14px rgba(229, 9, 20, 0.12);
    }}

    .booking-confirm-header {{
        font-size: 1.05rem;
        font-weight: 800;
        color: #DC2626;
        margin-bottom: 0.4rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}

    .booking-details-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 0.65rem;
        margin-top: 0.8rem;
        margin-bottom: 1rem;
    }}

    .booking-item {{
        background: {input_bg};
        border: 1px solid {border_color};
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
    }}

    .booking-item-label {{
        font-size: 0.65rem;
        color: {accent_crimson};
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.04em;
    }}

    .booking-item-value {{
        font-size: 0.88rem;
        font-weight: 800;
        color: {text_primary};
        margin-top: 0.1rem;
    }}

    /* Upcoming Booking Row Item */
    .booking-row {{
        background: {card_bg};
        border: 1px solid {border_color};
        border-radius: 10px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.65rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    }}

    /* Rejection reason callout box */
    .rejection-box {{
        background: rgba(229, 9, 20, 0.05);
        border: 1px solid rgba(229, 9, 20, 0.25);
        border-left: 3px solid {accent_crimson};
        border-radius: 8px;
        padding: 0.6rem 0.85rem;
        margin-top: 0.5rem;
        font-size: 0.8rem;
        color: #B91C1C;
    }}

    /* Empty state */
    .empty-state-box {{
        background: {card_bg};
        border: 1.5px dashed {border_color};
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        color: {text_secondary};
    }}

    /* Streamlit Tabs (High Contrast White Mode) */
    button[data-testid="stTab"] {{
        color: {text_secondary} !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
        padding: 0.65rem 1.4rem !important;
        border-bottom: 2px solid transparent !important;
        background: transparent !important;
        transition: all 0.2s ease !important;
    }}
    button[data-testid="stTab"]:hover {{
        color: {text_primary} !important;
    }}
    button[data-testid="stTab"][aria-selected="true"] {{
        color: {accent_crimson} !important;
        border-bottom: 2.5px solid {accent_crimson} !important;
        font-weight: 800 !important;
    }}

    /* Clean Streamlit Buttons */
    div.stButton > button,
    button[data-testid="baseButton-secondary"] {{
        background-color: {card_bg} !important;
        color: {text_primary} !important;
        border: 1.5px solid {border_color} !important;
        border-radius: 10px !important;
        padding: 0.55rem 1rem !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05) !important;
    }}
    div.stButton > button:hover,
    button[data-testid="baseButton-secondary"]:hover {{
        background-color: {hover_bg} !important;
        color: {accent_crimson} !important;
        border-color: {accent_crimson} !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(229, 9, 20, 0.12) !important;
    }}

    /* Primary Submit Button (Crimson Gradient #E50914) */
    div.stButton > button[kind="primary"],
    button[data-testid="baseButton-primary"] {{
        background: linear-gradient(135deg, {accent_crimson} 0%, #C62828 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.65rem 1.25rem !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
        box-shadow: 0 4px 14px rgba(229, 9, 20, 0.3) !important;
        transition: all 0.2s ease !important;
    }}
    div.stButton > button[kind="primary"]:hover,
    button[data-testid="baseButton-primary"]:hover {{
        background: linear-gradient(135deg, {accent_crimson_hover} 0%, {accent_crimson} 100%) !important;
        color: #FFFFFF !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 18px rgba(229, 9, 20, 0.45) !important;
    }}

    /* Form Labels & Text Inputs */
    div[data-testid="stTextInput"] label p,
    div[data-testid="stSelectbox"] label p,
    div[data-testid="stRadio"] label p,
    div[data-testid="stDateInput"] label p,
    div[data-testid="stTextArea"] label p,
    div[data-testid="stCheckbox"] label p {{
        color: {text_primary} !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
    }}
    div[data-testid="stCheckbox"] span {{
        color: {text_secondary} !important;
        font-size: 0.84rem !important;
    }}

    div[data-baseweb="input"] {{
        background-color: {input_bg} !important;
        border: 1.5px solid {border_color} !important;
        border-radius: 10px !important;
    }}
    div[data-baseweb="input"]:focus-within {{
        border-color: {accent_crimson} !important;
        box-shadow: 0 0 0 2px rgba(229, 9, 20, 0.15) !important;
    }}
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {{
        color: {text_primary} !important;
        background-color: transparent !important;
        font-size: 0.9rem !important;
    }}
    div[data-baseweb="textarea"] {{
        background-color: {input_bg} !important;
        border: 1.5px solid {border_color} !important;
        border-radius: 10px !important;
    }}
    div[data-baseweb="input"] input::placeholder,
    div[data-baseweb="textarea"] textarea::placeholder {{
        color: {placeholder_color} !important;
    }}

    /* Selectbox */
    div[data-baseweb="select"] {{
        background-color: {input_bg} !important;
        border-radius: 10px !important;
    }}
    div[data-baseweb="select"] > div {{
        background-color: {input_bg} !important;
        border: 1.5px solid {border_color} !important;
        border-radius: 10px !important;
        color: {text_primary} !important;
    }}
    </style>
    """
    st.markdown(clean_html(css), unsafe_allow_html=True)


inject_theme_css()

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


# ==============================================================================
# SAAS TWO-COLUMN AUTHENTICATION EXPERIENCE (SINGLE WHITE THEME)
# ==============================================================================
if st.session_state.authenticated_user is None:
    # Main Two-Column Layout
    col_left_brand, col_right_auth = st.columns([1.05, 1.25], gap="large")

    # --------------------------------------------------------------------------
    # LEFT PANEL: BRANDING & PLATFORM CAPABILITIES
    # --------------------------------------------------------------------------
    with col_left_brand:
        # Top Badges
        st.markdown(
            clean_html(f"""
            <div style="display: flex; gap: 0.6rem; align-items: center; margin-bottom: 1.1rem; flex-wrap: wrap;">
                <span style="background: rgba(229, 9, 20, 0.08); color: #DC2626; border: 1px solid rgba(229, 9, 20, 0.25); font-size: 0.72rem; font-weight: 700; padding: 0.25rem 0.75rem; border-radius: 9999px; letter-spacing: 0.03em;">● Academic Operations 2026</span>
                <span style="color: #64748B; font-size: 0.75rem; font-weight: 600;">v2.5 Production</span>
            </div>
            """),
            unsafe_allow_html=True,
        )

        # CampusPilot AI Logo & Title
        st.markdown(
            clean_html(f"""
            <div style="margin-bottom: 1.2rem;">
                <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
                    <span style="font-size: 2.2rem; line-height: 1;">🎓</span>
                    <span style="font-size: 1.85rem; font-weight: 800; color: #0F172A; letter-spacing: -0.02em;">CampusPilot AI</span>
                </div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #E50914; margin-bottom: 0.5rem; letter-spacing: -0.01em;">
                    Smart Campus Facility & Operations Platform
                </div>
                <p style="font-size: 0.88rem; color: #475569; line-height: 1.55; margin: 0;">
                    CampusPilot AI connects students and faculty administrators with real-time availability across university computer laboratories, specialized engineering suites, and collaborative study rooms.
                </p>
            </div>
            """),
            unsafe_allow_html=True,
        )

        # Key Features Box
        st.markdown(
            clean_html(f"""
            <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px; padding: 1.15rem; margin-bottom: 1rem; box-shadow: 0 2px 8px rgba(15,23,42,0.04);">
                <div style="font-size: 0.75rem; font-weight: 800; color: #E50914; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.85rem;">
                    Core Platform Capabilities
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.85rem;">
                    <div style="display: flex; gap: 0.75rem; align-items: flex-start;">
                        <span style="background: rgba(229, 9, 20, 0.08); color: #E50914; border-radius: 8px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;">⚡</span>
                        <div>
                            <div style="font-size: 0.86rem; font-weight: 700; color: #0F172A;">Real-time Lab & Room Availability</div>
                            <div style="font-size: 0.78rem; color: #64748B; line-height: 1.4;">Live workstation counts and automated schedule conflict checking across all campus zones.</div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.75rem; align-items: flex-start;">
                        <span style="background: rgba(16,185,129,0.1); color: #059669; border-radius: 8px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;">📅</span>
                        <div>
                            <div style="font-size: 0.86rem; font-weight: 700; color: #0F172A;">Smart Booking Management</div>
                            <div style="font-size: 0.78rem; color: #64748B; line-height: 1.4;">Zero double-booking guarantee with automated slot verification and instant confirmation ID receipts.</div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.75rem; align-items: flex-start;">
                        <span style="background: rgba(229, 9, 20, 0.08); color: #DC2626; border-radius: 8px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;">🤖</span>
                        <div>
                            <div style="font-size: 0.86rem; font-weight: 700; color: #0F172A;">Gemini AI Campus Assistant</div>
                            <div style="font-size: 0.78rem; color: #64748B; line-height: 1.4;">Autonomous natural language request parsing for equipment specs, capacity, and smart recommendations.</div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.75rem; align-items: flex-start;">
                        <span style="background: rgba(245,158,11,0.1); color: #D97706; border-radius: 8px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;">🛡️</span>
                        <div>
                            <div style="font-size: 0.86rem; font-weight: 700; color: #0F172A;">Role-Based Access Control</div>
                            <div style="font-size: 0.78rem; color: #64748B; line-height: 1.4;">Dedicated Student workflows and Faculty/Administrator approval & facility override panels.</div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.75rem; align-items: flex-start;">
                        <span style="background: rgba(16,185,129,0.1); color: #059669; border-radius: 8px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;">🏖️</span>
                        <div>
                            <div style="font-size: 0.86rem; font-weight: 700; color: #0F172A;">Automated Student Leave Policy</div>
                            <div style="font-size: 0.78rem; color: #64748B; line-height: 1.4;">Instant rule-based auto-acceptance for academic & medical leaves with full admin oversight.</div>
                        </div>
                    </div>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

        # Subtle Bottom Endorsement Card
        st.markdown(
            clean_html(f"""
            <div style="background: #F1F5F9; border: 1px dashed #CBD5E1; border-radius: 12px; padding: 0.85rem 1rem;">
                <div style="font-size: 0.78rem; color: #64748B; display: flex; align-items: center; gap: 0.5rem; line-height: 1.45;">
                    <span style="font-size: 1.05rem;">✨</span>
                    <span>Trusted by university academic departments, computing laboratories, and student study centers across campus.</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------------------------
    # RIGHT PANEL: AUTHENTICATION CARD WITH DISTINCT TABS
    # --------------------------------------------------------------------------
    with col_right_auth:
        tab_signin, tab_create = st.tabs(["🔐 Sign In", "📝 Create Account"])

        # ======================================================================
        # TAB 1: SIGN IN (SECURE PORTAL SELECTOR: STUDENT & ADMINISTRATOR)
        # ======================================================================
        with tab_signin:
            # Segmented portal selector
            portal_mode = st.radio(
                "Access Mode",
                ["👨‍🎓 Student Portal", "🛡️ Administrator Portal"],
                horizontal=True,
                key="auth_portal_mode",
                label_visibility="collapsed",
            )

            if portal_mode == "👨‍🎓 Student Portal":
                st.markdown(
                    clean_html(f"""
                    <div style="margin-top: 0.35rem; margin-bottom: 0.9rem;">
                        <h2 style="font-size: 1.3rem; font-weight: 800; color: #0F172A; margin: 0 0 0.2rem 0;">
                            👨‍🎓 Student Sign In
                        </h2>
                        <p style="font-size: 0.84rem; color: #64748B; margin: 0;">
                            Sign in with your university student email to access lab bookings and AI tools:
                        </p>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )

                # Email Input
                login_email = st.text_input(
                    "University Student Email",
                    value="arnav@campus.edu",
                    placeholder="e.g. arnav@campus.edu or your.email@university.edu",
                    key="signin_student_email_input",
                )

                # Password Input with Toggle
                col_pwd_fld, col_pwd_chk = st.columns([3.4, 1.6])
                with col_pwd_chk:
                    show_pwd = st.checkbox("Show password", key="signin_student_show_pwd")
                with col_pwd_fld:
                    login_password = st.text_input(
                        "Student Password",
                        value="Password123",
                        type="default" if show_pwd else "password",
                        placeholder="Enter your student password",
                        key="signin_student_pwd_input",
                    )

                # Remember Me
                c_rem, c_hint = st.columns([1, 1.2])
                with c_rem:
                    st.checkbox("Remember me", value=True, key="signin_student_rem_me")
                with c_hint:
                    st.markdown(
                        clean_html(f"""
                        <div style="text-align: right; font-size: 0.78rem; color: #64748B; padding-top: 0.35rem;">
                            🔒 Student University Access
                        </div>
                        """),
                        unsafe_allow_html=True,
                    )

                # Full-Width Crimson Sign In Button
                btn_signin = st.button("⚡ Sign In to Student Portal", type="primary", use_container_width=True, key="btn_signin_student_submit")

                if btn_signin:
                    if not login_email.strip() or not login_password:
                        st.error("Please enter both university email and password.")
                    else:
                        with st.spinner("Authenticating student credentials..."):
                            success, res = authenticate_user(login_email, login_password)
                            if success:
                                st.session_state.authenticated_user = res
                                st.session_state.current_page = "📊 Student Dashboard"
                                st.success(f"Welcome, {res.get('display_name') or res.get('full_name')}!")
                                time.sleep(0.3)
                                st.rerun()
                            else:
                                st.error(res)

            else:
                # ------------------------------------------------------------------
                # ADMINISTRATOR PORTAL (SECURE FACULTY ACCESS)
                # ------------------------------------------------------------------
                st.markdown(
                    clean_html(f"""
                    <div style="margin-top: 0.35rem; margin-bottom: 0.9rem;">
                        <h2 style="font-size: 1.3rem; font-weight: 800; color: #0F172A; margin: 0 0 0.2rem 0;">
                            🛡️ Institutional Administrator Sign In
                        </h2>
                        <p style="font-size: 0.84rem; color: #64748B; margin: 0;">
                            Authorized faculty & campus administrators only. Institutional verification enforced:
                        </p>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )

                admin_default_email = os.getenv("ADMIN_EMAIL", "admin@campus.edu")
                admin_email = st.text_input(
                    "Administrator Email",
                    value=admin_default_email,
                    placeholder="e.g. admin@campus.edu or faculty@university.edu",
                    key="signin_admin_email_input",
                )

                col_pwd_fld, col_pwd_chk = st.columns([3.4, 1.6])
                with col_pwd_chk:
                    show_admin_pwd = st.checkbox("Show password", key="signin_admin_show_pwd")
                with col_pwd_fld:
                    admin_password = st.text_input(
                        "Administrator Password",
                        value="",
                        type="default" if show_admin_pwd else "password",
                        placeholder="Enter administrator password",
                        key="signin_admin_pwd_input",
                    )

                c_rem_adm, c_hint_adm = st.columns([1, 1.2])
                with c_rem_adm:
                    st.checkbox("Remember session", value=True, key="signin_admin_rem_me")
                with c_hint_adm:
                    st.markdown(
                        clean_html(f"""
                        <div style="text-align: right; font-size: 0.78rem; color: #64748B; padding-top: 0.35rem;">
                            🛡️ Institutional Administrator Access
                        </div>
                        """),
                        unsafe_allow_html=True,
                    )

                btn_admin_signin = st.button("🛡️ Sign In as Administrator", type="primary", use_container_width=True, key="btn_signin_admin_submit")

                if btn_admin_signin:
                    if not admin_email.strip() or not admin_password:
                        st.error("Please enter both administrator email and password.")
                    else:
                        with st.spinner("Verifying institutional administrator privileges..."):
                            try:
                                success, res = authenticate_user(admin_email, admin_password, required_role="Administrator")
                            except TypeError:
                                success, res = authenticate_user(admin_email, admin_password)
                                if success and res.get("account_type") != "Administrator":
                                    success = False
                                    res = "⛔ Access Denied: This account does not possess institutional administrator privileges."
                            if success:
                                if res.get("account_type") != "Administrator":
                                    st.error("⛔ Access Denied: This account does not possess institutional administrator privileges. Please sign in via the Student Portal.")
                                else:
                                    st.session_state.authenticated_user = res
                                    st.session_state.current_page = "🛡️ Admin Dashboard"
                                    st.success(f"Welcome, Administrator {res.get('display_name') or res.get('full_name')}!")
                                    time.sleep(0.3)
                                    st.rerun()
                            else:
                                st.error(res)

        # ======================================================================
        # TAB 2: CREATE ACCOUNT (STUDENT REGISTRATION ONLY)
        # ======================================================================
        with tab_create:
            st.markdown(
                clean_html(f"""
                <div style="margin-top: 0.35rem; margin-bottom: 1.1rem;">
                    <h2 style="font-size: 1.35rem; font-weight: 800; color: #0F172A; margin: 0 0 0.25rem 0;">
                        📝 Register Student Account
                    </h2>
                    <p style="font-size: 0.84rem; color: #64748B; margin: 0;">
                        Create your verified student profile to book labs, study rooms, and submit leave requests:
                    </p>
                </div>
                """),
                unsafe_allow_html=True,
            )

            # Full Name
            reg_fullname = st.text_input(
                "Full Legal Name *",
                placeholder="e.g. Divyanshu Verma",
                key="create_fullname_input",
            )

            # University Email
            reg_email = st.text_input(
                "University Email *",
                placeholder="e.g. divyanshu@campus.edu or student@lpu.in",
                key="create_email_input",
            )

            # Student ID / Roll Number & Department
            c_sid, c_dept = st.columns([1, 1.2])
            with c_sid:
                reg_student_id = st.text_input(
                    "Student ID / Roll No *",
                    placeholder="e.g. CS2026-088",
                    key="create_studentid_input",
                )
            with c_dept:
                reg_department = st.selectbox(
                    "Department *",
                    [
                        "Computer Science & Engineering",
                        "Artificial Intelligence & Data Science",
                        "Electronics & Communication",
                        "Information Technology",
                        "Mechanical Engineering",
                    ],
                    key="create_dept_input",
                )

            # Passwords Row
            c_pwd1, c_pwd2 = st.columns(2)
            with c_pwd1:
                reg_password = st.text_input(
                    "Password *",
                    type="default" if st.session_state.get("show_reg_pwd_check") else "password",
                    placeholder="Create secure password",
                    key="create_pwd_input",
                )
            with c_pwd2:
                reg_confirm_password = st.text_input(
                    "Confirm Password *",
                    type="default" if st.session_state.get("show_reg_pwd_check") else "password",
                    placeholder="Re-enter password",
                    key="create_pwd_confirm_input",
                )

            st.checkbox("Show passwords", key="show_reg_pwd_check")

            # Password Requirement Indicators
            p_len = len(reg_password) >= 8
            p_up = bool(re.search(r"[A-Z]", reg_password))
            p_low = bool(re.search(r"[a-z]", reg_password))
            p_num = bool(re.search(r"\d", reg_password))

            color_ok = "#059669"
            color_mute = "#94A3B8"

            st.markdown(
                clean_html(f"""
                <div style="margin: 0.5rem 0 0.9rem 0; padding: 0.75rem 0.9rem; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px;">
                    <div style="font-size: 0.74rem; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.4rem;">
                        Password Security Checklist:
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.35rem; font-size: 0.75rem;">
                        <div style="color: {color_ok if p_len else color_mute}; font-weight: 600;">{'✓' if p_len else '○'} 8+ Characters</div>
                        <div style="color: {color_ok if p_up else color_mute}; font-weight: 600;">{'✓' if p_up else '○'} Uppercase Letter (A-Z)</div>
                        <div style="color: {color_ok if p_low else color_mute}; font-weight: 600;">{'✓' if p_low else '○'} Lowercase Letter (a-z)</div>
                        <div style="color: {color_ok if p_num else color_mute}; font-weight: 600;">{'✓' if p_num else '○'} Number (0-9)</div>
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )

            # Terms and Conditions
            reg_terms = st.checkbox(
                "I agree to the University Campus Facilities Policy & Terms of Service *",
                value=False,
                key="create_terms_check",
            )

            # Prominent Full-Width Crimson Create Account Button (Strictly Student Role)
            btn_create = st.button("🚀 Create Student Account & Enter Dashboard", type="primary", use_container_width=True, key="btn_create_submit")

            if btn_create:
                if not reg_fullname.strip() or not reg_email.strip() or not reg_password:
                    st.error("Please fill in all required fields marked with *.")
                elif not reg_terms:
                    st.error("Please accept the Terms of Service to create an account.")
                elif reg_password != reg_confirm_password:
                    st.error("Passwords do not match. Please re-enter identical passwords.")
                else:
                    with st.spinner("Creating your verified student account..."):
                        reg_ok, reg_res = register_user(
                            email=reg_email.strip(),
                            password=reg_password,
                            full_name=reg_fullname.strip(),
                            account_type="Student",  # Strictly locked to Student
                            student_id=reg_student_id.strip(),
                            department=reg_department.strip(),
                        )
                        if reg_ok:
                            st.session_state.authenticated_user = reg_res
                            st.session_state.current_page = None
                            st.success(f"🎉 Welcome to CampusPilot AI, {reg_res['full_name']}!")
                            time.sleep(0.4)
                            st.rerun()
                        else:
                            st.error(reg_res)

            st.markdown(
                clean_html(f"""
                <div style="text-align: center; margin-top: 1.1rem; font-size: 0.8rem; color: #64748B;">
                    Already registered? Select the <strong>Sign In</strong> tab above.
                </div>
                """),
                unsafe_allow_html=True,
            )

    st.stop()


# ==============================================================================
# DYNAMIC STUDENT / ADMIN IDENTITY RESOLUTION
# ==============================================================================
auth_user = st.session_state.authenticated_user
user_id = str(auth_user.get("student_id") or auth_user.get("user_id") or "CS2026-001").strip()
account_type = auth_user.get("account_type", "Student")
is_admin = account_type == "Administrator"
student_email = auth_user.get("email", "student@campus.edu")
university_name = auth_user.get("university", "Lovely Professional University")

# Resolve actual full name and display name dynamically
db_profile = get_student_profile(auth_user.get("user_id", "")) or get_student_profile_by_email(student_email)
if db_profile:
    raw_name = db_profile.get("full_name", "").strip() or auth_user.get("full_name", "").strip()
    department = db_profile.get("department", auth_user.get("department", "Engineering & Technology"))
else:
    raw_name = auth_user.get("full_name", "").strip()
    department = auth_user.get("department", "Engineering & Technology")

display_name = auth_user.get("display_name", "").strip() or raw_name or "Student"
student_name = raw_name or display_name or ("Administrator" if is_admin else "Student")
avatar_icon = auth_user.get("avatar", "🛡️" if is_admin else "👨‍🎓")

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
                try:
                    send_booking_confirmation_email(
                        recipient_email=student_email,
                        recipient_name=student_name,
                        facility_name=pending["item_name"],
                        booking_date=pending["booking_date"],
                        start_time=pending["start_time"],
                        end_time=pending["end_time"],
                        booking_id=booking_id_val,
                        facility_type=facility_label,
                    )
                except Exception as mail_err:
                    print(f"[Email Notification Note] {mail_err}")

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
# ROLE-BASED NAVIGATION PAGES
# ==============================================================================
if is_admin:
    NAV_PAGES = [
        "🛡️ Admin Dashboard",
        "📥 Booking Requests",
        "🏢 Facility Management",
        "🏖️ Leave Oversight",
        "💬 AI Assistant",
        "⚙️ Settings",
    ]
    if st.session_state.current_page not in NAV_PAGES:
        st.session_state.current_page = "🛡️ Admin Dashboard"
else:
    NAV_PAGES = [
        "📊 Student Dashboard",
        "💬 AI Assistant",
        "🔬 Lab Booking",
        "📚 Discussion Rooms",
        "📋 My Bookings",
        "🏖️ Leave Requests",
        "🏢 Facilities",
        "⚙️ Settings",
    ]
    if st.session_state.current_page not in NAV_PAGES:
        st.session_state.current_page = "📊 Student Dashboard"


# ==============================================================================
# SIDEBAR NAVIGATION
# ==============================================================================
with st.sidebar:
    st.markdown(
        clean_html(f"""
        <div style="padding: 0.4rem 0.2rem 0.8rem 0.2rem; display: flex; align-items: center; gap: 0.6rem;">
            <span style="font-size: 1.75rem;">🎓</span>
            <div>
                <div style="font-weight: 800; font-size: 1.2rem; color: #0F172A; letter-spacing: -0.02em;">CampusPilot AI</div>
                <div style="font-size: 0.72rem; color: #E50914; font-weight: 700;">{'Faculty Admin Portal' if is_admin else 'Student Operations'}</div>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

    # Action Button in Sidebar
    if is_admin:
        if st.button("📥 Review Requests", type="primary", use_container_width=True, key="sidebar_admin_req"):
            st.session_state.current_page = "📥 Booking Requests"
            st.rerun()
    else:
        if st.button("➕ New Booking Request", type="primary", use_container_width=True, key="sidebar_new_booking"):
            st.session_state.current_page = "🔬 Lab Booking"
            st.rerun()

    st.markdown("<div style='height: 0.4rem;'></div>", unsafe_allow_html=True)

    # Navigation Menu
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

    # Bottom Authenticated User Profile Card (White Theme)
    role_color = "#E50914" if is_admin else "#059669"
    st.markdown(
        clean_html(f"""
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 0.85rem; margin-top: 0.8rem; margin-bottom: 0.6rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
                <span style="font-size: 1.35rem;">{avatar_icon}</span>
                <div style="overflow: hidden;">
                    <div style="font-weight: 700; font-size: 0.92rem; color: #0F172A; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{student_name}</div>
                    <div style="font-size: 0.7rem; color: #64748B; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{student_email}</div>
                </div>
            </div>
            <div style="display: flex; gap: 0.3rem; margin-top: 0.4rem; flex-wrap: wrap;">
                <span style="background: #E2E8F0; color: #0F172A; font-size: 0.65rem; padding: 0.12rem 0.45rem; border-radius: 4px; font-weight: 600;">{user_id}</span>
                <span style="background: rgba(229,9,20,0.1); color: {role_color}; font-size: 0.65rem; padding: 0.12rem 0.45rem; border-radius: 4px; font-weight: 700;">{account_type}</span>
            </div>
            <div style="font-size: 0.68rem; color: #64748B; margin-top: 0.35rem; line-height: 1.35;">
                🏛️ {university_name}<br>
                📚 {department}
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

    if st.button("🚪 Sign Out", use_container_width=True, key="sidebar_logout_btn"):
        st.session_state.authenticated_user = None
        st.session_state.current_page = None
        st.session_state.messages = []
        st.session_state.langchain_history = []
        st.session_state.pending_booking = None
        st.rerun()


# ==============================================================================
# COMPACT TOP APP BAR / BRAND HEADER (CLEAN - NO THEME SWITCHER)
# ==============================================================================
backend_online = check_backend_health()
status_pill = (
    '<span class="badge-live">● Backend Live</span>'
    if backend_online
    else '<span class="badge-offline">● Backend Offline</span>'
)

c_nav_left, c_nav_right = st.columns([2.5, 1.5])

with c_nav_left:
    st.markdown(
        clean_html(f"""
        <div style="display: flex; align-items: center; gap: 0.65rem; padding: 0.4rem 0;">
            <span style="font-size: 1.35rem;">🎓</span>
            <div>
                <span class="brand-title">CampusPilot AI</span>
                <span class="brand-tagline">{'Faculty Administration' if is_admin else 'Smart Facility Operations'}</span>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

with c_nav_right:
    st.markdown(
        clean_html(f"""
        <div style="display: flex; align-items: center; justify-content: flex-end; gap: 0.45rem; padding: 0.35rem 0;">
            {status_pill}
            <span class="badge-profile-chip">{avatar_icon} {student_name}</span>
        </div>
        """),
        unsafe_allow_html=True,
    )

# Shared live facility data
labs = get_all_laboratories()
rooms = get_all_discussion_rooms()


# ==============================================================================
# ==============================================================================
# ADMINISTRATOR VIEWS
# ==============================================================================
# ==============================================================================

# ------------------------------------------------------------------------------
# ADMIN VIEW 1: 🛡️ ADMIN DASHBOARD
# ------------------------------------------------------------------------------
if is_admin and st.session_state.current_page == "🛡️ Admin Dashboard":
    metrics = get_admin_dashboard_metrics()

    st.markdown(
        clean_html(f"""
        <div class="hero-banner">
            <h2 class="hero-title">Faculty Administrator Portal — {student_name} 🛡️</h2>
            <p class="hero-subtitle">
                Departmental facility oversight, student booking approval queues, and facility operational controls.
                Real-time metrics computed directly from SQLite database.
            </p>
        </div>
        """),
        unsafe_allow_html=True,
    )

    # 4 Metric Cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Pending Requests</span>
                    <span class="stat-icon">⏳</span>
                </div>
                <div class="stat-value" style="color: {'#DC2626' if metrics['pending_requests'] > 0 else '#0F172A'};">{metrics['pending_requests']}</div>
                <div class="stat-footer" style="color: #D97706;">
                    <span>● Requires Review</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Approved Bookings</span>
                    <span class="stat-icon">✅</span>
                </div>
                <div class="stat-value">{metrics['approved_requests']}</div>
                <div class="stat-footer" style="color: #059669;">
                    <span>● Confirmed in Schedule</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Rejected Requests</span>
                    <span class="stat-icon">❌</span>
                </div>
                <div class="stat-value">{metrics['rejected_requests']}</div>
                <div class="stat-footer" style="color: #DC2626;">
                    <span>● With Documented Reason</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Active Facilities</span>
                    <span class="stat-icon">🏢</span>
                </div>
                <div class="stat-value">{metrics['active_laboratories'] + metrics['active_rooms']}</div>
                <div class="stat-footer" style="color: #059669;">
                    <span>● {metrics['active_laboratories']} Labs &bull; {metrics['active_rooms']} Rooms</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

    # Quick Jump to Pending Queue
    if metrics["pending_requests"] > 0:
        st.warning(f"⚠️ You have **{metrics['pending_requests']} student booking request(s)** awaiting administrative review.")
        if st.button("👉 Open Pending Requests Queue", type="primary", key="btn_dash_open_pending"):
            st.session_state.current_page = "📥 Booking Requests"
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📋 Recent Booking Submissions Across Campus")

    recent_requests = get_all_booking_requests()[:6]
    if recent_requests:
        for r in recent_requests:
            stat = r.get("status", "pending")
            badge = "badge-live" if stat in ("approved", "confirmed") else ("badge-rejected" if stat == "rejected" else "badge-pending")
            st.markdown(
                clean_html(f"""
                <div class="booking-row">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                        <span style="font-weight: 700; font-size: 0.95rem;">{r['facility_name']} <span style="font-size: 0.8rem; color: #64748B;">({r['service_type']})</span></span>
                        <span class="{badge}">{stat.upper()} &bull; #{r['booking_id']}</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #64748B;">
                        👤 <b>{r['student_name']}</b> ({r['student_id']}) &bull; 📅 {r['booking_date']} &bull; ⏰ {r['start_time']} - {r['end_time']}<br>
                        🎯 <b>Purpose:</b> {r.get('purpose') or 'Academic / General Practical'}
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )
    else:
        st.info("No booking requests recorded in the system yet.")


# ------------------------------------------------------------------------------
# ADMIN VIEW 2: 📥 BOOKING REQUESTS (APPROVAL & REJECTION WORKFLOW)
# ------------------------------------------------------------------------------
elif is_admin and st.session_state.current_page == "📥 Booking Requests":
    st.markdown("### 📥 Student Facility Booking Requests")
    st.caption("Review incoming student requests, verify schedule availability, and execute approvals or rejections with documented reasons:")

    req_tab_all, req_tab_pending, req_tab_appr, req_tab_rej = st.tabs([
        "All Requests",
        "⏳ Pending Approval (Action Required)",
        "✅ Approved",
        "❌ Rejected",
    ])

    def render_admin_request_list(status_filter=None, tab_key="all"):
        requests_list = get_all_booking_requests(status_filter=status_filter)
        if not requests_list:
            st.info(f"No requests found matching filter: {status_filter or 'All'}.")
            return

        for r in requests_list:
            b_id = r["booking_id"]
            s_type = r["service_type"]
            cur_status = r.get("status", "pending")
            status_badge = "badge-live" if cur_status in ("approved", "confirmed") else ("badge-rejected" if cur_status == "rejected" else "badge-pending")

            col_card, col_action = st.columns([3.2, 1.8])
            with col_card:
                rejection_html = ""
                if cur_status == "rejected" and r.get("rejection_reason"):
                    rejection_html = f"""<div class="rejection-box"><b>Rejection Reason:</b> {r['rejection_reason']}</div>"""

                dept_display = r.get("department") or "Computer Science & Engineering"
                created_display = r.get("created_at") or "Standard Request"

                st.markdown(
                    clean_html(f"""
                    <div class="content-card" style="margin-bottom: 0.75rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                            <span style="font-weight: 800; font-size: 1.05rem;">{r['facility_name']} <span style="font-size: 0.8rem; color: #64748B;">({s_type})</span></span>
                            <span class="{status_badge}">{cur_status.upper()} &bull; #{b_id}</span>
                        </div>
                        <div style="font-size: 0.84rem; color: #64748B; line-height: 1.55;">
                            👤 <b>Student:</b> {r['student_name']} &bull; <b>ID:</b> <code>{r['student_id']}</code> &bull; <b>Dept:</b> {dept_display}<br>
                            📅 <b>Date:</b> {r['booking_date']} &bull; ⏰ <b>Slot:</b> {r['start_time']} - {r['end_time']}<br>
                            🎯 <b>Purpose:</b> <i>{r.get('purpose') or 'Not specified'}</i><br>
                            ⏱️ <b>Submitted:</b> <span style="color: #64748B;">{created_display}</span>
                        </div>
                        {rejection_html}
                    </div>
                    """),
                    unsafe_allow_html=True,
                )

            with col_action:
                if cur_status == "pending":
                    # Approve Action
                    if st.button("✅ Approve Request", key=f"adm_appr_{tab_key}_{b_id}", type="primary", use_container_width=True):
                        ok, msg = approve_booking(b_id, s_type)
                        if ok:
                            st.success(f"Request #{b_id} Approved!")
                            time.sleep(0.4)
                            st.rerun()
                        else:
                            st.error(msg)

                    # Reject Expander
                    with st.expander("❌ Reject with Reason", expanded=False):
                        rej_reason = st.text_input(
                            "Rejection Reason",
                            value="Departmental priority examination scheduled during this slot",
                            key=f"rej_reason_in_{tab_key}_{b_id}",
                        )
                        if st.button("Confirm Rejection", key=f"adm_rej_{tab_key}_{b_id}", use_container_width=True):
                            if reject_booking(b_id, s_type, rej_reason):
                                st.warning(f"Request #{b_id} Rejected.")
                                time.sleep(0.4)
                                st.rerun()
                elif cur_status in ("approved", "confirmed"):
                    st.caption("Approved and active in schedule.")
                    if st.button("Revoke / Cancel", key=f"adm_cancel_{tab_key}_{b_id}", use_container_width=True):
                        cancel_reservation(b_id, s_type)
                        st.info(f"Booking #{b_id} cancelled.")
                        time.sleep(0.4)
                        st.rerun()
                else:
                    st.caption(f"Status: {cur_status.capitalize()}")

    with req_tab_all:
        render_admin_request_list(status_filter=None, tab_key="all")
    with req_tab_pending:
        render_admin_request_list(status_filter="pending", tab_key="pending")
    with req_tab_appr:
        render_admin_request_list(status_filter="approved", tab_key="approved")
    with req_tab_rej:
        render_admin_request_list(status_filter="rejected", tab_key="rejected")


# ------------------------------------------------------------------------------
# ADMIN VIEW 3: 🏢 FACILITY MANAGEMENT (ENABLE / DISABLE TOGGLES)
# ------------------------------------------------------------------------------
elif is_admin and st.session_state.current_page == "🏢 Facility Management":
    st.markdown("### 🏢 Campus Facility Operational Management")
    st.caption("Enable or disable facility booking for maintenance, exams, or departmental overrides:")

    st.markdown("#### 🔬 Computer Laboratories")
    for lab in labs:
        c_info, c_toggle = st.columns([3.5, 1.5])
        is_en = bool(lab.get("is_enabled", 1))
        with c_info:
            st.markdown(
                clean_html(f"""
                <div class="content-card" style="margin-bottom: 0.6rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 800; font-size: 1.05rem;">{lab['lab_name']}</span>
                        <span class="{'badge-live' if is_en else 'badge-offline'}">{'🟢 BOOKING ENABLED' if is_en else '🔴 BOOKING DISABLED'}</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #64748B; margin-top: 0.2rem;">
                        📍 {lab['location']} &bull; 👥 Capacity: <b>{lab['capacity']} Workstations</b>
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )
        with c_toggle:
            btn_label = "🔒 Disable Lab" if is_en else "🔓 Enable Lab"
            if st.button(btn_label, key=f"toggle_lab_{lab['lab_id']}", use_container_width=True):
                toggle_facility_status("lab", lab["lab_id"], 0 if is_en else 1)
                st.rerun()

    st.markdown("---")
    st.markdown("#### 📚 Discussion Rooms")
    for room in rooms:
        c_rinfo, c_rtoggle = st.columns([3.5, 1.5])
        is_ren = bool(room.get("is_enabled", 1))
        with c_rinfo:
            st.markdown(
                clean_html(f"""
                <div class="content-card" style="margin-bottom: 0.6rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 800; font-size: 1.05rem;">{room['room_name']}</span>
                        <span class="{'badge-live' if is_ren else 'badge-offline'}">{'🟢 BOOKING ENABLED' if is_ren else '🔴 BOOKING DISABLED'}</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #64748B; margin-top: 0.2rem;">
                        📍 {room['location']} &bull; 👥 Capacity: <b>{room['capacity']} Seats</b>
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )
        with c_rtoggle:
            rbtn_label = "🔒 Disable Room" if is_ren else "🔓 Enable Room"
            if st.button(rbtn_label, key=f"toggle_room_{room['room_id']}", use_container_width=True):
                toggle_facility_status("room", room["room_id"], 0 if is_ren else 1)
                st.rerun()


# ------------------------------------------------------------------------------
# ADMIN VIEW 4: 🏖️ LEAVE OVERSIGHT
# ------------------------------------------------------------------------------
elif is_admin and st.session_state.current_page == "🏖️ Leave Oversight":
    st.markdown("### 🏖️ Campus Student Leave Requests Oversight")
    st.caption("Review student leave applications across academic departments with policy decisions and administrator approval controls:")

    all_leaves = get_all_leave_requests()
    if all_leaves:
        pending_leaves = [l for l in all_leaves if "pending" in l.get("status", "").lower()]
        approved_leaves = [l for l in all_leaves if "approved" in l.get("status", "").lower()]
        rejected_leaves = [l for l in all_leaves if "rejected" in l.get("status", "").lower()]

        st.markdown(
            f"**Total Leaves:** `{len(all_leaves)}` &bull; **Action Required:** `{len(pending_leaves)}` &bull; **Approved:** `{len(approved_leaves)}` &bull; **Rejected:** `{len(rejected_leaves)}`"
        )

        for l in all_leaves:
            l_id = l["leave_id"]
            cur_lstatus = l.get("status", "Pending Review")
            badge_class = "badge-live" if "approved" in cur_lstatus.lower() else ("badge-rejected" if "rejected" in cur_lstatus.lower() else "badge-pending")

            col_lcard, col_lact = st.columns([3.4, 1.6])
            with col_lcard:
                st.markdown(
                    clean_html(f"""
                    <div class="content-card" style="margin-bottom: 0.75rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                            <span style="font-weight: 800; font-size: 1.05rem;">{l['leave_type']} &bull; {l['student_name']}</span>
                            <span class="{badge_class}">{cur_lstatus}</span>
                        </div>
                        <div style="font-size: 0.84rem; color: #64748B; line-height: 1.5;">
                            👤 <b>ID:</b> <code>{l['student_id']}</code> &bull; <b>Email:</b> {l['student_email']}<br>
                            📅 <b>Dates:</b> {l['start_date']} to {l['end_date']}<br>
                            📝 <b>Reason:</b> <i>{l['reason']}</i>
                        </div>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )

            with col_lact:
                if "pending" in cur_lstatus.lower():
                    if st.button("✅ Approve Leave", key=f"appr_leave_btn_{l_id}", type="primary", use_container_width=True):
                        update_leave_status(l_id, "Approved (Admin)")
                        st.success(f"Leave #{l_id} Approved!")
                        time.sleep(0.4)
                        st.rerun()

                    if st.button("❌ Reject Leave", key=f"rej_leave_btn_{l_id}", use_container_width=True):
                        update_leave_status(l_id, "Rejected")
                        st.warning(f"Leave #{l_id} Rejected.")
                        time.sleep(0.4)
                        st.rerun()
                else:
                    st.caption(f"Status: {cur_lstatus}")
    else:
        st.info("No student leave requests recorded yet.")


# ==============================================================================
# ==============================================================================
# STUDENT VIEWS
# ==============================================================================
# ==============================================================================

# ------------------------------------------------------------------------------
# STUDENT VIEW 1: 📊 STUDENT DASHBOARD
# ------------------------------------------------------------------------------
elif not is_admin and st.session_state.current_page == "📊 Student Dashboard":
    # 1. Personalized Hero Welcome Banner
    st.markdown(
        clean_html(f"""
        <div class="hero-banner">
            <h2 class="hero-title">Welcome back, {student_name}! 👋</h2>
            <p class="hero-subtitle">
                Logged in as <b>Student</b> &bull; Roll No: <code>{user_id}</code> &bull; Department: <b>{department}</b>.<br>
                State your request in natural language — CampusPilot AI verifies real-time SQLite availability,
                detects scheduling conflicts, and submits your booking requests.
            </p>
        </div>
        """),
        unsafe_allow_html=True,
    )

    # 2. Suggested Prompt Chips (Direct AI Triggers)
    st.caption("⚡ **Click any prompt to run an autonomous request:**")
    h_c1, h_c2, h_c3, h_c4 = st.columns(4)
    with h_c1:
        if st.button("🔬 Lab for 30 students tomorrow 10-12", use_container_width=True, key="h_p1"):
            process_user_input("I need a computer lab for 30 students tomorrow from 10 AM to 12 PM for a Python practical")
            st.session_state.current_page = "💬 AI Assistant"
            st.rerun()
    with h_c2:
        if st.button("📚 Room for 4 students tomorrow 2-4 PM", use_container_width=True, key="h_p2"):
            process_user_input("Find me a discussion room for 4 people tomorrow from 2 PM to 4 PM for group study")
            st.session_state.current_page = "💬 AI Assistant"
            st.rerun()
    with h_c3:
        if st.button("🔍 Check AI Lab tomorrow 10-12", use_container_width=True, key="h_p3"):
            process_user_input("Check if AI Lab is available tomorrow from 10:00 to 12:00")
            st.session_state.current_page = "💬 AI Assistant"
            st.rerun()
    with h_c4:
        if st.button("📋 Show my upcoming bookings", use_container_width=True, key="h_p4"):
            process_user_input(f"Show all my upcoming reservations for {user_id}")
            st.session_state.current_page = "💬 AI Assistant"
            st.rerun()

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

    # 3. Four Student Metric Cards
    my_all_res = get_all_student_reservations(student_id=user_id)
    my_active = len([b for b in my_all_res if b.get("status") in ("confirmed", "approved")])
    my_pending = len([b for b in my_all_res if b.get("status") == "pending"])
    my_leaves = len(get_student_leave_requests(student_id=user_id))

    c_s1, c_s2, c_s3, c_s4 = st.columns(4)
    with c_s1:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Active Bookings</span>
                    <span class="stat-icon">📅</span>
                </div>
                <div class="stat-value">{my_active}</div>
                <div class="stat-footer" style="color: #059669;">
                    <span>● Confirmed in SQLite</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with c_s2:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Pending Approval</span>
                    <span class="stat-icon">⏳</span>
                </div>
                <div class="stat-value" style="color: {'#DC2626' if my_pending > 0 else '#0F172A'};">{my_pending}</div>
                <div class="stat-footer" style="color: #D97706;">
                    <span>● Under Review</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with c_s3:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">Approved Leaves</span>
                    <span class="stat-icon">🏖️</span>
                </div>
                <div class="stat-value">{my_leaves}</div>
                <div class="stat-footer" style="color: #059669;">
                    <span>● Auto-Accepted</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with c_s4:
        st.markdown(
            clean_html(f"""
            <div class="stat-card">
                <div class="stat-header">
                    <span class="stat-label">AI Campus Assistant</span>
                    <span class="stat-icon">🤖</span>
                </div>
                <div class="stat-value">Online</div>
                <div class="stat-footer" style="color: #059669;">
                    <span>● Gemini-Powered</span>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

    # 4. Balanced Two-Column Section
    col_dash_left, col_dash_right = st.columns([1.4, 1], gap="large")

    with col_dash_left:
        st.markdown(
            clean_html(f"""
            <div class="card-header-title">
                <span>📋 My Recent Reservations</span>
                <span class="badge-profile-chip">{user_id}</span>
            </div>
            """),
            unsafe_allow_html=True,
        )

        if my_all_res:
            for b in my_all_res[:4]:
                b_stat = b.get("status", "pending")
                badge = "badge-live" if b_stat in ("confirmed", "approved") else ("badge-rejected" if b_stat == "rejected" else "badge-pending")
                st.markdown(
                    clean_html(f"""
                    <div class="booking-row">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
                            <span style="font-weight: 700; font-size: 0.95rem;">{b['facility_name']}</span>
                            <span class="{badge}">{b_stat.upper()} &bull; #{b['booking_id']}</span>
                        </div>
                        <div style="font-size: 0.82rem; color: #64748B;">
                            📅 {b['booking_date']} &bull; ⏰ {b['start_time']} - {b['end_time']}<br>
                            🎯 <b>Purpose:</b> {b.get('purpose') or 'Academic Practical'}
                        </div>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )
        else:
            st.info("You have no reservations yet. Click below to book a lab or study room!")

    with col_dash_right:
        st.markdown(
            clean_html(f"""
            <div class="card-header-title">
                <span>⚡ Quick Actions</span>
            </div>
            """),
            unsafe_allow_html=True,
        )
        qa1, qa2 = st.columns(2)
        with qa1:
            if st.button("🔬 Book Lab", use_container_width=True, key="sd_qa_lab"):
                st.session_state.current_page = "🔬 Lab Booking"
                st.rerun()
            if st.button("🏖️ Leave Request", use_container_width=True, key="sd_qa_leave"):
                st.session_state.current_page = "🏖️ Leave Requests"
                st.rerun()
        with qa2:
            if st.button("📚 Book Room", use_container_width=True, key="sd_qa_room"):
                st.session_state.current_page = "📚 Discussion Rooms"
                st.rerun()
            if st.button("📋 My Bookings", use_container_width=True, key="sd_qa_myb"):
                st.session_state.current_page = "📋 My Bookings"
                st.rerun()

        st.markdown("<div style='height: 0.6rem;'></div>", unsafe_allow_html=True)
        st.markdown(
            clean_html(f"""
            <div class="content-card">
                <div style="font-weight: 700; font-size: 0.88rem; margin-bottom: 0.4rem; color: #E50914;">💡 Booking Workflow Guide:</div>
                <div style="font-size: 0.8rem; color: #64748B; line-height: 1.5;">
                    <b>1. Submit Request:</b> Select lab and state your purpose.<br>
                    <b>2. Pending Status:</b> Awaits faculty admin review.<br>
                    <b>3. Admin Approval:</b> Confirms slot or records reason.<br>
                    <b>4. Instant Ledger:</b> Track live status in My Bookings.
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------------------------
# SHARED VIEW: 💬 AI ASSISTANT
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "💬 AI Assistant":
    st.markdown(f"### 💬 Gemini-Powered AI Campus Assistant ({student_name})")
    st.caption("Describe your scheduling needs naturally. The assistant extracts constraints, queries SQLite, ranks candidate venues, and presents interactive options.")

    # Suggested prompt pills
    st.markdown("**Suggested Prompts:**")
    ap_c1, ap_c2, ap_c3, ap_c4 = st.columns(4)
    with ap_c1:
        if st.button("💻 Lab for 30 students tomorrow 10-12", use_container_width=True, key="ap_p1"):
            process_user_input("I need a computer lab for 30 students tomorrow from 10 AM to 12 PM for a Python practical")
            st.rerun()
    with ap_c2:
        if st.button("📚 Room for 4 students tomorrow 2-4 PM", use_container_width=True, key="ap_p2"):
            process_user_input("Find me a discussion room for 4 people tomorrow from 2 PM to 4 PM for group study")
            st.rerun()
    with ap_c3:
        if st.button("🔍 Check AI Lab Tomorrow 10-12", use_container_width=True, key="ap_p3"):
            process_user_input("Check if AI Lab is available tomorrow from 10:00 to 12:00")
            st.rerun()
    with ap_c4:
        if st.button("📋 Show My Bookings", use_container_width=True, key="ap_p4"):
            process_user_input(f"Show all my upcoming reservations for {user_id}")
            st.rerun()

    st.markdown("---")

    # Conversation History
    for m_idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Tool Execution Traces Expander
            if msg.get("steps"):
                with st.expander(f"🛠️ Execution Trace ({len(msg['steps'])} tool steps)", expanded=False):
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
                        clean_html(f"""
                        <div class="rec-card">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                                <span style="font-weight: 800; font-size: 1.05rem; color: #0F172A;">{rec['facility_name']}</span>
                                <span class="{badge_class}">{rec.get('match_badge', 'Option')}</span>
                            </div>
                            <div style="font-size: 0.84rem; color: #64748B; margin-bottom: 0.4rem;">
                                📍 {rec.get('location')} &bull; 👥 Capacity: <b>{rec.get('capacity')}</b> &bull; ⏰ <b>{rec.get('start_time')} - {rec.get('end_time')}</b> ({rec.get('booking_date')})
                            </div>
                            <div style="font-size: 0.84rem; color: #E50914; margin-bottom: 0.75rem;">
                                💡 <i>{rec.get('match_reason')}</i>
                            </div>
                        </div>
                        """),
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
            clean_html(f"""
            <div class="booking-confirm-card">
                <div class="booking-confirm-header">
                    <span>🛡️ Explicit Confirmation Required</span>
                </div>
                <p style="font-size: 0.9rem; color: #64748B; margin: 0 0 1rem 0;">
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
                        <div class="booking-item-label">Account Details</div>
                        <div class="booking-item-value">{student_name} ({user_id})</div>
                    </div>
                </div>
            </div>
            """),
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


# ------------------------------------------------------------------------------
# STUDENT VIEW 2: 🔬 LAB BOOKING (SUBMITS AS PENDING ADMIN APPROVAL)
# ------------------------------------------------------------------------------
elif not is_admin and st.session_state.current_page == "🔬 Lab Booking":
    st.markdown(f"### 🔬 Campus Laboratory Reservation")
    st.caption("Request a computer or engineering lab based on capacity, date, and academic purpose. Submissions enter the administrator review queue:")

    col_form, col_display = st.columns([1.2, 1], gap="large")

    with col_form:
        st.markdown("#### 📅 Direct Slot Checker & Booking Form")
        enabled_labs = [l for l in labs if l.get("is_enabled", 1) == 1]
        if not enabled_labs:
            st.error("All laboratory bookings are currently disabled by the administrator.")
            lab_options = {}
        else:
            lab_options = {lab["lab_name"]: lab["lab_id"] for lab in enabled_labs}

        if lab_options:
            selected_lab_name = st.selectbox("Select Laboratory", list(lab_options.keys()), key="lab_sel_box")
            selected_lab_id = lab_options[selected_lab_name]

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                pick_date = st.date_input("Booking Date", value=date.today() + timedelta(days=1), key="lab_date_pick")
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
                pick_slot = st.selectbox("Time Interval", slot_labels, index=1, key="lab_slot_pick")

            start_t, end_t = pick_slot.split(" - ")
            date_str = pick_date.strftime("%Y-%m-%d")

            # Purpose Field
            lab_purpose = st.text_input(
                "Purpose of Reservation *",
                value="Final Year AI Project Model Training Practical",
                placeholder="e.g. Machine Learning Practical, Cloud Computing Lab Session",
                key="lab_purpose_input",
            )

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🔍 Check Availability", use_container_width=True, key="btn_check_lab"):
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
                if st.button("⚡ Submit Booking Request", type="primary", use_container_width=True, key="btn_confirm_lab"):
                    if not lab_purpose.strip():
                        st.error("Please provide the purpose of your reservation.")
                    else:
                        with st.spinner("Submitting booking request for admin approval..."):
                            try:
                                b_record = create_booking(
                                    student_id=user_id,
                                    student_name=student_name,
                                    lab_id=selected_lab_id,
                                    booking_date=date_str,
                                    start_time=start_t,
                                    end_time=end_t,
                                    status="pending",
                                    purpose=lab_purpose.strip(),
                                )
                                st.success(
                                    f"🎉 Request #{b_record['booking_id']} Submitted! "
                                    f"Status: **Pending Admin Approval**. You can track review status under **My Bookings**."
                                )
                                time.sleep(1.2)
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Booking Error: {str(ex)}")

    with col_display:
        st.markdown(f"#### 📋 Reservations on {date_str if 'date_str' in locals() else today_str}")
        if lab_options:
            bookings_on_date = get_bookings_by_date(date_str, lab_id=selected_lab_id)
            if bookings_on_date:
                for b in bookings_on_date:
                    st.markdown(
                        clean_html(f"""
                        <div class="booking-row">
                            <b>{b['start_time']} - {b['end_time']}</b> &bull; {b['student_name']}<br>
                            <span style="font-size: 0.78rem; color: #64748B;">Ref #{b['booking_id']} &bull; Status: {b['status'].upper()}</span>
                        </div>
                        """),
                        unsafe_allow_html=True,
                    )
            else:
                st.info(f"No existing reservations for {selected_lab_name} on {date_str}. All slots are available!")


# ------------------------------------------------------------------------------
# STUDENT VIEW 3: 📚 DISCUSSION ROOMS
# ------------------------------------------------------------------------------
elif not is_admin and st.session_state.current_page == "📚 Discussion Rooms":
    st.markdown("### 📚 Library Discussion Rooms")
    st.caption("Reserve collaborative group study spaces equipped with whiteboards and digital displays:")

    col_r_form, col_r_display = st.columns([1.2, 1], gap="large")

    with col_r_form:
        st.markdown("#### 📅 Discussion Room Reservation Form")
        enabled_rooms = [r for r in rooms if r.get("is_enabled", 1) == 1]
        if not enabled_rooms:
            st.error("All discussion rooms are currently disabled by the administrator.")
            room_options = {}
        else:
            room_options = {room["room_name"]: room["room_id"] for room in enabled_rooms}

        if room_options:
            selected_room_name = st.selectbox("Select Discussion Room", list(room_options.keys()), key="room_sel_box")
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

            room_purpose = st.text_input(
                "Purpose of Discussion / Study *",
                value="Capstone Project Group Brainstorming & Architecture Design",
                key="room_purpose_in",
            )

            col_rbtn1, col_rbtn2 = st.columns(2)
            with col_rbtn1:
                if st.button("🔍 Check Room Availability", use_container_width=True, key="btn_check_room"):
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
                if st.button("⚡ Reserve Discussion Room", type="primary", use_container_width=True, key="btn_confirm_room"):
                    with st.spinner("Reserving room in SQLite..."):
                        try:
                            rb_rec = create_room_booking(
                                student_id=user_id,
                                student_name=student_name,
                                room_id=selected_room_id,
                                booking_date=room_date_str,
                                start_time=start_rt,
                                end_time=end_rt,
                                status="confirmed",
                                purpose=room_purpose.strip(),
                            )
                            st.success(f"🎉 Discussion Room Reserved! Reference #{rb_rec['booking_id']}")
                            time.sleep(1)
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Reservation Error: {str(ex)}")

    with col_r_display:
        st.markdown(f"#### 📋 Reservations on {room_date_str if 'room_date_str' in locals() else today_str}")
        if room_options:
            r_bookings = get_room_bookings_by_date(room_date_str, room_id=selected_room_id)
            if r_bookings:
                for rb in r_bookings:
                    st.markdown(
                        clean_html(f"""
                        <div class="booking-row">
                            <b>{rb['start_time']} - {rb['end_time']}</b> &bull; {rb['student_name']}<br>
                            <span style="font-size: 0.78rem; color: #64748B;">Ref #{rb['booking_id']} &bull; Status: {rb['status'].upper()}</span>
                        </div>
                        """),
                        unsafe_allow_html=True,
                    )
            else:
                st.info(f"No existing reservations for {selected_room_name} on {room_date_str}. All slots are available!")


# ------------------------------------------------------------------------------
# STUDENT VIEW 4: 📋 MY BOOKINGS (PENDING, APPROVED, REJECTED + REASONS)
# ------------------------------------------------------------------------------
elif not is_admin and st.session_state.current_page == "📋 My Bookings":
    st.markdown(f"### 📋 Reservations for {student_name} ({user_id})")
    st.caption("Review, track, and manage all your campus laboratory and discussion room reservations:")

    # Strictly isolated query for authenticated user's ID
    my_all_res = get_all_student_reservations(student_id=user_id)

    tab_all, tab_pending, tab_approved, tab_rejected, tab_cancelled = st.tabs([
        "All My Bookings",
        "⏳ Pending Approval",
        "✅ Approved",
        "❌ Rejected",
        "🚫 Cancelled",
    ])

    def render_student_booking_list(filter_status=None, tab_id="all"):
        bookings = my_all_res
        if filter_status:
            if filter_status == "approved":
                bookings = [b for b in bookings if b.get("status") in ("approved", "confirmed")]
            else:
                bookings = [b for b in bookings if b.get("status") == filter_status]

        if not bookings:
            st.info(f"No bookings found in category: {filter_status or 'All'}.")
            return

        for b in bookings:
            cur_stat = b.get("status", "pending")
            status_badge = "badge-live" if cur_stat in ("approved", "confirmed") else ("badge-rejected" if cur_stat == "rejected" else "badge-pending")
            b_id = b["booking_id"]
            s_type = b["service_type"]

            c_info, c_action = st.columns([4, 1.2])
            with c_info:
                rejection_html = ""
                if cur_stat == "rejected" and b.get("rejection_reason"):
                    rejection_html = f"""<div class="rejection-box"><b>Administrator Feedback:</b> {b['rejection_reason']}</div>"""

                st.markdown(
                    clean_html(f"""
                    <div class="content-card" style="margin-bottom: 0.7rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                            <span style="font-weight: 800; font-size: 1.05rem; color: #0F172A;">{b['facility_name']} <span style="font-size: 0.8rem; color: #64748B;">({s_type})</span></span>
                            <span class="{status_badge}">REF #{b_id} &bull; {cur_stat.upper()}</span>
                        </div>
                        <div style="font-size: 0.84rem; color: #64748B; line-height: 1.5;">
                            📅 <b>{b['booking_date']}</b> &bull; ⏰ <b>{b['start_time']} - {b['end_time']}</b> &bull; 📍 {b['location']}<br>
                            🎯 <b>Purpose:</b> <i>{b.get('purpose') or 'Academic Practical'}</i>
                        </div>
                        {rejection_html}
                    </div>
                    """),
                    unsafe_allow_html=True,
                )
            with c_action:
                if cur_stat in ("confirmed", "approved", "pending"):
                    btn_key = f"cancel_{tab_id}_{s_type.replace(' ', '_')}_{b_id}"
                    if st.button("Cancel Booking", key=btn_key, use_container_width=True):
                        success = cancel_reservation(b_id, s_type)
                        if success:
                            st.success(f"Booking #{b_id} cancelled.")
                            time.sleep(0.4)
                            st.rerun()

    with tab_all:
        render_student_booking_list(filter_status=None, tab_id="all")
    with tab_pending:
        render_student_booking_list(filter_status="pending", tab_id="pending")
    with tab_approved:
        render_student_booking_list(filter_status="approved", tab_id="approved")
    with tab_rejected:
        render_student_booking_list(filter_status="rejected", tab_id="rejected")
    with tab_cancelled:
        render_student_booking_list(filter_status="cancelled", tab_id="cancelled")


# ------------------------------------------------------------------------------
# STUDENT VIEW 5: 🏖️ LEAVE REQUESTS (AUTOMATIC ACCEPTANCE RULE)
# ------------------------------------------------------------------------------
elif not is_admin and st.session_state.current_page == "🏖️ Leave Requests":
    st.markdown("### 🏖️ Student Academic & Medical Leave Requests")
    st.caption("Submit leave requests evaluated under the automated university campus leave policy:")

    col_lform, col_lhistory = st.columns([1.2, 1], gap="large")

    with col_lform:
        st.markdown("#### 📝 New Leave Application")
        leave_type = st.selectbox(
            "Leave Category *",
            [
                "Medical / Sick Leave",
                "Academic / Conference Leave",
                "On-Duty / Project Work Leave",
                "Personal / Family Emergency",
            ],
            key="leave_type_select",
        )

        c_ld1, c_ld2 = st.columns(2)
        with c_ld1:
            l_start = st.date_input("Start Date *", value=date.today() + timedelta(days=1), key="leave_start_date")
        with c_ld2:
            l_end = st.date_input("End Date *", value=date.today() + timedelta(days=2), key="leave_end_date")

        leave_reason = st.text_area(
            "Reason / Justification *",
            placeholder="e.g. Attending the IEEE Student Conference on AI and Robotics in New Delhi",
            key="leave_reason_text",
        )

        if st.button("🚀 Submit Leave Request", type="primary", use_container_width=True, key="btn_submit_leave"):
            if not leave_reason.strip():
                st.error("Please provide a reason for the leave request.")
            elif l_start > l_end:
                st.error("Start date cannot be after end date.")
            else:
                with st.spinner("Applying university leave policy..."):
                    try:
                        l_rec = create_leave_request(
                            student_id=user_id,
                            student_name=student_name,
                            student_email=student_email,
                            leave_type=leave_type,
                            start_date=l_start.strftime("%Y-%m-%d"),
                            end_date=l_end.strftime("%Y-%m-%d"),
                            reason=leave_reason.strip(),
                        )
                        if "approved" in l_rec['status'].lower():
                            st.success(
                                f"🎉 Leave Request Auto-Accepted! Reference #{l_rec['leave_id']}. "
                                f"Policy Decision: **{l_rec['status']}**."
                            )
                        else:
                            st.info(
                                f"📋 Leave Request Submitted for Administrator Review. Reference #{l_rec['leave_id']}. "
                                f"Status: **{l_rec['status']}**."
                            )
                        time.sleep(1)
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Leave Submission Error: {str(ex)}")

    with col_lhistory:
        st.markdown("#### 📋 My Leave Records")
        my_leaves = get_student_leave_requests(student_id=user_id)
        if my_leaves:
            for l in my_leaves:
                st_val = l.get("status", "Pending Review")
                badge_cls = "badge-live" if "approved" in st_val.lower() else ("badge-rejected" if "rejected" in st_val.lower() else "badge-pending")
                st.markdown(
                    clean_html(f"""
                    <div class="content-card" style="margin-bottom: 0.6rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                            <span style="font-weight: 700; font-size: 0.95rem;">{l['leave_type']}</span>
                            <span class="{badge_cls}">{st_val}</span>
                        </div>
                        <div style="font-size: 0.82rem; color: #64748B;">
                            📅 {l['start_date']} to {l['end_date']}<br>
                            📝 <i>{l['reason']}</i>
                        </div>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )
        else:
            st.info("No past leave requests found.")


# ------------------------------------------------------------------------------
# STUDENT VIEW 6: 🏢 FACILITIES CATALOG
# ------------------------------------------------------------------------------
elif not is_admin and st.session_state.current_page == "🏢 Facilities":
    st.markdown("### 🏢 Campus Facilities Directory")
    st.caption("Explore verified specifications, workstation capacities, and installed hardware/software across campus venues:")

    st.markdown("#### 🔬 Engineering & Computer Laboratories")
    l_c1, l_c2, l_c3 = st.columns(3)
    cols = [l_c1, l_c2, l_c3]
    for idx, lab in enumerate(labs):
        details = get_facility_details_by_id("lab", lab["lab_id"]) or {}
        is_en = bool(lab.get("is_enabled", 1))
        with cols[idx % 3]:
            st.markdown(
                clean_html(f"""
                <div class="content-card" style="margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="font-weight: 800; font-size: 1.1rem; color: #0F172A;">{lab['lab_name']}</span>
                        <span class="{'badge-live' if is_en else 'badge-offline'}">{'ACTIVE' if is_en else 'MAINTENANCE'}</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 0.6rem;">
                        📍 {lab['location']}<br>
                        👥 Capacity: <b>{lab['capacity']} Workstations</b>
                    </div>
                    <div style="font-size: 0.78rem; color: #E50914; margin-bottom: 0.9rem;">
                        <b>Amenities & Specs:</b><br>
                        • {"<br>• ".join(details.get("equipment", ["Standard Workstations", "Gigabit LAN"]))}
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )
            if is_en:
                if st.button(f"⚡ Book {lab['lab_name']}", key=f"fac_book_lab_{lab['lab_id']}", use_container_width=True):
                    st.session_state.current_page = "🔬 Lab Booking"
                    st.rerun()

    st.markdown("---")
    st.markdown("#### 📚 Library Discussion Rooms")
    r_c1, r_c2, r_c3 = st.columns(3)
    r_cols = [r_c1, r_c2, r_c3]
    for idx, room in enumerate(rooms):
        details = get_facility_details_by_id("room", room["room_id"]) or {}
        is_ren = bool(room.get("is_enabled", 1))
        with r_cols[idx % 3]:
            st.markdown(
                clean_html(f"""
                <div class="content-card" style="margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="font-weight: 800; font-size: 1.1rem; color: #0F172A;">{room['room_name']}</span>
                        <span class="{'badge-live' if is_ren else 'badge-offline'}">{'ACTIVE' if is_ren else 'MAINTENANCE'}</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 0.6rem;">
                        📍 {room['location']}<br>
                        👥 Capacity: <b>{room['capacity']} Seats</b>
                    </div>
                    <div style="font-size: 0.78rem; color: #E50914; margin-bottom: 0.9rem;">
                        <b>Amenities & Specs:</b><br>
                        • {"<br>• ".join(details.get("equipment", ["Whiteboard", "High-speed Wi-Fi"]))}
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )
            if is_ren:
                if st.button(f"⚡ Book {room['room_name']}", key=f"fac_book_room_{room['room_id']}", use_container_width=True):
                    st.session_state.current_page = "📚 Discussion Rooms"
                    st.rerun()


# ------------------------------------------------------------------------------
# SHARED VIEW: ⚙️ SETTINGS & DIAGNOSTICS (NO THEME SWITCHER)
# ------------------------------------------------------------------------------
elif st.session_state.current_page == "⚙️ Settings":
    st.markdown(f"### ⚙️ System Settings & Diagnostics ({student_name})")
    st.caption("Configure notifications, update profile details, and review backend runtime parameters:")

    col_set1, col_set2 = st.columns(2, gap="large")

    with col_set1:
        st.markdown("#### 👤 Account Profile Information")
        with st.form("form_edit_profile"):
            edit_name = st.text_input("Full Name", value=raw_name if raw_name else "", key="edit_prof_name")
            st.text_input("Account Identifier / Student ID", value=user_id, disabled=True, key="edit_prof_id")
            st.text_input("Account Role / Type", value=account_type, disabled=True, key="edit_prof_role")
            st.text_input("Registered Email", value=student_email, disabled=True, key="edit_prof_email")
            st.text_input("Institution", value=university_name, disabled=True, key="edit_prof_univ")
            edit_dept = st.text_input("Department", value=department, key="edit_prof_dept")
            save_prof_btn = st.form_submit_button("Update Profile Details", type="primary")

            if save_prof_btn:
                upsert_student_profile(
                    user_id=auth_user.get("user_id", user_id),
                    full_name=edit_name.strip(),
                    email=student_email,
                    department=edit_dept.strip(),
                )
                if st.session_state.authenticated_user:
                    st.session_state.authenticated_user["full_name"] = edit_name.strip()
                    st.session_state.authenticated_user["display_name"] = edit_name.strip()
                    st.session_state.authenticated_user["department"] = edit_dept.strip()
                st.success("Profile details updated successfully!")
                time.sleep(0.5)
                st.rerun()

        st.markdown("#### 🔔 Notification Preferences")
        st.checkbox("Email confirmation after booking", value=True, key="notif_email")
        st.checkbox("Calendar invitation attachment (.ics)", value=True, key="notif_ics")

    with col_set2:
        st.markdown("#### 🖥️ System Health & Diagnostics")
        st.caption("Technical infrastructure metrics:")
        st.markdown(
            clean_html(f"""
            <div class="content-card" style="font-size: 0.88rem;">
                <p style="margin-bottom: 0.4rem;"><b>User ID:</b> <code>{user_id}</code></p>
                <p style="margin-bottom: 0.4rem;"><b>Active Identity:</b> <code>{student_name}</code> ({account_type})</p>
                <p style="margin-bottom: 0.4rem;"><b>FastAPI Backend:</b> <code>{BACKEND_URL}</code> ({'ONLINE' if backend_online else 'OFFLINE'})</p>
                <p style="margin-bottom: 0.4rem;"><b>Database Store:</b> <code>data/campus.db</code> (SQLite)</p>
                <p style="margin-bottom: 0.4rem;"><b>AI Engine:</b> <code>Gemini-Powered AI Campus Assistant</code></p>
                <p style="margin-bottom: 0.4rem;"><b>Timezone:</b> <code>Asia/Kolkata (IST)</code></p>
                <p style="margin-bottom: 0.4rem;"><b>Theme:</b> <code>Light Mode (Permanent)</code></p>
                <p style="margin-bottom: 0.4rem;"><b>Email Dispatch:</b> <code>{'Gmail SMTP Active' if is_smtp_configured() else 'Simulated / Ready'}</code></p>
            </div>
            """),
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height: 0.6rem;'></div>", unsafe_allow_html=True)
        if st.button("🚪 Sign Out of CampusPilot", type="secondary", use_container_width=True, key="settings_logout_btn"):
            st.session_state.authenticated_user = None
            st.session_state.current_page = None
            st.session_state.messages = []
            st.session_state.langchain_history = []
            st.session_state.pending_booking = None
            st.rerun()
