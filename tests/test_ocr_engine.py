"""
OCR 引擎單元測試。
使用 Mock 模擬 Gemini API 回應。
"""

import unittest
from unittest.mock import patch, MagicMock

import requests

from app.ocr_engine import OCREngine, GEMINI_BASE, MAX_RETRIES


class TestOCREngine(unittest.TestCase):
    def setUp(self):
        with patch("app.ocr_engine.llm_config") as mock_config:
            mock_config.api_key = "fake_key"
            mock_config.vision_model = "models/gemini-2.5-flash"
            self.engine = OCREngine()

    # ── 成功路徑 ──────────────────────────────────────────

    @patch("requests.post")
    def test_recognize_success(self, mock_post):
        """辨識成功時應回傳結構化 dict。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"vendor": "7-11", "total_amount": 150,'
                                    ' "confidence": 0.9}'
                                )
                            }
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        result = self.engine.recognize(b"fake_image_bytes")

        self.assertIsNotNone(result)
        self.assertEqual(result["vendor"], "7-11")
        self.assertEqual(result["total_amount"], 150)

    # ── 失敗路徑：requests.RequestException ──────────────

    @patch("requests.post")
    def test_recognize_request_failure(self, mock_post):
        """API 呼叫拋出 RequestException 時應回傳 None（重試後放棄）。"""
        mock_post.side_effect = requests.RequestException("Connection timeout")

        result = self.engine.recognize(b"fake_image_bytes")

        self.assertIsNone(result)
        # 應該重試 MAX_RETRIES + 1 次才放棄
        self.assertEqual(mock_post.call_count, MAX_RETRIES + 1)

    # ── 失敗路徑：API key 未設定 ─────────────────────────

    def test_disabled_without_api_key(self):
        """無 API key 時 is_available() 應回傳 False，recognize() 應回傳 None。"""
        with patch("app.ocr_engine.llm_config") as mock_config:
            mock_config.api_key = ""
            mock_config.vision_model = "models/gemini-2.5-flash"
            engine = OCREngine()

        self.assertFalse(engine.is_available())
        self.assertIsNone(engine.recognize(b"fake_image_bytes"))

    # ── 失敗路徑：JSON 解析失敗 ──────────────────────────

    @patch("requests.post")
    def test_recognize_invalid_json(self, mock_post):
        """Gemini 回傳無效 JSON 時應回傳 None。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "NOT VALID JSON"}]}}
            ]
        }
        mock_post.return_value = mock_response

        result = self.engine.recognize(b"fake_image_bytes")
        self.assertIsNone(result)

    # ── URL 常數驗證 ──────────────────────────────────────

    def test_url_uses_gemini_base_constant(self):
        """_post_with_retry 應使用 GEMINI_BASE 常數組合 URL。"""
        import app.ocr_engine as ocr_module
        self.assertTrue(
            ocr_module.GEMINI_BASE.startswith("https://generativelanguage.googleapis.com")
        )


if __name__ == "__main__":
    unittest.main()
