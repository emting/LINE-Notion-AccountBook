"""
補習班記帳系統 — 組態設定
所有敏感資訊透過環境變數載入。
"""

import os
from dataclasses import dataclass

@dataclass
class LineConfig:
    """LINE Messaging API 設定"""
    channel_access_token: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    channel_secret: str = os.getenv("LINE_CHANNEL_SECRET", "")

@dataclass
class NotionConfig:
    """Notion API 設定"""
    api_key: str = os.getenv("NOTION_API_KEY", "")
    database_id: str = os.getenv("NOTION_DATABASE_ID", "")
    api_version: str = "2022-06-28"

@dataclass
class LLMConfig:
    """Google Gemini API 設定（含 Vision OCR）"""
    api_key: str = os.getenv("GEMINI_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "models/gemini-2.5-flash")
    # Vision model 用於 OCR（同一模型即支援 multimodal）
    vision_model: str = os.getenv("VISION_MODEL", "models/gemini-2.5-flash")

@dataclass
class AppConfig:
    """應用程式設定"""
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "5000"))
    debug: bool = os.getenv("APP_DEBUG", "false").lower() == "true"
    # 補習班名稱（用於回覆訊息）
    school_name: str = os.getenv("SCHOOL_NAME", "我的補習班")

line_config = LineConfig()
notion_config = NotionConfig()
llm_config = LLMConfig()
app_config = AppConfig()
