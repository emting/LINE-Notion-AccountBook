"""
Data Processor 整合測試。
包含 Rule Engine 金額提取 (Bug #2) 與 收支判斷 (Bug #3) 測試案件。
"""

import unittest
from app.data_processor import DataProcessor

class TestDataProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = DataProcessor()

    def test_extract_amount_various_formats(self):
        """測試不同金額格式 (Bug #2 修正測試)。"""
        cases = [
            ("NT$4,500", 4500.0),
            ("$1,200", 1200.0),
            ("＄300", 300.0),
            ("1200元", 1200.0),
            ("300塊", 300.0),
            ("10,000.5", 10000.5),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.processor._extract_amount(text), expected)

    def test_detect_type_phrases(self):
        """測試收支關鍵字判斷 (Bug #3 修正測試)。"""
        cases = [
            ("收到學費", "收入"),
            ("入帳五千", "收入"),
            ("退款回傳", "收入"),
            ("買了便當", "支出"),
            ("付房租", "支出"),
            ("支付電費", "支出"),
            ("修繕冷氣", "支出"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.processor._detect_type(text), expected)

    def test_detect_category(self):
        """測試分類判斷。"""
        cases = [
            ("影印紙 100", "支出", "辦公用品"),
            ("講義 500", "支出", "教材費"),
            ("水電費 2000", "支出", "房租水電"),
            ("工讀生薪資", "支出", "人事費用"),
            ("收到學費 5000", "收入", "學費收入"),
        ]
        for text, entry_type, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.processor._detect_category(text, entry_type), expected)

if __name__ == '__main__':
    unittest.main()
