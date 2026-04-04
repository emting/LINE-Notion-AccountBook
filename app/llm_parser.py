"""
LLM-Powered Intelligent Parser Module.

This module uses OpenAI-compatible LLM APIs to parse unstructured natural
language text into structured task data. It replaces the keyword-based
approach with true AI understanding, enabling:

    - Accurate intent recognition regardless of phrasing
    - Context-aware category classification
    - Intelligent priority inference from tone and urgency cues
    - Flexible date extraction from natural language expressions
    - Automatic summarization for task titles

The module implements a fallback strategy: if the LLM API is unavailable
or returns an error, it gracefully degrades to the rule-based parser.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from openai import OpenAI

from config.settings import llm_config

logger = logging.getLogger(__name__)

# System prompt that instructs the LLM how to parse user messages
SYSTEM_PROMPT = """你是一個專業的任務解析助手。你的工作是將使用者傳送的自然語言訊息解析為結構化的任務資料。

請根據使用者的訊息，提取以下欄位並以 JSON 格式回傳：

{
  "title": "簡潔的任務標題（10-30字）",
  "category": "任務分類",
  "priority": "優先級",
  "due_date": "截止日期或null",
  "description": "任務的詳細描述"
}

欄位規則：
1. **title**: 從訊息中提取核心任務，用簡潔的語句表達。不要照抄原文，要提煉重點。
2. **category**: 必須是以下其中之一：Meeting, Todo, Reminder, Note, Idea, Bug, Feature, Research, Communication。根據訊息內容智慧判斷最適合的分類。
3. **priority**: 必須是 High, Medium, Low 其中之一。根據以下線索判斷：
   - High: 包含「緊急」「重要」「馬上」「立刻」「ASAP」「deadline」等詞彙，或語氣急迫
   - Medium: 一般性任務，沒有特別的時間壓力
   - Low: 包含「有空再」「不急」「之後」「考慮」等詞彙
4. **due_date**: 如果訊息中提到時間，轉換為 ISO 8601 格式（YYYY-MM-DD）。今天的日期是 {today}。
   - 「明天」→ 明天的日期
   - 「下週一」→ 下週一的日期
   - 「月底」→ 本月最後一天
   - 如果沒有提到時間，回傳 null
5. **description**: 保留原始訊息的完整語意，補充任何有用的上下文資訊。

請只回傳 JSON，不要包含任何其他文字或 markdown 標記。"""


class LLMParser:
    """
    Uses LLM API to intelligently parse natural language into structured tasks.

    This parser sends the user's message to an OpenAI-compatible LLM endpoint
    along with a carefully crafted system prompt. The LLM returns structured
    JSON which is then validated and converted into a ParsedTask object.

    Attributes:
        client: The OpenAI client instance.
        model: The model identifier to use for completions.
        enabled: Whether the LLM parser is active (requires valid API key).
    """

    def __init__(self):
        self.model = llm_config.model
        self.enabled = bool(llm_config.api_key)

        if self.enabled:
            # Build client kwargs
            client_kwargs = {"api_key": llm_config.api_key}
            if llm_config.base_url:
                client_kwargs["base_url"] = llm_config.base_url
            self.client = OpenAI(**client_kwargs)
            logger.info(
                "LLM Parser initialized with model: %s", self.model
            )
        else:
            self.client = None
            logger.warning(
                "LLM Parser disabled: OPENAI_API_KEY not configured. "
                "Falling back to rule-based parsing."
            )

    def parse(self, text: str) -> Optional[dict]:
        """
        Parse a text message using the LLM API.

        Sends the user's message to the LLM with a structured system prompt,
        then parses the JSON response into a dictionary.

        Args:
            text: The raw text message from the user.

        Returns:
            A dictionary with keys: title, category, priority, due_date,
            description. Returns None if parsing fails or LLM is disabled.
        """
        if not self.enabled:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        system_prompt = SYSTEM_PROMPT.replace("{today}", today)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,  # Low temperature for consistent parsing
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("LLM returned empty response.")
                return None

            parsed = json.loads(content)
            logger.info("LLM parsed result: %s", json.dumps(parsed, ensure_ascii=False)[:200])

            # Validate required fields
            validated = self._validate_result(parsed)
            return validated

        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON response: %s", e)
            return None
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            return None

    def _validate_result(self, parsed: dict) -> Optional[dict]:
        """
        Validate and normalize the LLM's parsed output.

        Ensures all required fields are present and values are within
        expected ranges. Invalid values are corrected to defaults.

        Args:
            parsed: The raw dictionary from the LLM's JSON response.

        Returns:
            A validated dictionary, or None if the result is unusable.
        """
        valid_categories = {
            "Meeting", "Todo", "Reminder", "Note", "Idea",
            "Bug", "Feature", "Research", "Communication",
        }
        valid_priorities = {"High", "Medium", "Low"}

        result = {}

        # Title is required
        title = parsed.get("title", "").strip()
        if not title:
            logger.warning("LLM result missing title.")
            return None
        result["title"] = title

        # Category with fallback
        category = parsed.get("category", "Todo")
        result["category"] = category if category in valid_categories else "Todo"

        # Priority with fallback
        priority = parsed.get("priority", "Medium")
        result["priority"] = priority if priority in valid_priorities else "Medium"

        # Due date validation
        due_date = parsed.get("due_date")
        if due_date and due_date != "null":
            try:
                datetime.strptime(str(due_date), "%Y-%m-%d")
                result["due_date"] = str(due_date)
            except (ValueError, TypeError):
                logger.warning("Invalid due_date from LLM: %s", due_date)
                result["due_date"] = None
        else:
            result["due_date"] = None

        # Description
        result["description"] = parsed.get("description", "")

        return result

    def is_available(self) -> bool:
        """Check if the LLM parser is enabled and ready."""
        return self.enabled and self.client is not None
