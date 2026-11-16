"""CampusPilot AI - Modern SaaS Streamlit Web Frontend.

A polished, responsive interface for the college demonstration:
- Modern SaaS light theme with deep navy and vibrant blue accents.
- Header with branding, subtitle, and compact live status indicator.
- Sidebar with student profile inputs and individual laboratory cards.
- Quick prompt chips for common student queries.
- Styled student and AI chat message cards.
- Step-by-step Tool Execution Inspector with success/failure badges.
- Distinct Booking Confirmation Card with single-click execution.
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
from app.tools.campus_tools import create_lab_booking
from app.tools.date_utils import get_current_date_context, resolve_relative_dates_in_text

# Configuration
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

# Streamlit Page Configuration
st.set_page_config(
    page_title="CampusPilot AI — Campus Service Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished Light SaaS Theme
st.markdown(
    """
    <style>
    /* Global Styles */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Top App Header Styling */
    .brand-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.2rem 1.6rem;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 1.4rem;
    }
    
    .brand-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    
    .brand-subtitle {
        font-size: 0.88rem;
        color: #64748b;
        margin-top: 0.2rem;
        margin-bottom: 0;
    }
    
    .status-badge-online {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.35rem 0.75rem;
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
        gap: 0.4rem;
        padding: 0.35rem 0.75rem;
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 9999px;
        color: #991b1b;
        font-size: 0.82rem;
        font-weight: 600;
    }
    
    /* Laboratory Information Cards */
    .lab-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.85rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    
    .lab-card:hover {
        border-color: #93c5fd;
        transform: translateY(-1px);
    }
    
    .lab-card-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: #1e3a8a;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    .lab-card-badge {
        background: #eff6ff;
        color: #1d4ed8;
        padding: 0.15rem 0.45rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    
    .lab-card-detail {
        font-size: 0.8rem;
        color: #64748b;
        margin: 0.15rem 0;
    }
    
    /* Quick Prompt Chips */
    .chip-container {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-bottom: 1.2rem;
    }
    
    /* Tool Inspector Styling */
    .step-box {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
    }
    
    .step-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }
    
    /* Booking Confirmation Card */
    .booking-card {
        background: #ffffff;
        border: 2px solid #2563eb;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);
        margin: 1.2rem 0;
    }
    
    .booking-card-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1e3a8a;
        margin-bottom: 0.8rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .booking-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.8rem;
        margin-bottom: 1.2rem;
    }
    
    .booking-item {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
    }
    
    .booking-item-label {
        font-size: 0.74rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    
    .booking-item-value {
        font-size: 0.95rem;
        font-weight: 600;
        color: #0f172a;
        margin-top: 0.15rem;
    }
    
    /* Success Confirmation Card */
    .success-card {
        background: #f0fdf4;
        border: 1px solid #86efac;
        border-left: 5px solid #16a34a;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin: 0.8rem 0;
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


# Helper: Fetch laboratory list from backend
def fetch_laboratories() -> list:
    try:
        res = requests.get(f"{BACKEND_URL}/labs", timeout=2)
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
                "I am your agentic campus assistant for laboratory workflows. You can:\n"
                "• Inquire about available laboratories and their facilities.\n"
                "• Check real-time slot availability for specific dates and times.\n"
                "• Reserve a laboratory slot with interactive confirmation."
            ),
            "steps": [],
        }
    ]

if "langchain_history" not in st.session_state:
    st.session_state.langchain_history = []

if "pending_booking" not in st.session_state:
    st.session_state.pending_booking = None


# ==========================================
# SIDEBAR: Student Credentials & Labs Directory
# ==========================================
with st.sidebar:
    st.markdown("### 👤 Student Profile")
    st.caption("Information used when booking campus resources")

    student_name = st.text_input(
        "Full Name",
        value=st.session_state.get("student_name", "Aarav Sharma"),
        placeholder="Enter student name",
    )
    student_id = st.text_input(
        "Student ID / Roll No",
        value=st.session_state.get("student_id", "CS2026-042"),
        placeholder="Enter roll number",
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
        st.caption("Run: `uvicorn app.main:app --reload` in your terminal.")

    st.markdown("---")

    # Campus Laboratories Directory
    st.markdown("### 🏛️ Registered Laboratories")
    labs = fetch_laboratories()
    if labs:
        lab_icons = {1: "💻", 2: "🤖", 3: "🌐"}
        for lab in labs:
            icon = lab_icons.get(lab["lab_id"], "🔬")
            st.markdown(
                f"""
                <div class="lab-card">
                    <div class="lab-card-title">
                        <span>{icon} {lab['lab_name']}</span>
                        <span class="lab-card-badge">ID: {lab['lab_id']}</span>
                    </div>
                    <div class="lab-card-detail">👥 Capacity: <b>{lab['capacity']} seats</b></div>
                    <div class="lab-card-detail">📍 Location: <b>{lab.get('location', 'Main Block')}</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("Unable to load laboratories. Ensure the backend server is active.")

    st.markdown("---")

    # Reset Conversation Button
    if st.button("🔄 Reset Conversation", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Conversation reset. How can I assist you with laboratory bookings today?",
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
    '<span class="status-badge-online">🟢 Online</span>'
    if is_online
    else '<span class="status-badge-offline">🔴 Offline</span>'
)

st.markdown(
    f"""
    <div class="brand-header">
        <div>
            <h1 class="brand-title">🎓 CampusPilot AI</h1>
            <p class="brand-subtitle">Agentic AI Assistant for Multi-Step Campus Service Workflows</p>
        </div>
        <div>
            {status_html}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# Execute confirmed booking creation
def confirm_pending_booking():
    """Execute confirmed booking creation and clear pending state."""
    pending = st.session_state.pending_booking
    if not pending:
        return

    # Immediately clear pending state to prevent duplicate submissions on rerun
    st.session_state.pending_booking = None

    with st.spinner("Executing confirmed booking with the campus database..."):
        try:
            booking_res = create_lab_booking.invoke({
                "student_id": pending["student_id"],
                "student_name": pending["student_name"],
                "lab_id": int(pending["lab_id"]),
                "booking_date": pending["booking_date"],
                "start_time": pending["start_time"],
                "end_time": pending["end_time"],
            })

            # Append successful booking result to chat
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": booking_res,
                    "steps": [
                        {
                            "tool": "create_lab_booking",
                            "args": pending,
                            "observation": booking_res,
                        }
                    ],
                }
            )
            st.session_state.langchain_history.append(AIMessage(content=booking_res))
        except Exception as e:
            err_msg = f"Failed to confirm booking: {str(e)}"
            st.session_state.messages.append({"role": "assistant", "content": err_msg, "steps": []})
            st.session_state.langchain_history.append(AIMessage(content=err_msg))


# Processing user message through Agent
def process_user_input(user_text: str):
    # Handle user confirmation or cancellation via chat text
    lower_input = user_text.strip().lower()
    if st.session_state.pending_booking and lower_input in ("confirm", "yes", "proceed", "go ahead", "confirm booking"):
        confirm_pending_booking()
        return

    if st.session_state.pending_booking and lower_input in ("cancel", "no", "stop"):
        st.session_state.pending_booking = None
        cancel_text = "The pending booking request has been cancelled."
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


# Quick Prompt Chips
st.markdown("**💡 Quick Examples:**")
col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    if st.button("🏢 What labs are available?", use_container_width=True):
        process_user_input("What laboratories are available on campus?")
        st.rerun()
with col_p2:
    if st.button("🔍 Check AI Lab Tomorrow", use_container_width=True):
        process_user_input("Check whether AI Lab is available tomorrow from 10:00 AM to 12:00 PM.")
        st.rerun()
with col_p3:
    if st.button("📅 Book AI Lab Tomorrow (10-12)", use_container_width=True):
        process_user_input("I want to book AI Lab tomorrow from 10:00 AM to 12:00 PM.")
        st.rerun()

st.markdown("---")

# Display Conversation History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Tool Activity Inspector
        if msg.get("steps"):
            with st.expander(f"🛠️ Agent Execution Trace ({len(msg['steps'])} tool steps)", expanded=False):
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
# CONFIRM BOOKING ACTION CARD
# Displayed only when an availability check succeeded and slot is available
# ==========================================
if st.session_state.pending_booking:
    pending = st.session_state.pending_booking

    st.markdown(
        f"""
        <div class="booking-card">
            <div class="booking-card-header">
                <span>🗓️</span>
                <span>Slot Available — Confirm Your Booking</span>
            </div>
            <div class="booking-grid">
                <div class="booking-item">
                    <div class="booking-item-label">Laboratory</div>
                    <div class="booking-item-value">{pending['lab_name']} (ID: {pending['lab_id']})</div>
                </div>
                <div class="booking-item">
                    <div class="booking-item-label">Date (Asia/Kolkata)</div>
                    <div class="booking-item-value">{pending['booking_date']}</div>
                </div>
                <div class="booking-item">
                    <div class="booking-item-label">Time Interval</div>
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

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("✅ Confirm Booking", type="primary", use_container_width=True, key="btn_confirm_booking"):
            confirm_pending_booking()
            st.rerun()

    with col2:
        if st.button("❌ Cancel Request", use_container_width=True, key="btn_cancel_booking"):
            st.session_state.pending_booking = None
            cancel_msg = "The pending booking request was cancelled."
            st.session_state.messages.append({"role": "assistant", "content": cancel_msg, "steps": []})
            st.session_state.langchain_history.append(AIMessage(content=cancel_msg))
            st.rerun()


# User Chat Input
if prompt := st.chat_input("Ask a question or request a booking (e.g. 'Is AI Lab free tomorrow from 10 to 12?')..."):
    process_user_input(prompt)
    st.rerun()
