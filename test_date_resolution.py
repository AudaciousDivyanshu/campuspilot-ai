"""Verification test for relative and natural-language date resolution.

Verifies:
1. Pure Python unit tests for `resolve_date_string` (today, tomorrow, day after tomorrow, explicit dates).
2. Live Agent test with user query:
   'Check whether AI Lab is available tomorrow from 10:00 AM to 12:00 PM.'
3. Live Agent test with user query:
   'Is Computer Lab 1 available day after tomorrow from 14:00 to 16:00?'
4. Live Agent test with explicit natural-language date:
   'Check if Networking Lab is available on 20 November 2026 from 10:00 to 12:00.'

Note: None of these tests create real bookings.
"""

from datetime import datetime, timedelta
import os
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

from langchain_core.messages import HumanMessage
from app.agent.booking_agent import CampusBookingAgent
from app.tools.date_utils import get_current_date_context, resolve_date_string


def test_unit_date_resolution():
    print("=" * 65, flush=True)
    print(" [Part 1] Unit Testing resolve_date_string (Python Logic)", flush=True)
    print("=" * 65, flush=True)

    kolkata = ZoneInfo("Asia/Kolkata")
    now = datetime.now(kolkata)
    expected_today = now.date().strftime("%Y-%m-%d")
    expected_tomorrow = (now.date() + timedelta(days=1)).strftime("%Y-%m-%d")
    expected_day_after = (now.date() + timedelta(days=2)).strftime("%Y-%m-%d")

    print(f" Current Asia/Kolkata Datetime : {now.strftime('%Y-%m-%d %H:%M:%S %Z')}", flush=True)
    print(f" Expected 'today'              : {expected_today}", flush=True)
    print(f" Expected 'tomorrow'           : {expected_tomorrow}", flush=True)
    print(f" Expected 'day after tomorrow' : {expected_day_after}", flush=True)

    # Test cases
    cases = [
        ("today", expected_today),
        ("tomorrow", expected_tomorrow),
        ("day after tomorrow", expected_day_after),
        ("20 November 2026", "2026-11-20"),
        ("20th Nov 2026", "2026-11-20"),
        ("November 20, 2026", "2026-11-20"),
        ("2026-11-20", "2026-11-20"),
    ]

    for raw, expected in cases:
        result = resolve_date_string(raw)
        print(f"   ✓ Input: '{raw:22}' -> Resolved: '{result}'", flush=True)
        assert result == expected, f"Failed for {raw}: got {result}, expected {expected}"

    print(" PASS: All unit date conversions succeeded.\n", flush=True)


def test_live_agent_date_resolution():
    print("=" * 65, flush=True)
    print(" [Part 2] Live Agent Tool Argument Date Verification", flush=True)
    print("=" * 65, flush=True)

    date_ctx = get_current_date_context()
    expected_tomorrow = date_ctx["tomorrow"]
    expected_day_after = date_ctx["day_after_tomorrow"]

    # Start FastAPI server subprocess
    print("Launching FastAPI server subprocess...", flush=True)
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)

    try:
        agent = CampusBookingAgent()
        print(f"Agent loaded using model: {agent.model_name}", flush=True)

        # -------------------------------------------------------------
        # TEST 1: The exact user scenario for "tomorrow"
        # -------------------------------------------------------------
        user_query_tomorrow = "Check whether AI Lab is available tomorrow from 10:00 AM to 12:00 PM."
        print(f"\n--- Testing Query 1: '{user_query_tomorrow}' ---", flush=True)
        res1 = agent.run([HumanMessage(content=user_query_tomorrow)])

        print("\nAgent Steps / Tool Invocations:", flush=True)
        found_check_tool = False
        for step in res1["steps"]:
            print(f"Tool Name: {step['tool']}", flush=True)
            print(f"Exact Tool Arguments Generated: {step['args']}", flush=True)
            print(f"Observation: {step['observation']}", flush=True)

            if step["tool"] == "check_lab_availability":
                found_check_tool = True
                actual_date = step["args"].get("booking_date")
                print(f"\n>> Target Tool: check_lab_availability", flush=True)
                print(f">> Generated booking_date : '{actual_date}'", flush=True)
                print(f">> Expected booking_date  : '{expected_tomorrow}'", flush=True)
                assert actual_date == expected_tomorrow, (
                    f"Date mismatch! Got '{actual_date}', expected '{expected_tomorrow}'"
                )

        assert found_check_tool, "Agent did not invoke check_lab_availability"
        print(" PASS: 'tomorrow' correctly resolved to Asia/Kolkata date!", flush=True)

        # -------------------------------------------------------------
        # TEST 2: "day after tomorrow"
        # -------------------------------------------------------------
        user_query_day_after = "Is Computer Lab 1 available day after tomorrow from 14:00 to 16:00?"
        print(f"\n--- Testing Query 2: '{user_query_day_after}' ---", flush=True)
        res2 = agent.run([HumanMessage(content=user_query_day_after)])

        for step in res2["steps"]:
            if step["tool"] == "check_lab_availability":
                actual_date = step["args"].get("booking_date")
                print(f"Exact Tool Arguments Generated: {step['args']}", flush=True)
                assert actual_date == expected_day_after, (
                    f"Date mismatch! Got '{actual_date}', expected '{expected_day_after}'"
                )
        print(" PASS: 'day after tomorrow' correctly resolved!", flush=True)

        # -------------------------------------------------------------
        # TEST 3: Explicit natural language date "20 November 2026"
        # -------------------------------------------------------------
        user_query_explicit = "Check if Networking Lab is available on 20 November 2026 from 10:00 to 12:00."
        print(f"\n--- Testing Query 3: '{user_query_explicit}' ---", flush=True)
        res3 = agent.run([HumanMessage(content=user_query_explicit)])

        for step in res3["steps"]:
            if step["tool"] == "check_lab_availability":
                actual_date = step["args"].get("booking_date")
                print(f"Exact Tool Arguments Generated: {step['args']}", flush=True)
                assert actual_date == "2026-11-20", (
                    f"Date mismatch! Got '{actual_date}', expected '2026-11-20'"
                )
        print(" PASS: '20 November 2026' correctly resolved to '2026-11-20'!", flush=True)

        print("\n" + "=" * 65, flush=True)
        print(" ALL RELATIVE-DATE RESOLUTION TESTS PASSED!", flush=True)
        print("=" * 65, flush=True)

    finally:
        server_process.terminate()
        server_process.wait()


if __name__ == "__main__":
    test_unit_date_resolution()
    test_live_agent_date_resolution()
