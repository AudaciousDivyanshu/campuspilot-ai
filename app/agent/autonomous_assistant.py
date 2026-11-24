"""Autonomous AI Campus Assistant for CampusPilot AI.

Implements multi-step conversational facility booking, availability checking against SQLite,
entity extraction using Gemini API and deterministic Python parsing, conflict detection,
and strict human-in-the-loop confirmation gates without external agent frameworks.
"""

from datetime import date, datetime, timedelta
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.database.operations import (
    check_booking_overlap,
    check_room_booking_overlap,
    create_booking,
    create_room_booking,
    get_all_discussion_rooms,
    get_all_laboratories,
    get_all_student_reservations,
    get_discussion_room_by_id,
    get_laboratory_by_id,
)
from app.tools.date_utils import (
    get_current_date_context,
    resolve_date_string,
    resolve_relative_dates_in_text,
)

LAB_CATALOG = {
    1: {"name": "Computer Lab 1", "capacity": 40, "location": "Main Block, Floor 2", "type": "lab"},
    2: {"name": "AI Lab", "capacity": 30, "location": "Science Block, Room 204", "type": "lab"},
    3: {"name": "Networking Lab", "capacity": 35, "location": "Tech Wing, Ground Floor", "type": "lab"},
}

ROOM_CATALOG = {
    1: {"name": "Discussion Room 1", "capacity": 4, "location": "Library, 2nd Floor, Wing A", "type": "room"},
    2: {"name": "Discussion Room 2", "capacity": 6, "location": "Library, 2nd Floor, Wing B", "type": "room"},
    3: {"name": "Discussion Room 3", "capacity": 8, "location": "Library, 3rd Floor, Annex", "type": "room"},
}


def _call_gemini_extraction(user_text: str, current_state: Dict[str, Any], date_ctx: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Attempt entity extraction via Gemini API using direct official google-genai client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

        prompt = f"""You are the natural language parser for CampusPilot AI university facility booking.
Extract structured booking entities from the student's message.

CURRENT DATE CONTEXT (Asia/Kolkata):
- Today: {date_ctx['today']}
- Tomorrow: {date_ctx['tomorrow']}
- Day after tomorrow: {date_ctx['day_after_tomorrow']}

FACILITIES:
- Labs: 'Computer Lab 1' (id: 1), 'AI Lab' (id: 2), 'Networking Lab' (id: 3)
- Rooms: 'Discussion Room 1' (id: 1), 'Discussion Room 2' (id: 2), 'Discussion Room 3' (id: 3)

EXISTING CONVERSATION STATE:
{json.dumps(current_state, default=str)}

STUDENT MESSAGE:
"{user_text}"

Return strictly valid JSON with these fields (use null if not mentioned or unchanged):
{{
  "intent": "book_lab" | "book_room" | "check_availability" | "view_bookings" | "submit_leave" | "facility_info" | "greeting" | "general",
  "facility_type": "lab" | "room" | null,
  "facility_name": string | null,
  "facility_id": integer | null,
  "date": "YYYY-MM-DD" | null,
  "start_time": "HH:MM" | null,
  "end_time": "HH:MM" | null,
  "occupants": integer | null,
  "purpose": string | null
}}
"""
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        text = response.text.strip()
        # Extract JSON substring
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception:
        # Fall back gracefully to deterministic rule-based NLP extraction
        return None
    return None


def _rule_based_nlp_extraction(user_text: str, current_state: Dict[str, Any], date_ctx: Dict[str, str]) -> Dict[str, Any]:
    """Deterministic Python entity extraction for robust multi-turn parsing."""
    raw = user_text.strip()
    low = raw.lower()
    extracted = dict(current_state or {})

    # 1. Intent Detection
    if any(k in low for k in ["view my booking", "show my booking", "my reservation", "list my booking", "upcoming booking"]):
        extracted["intent"] = "view_bookings"
        return extracted
    elif any(k in low for k in ["leave request", "apply for leave", "submit leave", "medical leave", "sick leave"]):
        extracted["intent"] = "submit_leave"
        return extracted
    elif any(k in low for k in ["facility info", "campus facilit", "about labs", "what labs", "list labs", "available facilities"]):
        extracted["intent"] = "facility_info"
        return extracted
    elif any(k in low for k in ["check availability", "is it available", "slot available", "check ai lab", "check slot"]):
        extracted["intent"] = "check_availability"
    elif any(k in low for k in ["book a room", "book discussion room", "study room", "reserve room"]):
        extracted["intent"] = "book_room"
        extracted["facility_type"] = "room"
    elif any(k in low for k in ["book a lab", "book lab", "reserve lab", "need a lab", "need the lab", "computer lab", "ai lab"]):
        extracted["intent"] = "book_lab"
        extracted["facility_type"] = "lab"

    # 2. Facility Identification
    if re.search(r"\b(?:ai lab|deep learning lab|artificial intelligence)\b", low):
        extracted["facility_name"] = "AI Lab"
        extracted["facility_id"] = 2
        extracted["facility_type"] = "lab"
    elif re.search(r"\b(?:computer lab 1|computer lab|pc lab|programming lab)\b", low):
        extracted["facility_name"] = "Computer Lab 1"
        extracted["facility_id"] = 1
        extracted["facility_type"] = "lab"
    elif re.search(r"\b(?:networking lab|network lab|cisco lab)\b", low):
        extracted["facility_name"] = "Networking Lab"
        extracted["facility_id"] = 3
        extracted["facility_type"] = "lab"
    elif re.search(r"\b(?:discussion room 1|room 1)\b", low):
        extracted["facility_name"] = "Discussion Room 1"
        extracted["facility_id"] = 1
        extracted["facility_type"] = "room"
    elif re.search(r"\b(?:discussion room 2|room 2)\b", low):
        extracted["facility_name"] = "Discussion Room 2"
        extracted["facility_id"] = 2
        extracted["facility_type"] = "room"
    elif re.search(r"\b(?:discussion room 3|room 3)\b", low):
        extracted["facility_name"] = "Discussion Room 3"
        extracted["facility_id"] = 3
        extracted["facility_type"] = "room"
    elif "discussion room" in low or "library room" in low:
        extracted["facility_type"] = "room"
    elif "laboratory" in low or "lab" in low:
        if not extracted.get("facility_type"):
            extracted["facility_type"] = "lab"

    # 3. Date Resolution
    if "day after tomorrow" in low:
        extracted["date"] = date_ctx["day_after_tomorrow"]
    elif "tomorrow" in low:
        extracted["date"] = date_ctx["tomorrow"]
    elif "today" in low:
        extracted["date"] = date_ctx["today"]
    else:
        # Check for explicit YYYY-MM-DD
        d_match = re.search(r"\b(202\d-[01]\d-[0-3]\d)\b", raw)
        if d_match:
            try:
                extracted["date"] = resolve_date_string(d_match.group(1))
            except Exception:
                pass

    # 4. Time Interval Resolution
    # Pattern 1: e.g. "10:00 to 12:00" or "10:00 - 12:00"
    t_match_24 = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(?:to|-)\s*([01]?\d|2[0-3]):([0-5]\d)\b", raw)
    if t_match_24:
        s_h, s_m, e_h, e_m = t_match_24.groups()
        extracted["start_time"] = f"{int(s_h):02d}:{s_m}"
        extracted["end_time"] = f"{int(e_h):02d}:{e_m}"
    else:
        # Pattern 2: e.g. "10 AM to 12 PM", "10am-12pm", "2 PM to 4 PM"
        t_match_ampm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*(?:to|-)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
        if t_match_ampm:
            sh, sm, sp, eh, em, ep = t_match_ampm.groups()
            s_hour = int(sh) % 12 + (12 if sp == "pm" else 0)
            e_hour = int(eh) % 12 + (12 if ep == "pm" else 0)
            extracted["start_time"] = f"{s_hour:02d}:{sm or '00'}"
            extracted["end_time"] = f"{e_hour:02d}:{em or '00'}"
        else:
            # Pattern 3: e.g. "10-12" or "10 to 12"
            t_match_short = re.search(r"\b(\d{1,2})\s*(?:to|-)\s*(\d{1,2})\b", low)
            if t_match_short:
                sh, eh = int(t_match_short.group(1)), int(t_match_short.group(2))
                # Heuristic: 9-17 is standard daytime hours
                if 8 <= sh <= 18 and 8 <= eh <= 20 and sh < eh:
                    extracted["start_time"] = f"{sh:02d}:00"
                    extracted["end_time"] = f"{eh:02d}:00"

    # 5. Occupants Resolution
    cap_match = re.search(r"\b(\d+)\s*(?:students?|people|persons?|occupants?|seats?|members?)\b", low)
    if cap_match:
        extracted["occupants"] = int(cap_match.group(1))

    # 6. Purpose Resolution
    for p_prefix in ["for my ", "for a ", "for the ", "for "]:
        if p_prefix in low:
            p_part = raw[low.index(p_prefix) + len(p_prefix):].strip()
            # Clean trailing punctuation
            p_part = re.split(r"[,.;!?]|\btomorrow\b|\btoday\b|\bfrom\b", p_part, flags=re.IGNORECASE)[0].strip()
            if len(p_part) >= 3 and not any(p_part.lower().startswith(w) for w in ["10", "11", "12", "1", "2", "3", "4", "5", "6", "7", "8", "9"]):
                extracted["purpose"] = p_part
                break

    return extracted


class AutonomousAssistant:
    """Manages the interactive multi-turn conversation and real-time SQLite integration."""

    @staticmethod
    def process_turn(
        user_text: str,
        current_state: Optional[Dict[str, Any]] = None,
        student_context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Process a conversational turn, maintaining state and checking real SQLite availability."""
        date_ctx = get_current_date_context()
        state = dict(current_state or {})
        clean_text = user_text.strip()
        lower_text = clean_text.lower()

        # Handle operation shortcuts
        if lower_text == "book a laboratory":
            return {
                "reply": "I'd be glad to help you reserve a campus laboratory! Which laboratory would you like to book:\n\n"
                         "- 🔬 **AI & Deep Learning Supercomputing Lab** (Capacity: 30, Science Block)\n"
                         "- 💻 **Computer Lab 1** (Capacity: 40, Main Block)\n"
                         "- 🌐 **Networking & Telecommunications Lab** (Capacity: 35, Tech Wing)\n\n"
                         "Please let me know the laboratory, preferred date, and time slot (e.g., *AI Lab tomorrow from 10 AM to 12 PM*).",
                "state": {"intent": "book_lab", "facility_type": "lab"},
                "pending_booking": None,
                "alternatives": [],
            }
        elif lower_text == "book a discussion room":
            return {
                "reply": "Certainly! Library discussion rooms are self-service facilities with instant confirmation. Which room would you like to book:\n\n"
                         "- 📚 **Discussion Room 1** (4 seats, Library 2nd Floor, Wing A)\n"
                         "- 📚 **Discussion Room 2** (6 seats, Library 2nd Floor, Wing B)\n"
                         "- 📚 **Discussion Room 3** (8 seats, Library 3rd Floor, Annex)\n\n"
                         "What date and time interval would you like to reserve?",
                "state": {"intent": "book_room", "facility_type": "room"},
                "pending_booking": None,
                "alternatives": [],
            }
        elif lower_text == "check availability":
            return {
                "reply": "I can verify live slot availability across any laboratory or study room in the SQLite database. Please tell me which facility and date/time you want to verify (e.g. *Check AI Lab tomorrow 10:00 to 12:00*).",
                "state": {"intent": "check_availability"},
                "pending_booking": None,
                "alternatives": [],
            }
        elif lower_text == "view my bookings":
            stu_id = (student_context or {}).get("student_id", "CS2026-001")
            my_bookings = get_all_student_reservations(student_id=stu_id)
            if not my_bookings:
                reply = f"You do not have any active or pending bookings recorded for Student ID `{stu_id}`."
            else:
                lines = [f"Here are your current facility reservations from the database for `{stu_id}`:"]
                for b in my_bookings[:5]:
                    badge = "✅ Approved" if b.get("status") in ("confirmed", "approved") else ("❌ Rejected" if b.get("status") == "rejected" else "⏳ Pending Approval")
                    lines.append(f"- **{b['facility_name']}** ({b['service_type']}): {b['booking_date']} &bull; {b['start_time']} - {b['end_time']} &bull; Status: **{badge}** (Ref #{b['booking_id']})")
                reply = "\n".join(lines)
            return {
                "reply": reply,
                "state": {},
                "pending_booking": None,
                "alternatives": [],
            }
        elif lower_text == "submit a leave request":
            return {
                "reply": "To apply for an academic, medical, or on-duty leave, please navigate to **🏖️ Leave Requests** in the sidebar. All leave requests enter the administrator's review queue with initial status `Pending Approval`.",
                "state": {},
                "pending_booking": None,
                "alternatives": [],
            }
        elif lower_text == "campus facility information":
            labs = get_all_laboratories()
            rooms = get_all_discussion_rooms()
            reply = "### 🏢 Campus Facility Directory & Live Specifications\n\n**Campus Laboratories:**\n"
            for l in labs:
                status_lbl = "Active" if l.get("is_enabled", 1) == 1 else "Temporarily Disabled"
                reply += f"- **{l['lab_name']}** (ID: {l['lab_id']}) &bull; Capacity: **{l['capacity']} seats** &bull; Location: {l['location']} &bull; Status: *{status_lbl}*\n"
            reply += "\n**Library Discussion Rooms (Self-Service):**\n"
            for r in rooms:
                status_lbl = "Active" if r.get("is_enabled", 1) == 1 else "Temporarily Disabled"
                reply += f"- **{r['room_name']}** (ID: {r['room_id']}) &bull; Capacity: **{r['capacity']} seats** &bull; Location: {r['location']} &bull; Status: *{status_lbl}*\n"
            reply += "\nYou can ask me to check availability or book any of these facilities anytime!"
            return {
                "reply": reply,
                "state": {},
                "pending_booking": None,
                "alternatives": [],
            }

        # 1. Extraction: Try Gemini first, fallback to rule-based parser
        gemini_result = _call_gemini_extraction(clean_text, state, date_ctx)
        extracted = _rule_based_nlp_extraction(clean_text, state, date_ctx)

        # Merge Gemini extractions if valid
        if gemini_result and isinstance(gemini_result, dict):
            for k in ["facility_type", "facility_name", "facility_id", "date", "start_time", "end_time", "occupants", "purpose"]:
                if gemini_result.get(k):
                    extracted[k] = gemini_result[k]

        # Preserve previously stored state values if not overwritten
        for k, v in state.items():
            if k not in extracted or extracted[k] is None:
                extracted[k] = v

        # 2. Check Missing Information for Booking
        fac_type = extracted.get("facility_type")
        fac_id = extracted.get("facility_id")
        fac_name = extracted.get("facility_name")
        req_date = extracted.get("date")
        req_start = extracted.get("start_time")
        req_end = extracted.get("end_time")

        # Resolve facility_id and facility_name if only one is present
        if fac_name and not fac_id:
            for fid, fval in {**LAB_CATALOG, **ROOM_CATALOG}.items():
                if fval["name"].lower() == fac_name.lower():
                    fac_id = fid
                    extracted["facility_id"] = fid
                    extracted["facility_type"] = fval["type"]
                    break

        if fac_id and not fac_name:
            if fac_type == "room" and fac_id in ROOM_CATALOG:
                fac_name = ROOM_CATALOG[fac_id]["name"]
                extracted["facility_name"] = fac_name
            elif fac_id in LAB_CATALOG:
                fac_name = LAB_CATALOG[fac_id]["name"]
                extracted["facility_name"] = fac_name

        # Interactive Follow-up Question Prompts
        if not fac_name and not fac_id:
            if fac_type == "lab":
                return {
                    "reply": "Which laboratory would you like to book: **AI Lab**, **Computer Lab 1**, or **Networking Lab**?",
                    "state": extracted,
                    "pending_booking": None,
                    "alternatives": [],
                }
            elif fac_type == "room":
                return {
                    "reply": "Which discussion room would you like to book: **Discussion Room 1** (4 seats), **Room 2** (6 seats), or **Room 3** (8 seats)?",
                    "state": extracted,
                    "pending_booking": None,
                    "alternatives": [],
                }
            else:
                return {
                    "reply": "Would you like to book a **Campus Laboratory** (e.g., AI Lab, Computer Lab) or a **Library Discussion Room**?",
                    "state": extracted,
                    "pending_booking": None,
                    "alternatives": [],
                }

        if not req_date:
            return {
                "reply": f"For what date would you like to reserve **{fac_name}**? (e.g., *today*, *tomorrow*, or a specific date like `{date_ctx['tomorrow']}`)",
                "state": extracted,
                "pending_booking": None,
                "alternatives": [],
            }

        if not req_start or not req_end:
            return {
                "reply": f"What time slot would you like to use **{fac_name}** on **{req_date}**? (e.g., *10:00 to 12:00* or *2 PM to 4 PM*)",
                "state": extracted,
                "pending_booking": None,
                "alternatives": [],
            }

        # 3. All Required Details Collected -> Live SQLite Availability Check
        is_room = (fac_type == "room") or (fac_name and ("room" in fac_name.lower() or "discussion" in fac_name.lower()))
        is_lab = not is_room
        facility_info = LAB_CATALOG.get(fac_id) if is_lab else ROOM_CATALOG.get(fac_id)
        if not facility_info:
            facility_info = {"name": fac_name or "Facility", "capacity": 30, "location": "Campus"}

        # Check facility enabled status
        if is_lab:
            db_lab = get_laboratory_by_id(fac_id)
            if db_lab and db_lab.get("is_enabled", 1) == 0:
                return {
                    "reply": f"⚠️ **{fac_name}** has been temporarily marked as disabled by the campus administrator for maintenance. Would you like to check another lab, such as Computer Lab 1 or Networking Lab?",
                    "state": extracted,
                    "pending_booking": None,
                    "alternatives": [],
                }
            has_conflict = check_booking_overlap(
                lab_id=fac_id,
                booking_date=req_date,
                start_time=req_start,
                end_time=req_end,
            )
        else:
            db_room = get_discussion_room_by_id(fac_id)
            if db_room and db_room.get("is_enabled", 1) == 0:
                return {
                    "reply": f"⚠️ **{fac_name}** has been temporarily marked as disabled by the administrator. Would you like to check another discussion room?",
                    "state": extracted,
                    "pending_booking": None,
                    "alternatives": [],
                }
            has_conflict = check_room_booking_overlap(
                room_id=fac_id,
                booking_date=req_date,
                start_time=req_start,
                end_time=req_end,
            )

        # 4. Handle Conflict vs Available
        if has_conflict:
            # Search genuinely available alternative slots on that date
            alternatives = []
            test_slots = [("09:00", "11:00"), ("11:00", "13:00"), ("14:00", "16:00"), ("16:00", "18:00")]
            for s_slot, e_slot in test_slots:
                if s_slot == req_start and e_slot == req_end:
                    continue
                alt_conflict = check_booking_overlap(lab_id=fac_id, booking_date=req_date, start_time=s_slot, end_time=e_slot) if is_lab else check_room_booking_overlap(room_id=fac_id, booking_date=req_date, start_time=s_slot, end_time=e_slot)
                if not alt_conflict:
                    alternatives.append((s_slot, e_slot))

            alt_msg = ""
            if alternatives:
                alt_msg = "\n\n**Genuinely available alternative slots on " + req_date + " in " + fac_name + ":**\n"
                for as_t, ae_t in alternatives:
                    alt_msg += f"- ⏰ `{as_t} - {ae_t}`\n"
                alt_msg += "\nReply with one of these times if you would like to proceed with that slot!"
            else:
                alt_msg = "\n\nPlease select another date or consider checking another laboratory."

            return {
                "reply": f"❌ **Conflict Detected**: Slot `{req_start} - {req_end}` on `{req_date}` in **{fac_name}** is already occupied in the database schedule.{alt_msg}",
                "state": extracted,
                "pending_booking": None,
                "alternatives": alternatives,
            }

        # Slot is Available! Build Pending Confirmation
        approval_note = "Requires Administrator Approval (Submits as Pending Approval)" if is_lab else "Instant Self-Service Confirmation"
        occupants_display = extracted.get("occupants") or facility_info.get("capacity")
        purpose_display = extracted.get("purpose") or "Academic Project / Research"

        pending_dict = {
            "service_type": "lab" if is_lab else "room",
            "item_id": fac_id,
            "item_name": fac_name,
            "lab_id": fac_id if is_lab else None,
            "room_id": fac_id if not is_lab else None,
            "booking_date": req_date,
            "start_time": req_start,
            "end_time": req_end,
            "occupants": occupants_display,
            "purpose": purpose_display,
            "approval_requirement": approval_note,
            "student_id": (student_context or {}).get("student_id", "CS2026-001"),
            "student_name": (student_context or {}).get("student_name", "Student"),
        }

        confirmation_reply = (
            f"✅ **Slot Confirmed Available!**\n\n"
            f"I checked the real-time SQLite database, and **{fac_name}** is free on **{req_date}** from **{req_start} to {req_end}**.\n\n"
            f"**Reservation Parameters:**\n"
            f"- 🏢 **Facility:** {fac_name} ({facility_info.get('location')})\n"
            f"- 📅 **Date:** `{req_date}`\n"
            f"- ⏰ **Time:** `{req_start}` to `{req_end}`\n"
            f"- 👥 **Capacity / Occupants:** {occupants_display} seats\n"
            f"- 🎯 **Purpose:** *{purpose_display}*\n"
            f"- 🛡️ **Policy:** *{approval_note}*\n\n"
            f"Please review the summary below and click **Confirm Booking** to record your request."
        )

        return {
            "reply": confirmation_reply,
            "state": extracted,
            "pending_booking": pending_dict,
            "alternatives": [],
        }

    @staticmethod
    def execute_booking(pending: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
        """Commit confirmed booking to SQLite.

        Laboratories are submitted with status='pending' (Pending Approval).
        Discussion rooms are self-service and submitted with status='confirmed'.
        """
        service_type = pending.get("service_type", "lab")
        student_id = pending.get("student_id", "")
        student_name = pending.get("student_name", "")
        booking_date = pending.get("booking_date", "")
        start_time = pending.get("start_time", "")
        end_time = pending.get("end_time", "")
        purpose = pending.get("purpose", "Requested via CampusPilot AI Assistant")

        try:
            if service_type == "room":
                res = create_room_booking(
                    student_id=student_id,
                    student_name=student_name,
                    room_id=int(pending.get("room_id") or pending.get("item_id")),
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    purpose=purpose,
                )
                b_id = res["booking_id"]
                msg = (
                    f"🎉 **Discussion Room Booking Confirmed!**\n"
                    f"- **Reference ID:** `#{b_id}`\n"
                    f"- **Venue:** {pending.get('item_name')}\n"
                    f"- **Date & Time:** {booking_date} ({start_time} - {end_time})\n"
                    f"- **Status:** **Confirmed in SQLite** (Self-Service).\n"
                    f"You may now use the room at your scheduled time."
                )
                return True, msg, b_id
            else:
                # Lab booking strictly starts with status='pending' for Administrator Approval
                res = create_booking(
                    student_id=student_id,
                    student_name=student_name,
                    lab_id=int(pending.get("lab_id") or pending.get("item_id")),
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    status="pending",
                    purpose=purpose,
                )
                b_id = res["booking_id"]
                msg = (
                    f"🚀 **Laboratory Reservation Request Submitted!**\n"
                    f"- **Reference ID:** `#{b_id}`\n"
                    f"- **Laboratory:** {pending.get('item_name')}\n"
                    f"- **Date & Slot:** {booking_date} ({start_time} - {end_time})\n"
                    f"- **Purpose:** *{purpose}*\n"
                    f"- **Current Status:** ⏳ **Pending Approval** (Awaiting Administrator Review).\n"
                    f"Your request has been added to the Administrator Dashboard approval queue. "
                    f"You can monitor live status under **My Bookings**."
                )
                return True, msg, b_id
        except Exception as e:
            return False, f"Failed to record booking in database: {str(e)}", None
