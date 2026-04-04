"""
Integration tests for the LLM Parser module.

These tests verify that the LLM-powered parser correctly interprets
various natural language inputs and returns structured task data.
Requires OPENAI_API_KEY environment variable to be set.
"""

import sys
import os
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.llm_parser import LLMParser
from app.data_processor import DataProcessor


class TestLLMParser(unittest.TestCase):
    """Integration tests for the LLM Parser."""

    def setUp(self):
        self.parser = LLMParser()
        if not self.parser.is_available():
            self.skipTest("OPENAI_API_KEY not configured, skipping LLM tests.")

    def test_simple_task(self):
        """Test parsing a simple task description."""
        result = self.parser.parse("幫我訂明天下午的會議室")
        self.assertIsNotNone(result)
        self.assertTrue(len(result["title"]) > 0)
        self.assertIn(result["priority"], ["High", "Medium", "Low"])

    def test_urgent_task(self):
        """Test that urgency cues are detected."""
        result = self.parser.parse("緊急！伺服器掛了，馬上修復")
        self.assertIsNotNone(result)
        self.assertEqual(result["priority"], "High")

    def test_low_priority_task(self):
        """Test that low priority cues are detected."""
        result = self.parser.parse("有空的時候幫我整理一下文件，不急")
        self.assertIsNotNone(result)
        self.assertEqual(result["priority"], "Low")

    def test_meeting_category(self):
        """Test that meeting-related text is categorized correctly."""
        result = self.parser.parse("下週三跟客戶開會討論新專案的需求")
        self.assertIsNotNone(result)
        self.assertIn(result["category"], ["Meeting", "Communication"])

    def test_bug_category(self):
        """Test that bug-related text is categorized correctly."""
        result = self.parser.parse("登入頁面的驗證碼顯示不出來，使用者反映很多次了")
        self.assertIsNotNone(result)
        self.assertIn(result["category"], ["Bug", "Todo"])

    def test_idea_category(self):
        """Test that idea-related text is categorized correctly."""
        result = self.parser.parse("我有個想法，我們可以做一個自動化的報表系統")
        self.assertIsNotNone(result)
        self.assertIn(result["category"], ["Idea", "Feature"])

    def test_date_extraction(self):
        """Test that dates are correctly extracted."""
        result = self.parser.parse("2026-04-15 前要完成季度報告")
        self.assertIsNotNone(result)
        self.assertEqual(result["due_date"], "2026-04-15")

    def test_complex_message(self):
        """Test parsing a complex, multi-faceted message."""
        result = self.parser.parse(
            "我們需要在這週五之前完成新版 App 的 UI 設計稿，"
            "包含首頁、個人頁面和設定頁面，這個很重要因為下週一要給客戶看"
        )
        self.assertIsNotNone(result)
        self.assertTrue(len(result["title"]) > 0)
        self.assertEqual(result["priority"], "High")
        self.assertTrue(len(result["description"]) > 0)


class TestDataProcessorWithLLM(unittest.TestCase):
    """Test the DataProcessor's dual-engine strategy."""

    def setUp(self):
        self.processor = DataProcessor()

    def test_freeform_uses_llm_when_available(self):
        """Verify that free-form text uses LLM engine when available."""
        if not self.processor.llm_parser.is_available():
            self.skipTest("LLM not available")
        task = self.processor.process("幫我安排明天跟設計師討論 Logo 的會議")
        self.assertEqual(task.parse_engine, "llm")
        self.assertGreater(task.parse_confidence, 0.9)

    def test_command_always_uses_rule_engine(self):
        """Verify that command format always uses rule engine."""
        task = self.processor.process("/task 寫文件 --priority high --date 2026-04-10")
        self.assertEqual(task.parse_engine, "rule")
        self.assertEqual(task.priority, "High")

    def test_structured_always_uses_rule_engine(self):
        """Verify that structured format always uses rule engine."""
        task = self.processor.process("標題: 開會 | 優先級: 高 | 日期: 2026-04-10")
        self.assertEqual(task.parse_engine, "rule")
        self.assertEqual(task.title, "開會")

    def test_confirmation_shows_engine(self):
        """Verify confirmation message indicates which engine was used."""
        task = self.processor.process("記得買牛奶")
        msg = self.processor.format_confirmation_message(task)
        if task.parse_engine == "llm":
            self.assertIn("AI 智慧解析", msg)
        else:
            self.assertIn("規則引擎解析", msg)


if __name__ == "__main__":
    unittest.main()
