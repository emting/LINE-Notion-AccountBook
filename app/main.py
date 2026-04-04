"""
LINE-Notion-Sync: Main Application Entry Point.

This Flask application serves as the webhook endpoint for LINE Messaging API.
When a user sends a text message via LINE, the application:

    1. Receives and verifies the webhook event from LINE Platform.
    2. Extracts the text content from the message event.
    3. Processes and parses the text into structured task data.
    4. Creates a corresponding entry in the configured Notion database.
    5. Sends a confirmation reply back to the user via LINE.

Usage:
    python -m app.main

Environment Variables Required:
    LINE_CHANNEL_ACCESS_TOKEN  - LINE Messaging API channel access token
    LINE_CHANNEL_SECRET        - LINE Messaging API channel secret
    NOTION_API_KEY             - Notion integration API key (internal integration)
    NOTION_DATABASE_ID         - Target Notion database ID
"""

import sys
import os
import logging

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, abort, jsonify

from app.line_handler import LineWebhookHandler, LineSignatureError
from app.notion_client import NotionDatabaseClient, NotionClientError
from app.data_processor import DataProcessor
from config.settings import app_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize service components
line_handler = LineWebhookHandler()
notion_client = NotionDatabaseClient()
data_processor = DataProcessor()


@app.route("/", methods=["GET"])
def health_check():
    """
    Health check endpoint.

    Returns a simple JSON response to confirm the server is running.
    Useful for monitoring and load balancer health checks.
    """
    return jsonify({
        "status": "ok",
        "service": "LINE-Notion-Sync",
        "version": "1.0.0",
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    LINE Messaging API Webhook Endpoint.

    This endpoint receives POST requests from the LINE Platform whenever
    a user interacts with the LINE Official Account. The full processing
    pipeline is executed here:

        LINE Platform → Signature Verification → Event Parsing →
        Text Extraction → Data Processing → Notion Write → LINE Reply

    Returns:
        200 OK on success (required by LINE Platform).
        400 Bad Request if the signature header is missing.
        403 Forbidden if signature verification fails.
        500 Internal Server Error on unexpected failures.
    """
    # Step 1: Get the request signature
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        logger.warning("Missing X-Line-Signature header.")
        abort(400, description="Missing X-Line-Signature header")

    # Step 2: Get the raw request body
    body = request.get_data(as_text=True)
    logger.info("Received webhook request (body length: %d)", len(body))

    # Step 3: Verify the signature
    try:
        line_handler.verify_signature(body, signature)
    except LineSignatureError:
        logger.warning("Signature verification failed.")
        abort(403, description="Invalid signature")

    # Step 4: Parse events from the webhook body
    events = line_handler.parse_events(body)

    # Step 5: Process each event
    for event in events:
        try:
            _process_event(event)
        except Exception as e:
            logger.error("Error processing event: %s", e, exc_info=True)
            # Continue processing other events even if one fails

    return "OK", 200


def _process_event(event: dict) -> None:
    """
    Process a single LINE webhook event.

    This function orchestrates the full pipeline for a single event:
    extract text, parse it, write to Notion, and reply to the user.

    Args:
        event: A single webhook event dictionary from LINE.
    """
    # Extract text message
    text = line_handler.extract_text_message(event)
    if not text:
        return

    user_id = line_handler.get_user_id(event)
    reply_token = line_handler.get_reply_token(event)

    # Get user profile for the source field
    user_name = "Unknown"
    if user_id:
        profile = line_handler.get_user_profile(user_id)
        if profile:
            user_name = profile.get("displayName", "Unknown")

    logger.info("Processing message from '%s': '%s'", user_name, text[:80])

    # Handle special commands
    if text.lower() in ("/help", "help", "幫助"):
        _send_help_message(reply_token)
        return

    if text.lower() in ("/status", "status", "狀態"):
        _send_status_message(reply_token)
        return

    # Parse the message into structured task data
    task = data_processor.process(text)

    if not task.title:
        line_handler.reply_message(
            reply_token,
            "無法解析您的訊息，請重新輸入。\n\n"
            "支援的格式：\n"
            "1. 自由輸入：明天下午三點要開會\n"
            "2. 結構化：標題: 開會 | 日期: 2026-04-05 | 優先級: 高\n"
            "3. 指令：/task 開會 --priority high --date 2026-04-05",
        )
        return

    # Write to Notion database
    try:
        notion_client.create_task_entry(
            title=task.title,
            category=task.category,
            priority=task.priority,
            due_date=task.due_date,
            description=task.description,
            source_user=user_name,
            status="Not Started",
        )
        logger.info("Task '%s' written to Notion successfully.", task.title)

        # Send confirmation reply
        confirmation = data_processor.format_confirmation_message(task)
        line_handler.reply_message(reply_token, confirmation)

    except NotionClientError as e:
        logger.error("Failed to write to Notion: %s", e)
        line_handler.reply_message(
            reply_token,
            f"寫入 Notion 資料庫時發生錯誤：{str(e)}\n請確認 Notion 設定是否正確。",
        )


def _send_help_message(reply_token: str) -> None:
    """Send a help message explaining supported input formats."""
    help_text = (
        "📖 LINE-Notion-Sync 使用說明\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📝 自由輸入（自動解析）：\n"
        "  明天下午三點要開會，優先級高\n\n"
        "📋 結構化輸入：\n"
        "  標題: 開會 | 日期: 2026-04-05 | 優先級: 高\n\n"
        "⌨️ 指令格式：\n"
        "  /task 開會 --priority high --date 2026-04-05\n\n"
        "🔧 其他指令：\n"
        "  /help - 顯示此說明\n"
        "  /status - 查看系統狀態"
    )
    line_handler.reply_message(reply_token, help_text)


def _send_status_message(reply_token: str) -> None:
    """Send a status message showing the system's current state."""
    try:
        schema = notion_client.get_database_schema()
        prop_names = list(schema.keys())
        status_text = (
            "✅ 系統狀態正常\n\n"
            f"📊 Notion 資料庫欄位：\n"
            f"  {', '.join(prop_names)}\n\n"
            f"🔗 連線狀態：正常"
        )
    except NotionClientError:
        status_text = (
            "⚠️ 系統狀態異常\n\n"
            "❌ 無法連線至 Notion 資料庫\n"
            "請確認 NOTION_API_KEY 和 NOTION_DATABASE_ID 是否正確設定。"
        )

    line_handler.reply_message(reply_token, status_text)


if __name__ == "__main__":
    logger.info(
        "Starting LINE-Notion-Sync server on %s:%d",
        app_config.host,
        app_config.port,
    )
    app.run(
        host=app_config.host,
        port=app_config.port,
        debug=app_config.debug,
    )
