"""LINE Messaging API Webhook Handler（記帳版）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Optional

import requests

from config.settings import line_config

logger = logging.getLogger(__name__)

LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_DATA_API = "https://api-data.line.me/v2/bot/message"
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class LineSignatureError(Exception):
    pass


class LineWebhookHandler:
    def __init__(self) -> None:
        self.channel_secret = line_config.channel_secret
        self.channel_access_token = line_config.channel_access_token
        self.reply_url = f"{LINE_API_BASE}/message/reply"
        self.push_url = f"{LINE_API_BASE}/message/push"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}",
        }

    def verify_signature(self, body: str, signature: str) -> bool:
        """驗證 LINE Webhook 簽章（HMAC-SHA256）。"""
        hash_value = hmac.new(
            self.channel_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(hash_value).decode("utf-8")
        if not hmac.compare_digest(expected, signature):
            raise LineSignatureError("Invalid signature")
        return True

    def parse_events(self, body: str) -> list[dict]:
        """解析 webhook body，回傳事件清單。"""
        try:
            payload = json.loads(body)
            return payload.get("events", [])
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse webhook body: %s", exc)
            return []

    def extract_text_message(self, event: dict) -> Optional[str]:
        """提取文字訊息內容，非文字事件回傳 None。"""
        if event.get("type") != "message":
            return None
        message = event.get("message", {})
        if message.get("type") != "text":
            return None
        return message.get("text", "").strip() or None

    def extract_image_message(self, event: dict) -> Optional[str]:
        """提取圖片訊息的 message ID，非圖片事件回傳 None。"""
        if event.get("type") != "message":
            return None
        message = event.get("message", {})
        if message.get("type") != "image":
            return None
        return message.get("id")

    def download_image(self, message_id: str) -> Optional[bytes]:
        """
        從 LINE 伺服器下載圖片二進位資料。
        超過 10MB 上限則拒絕下載（優化 ⑦）。
        """
        url = f"{LINE_DATA_API}/{message_id}/content"
        headers = {"Authorization": f"Bearer {self.channel_access_token}"}
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            image_bytes = response.content
            if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                logger.warning(
                    "Image %s exceeds size limit: %d bytes", message_id, len(image_bytes)
                )
                return None
            logger.info("Downloaded image: %s (%d bytes)", message_id, len(image_bytes))
            return image_bytes
        except requests.RequestException as exc:
            logger.error("Failed to download image %s: %s", message_id, exc)
            return None

    def get_user_profile(self, user_id: str) -> Optional[dict]:
        """讀取 LINE 使用者個人資料（含 displayName）。"""
        url = f"{LINE_API_BASE}/profile/{user_id}"
        headers = {"Authorization": f"Bearer {self.channel_access_token}"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.error("Failed to get user profile %s: %s", user_id, exc)
            return None

    def reply_message(self, reply_token: str, text: str) -> bool:
        """透過 reply token 回覆訊息（只能使用一次）。"""
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        }
        try:
            response = requests.post(
                self.reply_url, headers=self.headers, json=payload, timeout=10
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("Failed to send reply: %s", exc)
            return False

    def push_message(self, user_id: str, text: str) -> bool:
        """主動推送訊息給使用者（優化 ⑧：從 main.py 歸位至此）。"""
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": text}],
        }
        try:
            response = requests.post(
                self.push_url, headers=self.headers, json=payload, timeout=10
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("Failed to push message to %s: %s", user_id, exc)
            return False

    def get_reply_token(self, event: dict) -> Optional[str]:
        return event.get("replyToken")

    def get_user_id(self, event: dict) -> Optional[str]:
        return event.get("source", {}).get("userId")
