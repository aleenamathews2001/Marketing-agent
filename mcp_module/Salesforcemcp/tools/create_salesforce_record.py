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

 

def create_salesforce_record(object_name: str, fields: dict) -> dict:
    """Creates a new record in Salesforce for the specified object with the given fields"""
    if not object_name or not isinstance(object_name, str):
        return {"error": "Invalid object_name parameter - must be a non-empty string"}
    
    if not fields or not isinstance(fields, dict):
        return {"error": "Invalid fields parameter - must be a non-empty dictionary"}
    
    try:
        # Check if sf connection exists
        client = get_client()
        if not client.sf:
            return {"error": "Salesforce connection not established"}
        
        # Get the Salesforce object dynamically
        sf_object = getattr(client.sf, object_name)
        
        # Create the record
        result = sf_object.create(fields)
        
        if not result or not result.get("id"):
            return {"error": "Record creation failed - no ID returned"}
        
        return {"success": True, "id": result.get("id")}
        
    except AttributeError as e:
        logging.error(f"Salesforce object error: {e}")
        return {"error": f"Invalid object name '{object_name}': {str(e)}"}
    except Exception as e:
        logging.error(f"Record creation error: {e}")
        return {"error": f"Failed to create record: {str(e)}"}