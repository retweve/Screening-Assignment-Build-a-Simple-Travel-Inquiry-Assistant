"""
tests/test_parser.py - Unit tests for field extraction and reply generation.
"""

import asyncio
import sys
import os
import pytest

# Allow importing from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from parser import (
    rule_based_extract,
    generate_rule_based_reply,
    _extract_duration,
    _extract_group_size,
    _extract_budget,
    _extract_travel_time,
    _extract_destination,
    _classify_trip_type,
    _classify_intent,
)


# ---------------------------------------------------------------------------
# Helper extraction tests
# ---------------------------------------------------------------------------

class TestExtractDuration:
    def test_days(self):
        assert _extract_duration("7-day trip to Japan") == "7 days"

    def test_nights(self):
        assert _extract_duration("10 nights in Bali") == "10 nights"

    def test_weeks(self):
        assert _extract_duration("2 weeks vacation") == "14 days"

    def test_none(self):
        assert _extract_duration("I want to travel") is None


class TestExtractGroupSize:
    def test_numeric(self):
        assert _extract_group_size("trip for 2 people") == 2

    def test_word(self):
        assert _extract_group_size("three of us are going") == 3

    def test_couple(self):
        assert _extract_group_size("honeymoon for a couple") == 2

    def test_none(self):
        assert _extract_group_size("I want to travel") is None


class TestExtractBudget:
    def test_dollar_sign(self):
        assert _extract_budget("Budget is $3000") == 3000

    def test_usd_keyword(self):
        assert _extract_budget("around 5000 USD") == 5000

    def test_commas(self):
        assert _extract_budget("budget around $10,000 USD") == 10000

    def test_none(self):
        assert _extract_budget("I want to travel") is None


class TestExtractTravelTime:
    def test_month(self):
        assert _extract_travel_time("trip to Japan in October") == "October"

    def test_relative(self):
        result = _extract_travel_time("I want to travel next month")
        assert result is not None

    def test_none(self):
        assert _extract_travel_time("I want to travel") is None


class TestExtractDestination:
    def test_known_country(self):
        assert _extract_destination("I want to go to Japan") == "Japan"

    def test_city(self):
        assert _extract_destination("Planning a trip to Paris") == "Paris"

    def test_none(self):
        assert _extract_destination("I want to travel somewhere") is None


class TestClassifyTripType:
    def test_honeymoon(self):
        assert _classify_trip_type("planning a honeymoon trip") == "honeymoon"

    def test_family(self):
        assert _classify_trip_type("family-friendly tours in Europe") == "family"

    def test_beach(self):
        assert _classify_trip_type("looking for a beach vacation") == "beach"

    def test_visa(self):
        assert _classify_trip_type("Need visa help for Canada") == "visa assistance"

    def test_default(self):
        assert _classify_trip_type("I want to travel") == "general leisure"


class TestClassifyIntent:
    def test_booking(self):
        assert _classify_intent("I am ready to book") == "booking"

    def test_pricing(self):
        assert _classify_intent("What's the price?") == "pricing inquiry"

    def test_visa(self):
        assert _classify_intent("Need visa help for a trip to Canada") == "visa inquiry"

    def test_planning(self):
        assert _classify_intent("I want to plan a 7-day trip") == "trip planning"


# ---------------------------------------------------------------------------
# Integration tests: rule_based_extract
# ---------------------------------------------------------------------------

class TestRuleBasedExtract:
    def test_full_inquiry(self):
        msg = "Hi, I want to plan a 7-day trip to Japan in October for 2 people. Budget is around 3000 USD."
        fields = rule_based_extract(msg)
        assert fields["destination"] == "Japan"
        assert fields["duration"] == "7 days"
        assert fields["travel_time"] == "October"
        assert fields["group_size"] == 2
        assert fields["budget"] == 3000
        assert fields["missing_fields"] == []

    def test_family_inquiry(self):
        msg = "Do you have family-friendly tours in Europe?"
        fields = rule_based_extract(msg)
        assert fields["destination"] == "Europe"
        assert fields["trip_type"] == "family"
        assert "travel_time" in fields["missing_fields"]
        assert "budget" in fields["missing_fields"]

    def test_vague_inquiry(self):
        msg = "What's the price?"
        fields = rule_based_extract(msg)
        assert fields["destination"] is None
        assert "destination" in fields["missing_fields"]

    def test_booking_inquiry(self):
        msg = "Can someone contact me? I am ready to book."
        fields = rule_based_extract(msg)
        assert fields["intent"] == "booking"

    def test_visa_inquiry(self):
        msg = "Need visa help for a trip to Canada."
        fields = rule_based_extract(msg)
        assert fields["destination"] == "Canada"
        assert fields["trip_type"] == "visa assistance"
        assert fields["intent"] == "visa inquiry"


# ---------------------------------------------------------------------------
# Reply generation tests
# ---------------------------------------------------------------------------

class TestGenerateReply:
    def test_clarifying_when_many_missing(self):
        fields = {
            "destination": None,
            "trip_type": "general leisure",
            "duration": None,
            "travel_time": None,
            "group_size": None,
            "budget": None,
            "intent": "general inquiry",
            "missing_fields": ["destination", "travel_time", "group_size", "budget"],
        }
        reply_type, reply = generate_rule_based_reply(fields)
        assert reply_type == "clarifying_question"
        assert len(reply) > 0

    def test_initial_response_when_complete(self):
        fields = {
            "destination": "Japan",
            "trip_type": "general leisure",
            "duration": "7 days",
            "travel_time": "October",
            "group_size": 2,
            "budget": 3000,
            "intent": "trip planning",
            "missing_fields": [],
        }
        reply_type, reply = generate_rule_based_reply(fields)
        assert reply_type == "initial_response"
        assert "Japan" in reply

    def test_booking_reply_mentions_consultant(self):
        fields = {
            "destination": "Bali",
            "trip_type": "general leisure",
            "duration": None,
            "travel_time": None,
            "group_size": 2,
            "budget": None,
            "intent": "booking",
            "missing_fields": ["travel_time", "budget"],
        }
        reply_type, reply = generate_rule_based_reply(fields)
        # Only 2 missing fields → still clarifying
        assert reply_type == "clarifying_question"


# ---------------------------------------------------------------------------
# Async process_inquiry (rule-based mode — no API key)
# ---------------------------------------------------------------------------

class TestProcessInquiryAsync:
    def test_process_full_inquiry(self):
        """process_inquiry should return all required keys."""
        import asyncio
        import config
        import parser as parser_module

        # Temporarily clear API key to force rule-based fallback
        original_key = config.settings.openai_api_key
        config.settings.openai_api_key = ""
        try:
            msg = "I want to plan a 7-day trip to Japan in October for 2 people. Budget is around $3000."
            result = asyncio.run(parser_module.process_inquiry(msg))
            for key in ["destination", "trip_type", "duration", "travel_time",
                        "group_size", "budget", "intent", "missing_fields",
                        "reply_type", "reply"]:
                assert key in result, f"Missing key: {key}"
            assert result["destination"] == "Japan"
            assert result["reply_type"] == "initial_response"
        finally:
            config.settings.openai_api_key = original_key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
