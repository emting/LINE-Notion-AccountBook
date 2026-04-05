"""
OCR 引擎單元測試。
使用 Mock 模擬 Gemini API 回應。
"""

import unittest
from unittest.mock import patch, MagicMock
from app.ocr_engine import OCREngine

class TestOCREngine(unittest.TestCase):
    def setUp(self):
        with patch('app.ocr_engine.llm_config') as mock_config:
            mock_config.api_key = "fake_key"
            mock_config.vision_model = "vision-model"
            self.engine = OCREngine()

    @patch('requests.post')
    def test_recognize_success(self, mock_post):
        # 模擬成功回應
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"vendor": "7-11", "total_amount": 150, "confidence": 0.9}'
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response

        result = self.engine.recognize(b"fake_image_bytes")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["vendor"], "7-11")
        self.assertEqual(result["total_amount"], 150)

    @patch('requests.post')
    def test_recognize_failure(self, mock_post):
        # 模擬 API 錯誤
        mock_post.side_effect = Exception("API Error")
        
        result = self.engine.recognize(b"fake_image_bytes")
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
