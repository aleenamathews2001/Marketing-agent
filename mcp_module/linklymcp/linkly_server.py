from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from tools import create_short_link,generate_uniqueurl,track_link_clicks,delete_links

mcp = FastMCP("linkly-mcp")

 

mcp.tool()(create_short_link)
mcp.tool()(generate_uniqueurl)
mcp.tool()(track_link_clicks)
mcp.tool()(delete_links)
def main():
    # Initialize and run the server
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()