"""
LLM 解析引擎單元測試。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

import requests

from app.llm_parser import LLMParser, GEMINI_BASE, MAX_RETRIES, VALID_CATEGORIES


class TestLLMParser(unittest.TestCase):
    def setUp(self):
        with patch("app.llm_parser.llm_config") as mock_config:
            mock_config.api_key = "fake_key"
            mock_config.model = "models/gemini-2.5-flash"
            self.parser = LLMParser()

    # ── 成功路徑 ──────────────────────────────────────────

    @patch("requests.post")
    def test_parse_amount_and_type(self, mock_post):
        """成功解析收支訊息，回傳正確金額與類型。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"title": "買數學講義", "amount": 4500,'
                                    ' "type": "支出", "category": "教材費"}'
                                )
                            }
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        result = self.parser.parse("買了 10 本數學講義 $4500")

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "買數學講義")
        self.assertEqual(result["amount"], 4500.0)
        self.assertEqual(result["type"], "支出")
        self.assertEqual(result["category"], "教材費")

    # ── _validate_result 正規化 ──────────────────────────

    def test_validate_result_invalid_category_expense(self):
        """支出類型使用不存在分類時，fallback 為「其他支出」。"""
        data = {"title": "測試", "amount": 100, "type": "支出", "category": "不存在的分類"}
        result = self.parser._validate_result(data)
        self.assertEqual(result["category"], "其他支出")

    def test_validate_result_invalid_category_income(self):
        """收入類型使用不存在分類時，fallback 為「其他收入」。"""
        data = {"title": "測試", "amount": 500, "type": "收入", "category": "亂填"}
        result = self.parser._validate_result(data)
        self.assertEqual(result["category"], "其他收入")

    def test_validate_result_invalid_type_fallback(self):
        """無效 type 欄位應 fallback 為「支出」。"""
        data = {"title": "測試", "amount": 100, "type": "其他", "category": "教材費"}
        result = self.parser._validate_result(data)
        self.assertEqual(result["type"], "支出")

    def test_validate_result_missing_title(self):
        """缺少 title 應回傳 None。"""
        result = self.parser._validate_result({"amount": 100, "type": "支出"})
        self.assertIsNone(result)

    def test_validate_result_amount_coercion(self):
        """金額應強制轉為正數浮點數。"""
        data = {"title": "退款", "amount": "-500", "type": "收入", "category": "其他收入"}
        result = self.parser._validate_result(data)
        self.assertEqual(result["amount"], 500.0)

    # ── 失敗路徑：RequestException 重試 ──────────────────

    @patch("requests.post")
    def test_parse_request_failure_with_retry(self, mock_post):
        """API 呼叫失敗時應重試 MAX_RETRIES+1 次後回傳 None。"""
        mock_post.side_effect = requests.RequestException("Timeout")

        result = self.parser.parse("買講義 1000")

        self.assertIsNone(result)
        self.assertEqual(mock_post.call_count, MAX_RETRIES + 1)

    # ── 失敗路徑：無 API key ─────────────────────────────

    def test_disabled_without_api_key(self):
        """無 API key 時 is_available() 應回傳 False。"""
        with patch("app.llm_parser.llm_config") as mock_config:
            mock_config.api_key = ""
            mock_config.model = "models/gemini-2.5-flash"
            parser = LLMParser()

        self.assertFalse(parser.is_available())
        self.assertIsNone(parser.parse("買講義 1000"))

    # ── 失敗路徑：JSON 解析失敗 ──────────────────────────

    @patch("requests.post")
    def test_parse_invalid_json(self, mock_post):
        """Gemini 回傳無效 JSON 時應回傳 None。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "NOT JSON"}]}}]
        }
        mock_post.return_value = mock_response

        result = self.parser.parse("測試")
        self.assertIsNone(result)

    # ── 常數驗證 ──────────────────────────────────────────

    def test_valid_categories_count(self):
        """VALID_CATEGORIES 應包含 14 種分類。"""
        self.assertEqual(len(VALID_CATEGORIES), 14)

    def test_url_uses_gemini_base_constant(self):
        """GEMINI_BASE 應為正確的 Google API 端點。"""
        self.assertTrue(GEMINI_BASE.startswith("https://generativelanguage.googleapis.com"))


if __name__ == "__main__":
    unittest.main()
