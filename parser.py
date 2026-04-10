"""
parser.py - Travel inquiry field extraction and reply generation
Uses OpenAI-compatible API for AI-powered extraction and reply generation.
Falls back to rule-based heuristics if AI API is unavailable.
"""

import re
import json
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMPORTANT_FIELDS = ["destination", "travel_time", "group_size", "budget"]

TRIP_TYPE_KEYWORDS: dict[str, list[str]] = {
    "honeymoon": ["honeymoon"],
    "family": ["family", "kids", "children", "child"],
    "beach": ["beach", "coastal", "seaside", "island"],
    "adventure": ["adventure", "hiking", "trekking", "backpack"],
    "business": ["business", "conference", "meeting", "work"],
    "visa assistance": ["visa", "immigration", "permit"],
    "general leisure": [],  # default fallback
}

INTENT_KEYWORDS: dict[str, list[str]] = {
    "booking": ["book", "reserve", "ready to book", "contact me"],
    "pricing inquiry": ["price", "cost", "how much", "cheap", "budget"],
    "visa inquiry": ["visa", "immigration"],
    "trip planning": ["plan", "trip", "travel", "tour", "vacation", "holiday", "want to go"],
    "destination inquiry": ["where", "recommend", "suggestion", "don't know where"],
    "general inquiry": [],  # default fallback
}


# ---------------------------------------------------------------------------
# Rule-based helpers
# ---------------------------------------------------------------------------

def _extract_duration(text: str) -> str | None:
    """Extract trip duration from free text."""
    patterns = [
        r"(\d+)\s*-?\s*day",
        r"(\d+)\s*days?",
        r"(\d+)\s*night",
        r"(\d+)\s*nights?",
        r"(\d+)\s*week",
        r"(\d+)\s*weeks?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            unit = re.search(r"(day|night|week)s?", m.group(0), re.IGNORECASE).group(1).lower()
            if unit == "week":
                return f"{num * 7} days"
            return f"{num} {unit}{'s' if num > 1 else ''}"
    return None


def _extract_group_size(text: str) -> int | None:
    """Extract number of travellers from free text."""
    patterns = [
        r"(\d+)\s*(?:people|persons?|travell?ers?|adults?|passengers?|pax)",
        r"for\s+(\d+)",
        r"(\d+)\s*of\s+us",
        r"\b(two|three|four|five|six)\b",
    ]
    word_map = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            return word_map.get(val, int(val) if val.isdigit() else None)
    # "a couple" or "couple"
    if re.search(r"\bcouple\b", text, re.IGNORECASE):
        return 2
    return None


def _extract_budget(text: str) -> int | None:
    """Extract budget amount in USD (or generic number) from free text."""
    patterns = [
        r"\$\s*(\d[\d,]*)",
        r"(\d[\d,]*)\s*(?:usd|dollars?|bucks?)",
        r"budget\s+(?:is\s+)?(?:around\s+)?(?:\$\s*)?(\d[\d,]*)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _extract_travel_time(text: str) -> str | None:
    """Extract travel month / season / relative time."""
    months = (
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )
    m = re.search(months, text, re.IGNORECASE)
    if m:
        return m.group(0).capitalize()
    # "next month", "next year", "this summer" etc.
    m2 = re.search(r"(next\s+\w+|this\s+\w+|in\s+\d{4})", text, re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None


def _classify_trip_type(text: str) -> str:
    text_lower = text.lower()
    for trip_type, keywords in TRIP_TYPE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return trip_type
    return "general leisure"


def _classify_intent(text: str) -> str:
    text_lower = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return intent
    return "general inquiry"


def _extract_destination(text: str) -> str | None:
    """Very lightweight rule-based destination extraction."""
    # Named countries / regions commonly mentioned in travel
    known_places = [
        "Japan", "Europe", "Canada", "Australia", "Thailand", "Bali",
        "Paris", "London", "New York", "Maldives", "Dubai", "Singapore",
        "Korea", "Vietnam", "Italy", "Spain", "France", "Greece", "Turkey",
        "India", "China", "Mexico", "Hawaii", "Caribbean",
    ]
    for place in known_places:
        if re.search(r"\b" + re.escape(place) + r"\b", text, re.IGNORECASE):
            return place
    # "trip to <Place>" pattern
    m = re.search(r"trip\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Rule-based extraction (no API needed)
# ---------------------------------------------------------------------------

def rule_based_extract(message: str) -> dict[str, Any]:
    """Extract fields using heuristic rules only (no external API)."""
    destination = _extract_destination(message)
    duration = _extract_duration(message)
    group_size = _extract_group_size(message)
    budget = _extract_budget(message)
    travel_time = _extract_travel_time(message)
    trip_type = _classify_trip_type(message)
    intent = _classify_intent(message)

    # Determine missing fields
    missing: list[str] = []
    if not destination:
        missing.append("destination")
    if not travel_time:
        missing.append("travel_time")
    if group_size is None:
        missing.append("group_size")
    if budget is None:
        missing.append("budget")

    return {
        "destination": destination,
        "trip_type": trip_type,
        "duration": duration,
        "travel_time": travel_time,
        "group_size": group_size,
        "budget": budget,
        "intent": intent,
        "missing_fields": missing,
    }


# ---------------------------------------------------------------------------
# AI-powered extraction and reply
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a travel inquiry assistant for WanderFlow, a travel company.
Your task is to analyze a customer travel inquiry and return a JSON object.

Extract or infer these fields (use null if truly unknown):
- destination (string or null)
- trip_type (string: one of "honeymoon", "family", "beach", "adventure", "business", "visa assistance", "general leisure")
- duration (string or null, e.g. "7 days")
- travel_time (string or null, e.g. "October", "next month")
- group_size (integer or null)
- budget (integer or null, in USD)
- intent (string: one of "booking", "pricing inquiry", "visa inquiry", "trip planning", "destination inquiry", "general inquiry")
- missing_fields (list of important missing fields from: destination, travel_time, group_size, budget)
- reply_type (string: "initial_response" if enough info, "clarifying_question" if key info missing)
- reply (string: short, professional, natural reply in English — no invented prices or promises)

Return ONLY valid JSON. No markdown, no explanation.
"""


async def ai_extract_and_reply(message: str) -> dict[str, Any]:
    """Call AI API to extract fields and generate reply."""
    payload = {
        "model": settings.ai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "temperature": 0.3,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(settings.openai_api_base, headers=headers, json=payload)
        resp.raise_for_status()
    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown code fences if present
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)
    return json.loads(raw_text)


# ---------------------------------------------------------------------------
# Generate reply from structured fields (no AI)
# ---------------------------------------------------------------------------

def generate_rule_based_reply(fields: dict[str, Any]) -> tuple[str, str]:
    """
    Build reply_type and reply text from extracted fields.
    Returns (reply_type, reply_text).
    """
    missing = fields.get("missing_fields", [])
    destination = fields.get("destination")
    duration = fields.get("duration")
    travel_time = fields.get("travel_time")
    group_size = fields.get("group_size")
    budget = fields.get("budget")
    trip_type = fields.get("trip_type", "general leisure")
    intent = fields.get("intent", "general inquiry")

    # Decide reply type: clarifying if more than 1 important field missing
    if len(missing) > 1:
        reply_type = "clarifying_question"
        # Ask about the single most important missing piece
        ask_field = missing[0]
        question_map = {
            "destination": "Could you let us know which destination or region you have in mind?",
            "travel_time": "When are you planning to travel?",
            "group_size": "How many travellers will be joining this trip?",
            "budget": "Do you have a rough budget in mind for this trip?",
        }
        question = question_map.get(ask_field, "Could you provide more details about your trip?")

        parts = ["Thanks for reaching out to WanderFlow!"]
        if destination:
            parts.append(f"A trip to {destination} sounds wonderful.")
        if trip_type != "general leisure":
            parts.append(f"We see you're interested in a {trip_type} trip.")
        parts.append(question)
        reply = " ".join(parts)

    else:
        reply_type = "initial_response"
        parts = ["Thanks for your message!"]

        details = []
        if destination:
            details.append(f"a trip to {destination}")
        if duration:
            details.append(f"for {duration}")
        if travel_time:
            details.append(f"in {travel_time}")
        if group_size:
            details.append(f"for {group_size} {'person' if group_size == 1 else 'people'}")
        if budget:
            details.append(f"with a budget of around ${budget:,} USD")

        if details:
            parts.append("We received your inquiry about " + ", ".join(details) + ".")
        if trip_type and trip_type != "general leisure":
            parts.append(f"This looks like a {trip_type} trip.")

        if intent == "booking":
            parts.append("One of our travel consultants will reach out to you shortly to proceed with your booking.")
        elif intent == "visa inquiry":
            parts.append("Our visa support team will be happy to guide you through the requirements.")
        elif intent == "pricing inquiry":
            parts.append("We'll put together some tailored options that fit your budget.")
        else:
            parts.append("We'd love to help you plan the perfect trip and will follow up with suitable options.")

        reply = " ".join(parts)

    return reply_type, reply


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def process_inquiry(message: str) -> dict[str, Any]:
    """
    Process a raw travel inquiry message.
    Tries AI API first; falls back to rule-based logic.
    """
    if settings.openai_api_key:
        try:
            result = await ai_extract_and_reply(message)
            logger.info("AI extraction succeeded.")
            # Ensure all required keys are present (defensive merge with rule-based)
            rule_fields = rule_based_extract(message)
            for key in ["destination", "trip_type", "duration", "travel_time",
                        "group_size", "budget", "intent", "missing_fields"]:
                if result.get(key) is None and rule_fields.get(key) is not None:
                    result[key] = rule_fields[key]
            # Ensure missing_fields is up to date
            if not result.get("missing_fields"):
                result["missing_fields"] = rule_fields["missing_fields"]
            return result
        except Exception as exc:
            logger.warning("AI API call failed (%s). Falling back to rule-based logic.", exc)

    # Rule-based fallback
    fields = rule_based_extract(message)
    reply_type, reply = generate_rule_based_reply(fields)
    return {**fields, "reply_type": reply_type, "reply": reply}
