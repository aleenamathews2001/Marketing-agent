from core.state import MarketingState
 
from baseagent import  get_member_dependency,call_mcp
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
import logging, sys, os, json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from core.state import MarketingState
 
import logging

# async def dynamic_caller(state: MarketingState) -> MarketingState:
#     service_name = state.get("next_action")
#     if not service_name or service_name == "complete":
#         # nothing to do
#         return state

#     logging.info(f"🛰 [MCP Caller] Invoking {service_name}")

#     parent_member = state.get("parent_member", "Marketing Agent")
#     entity_type = state.get("entity_type", "MCP")
#     dependency_type = state.get("dependency_type", "Agent→MCP")

#     registry =  get_member_dependency(
#         parent_member=parent_member 
#     )
#     config = registry.get(service_name)
#     if not config:
#         msg = f"Service {service_name} not found in registry"
#         logging.warning(msg)
#         state["error"] = msg
#         # also stop here so we don't spin
#         state["next_action"] = "complete"
#         return state

#     # 🔹 Record that this MCP was called
#     called = state.setdefault("called_services", [])
#     if service_name not in called:
#         called.append(service_name)

#     # 🔹 Simulate the MCP's effect for now (no real call yet)
#     lower = service_name.lower()
#     if "salesforce" in lower:
#         state["salesforce_data"] = {"status": "simulated-success"}
#     if "brevo" in lower:
#         state["brevo_results"] = {"status": "simulated-success"}
#     if "linkly" in lower:
#         state["linkly_links"] = {"status": "simulated-success"}

#     results = state.setdefault("mcp_results", {})
#     results[service_name] = {
#         "status": "simulated",
#         "details": f"Simulated MCP call for {service_name}",
#     }

#     state["current_agent"] = service_name
#     # ❗ Do NOT force next_action = "complete" here; we want the orchestrator
#     # to decide the next MCP (Brevo) based on the updated state.
#     return state

async def dynamic_caller(state: MarketingState) -> MarketingState:
    service_name = state.get("next_action")
    if not service_name or service_name == "complete":
        # nothing to do
        return state

    logging.info(f"🛰 [MCP Caller] Invoking {service_name}")

    parent_member = state.get("parent_member", "Marketing Agent")

    # Your existing registry lookup
    registry = get_member_dependency(
        parent_member=parent_member
        # you can also use entity_type / dependency_type if your helper supports it
    )
    config = registry.get(service_name)
    if not config:
        msg = f"Service {service_name} not found in registry"
        logging.warning(msg)
        state["error"] = msg
        # Stop here so we don't spin forever
        state["next_action"] = "complete"
        return state

    # 🔹 Track which MCPs were called
    called = state.setdefault("called_services", [])
    if service_name not in called:
        called.append(service_name)

    # 🔹 Actually call the MCP and let the LLM pick tools & args
    try:
        mcp_result = await call_mcp(service_name, config, state)
    except Exception as e:
        logging.exception(f"❌ Error calling MCP {service_name}: {e}")
        state["error"] = f"Error calling MCP {service_name}: {e}"
        # let orchestrator decide what to do next, don't override next_action here
        return state

    # 🔹 Store results in a common place
    results = state.setdefault("mcp_results", {})
    results[service_name] = mcp_result

    # ✅ FIX: Persist shared result sets (e.g. "Campaign") for future agents to use
    if "result_sets" in mcp_result:
        shared = state.setdefault("shared_result_sets", {})
        # Merge new result sets into shared state
        for key, val in mcp_result["result_sets"].items():
            if key != "previous_result": # Don't persist ephemeral 'previous_result'
                 shared[key] = val
        logging.info(f"💾 [DynamicCaller] Updated shared_result_sets with keys: {list(mcp_result['result_sets'].keys())}")

    # Optionally also set service-specific keys for convenience
    lower = service_name.lower()
    if "salesforce" in lower:
        state["salesforce_data"] = mcp_result
        
        # ✅ Clear task directive after CampaignMember status update
        if state.get("task_directive") == "Update CampaignMember status to 'Sent' for successfully sent emails":
            # Check if the update was actually performed
            tool_results = mcp_result.get("tool_results", [])
            
            # Look for upsert_salesforce_record or batch_upsert operations on CampaignMember
            for result in tool_results:
                tool_name = result.get("tool_name", "")
                if "upsert" in tool_name.lower() and result.get("status") == "success":
                    # Check if it was updating CampaignMember
                    request = result.get("request", {})
                    if request.get("object_type") == "CampaignMember" or request.get("sobject_type") == "CampaignMember":
                        logging.info("✅ [Salesforce MCP] CampaignMember status updated, clearing task directive")
                        state["task_directive"] = None
                        state["pending_updates"] = None
                        break
        
        # # ✅ Extract contacts from previous_results for Brevo to access
        # salesforce_data = {
        #     **mcp_result,
        #     "contacts": mcp_result.get("previous_results", [])  # ✅ Use fresh result
        # }
        # state["salesforce_data"] = salesforce_data
        # logging.info(f"[{service_name}] salesforce_data next_action...,{salesforce_data}")
        # logging.info(f"📦 Stored {len(salesforce_data.get('contacts', []))} contacts in salesforce_data")
    elif "brevo" in lower:
        state["brevo_results"] = mcp_result
        
        # ✅ Set task directive to update CampaignMember status after email sending
        tool_results = mcp_result.get("tool_results", [])
        
        # Find send_batch_emails results
        for result in tool_results:
            if result.get("tool_name") == "send_batch_emails" and result.get("status") == "success":
                # Parse the response to get recipient results
                response_obj = result.get("response")
                if response_obj and hasattr(response_obj, 'content'):
                    try:
                        for item in response_obj.content:
                            if hasattr(item, 'text'):
                                email_result = json.loads(item.text)
                                
                                # Extract successful contact IDs
                                recipient_results = email_result.get("recipient_results", [])
                                successful_contacts = [
                                    r["contact_id"] for r in recipient_results 
                                    if r.get("status") == "sent" and r.get("contact_id")
                                ]
                                
                                if successful_contacts:
                                    logging.info(f"📧 [Brevo MCP] {len(successful_contacts)} emails sent successfully")
                                    logging.info(f"📋 [Brevo MCP] Setting task directive to update CampaignMember status")
                                    
                                    state["task_directive"] = "Update CampaignMember status to 'Sent' for successfully sent emails"
                                    state["pending_updates"] = {
                                        "object": "CampaignMember",
                                        "operation": "update_status_to_sent",
                                        "successful_contacts": successful_contacts,
                                        "reason": f"{len(successful_contacts)} emails sent successfully via Brevo"
                                    }
                                break
                    except (json.JSONDecodeError, AttributeError) as e:
                        logging.warning(f"Could not parse Brevo email results: {e}")
                        
    elif "linkly" in lower:
        state["linkly_links"] = mcp_result

    # The orchestrator node will decide next_action from here.
    state["current_agent"] = service_name
    return state