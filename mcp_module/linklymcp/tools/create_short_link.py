from typing import List, Dict, Any, Optional
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from Client.Linkly_client import LinklyApiClient
from Error.linkly_error import LinklyApiError

async def create_short_link(
    url: str
) -> dict:
    """
    Create a personalized short link for a contact using the Linkly API.

    Use this tool when you need a trackable, compact URL for a specific user
    (e.g., for email campaigns or personalized outreach). Returns full link
    details or an error message.
    """
    client = LinklyApiClient()
    
    try:
       
        payload = {
            "workspace_id": client.workspace_id,
            "url": url
        }
        # Linkly API endpoint: POST /api/v1/link
        result = await client.request("/api/v1/link", method="POST", data=payload)
        
        return result
        
    except LinklyApiError as e:
        return {
            "error": f"[{e.status_code}] {e.message}",
            "details": e.details
        }
    finally:
        await client.close()
