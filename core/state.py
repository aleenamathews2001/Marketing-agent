# core/state.py
from typing import TypedDict, List, Dict, Any, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import operator


def merge_dicts(left: Optional[Dict], right: Optional[Dict]) -> Optional[Dict]:
    """
    Reducer that merges dicts, preserving left if right is None/empty.
    This ensures salesforce_data persists across state updates.
    """
     
    if right is None or (isinstance(right, dict) and len(right) == 0):
        return left
    if left is None:
        return right
    # Merge: right takes precedence for overlapping keys
    result = {**left, **right}
    return result



def merge_history(left: Optional[List[Dict]], right: Optional[List[Dict]]) -> Optional[List[Dict]]:
    """
    Reducer that appends new history items to the existing list.
    """
    if left is None:
        return right
    if right is None:
        return left
    return left + right

class MarketingState(TypedDict):
    user_goal: str
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Orchestrator routing
    iteration_count: int
    max_iterations: int
    next_action: str  # "salesforce" | "brevo" | "linkly" | "complete"
    current_agent: str
    
    # Data coming back from sub-agents - use merge_dicts to preserve across updates
    salesforce_data: Annotated[Optional[Dict[str, Any]], merge_dicts]
    brevo_results: Annotated[Optional[Dict[str, Any]], merge_dicts]
    linkly_links: Annotated[Optional[Dict[str, Any]], merge_dicts]
    
    # Generic MCP results storage for dynamic handling
    mcp_results: Annotated[Optional[Dict[str, Any]], merge_dicts]
    
    # Persistent Session History
    session_history: Annotated[Optional[List[Dict[str, Any]]], merge_history]
    
    # 🔑 Session Context: Stores created records across multiple requests in same WebSocket session
    session_context: Annotated[Optional[Dict[str, Any]], merge_dicts]
      
    # ✅ SHARED RESULT SETS: Data persistence across agents (e.g. campaign data for Brevo)
    shared_result_sets: Annotated[Optional[Dict[str, Any]], merge_dicts]
 

    # Final result + errors
    error: Optional[str]
    final_response: Optional[str]


