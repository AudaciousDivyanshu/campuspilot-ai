"""CampusPilot AI - Intelligent Multi-Service Campus Assistant.

Modern AI Campus Management Dashboard built with Streamlit:
- Professional light theme with deep navy and vibrant blue accents.
- Header with branding, subtitle ("Your Intelligent Campus Assistant"), and live backend status.
- Campus facilities directory for both Laboratories and Library Discussion Rooms.
- Quick action service cards with "Coming Soon" badges for future campus integrations.
- Agentic ReAct conversation flow with compact tool execution inspector.
- Human-in-the-Loop booking confirmation card preventing duplicate submissions on reruns.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
import requests
import streamlit as st

# Add project root to sys.path so app packages are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.booking_agent import CampusBookingAgent
from app.tools.campus_tools import create_lab_booking, create_room_reservation
from app.tools.date_utils import get_current_date_context, resolve_relative_dates_in_text

# Configuration
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

# Streamlit Page Configuration
st.set_page_config(
    page_title="CampusPilot AI — Campus Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Professional SaaS Light Dashboard Theme
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Top App Header Styling */
    .brand-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.1rem 1.5rem;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        margin-bottom: 1.2rem;
    }
    
    .brand-title {
        font-size: 1.45rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    
    .brand-subtitle {
        font-size: 0.86rem;
        color: #64748b;
        margin-top: 0.2rem;
        margin-bottom: 0;
    }
    
    .status-badge-online {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.35rem 0.8rem;
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 9999px;
        color: #166534;
        font-size: 0.82rem;
        font-weight: 600;
    }
    
    .status-badge-offline {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.35rem 0.8rem;
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 9999px;
        color: #991b1b;
        font-size: 0.82rem;
        font-weight: 600;
    }

    /* Facility Information Cards in Sidebar */
    .facility-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.75rem 0.85rem;
        margin-bottom: 0.65rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
        transition: border-color 0.15s ease;
    }
    .facility-card:hover {
        border-color: #93c5fd;
    }
    .facility-card-title {
        font-size: 0.9rem;
        font-weight: 600;
        color: #1e3a8a;
        margin-bottom: 0.25rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .facility-card-badge {
        background: #eff6ff;
        color: #1d4ed8;
        padding: 0.12rem 0.45rem;
        border-radius: 5px;
        font-size: 0.72rem;
        font-weight: 600;
    }
    .facility-card-detail {
        font-size: 0.78rem;
        color: #64748b;
        margin: 0.1rem 0;
    }

    /* Dashboard Action Cards */
    .service-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .service-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 10px rgba(15, 23, 42, 0.07);
    }
    .service-card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.4rem;
    }
    .service-card-title {
        font-size: 0.98rem;
        font-weight: 600;
        color: #0f172a;
    }
    .service-card-desc {
        font-size: 0.82rem;
        color: #64748b;
        margin-bottom: 0.75rem;
    }
    .badge-active {
        background: #ecfdf5;
        color: #047857;
        font-size: 0.7rem;
        font-weight: 600;
        padding: 0.2rem 0.5rem;
        border-radius: 9999px;
        border: 1px solid #a7f3d0;
    }
    .badge-coming-soon {
        background: #f1f5f9;
        color: #64748b;
        font-size: 0.7rem;
        font-weight: 600;
        padding: 0.2rem 0.5rem;
        border-radius: 9999px;
        border: 1px solid #cbd5e1;
    }

    /* Booking Confirmation Card */
    .booking-card {
        background: #ffffff;
        border: 2px solid #2563eb;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
        margin: 1.2rem 0;
    }
    .booking-card-header {
        font-size: 1.08rem;
        font-weight: 700;
        color: #1e3a8a;
        margin-bottom: 0.85rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .booking-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.75rem;
        margin-bottom: 1.1rem;
    }
    .booking-item {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
    }
    .booking-item-label {
        font-size: 0.72rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .booking-item-value {
        font-size: 0.92rem;
        font-weight: 600;
        color: #0f172a;
        margin-top: 0.15rem;
    }

    /* Compact Tool Inspector */
    .tool-step-header {
        font-size: 0.85rem;
        font-weight: 600;
        color: #334155;
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin-bottom: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# Helper: Check FastAPI backend status
def check_backend_status() -> bool:
    try:
        res = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return res.status_code == 200
    except requests.RequestException:
        return False


# Helper: Fetch laboratories list from backend
def fetch_laboratories() -> list:
    try:
        res = requests.get(f"{BACKEND_URL}/labs", timeout=2)
        if res.status_code == 200:
            return res.json()
    except requests.RequestException:
        pass
    return []


# Helper: Fetch library discussion rooms from backend
def fetch_discussion_rooms() -> list:
    try:
        res = requests.get(f"{BACKEND_URL}/rooms", timeout=2)
        if res.status_code == 200:
            return res.json()
    except requests.RequestException:
        pass
    return []


# Initialize Agent in Session State
@st.cache_resource
def get_agent() -> CampusBookingAgent:
    return CampusBookingAgent()


# Initialize Session State Variables
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **Welcome to CampusPilot AI!**\n\n"
                "I am your agentic assistant for campus services. I can assist you with:\n"
                "• **Laboratory Bookings**: Computer Lab 1, AI Lab, Networking Lab.\n"
                "• **Library Discussion Rooms**: Group study & discussion rooms 1 to 3.\n"
                "• **Availability Checking**: Inquire about live slots for today, tomorrow, or specific dates.\n"
                "• **Confirmed Reservations**: Safe two-step reservation with explicit confirmation."
            ),
            "steps": [],
        }
    ]

if "langchain_history" not in st.session_state:
    st.session_state.langchain_history = []

if "pending_booking" not in st.session_state:
    st.session_state.pending_booking = None


# ==========================================
# SIDEBAR: Profile & Facilities Directory
# ==========================================
with st.sidebar:
    st.markdown("### 👤 Student Profile")
    st.caption("Active credentials attached to reservation requests")

    student_name = st.text_input(
        "Full Name",
        value=st.session_state.get("student_name", "Aarav Sharma"),
        placeholder="e.g. Aarav Sharma",
    )
    student_id = st.text_input(
        "Student ID / Roll No",
        value=st.session_state.get("student_id", "CS2026-042"),
        placeholder="e.g. CS2026-042",
    )
    st.session_state["student_name"] = student_name
    st.session_state["student_id"] = student_id

    st.markdown("---")

    # Backend Connection Status
    st.markdown("### 🔌 System Connectivity")
    is_online = check_backend_status()
    if is_online:
        st.markdown(
            '<div class="status-badge-online">● Backend API Connected (Port 8000)</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-badge-offline">● Backend Offline (Check Uvicorn)</div>',
            unsafe_allow_html=True,
        )
        st.caption("Run: `uvicorn app.main:app --reload`")

    st.markdown("---")

    # Campus Facilities Directory Navigation
    st.markdown("### 🏛️ Campus Facilities")
    facility_tab = st.radio(
        "Browse Directory:",
        ["Laboratories", "Library Rooms"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if facility_tab == "Laboratories":
        labs = fetch_laboratories()
        if labs:
            lab_icons = {1: "💻", 2: "🤖", 3: "🌐"}
            for lab in labs:
                icon = lab_icons.get(lab["lab_id"], "🔬")
                st.markdown(
                    f"""
                    <div class="facility-card">
                        <div class="facility-card-title">
                            <span>{icon} {lab['lab_name']}</span>
                            <span class="facility-card-badge">ID: {lab['lab_id']}</span>
                        </div>
                        <div class="facility-card-detail">👥 Capacity: <b>{lab['capacity']} workstations</b></div>
                        <div class="facility-card-detail">📍 Location: <b>{lab.get('location', 'Main Block')}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No laboratory data available. Ensure backend is active.")

    else:
        rooms = fetch_discussion_rooms()
        if rooms:
            room_icons = {1: "📖", 2: "👥", 3: "💡"}
            for room in rooms:
                icon = room_icons.get(room["room_id"], "📚")
                st.markdown(
                    f"""
                    <div class="facility-card">
                        <div class="facility-card-title">
                            <span>{icon} {room['room_name']}</span>
                            <span class="facility-card-badge">ID: {room['room_id']}</span>
                        </div>
                        <div class="facility-card-detail">👥 Capacity: <b>{room['capacity']} persons</b></div>
                        <div class="facility-card-detail">📍 Location: <b>{room.get('location', 'Library')}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No discussion room data available. Ensure backend is active.")

    st.markdown("---")

    # Reset Conversation Button
    if st.button("🔄 Reset Conversation", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Conversation reset. How can I assist you with campus facilities today?",
                "steps": [],
            }
        ]
        st.session_state.langchain_history = []
        st.session_state.pending_booking = None
        st.rerun()


# ==========================================
# MAIN INTERFACE: Brand Header
# ==========================================
status_html = (
    '<span class="status-badge-online">🟢 System Online</span>'
    if is_online
    else '<span class="status-badge-offline">🔴 System Offline</span>'
)

st.markdown(
    f"""
    <div class="brand-header">
        <div>
            <h1 class="brand-title">🎓 CampusPilot AI</h1>
            <p class="brand-subtitle">Your Intelligent Campus Assistant for Multi-Step Workflows</p>
        </div>
        <div>
            {status_html}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# Helper: Execute confirmed booking or reservation
def confirm_pending_booking():
    """Execute confirmed reservation and clear pending state to prevent duplicates."""
    pending = st.session_state.pending_booking
    if not pending:
        return

    # Immediately clear pending state to prevent duplicate submissions on rerun
    st.session_state.pending_booking = None
    service_type = pending.get("service_type", "lab")

    with st.spinner("Confirming reservation with the campus database..."):
        try:
            if service_type == "room":
                res_output = create_room_reservation.invoke({
                    "student_id": pending["student_id"],
                    "student_name": pending["student_name"],
                    "room_id": int(pending["item_id"]),
                    "booking_date": pending["booking_date"],
                    "start_time": pending["start_time"],
                    "end_time": pending["end_time"],
                })
                tool_used = "create_room_reservation"
            else:
                res_output = create_lab_booking.invoke({
                    "student_id": pending["student_id"],
                    "student_name": pending["student_name"],
                    "lab_id": int(pending["item_id"]),
                    "booking_date": pending["booking_date"],
                    "start_time": pending["start_time"],
                    "end_time": pending["end_time"],
                })
                tool_used = "create_lab_booking"

            # Append successful booking result to chat
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
                }
            )
            st.session_state.langchain_history.append(AIMessage(content=res_output))
        except Exception as e:
            err_msg = f"Failed to confirm reservation: {str(e)}"
            st.session_state.messages.append({"role": "assistant", "content": err_msg, "steps": []})
            st.session_state.langchain_history.append(AIMessage(content=err_msg))


# Processing user message through Agent
def process_user_input(user_text: str):
    lower_input = user_text.strip().lower()

    # Handle confirmation or cancellation via chat text
    if st.session_state.pending_booking and lower_input in ("confirm", "yes", "proceed", "go ahead", "confirm booking", "confirm reservation"):
        confirm_pending_booking()
        return

    if st.session_state.pending_booking and lower_input in ("cancel", "no", "stop"):
        st.session_state.pending_booking = None
        cancel_text = "The pending reservation request has been cancelled."
        st.session_state.messages.append({"role": "assistant", "content": cancel_text, "steps": []})
        st.session_state.langchain_history.append(AIMessage(content=cancel_text))
        return

    # Pre-anchor relative date terms (e.g. 'tomorrow' -> 'YYYY-MM-DD (tomorrow)')
    anchored_text = resolve_relative_dates_in_text(user_text)

    # Append to UI and LangChain history
    st.session_state.messages.append({"role": "user", "content": user_text, "steps": []})
    st.session_state.langchain_history.append(HumanMessage(content=anchored_text))

    student_ctx = {
        "student_name": st.session_state.get("student_name", "Student"),
        "student_id": st.session_state.get("student_id", "Unknown"),
    }

    try:
        agent = get_agent()
        with st.spinner("CampusPilot AI is analyzing request and checking campus tools..."):
            result = agent.run(
                messages=st.session_state.langchain_history,
                student_context=student_ctx,
            )

        assistant_text = result["response"]
        steps = result["steps"]

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": assistant_text,
                "steps": steps,
            }
        )
        st.session_state.langchain_history.append(AIMessage(content=assistant_text))

        # Update structured pending booking state
        if result.get("pending_booking"):
            pending = result["pending_booking"]
            pending["student_id"] = student_ctx["student_id"]
            pending["student_name"] = student_ctx["student_name"]
            st.session_state.pending_booking = pending
        else:
            st.session_state.pending_booking = None

    except Exception as e:
        st.error(f"Error executing agent: {str(e)}")


# ==========================================
# MAIN DASHBOARD: Quick Action Service Cards
# ==========================================
col_s1, col_s2, col_s3, col_s4 = st.columns(4)

with col_s1:
    st.markdown(
        """
        <div class="service-card">
            <div>
                <div class="service-card-header">
                    <span class="service-card-title">💻 Laboratories</span>
                    <span class="badge-active">Active</span>
                </div>
                <div class="service-card-desc">Check availability and book AI, Computer, or Networking labs.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Check Labs", key="btn_service_labs", use_container_width=True):
        process_user_input("What laboratories are available on campus?")
        st.rerun()

with col_s2:
    st.markdown(
        """
        <div class="service-card">
            <div>
                <div class="service-card-header">
                    <span class="service-card-title">📚 Library Rooms</span>
                    <span class="badge-active">Active</span>
                </div>
                <div class="service-card-desc">Reserve group study and collaborative discussion rooms.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Check Rooms", key="btn_service_rooms", use_container_width=True):
        process_user_input("What library discussion rooms are available?")
        st.rerun()

with col_s3:
    st.markdown(
        """
        <div class="service-card">
            <div>
                <div class="service-card-header">
                    <span class="service-card-title">🏛️ Seminar Hall</span>
                    <span class="badge-coming-soon">Coming Soon</span>
                </div>
                <div class="service-card-desc">Departmental lectures, guest seminars, and symposiums.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button("Unavailable", key="btn_service_seminar", disabled=True, use_container_width=True)

with col_s4:
    st.markdown(
        """
        <div class="service-card">
            <div>
                <div class="service-card-header">
                    <span class="service-card-title">⚽ Sports Facility</span>
                    <span class="badge-coming-soon">Coming Soon</span>
                </div>
                <div class="service-card-desc">Badminton, basketball courts, and equipment checkout.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button("Unavailable", key="btn_service_sports", disabled=True, use_container_width=True)

st.markdown("---")

# Quick Example Prompt Chips
st.markdown("**💡 Suggested Inquiries:**")
col_p1, col_p2, col_p3, col_p4 = st.columns(4)

with col_p1:
    if st.button("🔍 Check AI Lab Tomorrow", use_container_width=True):
        process_user_input("Check whether AI Lab is available tomorrow from 10:00 AM to 12:00 PM.")
        st.rerun()

with col_p2:
    if st.button("📖 Check Discussion Room 2", use_container_width=True):
        process_user_input("Is Discussion Room 2 available tomorrow from 2:00 PM to 4:00 PM?")
        st.rerun()

with col_p3:
    if st.button("📅 Book Discussion Room 1", use_container_width=True):
        process_user_input("I want to book Discussion Room 1 tomorrow from 10:00 AM to 12:00 PM.")
        st.rerun()

with col_p4:
    if st.button("📋 List All Library Rooms", use_container_width=True):
        process_user_input("List all discussion rooms in the library.")
        st.rerun()

st.markdown("---")

# Display Conversation History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Compact Tool Activity Inspector
        if msg.get("steps"):
            with st.expander(f"🛠️ Agent Execution Inspector ({len(msg['steps'])} tool steps)", expanded=False):
                for idx, step in enumerate(msg["steps"], 1):
                    tool_name = step.get("tool", "unknown_tool")
                    obs = str(step.get("observation", ""))
                    is_success = not ("error" in obs.lower() or "rejected" in obs.lower() or "unavailable" in obs.lower())
                    status_icon = "✅" if is_success else "ℹ️"

                    st.markdown(f"**Step {idx}: {status_icon} Executed Tool `{tool_name}`**")
                    col_args, col_obs = st.columns([1, 1])
                    with col_args:
                        st.caption("Tool Arguments:")
                        st.json(step.get("args", {}))
                    with col_obs:
                        st.caption("Tool Observation:")
                        if is_success:
                            st.success(obs)
                        else:
                            st.info(obs)
                    st.markdown("---")


# ==========================================
# CONFIRM RESERVATION ACTION CARD
# Displayed only when an availability check succeeded
# ==========================================
if st.session_state.pending_booking:
    pending = st.session_state.pending_booking
    is_room = pending.get("service_type") == "room"
    facility_type_title = "Library Discussion Room" if is_room else "Campus Laboratory"
    facility_icon = "📚" if is_room else "💻"

    st.markdown(
        f"""
        <div class="booking-card">
            <div class="booking-card-header">
                <span>{facility_icon} Slot Available — Confirm Your Reservation</span>
                <span class="badge-active">{facility_type_title}</span>
            </div>
            <div class="booking-grid">
                <div class="booking-item">
                    <div class="booking-item-label">Facility</div>
                    <div class="booking-item-value">{pending.get('item_name', pending.get('lab_name'))} (ID: {pending.get('item_id', pending.get('lab_id'))})</div>
                </div>
                <div class="booking-item">
                    <div class="booking-item-label">Date (Asia/Kolkata)</div>
                    <div class="booking-item-value">{pending['booking_date']}</div>
                </div>
                <div class="booking-item">
                    <div class="booking-item-label">Time Slot</div>
                    <div class="booking-item-value">{pending['start_time']} to {pending['end_time']}</div>
                </div>
                <div class="booking-item">
                    <div class="booking-item-label">Student Details</div>
                    <div class="booking-item-value">{pending['student_name']} ({pending['student_id']})</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_c1, col_c2 = st.columns([1, 1])
    with col_c1:
        if st.button("✅ Confirm Reservation", type="primary", use_container_width=True, key="btn_confirm_action"):
            confirm_pending_booking()
            st.rerun()

    with col_c2:
        if st.button("❌ Cancel Request", use_container_width=True, key="btn_cancel_action"):
            st.session_state.pending_booking = None
            cancel_msg = "The pending reservation request was cancelled."
            st.session_state.messages.append({"role": "assistant", "content": cancel_msg, "steps": []})
            st.session_state.langchain_history.append(AIMessage(content=cancel_msg))
            st.rerun()


# User Chat Input
if prompt := st.chat_input("Ask a question or request a booking (e.g. 'Is Discussion Room 2 free tomorrow 2-4 PM?')..."):
    process_user_input(prompt)
    st.rerun()
