"""
LLM 解析引擎單元測試。
"""

import unittest
from unittest.mock import patch, MagicMock
from app.llm_parser import LLMParser

class TestLLMParser(unittest.TestCase):
    def setUp(self):
        with patch('app.llm_parser.llm_config') as mock_config:
            mock_config.api_key = "fake_key"
            mock_config.model = "llm-model"
            self.parser = LLMParser()

    @patch('requests.post')
    def test_parse_amount_and_type(self, mock_post):
        # 模擬 LLM 回傳 JSON
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"title": "買數學講義", "amount": 4500, "type": "支出", "category": "教材費"}'
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response

        result = self.parser.parse("買了 10 本數學講義 $4500")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "買數學講義")
        self.assertEqual(result["amount"], 4500)
        self.assertEqual(result["type"], "支出")
        self.assertEqual(result["category"], "教材費")

    def test_validate_result_invalid_category(self):
        # 測試分類矯正邏輯
        invalid_data = {
            "title": "測試",
            "amount": 100,
            "type": "支出",
            "category": "不存在的分類"
        }
        validated = self.parser._validate_result(invalid_data)
        self.assertEqual(validated["category"], "其他支出")

if __name__ == '__main__':
    unittest.main()
