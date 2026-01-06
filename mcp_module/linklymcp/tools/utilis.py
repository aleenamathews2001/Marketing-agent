import re
import logging
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

def extract_urls_from_template(template_content: str) -> list[str]:
    """
    Extract all URLs from a Brevo email template (HTML or text).
    
    Finds URLs in:
    - HTML href attributes: <a href="...">
    - Plain text URLs: https://... or http://...
    - Brevo template variables: {{ params.URL }}
    
    Args:
        template_content: HTML or text content of email template
    
    Returns:
        List of unique URLs found in the template
    """
    urls = set()
    
    # Pattern 1: Extract from HTML href attributes
    href_pattern = r'href=["\'](https?://[^\s"\'<>]+)["\']'
    urls.update(re.findall(href_pattern, template_content, re.IGNORECASE))
    
    # Pattern 2: Extract plain text URLs
    url_pattern = r'https?://[^\s<>"\')]+[^\s<>"\'.,;:!?)\]]'
    urls.update(re.findall(url_pattern, template_content, re.IGNORECASE))
    
    # Pattern 3: Remove common tracking/unsubscribe/image URLs
    filtered_urls = [
        url for url in urls 
        if not any(exclude in url.lower() for exclude in [
            'unsubscribe', 'pixel', 'track', 'beacon', 
            '.png', '.jpg', '.gif', '.jpeg', '.svg',
            'sendinblue.com/track', 'brevo.com/track'
        ])
    ]
    
    return list(filtered_urls)

def format_url_with_tracking(base_url: str, campaign_id: str, contact_email: str) -> str:
    """
    Format URL with campaign ID and email as query parameters.
    
    Example output:
    https://example.com/page?campaign=CAMP-2025&email=user@example.com
    
    Args:
        base_url: Original URL
        campaign_id: Campaign identifier
        contact_email: Contact email
    
    Returns:
        Formatted URL with tracking parameters
    """
    # Parse the URL
    parsed = urlparse(base_url)
    
    # Get existing query parameters
    query_params = parse_qs(parsed.query)
    
    # Add tracking parameters (flatten any lists from parse_qs)
    query_params = {k: v[0] if isinstance(v, list) else v for k, v in query_params.items()}
    query_params['campaign'] = campaign_id
    # query_params['email'] = contact_email
    
    # Rebuild URL with new query string
    new_query = urlencode(query_params)
    new_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))
    
    return new_url
