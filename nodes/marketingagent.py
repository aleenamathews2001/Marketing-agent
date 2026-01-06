from baseagent import  get_member_dependency
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import logging
from baseagent import fetch_prompt_metadata,resolve_placeholders,call_llm
from core.state import MarketingState


async def orchestrator_node(state: MarketingState) -> MarketingState:
    logging.info("🎯 Orchestrator analyzing workflow...")
     
    # Iteration guard
    state["iteration_count"] = state.get("iteration_count", 0) + 1
    if state["iteration_count"] >= state.get("max_iterations", 10):
        logging.warning("Max iterations reached, completing workflow")
        state["next_action"] = "complete"
        state["error"] = "Maximum iterations reached"
        return state

    # These can be overridden in state later using PromptConfig LLM params
    parent_member = state.get("parent_member", "Marketing Agent")

     
    registry = get_member_dependency(parent_member=parent_member)
     
    # Pre-format "Available Agents" string for the prompt
    services_info = "\n".join(
        f"- {name}: {meta.get('description', 'No description')}"
        for name, meta in registry.items()
    )

    internal_actions = list(registry.keys()) 
    # internal_actions = [s for s in sf_services]
    valid_actions = internal_actions + ["complete"]
    allowed_str = ", ".join(valid_actions)

    progress_summary = _build_progress_summary(state)

    # 2) Store all dynamic values in state so PromptConfig can read them
    state["services_info"] = services_info
    state["progress_summary"] = progress_summary
    state["valid_actions"] = valid_actions
    state["allowed_str"] = allowed_str
    # 3) Load prompt metadata from Salesforce
    system_prompt_meta = fetch_prompt_metadata("Marketing Agent Prompt")
  
    logging.debug(f"system_prompt_meta {system_prompt_meta}...")

    # 4) Resolve placeholders using ONLY state
    resolved_prompt = resolve_placeholders(
        prompt=system_prompt_meta["prompt"],
        configs=system_prompt_meta["configs"],
        state=state  
    )
    
    # ⚠️ ORCHESTRATOR REVIEW PROTOCOL INJECTION
    resolved_prompt += """
    
    ⚠️ REVIEW PROTOCOL:
    If the last action was 'Salesforce MCP' finding contacts (using run_dynamic_soql) for a campaign, and the campaign has NOT been created yet:
    - OR if the Execution Summary contains 'propose_action':
    - The system is in "Review Mode".
    - Do NOT route to Salesforce MCP again immediately.
    - RESPOND WITH 'complete'.
    - This allows the Completion Node to ask the user for confirmation.
    
    ⚠️ AGENT HANDOFF RULES:
    1. EMAIL SENDING:
       - If User Goal is "Send Email" (or similar):
       - AND Salesforce MCP has successfully fetched contacts (seen in progress summary):
       - THEN you MUST route to 'Brevo MCP' next.
       - Do NOT choose 'complete' until the emails are actually sent by Brevo.
    2. POST-EMAIL UPDATE (CRITICAL):
       - If 'Brevo MCP' has JUST successfully sent emails (seen in progress summary): **IMPORTANT**
       - AND the Campaign Members have not yet been updated to 'Sent': **IMPORTANT**
       - THEN you MUST route back to 'Salesforce MCP'. ***IMPORTANT***
       - REASON: To update the 'Status' of the CampaignMember records to 'Sent'.***IMPORTANT***
       - Do NOT choose 'complete' until this update is done.***IMPORTANT***
    """

    # 2. POST-EMAIL UPDATE (CRITICAL):
    #    - If 'Brevo MCP' has JUST successfully sent emails (seen in progress summary):
    #    - CHECK if CampaignMember status update has ALREADY been completed:
    #      * Look for 'upsert_salesforce_record'or 'batch_upsert_salesforce_records' operations on 'CampaignMember' with 'Status: Sent' in the progress summary
    #      * If found: The update is DONE. Route to 'complete'.
    #      * If NOT found: The update is PENDING. Route to 'Salesforce MCP'.
    #    - REASON: To update the 'Status' of the CampaignMember records to 'Sent' (only if not already done).
    #    - Do NOT route to Salesforce MCP twice for the same update operation.
    #     model_name = system_prompt_meta.get("model") or "gpt-4.1"
    #     llm = ChatOpenAI(model=model_name, temperature=0)
    #     # 5) User prompt (you probably want dynamic allowed_str here)
    user_prompt = f"""User Goal: {state['user_goal']}

Progress So Far:
{progress_summary}

Based on the User Goal and Progress Summary above:
- If the goal is ALREADY realized by the completed operations, respond with 'complete'.
- If there is NEW work to be done, choose the next agent (Salesforce MCP, Brevo MCP, Linkly MCP).
- Do NOT repeat successful operations.

What should we do next? Respond with ONLY one of Salesforce MCP, Brevo MCP, Linkly MCP, or complete"""
#     messages = [
#         SystemMessage(content=resolved_prompt),
#         HumanMessage(content=user_prompt),
#     ]
    try:
        raw_next_agent = await call_llm(
            system_prompt=resolved_prompt,
            user_prompt=user_prompt,   # provider + model from SF
            default_model= system_prompt_meta["model"],
            default_provider=system_prompt_meta["provider"],
            default_temperature=0.0,
        )
         
        # raw_next_agent = response.content.strip()
        normalized = raw_next_agent.strip()

        logging.info(f"Next agent (raw): {raw_next_agent}")
        logging.info(f"Next agent (normalized): {normalized}")

        if normalized not in valid_actions:
            logging.warning(f"Invalid routing decision: {raw_next_agent}, defaulting to complete")
            normalized = "complete"

        state["next_action"] = normalized          # e.g. "Salesforce MCP"
        state["current_agent"] = "orchestrator"

        state.setdefault("messages", [])
        state["messages"].append(
            AIMessage(content=f"Orchestrator decision: Route to {normalized}")
        )

        logging.info(f"✅ Routing decision: {normalized}")

    except Exception as e:
        logging.error(f"Orchestrator error: {e}")
        state["error"] = f"Orchestrator failed: {str(e)}"
        state["next_action"] = "complete"

    return state



def _build_progress_summary(state: MarketingState) -> str:
    """
    Build a DETAILED, DYNAMIC summary of all MCP executions.
    Iterates over state['mcp_results'] to handle any registered service.
    """
    mcp_results = state.get("mcp_results", {})
    if not mcp_results:
        return "ℹ️ No MCPs have been called yet."

    summary_parts = []
    
    # Sort to keep consistent order if needed, or just iterate
    for service_name, data in mcp_results.items():
        if not data:
            continue
            
        exec_summary = data.get("execution_summary", {})
        tool_results = data.get("tool_results", [])
        
        if exec_summary:
            total_calls = exec_summary.get("total_calls", 0)
            successful = exec_summary.get("successful_calls", 0)
            failed = exec_summary.get("failed_calls", 0)
            
            # Extract SPECIFIC operations details
            operations_detail = []
            # Show up to 10 relevant operations
            for result in tool_results[-10:]: 
                tool_name = result.get("tool_name", "unknown")
                status = result.get("status", "unknown")
                
                # Check for response content first (User Request: "from tool result get the summary")
                response_obj = result.get("response")
                tool_output_text = ""
                
                # Try to extract text from MCP response object
                if response_obj and hasattr(response_obj, 'content'):
                    try:
                        texts = []
                        for item in response_obj.content:
                            if hasattr(item, 'text'):
                                texts.append(item.text)
                        if texts:
                            tool_output_text = " | ".join(texts)
                            # Truncate if too long to avoid cluttering context
                            if len(tool_output_text) > 200:
                                tool_output_text = tool_output_text[:197] + "..."
                    except Exception:
                        pass
                
                if tool_output_text:
                     op_desc = f"{tool_name} -> {tool_output_text}"
                else:
                    # Fallback: Generic dumping of request arguments without hardcoding
                    request = result.get("request", {})
                    
                    # Flatten request details for summary
                    details = []
                    for k, v in request.items():
                        if isinstance(v, dict):
                            # For nested dicts like "fields", just show the values
                            flat_v = ", ".join(f"{sub_k}={sub_v}" for sub_k, sub_v in v.items())
                            details.append(f"{k}: {{{flat_v}}}")
                        else:
                            details.append(f"{k}={v}")
                    
                    args_str = ", ".join(details)
                    op_desc = f"{tool_name} ({args_str})"

                operations_detail.append(f"{op_desc} ({status})")
            
            ops_str = "\n  - ".join(operations_detail) if operations_detail else "No specific operations"
            
            summary_parts.append(
                f"✅ {service_name.upper()} COMPLETED:\n"
                f"  Stats: {total_calls} calls ({successful} success, {failed} failed)\n"
                f"  Operations:\n  - {ops_str}"
            )
        else:
            summary_parts.append(f"⚠️ {service_name}: Called but no detailed summary available")

    if not summary_parts:
        return "ℹ️ No operations recorded yet."
    logging.info(f"Summary parts: {summary_parts}")
    return "\n\n".join(summary_parts)
