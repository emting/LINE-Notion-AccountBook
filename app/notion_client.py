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
    """補習班記帳 Notion 資料庫客戶端。"""

    def __init__(self) -> None:
        self.api_key = notion_config.api_key
        self.data_source_id = notion_config.data_source_id
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
        
        # 取得今天日期 YYYY-MM-DD
        today_date = datetime.now().strftime("%Y-%m-%d")
        
        properties: dict = {
            "摘要": {
                "title": [{"text": {"content": title}}]
            },
            "金額": {"number": float(amount)},
            "收支類型": {"select": {"name": entry_type}},
            "分類": {"select": {"name": category}},
            "付款方式": {"select": {"name": payment_method}},
            "備註": {
                "rich_text": [{"text": {"content": str(description)[:2000]}}]
                if description else []
            },
            "記錄時間": {"date": {"start": today_date}},
        }

        # 選填欄位處理
        if date:
            try:
                formatted_date = datetime.fromisoformat(date.replace("/", "-")).strftime("%Y-%m-%d")
                properties["日期"] = {"date": {"start": formatted_date}}
            except (ValueError, TypeError):
                properties["日期"] = {"date": {"start": today_date}}
        else:
            properties["日期"] = {"date": {"start": today_date}}

        if vendor:
            properties["對象/廠商"] = {
                "rich_text": [{"text": {"content": str(vendor)}}]
            }
        
        if invoice_number:
            properties["發票號碼"] = {
                "rich_text": [{"text": {"content": str(invoice_number)}}]
            }
        
        if tax_amount is not None:
            properties["稅額"] = {"number": float(tax_amount)}
        
        if source_user:
            properties["記錄人"] = {
                "rich_text": [{"text": {"content": str(source_user)}}]
            }

        return self._create_page(properties)

    def _create_page(self, properties: dict) -> dict:
        """向 Notion API 提交一頁（一筆記帳記錄）。"""
        url = f"{NOTION_API_BASE}/pages"
        payload = {
            "parent": {"data_source_id": self.data_source_id},
            "properties": properties,
        }
        try:
            response = requests.post(
                url, headers=self.headers, json=payload, timeout=30
            )
            if not response.ok:
                logger.error("Notion API Error: %s", response.text)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            error_body = exc.response.text if exc.response is not None else str(exc)
            status_code = exc.response.status_code if exc.response is not None else "Unknown"
            logger.error(
                "Notion API Error. Status: %s, Response: %s, Parent: %s",
                status_code,
                error_body,
                payload.get("parent")
            )
            raise NotionClientError(
                f"Failed (Status {status_code}): {error_body}"
            ) from exc
        except requests.RequestException as exc:
            raise NotionClientError(f"Request failed: {exc}") from exc

    def get_database_schema(self) -> dict:
        """讀取 Notion 資料庫 Schema。"""
        # 這裡我們維持原有的 API 調用方式，或根據需要調整
        url = f"{NOTION_API_BASE}/databases/{self.data_source_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json().get("properties", {})
        except requests.RequestException as exc:
            raise NotionClientError(f"Schema retrieval failed: {exc}") from exc
