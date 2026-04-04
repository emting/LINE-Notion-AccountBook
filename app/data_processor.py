"""
Data Processor Module.

This module serves as the intelligent processing layer between LINE input
and Notion output. It implements a dual-engine architecture:

    1. **Primary Engine (LLM)**: Uses OpenAI-compatible LLM API for deep
       natural language understanding, intelligent classification, and
       context-aware parsing.
    2. **Fallback Engine (Rule-based)**: Uses keyword matching and regex
       patterns as a reliable fallback when the LLM is unavailable.

The processor automatically selects the best available engine and ensures
graceful degradation if the LLM API encounters errors.

Supported input formats:
    1. Free-form text: "明天下午三點要開會，優先級高"
    2. Structured format: "標題: 開會 | 日期: 2026-04-05 | 優先級: 高"
    3. Command format: "/task 開會 --priority high --date 2026-04-05"
"""

import re
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

from app.llm_parser import LLMParser

logger = logging.getLogger(__name__)

# Priority mapping for Chinese and English keywords (fallback engine)
PRIORITY_KEYWORDS = {
    "high": ["高", "緊急", "重要", "urgent", "high", "hi"],
    "medium": ["中", "一般", "普通", "medium", "med", "normal"],
    "low": ["低", "不急", "low", "lo"],
}

# Category keywords for auto-classification (fallback engine)
CATEGORY_KEYWORDS = {
    "Meeting": ["會議", "開會", "meeting", "meet", "討論", "sync"],
    "Todo": ["待辦", "todo", "task", "做", "完成", "處理"],
    "Reminder": ["提醒", "記得", "別忘", "reminder", "remind"],
    "Note": ["筆記", "記錄", "note", "備忘"],
    "Idea": ["想法", "點子", "idea", "靈感", "構想"],
    "Bug": ["bug", "錯誤", "問題", "issue", "修復", "fix"],
    "Feature": ["功能", "feature", "需求", "新增"],
}

# Relative date keywords (fallback engine)
RELATIVE_DATE_KEYWORDS = {
    "今天": 0,
    "today": 0,
    "明天": 1,
    "tomorrow": 1,
    "後天": 2,
    "大後天": 3,
    "下週": 7,
    "next week": 7,
}


@dataclass
class ParsedTask:
    """Represents a structured task parsed from user input."""
    title: str = ""
    category: str = ""
    priority: str = "Medium"
    due_date: Optional[str] = None
    description: str = ""
    raw_text: str = ""
    parse_confidence: float = 0.0
    parse_engine: str = "rule"  # "llm" or "rule"


class DataProcessor:
    """
    Processes raw text messages and extracts structured task data.

    This processor uses a dual-engine strategy:

    | Engine   | Trigger Condition                    | Confidence | Capabilities                    |
    |----------|--------------------------------------|------------|---------------------------------|
    | LLM      | API key configured & API available   | 0.95       | Deep NLU, context-aware parsing |
    | Rule     | LLM unavailable or returns error     | 0.6-0.9    | Keyword matching, regex parsing |

    The LLM engine is used for free-form text where understanding context
    and nuance is critical. Command and structured formats are always
    handled by the rule engine since their format is deterministic.
    """

    def __init__(self):
        self.llm_parser = LLMParser()
        if self.llm_parser.is_available():
            logger.info("DataProcessor initialized with LLM engine (primary) + Rule engine (fallback).")
        else:
            logger.info("DataProcessor initialized with Rule engine only (LLM not configured).")

    def process(self, text: str) -> ParsedTask:
        """
        Main entry point for processing a text message.

        Detects the input format and delegates to the appropriate parser.
        For free-form text, attempts LLM parsing first with rule-based fallback.

        Args:
            text: The raw text message from the LINE user.

        Returns:
            A ParsedTask object with extracted fields.
        """
        text = text.strip()
        if not text:
            return ParsedTask(raw_text=text)

        # Command and structured formats use deterministic rule engine
        if text.startswith("/task"):
            task = self._parse_command_format(text)
        elif "|" in text and ":" in text:
            task = self._parse_structured_format(text)
        else:
            # Free-form text: try LLM first, fallback to rules
            task = self._parse_with_llm_fallback(text)

        task.raw_text = text
        logger.info(
            "Parsed task [engine=%s]: title='%s', category='%s', priority='%s', "
            "due_date='%s', confidence=%.2f",
            task.parse_engine, task.title, task.category, task.priority,
            task.due_date, task.parse_confidence,
        )
        return task

    def _parse_with_llm_fallback(self, text: str) -> ParsedTask:
        """
        Attempt LLM parsing with graceful fallback to rule-based parsing.

        This method implements the core dual-engine strategy:
        1. If LLM is available, send the text for AI-powered parsing.
        2. If LLM returns a valid result, use it with high confidence.
        3. If LLM fails or is unavailable, fall back to the rule engine.

        Args:
            text: The free-form text message.

        Returns:
            A ParsedTask from either the LLM or rule engine.
        """
        if self.llm_parser.is_available():
            logger.info("Attempting LLM parsing for: '%s'", text[:80])
            llm_result = self.llm_parser.parse(text)

            if llm_result and llm_result.get("title"):
                task = ParsedTask(
                    title=llm_result["title"],
                    category=llm_result.get("category", "Todo"),
                    priority=llm_result.get("priority", "Medium"),
                    due_date=llm_result.get("due_date"),
                    description=llm_result.get("description", ""),
                    parse_confidence=0.95,
                    parse_engine="llm",
                )
                logger.info("LLM parsing succeeded.")
                return task
            else:
                logger.warning("LLM parsing returned no result, falling back to rule engine.")

        # Fallback to rule-based parsing
        return self._parse_freeform(text)

    # ── Command Format Parser (Rule Engine) ───────────────────

    def _parse_command_format(self, text: str) -> ParsedTask:
        """
        Parse command-style input: /task <title> --priority <p> --date <d>

        Args:
            text: The command string.

        Returns:
            A ParsedTask with extracted fields.
        """
        task = ParsedTask(parse_confidence=0.9, parse_engine="rule")

        # Remove the /task prefix
        content = text[5:].strip()

        # Extract --priority flag
        priority_match = re.search(
            r"--priority\s+(\S+)", content, re.IGNORECASE
        )
        if priority_match:
            task.priority = self._normalize_priority(priority_match.group(1))
            content = content[: priority_match.start()] + content[priority_match.end() :]

        # Extract --date flag
        date_match = re.search(r"--date\s+(\S+)", content, re.IGNORECASE)
        if date_match:
            task.due_date = self._parse_date(date_match.group(1))
            content = content[: date_match.start()] + content[date_match.end() :]

        # Extract --category flag
        cat_match = re.search(r"--category\s+(\S+)", content, re.IGNORECASE)
        if cat_match:
            task.category = cat_match.group(1)
            content = content[: cat_match.start()] + content[cat_match.end() :]

        task.title = content.strip()
        if not task.category:
            task.category = self._detect_category(task.title)

        return task

    # ── Structured Format Parser (Rule Engine) ────────────────

    def _parse_structured_format(self, text: str) -> ParsedTask:
        """
        Parse structured input: 標題: xxx | 日期: xxx | 優先級: xxx

        Args:
            text: The structured string with pipe-separated fields.

        Returns:
            A ParsedTask with extracted fields.
        """
        task = ParsedTask(parse_confidence=0.85, parse_engine="rule")
        parts = [p.strip() for p in text.split("|")]

        field_map = {
            "標題": "title",
            "title": "title",
            "日期": "due_date",
            "date": "due_date",
            "優先級": "priority",
            "priority": "priority",
            "分類": "category",
            "category": "category",
            "描述": "description",
            "description": "description",
        }

        for part in parts:
            if ":" not in part and "：" not in part:
                continue
            separator = "：" if "：" in part else ":"
            key, value = part.split(separator, 1)
            key = key.strip().lower()
            value = value.strip()

            mapped_field = field_map.get(key)
            if mapped_field == "title":
                task.title = value
            elif mapped_field == "due_date":
                task.due_date = self._parse_date(value)
            elif mapped_field == "priority":
                task.priority = self._normalize_priority(value)
            elif mapped_field == "category":
                task.category = value
            elif mapped_field == "description":
                task.description = value

        if not task.category and task.title:
            task.category = self._detect_category(task.title)

        return task

    # ── Free-form Parser (Rule Engine Fallback) ───────────────

    def _parse_freeform(self, text: str) -> ParsedTask:
        """
        Parse free-form natural language input using rule-based engine.

        This is the fallback parser used when the LLM engine is unavailable.
        It uses keyword detection and pattern matching to extract task
        information from unstructured Chinese or English text.

        Args:
            text: The free-form text message.

        Returns:
            A ParsedTask with best-effort extracted fields.
        """
        task = ParsedTask(parse_confidence=0.6, parse_engine="rule")

        task.priority = self._detect_priority(text)
        task.due_date = self._detect_date_in_text(text)
        task.category = self._detect_category(text)

        # Clean up text to extract title
        title = text
        for keywords in PRIORITY_KEYWORDS.values():
            for kw in keywords:
                title = re.sub(rf"[，,]?\s*優先級{kw}", "", title)
                title = re.sub(rf"[，,]?\s*priority\s*{kw}", "", title, flags=re.IGNORECASE)

        for kw in RELATIVE_DATE_KEYWORDS:
            title = title.replace(kw, "")
        title = re.sub(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", "", title)
        title = re.sub(r"下午|上午|早上|晚上|中午", "", title)
        title = re.sub(r"\d{1,2}[點:時]\d{0,2}分?", "", title)

        title = re.sub(r"[，,。.、]\s*$", "", title.strip())
        title = re.sub(r"^\s*[，,。.、]", "", title.strip())
        task.title = title.strip() if title.strip() else text[:50]

        task.description = text
        return task

    # ── Utility Methods ───────────────────────────────────────

    def _normalize_priority(self, value: str) -> str:
        """Normalize a priority value to High, Medium, or Low."""
        value_lower = value.lower().strip()
        for level, keywords in PRIORITY_KEYWORDS.items():
            if value_lower in keywords:
                return level.capitalize()
        return "Medium"

    def _detect_priority(self, text: str) -> str:
        """Detect priority level from keywords in text."""
        text_lower = text.lower()
        for level, keywords in PRIORITY_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return level.capitalize()
        return "Medium"

    def _detect_category(self, text: str) -> str:
        """Auto-detect task category from keywords in text."""
        text_lower = text.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return category
        return "Todo"

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse a date string into ISO 8601 format (YYYY-MM-DD)."""
        date_str = date_str.strip()

        if date_str in RELATIVE_DATE_KEYWORDS:
            delta = RELATIVE_DATE_KEYWORDS[date_str]
            target = datetime.now() + timedelta(days=delta)
            return target.strftime("%Y-%m-%d")

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d", "%m-%d"):
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _detect_date_in_text(self, text: str) -> Optional[str]:
        """Detect and extract date information from free-form text."""
        for keyword, delta in RELATIVE_DATE_KEYWORDS.items():
            if keyword in text:
                target = datetime.now() + timedelta(days=delta)
                return target.strftime("%Y-%m-%d")

        date_match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
        if date_match:
            return f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

        date_match = re.search(r"(\d{1,2})[-/](\d{1,2})", text)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{datetime.now().year}-{month:02d}-{day:02d}"

        return None

    def format_confirmation_message(self, task: ParsedTask) -> str:
        """
        Generate a user-friendly confirmation message for LINE reply.

        Args:
            task: The parsed task object.

        Returns:
            A formatted confirmation string in Chinese.
        """
        engine_label = "AI 智慧解析" if task.parse_engine == "llm" else "規則引擎解析"
        lines = [
            f"已成功將任務加入 Notion 資料庫！",
            f"（{engine_label}，信心度 {task.parse_confidence:.0%}）",
            f"",
            f"📋 標題：{task.title}",
            f"📁 分類：{task.category}",
            f"🔺 優先級：{task.priority}",
        ]
        if task.due_date:
            lines.append(f"📅 截止日期：{task.due_date}")
        if task.description and task.description != task.raw_text:
            lines.append(f"📝 描述：{task.description[:100]}")

        return "\n".join(lines)
