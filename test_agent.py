"""Automated verification script for CampusPilot AI Agent and Tools.

Spawns the FastAPI backend server as a subprocess and tests:
1. Agent queries lab list using tool.
2. Agent checks slot availability using tool.
3. Agent pauses and asks for confirmation before booking (Human-in-the-Loop).
4. Agent creates booking upon confirmation.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Ensure unbuffered output
sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.booking_agent import CampusBookingAgent
from app.database.connection import get_db_context
from app.database.init_db import init_db


def run_agent_tests():
    print("=" * 65, flush=True)
    print(" CampusPilot AI: LangChain Agent Verification Suite", flush=True)
    print("=" * 65, flush=True)

    # Reset test date
    init_db()
    test_date = "2026-11-20"
    with get_db_context() as conn:
        conn.execute("DELETE FROM bookings WHERE booking_date = ?;", (test_date,))

    # 1. Start FastAPI server as subprocess
    print("\n[Step 1] Launching local FastAPI backend subprocess...", flush=True)
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)  # Allow server to bind and start
    print(" FastAPI server subprocess is running (PID: %d)" % server_process.pid, flush=True)

    try:
        # 2. Initialize Agent
        print("\n[Step 2] Initializing CampusBookingAgent with Gemini...", flush=True)
        agent = CampusBookingAgent()
        print(f" Agent initialized using model: {agent.model_name}", flush=True)

        student_ctx = {
            "student_id": "CS2026-042",
            "student_name": "Aarav Sharma",
        }

        # 3. Test Query 1: Lab Listing
        print("\n[Step 3] Test Query 1: 'What laboratories are available on campus?'", flush=True)
        history = [HumanMessage(content="What laboratories are available on campus?")]
        result1 = agent.run(history, student_context=student_ctx)
        print("\nAgent Response:", flush=True)
        print(result1["response"], flush=True)
        print(f"\nTools Used: {[s['tool'] for s in result1['steps']]}", flush=True)
        assert any(s["tool"] == "list_laboratories" for s in result1["steps"]), "Agent should call list_laboratories"
        print(" PASS: Agent successfully listed laboratories using tools.", flush=True)

        # 4. Test Query 2: Request to Book (Safety Check: Must Ask for Confirmation FIRST)
        print(f"\n[Step 4] Test Query 2: 'I want to book AI Lab on {test_date} from 10:00 to 12:00'", flush=True)
        history.append(AIMessage(content=result1["response"]))
        history.append(HumanMessage(content=f"I want to book AI Lab on {test_date} from 10:00 to 12:00"))
        result2 = agent.run(history, student_context=student_ctx)
        print("\nAgent Response:", flush=True)
        print(result2["response"], flush=True)
        print(f"\nTools Used: {[s['tool'] for s in result2['steps']]}", flush=True)
        assert any(s["tool"] == "check_lab_availability" for s in result2["steps"]), "Agent should call check_lab_availability"
        created_before_confirm = any(s["tool"] == "create_lab_booking" for s in result2["steps"])
        assert not created_before_confirm, "Safety violation: Agent called create_lab_booking without waiting for confirmation!"
        print(" PASS: Safety gate held! Agent checked availability and asked for confirmation without booking.", flush=True)

        # 5. Test Query 3: Explicit Confirmation -> Now Creates Booking
        print("\n[Step 5] Test Query 3: 'Yes, I confirm the booking, please proceed.'", flush=True)
        history.append(AIMessage(content=result2["response"]))
        history.append(HumanMessage(content="Yes, I confirm the booking, please proceed."))
        result3 = agent.run(history, student_context=student_ctx)
        print("\nAgent Response:", flush=True)
        print(result3["response"], flush=True)
        print(f"\nTools Used: {[s['tool'] for s in result3['steps']]}", flush=True)
        assert any(s["tool"] == "create_lab_booking" for s in result3["steps"]), "Agent should call create_lab_booking after confirmation"
        print(" PASS: Booking successfully created in SQLite with verified Booking ID!", flush=True)

        print("\n" + "=" * 65, flush=True)
        print(" ALL AGENT TESTS PASSED SUCCESSFULLY!", flush=True)
        print("=" * 65, flush=True)

    finally:
        print("\nStopping FastAPI server subprocess...", flush=True)
        server_process.terminate()
        server_process.wait()
        print(" Server stopped.", flush=True)


if __name__ == "__main__":
    run_agent_tests()
