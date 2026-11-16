"""CampusPilot AI - LangChain Laboratory Booking Agent.

Implements an agentic ReAct / tool-calling workflow with Gemini and LangChain 1.x:
1. Dynamic Asia/Kolkata date anchoring (today, tomorrow, day after tomorrow).
2. Deterministic Python date resolution for relative and natural-language dates.
3. Structured extraction of pending bookings for frontend confirmation buttons.
4. Executes campus tools via FastAPI HTTP endpoints.
5. Strict Human-in-the-Loop safety: never books without explicit confirmation.
"""

import json
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.tools.campus_tools import (
    ALL_CAMPUS_TOOLS,
    check_lab_availability,
    check_room_availability,
    create_lab_booking,
    create_room_reservation,
    list_discussion_rooms,
    list_laboratories,
)
from app.tools.date_utils import (
    get_current_date_context,
    resolve_date_string,
    resolve_relative_dates_in_text,
)

load_dotenv()

LAB_NAMES = {
    1: "Computer Lab 1",
    2: "AI Lab",
    3: "Networking Lab",
}

ROOM_NAMES = {
    1: "Discussion Room 1",
    2: "Discussion Room 2",
    3: "Discussion Room 3",
}


def build_system_prompt(date_ctx: Dict[str, str], student_ctx: Optional[Dict[str, str]] = None) -> str:
    """Build a dynamic system prompt with real-time Asia/Kolkata dates and student context."""
    prompt = f"""You are CampusPilot AI, an intelligent, transparent campus assistant for multi-service campus workflows.
You assist students with two primary booking workflows:
1. Campus Laboratories (Computer Lab 1, AI Lab, Networking Lab)
2. Library Discussion Rooms (Discussion Room 1, Discussion Room 2, Discussion Room 3)

CURRENT DATE & TIME (Timezone: {date_ctx['timezone']}):
- Current Date (Today): {date_ctx['today']} ({date_ctx['today_human']})
- Tomorrow: {date_ctx['tomorrow']} ({date_ctx['tomorrow_human']})
- Day After Tomorrow: {date_ctx['day_after_tomorrow']} ({date_ctx['day_after_tomorrow_human']})

DATE HANDLING RULES:
1. RELATIVE DATES:
   - When the student mentions 'today', resolve the date strictly to '{date_ctx['today']}'.
   - When the student mentions 'tomorrow', resolve the date strictly to '{date_ctx['tomorrow']}'.
   - When the student mentions 'day after tomorrow', resolve the date strictly to '{date_ctx['day_after_tomorrow']}'.
2. EXPLICIT DATES:
   - Convert explicit dates (e.g. '20 November 2026', '20th Nov 2026') strictly into 'YYYY-MM-DD' format (e.g. '2026-11-20').
3. TOOL ARGUMENTS:
   - All tool calls taking `booking_date` MUST receive dates strictly in 'YYYY-MM-DD' format. Never guess or hallucinate arbitrary dates.

CRITICAL OPERATIONAL RULES:
1. SERVICE ROUTING & DISTINCTION:
   - If the student requests a Laboratory (e.g., 'lab', 'computer lab', 'AI lab', 'networking lab'):
     * Tools to use: `list_laboratories`, `check_lab_availability`, `create_lab_booking`.
   - If the student requests a Library Discussion Room (e.g., 'discussion room', 'library room', 'study room'):
     * Tools to use: `list_discussion_rooms`, `check_room_availability`, `create_room_reservation`.
   - Never mix up laboratory tools with library room tools.
2. USE TOOLS: Always use the provided tools to check actual data. Never guess or hallucinate IDs, availability, or booking IDs.
3. IDENTIFICATION:
   - Use `list_laboratories` to look up lab IDs.
   - Use `list_discussion_rooms` to look up discussion room IDs.
4. TIME FORMAT:
   - Times must be in 24-hour HH:MM format (e.g., 10:00 to 12:00, or convert '10:00 AM' -> '10:00', '2:00 PM' -> '14:00', '4:00 PM' -> '16:00').
5. HUMAN-IN-THE-LOOP CONFIRMATION (STRICT TWO-STEP PROCESS):
   - You MUST NEVER call `create_lab_booking` or `create_room_reservation` on the initial request.
   - Step 1: When a student asks to book a slot, you must ONLY check availability (`check_lab_availability` or `check_room_availability`).
   - If the slot is available, you MUST STOP and present the complete reservation summary:
     * Student: [Name] (ID: [ID])
     * Facility: [Lab / Discussion Room Name] (ID: [ID])
     * Date: [YYYY-MM-DD]
     * Time: [Start Time] to [End Time]
     Then explicitly ask: "The requested slot is available. Would you like me to book this for you? Please click the Confirm Booking button or reply 'CONFIRM'."
   - Step 2: ONLY call the booking creation tool when the student explicitly confirms (e.g., 'CONFIRM', 'yes', 'proceed', 'go ahead', 'confirm booking').
6. CONFLICT HANDLING:
   - If a slot is unavailable, politely explain that it is occupied and offer to check other times or other rooms/labs.
7. HONESTY:
   - Never claim a reservation succeeded unless the creation tool returned a success message with a valid Booking ID.
   - If an error occurs, explain the exact error clearly to the student.
"""

    if student_ctx and student_ctx.get("student_id"):
        prompt += (
            f"\nCURRENT STUDENT IN SESSION:\n"
            f"- Name: {student_ctx.get('student_name', 'Student')}\n"
            f"- ID: {student_ctx.get('student_id', 'Unknown')}\n"
            f"Use this student information when proposing or creating bookings."
        )

    return prompt


TOOL_MAP = {
    "list_laboratories": list_laboratories,
    "check_lab_availability": check_lab_availability,
    "create_lab_booking": create_lab_booking,
    "list_discussion_rooms": list_discussion_rooms,
    "check_room_availability": check_room_availability,
    "create_room_reservation": create_room_reservation,
}


def clean_text_content(content: Any) -> str:
    """Safely extract plain text from Gemini message content."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return str(content)


class CampusBookingAgent:
    """Manages the agentic conversation loop and tool execution."""

    def __init__(self, model_name: Optional[str] = None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or .env file.")

        # Default to gemini-3.5-flash-lite which is verified working
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=api_key,
        )
        self.llm_with_tools = self.llm.bind_tools(ALL_CAMPUS_TOOLS)

    def run(
        self,
        messages: List[BaseMessage],
        student_context: Optional[Dict[str, str]] = None,
        max_iterations: int = 5,
    ) -> Dict[str, Any]:
        """Execute the agentic ReAct loop for a conversation turn.

        Args:
            messages: List of prior conversation messages (HumanMessage, AIMessage, etc.)
            student_context: Optional dict with 'student_id' and 'student_name'
            max_iterations: Max tool-calling loops to prevent runaway execution

        Returns:
            Dict containing:
                - 'response': Final text response from the agent
                - 'steps': List of tool calls and observations executed during this turn
                - 'messages': Updated list of messages
                - 'pending_booking': Dict with booking details if a slot was confirmed available, else None
        """
        # Dynamically calculate current date context in Asia/Kolkata
        date_ctx = get_current_date_context()
        sys_prompt = build_system_prompt(date_ctx, student_ctx=student_context)

        # Pre-process messages to anchor any relative dates in user text
        sanitized_messages: List[BaseMessage] = []
        for msg in messages:
            if isinstance(msg, HumanMessage) and isinstance(msg.content, str):
                anchored_text = resolve_relative_dates_in_text(msg.content)
                sanitized_messages.append(HumanMessage(content=anchored_text))
            else:
                sanitized_messages.append(msg)

        conversation: List[BaseMessage] = [SystemMessage(content=sys_prompt)] + list(sanitized_messages)
        steps_executed: List[Dict[str, Any]] = []
        pending_booking: Optional[Dict[str, Any]] = None

        for iteration in range(max_iterations):
            ai_msg = self.llm_with_tools.invoke(conversation)
            conversation.append(ai_msg)

            # Check if model requested tool execution
            tool_calls = getattr(ai_msg, "tool_calls", None)
            if not tool_calls:
                return {
                    "response": clean_text_content(ai_msg.content),
                    "steps": steps_executed,
                    "messages": conversation,
                    "pending_booking": pending_booking,
                }

            # Execute requested tools
            for tc in tool_calls:
                tool_name = tc.get("name")
                tool_args = dict(tc.get("args", {}))
                tool_id = tc.get("id", f"call_{iteration}")

                # Enforce Python-level date resolution on booking_date argument
                if "booking_date" in tool_args and isinstance(tool_args["booking_date"], str):
                    try:
                        tool_args["booking_date"] = resolve_date_string(tool_args["booking_date"])
                    except Exception:
                        pass

                tool_func = TOOL_MAP.get(tool_name)
                if tool_func:
                    try:
                        observation = tool_func.invoke(tool_args)
                    except Exception as e:
                        observation = f"Tool execution error: {str(e)}"
                else:
                    observation = f"Error: Tool '{tool_name}' is not recognized."

                # Check if laboratory availability check verified an available slot
                if tool_name == "check_lab_availability":
                    obs_str = str(observation)
                    if obs_str.startswith("AVAILABLE:"):
                        lab_id = int(tool_args.get("lab_id", 0))
                        lab_name = LAB_NAMES.get(lab_id, f"Lab {lab_id}")
                        pending_booking = {
                            "service_type": "lab",
                            "item_id": lab_id,
                            "item_name": lab_name,
                            "lab_id": lab_id,
                            "room_id": None,
                            "booking_date": tool_args.get("booking_date"),
                            "start_time": tool_args.get("start_time"),
                            "end_time": tool_args.get("end_time"),
                            "student_id": (student_context or {}).get("student_id", "Unknown"),
                            "student_name": (student_context or {}).get("student_name", "Student"),
                        }
                    else:
                        pending_booking = None

                # Check if library discussion room availability check verified an available slot
                elif tool_name == "check_room_availability":
                    obs_str = str(observation)
                    if obs_str.startswith("AVAILABLE:"):
                        room_id = int(tool_args.get("room_id", 0))
                        room_name = ROOM_NAMES.get(room_id, f"Discussion Room {room_id}")
                        pending_booking = {
                            "service_type": "room",
                            "item_id": room_id,
                            "item_name": room_name,
                            "lab_id": None,
                            "room_id": room_id,
                            "booking_date": tool_args.get("booking_date"),
                            "start_time": tool_args.get("start_time"),
                            "end_time": tool_args.get("end_time"),
                            "student_id": (student_context or {}).get("student_id", "Unknown"),
                            "student_name": (student_context or {}).get("student_name", "Student"),
                        }
                    else:
                        pending_booking = None

                # If any booking creation tool was executed, clear pending booking
                if tool_name in ("create_lab_booking", "create_room_reservation"):
                    pending_booking = None

                steps_executed.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "observation": observation,
                    }
                )

                # Feed observation back to conversation
                conversation.append(
                    ToolMessage(
                        content=str(observation),
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )

        final_text = clean_text_content(ai_msg.content) if ai_msg else "Agent completed reasoning steps."
        return {
            "response": final_text,
            "steps": steps_executed,
            "messages": conversation,
            "pending_booking": pending_booking,
        }
