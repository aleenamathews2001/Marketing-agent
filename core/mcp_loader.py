# core/mcp_loader.py
from typing import Dict, List, Any
import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Global cache for preloaded tools
_PRELOADED_TOOLS: Dict[str, List[Dict[str, Any]]] = {}

def build_mcp_server_params(config: Dict[str, Any]) -> StdioServerParameters:
    """Helper to build server params from config."""
    return StdioServerParameters(
        command=config["command"],
        args=config["args"],
        env=config.get("env")
    )

async def preload_mcp_tools(service_configs: Dict[str, Dict[str, Any]]):
    """
    Pre-load all MCP tools at application startup.
    Call this once when the FastAPI server starts.
    """
    logging.info("🚀 Pre-loading MCP tools...")
    
    for service_name, config in service_configs.items():
        try:
            logging.info(f"⏳ Fetching tools for {service_name}...")
            server_params = build_mcp_server_params(config)
            
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    
                    tools_meta = []
                    for tool in tools_response.tools:
                        tools_meta.append({
                            "name": tool.name,
                            "description": getattr(tool, "description", ""),
                            "schema": getattr(tool, "inputSchema", {}),
                        })
                    
                    _PRELOADED_TOOLS[service_name] = tools_meta
                    logging.info(f"✅ Preloaded {len(tools_meta)} tools for {service_name}")
                    
        except Exception as e:
            logging.error(f"❌ Failed to preload tools for {service_name}: {e}")
    
    logging.info(f"🎉 Preloaded tools for {len(_PRELOADED_TOOLS)} services: {list(_PRELOADED_TOOLS.keys())}")

def get_preloaded_tools(service_name: str) -> List[Dict[str, Any]]:
    """Get preloaded tools for a service."""
    return _PRELOADED_TOOLS.get(service_name, [])
