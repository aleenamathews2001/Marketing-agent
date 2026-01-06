from typing import List, Dict, Any, Optional
from Error.sf_error import SalesforceApiError
from client.sf_client import SalesforceClient
import logging


# Lazy initialization
_sf_client = None

def get_client():
    global _sf_client
    if not _sf_client:
        _sf_client = SalesforceClient("marketing")
        _sf_client.connect()
    return _sf_client
def delete_salesforce_record(object_name: str, record_id: str) -> dict:
    """Deletes a Salesforce record for the specified object using its record ID."""
    if not object_name or not isinstance(object_name, str):
        return {"error": "Invalid object_name parameter - must be a non-empty string"}
    
    if not record_id or not isinstance(record_id, str):
        return {"error": "Invalid record_id parameter - must be a non-empty string"}
    client = get_client()
    sf = client.sf
    try:
        # Check if sf connection exists
        if not sf:
         return {"error": "Salesforce connection not established"}
        
        # Validate record ID format
        if not (len(record_id) == 15 or len(record_id) == 18):
            return {"error": "Invalid Salesforce record ID format"}
        
        # Delete the record
        sf.__getattr__(object_name).delete(record_id)
        return {"success": True}
        
    except AttributeError as e:
        logging.error(f"Salesforce object error: {e}")
        return {"error": f"Invalid object name or connection issue: {object_name}"}
    except Exception as e:
        logging.error(f"Record deletion error: {e}")
        return {"error": f"Failed to delete record: {str(e)}"}
