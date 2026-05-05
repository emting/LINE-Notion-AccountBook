"""LLM 記帳解析引擎。"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Optional

import requests

from config.settings import llm_config

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_RETRIES = 2
BASE_BACKOFF_SECONDS = 1

SYSTEM_PROMPT = """你是一個專業的補習班記帳助手。將使用者的訊息解析為結構化記帳資料。

請回傳單個 JSON 物件，絕對不要回傳列表或陣列。
如果使用者訊息包含多筆交易，請只解析第一筆交易。

欄位包含：
title、amount、type、category、date、vendor、payment_method、description、invoice_number、tax_amount。

欄位規則：
1. amount 與 tax_amount 必須是數字，不要包含逗號、貨幣符號或單位。
2. date 必須使用 YYYY-MM-DD 格式。
3. vendor、description、invoice_number 若無法判斷，請填空字串。
4. payment_method 若無法判斷，請填「未指定」。

type 欄位：「收入」或「支出」（依文意判斷）
判斷規則：
1. 「收到」「繳費」「入帳」「退款」「學費」 → 收入
2. 「買」「付」「支付」「花」「購」「修」「租」 → 支出

category 必須落在以下 14 項之一：
【收入類】學費收入、教材收入、報名費、其他收入
【支出類】教材費、房租水電、人事費用、設備維護、辦公用品、餐飲點心、交通費、廣告行銷、保險稅務、其他支出

payment_method 必須落在以下之一：
現金、刷卡、轉帳、LINE Pay、未指定

請只回傳 JSON，不要包含 markdown。"""

INCOME_CATEGORIES = frozenset({
    "學費收入",
    "教材收入",
    "報名費",
    "其他收入",
})

EXPENSE_CATEGORIES = frozenset({
    "教材費",
    "房租水電",
    "人事費用",
    "設備維護",
    "辦公用品",
    "餐飲點心",
    "交通費",
    "廣告行銷",
    "保險稅務",
    "其他支出",
})

VALID_CATEGORIES = INCOME_CATEGORIES | EXPENSE_CATEGORIES

VALID_PAYMENT_METHODS = frozenset({
    "現金",
    "刷卡",
    "轉帳",
    "LINE Pay",
    "未指定",
})


def _safe_string(value: Any) -> str:
    """安全轉換為去除前後空白的字串。"""
    return str(value or "").strip()


def _normalize_amount(value: Any) -> float:
    """將金額欄位正規化為非負浮點數。"""
    if value is None or value == "":
        return 0.0

    try:
        if isinstance(value, str):
            cleaned = value.strip()

            # 移除常見貨幣符號、單位與分隔符號
            cleaned = cleaned.replace(",", "")
            cleaned = cleaned.replace("NT$", "")
            cleaned = cleaned.replace("NTD", "")
            cleaned = cleaned.replace("TWD", "")
            cleaned = cleaned.replace("NT", "")
            cleaned = cleaned.replace("$", "")
            cleaned = cleaned.replace("元", "")
            cleaned = cleaned.strip()

            # 若字串中仍包含其他文字，嘗試抓第一個數字
            # 例如：「約 1,200 元」經前面處理後可能變成「約 1200」
            match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
            if match:
                cleaned = match.group(0)

            return abs(float(cleaned))

        return abs(float(value))

    except (TypeError, ValueError):
        logger.warning("Unable to normalize amount: %r", value)
        return 0.0


def _normalize_type(value: Any) -> str:
    """正規化收入/支出類型。"""
    entry_type = _safe_string(value)

    if entry_type in {"收入", "支出"}:
        return entry_type

    return "支出"


def _normalize_category(value: Any, entry_type: str) -> str:
    """依收入/支出類型正規化類別，避免類別與類型錯配。"""
    category = _safe_string(value)

    if entry_type == "收入":
        if category in INCOME_CATEGORIES:
            return category
        return "其他收入"

    if category in EXPENSE_CATEGORIES:
        return category

    return "其他支出"


def _normalize_payment_method(value: Any) -> str:
    """正規化付款方式。"""
    payment_method = _safe_string(value)

    if not payment_method:
        return "未指定"

    lower_value = payment_method.lower()

    if "line" in lower_value and "pay" in lower_value:
        return "LINE Pay"

    aliases = {
        "信用卡": "刷卡",
        "卡": "刷卡",
        "刷信用卡": "刷卡",
        "刷卡付款": "刷卡",
        "匯款": "轉帳",
        "銀行轉帳": "轉帳",
        "轉帳付款": "轉帳",
        "現金付款": "現金",
        "cash": "現金",
        "credit card": "刷卡",
        "card": "刷卡",
        "transfer": "轉帳",
        "bank transfer": "轉帳",
        "linepay": "LINE Pay",
        "line pay": "LINE Pay",
    }

    if payment_method in aliases:
        return aliases[payment_method]

    if lower_value in aliases:
        return aliases[lower_value]

    if payment_method in VALID_PAYMENT_METHODS:
        return payment_method

    return "未指定"


def _normalize_date(value: Any) -> str:
    """簡單正規化日期，無法判斷時回傳今天。"""
    today = datetime.now().strftime("%Y-%m-%d")

    if value is None or value == "":
        return today

    date_text = _safe_string(value)

    if date_text in {"今天", "今日"}:
        return today

    # 接受 YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        try:
            return datetime.strptime(date_text, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            return today

    # 接受 YYYY/M/D 或 YYYY/MM/DD
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", date_text):
        try:
            return datetime.strptime(date_text, "%Y/%m/%d").strftime("%Y-%m-%d")
        except ValueError:
            return today

    # 接受 YYYY.M.D 或 YYYY.MM.DD
    if re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", date_text):
        try:
            return datetime.strptime(date_text, "%Y.%m.%d").strftime("%Y-%m-%d")
        except ValueError:
            return today

    return today


class LLMParser:
    """將自然語言記帳訊息解析為結構化資料。"""

    def __init__(self) -> None:
        self.api_key = llm_config.api_key
        self.model = llm_config.model
        self.enabled = bool(self.api_key)

        if self.enabled:
            logger.info("LLM Parser initialized with model: %s", self.model)
        else:
            logger.warning("LLM Parser disabled: GEMINI_API_KEY not configured.")

    def _post_with_retry(self, payload: dict) -> Optional[dict]:
        """向 Gemini API 發送請求，失敗時指數退避重試。"""
        if not self.api_key:
            return None

        url = f"{GEMINI_BASE}/{self.model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json=payload,
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()

            except requests.RequestException as exc:
                is_last_attempt = attempt == MAX_RETRIES

                logger.warning(
                    "LLM request failed on attempt %d/%d: %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    exc,
                )

                if is_last_attempt:
                    logger.error(
                        "LLM API failed after %d retries: %s",
                        MAX_RETRIES,
                        exc,
                    )
                    return None

                time.sleep(BASE_BACKOFF_SECONDS * (2 ** attempt))

        return None

    def parse(self, text: str) -> Optional[dict]:
        """
        將自然語言文字解析為結構化記帳 dict。

        Args:
            text: 使用者輸入的記帳訊息。

        Returns:
            已驗證且正規化後的 dict，或 None。
        """
        if not self.enabled:
            return None

        text = _safe_string(text)
        if not text:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        full_prompt = f"{SYSTEM_PROMPT}\n今天日期：{today}\n\n使用者訊息：{text}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": full_prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 800,
                "responseMimeType": "application/json",
            },
        }

        data = self._post_with_retry(payload)
        if not data:
            return None

        try:
            candidates = data.get("candidates", [])
            if not candidates:
                logger.error("LLM response has no candidates.")
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                logger.error("LLM response has no content parts.")
                return None

            text_result = parts[0].get("text", "").strip()
            if not text_result:
                logger.error("LLM response text is empty.")
                return None

            text_result = self._strip_markdown_code_block(text_result)

            parsed = json.loads(text_result)
            return self._validate_result(parsed)

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM JSON: %s", exc)
            return None

        except Exception as exc:
            logger.exception("Unexpected error while parsing LLM response: %s", exc)
            return None

    def _strip_markdown_code_block(self, text_result: str) -> str:
        """移除 LLM 可能回傳的 markdown code block。"""
        text_result = text_result.strip()

        if not text_result.startswith("```"):
            return text_result

        lines = text_result.splitlines()

        # 例如：
        # ```json
        # {...}
        # ```
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()

        # 保底處理：直接移除反引號
        return text_result.strip("`").strip()

    def _validate_result(self, parsed: Any) -> Optional[dict]:
        """驗證並正規化 LLM 回傳的記帳資料。"""
        if isinstance(parsed, list):
            if not parsed:
                logger.error("LLM returned an empty list.")
                return None

            logger.warning(
                "LLM returned a list with %d item(s); using the first item.",
                len(parsed),
            )
            parsed = parsed[0]

        if not isinstance(parsed, dict):
            logger.error("LLM result is not a dict: %s", type(parsed))
            return None

        title = _safe_string(parsed.get("title"))
        if not title:
            logger.error("LLM result missing title.")
            return None

        amount = _normalize_amount(parsed.get("amount"))
        tax_amount = _normalize_amount(parsed.get("tax_amount"))

        entry_type = _normalize_type(parsed.get("type"))
        category = _normalize_category(parsed.get("category"), entry_type)
        payment_method = _normalize_payment_method(parsed.get("payment_method"))
        date = _normalize_date(parsed.get("date"))

        return {
            "title": title,
            "amount": amount,
            "type": entry_type,
            "category": category,
            "date": date,
            "vendor": _safe_string(parsed.get("vendor")),
            "payment_method": payment_method,
            "description": _safe_string(parsed.get("description")),
            "invoice_number": _safe_string(parsed.get("invoice_number")),
            "tax_amount": tax_amount,
        }

    def is_available(self) -> bool:
        """確認 LLM Parser 是否可用。"""
        return self.enabled
