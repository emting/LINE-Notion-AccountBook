"""
Data Processor 整合測試。

涵蓋：
- Bug #2：NT$ 金額正則修正（各格式）
- Bug #3：收支詞組判斷（完整詞組，避免歧義）
- Rule Engine 分類、OCR 路徑、確認訊息格式
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.data_processor import AccountEntry, DataProcessor


class TestExtractAmount(unittest.TestCase):
    """Bug #2 修正測試：各金額格式均能正確提取。"""

    def setUp(self):
        self.processor = DataProcessor()

    def test_nt_dollar(self):
        self.assertEqual(self.processor._extract_amount("NT$4,500"), 4500.0)

    def test_nt_dollar_no_comma(self):
        self.assertEqual(self.processor._extract_amount("NT$1200"), 1200.0)

    def test_dollar_sign(self):
        self.assertEqual(self.processor._extract_amount("$1,200"), 1200.0)

    def test_fullwidth_dollar(self):
        self.assertEqual(self.processor._extract_amount("＄300"), 300.0)

    def test_yuan_suffix(self):
        self.assertEqual(self.processor._extract_amount("1200元"), 1200.0)

    def test_kuai_suffix(self):
        self.assertEqual(self.processor._extract_amount("300塊"), 300.0)

    def test_no_amount(self):
        self.assertEqual(self.processor._extract_amount("買了講義"), 0.0)

    def test_decimal(self):
        self.assertAlmostEqual(self.processor._extract_amount("NT$10,000.5"), 10000.5)


class TestDetectType(unittest.TestCase):
    """Bug #3 修正測試：完整詞組，避免單字歧義。"""

    def setUp(self):
        self.processor = DataProcessor()

    def test_income_phrases(self):
        cases = [
            ("收到學費 5000", "收入"),
            ("入帳五千", "收入"),
            ("退款處理完成", "收入"),
            ("繳費成功", "收入"),
            ("學費繳交完畢", "收入"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.processor._detect_type(text), expected)

    def test_expense_phrases(self):
        cases = [
            ("買了便當", "支出"),
            ("付房租", "支出"),
            ("支付電費", "支出"),
            ("花了 500 元", "支出"),
            ("購買影印紙", "支出"),
            ("修繕冷氣", "支出"),
            ("租借投影機", "支出"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.processor._detect_type(text), expected)

    def test_ambiguous_defaults_to_expense(self):
        """無關鍵字時預設為支出。"""
        self.assertEqual(self.processor._detect_type("收據影本"), "支出")


class TestDetectCategory(unittest.TestCase):
    """分類關鍵字對應測試。"""

    def setUp(self):
        self.processor = DataProcessor()

    def test_categories(self):
        cases = [
            ("影印紙 100", "支出", "辦公用品"),
            ("講義 500", "支出", "教材費"),
            ("水電費 2000", "支出", "房租水電"),
            ("工讀生薪資", "支出", "人事費用"),
            ("收到學費 5000", "收入", "學費收入"),
            ("活動報名費", "收入", "報名費"),
        ]
        for text, entry_type, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    self.processor._detect_category(text, entry_type), expected
                )

    def test_unknown_defaults(self):
        self.assertEqual(self.processor._detect_category("未知支出", "支出"), "其他支出")
        self.assertEqual(self.processor._detect_category("未知收入", "收入"), "其他收入")


class TestProcessText(unittest.TestCase):
    """process_text 路由測試。"""

    def setUp(self):
        self.processor = DataProcessor()

    def test_command_expense(self):
        entry = self.processor.process_text("/支 講義 4500")
        self.assertEqual(entry.entry_type, "支出")
        self.assertEqual(entry.amount, 4500.0)
        self.assertEqual(entry.parse_engine, "rule")

    def test_command_income(self):
        entry = self.processor.process_text("/收 學費 12000")
        self.assertEqual(entry.entry_type, "收入")
        self.assertEqual(entry.amount, 12000.0)

    def test_structured_format(self):
        entry = self.processor.process_text("摘要: 講義 | 金額: 4500 | 類型: 支出")
        self.assertEqual(entry.title, "講義")
        self.assertEqual(entry.amount, 4500.0)
        self.assertEqual(entry.entry_type, "支出")

    def test_empty_text(self):
        entry = self.processor.process_text("")
        self.assertEqual(entry.title, "")
        self.assertEqual(entry.amount, 0.0)


class TestProcessImage(unittest.TestCase):
    """OCR 路徑測試。"""

    def setUp(self):
        self.processor = DataProcessor()

    def test_ocr_disabled(self):
        """OCR 引擎未啟用時應回傳失敗 entry。"""
        self.processor.ocr_engine.enabled = False
        entry = self.processor.process_image(b"fake")
        self.assertEqual(entry.title, "OCR 辨識失敗")
        self.assertEqual(entry.parse_engine, "ocr")

    def test_ocr_success(self):
        """OCR 成功時應正確對應欄位。"""
        self.processor.ocr_engine.enabled = True
        self.processor.ocr_engine.recognize = MagicMock(return_value={
            "vendor": "7-11",
            "total_amount": 150,
            "confidence": 0.95,
            "items": [{"name": "飲料", "amount": 150}],
            "raw_text": "7-11 飲料 150",
        })
        entry = self.processor.process_image(b"fake")
        self.assertEqual(entry.vendor, "7-11")
        self.assertEqual(entry.amount, 150.0)
        self.assertEqual(entry.parse_engine, "ocr")
        self.assertAlmostEqual(entry.parse_confidence, 0.95)

    def test_ocr_error_response(self):
        """OCR 回傳 error 欄位時應對應 title。"""
        self.processor.ocr_engine.enabled = True
        self.processor.ocr_engine.recognize = MagicMock(return_value={
            "error": "非發票或收據圖片",
            "raw_text": "一張貓咪照片",
        })
        entry = self.processor.process_image(b"fake")
        self.assertEqual(entry.title, "非發票或收據圖片")


class TestFormatConfirmation(unittest.TestCase):
    """確認訊息格式測試。"""

    def setUp(self):
        self.processor = DataProcessor()

    def test_expense_message(self):
        entry = AccountEntry(
            title="買講義",
            amount=4500,
            entry_type="支出",
            category="教材費",
            parse_engine="llm",
            parse_confidence=0.95,
        )
        msg = self.processor.format_confirmation(entry)
        self.assertIn("💸", msg)
        self.assertIn("買講義", msg)
        self.assertIn("$4,500", msg)
        self.assertIn("AI 智慧解析", msg)

    def test_income_message(self):
        entry = AccountEntry(
            title="學費",
            amount=12000,
            entry_type="收入",
            category="學費收入",
            parse_engine="rule",
            parse_confidence=0.6,
        )
        msg = self.processor.format_confirmation(entry)
        self.assertIn("💰", msg)
        self.assertIn("規則引擎解析", msg)


if __name__ == "__main__":
    unittest.main()
