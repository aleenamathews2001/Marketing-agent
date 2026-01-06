from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from Error.brevo_error import BrevoApiError

from client.brevo_client import BrevoApiClient
from tools import send_batch_emails
from tools import send_batch_emails, preview_email 
mcp = FastMCP("brevo-mcp1")

mcp.tool()(send_batch_emails)
mcp.tool()(preview_email)
# mcp.tool()(track_email_engagement)
 
def main():
    # Initialize and run the server
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()