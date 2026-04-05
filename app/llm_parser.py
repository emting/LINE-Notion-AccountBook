"""
LLM 記帳解析引擎 — 將自然語言轉為結構化記帳資料。
專為補習班收支場景最佳化 System Prompt。
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional

import requests

from config.settings import llm_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一個專業的補習班記帳助手。將使用者的訊息解析為結構化記帳資料。

請提取以下欄位並以 JSON 回傳：

{
  "title": "記帳摘要（簡潔描述）",
  "amount": 金額（正數）,
  "type": "收入" 或 "支出",
  "category": "分類",
  "date": "日期 YYYY-MM-DD 或 null",
  "vendor": "對象/廠商名稱（若有）",
  "payment_method": "現金/刷卡/轉帳/LINE Pay/未指定",
  "description": "完整描述",
  "invoice_number": "發票號碼（若有）",
  "tax_amount": 稅額（若有）
}

分類規則（category 必須是以下之一）：
【收入類】
- 學費收入：學生繳交的學費、補習費、課程費
- 教材收入：販售講義、課本的收入
- 報名費：新生報名費、活動報名費
- 其他收入：利息、補助款、退款收回等

【支出類】
- 教材費：購買講義、教科書、文具
- 房租水電：房租、水費、電費、網路費
- 人事費用：教師薪資、助教費、工讀費
- 設備維護：電腦、投影機、冷氣維修
- 辦公用品：影印紙、墨水匣、辦公耗材
- 餐飲點心：學生點心、教師餐費
- 交通費：交通、停車、油費
- 廣告行銷：傳單、網路廣告、招牌
- 保險稅務：保險費、稅金
- 其他支出：無法歸類的支出

判斷規則：
1. 「收到」「繳費」「入帳」→ 收入
2. 「買」「付」「繳」「支付」「花」→ 支出
3. 未明確指定類型時，根據內容智慧判斷
4. 今天日期: {today}

請只回傳 JSON。"""

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/{model}:generateContent"

class LLMParser:
    def __init__(self):
        self.api_key = llm_config.api_key
        self.model = llm_config.model
        self.enabled = bool(self.api_key)

    def parse(self, text: str) -> Optional[dict]:
        """
        解析自然語言文字。
        (Optimization #6: Added retry mechanism)
        """
        if not self.enabled:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        prompt = SYSTEM_PROMPT.replace("{today}", today)
        full_prompt = f"{prompt}\n\n使用者訊息：{text}"

        url = GEMINI_API_URL.format(model=self.model)
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 800,
                "responseMimeType": "application/json"
            }
        }

        # 指數退避重試 (Optimization #6)
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url, headers=headers, params=params,
                    json=payload, timeout=30
                )
                response.raise_for_status()
                data = response.json()

                candidates = data.get("candidates", [])
                if not candidates:
                    return None

                content = candidates[0].get("content", {}).get("parts", [])
                if not content:
                    return None

                text_result = content[0].get("text", "").strip()
                if text_result.startswith("```"):
                    lines = text_result.split("\n")
                    text_result = "\n".join(lines[1:-1])

                parsed = json.loads(text_result)
                return self._validate_result(parsed)

            except (Exception) as e:
                logger.error("LLM parsing (Attempt %d) failed: %s", attempt + 1, e)
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                else:
                    return None
            except json.JSONDecodeError as e:
                logger.error("Failed to parse LLM JSON: %s", e)
                return None

    def _validate_result(self, parsed: dict) -> Optional[dict]:
        """驗證並正規化 LLM 回傳的記帳資料。"""
        valid_categories = {
            "學費收入", "教材收入", "報名費", "其他收入",
            "教材費", "房租水電", "人事費用", "設備維護",
            "辦公用品", "餐飲點心", "交通費", "廣告行銷",
            "保險稅務", "其他支出",
        }

        title = parsed.get("title", "").strip()
        if not title:
            return None

        amount = parsed.get("amount")
        try:
            amount = abs(float(amount)) if amount is not None else 0
        except (ValueError, TypeError):
            amount = 0

        entry_type = parsed.get("type", "支出")
        if entry_type not in ("收入", "支出"):
            entry_type = "支出"

        category = parsed.get("category", "其他支出")
        if category not in valid_categories:
            category = "其他收入" if entry_type == "收入" else "其他支出"

        result = {
            "title": title,
            "amount": amount,
            "type": entry_type,
            "category": category,
            "date": parsed.get("date"),
            "vendor": parsed.get("vendor", ""),
            "payment_method": parsed.get("payment_method", "未指定"),
            "description": parsed.get("description", ""),
            "invoice_number": parsed.get("invoice_number", ""),
            "tax_amount": parsed.get("tax_amount", 0),
        }
        return result

    def is_available(self) -> bool:
        return self.enabled
