import os
import json
import asyncio
from typing import Any, Optional

import httpx  # Fast async HTTP client
from config import CONFIG
from Error.brevo_error import BrevoApiError


class BrevoApiClient:
    """Handles all HTTP communication with the Brevo API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or CONFIG["BREVO_API_KEY"]
        self.base_url = base_url or CONFIG["API_BASE_URL"]
        self.timeout = CONFIG["REQUEST_TIMEOUT"] / 1000  # convert ms → seconds

        if not self.api_key:
            raise ValueError("BREVO_API_KEY is required. Please set it in .env file.")

        # Use a single session for performance
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None) -> Any:
        """Send an async request to the Brevo API."""

        url = f"{self.base_url}{endpoint}"
        headers = {
            "accept": "application/json",
            "api-key": self.api_key,
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
            raise BrevoApiError(408, "Request timeout")
        except httpx.ConnectError as e:
            raise BrevoApiError(503, f"Network error: {str(e)}")
        except Exception as e:
            raise BrevoApiError(500, f"Unexpected error: {str(e)}")

    async def _handle_error(self, response: httpx.Response):
        """Handle Brevo error responses with detailed messages."""
        try:
            error_obj = response.json()
        except Exception:
            error_obj = {"message": response.text}

        status = response.status_code
        message = error_obj.get("message", "Unknown error")

        if status == 400:
            raise BrevoApiError(400, "Bad request", error_obj)
        elif status == 401:
            if "IP address" in message:
                raise BrevoApiError(
                    401,
                    (
                        "Authentication failed: Your IP address needs to be whitelisted. "
                        "Visit https://app.brevo.com/security/authorised_ips"
                    ),
                    error_obj,
                )
            raise BrevoApiError(401, "Authentication failed", error_obj)
        elif status == 403:
            raise BrevoApiError(403, "Access forbidden", error_obj)
        elif status == 404:
            if "campaign" in message:
                raise BrevoApiError(404, "Campaign not found. Check the campaign ID.", error_obj)
            raise BrevoApiError(404, "Resource not found", error_obj)
        elif status == 429:
            raise BrevoApiError(429, "Rate limit exceeded", error_obj)
        elif status >= 500:
            raise BrevoApiError(500, "Server error", error_obj)
        else:
            raise BrevoApiError(status, message, error_obj)

    async def close(self):
        """Gracefully close the HTTP client."""
        await self._client.aclose()
