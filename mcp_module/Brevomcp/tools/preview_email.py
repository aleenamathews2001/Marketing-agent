 
from typing import List, Dict, Any, Optional
from client.brevo_client import BrevoApiClient
from Error.brevo_error import BrevoApiError
 
async def preview_email(
    template_id: int,
    recipients: Optional[List[Dict[str, Any]]] = None,
    cc: Optional[List[Dict[str, Any]]] = None,
    bcc: Optional[List[Dict[str, Any]]] = None,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    **USE THIS TOOL ONLY WHEN USER EXPLICITLY ASKS TO PREVIEW/TEST/VERIFY EMAIL CONTENT.**
    **DO NOT USE THIS FOR ACTUAL EMAIL SENDING - USE send_batch_emails INSTEAD.**
    
    Generate local previews of a Brevo email template for all specified recipients (TO, CC, and BCC)
    without actually sending the email.

    This method fetches the specified Brevo template, applies any dynamic parameters defined for
    each recipient, and renders a personalized version of the email body.
 
    Notes:
        - No actual emails are sent; this function is for preview/testing ONLY
        - For ACTUAL email sending, you MUST use the `send_batch_emails` tool
        - Only use this when user says "preview", "test", "check", or "verify" email content
    """
    # Default empty lists
    recipients = recipients or []
    cc = cc or []
    bcc = bcc or []
    
    # Merge all recipients (to + cc + bcc)
    all_contacts = recipients + cc + bcc

    if not template_id or not all_contacts:
        return {"status": "error", "error": "Missing required fields: template_id and recipients/cc/bcc"}

    client = BrevoApiClient()
    try:
        # Fetch the template
        template_data = await client.request(f"/smtp/templates/{template_id}", method="GET")

        html_content = template_data.get("htmlContent", "")
        subject = template_data.get("subject", "")
        sender = template_data.get("sender", {})

        previews = []

        for contact in all_contacts:
            email = contact.get("email")
            name = contact.get("name", "")
            params = contact.get("params", {})

            # Copy content for this contact
            rendered_html = html_content
            rendered_subject = subject

            # Replace both {{key}} and {{params.key}} variants
            for key, value in params.items():
                rendered_html = rendered_html.replace(f"{{{{{key}}}}}", str(value))
                rendered_html = rendered_html.replace(f"{{{{ params.{key} }}}}", str(value))
                rendered_html = rendered_html.replace(f"{{{{params.{key}}}}}", str(value))

                rendered_subject = rendered_subject.replace(f"{{{{{key}}}}}", str(value))
                rendered_subject = rendered_subject.replace(f"{{{{ params.{key} }}}}", str(value))
                rendered_subject = rendered_subject.replace(f"{{{{params.{key}}}}}", str(value))

            previews.append({
                "recipient": {"email": email, "name": name},
                "sender": {
                    "email": sender_email or sender.get("email", ""),
                    "name": sender_name or sender.get("name", "")
                },
                "subject": rendered_subject,
                "original_subject": subject,
                "html_content": rendered_html,
                "original_html": html_content,
                "params_used": params
            })

        return {
            "status": "success",
            "template_id": template_id,
            "template_name": template_data.get("name", ""),
            "total_recipients": len(previews),
            "previews": previews
        }

    except BrevoApiError as e:
        return {
            "status": "error",
            "error": f"[{e.status_code}] {e.message}",
            "details": e.details
        }

    finally:
        await client.close()