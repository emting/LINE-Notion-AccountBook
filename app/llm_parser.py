"""LLM 記帳解析引擎。"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional

import requests

from config.settings import llm_config

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_RETRIES = 2
BASE_BACKOFF_SECONDS = 1

SYSTEM_PROMPT = """你是一個專業的補習班記帳助手。將使用者的訊息解析為結構化記帳資料。

請回傳 JSON，欄位包含：title、amount、type、category、date、vendor、payment_method、description、invoice_number、tax_amount。

type 欄位：「收入」或「支出」（依文意判斷）
判斷規則：
1. 「收到」「繳費」「入帳」「退款」「學費」 → 收入
2. 「買」「付」「支付」「花」「購」「修」「租」 → 支出

category 必須落在以下 14 項之一：
【收入類】學費收入、教材收入、報名費、其他收入
【支出類】教材費、房租水電、人事費用、設備維護、辦公用品、餐飲點心、交通費、廣告行銷、保險稅務、其他支出

payment_method 必須落在以下之一：
現金、刷卡、轉帳、LINE Pay、未指定 (注意大小寫與空格)

請只回傳 JSON，不要包含 markdown。"""

VALID_CATEGORIES = frozenset({
    "學費收入", "教材收入", "報名費", "其他收入",
    "教材費", "房租水電", "人事費用", "設備維護",
    "辦公用品", "餐飲點心", "交通費", "廣告行銷",
    "保險稅務", "其他支出",
})

VALID_PAYMENT_METHODS = frozenset({
    "現金", "刷卡", "轉帳", "LINE Pay", "未指定"
})


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
        """向 Gemini API 發送請求，失敗時指數退避重試（最多 MAX_RETRIES 次）。"""
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
                    "LLM request failed on attempt %d: %s", attempt + 1, exc
                )
                if is_last_attempt:
                    logger.error("LLM API failed after %d retries: %s", MAX_RETRIES, exc)
                    return None
                time.sleep(BASE_BACKOFF_SECONDS * (2 ** attempt))

        return None

    def parse(self, text: str) -> Optional[dict]:
        """
        將自然語言文字解析為結構化記帳 dict。

        Args:
            text: 使用者輸入的記帳訊息

        Returns:
            已驗證的 dict，或 None（解析失敗）
        """
        if not self.enabled:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        full_prompt = f"{SYSTEM_PROMPT}\n今天日期：{today}\n\n使用者訊息：{text}"

        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
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
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None

            text_result = parts[0].get("text", "").strip()
            if text_result.startswith("```"):
                lines = text_result.split("\n")
                text_result = "\n".join(lines[1:-1])

            parsed = json.loads(text_result)
            return self._validate_result(parsed)

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM JSON: %s", exc)
            return None

    def _validate_result(self, parsed: dict) -> Optional[dict]:
        """驗證並正規化 LLM 回傳的記帳資料。"""
        title = str(parsed.get("title", "")).strip()
        if not title:
            return None

        amount = parsed.get("amount")
        try:
            amount = abs(float(amount)) if amount else 0
        except (TypeError, ValueError):
            amount = 0

        entry_type = parsed.get("type", "支出")
        if entry_type not in {"收入", "支出"}:
            entry_type = "支出"

        category = parsed.get("category", "其他支出")
        if category not in VALID_CATEGORIES:
            category = "其他收入" if entry_type == "收入" else "其他支出"

        payment_method = parsed.get("payment_method", "未指定")
        # 簡單的正規化處理
        if "line" in payment_method.lower() and "pay" in payment_method.lower():
            payment_method = "LINE Pay"
        elif payment_method not in VALID_PAYMENT_METHODS:
            payment_method = "未指定"

        return {
            "title": title,
            "amount": amount,
            "type": entry_type,
            "category": category,
            "date": parsed.get("date"),
            "vendor": parsed.get("vendor", ""),
            "payment_method": payment_method,
            "description": parsed.get("description", ""),
            "invoice_number": parsed.get("invoice_number", ""),
            "tax_amount": parsed.get("tax_amount", 0),
        }

    def is_available(self) -> bool:
        return self.enabled
