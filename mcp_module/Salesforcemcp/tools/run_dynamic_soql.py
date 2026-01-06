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

def run_dynamic_soql(query: str) -> dict:
    """
    Use this tool when you need to fetch Salesforce data . Returns a dict with 'records' (list of results) and
    'total' (number of records), or an error description if the query fails.
    """
    # Validate query
    if not query or not isinstance(query, str):
        return {"error": "Invalid query parameter - must be a non-empty string"}

    if not query.strip().upper().startswith("SELECT"):
        return {"error": "Invalid SOQL query - must start with SELECT"}

    # Check Salesforce connection
    client = get_client()
    if client.sf is None:
        return {"error": "Salesforce connection not established"}

    try:
        result = client.sf.query_all(query)

        return {
            "records": result.get("records", []),
            "total": result.get("totalSize", 0)
        }

    except SalesforceApiError as e:
        logging.exception("SOQL execution failed")
        return {"status": "error", "error": str(e)}
