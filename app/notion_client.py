"""
Notion API Integration Client.

This module provides a client for interacting with the Notion API,
specifically for creating pages (rows) in a Notion database. It handles
authentication, request formatting, and error management.
"""

import logging
from datetime import datetime
from typing import Optional

import requests

from config.settings import notion_config

logger = logging.getLogger(__name__)

# Notion API base URL
NOTION_API_BASE = "https://api.notion.com/v1"


class NotionClientError(Exception):
    """Raised when a Notion API request fails."""
    pass


class NotionDatabaseClient:
    """Client for reading from and writing to a Notion database."""

    def __init__(self):
        self.api_key = notion_config.api_key
        self.database_id = notion_config.database_id
        self.api_version = notion_config.api_version
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.api_version,
        }

    def create_page(self, properties: dict) -> dict:
        """
        Create a new page (row) in the configured Notion database.

        This method sends a POST request to the Notion Pages API endpoint.
        The properties parameter must conform to the target database's schema.

        Args:
            properties: A dictionary of property names to property value objects,
                        following the Notion API page properties format.

        Returns:
            The created page object from the Notion API response.

        Raises:
            NotionClientError: If the API request fails.
        """
        url = f"{NOTION_API_BASE}/pages"
        payload = {
            "parent": {
                "database_id": self.database_id,
            },
            "properties": properties,
        }

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            page_id = result.get("id", "unknown")
            logger.info("Successfully created Notion page: %s", page_id)
            return result
        except requests.HTTPError as e:
            error_body = e.response.json() if e.response else {}
            error_msg = error_body.get("message", str(e))
            logger.error("Notion API error: %s", error_msg)
            raise NotionClientError(f"Failed to create page: {error_msg}") from e
        except requests.RequestException as e:
            logger.error("Notion request failed: %s", e)
            raise NotionClientError(f"Request failed: {e}") from e

    def create_task_entry(
        self,
        title: str,
        category: str = "",
        priority: str = "Medium",
        due_date: Optional[str] = None,
        description: str = "",
        source_user: str = "",
        status: str = "Not Started",
    ) -> dict:
        """
        Create a structured task entry in the Notion database.

        This is a high-level convenience method that maps parsed task data
        into the Notion database property format. The target database should
        have the following properties configured:

        | Property Name | Type     | Description                          |
        |---------------|----------|--------------------------------------|
        | Name          | title    | The task title (required)            |
        | Category      | select   | Task category (e.g., Meeting, Todo)  |
        | Priority      | select   | Priority level (High, Medium, Low)   |
        | Due Date      | date     | Optional due date in ISO 8601 format |
        | Description   | rich_text| Detailed description of the task     |
        | Source        | rich_text| Who sent this task (LINE user)       |
        | Status        | select   | Current task status                  |
        | Created At    | date     | Timestamp when the entry was created |

        Args:
            title: The task title.
            category: The task category.
            priority: Priority level (High, Medium, Low).
            due_date: Due date in ISO 8601 format (YYYY-MM-DD), or None.
            description: Detailed description text.
            source_user: The LINE display name of the sender.
            status: Current status of the task.

        Returns:
            The created page object from the Notion API.
        """
        properties = {
            "Name": {
                "title": [
                    {
                        "text": {"content": title},
                    }
                ],
            },
            "Category": {
                "select": {"name": category} if category else None,
            },
            "Priority": {
                "select": {"name": priority},
            },
            "Description": {
                "rich_text": [
                    {
                        "text": {"content": description[:2000]},
                    }
                ]
                if description
                else [],
            },
            "Source": {
                "rich_text": [
                    {
                        "text": {"content": f"LINE: {source_user}"},
                    }
                ]
                if source_user
                else [],
            },
            "Status": {
                "select": {"name": status},
            },
            "Created At": {
                "date": {
                    "start": datetime.now().isoformat(),
                },
            },
        }

        # Add due date only if provided
        if due_date:
            properties["Due Date"] = {
                "date": {"start": due_date},
            }

        # Remove properties with None values (e.g., empty category)
        properties = {
            k: v for k, v in properties.items() if v is not None
        }

        return self.create_page(properties)

    def query_database(self, filter_obj: Optional[dict] = None) -> list[dict]:
        """
        Query the Notion database and return matching pages.

        Args:
            filter_obj: Optional Notion filter object to narrow results.

        Returns:
            A list of page objects matching the query.
        """
        url = f"{NOTION_API_BASE}/databases/{self.database_id}/query"
        payload = {}
        if filter_obj:
            payload["filter"] = filter_obj

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            logger.info("Query returned %d result(s).", len(results))
            return results
        except requests.RequestException as e:
            logger.error("Failed to query Notion database: %s", e)
            raise NotionClientError(f"Query failed: {e}") from e

    def get_database_schema(self) -> dict:
        """
        Retrieve the database schema (properties definition).

        Returns:
            A dictionary describing the database's property schema.
        """
        url = f"{NOTION_API_BASE}/databases/{self.database_id}"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            db_obj = response.json()
            properties = db_obj.get("properties", {})
            logger.info(
                "Retrieved schema with %d properties.", len(properties)
            )
            return properties
        except requests.RequestException as e:
            logger.error("Failed to retrieve database schema: %s", e)
            raise NotionClientError(f"Schema retrieval failed: {e}") from e
