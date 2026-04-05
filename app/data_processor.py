"""
記帳資料處理器 — 雙引擎架構。
支援文字輸入與 OCR 辨識結果的統一處理。
"""

import re
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

from app.llm_parser import LLMParser
from app.ocr_engine import OCREngine

logger = logging.getLogger(__name__)

# 修正後收支關鍵字 (Bug #3)
INCOME_PHRASES = ["收到", "繳費", "入帳", "退款", "學費"]
EXPENSE_PHRASES = ["買", "付", "支付", "花", "購", "修", "租"]

# 分類關鍵字映射（Rule Engine fallback）
CATEGORY_KEYWORDS = {
    "教材費": ["講義", "教科書", "課本", "文具", "教材", "書"],
    "房租水電": ["房租", "水費", "電費", "網路", "瓦斯"],
    "人事費用": ["薪資", "薪水", "工讀", "助教", "鐘點費"],
    "設備維護": ["電腦", "投影機", "冷氣", "維修", "設備"],
    "辦公用品": ["影印", "墨水", "紙", "文具", "碳粉"],
    "餐飲點心": ["點心", "飲料", "便當", "餐", "零食"],
    "交通費": ["交通", "停車", "油費", "計程車", "高鐵"],
    "廣告行銷": ["傳單", "廣告", "招牌", "海報"],
    "學費收入": ["學費", "補習費", "課程費", "上課費"],
    "報名費": ["報名"],
    "教材收入": ["賣講義", "賣書"],
}

@dataclass
class AccountEntry:
    """結構化記帳資料。"""
    title: str = ""
    amount: float = 0.0
    entry_type: str = "支出"         # 收入 / 支出
    category: str = "其他支出"
    date: Optional[str] = None       # YYYY-MM-DD
    vendor: str = ""
    payment_method: str = "未指定"
    description: str = ""
    invoice_number: str = ""
    tax_amount: float = 0.0
    raw_text: str = ""
    parse_engine: str = "rule"       # "llm", "ocr", "rule"
    parse_confidence: float = 0.0
    items: list = field(default_factory=list)  # OCR 多品項

class DataProcessor:
    def __init__(self):
        self.llm_parser = LLMParser()
        self.ocr_engine = OCREngine()

    # ── 文字訊息處理 ──────────────────────────

    def process_text(self, text: str) -> AccountEntry:
        """處理文字輸入的記帳訊息。"""
        text = text.strip()
        if not text:
            return AccountEntry(raw_text=text)

        # 結構化格式（管道分隔）
        if "|" in text and ":" in text:
            entry = self._parse_structured(text)
        # 指令格式
        elif text.startswith("/record") or text.startswith("/收") or text.startswith("/支"):
            entry = self._parse_command(text)
        # 自由輸入：LLM → Rule fallback
        else:
            entry = self._parse_with_llm_fallback(text)

        entry.raw_text = text
        return entry

    # ── 圖片訊息處理（OCR）────────────────────

    def process_image(self, image_bytes: bytes) -> AccountEntry:
        """
        處理圖片（發票/收據）。
        1. Gemini Vision OCR 辨識圖片
        2. 將 OCR 結果轉為 AccountEntry
        """
        if not self.ocr_engine.is_available():
            return AccountEntry(
                title="OCR 辨識失敗",
                description="OCR 引擎未啟用",
                parse_engine="ocr",
                parse_confidence=0.0,
            )

        ocr_result = self.ocr_engine.recognize(image_bytes)
        if not ocr_result:
            return AccountEntry(
                title="OCR 辨識失敗",
                description="無法辨識圖片內容",
                parse_engine="ocr",
                parse_confidence=0.0,
            )

        # 檢查是否為錯誤回應
        if "error" in ocr_result:
            return AccountEntry(
                title=ocr_result.get("error", "非發票圖片"),
                description=ocr_result.get("raw_text", ""),
                parse_engine="ocr",
                parse_confidence=0.1,
            )

        # 將 OCR 結果轉為 AccountEntry
        entry = AccountEntry(
            title=self._build_ocr_title(ocr_result),
            amount=float(ocr_result.get("total_amount", 0) or 0),
            entry_type="支出",  # 發票/收據預設為支出
            category=self._classify_ocr(ocr_result),
            date=ocr_result.get("date"),
            vendor=ocr_result.get("vendor", ""),
            payment_method=ocr_result.get("payment_method", "未指定"),
            description=ocr_result.get("raw_text", ""),
            invoice_number=ocr_result.get("invoice_number", ""),
            tax_amount=float(ocr_result.get("tax_amount", 0) or 0),
            items=ocr_result.get("items", []),
            parse_engine="ocr",
            parse_confidence=float(ocr_result.get("confidence", 0.8)),
        )
        return entry

    # ── LLM Fallback ─────────────────────────

    def _parse_with_llm_fallback(self, text: str) -> AccountEntry:
        if self.llm_parser.is_available():
            result = self.llm_parser.parse(text)
            if result and result.get("title"):
                return AccountEntry(
                    title=result["title"],
                    amount=float(result.get("amount", 0) or 0),
                    entry_type=result.get("type", "支出"),
                    category=result.get("category", "其他支出"),
                    date=result.get("date"),
                    vendor=result.get("vendor", ""),
                    payment_method=result.get("payment_method", "未指定"),
                    description=result.get("description", ""),
                    invoice_number=result.get("invoice_number", ""),
                    tax_amount=float(result.get("tax_amount", 0) or 0),
                    parse_engine="llm",
                    parse_confidence=0.95,
                )
        # Rule Engine fallback
        return self._parse_freeform(text)

    # ── Rule Engine 解析 ─────────────────────

    def _parse_freeform(self, text: str) -> AccountEntry:
        entry = AccountEntry(parse_engine="rule", parse_confidence=0.6)
        entry.amount = self._extract_amount(text)
        entry.entry_type = self._detect_type(text)
        entry.category = self._detect_category(text, entry.entry_type)
        entry.date = self._detect_date(text)
        entry.title = self._clean_title(text)
        entry.description = text
        return entry

    def _parse_structured(self, text: str) -> AccountEntry:
        """解析：摘要: xxx | 金額: 1000 | 類型: 支出"""
        entry = AccountEntry(parse_engine="rule", parse_confidence=0.85)
        field_map = {
            "摘要": "title", "標題": "title", "title": "title",
            "金額": "amount", "amount": "amount",
            "類型": "entry_type", "type": "entry_type",
            "分類": "category", "category": "category",
            "日期": "date", "date": "date",
            "對象": "vendor", "vendor": "vendor",
            "付款方式": "payment_method",
            "發票號碼": "invoice_number",
        }
        for part in text.split("|"):
            sep = "：" if "：" in part else ":" if ":" in part else None
            if not sep:
                continue
            try:
                key, value = part.split(sep, 1)
                key = key.strip().lower()
                value = value.strip()
                mapped = field_map.get(key)
                if mapped == "title":
                    entry.title = value
                elif mapped == "amount":
                    entry.amount = self._parse_number(value)
                elif mapped == "entry_type":
                    entry.entry_type = "收入" if "收" in value else "支出"
                elif mapped == "category":
                    entry.category = value
                elif mapped == "date":
                    entry.date = self._parse_date_str(value)
                elif mapped == "vendor":
                    entry.vendor = value
                elif mapped == "payment_method":
                    entry.payment_method = value
                elif mapped == "invoice_number":
                    entry.invoice_number = value
            except ValueError:
                continue
        return entry

    def _parse_command(self, text: str) -> AccountEntry:
        """/record 買講義 1500 或 /支 講義 1500 或 /收 學費 5000"""
        entry = AccountEntry(parse_engine="rule", parse_confidence=0.9)
        if text.startswith("/收"):
            entry.entry_type = "收入"
            content = text[2:].strip()
        elif text.startswith("/支"):
            entry.entry_type = "支出"
            content = text[2:].strip()
        else:
            content = text[7:].strip()  # /record

        entry.amount = self._extract_amount(content)
        entry.title = re.sub(r"[\$＄NT\$]?\s*[\d,]+\.?\d*", "", content).strip()
        entry.category = self._detect_category(
            entry.title, entry.entry_type)
        return entry

    # ── 工具方法 ──────────────────────────────

    def _extract_amount(self, text: str) -> float:
        """
        從文字提取金額。 (Bug #2: Fixed regex patterns)
        """
        patterns = [
            r"NT\$\s*([\d,]+\.?\d*)",       # NT$4,500
            r"[\$＄]\s*([\d,]+\.?\d*)",      # $4,500 / ＄4,500
            r"([\d,]+\.?\d*)\s*[元塊]",      # 4500元 / 4500塊
            r"([\d,]+\.?\d+)"              # Bare numbers (last resort)
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return self._parse_number(match.group(1))
        return 0.0

    def _parse_number(self, s: str) -> float:
        try:
            return abs(float(s.replace(",", "")))
        except (ValueError, TypeError):
            return 0.0

    def _detect_type(self, text: str) -> str:
        """
        偵測收支類型。 (Bug #3: Using phrases to avoid ambiguity)
        """
        for ph in INCOME_PHRASES:
            if ph in text:
                return "收入"
        for ph in EXPENSE_PHRASES:
            if ph in text:
                return "支出"
        return "支出"

    def _detect_category(self, text: str, entry_type: str) -> str:
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return cat
        return "其他收入" if entry_type == "收入" else "其他支出"

    def _detect_date(self, text: str) -> Optional[str]:
        relative = {"今天": 0, "昨天": -1, "前天": -2}
        for kw, delta in relative.items():
            if kw in text:
                d = datetime.now() + timedelta(days=delta)
                return d.strftime("%Y-%m-%d")
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        return None

    def _parse_date_str(self, s: str) -> Optional[str]:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return self._detect_date(s)

    def _clean_title(self, text: str) -> str:
        title = re.sub(r"[\$＄NT\$]?\s*[\d,]+\.?\d*\s*[元塊]?", "", text)
        title = re.sub(r"[，,度。、]\s*$", "", title.strip())
        return title.strip()[:50] if title.strip() else text[:50]

    def _build_ocr_title(self, ocr: dict) -> str:
        vendor = ocr.get("vendor", "")
        items = ocr.get("items", [])
        if items:
            first_item = items[0].get("name", "")
            suffix = f" 等 {len(items)} 項" if len(items) > 1 else ""
            return f"{vendor} - {first_item}{suffix}".strip(" -")
        return vendor or "發票/收據"

    def _classify_ocr(self, ocr: dict) -> str:
        all_text = ocr.get("raw_text", "")
        items_text = " ".join(
            item.get("name", "") for item in ocr.get("items", []) if item.get("name")
        )
        combined = f"{all_text} {items_text}"
        return self._detect_category(combined, "支出")

    # ── 確認訊息 ─────────────────────────────

    def format_confirmation(self, entry: AccountEntry) -> str:
        icon = "💰" if entry.entry_type == "收入" else "💸"
        engine_map = {
            "llm": "AI 智慧解析",
            "ocr": "發票 OCR 辨識",
            "rule": "規則引擎解析",
        }
        engine_label = engine_map.get(entry.parse_engine, "解析")

        lines = [
            f"{icon} 已記錄到 Notion 資料庫！",
            f"（{engine_label}，信心度 {entry.parse_confidence:.0%}）",
            "",
            f"📋 摘要：{entry.title}",
            f"{icon} 類型：{entry.entry_type}",
            f"💵 金額：${entry.amount:,.0f}",
            f"📁 分類：{entry.category}",
        ]
        if entry.date:
            lines.append(f"📅 日期：{entry.date}")
        if entry.vendor:
            lines.append(f"🏪 對象：{entry.vendor}")
        if entry.invoice_number:
            lines.append(f"🧾 發票：{entry.invoice_number}")
        if entry.payment_method != "未指定":
            lines.append(f"💳 付款：{entry.payment_method}")
        if entry.items:
            lines.append(f"📦 品項：共 {len(entry.items)} 項")

        return "\n".join(lines)
