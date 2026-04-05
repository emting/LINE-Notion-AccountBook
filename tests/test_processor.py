"""
Data Processor 整合與單元測試（Task #11 — 優化 ⑩）。

使用 pytest + monkeypatch，涵蓋以下情境：
- Bug #2：NT$ 等各種金額正則解析
- Bug #3：收支詞組判斷與避免誤判
- 自由文字 / 結構化 / 指令格式解析
- 相對日期解析
- LLM 失敗時 fallback 到 Rule Engine
- format_confirmation 輸出
"""

import pytest
from unittest.mock import MagicMock

from app.data_processor import AccountEntry, DataProcessor


@pytest.fixture
def processor():
    return DataProcessor()


# ── 金額提取與正則（Bug #2 修正）─────────────────────

def test_extract_amount_nt_dollar(processor):
    assert processor._extract_amount("NT$4,500") == 4500.0
    assert processor._extract_amount("NT$1200") == 1200.0


def test_extract_amount_dollar_sign(processor):
    assert processor._extract_amount("$1,200") == 1200.0


def test_extract_amount_fullwidth_dollar(processor):
    assert processor._extract_amount("＄300") == 300.0


def test_extract_amount_yuan_suffix(processor):
    assert processor._extract_amount("1200元") == 1200.0


def test_extract_amount_kuai_suffix(processor):
    assert processor._extract_amount("300塊") == 300.0


def test_extract_amount_bare_number(processor):
    """測試裸數字 (指令 fallback)"""
    assert processor._extract_amount("4500") == 4500.0


def test_extract_amount_no_amount(processor):
    assert processor._extract_amount("買了講義") == 0.0


def test_extract_amount_decimal(processor):
    assert processor._extract_amount("NT$10,000.5") == 10000.5


# ── 收支與分類判斷（Bug #3 修正）────────────────────

@pytest.mark.parametrize("text, expected", [
    ("收到學費 5000", "收入"),
    ("入帳五千", "收入"),
    ("退款處理完成", "收入"),
    ("繳費成功", "收入"),
    ("買了便當", "支出"),
    ("付房租", "支出"),
    ("購買影印紙", "支出"),
])
def test_detect_type_phrases(processor, text, expected):
    """測試完整詞組辨識，避免單字歧義。"""
    assert processor._detect_type(text) == expected


def test_detect_type_avoids_receipt_false_positive(processor, monkeypatch):
    """測試「收據」不該被誤判為「收入」。"""
    monkeypatch.setattr(processor.llm_parser, "is_available", lambda: False)
    entry = processor.process_text("收據一張，買文具 200 元")
    assert entry.entry_type == "支出"


@pytest.mark.parametrize("text, entry_type, expected", [
    ("影印紙 100", "支出", "辦公用品"),
    ("講義 500", "支出", "教材費"),
    ("水電費 2000", "支出", "房租水電"),
    ("工讀生薪資", "支出", "人事費用"),
    ("收到學費 5000", "收入", "學費收入"),
    ("活動報名費", "收入", "報名費"),
    ("未知支出", "支出", "其他支出"),
    ("未知收入", "收入", "其他收入"),
])
def test_detect_category(processor, text, entry_type, expected):
    """分類關鍵字自動對應與預設值測試。"""
    assert processor._detect_category(text, entry_type) == expected


def test_relative_date_detection(processor, monkeypatch):
    """測試昨天、今天等相對日期。"""
    monkeypatch.setattr(processor.llm_parser, "is_available", lambda: False)
    entry = processor.process_text("昨天買講義 500 元")
    assert entry.date is not None


# ── 輸入格式路由 ──────────────────────────────────────

def test_process_freeform_text_with_nt_amount(processor, monkeypatch):
    monkeypatch.setattr(processor.llm_parser, "is_available", lambda: False)
    entry = processor.process_text("買了 30 本數學講義 NT$4,500")
    assert entry.amount == 4500
    assert entry.entry_type == "支出"
    assert entry.category == "教材費"
    assert entry.parse_engine == "rule"


def test_process_structured_text(processor):
    entry = processor.process_text("摘要: 講義 | 金額: 4500 | 類型: 支出 | 分類: 教材費")
    assert entry.title == "講義"
    assert entry.amount == 4500
    assert entry.entry_type == "支出"
    assert entry.category == "教材費"
    assert entry.parse_engine == "rule"


def test_process_command_expense(processor):
    entry = processor.process_text("/支 講義 4500")
    assert entry.entry_type == "支出"
    assert entry.amount == 4500.0
    assert entry.parse_engine == "rule"


def test_process_command_income(processor):
    entry = processor.process_text("/收 王小明學費 12000")
    assert entry.entry_type == "收入"
    assert entry.amount == 12000.0
    assert entry.parse_engine == "rule"


def test_process_empty_text(processor):
    entry = processor.process_text("")
    assert entry.title == ""
    assert entry.amount == 0.0


# ── LLM 降級機制 ─────────────────────────────────────

def test_rule_engine_fallback_when_llm_returns_none(processor, monkeypatch):
    """LLM 回傳 None 時（例如解析失敗），應退回 Rule Engine。"""
    monkeypatch.setattr(processor.llm_parser, "is_available", lambda: True)
    monkeypatch.setattr(processor.llm_parser, "parse", lambda text: None)
    entry = processor.process_text("買影印紙 300 元")
    
    assert entry.parse_engine == "rule"
    assert entry.amount == 300.0
    assert entry.entry_type == "支出"
    assert entry.category == "辦公用品"


# ── 圖片 / OCR 路徑 ───────────────────────────────────

def test_process_image_ocr_disabled(processor, monkeypatch):
    """OCR 引擎未啟用時應回傳失敗 entry。"""
    monkeypatch.setattr(processor.ocr_engine, "is_available", lambda: False)
    entry = processor.process_image(b"fake")
    assert entry.title == "OCR 辨識失敗"
    assert entry.parse_engine == "ocr"


def test_process_image_ocr_success(processor, monkeypatch):
    """OCR 成功時應正確對應欄位。"""
    monkeypatch.setattr(processor.ocr_engine, "is_available", lambda: True)
    mock_recognize = MagicMock(return_value={
        "vendor": "7-11",
        "total_amount": 150,
        "confidence": 0.95,
        "items": [{"name": "飲料", "amount": 150}],
        "raw_text": "7-11 飲料 150",
    })
    monkeypatch.setattr(processor.ocr_engine, "recognize", mock_recognize)
    
    entry = processor.process_image(b"fake")
    assert entry.vendor == "7-11"
    assert entry.amount == 150.0
    assert entry.parse_engine == "ocr"


# ── 輸出格式 ──────────────────────────────────────────

def test_format_confirmation(processor):
    entry = AccountEntry(
        title="講義採購",
        amount=4500,
        entry_type="支出",
        category="教材費",
        parse_engine="rule",
        parse_confidence=0.9,
    )
    message = processor.format_confirmation(entry)
    
    assert "💸" in message
    assert "講義採購" in message
    assert "教材費" in message
    assert "$4,500" in message
    assert "規則引擎解析" in message


def test_format_confirmation_income(processor):
    entry = AccountEntry(
        title="學費",
        amount=12000,
        entry_type="收入",
        category="學費收入",
        parse_engine="llm",
        parse_confidence=0.95,
    )
    message = processor.format_confirmation(entry)
    
    assert "💰" in message
    assert "AI 智慧解析" in message
    assert "學費" in message
    assert "$12,000" in message
