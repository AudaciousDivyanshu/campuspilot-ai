"""CampusPilot AI - Streamlit Web Frontend.

A clean, beginner-friendly web interface for the college demonstration:
- Real-time conversation with the LangChain Agent.
- Student profile input (Student ID, Name).
- Live backend connection status and campus laboratory directory.
- Transparent "Agent Activity & Tool Observation" expander.
- Robust Human-in-the-Loop "Confirm Booking" action button using structured pending booking state.
"""

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
from app.tools.date_utils import resolve_relative_dates_in_text

# Configuration
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

# Streamlit Page Config
st.set_page_config(
    page_title="CampusPilot AI - Campus Assistant",
    page_icon="🎓",
    layout="wide",
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
                "👋 Hello! I am **CampusPilot AI**, your college assistant for laboratory bookings.\n\n"
                "You can ask me to:\n"
                "- **List laboratories** on campus\n"
                "- **Check availability** for a specific date and time (e.g. *tomorrow from 10 AM to 12 PM*)\n"
                "- **Book a laboratory slot** (I will check availability and show a confirmation button before booking!)"
            ),
            "steps": [],
        }
    ]

if "langchain_history" not in st.session_state:
    st.session_state.langchain_history = []

if "pending_booking" not in st.session_state:
    st.session_state.pending_booking = None


# ==========================================
# SIDEBAR: Student Credentials & System Status
# ==========================================
with st.sidebar:
    st.header("🎓 Student Profile")
    student_name = st.text_input(
        "Student Name",
        value=st.session_state.get("student_name", "Aarav Sharma"),
        help="Your full name as recorded in college records",
    )
    student_id = st.text_input(
        "Student ID / Roll No",
        value=st.session_state.get("student_id", "CS2026-042"),
        help="Your unique college student roll number",
    )
    st.session_state["student_name"] = student_name
    st.session_state["student_id"] = student_id

    st.divider()

    st.subheader("🖥️ System Status")
    is_backend_online = check_backend_status()
    if is_backend_online:
        st.success(f"FastAPI Backend: **Online** ({BACKEND_URL})")
    else:
        st.error(f"FastAPI Backend: **Offline**\nRun: `uvicorn app.main:app --reload`")

    st.divider()

    st.subheader("🏛️ Campus Laboratories")
    labs = fetch_laboratories()
    if labs:
        for lab in labs:
            st.markdown(
                f"- **{lab['lab_name']}** (ID: `{lab['lab_id']}`)\n"
                f"  *Cap: {lab['capacity']} | Loc: {lab.get('location', 'N/A')}*"
            )
    else:
        st.caption("No laboratories loaded. Check if backend is running.")

    st.divider()

    if st.button("🔄 Reset Conversation", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Conversation reset. How can I help you today?",
                "steps": [],
            }
        ]
        st.session_state.langchain_history = []
        st.session_state.pending_booking = None
        st.rerun()


# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("🎓 CampusPilot AI")
st.caption(
    "Agentic AI Assistant for Multi-Step Campus Service Workflows • Built with FastAPI, SQLite, LangChain & Gemini"
)

# Display existing chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Display expandable tool trace if the agent executed actions in this turn
        if msg.get("steps"):
            with st.expander(f"🔍 Agent Activity & Tool Calls ({len(msg['steps'])} executed)", expanded=False):
                for idx, step in enumerate(msg["steps"], 1):
                    st.markdown(f"**Step {idx}: Called Tool `{step['tool']}`**")
                    st.json(step["args"])
                    st.markdown(f"**Tool Observation:**")
                    st.info(step["observation"])


# Finalize booking creation directly through backend
def confirm_pending_booking():
    """Execute confirmed booking creation and clear pending state."""
    pending = st.session_state.pending_booking
    if not pending:
        return

    # Immediately clear pending state to prevent duplicate submissions on rerun
    st.session_state.pending_booking = None

    with st.spinner("Connecting to FastAPI backend to finalize your confirmed booking..."):
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
    # Check if user typed a confirmation while a pending booking is active
    lower_input = user_text.strip().lower()
    if st.session_state.pending_booking and lower_input in ("confirm", "yes", "proceed", "go ahead", "confirm booking"):
        confirm_pending_booking()
        return

    if st.session_state.pending_booking and lower_input in ("cancel", "no", "stop"):
        st.session_state.pending_booking = None
        cancel_text = "Booking request was cancelled."
        st.session_state.messages.append({"role": "assistant", "content": cancel_text, "steps": []})
        st.session_state.langchain_history.append(AIMessage(content=cancel_text))
        return

    # Pre-anchor relative date terms (e.g. 'tomorrow' -> '2026-11-16 (tomorrow)')
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
        with st.spinner("CampusPilot AI is reasoning and executing tools..."):
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
            # Update student details with latest inputs from sidebar
            pending = result["pending_booking"]
            pending["student_id"] = student_ctx["student_id"]
            pending["student_name"] = student_ctx["student_name"]
            st.session_state.pending_booking = pending
        else:
            # Slot is occupied, not checked, or already booked
            st.session_state.pending_booking = None

    except Exception as e:
        st.error(f"Error running agent: {str(e)}")


# ==========================================
# CONFIRM BOOKING ACTION CARD
# Displayed only when an availability check succeeded and slot is available
# ==========================================
if st.session_state.pending_booking:
    pending = st.session_state.pending_booking
    st.markdown("---")
    st.success("### 🗓️ Slot Available — Confirm Your Booking")
    st.markdown(
        f"- **Laboratory:** **{pending['lab_name']}** (Lab ID: `{pending['lab_id']}`)\n"
        f"- **Date:** `{pending['booking_date']}`\n"
        f"- **Time:** `{pending['start_time']}` to `{pending['end_time']}`\n"
        f"- **Student:** **{pending['student_name']}** (ID: `{pending['student_id']}`)"
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("✅ Confirm Booking", type="primary", use_container_width=True, key="btn_confirm_booking"):
            confirm_pending_booking()
            st.rerun()

    with col2:
        if st.button("❌ Cancel Request", use_container_width=True, key="btn_cancel_booking"):
            st.session_state.pending_booking = None
            cancel_msg = "Booking request was cancelled."
            st.session_state.messages.append({"role": "assistant", "content": cancel_msg, "steps": []})
            st.session_state.langchain_history.append(AIMessage(content=cancel_msg))
            st.rerun()


# User Chat Input
if prompt := st.chat_input("E.g., 'Check whether AI Lab is available tomorrow from 10:00 AM to 12:00 PM'"):
    process_user_input(prompt)
    st.rerun()
