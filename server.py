# fastapi_websocket.py
"""
FastAPI WebSocket endpoint for real-time agent communication
"""
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from core.mcp_loader import preload_mcp_tools
from baseagent import get_member_dependency
from graph.marketing_graph import build_marketing_graph
from core.state import MarketingState

import logging

# Load environment variables
load_dotenv()

# ✅ Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("agent.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

app = FastAPI()

 


@app.on_event("startup")
async def startup_event():
    """Pre-load MCP tools on server startup"""
    try:
        logging.info("🚀 Starting Marketing Agent Server...")
        # Get registry which contains configs for all MCPs
        registry = get_member_dependency("Marketing Agent")
        
        # Filter for valid MCP configs that have executionEndpoint
        service_configs = {}
        for name, data in registry.items():
            if data.get("executionEndpoint"):
                # Adapt config format for loader
                config = {
                    "command": "python", # Default command
                    "args": data.get("executionEndpoint"),
                    "env": None
                }
                # Handle JSON string args 
                if isinstance(config["args"], str):
                    try:
                        config["args"] = json.loads(config["args"])
                    except:
                        config["args"] = [config["args"]]
                        
                service_configs[name] = config
        
        if service_configs:
            await preload_mcp_tools(service_configs)
        else:
            logging.warning("⚠️ No valid MCP configurations found to preload")
            
    except Exception as e:
        logging.error(f"❌ Error during startup tool preloading: {e}")

class MessageRequest(BaseModel):
    message: str

class MessageResponse(BaseModel):
    success: bool
    response: str
    iterations: int
    error: str | None = None  # Optional field with default None
    salesforce_data: bool = False

 
@app.websocket("/ws/chat")
async def run_agent(websocket: WebSocket):
    await websocket.accept()  # Accept connection
    
    # 🔑 Session context: persists across messages (GENERIC for ANY Salesforce object)
    session_context = {
        "created_records": {},         # Generic: {"Campaign": [{Id, Name}, ...], "Contact": [...], "Lead": [...], etc.}
        "conversation_history": []     # Store previous user goals and results
    }
    
    try:
        while True:  # Keep connection open
            # 1. RECEIVE message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            
            # 2. PROCESS the message
            agent_graph = build_marketing_graph()
            initial_state: MarketingState = {
                "user_goal": user_message,  # Use received message
                "messages": [],
                "max_iterations": 5,
                "iteration_count": 0,
                # 🔑 Inject session context into state
                "session_context": session_context.copy(),  # Pass context to the graph
            }
            final_state = await agent_graph.ainvoke(initial_state)
            
            # 🔑 UPDATE session context with newly created records
            if final_state.get("salesforce_data"):
                sf_data = final_state["salesforce_data"]
                previous_results = sf_data.get("previous_results", [])
                tool_results = sf_data.get("tool_results", [])
                
                logging.info(f"🔍 DEBUG: previous_results type: {type(previous_results)}")
                logging.info(f"🔍 DEBUG: previous_results count: {len(previous_results) if previous_results else 0}")
                if previous_results:
                    logging.info(f"🔍 DEBUG: First previous_result sample: {previous_results[0] if previous_results else 'None'}")

                # Strategy 2: Extract from tool_results (for create/upsert operations) - GENERIC
                if tool_results:
                    for tool_result in tool_results:
                        if tool_result.get("status") != "success":
                            continue
                        
                        tool_name = tool_result.get("tool_name", "")
                        request = tool_result.get("request", {})
                        
                        # Handle ANY object type creation/upsert
                        obj_type = request.get("object_name", "") or request.get("sobject", "")
                        
                        if obj_type:
                            response = tool_result.get("response", {})
                            record_id = None
                            # Get Name field, or use object type if Name doesn't exist
                            record_name = request.get("fields", {}).get("Name") or f"{obj_type} Record"
                            
                            # Parse response to get ID
                            if hasattr(response, 'content'):
                                for item in response.content:
                                    if hasattr(item, 'text'):
                                        try:
                                            parsed = json.loads(item.text)
                                            record_id = parsed.get("id") or parsed.get("Id")
                                        except:
                                            pass
                            # Also check if response is already a dict (direct tool result)
                            elif isinstance(response, dict):
                                record_id = response.get("id") or response.get("Id")
                            
                            if record_id:
                                if obj_type not in session_context["created_records"]:
                                    session_context["created_records"][obj_type] = []
                                
                                record_info = {
                                    "Id": record_id,
                                    "Name": record_name
                                }
                                # Avoid duplicates
                                if not any(r["Id"] == record_id for r in session_context["created_records"][obj_type]):
                                    session_context["created_records"][obj_type].append(record_info)
                                    logging.info(f"📌 Stored {obj_type} from {tool_name}: {record_info}")
        
                # Store conversation history
                session_context["conversation_history"].append({
                    "user_goal": user_message,
                    "result_summary": final_state.get("final_response", "")
                })
            
            # 3. SEND response back to client
            # 🔴 Filter out junction objects (objects without Name field) for UI display
            filtered_records = {}
            for obj_type, records in session_context["created_records"].items():
                # Only include records that have an actual Name (not auto-generated)
                main_records = [r for r in records if r.get("Name") and not r["Name"].endswith(" Record")]
                if main_records:
                    filtered_records[obj_type] = main_records
            
            final_resp = final_state.get("final_response", "Task completed")
            
            # 🚀 CHECK FOR CONTROL MESSAGES (Review Proposal)
            # If the response is our special JSON, send it RAW so LWC sees type='review_proposal'
            sent_special = False
            if isinstance(final_resp, str) and '"type": "review_proposal"' in final_resp:
                try:
                    control_msg = json.loads(final_resp)
                    # Preserve context if needed, but usually proposal has everything
                    await websocket.send_json(control_msg)
                    sent_special = True
                except Exception as e:
                    logging.error(f"Failed to parse control message: {e}")

            if not sent_special:
                await websocket.send_json({
                    "type": "response",
                    "success": True,
                    "response": final_resp,
                    "iterations": final_state.get("iteration_count", 0),
                    "salesforce_data": bool(final_state.get("salesforce_data")),
                    "created_records": filtered_records,  # Send filtered version to UI
                    "error": final_state.get("error")
                })
            
    except WebSocketDisconnect:
        logging.info("Client disconnected")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })

if __name__ == "__main__":
    import uvicorn
    import os
    
    # 📝 Print log location for debugging
    log_path = os.path.abspath("agent.log")
    print(f"📝 Logging initialized. File: {log_path}")

    # 🚀 ROBUST LOGGING: Disable Uvicorn's config and attach our handlers manually
    # This prevents Uvicorn from resetting logging settings
    log_config = uvicorn.config.LOGGING_CONFIG
    
    # Run with log_config=None to prevent override
    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=None)

    # Note: Handlers are already attached by logging.basicConfig(force=True) above.
    # Uvicorn loggers (uvicorn, uvicorn.access) will inherit from root logger 
    # if propagation is on (default).
    
    # Explicitly ensure uvicorn loggers use our handlers if needed:
    req_logger = logging.getLogger("uvicorn.access")
    req_logger.handlers = logging.getLogger().handlers 
    err_logger = logging.getLogger("uvicorn.error")
    err_logger.handlers = logging.getLogger().handlers
