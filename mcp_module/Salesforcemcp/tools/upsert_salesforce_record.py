from typing import List, Dict, Any, Optional
from Error.sf_error import SalesforceApiError
from client.sf_client import SalesforceClient
from .run_dynamic_soql import run_dynamic_soql
import logging


# Lazy initialization
_sf_client = None

def get_client():
    global _sf_client
    if not _sf_client:
        _sf_client = SalesforceClient("marketing")
        _sf_client.connect()
    return _sf_client

def upsert_salesforce_record(object_name: str, record_id: str, fields: dict) -> dict:
    """
    Create or update a Salesforce record  

    If record_id is provided, this updates that record. If record_id is empty
    or None, this creates a new record with the given fields. Returns a dict
    with success flag, operation type ("create" or "update"), and record_id,
    or an error message on failure.
    """

    client = get_client()
    sf = client.sf

    if not sf:
        return {"error": "Salesforce connection not established"}

    if not object_name:
        return {"error": "object_name must be a non-empty string"}

    if not fields or not isinstance(fields, dict):
        return {"error": "fields must be a non-empty dictionary"}

    try:
        sobject_api = getattr(sf, object_name)

        # -------- UPDATE --------
        if record_id and str(record_id).strip() != "":
            sobject_api.update(record_id, fields)

            return {
                "success": True,
                "operation": "update",
                "record_id": record_id
            }

        # -------- CREATE --------
        create_result = sobject_api.create(fields)

        return {
            "success": True,
            "operation": "create",
            "record_id": create_result.get("id")
        }

    except Exception as e:
        logging.exception("Upsert failed")
        return {"error": f"Failed to upsert record: {str(e)}"}
