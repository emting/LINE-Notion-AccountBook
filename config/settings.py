"""
Configuration settings for LINE-Notion-Sync.

All sensitive credentials are loaded from environment variables.
Copy .env.example to .env and fill in your actual values before running.
"""

import os
from dataclasses import dataclass


@dataclass
class LineConfig:
    """LINE Messaging API configuration."""
    channel_access_token: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    channel_secret: str = os.getenv("LINE_CHANNEL_SECRET", "")


@dataclass
class NotionConfig:
    """Notion API configuration."""
    api_key: str = os.getenv("NOTION_API_KEY", "")
    database_id: str = os.getenv("NOTION_DATABASE_ID", "")
    api_version: str = "2022-06-28"


@dataclass
class LLMConfig:
    """
    Google Gemini API configuration.

    Uses GEMINI_API_KEY as the primary key.
    Model defaults to gemini-2.0-flash which offers the best balance of
    speed and capability for task parsing.
    """
    api_key: str = os.getenv("GEMINI_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "models/gemini-2.5-flash")
    # base_url kept for compatibility but not used with Gemini
    base_url: str = os.getenv("LLM_BASE_URL", "")


@dataclass
class AppConfig:
    """Application-level configuration."""
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "5000"))
    debug: bool = os.getenv("APP_DEBUG", "false").lower() == "true"


# Singleton instances
line_config = LineConfig()
notion_config = NotionConfig()
llm_config = LLMConfig()
app_config = AppConfig()
