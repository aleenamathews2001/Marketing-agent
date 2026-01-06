from typing import List, Optional
from Client.Linkly_client import LinklyApiClient
from Error.linkly_error import LinklyApiError


async def delete_links(
    campaign_id: Optional[str] = None,
    link_ids: Optional[List[int]] = None,
    confirm: bool = False,
    use_bulk: bool = True,
    debug: bool = False
) -> dict:
    """
    Delete multiple Linkly short links by campaign_id or link_ids.
    Use this tool when cleaning up old or unused links
    ⚠️ WARNING: This action is IRREVERSIBLE! Deleted links cannot be recovered.
    Returns:
        dict with deletion results or error
    """
    client = LinklyApiClient()
    
    try:
        # Safety check
        if not confirm:
            preview_info = {
                "status": "confirmation_required",
                "message": "⚠️ Deletion requires confirmation. Set confirm=True to proceed.",
                "warning": "This action is IRREVERSIBLE. Deleted links cannot be recovered.",
                "next_steps": "Review the links to be deleted, then call again with confirm=True"
            }
            
            # If campaign_id provided, show what would be deleted
            if campaign_id:
                try:
                    links_endpoint = f"/api/v1/workspace/{client.workspace_id}/links"
                    links_response = await client.request(links_endpoint, method="GET")
                    
                    links_data = []
                    if isinstance(links_response, list):
                        links_data = links_response
                    elif isinstance(links_response, dict):
                        links_data = (
                            links_response.get("links") or 
                            links_response.get("data") or 
                            links_response.get("results") or 
                            []
                        )
                    
                    matching_links = []
                    for link in links_data:
                        all_urls = f"{link.get('destination', '')} {link.get('formatted_url', '')} {link.get('url', '')}"
                        patterns = [
                            f"campaign={campaign_id}",
                            f"campaign_id={campaign_id}",
                            f"campaignId={campaign_id}",
                            campaign_id
                        ]
                        
                        if any(pattern in all_urls for pattern in patterns):
                            matching_links.append({
                                "link_id": link.get("id"),
                                "short_url": link.get("full_url", ""),
                                "destination": link.get("destination", "")[:100]
                            })
                    
                    preview_info["preview"] = {
                        "campaign_id": campaign_id,
                        "links_to_delete": len(matching_links),
                        "sample_links": matching_links[:5]  # Show first 5
                    }
                except:
                    pass
            
            elif link_ids:
                preview_info["preview"] = {
                    "link_ids_to_delete": link_ids,
                    "total_links": len(link_ids)
                }
            
            preview_info["example_with_confirm"] = {
                "campaign_id": campaign_id or "CAMP-2025-AUTUMN",
                "confirm": True
            } if campaign_id else {
                "link_ids": link_ids or [123, 456],
                "confirm": True
            }
            
            return preview_info
        
        if not campaign_id and not link_ids:
            return {
                "status": "missing_parameters",
                "message": "Please provide either campaign_id or link_ids",
                "examples": {
                    "by_campaign": {
                        "campaign_id": "CAMP-2025-AUTUMN",
                        "confirm": True
                    },
                    "by_link_ids": {
                        "link_ids": [123, 456],
                        "confirm": True
                    }
                }
            }
        
        debug_info = {
            "steps": [],
            "links_found": [],
            "bulk_attempted": False,
            "bulk_succeeded": False
        }
        
        # Step 1: Get link IDs if campaign_id provided
        if campaign_id and not link_ids:
            try:
                links_endpoint = f"/api/v1/workspace/{client.workspace_id}/links"
                debug_info["steps"].append(f"Fetching links from: {links_endpoint}")
                
                links_response = await client.request(links_endpoint, method="GET")
                
                link_ids = []
                links_data = []
                
                # Handle different response formats
                if isinstance(links_response, list):
                    links_data = links_response
                elif isinstance(links_response, dict):
                    links_data = (
                        links_response.get("links") or 
                        links_response.get("data") or 
                        links_response.get("results") or 
                        []
                    )
                
                debug_info["steps"].append(f"Total links retrieved: {len(links_data)}")
                
                # Find links matching the campaign
                for link in links_data:
                    link_destination = link.get("destination", "")
                    link_formatted = link.get("formatted_url", "")
                    link_url = link.get("url", "")
                    link_id = link.get("id") or link.get("link_id")
                    link_short_url = link.get("full_url") or link.get("short_url", "")
                    
                    # Combine all possible URL fields
                    all_urls = f"{link_destination} {link_formatted} {link_url}"
                    
                    # Check multiple patterns for campaign matching
                    patterns = [
                        f"campaign={campaign_id}",
                        f"campaign_id={campaign_id}",
                        f"campaignId={campaign_id}",
                        campaign_id
                    ]
                    
                    if any(pattern in all_urls for pattern in patterns):
                        if link_id:
                            link_ids.append(int(link_id))
                            debug_info["links_found"].append({
                                "link_id": link_id,
                                "short_url": link_short_url,
                                "destination": link_destination[:100]
                            })
                
                debug_info["total_links_checked"] = len(links_data)
                debug_info["matching_links_found"] = len(link_ids)
                
                if not link_ids:
                    return {
                        "status": "no_links_found",
                        "message": f"No links found for campaign '{campaign_id}'",
                        "campaign_id": campaign_id,
                        "total_links_checked": len(links_data),
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
                "status": "error",
                "message": "No link IDs to delete"
            }
        
        # Convert all link_ids to integers
        link_ids = [int(lid) for lid in link_ids]
        
        debug_info["link_ids_to_delete"] = link_ids
        debug_info["total_links_to_delete"] = len(link_ids)
        
        deletion_results = {
            "successful": [],
            "failed": []
        }
        
        # Step 2: Try BULK DELETE first (if use_bulk=True)
        if use_bulk:
            debug_info["bulk_attempted"] = True
            debug_info["steps"].append(f"Attempting bulk delete for {len(link_ids)} links")
            
            endpoint = f"/api/v1/workspace/{client.workspace_id}/links"
            
            # Try different bulk payload formats
            payloads_to_try = [
                {"link_ids": [str(lid) for lid in link_ids]},  # String IDs
                {"link_ids": link_ids},  # Integer IDs
                {"ids": [str(lid) for lid in link_ids]},
                {"ids": link_ids},
                {"links": [str(lid) for lid in link_ids]},
                {"links": link_ids}
            ]
            
            bulk_success = False
            
            for i, payload in enumerate(payloads_to_try):
                try:
                    if debug:
                        debug_info["steps"].append(f"Bulk attempt {i+1}: {list(payload.keys())}")
                    
                    result = await client.request(endpoint, method="DELETE", data=payload)
                    
                    # Bulk delete succeeded!
                    debug_info["bulk_succeeded"] = True
                    debug_info["bulk_payload_used"] = payload
                    debug_info["steps"].append(f"✓ Bulk delete successful with payload: {list(payload.keys())}")
                    
                    # Mark all as successfully deleted
                    for link_id in link_ids:
                        deletion_results["successful"].append({
                            "link_id": link_id,
                            "status": "deleted",
                            "method": "bulk"
                        })
                    
                    bulk_success = True
                    break
                    
                except LinklyApiError as e:
                    if debug:
                        debug_info["steps"].append(f"Bulk attempt {i+1} failed: [{e.status_code}] {e.message}")
                    continue
                    
                except Exception as e:
                    if debug:
                        debug_info["steps"].append(f"Bulk attempt {i+1} failed: {str(e)}")
                    continue
            
            if not bulk_success:
                debug_info["steps"].append("All bulk attempts failed, falling back to individual deletion")
        else:
            debug_info["steps"].append("Bulk deletion skipped (use_bulk=False)")
        
        # Step 3: Individual deletion (if bulk failed or not attempted)
        if not deletion_results["successful"]:
            debug_info["steps"].append(f"Deleting {len(link_ids)} links individually")
            
            for link_id in link_ids:
                endpoint = f"/api/v1/workspace/{client.workspace_id}/links"
                
                # Try individual deletion with different payload formats
                payloads_to_try = [
                    {"link_ids": [str(link_id)]},
                    {"link_ids": [link_id]},
                    {"ids": [str(link_id)]},
                    {"ids": [link_id]}
                ]
                
                success = False
                last_error = None
                
                for payload in payloads_to_try:
                    try:
                        result = await client.request(endpoint, method="DELETE", data=payload)
                        
                        deletion_results["successful"].append({
                            "link_id": link_id,
                            "status": "deleted",
                            "method": "individual",
                            "response": result
                        })
                        
                        if debug:
                            debug_info["steps"].append(f"✓ Link {link_id} deleted successfully")
                        
                        success = True
                        break
                        
                    except LinklyApiError as e:
                        last_error = e
                        continue
                        
                    except Exception as e:
                        last_error = e
                        continue
                
                # If all attempts failed for this link
                if not success:
                    error_msg = f"[{last_error.status_code}] {last_error.message}" if isinstance(last_error, LinklyApiError) else str(last_error)
                    
                    deletion_results["failed"].append({
                        "link_id": link_id,
                        "error": error_msg,
                        "details": last_error.details if isinstance(last_error, LinklyApiError) else None
                    })
                    
                    if debug:
                        debug_info["steps"].append(f"✗ Failed to delete link {link_id}: {error_msg}")
        
        # Step 4: Build summary response
        total_deleted = len(deletion_results["successful"])
        total_failed = len(deletion_results["failed"])
        
        response = {
            "status": "success" if total_failed == 0 else "partial_success" if total_deleted > 0 else "failed",
            "campaign_id": campaign_id,
            "summary": {
                "total_links": len(link_ids),
                "successfully_deleted": total_deleted,
                "failed_to_delete": total_failed,
                "success_rate": f"{(total_deleted / len(link_ids) * 100):.1f}%",
                "bulk_used": debug_info.get("bulk_succeeded", False)
            },
            "results": deletion_results,
            "debug_info": debug_info if debug else None
        }
        
        # Add message based on outcome
        if total_failed == 0:
            response["message"] = f"✓ Successfully deleted all {total_deleted} links"
        elif total_deleted > 0:
            response["message"] = f"⚠️ Deleted {total_deleted} links, but {total_failed} failed"
        else:
            response["message"] = f"✗ Failed to delete all {total_failed} links"
        
        return response
        
    except LinklyApiError as e:
        return {
            "status": "error",
            "error_type": "LinklyApiError",
            "message": e.message,
            "status_code": e.status_code,
            "details": e.details
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc() if debug else None
        }
    finally:
        await client.close()