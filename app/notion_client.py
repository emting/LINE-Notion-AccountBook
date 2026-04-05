"""Notion API 記帳資料庫客戶端。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from config.settings import notion_config

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"


class NotionClientError(Exception):
    pass


class NotionAccountClient:
    """補習班記帳 Notion 資料庫客戶端。

    Notion 資料庫預期 Schema（12 欄位）：
    | 欄位名稱   | 類型       |
    |-----------|-----------|
    | 摘要       | title     |
    | 金額       | number    |
    | 收支類型   | select    |
    | 分類       | select    |
    | 日期       | date      |
    | 對象/廠商  | rich_text |
    | 付款方式   | select    |
    | 備註       | rich_text |
    | 發票號碼   | rich_text |
    | 稅額       | number    |
    | 記錄人     | rich_text |
    | 記錄時間   | date      |
    """

    def __init__(self) -> None:
        self.api_key = notion_config.api_key
        self.database_id = notion_config.database_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": notion_config.api_version,
        }

    def create_account_entry(
        self,
        title: str,
        amount: float,
        entry_type: str = "支出",
        category: str = "其他支出",
        date: Optional[str] = None,
        vendor: str = "",
        payment_method: str = "未指定",
        description: str = "",
        invoice_number: str = "",
        tax_amount: float = 0,
        source_user: str = "",
    ) -> dict:
        """建立一筆記帳紀錄並寫入 Notion 資料庫。"""
        properties: dict = {
            "摘要": {
                "title": [{"text": {"content": title}}]
            },
            "金額": {"number": amount},
            "收支類型": {"select": {"name": entry_type}},
            "分類": {"select": {"name": category}},
            "付款方式": {"select": {"name": payment_method}},
            "備註": {
                "rich_text": [{"text": {"content": description[:2000]}}]
                if description else []
            },
            "記錄時間": {"date": {"start": datetime.now().isoformat()}},
        }

        # 選填欄位
        if date:
            properties["日期"] = {"date": {"start": date}}
        if vendor:
            properties["對象/廠商"] = {
                "rich_text": [{"text": {"content": vendor}}]
            }
        if invoice_number:
            properties["發票號碼"] = {
                "rich_text": [{"text": {"content": invoice_number}}]
            }
        if tax_amount:
            properties["稅額"] = {"number": tax_amount}
        if source_user:
            properties["記錄人"] = {
                "rich_text": [{"text": {"content": source_user}}]
            }

        return self._create_page(properties)

    def _create_page(self, properties: dict) -> dict:
        """向 Notion API 提交一頁（一筆記帳記錄）。"""
        url = f"{NOTION_API_BASE}/pages"
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
        }
        try:
            response = requests.post(
                url, headers=self.headers, json=payload, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            error_body = exc.response.json() if exc.response else {}
            raise NotionClientError(
                f"Failed: {error_body.get('message', str(exc))}"
            ) from exc
        except requests.RequestException as exc:
            raise NotionClientError(f"Request failed: {exc}") from exc

    def get_database_schema(self) -> dict:
        """讀取 Notion 資料庫 Schema，可用於驗證欄位設定。"""
        url = f"{NOTION_API_BASE}/databases/{self.database_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json().get("properties", {})
        except requests.RequestException as exc:
            raise NotionClientError(f"Schema retrieval failed: {exc}") from exc
