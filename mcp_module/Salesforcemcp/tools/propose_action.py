import json
from typing import Dict, Any, Optional

async def propose_action(
    object_name: str,
    fields: Dict[str, Any],
    action_type: str = "create",
    reason: str = "Proposed action for user review"
) -> Dict[str, Any]:
    """
    Proposes an action (like creating a record) without executing it.
    Used for 'Dry Run' or 'Review' phases.
    
    Args:
        object_name: The Salesforce object (e.g., 'Campaign')
        fields: The fields that WOULD be used (e.g., {'Name': 'My Campaign'})
        action_type: 'create', 'update', or 'delete'
        reason: Why this action is being proposed
        
    Returns:
        Structured dictionary containing the proposal details.
    """
    return {
        "status": "proposed",
        "proposal": {
            "object_name": object_name,
            "fields": fields,
            "action_type": action_type,
            "reason": reason
        },
        "message": f"Proposed {action_type} for {object_name}: {json.dumps(fields)}"
    }
