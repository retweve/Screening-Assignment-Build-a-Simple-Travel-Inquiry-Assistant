"""
config.py - Application configuration loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_api_base: str = os.getenv(
        "OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions"
    )
    ai_model: str = os.getenv("AI_MODEL", "gpt-4o-mini")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
