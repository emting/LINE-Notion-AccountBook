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
    """OpenAI-compatible LLM API configuration."""
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    base_url: str = os.getenv("OPENAI_BASE_URL", "")
    model: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")


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
