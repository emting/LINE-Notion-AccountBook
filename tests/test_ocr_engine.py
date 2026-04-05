"""
OCR 引擎單元測試（Task #9 — 優化 ⑩）。

使用 pytest + monkeypatch，涵蓋以下情境：
- 初始化（有 / 無 API key）
- 正常辨識流程
- code fence 自動清理
- 非發票圖片 error payload
- 空 candidates 清單
- API 失敗回傳 None（含重試次數驗證）
- 引擎停用時不發出 HTTP 請求

Note: config/settings.py 使用 frozen=True dataclass，
因此以 monkeypatch 整個 llm_config 物件（MagicMock）取代，
而非直接對欄位 setattr。
"""

import json
from unittest.mock import MagicMock

import pytest
import requests

from app.ocr_engine import MAX_RETRIES, OCREngine


# ── 輔助 stub ─────────────────────────────────────────

class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _mock_llm_config(api_key: str, vision_model: str = "models/test-vision"):
    """建立 frozen=True 相容的 llm_config mock。"""
    cfg = MagicMock()
    cfg.api_key = api_key
    cfg.vision_model = vision_model
    cfg.model = vision_model
    return cfg


# ── 初始化測試 ────────────────────────────────────────

def test_init_without_api_key(monkeypatch):
    """無 API key 時 is_available() 應回傳 False。"""
    monkeypatch.setattr("app.ocr_engine.llm_config", _mock_llm_config(""))
    engine = OCREngine()
    assert engine.is_available() is False


def test_init_with_api_key(monkeypatch):
    """有 API key 時 is_available() 應回傳 True，model 正確設定。"""
    monkeypatch.setattr(
        "app.ocr_engine.llm_config",
        _mock_llm_config("test-key", "models/test-vision"),
    )
    engine = OCREngine()
    assert engine.is_available() is True
    assert engine.model == "models/test-vision"


# ── 成功路徑 ──────────────────────────────────────────

def test_recognize_success(monkeypatch):
    """正常 OCR 辨識應回傳完整結構化 dict。"""
    monkeypatch.setattr("app.ocr_engine.llm_config", _mock_llm_config("test-key"))
    engine = OCREngine()

    ocr_data = {
        "vendor": "7-ELEVEN",
        "items": [{"name": "飲料", "quantity": 1, "unit_price": 35, "amount": 35}],
        "total_amount": 35,
        "tax_amount": 0,
        "invoice_number": "AB12345678",
        "date": "2026-04-05",
        "payment_method": "現金",
        "raw_text": "7-ELEVEN 飲料 35",
        "confidence": 0.92,
    }
    payload = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(ocr_data, ensure_ascii=False)}]}}]
    }

    monkeypatch.setattr(
        "app.ocr_engine.requests.post",
        lambda *args, **kwargs: DummyResponse(payload),
    )
    result = engine.recognize(b"fake-image")

    assert result is not None
    assert result["vendor"] == "7-ELEVEN"
    assert result["total_amount"] == 35
    assert result["confidence"] == 0.92
    assert result["invoice_number"] == "AB12345678"


def test_recognize_strips_code_fence(monkeypatch):
    """Gemini 回傳 JSON 含 code fence 時應自動清除後正確解析（優化 ⑩）。"""
    monkeypatch.setattr("app.ocr_engine.llm_config", _mock_llm_config("test-key"))
    engine = OCREngine()

    fenced = (
        "```json\n"
        '{"vendor": "全家", "items": [], "total_amount": 88, "confidence": 0.8}\n'
        "```"
    )
    payload = {"candidates": [{"content": {"parts": [{"text": fenced}]}}]}
    monkeypatch.setattr(
        "app.ocr_engine.requests.post",
        lambda *args, **kwargs: DummyResponse(payload),
    )
    result = engine.recognize(b"fake-image")

    assert result is not None
    assert result["vendor"] == "全家"
    assert result["total_amount"] == 88


# ── 特殊 payload 路徑 ─────────────────────────────────

def test_recognize_non_receipt_payload(monkeypatch):
    """非發票/收據圖片時，Gemini 回傳 error 欄位，應原樣回傳 dict。"""
    monkeypatch.setattr("app.ocr_engine.llm_config", _mock_llm_config("test-key"))
    engine = OCREngine()

    error_data = {"error": "非發票或收據圖片", "raw_text": "風景照片"}
    payload = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(error_data, ensure_ascii=False)}]}}]
    }
    monkeypatch.setattr(
        "app.ocr_engine.requests.post",
        lambda *args, **kwargs: DummyResponse(payload),
    )
    result = engine.recognize(b"fake-image")

    assert result is not None
    assert result["error"] == "非發票或收據圖片"
    assert result["raw_text"] == "風景照片"


def test_recognize_empty_candidates(monkeypatch):
    """Gemini 回傳空 candidates 清單時應回傳 None。"""
    monkeypatch.setattr("app.ocr_engine.llm_config", _mock_llm_config("test-key"))
    engine = OCREngine()

    monkeypatch.setattr(
        "app.ocr_engine.requests.post",
        lambda *args, **kwargs: DummyResponse({"candidates": []}),
    )
    result = engine.recognize(b"fake-image")
    assert result is None


# ── 失敗路徑 ──────────────────────────────────────────

def test_recognize_request_failure(monkeypatch):
    """
    API 呼叫拋出 requests.RequestException 時應重試後回傳 None。

    Note: _post_with_retry 精確捕捉 requests.RequestException（Task #4 規格），
    因此 monkeypatch 拋出 RequestException 而非裸 Exception。
    """
    monkeypatch.setattr("app.ocr_engine.llm_config", _mock_llm_config("test-key"))
    engine = OCREngine()

    call_count = {"n": 0}

    def raise_request_error(*args, **kwargs):
        call_count["n"] += 1
        raise requests.RequestException("network error")

    monkeypatch.setattr("app.ocr_engine.requests.post", raise_request_error)
    result = engine.recognize(b"fake-image")

    assert result is None
    assert call_count["n"] == MAX_RETRIES + 1  # 3 次（含首次）


def test_recognize_disabled(monkeypatch):
    """無 API key 時 recognize() 應直接回傳 None，不發出任何 HTTP 請求。"""
    monkeypatch.setattr("app.ocr_engine.llm_config", _mock_llm_config(""))
    engine = OCREngine()

    call_count = {"n": 0}

    def should_not_call(*args, **kwargs):
        call_count["n"] += 1

    monkeypatch.setattr("app.ocr_engine.requests.post", should_not_call)
    result = engine.recognize(b"fake-image")

    assert result is None
    assert call_count["n"] == 0
