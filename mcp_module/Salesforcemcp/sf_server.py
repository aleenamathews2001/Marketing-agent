from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from Error.sf_error import SalesforceApiError
 

from tools import (
    run_dynamic_soql,
    create_salesforce_record,
    upsert_salesforce_record,
    delete_salesforce_record,
    generate_all_toolinput,
    ask_user,
    propose_action,
    batch_upsert_salesforce_records
)

# Initialize MCP
mcp = FastMCP("salesforce-mcp")
mcp.tool()(run_dynamic_soql)
mcp.tool()(create_salesforce_record)
mcp.tool()(upsert_salesforce_record)
mcp.tool()(delete_salesforce_record)
mcp.tool()(generate_all_toolinput)
mcp.tool()(ask_user)
mcp.tool()(propose_action)
mcp.tool()(batch_upsert_salesforce_records)

 


 

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
