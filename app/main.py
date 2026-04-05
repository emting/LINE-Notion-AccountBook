"""
LINE-Notion-AccountBook: 補習班記帳系統主入口。
支援文字記帳 + 發票/收據圖片 OCR。
"""

import sys
import os
import logging
import threading

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, abort, jsonify

from app.line_handler import LineWebhookHandler, LineSignatureError
from app.notion_client import NotionAccountClient, NotionClientError
from app.data_processor import DataProcessor
from config.settings import app_config, validate_config, ConfigValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
line_handler = LineWebhookHandler()
notion_client = NotionAccountClient()
data_processor = DataProcessor()

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "service": "LINE-Notion-AccountBook",
        "version": "3.1.0",
        "school": app_config.school_name,
        "llm_engine": "active" if data_processor.llm_parser.is_available() else "inactive",
        "ocr_engine": "active" if data_processor.ocr_engine.is_available() else "inactive",
    })

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        abort(400, description="Missing X-Line-Signature header")

    body = request.get_data(as_text=True)

    try:
        line_handler.verify_signature(body, signature)
    except LineSignatureError:
        abort(403, description="Invalid signature")

    events = line_handler.parse_events(body)
    for event in events:
        try:
            _process_event(event)
        except Exception as e:
            logger.error("Error processing event: %s", e, exc_info=True)

    return "OK", 200

def _process_event(event: dict) -> None:
    """處理單一 LINE 事件（文字或圖片）。"""
    user_id = line_handler.get_user_id(event)
    reply_token = line_handler.get_reply_token(event)

    user_name = "Unknown"
    if user_id:
        profile = line_handler.get_user_profile(user_id)
        if profile:
            user_name = profile.get("displayName", "Unknown")

    # ── 文字訊息 ──────────────────────────
    text = line_handler.extract_text_message(event)
    if text:
        # 特殊指令
        if text.lower() in ("/help", "help", "幫助"):
            _send_help(reply_token)
            return
        if text.lower() in ("/status", "status", "狀態"):
            _send_status(reply_token)
            return

        entry = data_processor.process_text(text)
        if not entry.title or entry.amount == 0:
            line_handler.reply_message(
                reply_token,
                "無法解析金額，請重新輸入。\n\n"
                "支援格式：\n"
                "1. 自由輸入：買了 30 本講義 $4500\n"
                "2. 結構化：摘要: 講義 | 金額: 4500 | 類型: 支出\n"
                "3. 指令：/支 講義 4500\n"
                "4. 📸 直接拍發票照片",
            )
            return

        _write_to_notion(entry, user_name, reply_token)
        return

    # ── 圖片訊息（OCR）───────────────────
    image_id = line_handler.extract_image_message(event)
    if image_id:
        line_handler.reply_message(
            reply_token,
            "📸 收到圖片，正在進行 OCR 辨識中..."
        )
        
        # Bug #4: OCR 辨識耗時，改用背景執行緒處理 (非同步)
        threading.Thread(
            target=_process_image_async,
            args=(image_id, user_name, user_id),
            daemon=True,
        ).start()

def _process_image_async(image_id: str, user_name: str, user_id: str):
    """背景處理圖片 OCR 並寫入 Notion。"""
    try:
        image_bytes = line_handler.download_image(image_id)
        if not image_bytes:
            return

        entry = data_processor.process_image(image_bytes)
        if entry.amount == 0 and entry.parse_confidence < 0.3:
            logger.warning("OCR failed or no amount detected for image %s", image_id)
            line_handler.push_message(user_id, "⚠️ 無法從圖片中辨識出有效的金額或品項。")
            return

        # 寫入 Notion 並發送 Push Message
        notion_client.create_account_entry(
            title=entry.title,
            amount=entry.amount,
            entry_type=entry.entry_type,
            category=entry.category,
            date=entry.date,
            vendor=entry.vendor,
            payment_method=entry.payment_method,
            description=entry.description,
            invoice_number=entry.invoice_number,
            tax_amount=entry.tax_amount,
            source_user=user_name,
        )
        confirmation = data_processor.format_confirmation(entry)
        line_handler.push_message(user_id, confirmation)
        
    except Exception as e:
        logger.error("Async OCR processing error: %s", e, exc_info=True)
        line_handler.push_message(user_id, f"❌ 處理圖片時發生錯誤：{str(e)}")

def _write_to_notion(entry, user_name, reply_token):
    """文字訊息場景：寫入 Notion 並用 reply 回覆。"""
    try:
        notion_client.create_account_entry(
            title=entry.title,
            amount=entry.amount,
            entry_type=entry.entry_type,
            category=entry.category,
            date=entry.date,
            vendor=entry.vendor,
            payment_method=entry.payment_method,
            description=entry.description,
            invoice_number=entry.invoice_number,
            tax_amount=entry.tax_amount,
            source_user=user_name,
        )
        confirmation = data_processor.format_confirmation(entry)
        line_handler.reply_message(reply_token, confirmation)
    except NotionClientError as e:
        line_handler.reply_message(
            reply_token,
            f"寫入 Notion 時發生錯誤：{e}\n請確認資料庫設定。",
        )

def _send_help(reply_token):
    help_text = (
        f"📖 {app_config.school_name} 記帳系統\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📝 文字記帳：\n"
        "  買了 30 本數學講義 $4,500\n\n"
        "📸 拍照記帳：\n"
        "  直接拍發票或收據照片\n\n"
        "📋 結構化輸入：\n"
        "  摘要: 講義 | 金額: 4500 | 類型: 支出\n\n"
        "⌨️ 指令格式：\n"
        "  /支 數學講義 4500\n"
        "  /收 王小明學費 12000\n\n"
        "🔧 其他指令：\n"
        "  /help - 顯示此說明\n"
        "  /status - 查看系統狀態"
    )
    line_handler.reply_message(reply_token, help_text)

def _send_status(reply_token):
    llm = "已啟用" if data_processor.llm_parser.is_available() else "未設定"
    ocr = "已啟用" if data_processor.ocr_engine.is_available() else "未設定"
    status_text = (
        f"✅ {app_config.school_name} 記帳系統\n\n"
        f"🧠 LLM 智慧解析：{llm}\n"
        f"📸 OCR 發票辨識：{ocr}\n"
        f"🔗 Notion 連線：正常"
    )
    line_handler.reply_message(reply_token, status_text)

if __name__ == "__main__":
    try:
        validate_config()
    except ConfigValidationError as e:
        logger.warning("Config validation warning: %s", e)
    app.run(
        host=app_config.host,
        port=app_config.port,
        debug=app_config.debug,
    )
