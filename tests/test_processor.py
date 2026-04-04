"""
Unit tests for the DataProcessor module.

These tests verify that the data processor correctly parses
various input formats into structured task data. Tests are designed
to work with both the LLM engine and the rule-based fallback engine.
"""

import sys
import os
import unittest
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_processor import DataProcessor, ParsedTask


class TestDataProcessor(unittest.TestCase):
    """Test suite for the DataProcessor class."""

    def setUp(self):
        self.processor = DataProcessor()

    # ── Command format tests (always rule engine) ─────────────

    def test_command_basic(self):
        result = self.processor.process("/task 準備週會簡報")
        self.assertEqual(result.title, "準備週會簡報")
        self.assertEqual(result.parse_engine, "rule")
        self.assertGreater(result.parse_confidence, 0.8)

    def test_command_with_priority(self):
        result = self.processor.process("/task 修復登入問題 --priority high")
        self.assertEqual(result.title.strip(), "修復登入問題")
        self.assertEqual(result.priority, "High")
        self.assertEqual(result.parse_engine, "rule")

    def test_command_with_date(self):
        result = self.processor.process("/task 寄發票 --date 2026-04-10")
        self.assertEqual(result.title.strip(), "寄發票")
        self.assertEqual(result.due_date, "2026-04-10")
        self.assertEqual(result.parse_engine, "rule")

    def test_command_full(self):
        result = self.processor.process(
            "/task 客戶提案 --priority high --date 2026-04-15 --category Meeting"
        )
        self.assertEqual(result.title.strip(), "客戶提案")
        self.assertEqual(result.priority, "High")
        self.assertEqual(result.due_date, "2026-04-15")
        self.assertEqual(result.category, "Meeting")
        self.assertEqual(result.parse_engine, "rule")

    # ── Structured format tests (always rule engine) ──────────

    def test_structured_basic(self):
        result = self.processor.process("標題: 開會 | 優先級: 高")
        self.assertEqual(result.title, "開會")
        self.assertEqual(result.priority, "High")
        self.assertEqual(result.parse_engine, "rule")

    def test_structured_full(self):
        result = self.processor.process(
            "標題: 系統上線 | 日期: 2026-05-01 | 優先級: 高 | 分類: Feature"
        )
        self.assertEqual(result.title, "系統上線")
        self.assertEqual(result.due_date, "2026-05-01")
        self.assertEqual(result.priority, "High")
        self.assertEqual(result.category, "Feature")
        self.assertEqual(result.parse_engine, "rule")

    def test_structured_with_description(self):
        result = self.processor.process(
            "標題: 寫文件 | 描述: 完成 API 文件撰寫 | 優先級: 中"
        )
        self.assertEqual(result.title, "寫文件")
        self.assertEqual(result.description, "完成 API 文件撰寫")
        self.assertEqual(result.priority, "Medium")
        self.assertEqual(result.parse_engine, "rule")

    # ── Free-form text tests (LLM or rule engine) ─────────────
    # These tests validate the output regardless of which engine is used.

    def test_freeform_with_priority(self):
        result = self.processor.process("要開會，優先級高")
        self.assertEqual(result.priority, "High")
        self.assertTrue(len(result.title) > 0)

    def test_freeform_with_relative_date(self):
        result = self.processor.process("明天要交報告")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(result.due_date, tomorrow)

    def test_freeform_with_explicit_date(self):
        result = self.processor.process("2026-04-20 前完成設計稿")
        self.assertEqual(result.due_date, "2026-04-20")

    def test_freeform_meeting_category(self):
        result = self.processor.process("下週一要跟客戶開會")
        self.assertIn(result.category, ["Meeting", "Communication", "Todo"])

    def test_freeform_reminder_category(self):
        result = self.processor.process("記得買牛奶")
        # LLM may classify as Todo or Reminder, both are acceptable
        self.assertIn(result.category, ["Reminder", "Todo"])

    def test_freeform_bug_category(self):
        result = self.processor.process("登入頁面有 bug 需要修復")
        self.assertIn(result.category, ["Bug", "Todo"])

    # ── Edge cases ────────────────────────────────────────────

    def test_empty_input(self):
        result = self.processor.process("")
        self.assertEqual(result.title, "")

    def test_whitespace_only(self):
        result = self.processor.process("   ")
        self.assertEqual(result.title, "")

    def test_very_long_input(self):
        long_text = "這是一個很長的任務描述 " * 100
        result = self.processor.process(long_text)
        self.assertTrue(len(result.title) > 0)

    # ── Confirmation message tests ────────────────────────────

    def test_confirmation_message(self):
        task = ParsedTask(
            title="開會",
            category="Meeting",
            priority="High",
            due_date="2026-04-05",
            parse_engine="rule",
        )
        msg = self.processor.format_confirmation_message(task)
        self.assertIn("開會", msg)
        self.assertIn("Meeting", msg)
        self.assertIn("High", msg)
        self.assertIn("2026-04-05", msg)
        self.assertIn("Notion", msg)

    def test_confirmation_message_shows_llm_engine(self):
        task = ParsedTask(
            title="開會",
            category="Meeting",
            priority="High",
            parse_engine="llm",
            parse_confidence=0.95,
        )
        msg = self.processor.format_confirmation_message(task)
        self.assertIn("AI 智慧解析", msg)

    def test_confirmation_message_shows_rule_engine(self):
        task = ParsedTask(
            title="開會",
            category="Meeting",
            priority="High",
            parse_engine="rule",
            parse_confidence=0.85,
        )
        msg = self.processor.format_confirmation_message(task)
        self.assertIn("規則引擎解析", msg)


if __name__ == "__main__":
    unittest.main()
