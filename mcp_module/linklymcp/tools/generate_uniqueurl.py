from .utilis import extract_urls_from_template, format_url_with_tracking
from .create_short_link import create_short_link
import asyncio

async def generate_uniqueurl(
    campaign_id: str,
    contacts: list[dict],
    template_url: str | list[str] | None = None,
    template_content: str | None = None,
    urls: list[str] | None = None,
    batch_size: int = 5,
    delay_between_batches: float = 0.5
) -> dict:
    """
    Generate unique, trackable Linkly URLs for all contacts in a campaign.

    Use this tool when you need one short link per contact for personalized
    engagement tracking. Supports multiple base URLs and batch processing.
    """

    
    if not contacts or not campaign_id:
        return {
            "status": "error",
            "message": "Missing campaign_id or contacts list is empty.",
        }

    # Extract URLs from Brevo template if provided
    extracted_urls = None
    if template_content:
        extracted_urls = extract_urls_from_template(template_content)
        if not extracted_urls:
            return {
                "status": "error",
                "message": "No valid URLs found in template_content",
                "template_preview": template_content[:200] + "..." if len(template_content) > 200 else template_content
            }
        # Use extracted URLs if urls parameter not provided
        if not urls and extracted_urls:
            urls = extracted_urls

    results = []
    total_links_created = 0
    
    # Helper function to create a single short link with error handling
    async def create_link_for_contact(contact_email: str, contact_name: str, url: str, url_index: int = 0):
        formatted_url = format_url_with_tracking(url, campaign_id, contact_email)
        
        try:
            result = await create_short_link(formatted_url)
            
            if "error" in result:
                return {
                    "url_index": url_index,
                    "original_url": url,
                    "formatted_url": formatted_url,
                    "short_url": None,
                    "status": "error",
                    "error": result["error"],
                }
            else:
                return {
                    "url_index": url_index,
                    "original_url": url,
                    "formatted_url": formatted_url,
                    "short_url": result.get("full_url"),
                    "link_id": result.get("id"),
                    "status": "success",
                }
        except Exception as e:
            return {
                "url_index": url_index,
                "original_url": url,
                "formatted_url": formatted_url,
                "short_url": None,
                "status": "error",
                "error": str(e),
            }
    
    # Process each contact
    for contact in contacts:
        contact_email = contact.get("email")
        contact_name = contact.get("name", "")
        
        if not contact_email:
            results.append({
                "contact": contact,
                "status": "error",
                "error": "Missing email address"
            })
            continue
        
        # Determine which URLs to use for this contact
        contact_urls = []
        
        # Priority: contact["urls"] > contact["url"] > urls > template_url
        if "urls" in contact and contact["urls"]:
            # Contact has multiple URLs
            contact_urls = contact["urls"]
        elif "url" in contact and contact["url"]:
            # Contact has single URL
            contact_urls = [contact["url"]]
        elif urls:
            # Use URLs from parameter (all contacts get these URLs)
            contact_urls = urls
        elif template_url:
            # template_url can be either a string or a list
            if isinstance(template_url, list):
                contact_urls = template_url
            else:
                contact_urls = [template_url]
        
        if not contact_urls:
            results.append({
                "contact": {"email": contact_email, "name": contact_name},
                "status": "error",
                "error": "No URLs provided for this contact"
            })
            continue
        
        # Create short links for all URLs for this contact
        contact_result = {
            "contact": {"email": contact_email, "name": contact_name},
            "links": [],
            "status": "pending"
        }
        
        # Process URLs in batches to avoid overwhelming the API
        all_tasks = []
        for idx, url in enumerate(contact_urls):
            task = create_link_for_contact(contact_email, contact_name, url, idx)
            all_tasks.append(task)
        
        # Execute in batches
        link_results = []
        for i in range(0, len(all_tasks), batch_size):
            batch = all_tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            link_results.extend(batch_results)
            
            # Add delay between batches to avoid rate limiting
            if i + batch_size < len(all_tasks):
                await asyncio.sleep(delay_between_batches)
        
        # Process results
        success_count = 0
        error_count = 0
        
        for link_result in link_results:
            if isinstance(link_result, Exception):
                contact_result["links"].append({
                    "status": "error",
                    "error": str(link_result)
                })
                error_count += 1
            else:
                contact_result["links"].append(link_result)
                if link_result["status"] == "success":
                    success_count += 1
                    total_links_created += 1
                else:
                    error_count += 1
        
        # Set overall status for this contact
        if success_count > 0 and error_count == 0:
            contact_result["status"] = "success"
        elif success_count > 0 and error_count > 0:
            contact_result["status"] = "partial_success"
        else:
            contact_result["status"] = "failed"
        
        contact_result["summary"] = {
            "total_urls": len(contact_urls),
            "successful_links": success_count,
            "failed_links": error_count
        }
        
        results.append(contact_result)

    # Build response
    response = {
        "status": "success",
        "campaign_id": campaign_id,
        "total_contacts": len(results),
        "total_links_created": total_links_created,
        "total_links_attempted": sum(len(r.get("links", [])) for r in results),
        "results": results,
    }
    
    # Include extracted URLs in response if template was provided
    if extracted_urls:
        response["extracted_urls"] = extracted_urls
    
    # Add summary statistics
    successful_contacts = sum(1 for r in results if r.get("status") == "success")
    partial_contacts = sum(1 for r in results if r.get("status") == "partial_success")
    failed_contacts = sum(1 for r in results if r.get("status") == "failed")
    
    response["summary"] = {
        "successful_contacts": successful_contacts,
        "partial_contacts": partial_contacts,
        "failed_contacts": failed_contacts,
        "success_rate": f"{(successful_contacts / len(results) * 100):.1f}%" if results else "0%"
    }
    
    return response