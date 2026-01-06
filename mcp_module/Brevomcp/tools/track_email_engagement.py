
from typing import Any, List, Dict, Optional
from urllib.parse import urlencode
from client.brevo_client import BrevoApiClient
from Error.brevo_error import BrevoApiError
 
async def track_email_engagement(
emails: List[str]
 )->Dict[str, Any]:
    """
    Track email engagement (opens, clicks, bounces, deliveries) for one or more
    email addresses using Brevo.

    Use this tool after sending emails to see who engaged. It calls Brevo's
    statistics API, returns per-email metrics plus an overall campaign summary
    with open/click/bounce/delivery rates.
    """
    

    if not emails:
        return {"status": "error", "error": "Missing required input: emails"}

    client = BrevoApiClient()
    engagement_results: Dict[str, Any] = {}

    try:
        for email in emails:
            try:
                events_data = await get_statistics_events(client, email)
                if events_data:
                    engagement_results[email] = events_data
                else:
                    engagement_results[email] = {
                        "email": email,
                        "note": "No events found. Email may not have been opened or tracking disabled.",
                        "opened": False,
                        "clicked": False,
                        "delivered": False,
                        "bounced": False
                    }

            except BrevoApiError as e:
                engagement_results[email] = {
                    "status": "error",
                    "error": f"[{e.status_code}] {e.message}"
                }
            except Exception as e:
                engagement_results[email] = {
                    "status": "error",
                    "error": str(e)
                }

    finally:
        await client.close()

    campaign_summary = calculate_campaign_summary(engagement_results)

    return {
        "summary": campaign_summary,
        "engagement": engagement_results,
        "note": "For real-time tracking, configure Brevo webhooks."
    }


async def get_statistics_events(
    client: BrevoApiClient,
    email: str
     
) -> Optional[Dict[str, Any]]:
    """
    Fetch email engagement data from Brevo's /smtp/statistics/events endpoint.
    """
    params = {"email": email, "limit": 100, "offset": 0}
   

    query_string = urlencode(params)
    url = f"/smtp/statistics/events?{query_string}"

    response = await client.request(url, method="GET")
    events = response.get("events", [])

    if not events:
        return None

    return parse_email_events(events)


def parse_email_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse events list from Brevo statistics endpoint into a normalized format.
    """
    data = {
        "opened": False,
        "clicked": False,
        "bounced": False,
        "unsubscribed": False,
        "complained": False,
        "delivered": False,
        "clicked_links": [],
        "open_count": 0,
        "click_count": 0,
        "events": events
    }

    for event in events:
        event_type = event.get("event")
        if event_type in ["first opening", "opened", "open"]:
            data["opened"] = True
            data["open_count"] += 1
        elif event_type == "clicks":
            data["clicked"] = True
            data["click_count"] += 1
            url = event.get("url") or event.get("link")
            if url and url not in data["clicked_links"]:
                data["clicked_links"].append(url)
        elif event_type in ["hard_bounce", "softBounces", "invalid_email"]:
            data["bounced"] = True
        elif event_type == "unsubscribe":
            data["unsubscribed"] = True
        elif event_type == "complaint":
            data["complained"] = True
        elif event_type == "delivered":
            data["delivered"] = True
         
        if data["clicked"] and not data["opened"]:
            data["opened"] = True   
            data["open_count"] = data["click_count"]   

    return data


def calculate_campaign_summary(engagement: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate per-email engagement results into an overall summary.
    """
    summary = {
        "total": 0,
        "opened": 0,
        "clicked": 0,
        "bounced": 0,
        "delivered": 0,
        "open_rate": 0,
        "click_rate": 0,
        "bounce_rate": 0,
        "delivery_rate": 0
    }

    for result in engagement.values():
        if result.get("status") == "error":
            continue
        summary["total"] += 1
        if result.get("opened"):
            summary["opened"] += 1
        if result.get("clicked"):
            summary["clicked"] += 1
        if result.get("bounced"):
            summary["bounced"] += 1
        if result.get("delivered"):
            summary["delivered"] += 1

    if summary["total"] > 0:
        summary["open_rate"] = round((summary["opened"] / summary["total"]) * 100, 2)
        summary["click_rate"] = round((summary["clicked"] / summary["total"]) * 100, 2)
        summary["bounce_rate"] = round((summary["bounced"] / summary["total"]) * 100, 2)
        summary["delivery_rate"] = round((summary["delivered"] / summary["total"]) * 100, 2)

    return summary
