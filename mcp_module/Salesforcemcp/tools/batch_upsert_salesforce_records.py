from typing import List, Dict, Any, Optional
from Error.sf_error import SalesforceApiError
from client.sf_client import SalesforceClient
import logging
import json

# Lazy initialization
_sf_client = None

def get_client():
    global _sf_client
    if not _sf_client:
        _sf_client = SalesforceClient("marketing")
        _sf_client.connect()
    return _sf_client

async def batch_upsert_salesforce_records(
    object_name: str,
    records: List[Dict[str, Any]]
) -> str:
    """
    Batch create or update multiple Salesforce records in a single operation.
    
    This tool is optimized for bulk operations and should be used when you need to
    create or update multiple records of the same object type.
    
    Args:
        object_name: The Salesforce object API name (e.g., "CampaignMember", "Contact")
        records: List of record dictionaries, each containing:
            - record_id: (Optional) If provided, updates that record; if empty/None, creates new record
            - fields: Dictionary of field names and values to set
            
    Returns:
        JSON string with:
        - success: Overall operation success
        - total_records: Total number of records processed
        - successful: Number of successful operations
        - failed: Number of failed operations
        - results: List of individual results with operation type and record_id
        - errors: List of any errors encountered
    
    Example:
        records = [
            {"record_id": "003xxx", "fields": {"Status": "Sent"}},
            {"record_id": "", "fields": {"FirstName": "John", "LastName": "Doe"}}
        ]
    """
    
    client = get_client()
    sf = client.sf
    
    if not sf:
        return json.dumps({
            "success": False,
            "error": "Salesforce connection not established"
        }, indent=2)
    
    if not object_name:
        return json.dumps({
            "success": False,
            "error": "object_name must be a non-empty string"
        }, indent=2)
    
    if not records or not isinstance(records, list):
        return json.dumps({
            "success": False,
            "error": "records must be a non-empty list"
        }, indent=2)
    
    results = []
    errors = []
    successful_count = 0
    failed_count = 0
    
    try:
        sobject_api = getattr(sf, object_name)
        
        for idx, record in enumerate(records):
            try:
                # Extract record_id and fields from the record
                record_id = record.get("record_id", "")
                fields = record.get("fields", {})
                
                if not fields or not isinstance(fields, dict):
                    errors.append({
                        "index": idx,
                        "error": "fields must be a non-empty dictionary",
                        "record": record
                    })
                    failed_count += 1
                    continue
                
                # -------- UPDATE --------
                if record_id and str(record_id).strip() != "":
                    sobject_api.update(record_id, fields)
                    results.append({
                        "index": idx,
                        "success": True,
                        "operation": "update",
                        "record_id": record_id
                    })
                    successful_count += 1
                
                # -------- CREATE --------
                else:
                    create_result = sobject_api.create(fields)
                    new_id = create_result.get("id")
                    results.append({
                        "index": idx,
                        "success": True,
                        "operation": "create",
                        "record_id": new_id
                    })
                    successful_count += 1
                    
            except Exception as e:
                logging.exception(f"Failed to process record at index {idx}")
                errors.append({
                    "index": idx,
                    "error": str(e),
                    "record": record
                })
                failed_count += 1
        
        return json.dumps({
            "success": failed_count == 0,
            "total_records": len(records),
            "successful": successful_count,
            "failed": failed_count,
            "results": results,
            "errors": errors if errors else None
        }, indent=2)
        
    except Exception as e:
        logging.exception("Batch upsert failed")
        return json.dumps({
            "success": False,
            "error": f"Failed to access Salesforce object '{object_name}': {str(e)}"
        }, indent=2)
