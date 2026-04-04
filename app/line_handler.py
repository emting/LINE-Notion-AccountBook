"""
LINE Messaging API Webhook Handler.

This module handles incoming webhook events from the LINE Platform,
verifies request signatures, and extracts user messages for processing.
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
    """Raised when LINE webhook signature verification fails."""
    pass


class LineWebhookHandler:
    """Handles LINE Messaging API webhook events."""

    def __init__(self):
        self.channel_secret = line_config.channel_secret
        self.channel_access_token = line_config.channel_access_token
        self.reply_url = "https://api.line.me/v2/bot/message/reply"

    def verify_signature(self, body: str, signature: str) -> bool:
        """
        Verify the webhook request signature from LINE Platform.

        The LINE Platform sends a signature in the X-Line-Signature header.
        We compute the expected signature using HMAC-SHA256 with the channel
        secret and compare it against the received signature.

        Args:
            body: Raw request body as a string.
            signature: The X-Line-Signature header value.

        Returns:
            True if the signature is valid.

        Raises:
            LineSignatureError: If the signature does not match.
        """
        hash_value = hmac.new(
            self.channel_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_signature = base64.b64encode(hash_value).decode("utf-8")

        if not hmac.compare_digest(expected_signature, signature):
            logger.warning("LINE signature verification failed.")
            raise LineSignatureError("Invalid signature")

        return True

    def parse_events(self, body: str) -> list[dict]:
        """
        Parse webhook body and extract event objects.

        Args:
            body: Raw request body as a JSON string.

        Returns:
            A list of event dictionaries from the webhook payload.
        """
        try:
            payload = json.loads(body)
            events = payload.get("events", [])
            logger.info("Parsed %d event(s) from LINE webhook.", len(events))
            return events
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LINE webhook body: %s", e)
            return []

    def extract_text_message(self, event: dict) -> Optional[str]:
        """
        Extract text content from a message event.

        Only processes events of type 'message' with message type 'text'.
        Other event types (e.g., follow, unfollow, postback) are ignored.

        Args:
            event: A single webhook event dictionary.

        Returns:
            The text content if the event is a text message, otherwise None.
        """
        if event.get("type") != "message":
            logger.debug("Skipping non-message event: %s", event.get("type"))
            return None

        message = event.get("message", {})
        if message.get("type") != "text":
            logger.debug("Skipping non-text message: %s", message.get("type"))
            return None

        text = message.get("text", "").strip()
        logger.info("Extracted text message: '%s'", text[:50])
        return text if text else None

    def get_user_profile(self, user_id: str) -> Optional[dict]:
        """
        Retrieve the user's LINE profile information.

        Args:
            user_id: The LINE user ID.

        Returns:
            A dictionary containing displayName, userId, pictureUrl, etc.
        """
        url = f"https://api.line.me/v2/bot/profile/{user_id}"
        headers = {"Authorization": f"Bearer {self.channel_access_token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error("Failed to get user profile: %s", e)
            return None

    def reply_message(self, reply_token: str, text: str) -> bool:
        """
        Send a reply message back to the user via LINE.

        Args:
            reply_token: The reply token from the webhook event.
            text: The text message to send.

        Returns:
            True if the reply was sent successfully, False otherwise.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}",
        }
        payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        }

        try:
            response = requests.post(
                self.reply_url,
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Reply sent successfully.")
            return True
        except requests.RequestException as e:
            logger.error("Failed to send reply: %s", e)
            return False

    def get_reply_token(self, event: dict) -> Optional[str]:
        """
        Extract the reply token from a webhook event.

        Args:
            event: A single webhook event dictionary.

        Returns:
            The reply token string, or None if not available.
        """
        return event.get("replyToken")

    def get_user_id(self, event: dict) -> Optional[str]:
        """
        Extract the user ID from a webhook event's source.

        Args:
            event: A single webhook event dictionary.

        Returns:
            The user ID string, or None if not available.
        """
        source = event.get("source", {})
        return source.get("userId")
