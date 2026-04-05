"""
OCR Engine — 使用 Google Gemini Vision API 辨識發票/收據。

支援：
- 台灣電子發票（統一發票）
- 手寫收據
- 超商/賣場發票
- 一般商業收據

透過 Gemini multimodal API 將圖片轉為結構化 JSON。
"""

import base64
import json
import logging
import time
from typing import Optional

import requests

from config.settings import llm_config

logger = logging.getLogger(__name__)

OCR_SYSTEM_PROMPT = """你是一個專業的發票/收據 OCR 辨識助手，專門為補習班記帳服務。

請仔細辨識圖片中的發票或收據，提取以下資訊並以 JSON 格式回傳：

{
  "vendor": "商家/供應商名稱",
  "items": [
    {"name": "品項名稱", "quantity": 數量, "unit_price": 單價, "amount": 小計}
  ],
  "total_amount": 總金額（數字）,
  "tax_amount": 稅額（數字，若無則 0）,
  "invoice_number": "發票號碼（若有）",
  "date": "日期（YYYY-MM-DD 格式）",
  "payment_method": "付款方式（現金/刷卡/轉帳/未知）",
  "raw_text": "圖片中辨識出的完整文字",
  "confidence": 0.0-1.0 的辨識信心度
}

辨識規則：
1. 金額務必為數字，去除千分位逗號
2. 若圖片模糊或無法辨識某欄位，該欄位回傳 null
3. 台灣統一發票格式：注意「營業人」「統一編號」「品名」「金額」等欄位
4. 手寫收據：盡力辨識手寫文字
5. 若圖片不是發票/收據，回傳 {"error": "非發票或收據圖片", "raw_text": "辨識到的文字"}

請只回傳 JSON，不要包含 markdown 標記。"""

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/{model}:generateContent"

class OCREngine:
    """
    使用 Gemini Vision API 進行發票/收據 OCR 辨識。
    """

    def __init__(self):
        self.api_key = llm_config.api_key
        self.model = llm_config.vision_model
        self.enabled = bool(self.api_key)

        if self.enabled:
            logger.info("OCR Engine initialized with model: %s", self.model)
        else:
            logger.warning("OCR Engine disabled: GEMINI_API_KEY not configured.")

    def recognize(self, image_bytes: bytes) -> Optional[dict]:
        """
        辨識發票/收據圖片。
        (Optimization #6: Added retry mechanism)
        """
        if not self.enabled:
            return None

        # 將圖片轉為 base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        url = GEMINI_API_URL.format(model=self.model)
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": OCR_SYSTEM_PROMPT},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_b64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2000,
                "responseMimeType": "application/json"
            }
        }

        # 指數退避重試 (Optimization #6)
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    url, headers=headers, params=params,
                    json=payload, timeout=60
                )
                response.raise_for_status()
                data = response.json()

                candidates = data.get("candidates", [])
                if not candidates:
                    return None

                content = candidates[0].get("content", {}).get("parts", [])
                if not content:
                    return None

                text = content[0].get("text", "").strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    text = "\n".join(lines[1:-1])

                result = json.loads(text)
                logger.info("OCR result: %s",
                            json.dumps(result, ensure_ascii=False)[:300])
                return result

            except Exception as e:
                logger.error("Gemini Vision API (Attempt %d) failed: %s", attempt + 1, e)
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # 指數退避
                else:
                    return None
            except json.JSONDecodeError as e:
                logger.error("Failed to parse OCR JSON: %s", e)
                return None

    def is_available(self) -> bool:
        return self.enabled
