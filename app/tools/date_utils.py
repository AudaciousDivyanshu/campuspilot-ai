"""Date resolution utilities for CampusPilot AI in the Asia/Kolkata timezone.

Handles dynamic resolution of:
- Current date (today)
- tomorrow
- day after tomorrow
- natural language dates (e.g. '20 November 2026', '20th Nov 2026')
- ISO dates ('YYYY-MM-DD')
- Text-level relative date replacement
"""

from datetime import datetime, timedelta
import re
from typing import Dict
from zoneinfo import ZoneInfo
import dateutil.parser

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


def get_kolkata_now() -> datetime:
    """Return the current datetime in the Asia/Kolkata timezone."""
    return datetime.now(KOLKATA_TZ)


def get_current_date_context() -> Dict[str, str]:
    """Obtain the dynamic current date and relative milestones in Asia/Kolkata.

    Returns:
        Dict with 'today', 'tomorrow', 'day_after_tomorrow', and formatted strings.
    """
    now = get_kolkata_now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    day_after_tomorrow = today + timedelta(days=2)

    return {
        "today": today.strftime("%Y-%m-%d"),
        "today_human": today.strftime("%A, %d %B %Y"),
        "tomorrow": tomorrow.strftime("%Y-%m-%d"),
        "tomorrow_human": tomorrow.strftime("%A, %d %B %Y"),
        "day_after_tomorrow": day_after_tomorrow.strftime("%Y-%m-%d"),
        "day_after_tomorrow_human": day_after_tomorrow.strftime("%A, %d %B %Y"),
        "timezone": "Asia/Kolkata",
    }


def resolve_relative_dates_in_text(text: str) -> str:
    """Scan natural language user input and explicitly anchor relative date phrases to YYYY-MM-DD.

    Replaces:
    - 'day after tomorrow' -> 'YYYY-MM-DD (day after tomorrow)'
    - 'tomorrow' -> 'YYYY-MM-DD (tomorrow)'
    - 'today' -> 'YYYY-MM-DD (today)'

    This prevents the LLM from independently guessing or hallucinating arbitrary dates.
    """
    if not text or not isinstance(text, str):
        return text

    now = get_kolkata_now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    pattern_day_after = re.compile(r"\b(day after tomorrow|day after tmrw)\b", re.IGNORECASE)
    pattern_tomorrow = re.compile(r"\b(tomorrow|tmrw)\b", re.IGNORECASE)
    pattern_today = re.compile(r"\b(today)\b", re.IGNORECASE)

    res = pattern_day_after.sub(f"{day_after.strftime('%Y-%m-%d')} (day after tomorrow)", text)
    res = pattern_tomorrow.sub(f"{tomorrow.strftime('%Y-%m-%d')} (tomorrow)", res)
    res = pattern_today.sub(f"{today.strftime('%Y-%m-%d')} (today)", res)
    return res


def resolve_date_string(date_input: str) -> str:
    """Resolve relative dates or natural language date strings to strict 'YYYY-MM-DD'.

    Supported formats:
    - 'today', 'now'
    - 'tomorrow', 'tmrw'
    - 'day after tomorrow', 'day after tmrw'
    - 'YYYY-MM-DD' (e.g., '2026-11-20')
    - '20 November 2026', '20th Nov 2026', 'November 20, 2026'

    Args:
        date_input: Raw date string from user or model.

    Returns:
        Formatted 'YYYY-MM-DD' date string.

    Raises:
        ValueError: If the date cannot be parsed.
    """
    if not date_input or not isinstance(date_input, str):
        raise ValueError("Date input must be a non-empty string.")

    cleaned = date_input.strip().lower()
    now = get_kolkata_now()
    today = now.date()

    if cleaned in ("today", "now"):
        return today.strftime("%Y-%m-%d")
    elif cleaned in ("tomorrow", "tmrw"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif cleaned in ("day after tomorrow", "day after tmrw"):
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")

    # Check for strict ISO format YYYY-MM-DD first
    if re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        try:
            parsed_iso = datetime.strptime(cleaned, "%Y-%m-%d").date()
            return parsed_iso.strftime("%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid calendar date: {date_input}") from e

    # Parse explicit natural language date (e.g., '20 November 2026')
    try:
        parsed_dt = dateutil.parser.parse(
            date_input,
            fuzzy=True,
            default=now,
        ).date()
        return parsed_dt.strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"Could not parse date '{date_input}'. Please use YYYY-MM-DD format.") from e
