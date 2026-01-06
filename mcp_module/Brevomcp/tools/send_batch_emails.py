from __future__ import annotations
from typing import List, Dict, Any, Optional
from client.brevo_client import BrevoApiClient
from Error.brevo_error import BrevoApiError
import json
import traceback

 
 
async def send_batch_emails(
    template_id: int,
    recipients: List[Dict[str, Any]],
    sender_email: str="aleenamathews2001@gmail.com",
    sender_name: Optional[str] = "Aleena Mathews",
    subject: Optional[str] = None,
    message_versions: Optional[List[Dict[str, Any]]] = None,
    cc: Optional[List[Dict[str, Any]]] = None,
    bcc: Optional[List[Dict[str, Any]]] = None,
    tags: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None
) -> str:
     
    """
    **PRIMARY TOOL FOR SENDING ACTUAL EMAILS VIA BREVO.**
    **Use this tool when the user wants to SEND emails, not just preview them.**
    
    Send personalized batch emails via Brevo to multiple recipients using templates.
    Supports per-recipient personalization, CC/BCC, and both identical and personalized content.
    
    PARAMETERS:
    - template_id: Brevo template ID to use
    - recipients: List of recipient objects with email, name, and optional params
        * Use ONLY when sending IDENTICAL content to all recipients
        * DO NOT use this for personalized emails where each recipient gets different content
    - message_versions: List of message objects, one per recipient with personalized content
        * REQUIRED for personalized emails where each recipient gets different content
        * Create ONE object per recipient with their actual data (no placeholders)
        * Each object should have 'to' (list with one recipient) and 'params' (personalization data)
    
    Returns a JSON string with success status, message ID, and send statistics.
    
    NOTE: For previewing/testing email content WITHOUT sending, use the preview_email tool instead.
    """

     

    
    # Default empty lists for optional arguments
    if cc is None:
        cc = []
    if bcc is None:
        bcc = []
    if tags is None:
        tags = []
    if headers is None:
        headers = {}
    # if shared_params is None:
    #     shared_params = {}

    # Basic validation
    if not sender_email:
        raise ValueError("Missing required field: sender_email")
    
    if not recipients and not message_versions:
        raise ValueError("Must provide either recipients or message_versions")

    client = BrevoApiClient()

    try:
        # CASE 1: Template with individual params (use messageVersions)
        if template_id and (any("params" in r for r in recipients) or 
                           any("params" in r for r in cc) or 
                           any("params" in r for r in bcc)):
            
            message_versions_list = []
            
            # Add 'to' recipients with their individual params
            for r in recipients:
                version = {
                    "to": [{"email": r["email"], "name": r.get("name", "")}]
                }
                if "params" in r:
                    version["params"] = r["params"]
                message_versions_list.append(version)
            
            # Add 'cc' recipients with their individual params
            for r in cc:
                version = {
                    "to": [{"email": r["email"], "name": r.get("name", "")}]
                }
                if "params" in r:
                    version["params"] = r["params"]
                message_versions_list.append(version)
            
            # Add 'bcc' recipients with their individual params
            for r in bcc:
                version = {
                    "to": [{"email": r["email"], "name": r.get("name", "")}]
                }
                if "params" in r:
                    version["params"] = r["params"]
                message_versions_list.append(version)
            
            payload = {
                "sender": {
                    "email": sender_email,
                    "name": sender_name or ""
                },
                "templateId": template_id,
                "messageVersions": message_versions_list
            }
            
            if tags:
                payload["tags"] = tags
            if headers:
                payload["headers"] = headers
        
        # CASE 2: Template with shared params (traditional CC/BCC)
        elif template_id:
            payload = {
                "sender": {
                    "email": sender_email,
                    "name": sender_name or ""
                },
                "to": recipients,
                "templateId": template_id
            }
            
            if cc:
                payload["cc"] = cc
            if bcc:
                payload["bcc"] = bcc
            # Removed shared_params - not needed for per-recipient params
            if tags:
                payload["tags"] = tags
            if headers:
                payload["headers"] = headers
        
        # CASE 3: No valid configuration
        else:
            raise ValueError("Invalid configuration: template_id is required")
        
        # CASE 3: HTML/Text content with messageVersions
        # elif message_versions:
        #     message_versions_list = []
            
        #     for mv in message_versions:
        #         version = {
        #             "to": mv.get("to", [])
        #         }
        #         if "params" in mv:
        #             version["params"] = mv["params"]
        #         if "subject" in mv:
        #             version["subject"] = mv["subject"]
        #         if "htmlContent" in mv:
        #             version["htmlContent"] = mv["htmlContent"]
        #         if "textContent" in mv:
        #             version["textContent"] = mv["textContent"]
        #         message_versions_list.append(version)
            
        #     payload = {
        #         "sender": {
        #             "email": sender_email,
        #             "name": sender_name or ""
        #         },
        #         "messageVersions": message_versions_list
        #     }
            
        #     # Add defaults for versions that don't specify them
        #     if subject:
        #         payload["subject"] = subject
        #     if html_content:
        #         payload["htmlContent"] = html_content
        #     if text_content:
        #         payload["textContent"] = text_content
        #     if tags:
        #         payload["tags"] = tags
        #     if headers:
        #         payload["headers"] = headers
        
        # CASE 4: Simple HTML/Text email with CC/BCC
        # else:
        #     if not subject:
        #         return json.dumps({
        #             "status": "error",
        #             "message": "Subject is required for HTML/text emails"
        #         }, indent=2)
            
        #     if not html_content and not text_content:
        #         return json.dumps({
        #             "status": "error",
        #             "message": "Either html_content or text_content is required"
        #         }, indent=2)
            
        #     payload = {
        #         "sender": {
        #             "email": sender_email,
        #             "name": sender_name or ""
        #         },
        #         "to": recipients,
        #         "subject": subject
        #     }
            
        #     if cc:
        #         payload["cc"] = cc
        #     if bcc:
        #         payload["bcc"] = bcc
        #     if html_content:
        #         payload["htmlContent"] = html_content
        #     if text_content:
        #         payload["textContent"] = text_content
        #     if tags:
        #         payload["tags"] = tags
        #     if headers:
        #         payload["headers"] = headers

        # Make the API request
        response = await client.request("/smtp/email", method="POST", data=payload)

        # Determine mode based on what was sent
        if template_id and message_versions:
            mode = "template_with_personalization"
        elif template_id:
            mode = "template_with_cc_bcc"
        elif message_versions:
            mode = "messageVersions_with_html"
        else:
            mode = "simple_email"

        result = {
            "status": "success",
            "mode": mode,
            "messageId": response.get("messageId"),
            "template_id": template_id,
            "recipients_sent": len(recipients) if recipients else len(message_versions) if message_versions else 0,
            "cc_sent": len(cc),
            "bcc_sent": len(bcc),
            "tags": tags
        }

        return json.dumps(result, indent=2)

    except BrevoApiError as e:
       # Re-raise Brevo API errors with full context
        raise BrevoApiError(
            status_code=e.status_code,
            message=f"Brevo API error: {e.message}",
            details=e.details
        )
    except Exception as e:
        # Re-raise other exceptions with traceback
        raise RuntimeError(f"Email sending failed: {str(e)}\n{traceback.format_exc()}")
    finally:
        await client.close()
