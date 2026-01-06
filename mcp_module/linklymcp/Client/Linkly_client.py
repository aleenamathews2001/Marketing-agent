import os
import json
import asyncio
from typing import Any, Optional

import httpx
from config import CONFIG
from Error.linkly_error import LinklyApiError


class LinklyApiClient:
    """Handles all HTTP communication with the Linkly API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, workspace_id: Optional[str] = None):
        self.api_key = api_key or CONFIG["LINKLY_API_KEY"]
        self.base_url = base_url or CONFIG["LINKLY_BASE_URL"]
        self.workspace_id = workspace_id or CONFIG["LINKLY_WORKSPACE"]
        self.timeout = CONFIG.get("REQUEST_TIMEOUT", 30000) / 1000  # convert ms → seconds

        if not self.api_key:
            raise ValueError("LINKLY_API_KEY is required. Please set it in .env file.")

        # Use a single session for performance with follow_redirects
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)

    async def request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None) -> Any:
        """Send an async request to the Linkly API."""

        # Add api_key as query parameter (use & if endpoint already has query params)
        separator = "&" if "?" in endpoint else "?"
        url = f"{self.base_url}{endpoint}{separator}api_key={self.api_key}"
        
        headers = {
            "Content-Type": "application/json",
        }

        # Include JSON body if provided
        request_kwargs = {"headers": headers}
        if data is not None:
            request_kwargs["json"] = data

        try:
            response = await self._client.request(method, url, **request_kwargs)
            if response.status_code >= 400:
                await self._handle_error(response)

            if response.status_code == 204:
                return {}  # No content

            if "application/json" in response.headers.get("content-type", ""):
                return response.json()

            return {}

        except httpx.ReadTimeout:
            raise LinklyApiError(408, "Request timeout")
        except httpx.ConnectError as e:
            raise LinklyApiError(503, f"Network error: {str(e)}")
        except Exception as e:
            raise LinklyApiError(500, f"Unexpected error: {str(e)}")

    async def _handle_error(self, response: httpx.Response):
        """Handle Linkly error responses with detailed messages."""
        try:
            error_obj = response.json()
        except Exception:
            error_obj = {"message": response.text}

        status = response.status_code
        message = error_obj.get("message", "Unknown error")

        if status == 400:
            raise LinklyApiError(400, "Bad request - Invalid parameters", error_obj)
        elif status == 401:
            raise LinklyApiError(401, "Authentication failed - Invalid API key", error_obj)
        elif status == 403:
            raise LinklyApiError(403, "Access forbidden - Insufficient permissions", error_obj)
        elif status == 404:
            raise LinklyApiError(404, "Resource not found", error_obj)
        elif status == 429:
            raise LinklyApiError(429, "Rate limit exceeded - Too many requests", error_obj)
        elif status >= 500:
            raise LinklyApiError(500, "Linkly server error", error_obj)
        else:
            raise LinklyApiError(status, message, error_obj)

    async def close(self):
        """Gracefully close the HTTP client."""
        await self._client.aclose()