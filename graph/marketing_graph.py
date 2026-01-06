from core.state import MarketingState
from langgraph.graph import StateGraph, END
from nodes.marketingagent import orchestrator_node
from nodes.dynamic_caller import dynamic_caller
from nodes.completion import completion_node
import logging


async def salesforce_entry_node(state: MarketingState) -> MarketingState:
    logging.info("📡 [Salesforce] Selected by orchestrator (placeholder).")
    state["salesforce_data"] = state.get("salesforce_data", "placeholder-salesforce-call")
    state["current_agent"] = "salesforce"
    return state


async def brevo_entry_node(state: MarketingState) -> MarketingState:
    logging.info("📧 [Brevo] Selected by orchestrator (placeholder).")
    state["brevo_results"] = state.get("brevo_results", "placeholder-brevo-call")
    state["current_agent"] = "brevo"
    return state


async def linkly_entry_node(state: MarketingState) -> MarketingState:
    logging.info("🔗 [Linkly] Selected by orchestrator (placeholder).")
    state["linkly_links"] = state.get("linkly_links", "placeholder-linkly-call")
    state["current_agent"] = "linkly"
    return state


# def route_decision(state: MarketingState) -> str:
#     """
#     Used by add_conditional_edges.
#     Must return one of: 'salesforce mcp', 'brevo mcp', 'linkly mcp', 'complete'.
#     """
#     return state.get("next_action", "complete")

def route_decision(state: MarketingState) -> str:
    """
    Router for the 'orchestrator' node.

    - If the orchestrator decided we're done (next_action == 'complete'),
      go to 'completion'.
    - Otherwise, always go to 'dynamic_caller' which will look at
      state["next_action"] and invoke the right MCP.
    """
    next_action = state.get("next_action", "complete")
    if next_action == "complete":
        return "complete"
    return "dynamic_caller"

def build_marketing_graph():
    builder = StateGraph(MarketingState)

    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("dynamic_caller", dynamic_caller)
    # builder.add_node("salesforce mcp", salesforce_entry_node)
    # builder.add_node("brevo mcp", brevo_entry_node)
    # builder.add_node("linkly mcp", linkly_entry_node)
    builder.add_node("completion", completion_node)

    builder.set_entry_point("orchestrator")

    builder.add_conditional_edges(
        "orchestrator",
        route_decision,
        {
            # "salesforce mcp": "salesforce mcp",
            "dynamic_caller":"dynamic_caller",
            # "brevo mcp": "brevo mcp",
            # "linkly mcp": "linkly mcp",
            "complete": "completion",
        },
    )

    # builder.add_edge("salesforce mcp", "orchestrator")
    builder.add_edge("dynamic_caller", "orchestrator")
    # builder.add_edge("linkly mcp", "orchestrator")

    builder.add_edge("completion", END)

    return builder.compile()
