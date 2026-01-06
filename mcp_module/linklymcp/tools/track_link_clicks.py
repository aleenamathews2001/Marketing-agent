from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, parse_qs
from Client.Linkly_client import LinklyApiClient
from Error.linkly_error import LinklyApiError

async def track_link_clicks(
    campaign_id: Optional[str] = None,
    link_ids: Optional[List[int]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
    exclude_bots: bool = True,
    unique_only: bool = False,
    # timezone: str = "",
    frequency: str = "day",
    debug: bool = False
) -> dict:
    """
    Track link clicks and campaign engagement using the Linkly API.

    Use this tool to analyze how contacts interact with your short links—
    including total clicks, per-link analytics, country/device stats, and
    overall engagement rates. Supports tracking by campaign_id or link_ids.
    """

    client = LinklyApiClient()
    
    try:
        # Default to last 30 days
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        debug_info = {
            "steps": [],
            "links_found": [],
            "campaign_search": campaign_id
        }
        
        # Step 1: Get link IDs if campaign_id provided but no link_ids
        if campaign_id and not link_ids:
            try:
                links_endpoint = f"/api/v1/workspace/{client.workspace_id}/links"
                debug_info["steps"].append(f"Fetching links from: {links_endpoint}")
                
                links_response = await client.request(links_endpoint, method="GET")
                debug_info["steps"].append(f"Links response type: {type(links_response)}")
                
                link_ids = []
                links_data = []
                
                # Handle different response formats
                if isinstance(links_response, list):
                    links_data = links_response
                    debug_info["steps"].append(f"Got {len(links_data)} links in list format")
                elif isinstance(links_response, dict):
                    if "links" in links_response:
                        links_data = links_response["links"]
                        debug_info["steps"].append(f"Got {len(links_data)} links from 'links' key")
                    elif "data" in links_response:
                        links_data = links_response["data"]
                        debug_info["steps"].append(f"Got {len(links_data)} links from 'data' key")
                    elif "results" in links_response:
                        links_data = links_response["results"]
                        debug_info["steps"].append(f"Got {len(links_data)} links from 'results' key")
                
                # Find links matching the campaign
                for link in links_data:
                    debug_info["steps"].append(f"Get {link} links ")
                    # Check both destination and formatted_url (Linkly stores base URL in destination)
                    link_destination = link.get("destination", "")
                    link_formatted = link.get("formatted_url", "")
                    link_url = link.get("url", "")
                    link_id = link.get("id") or link.get("link_id")
                    
                    # Combine all possible URL fields
                    all_urls = f"{link_destination} {link_formatted} {link_url}"
                    
                    # Store for debugging
                    if debug:
                        debug_info["links_found"].append({
                            "link_id": link_id,
                            "destination": link_destination,
                            "formatted_url": link_formatted,
                            "matches": campaign_id in all_urls
                        })
                    
                    # Check multiple patterns for campaign matching
                    patterns = [
                        f"campaign={campaign_id}",
                        f"campaign_id={campaign_id}",
                        f"campaignId={campaign_id}",
                        campaign_id  # Just the campaign ID anywhere
                    ]
                    
                    if any(pattern in all_urls for pattern in patterns):
                        if link_id:
                            link_ids.append(str(link_id))
                            debug_info["steps"].append(f"Matched link {link_id}")
                
                debug_info["total_links_checked"] = len(links_data)
                debug_info["matching_links_found"] = len(link_ids)
                
                if not link_ids:
                    return {
                        "status": "no_links_found",
                        "message": f"No links found for campaign '{campaign_id}'",
                        "campaign_id": campaign_id,
                        "debug_info": debug_info if debug else None,
                        "suggestion": "Check if campaign_id matches exactly. Enable debug=True to see all links."
                    }
                    
            except Exception as e:
                import traceback
                return {
                    "status": "error_fetching_links",
                    "error": str(e),
                    "traceback": traceback.format_exc() if debug else None,
                    "debug_info": debug_info if debug else None
                }
        
        if not link_ids:
            return {
                "status": "missing_parameters",
                "message": "Please provide either campaign_id or link_ids"
            }
        
        debug_info["link_ids_to_check"] = link_ids
        
        # Step 2: Fetch clicks for each link
        all_clicks = []
        base_params = {
            
            "unique": "true" if unique_only else "false",
            "format": "json",
            "frequency": "day"
            
        }
        
        if country:
            base_params["country"] = country.upper()
        
        clicks_per_link = {}
        errors_per_link = {}
        
        for link_id in link_ids:
            params = base_params.copy()
            params["link_id"] = str(link_id)
            
            query_string = urlencode(params)
            # Build endpoint with query string (API key will be added by client)
            endpoint = f"/api/v1/workspace/{client.workspace_id}/clicks?{query_string}"
            
            if debug:
                debug_info["steps"].append(f"Fetching clicks for link {link_id}")
            
            try:
                result = await client.request(endpoint, method="GET")
                debug_info["steps"].append(f"Fetching result for link {result}")
                link_clicks = []
                if isinstance(result, dict):
                    if "traffic" in result:
                        traffic_data = result.get("traffic", [])
                        click_count = sum(item.get("y", 0) for item in traffic_data if isinstance(item, dict))
                        clicks_per_link[link_id] = click_count
                        link_clicks = []  # Or handle as needed
                    else:
                        # Handle individual click data
                        link_clicks = result.get("clicks", []) or result.get("data", [])
                        clicks_per_link[link_id] = len(link_clicks)
                # if isinstance(result, list):
                #     link_clicks = result
                # elif isinstance(result, dict):
                #     link_clicks = result.get("clicks", []) or result.get("data", [])
                
                # clicks_per_link[link_id] = len(link_clicks)
                # all_clicks.extend(link_clicks)
                
                if debug:
                    debug_info["steps"].append(f"Link {link_id}: {len(link_clicks)} clicks")
                    
            except LinklyApiError as e:
                errors_per_link[link_id] = f"{e.status_code}: {e.message}"
                if debug:
                    debug_info["steps"].append(f"Error fetching clicks for link {link_id}: [{e.status_code}] {e.message}")
                continue
            except Exception as e:
                errors_per_link[link_id] = str(e)
                if debug:
                    debug_info["steps"].append(f"Error fetching clicks for link {link_id}: {str(e)}")
                continue
        
        debug_info["clicks_per_link"] = clicks_per_link
        debug_info["errors_per_link"] = errors_per_link if errors_per_link else None
        debug_info["total_clicks_before_filter"] = len(all_clicks)
        
        # Filter by campaign if needed (double-check)
        if campaign_id and all_clicks:
            filtered = []
            for click in all_clicks:
                dest = click.get("destination", "") or click.get("url", "")
                if campaign_id in dest:
                    filtered.append(click)
            
            if debug:
                debug_info["steps"].append(f"Filtered from {len(all_clicks)} to {len(filtered)} clicks")
            
            all_clicks = filtered
        
        debug_info["total_clicks_after_filter"] = len(all_clicks)
        
        # If all requests failed, return error
        if errors_per_link and not all_clicks and len(errors_per_link) == len(link_ids):
            return {
                "status": "authentication_error",
                "message": "Failed to fetch clicks for all links - authentication issue",
                "errors": errors_per_link,
                "debug_info": debug_info if debug else None,
                "suggestion": "Check if your API key is valid and has permission to access click data. The API key should be automatically added to requests by LinklyApiClient."
            }
        
        # Step 3: Return if no clicks found
        if not all_clicks:
            return {
                "status": "no_clicks",
                "message": "No clicks recorded yet for these links",
                "campaign_id": campaign_id,
                "date_range": f"{start_date} to {end_date}",
                "link_ids_checked": link_ids,
                "total_links": len(link_ids),
                "total_clicks": 0,
                "clicks_per_link": clicks_per_link,
                "debug_info": debug_info if debug else None,
                "suggestion": "Links exist but haven't been clicked yet. Share the links to start tracking clicks."
            }
        
        # Step 4: Analyze clicks
        clicks_by_contact = {}
        clicks_by_date = {}
        clicks_by_country = {}
        clicks_by_device = {}
        clicks_by_browser = {}
        unique_ips = set()
        
        for click in all_clicks:
            if not isinstance(click, dict):
                continue
            
            # Extract email from destination URL
            dest_url = click.get("destination", "") or click.get("url", "")
            email = None
            
            if "email=" in dest_url:
                try:
                    parsed = urlparse(dest_url)
                    params = parse_qs(parsed.query)
                    email = params.get("email", [None])[0]
                    if email:
                        email = email.strip()
                except:
                    pass
            
            # Track by contact email
            if email:
                if email not in clicks_by_contact:
                    clicks_by_contact[email] = {
                        "total_clicks": 0,
                        "first_clicked_at": None,
                        "last_clicked_at": None,
                        "country": click.get("country", "Unknown"),
                        "device": click.get("device", "Unknown"),
                        "browser": click.get("browser", "Unknown"),
                        "city": click.get("city", "Unknown")
                    }
                
                clicks_by_contact[email]["total_clicks"] += 1
                
                timestamp = click.get("timestamp") or click.get("created_at") or click.get("clickedAt")
                if timestamp:
                    if not clicks_by_contact[email]["first_clicked_at"]:
                        clicks_by_contact[email]["first_clicked_at"] = timestamp
                    clicks_by_contact[email]["last_clicked_at"] = timestamp
            
            # Track by date
            timestamp = click.get("timestamp") or click.get("created_at") or ""
            if timestamp:
                date = str(timestamp).split("T")[0]
                clicks_by_date[date] = clicks_by_date.get(date, 0) + 1
            
            # Track by country
            country_code = click.get("country", "Unknown")
            clicks_by_country[country_code] = clicks_by_country.get(country_code, 0) + 1
            
            # Track by device
            device = click.get("device", "Unknown")
            clicks_by_device[device] = clicks_by_device.get(device, 0) + 1
            
            # Track by browser
            browser = click.get("browser", "Unknown")
            clicks_by_browser[browser] = clicks_by_browser.get(browser, 0) + 1
            
            # Track unique IPs
            ip = click.get("ip") or click.get("ipAddress")
            if ip:
                unique_ips.add(ip)
        
        # Calculate engagement rate
        engagement_rate = (len(clicks_by_contact) / len(link_ids) * 100) if link_ids else 0
        
        # Step 5: Build summary response
        result = {
            "status": "success",
            "campaign_id": campaign_id,
            "date_range": {
                "start": start_date,
                "end": end_date
            },
            "summary": {
                "total_clicks": len(all_clicks),
                "unique_visitors": len(unique_ips),
                "contacts_who_clicked": len(clicks_by_contact),
                "links_tracked": len(link_ids),
                "engagement_rate": f"{engagement_rate:.1f}%"
            },
            "clicks_per_link": clicks_per_link,
            "analytics": {
                "by_contact": clicks_by_contact,
                "by_date": dict(sorted(clicks_by_date.items())),
                "by_country": clicks_by_country,
                "by_device": clicks_by_device,
                "by_browser": clicks_by_browser
            },
            "debug_info": debug_info if debug else None
        }
        
        # Add top performers if we have data
        if clicks_by_contact:
            result["top_performers"] = {
                "most_engaged": max(clicks_by_contact.items(), key=lambda x: x[1]["total_clicks"])[0],
                "most_engaged_clicks": max(c["total_clicks"] for c in clicks_by_contact.values())
            }
        
        if clicks_by_date:
            result["top_performers"] = result.get("top_performers", {})
            result["top_performers"]["most_active_day"] = max(clicks_by_date.items(), key=lambda x: x[1])[0]
        
        return result
        
    except LinklyApiError as e:
        return {
            "status": "error",
            "error_type": "LinklyApiError",
            "message": e.message,
            "status_code": e.status_code
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        await client.close()