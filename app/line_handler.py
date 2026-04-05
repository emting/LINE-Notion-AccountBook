"""
LINE Messaging API Webhook Handler（記帳版）。
新增：圖片訊息接收與下載功能，支援發票/收據 OCR。
"""

import hashlib
import hmac
import base64
import json
import logging
from typing import Optional

import requests

from config.settings import line_config

logger = logging.getLogger(__name__)

class LineSignatureError(Exception):
    pass

class LineWebhookHandler:
    def __init__(self):
        self.channel_secret = line_config.channel_secret
        self.channel_access_token = line_config.channel_access_token
        self.reply_url = "https://api.line.me/v2/bot/message/reply"
        self.content_url = "https://api-data.line.me/v2/bot/message/{}/content"

    def verify_signature(self, body: str, signature: str) -> bool:
        if not self.channel_secret:
            logger.warning("Channel secret is not configured. Skipping signature verification.")
            return True
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
        try:
            payload = json.loads(body)
            return payload.get("events", [])
        except json.JSONDecodeError as e:
            logger.error("Failed to parse webhook body: %s", e)
            return []

    def extract_text_message(self, event: dict) -> Optional[str]:
        """提取文字訊息。"""
        if event.get("type") != "message":
            return None
        message = event.get("message", {})
        if message.get("type") != "text":
            return None
        return message.get("text", "").strip() or None

    def extract_image_message(self, event: dict) -> Optional[str]:
        """
        提取圖片訊息的 message ID。
        回傳 message_id 供後續下載圖片使用。
        """
        if event.get("type") != "message":
            return None
        message = event.get("message", {})
        if message.get("type") != "image":
            return None
        return message.get("id")

    def download_image(self, message_id: str) -> Optional[bytes]:
        """
        從 LINE 伺服器下載圖片二進位資料。
        用於發票/收據 OCR 辨識。
        """
        url = self.content_url.format(message_id)
        headers = {"Authorization": f"Bearer {self.channel_access_token}"}
        try:
            # 加入 10MB 上限驗證 (Optimization #7)
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()
            
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > 10 * 1024 * 1024:
                logger.warning("Image size exceeds 10MB limit: %s", content_length)
                return None
                
            content = response.content
            logger.info("Downloaded image: %s (%d bytes)",
                        message_id, len(content))
            return content
        except requests.RequestException as e:
            logger.error("Failed to download image %s: %s", message_id, e)
            return None

    def get_user_profile(self, user_id: str) -> Optional[dict]:
        url = f"https://api.line.me/v2/bot/profile/{user_id}"
        headers = {"Authorization": f"Bearer {self.channel_access_token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            return None

    def reply_message(self, reply_token: str, text: str) -> bool:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}",
        }
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        }
        try:
            resp = requests.post(self.reply_url, headers=headers,
                                json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("Failed to send reply: %s", e)
            return False

    def push_message(self, user_id: str, text: str) -> bool:
        """
        主動推送訊息給使用者（用於 OCR 非同步回覆）。
        (Optimization #8: Moved from main.py)
        """
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}",
        }
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": text}],
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Push message failed: %s", e)
            return False

    def get_reply_token(self, event: dict) -> Optional[str]:
        return event.get("replyToken")

    def get_user_id(self, event: dict) -> Optional[str]:
        return event.get("source", {}).get("userId")
