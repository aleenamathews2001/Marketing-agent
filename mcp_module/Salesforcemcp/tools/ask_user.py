from typing import Any, Dict

async def ask_user(message: str) -> Dict[str, Any]:
    """
    Ask the user a question or request missing information.
    This tool should be used when the agent needs more input to proceed.
    
    Args:
        message: The question or message to display to the user.
        
    Returns:
        A JSON response structure indicating the request for user input.
    """
    return {
        "type": "ask_user",
        "message": message,
        # The Orchestrator or UI should interpret this type 
        # to stop execution and wait for user input.
        "uiType": "UserRequest" 
    }
