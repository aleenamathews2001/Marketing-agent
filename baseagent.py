import json
from functools import lru_cache
from typing import Dict, List, Any ,Optional
from dataclasses import dataclass
import os
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
import asyncio
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from mcp_module.Salesforcemcp.client.sf_client import SalesforceClient
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from core.state import MarketingState
import sys
import re
_sf_connected=False
# logging.basicConfig removed to allow server.py to configure logging
logger = logging.getLogger(__name__)
# Choose the org that hosts these MemberDefinition records
SF_ORG_TYPE = "agent"  # or "marketing", depending on your setup

sf_client = SalesforceClient(SF_ORG_TYPE)

@dataclass
class PromptConfig:
    """Represents a single prompt configuration item"""
    name: str
    config_type: str
    placeholder_name: Optional[str] = None
    data_type: Optional[str] = None
    is_required: bool = False
    default_value: Optional[str] = None
    description: Optional[str] = None
    tool_name: Optional[str] = None
    source_type: Optional[str] = None
    state_path: Optional[str] = None  # New: path in state like "user_goal" or "results.salesforce"

def _load_planning_config(input_schema: Dict[str, Any], mcp_name: str) -> Dict[str, Any]:
    """
    Extract planning configuration from InputSchema__c.
    Falls back to defaults if _planning section missing.
    """
    planning = input_schema.get("_planning", {})
    
    return {
        "strategy": planning.get("strategy", "llm_planner"),
        "tool_name": planning.get("tool_name"),
        "required_context": planning.get("required_context", []),
        "prompt_template": planning.get("prompt_template"), # Name of Salesforce PromptTemplate
    }

def ensure_sf_connected():
    """Ensure Salesforce is connected (call this at runtime, not import time)"""
    global _sf_connected
    if not _sf_connected:
        _sf_connected = sf_client.connect()
    return _sf_connected
@lru_cache
def _load_agent_member_dependency_cached(
    parent_member: str 
) -> Dict[str, Any]:
    """
    Internal cached loader.
    Cache key is (parent_member, entity_type, dependency_type).
    """
    if not sf_client.connect():
        raise RuntimeError(f"[{SF_ORG_TYPE}] Salesforce connection failed for MCP registry")

    sf = sf_client.sf

    md_query = f"""
        SELECT Id, Name, EntityType__c, Description__c, Intent__c, Status__c,
               InputSchema__c, OutputSchema__c,ExecutionEndpoint__c
        FROM MemberDefinition__c
        WHERE Status__c = 'Active'
          
    """
    md_result = sf.query(md_query)
    md_records = md_result.get("records", [])

    # 2) Get dependencies for the given parent_member and dependency_type
    dep_query = f"""
        SELECT Id,
               ParentMember__c,
               DependantMember__r.Name,
               DependencyType__c,
               CallOrder__c
        FROM MemberDependency__c
        WHERE ParentMember__c = '{parent_member}'
           

    
    """
    dep_result = sf.query(dep_query)
    dep_records = dep_result.get("records", [])

    # Build a map: memberName -> list of dependency info
    deps_by_member_name: Dict[str, List[Dict[str, Any]]] = {}
    for dep in dep_records:
        name = dep["DependantMember__r"]["Name"]
        deps_by_member_name.setdefault(name, []).append(
            {
                "id": dep["Id"],
                "parent_member": dep.get("ParentMember__c"),
                "parent_entity": dep.get("ParentEntity__c"),
                "dependency_type": dep.get("DependencyType__c"),
                "call_order": dep.get("CallOrder__c"),
            }
        )

    # Build final registry (only entries that actually exist as MemberDefinition__c)
    registry: Dict[str, Any] = {}

    for rec in md_records:
        name = rec["Name"]  # e.g. "Linkly MCP"
        input_schema = rec.get("InputSchema__c") or "{}"
        output_schema = rec.get("OutputSchema__c") or "{}"

        try:
            input_schema_json = json.loads(input_schema)
        except Exception:
            input_schema_json = {}

        try:
            output_schema_json = json.loads(output_schema)
        except Exception:
            output_schema_json = {}

        # ✅ Extract planning configuration
        planning_config = _load_planning_config(input_schema_json, name)

        registry[name] = {
            "name": name,
            "entity_type": rec.get("EntityType__c"),
            "description": rec.get("Description__c"),
            "executionEndpoint": rec.get("ExecutionEndpoint__c"),
            "intent": rec.get("Intent__c"),
            "status": rec.get("Status__c"),
            "input_schema": input_schema_json,
            "output_schema": output_schema_json,
            "dependencies": deps_by_member_name.get(name, []),
            
            # ✅ Planning configuration from InputSchema__c
            "planning_strategy": planning_config["strategy"],
            "planning_tool_name": planning_config["tool_name"],
            "planning_prompt_template": planning_config["prompt_template"],
            "required_context": planning_config["required_context"],
        }

    return registry


def load_agent_member_dependency(
    parent_member: str   
) -> Dict[str, Any]:
    """
    Public wrapper around the cached loader.

    - parent_member: which Agent is the parent? (e.g. "Marketing Agent")
    - entity_type:  which MemberDefinition__c.EntityType__c to load? (e.g. "MCP")
    - dependency_type: which relationship type? (e.g. "Agent→MCP")

    This will be cached per unique (parent_member, entity_type, dependency_type) tuple.
    """
    
    return _load_agent_member_dependency_cached(parent_member)


def get_member_dependency(
    parent_member: str = "Marketing Agent" 
) -> Dict[str, Any]:
    """
    Return the full registry dict for the given parent_member / entity_type / dependency_type.
    """
    return load_agent_member_dependency(parent_member)


def refresh_member_dependency(
    parent_member: str = "Marketing Agent" 
) -> Dict[str, Any]:
    """
    Clear cache for this combination and re-load from Salesforce.
    Useful if MemberDefinition__c or MemberDependency__c are updated at runtime.
    """
    _load_agent_member_dependency_cached.cache_clear()
    # After clearing, re-call with the desired combination
    return _load_agent_member_dependency_cached(parent_member )

def fetch_prompt_metadata(template_name: str) -> Optional[Dict[str, str]]:
    try:
        if not ensure_sf_connected():
            logger.error("Salesforce not connected.")
            return None

        # Get PromptTemplate Id
        template_query = f"""
        SELECT Id FROM PromptTemplate__c 
        WHERE Name = '{template_name}' AND Status__c = 'Active' LIMIT 1
        """
        template_result = sf_client.sf.query(template_query)
        if not template_result['records']:
            logger.warning(f"No active PromptTemplate found for {template_name}")
            return None

        template_id = template_result['records'][0]['Id']

        # Get latest active version with model details
        version_query = f"""
        SELECT Id,TemplateText__c,LlmModel__c,LLMProvider__c FROM PromptTemplateVersion__c 
        WHERE PromptTemplate__c = '{template_id}' 
        AND Status__c = 'Active' 
        ORDER BY VersionNumber__c DESC 
        LIMIT 1
        """
        version_result = sf_client.sf.query(version_query)
        if not version_result['records']:
            logger.warning(f"No active version found for template {template_name}")
            return None

        record = version_result['records'][0]
        
        version_id = record['Id']
        
        # Get all configs for this version
        config_query = f"""
        SELECT 
            Name,
            ConfigType__c,
            PlaceholderName__c,
            DataType__c,
            IsRequired__c,
            DefaultValue__c,
            Description__c,
            ToolName__c,
            SourceType__c
        FROM PromptConfig__c
        WHERE PromptTemplateVersion__c = '{version_id}'
        ORDER BY Name
        """
        config_result =  sf_client.sf.query(config_query)
        
        # Parse configs
        configs = [
            PromptConfig(
                name=rec['Name'],
                config_type=rec['ConfigType__c'],
                placeholder_name=rec.get('PlaceholderName__c'),
                data_type=rec.get('DataType__c'),
                is_required=rec.get('IsRequired__c', False),
                default_value=rec.get('DefaultValue__c'),
                description=rec.get('Description__c'),
                tool_name=rec.get('ToolName__c'),
                source_type=rec.get('SourceType__c')
            )
            for rec in config_result['records']
        ]
        return {
            
            "prompt": record["TemplateText__c"],
            "model": record["LlmModel__c"],
            "provider": record["LLMProvider__c"],
            "configs":configs
        }

    except Exception as e:
        logger.error(f"Error fetching prompt metadata: {e}")
        return None


def resolve_placeholders(
    prompt: str,
    configs: List[PromptConfig],
    state: Dict[str, Any] 
) -> str:
    """
    Resolve all placeholders in the template text
    
    Args:
        prompt: Template with placeholders like {placeholder_name}
        configs: List of PromptConfig objects
        state: Current state dict (e.g., MarketingState)
        context: Additional context data
        
    Returns:
        Resolved template text
    """
    resolved_text = prompt
    
    
    # Build placeholder map
    placeholder_map = {}
    for config in configs:
        if config.config_type in ['Template Placeholder', 'Condition']:
            placeholder_name = config.placeholder_name or config.name
            value = _resolve_single_placeholder(config, state)
            placeholder_map[placeholder_name] = value
    
    # Replace placeholders
    for placeholder, value in placeholder_map.items():
        pattern = r'\{' + re.escape(placeholder) + r'\}'
        resolved_text = re.sub(pattern, str(value), resolved_text)
    
    # Check for unresolved required placeholders
    remaining_placeholders = re.findall(r'\{(\w+)\}', resolved_text)
    if remaining_placeholders:
        logger.warning(f"Unresolved placeholders: {remaining_placeholders}")
    
    return resolved_text

def _resolve_single_placeholder(
    config: PromptConfig,
    state: Dict[str, Any]
) -> Any:
    """
    Resolve a single placeholder based on its source type
    
    Args:
        config: PromptConfig object
        state: Current state
    Returns:
        Resolved value
    """
    source_type = config.source_type or 'literal'
    
    if source_type == 'literal':
        # Direct value from config
        return config.value or config.default_value or ''
    
    elif source_type == 'Context':
        # Get from state using state_path or placeholder_name
        path = config.state_path or config.placeholder_name
        return _get_nested_value(state, path, config.default_value)
    
    # elif source_type == 'Business service':
    #     # Call a tool/function to get value
    #     if config.tool_name:
    #         return _call_business_service(config.tool_name, state, context)
    #     return config.default_value or ''
    
    else:
        logger.warning(f"Unknown source_type: {source_type}")
        return config.default_value or ''

def _get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Get nested value from dict using dot notation
    
    Example: 'results.salesforce.account_id' -> data['results']['salesforce']['account_id']
    """
    if not path:
        return default
    
    keys = path.split('.')
    value = data
    
    try:
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            
            if value is None:
                return default
        return value
    except (KeyError, TypeError, AttributeError):
        return default


def build_llm(
    default_model: str,
    default_provider: str,
    default_temperature: float,
    api_key: Optional[str] = None,
):
    """
    Build an LLM client (OpenAI, Claude, Gemini) based on provider + model
    coming from PromptTemplateVersion__c.
    """
    provider = default_provider.lower()
    model = default_model.lower()
    temperature = default_temperature


    if provider == "openai":
        return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)

    # elif provider == "anthropic":
    #     # e.g. model="claude-3-5-sonnet-20241022"
    #     return ChatAnthropic(model=model, temperature=temperature, api_key=api_key)

    # elif provider == "gemini":
    #     # e.g. model="gemini-1.5-flash"
    #     return ChatGoogleGenerativeAI(model=model, temperature=temperature, api_key=api_key)

    else:
        logger.warning(f"Unknown provider '{provider}', defaulting to OpenAI {default_model}")
        return ChatOpenAI(model=default_model, temperature=temperature, api_key=api_key)
  
# async def call_llm(
#     system_prompt: str,
#     user_prompt: str,
#     default_model: str,
#     default_provider: str,
#     default_temperature: float,
#     api_key: Optional[str] = None,
# ) -> str:
#     """
#     Send a system + user prompt pair to the selected LLM and return the text content.
#     """
#     logger.info("🔵 Starting LLM call...")
#     logger.info(f"🔵 Model: {default_model}, Provider: {default_provider}")
#     llm = build_llm(
#         default_model=default_model,
#         default_provider=default_provider,
#         default_temperature=default_temperature,
#         api_key=api_key,
#     )

#     messages = [
#         SystemMessage(content=system_prompt),
#         HumanMessage(content=user_prompt),
#     ]

#     response = await llm.ainvoke(messages)
#     logger.info("f🔵 LLM call complete,{response}")
#     return response.content

# At module level
openai_async_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def call_llm(
    system_prompt: str,
    user_prompt: str,
    default_model: str,
    default_provider: str,
    default_temperature: float,
    api_key: Optional[str] = None,
) -> str:
    """
    Send a system + user prompt pair to the selected LLM and return the text content.
    Uses direct OpenAI client instead of LangChain to avoid async issues.
    """
    logger.info("🔵 Starting LLM call...")
    logger.info(f"🔵 Model: {default_model}, Provider: {default_provider}")
    
    provider = default_provider.lower()
    
    if provider == "openai":
        try:
            logger.info("🔵 Calling OpenAI API...")
            
            # Use the working OpenAI client
            client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
            
            response = await client.chat.completions.create(
                model=default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=default_temperature
            )
            
            content = response.choices[0].message.content
            logger.info(f"🔵 LLM call complete: {content[:100]}...")
            return content
            
        except Exception as e:
            logger.error(f"❌ OpenAI call failed: {e}", exc_info=True)
            raise
    
    else:
        # Fallback to LangChain for other providers
        logger.warning(f"Provider {provider} not directly supported, using LangChain")
        
        llm = build_llm(
            default_model=default_model,
            default_provider=default_provider,
            default_temperature=default_temperature,
            api_key=api_key,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = await asyncio.wait_for(llm.ainvoke(messages), 30.0)
            logger.info(f"🔵 LLM call complete: {response}")
            return response.content
        except asyncio.TimeoutError:
            logger.error("❌ LLM call timed out")
            raise TimeoutError("LLM request timed out")

def build_mcp_server_params(config: Dict[str, Any]) -> StdioServerParameters:
    """
    Convert your MCP registry config (from Salesforce) into StdioServerParameters.
    Change the keys to match your actual metadata.
    """

    # Example 1: explicit fields
    command = config.get("command") or "python"
    args_raw = config.get("executionEndpoint") or []

    # Example 2: args stored as JSON string in Salesforce:
    # {"args": "[\"mcp_module/Salesforcemcp/sf_server.py\"]"}
    if isinstance(args_raw, str):
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            args = [args_raw]
    else:
        args = args_raw

    return StdioServerParameters(
        command=command,
        args=args,
    )
    
    plan["calls"] = valid_calls
    logging.info(f"🎯 [{service_name}] Final plan: {len(valid_calls)} calls, needs_next={plan.get('needs_next_iteration')}")
    
    return plan


async def plan_mcp_execution(
    service_name: str,
    config: Dict[str, Any],
    tools_meta: List[Dict[str, Any]],
    state: MarketingState,
    session: ClientSession,
    iteration: int,
    previous_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Unified planning function - NO manual routing for different MCPs.
    """
    logging.info(f"[{service_name}] Planning execution...,{previous_results}")
    planning_strategy = config.get("planning_strategy", "llm_planner")
    
    # ✅ Check if required context is available
    required_context = config.get("required_context", [])
    # missing_context = []
    # for context_path in required_context:
    #     if not _get_nested_value(state, context_path):
    #         missing_context.append(context_path)
    
    # if missing_context:
    #     logging.warning(f"[{service_name}] Missing required context: {missing_context}")
    #     return {
    #         "calls": [],
    #         "needs_next_iteration": False,
    #         "needs_salesforce_data": True,
    #         "missing_context": missing_context
    #     }
    
    # ✅ Strategy 1: Internal Tool (e.g., Salesforce MCP)
    if planning_strategy == "internal_tool":
        tool_name = config.get("planning_tool_name")
        if not tool_name:
            logging.error(f"[{service_name}] Internal tool strategy but no tool_name")
            return {"calls": [], "needs_next_iteration": False}
        
        # Only use internal tool on first iteration
        if iteration == 1:
            user_goal = state.get("user_goal", "")
            planning_context = {
                **state,
                "salesforcemcptool": tools_meta,
                "session_context": state.get("session_context", {})
            }
            
            gen_args = {"query": user_goal, "context": planning_context}
            logging.info(f"[{service_name}] Calling internal planner: {tool_name}")
            
            gen_result = await session.call_tool(tool_name, gen_args)
            plan_text = extract_json_response_from_tool_result(gen_result)
            logging.info(f"[{service_name}] Plan text: {plan_text}")
            
            if not plan_text:
                return {"calls": [], "needs_next_iteration": False}
            
            try:
                return json.loads(plan_text)
            except json.JSONDecodeError as e:
                logging.error(f"[{service_name}] Invalid plan JSON: {e}")
                return {"calls": [], "needs_next_iteration": False}
        else:
            # ✅ FIX: Don't fall back to LLM planner for internal_tool MCPs
            # If we have previous_results, the work is done  
            if previous_results:
                logging.info(f"[{service_name}] Internal tool completed with {len(previous_results)} results, stopping")
                return {"calls": [], "needs_next_iteration": False}
            
            # If no previous results but iteration > 1, something went wrong
            logging.warning(f"[{service_name}] Iteration {iteration} but no previous results, stopping")
            return {"calls": [], "needs_next_iteration": False}
    
    # ✅ Strategy 2: LLM Planner (e.g., Brevo, Linkly)
    if planning_strategy == "llm_planner":
        # Get MCP-specific prompt from Salesforce PromptTemplate
        mcp_specific_prompt = ""
        template_name = config.get("planning_prompt_template")
        
        if template_name:
            prompt_meta = fetch_prompt_metadata(template_name)
            if prompt_meta:
                 # Resolve placeholders if needed
                 mcp_specific_prompt = resolve_placeholders(prompt_meta["prompt"], prompt_meta["configs"], state)
            else:
                 logging.warning(f"[{service_name}] Prompt template '{template_name}' not found or empty.")
        
        tools_for_prompt = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "schema": t.get("schema", {}),
            }
            for t in tools_meta
        ]
        logging.info(f"[{service_name}] Tools for prompt: {tools_for_prompt}")
        
        system_content = f"""You are a planner for '{service_name}'.

AVAILABLE TOOLS (name, description, schema):
{json.dumps(tools_for_prompt, indent=2)}

{mcp_specific_prompt}

EXECUTION STRATEGY:
- Plan ONLY ONE STEP at a time (one logical operation)
- Use "store_as": "name" to save results for later reference (e.g., "contacts", "campaign")
- Use "iterate_over": "name" to iterate over saved results (or "previous_result" for immediate previous)
- Use {{name.field}} to reference fields from other result sets
- Check if previous results are available before planning next steps

RESPONSE FORMAT (pure JSON, no comments):
{{
  "calls": [
    {{
      "tool": "<tool_name>",
      "reason": "<why>",
      "arguments": {{}},
      "store_as": null,
      "iterate_over": null
    }}
  ],
  "needs_next_iteration": true,
  "needs_salesforce_data": false
}}

Set "store_as": "name" to save results with a semantic name for cross-tool referencing.
Set "iterate_over": "previous_result" when the tool should run for EACH item from previous results.
Set "iterate_over": "name" to iterate over a specific named result set.
Set "needs_next_iteration": true if more steps are needed after this one.
Set "needs_salesforce_data": true if you need contact/campaign data from Salesforce.

IMPORTANT RULES:
1. Use placeholders like {{{{Id}}}} for values from previous results
2. NO comments (//) in JSON
3. NO markdown, NO explanations
"""
        
        # Build user prompt with context
        stage_info = ""
        if previous_results:
            # Show more context for reasonable result sets
            # For bulk operations (like email sending), need to see all contacts
            num_results = len(previous_results)
            
            if num_results <= 10:
                # Show all items for small result sets
                stage_info = f"\n\nPREVIOUS RESULTS ({num_results} items):\n{json.dumps(previous_results, indent=2)}"
            else:
                # For large result sets, show summary + sample
                stage_info = f"\n\nPREVIOUS RESULTS: {num_results} items total\n"
                stage_info += f"Sample (first 2):\n{json.dumps(previous_results[:2], indent=2)}\n\n"
                stage_info += "IMPORTANT: ALL items from previous results are available for iteration. "
                stage_info += f"Use 'iterate_over': 'previous_result' to process all {num_results} items."
        else:
            stage_info = "\n\nThis is the FIRST step. No previous results available yet."
        
        # Add available context from state
        context_info = "\n\nAVAILABLE CONTEXT:"
        for context_path in required_context:
            value = _get_nested_value(state, context_path)
            if value:
                # Truncate long values
                value_str = json.dumps(value, indent=2)
                if len(value_str) > 200:
                    value_str = value_str[:200] + "..."
                context_info += f"\n- {context_path}: {value_str}"
        
        user_content = f"""USER REQUEST:
{state.get('user_goal', '')}

CURRENT PHASE DIRECTIVE:
{state.get('task_directive', 'No specific directive. Proceed based on User Request.')}

{stage_info}
{context_info}

TASK:
Plan the NEXT step only. What tool should be called now? 
Follow the "CURRENT PHASE DIRECTIVE" strictly if present.

Respond with pure JSON (no comments, no markdown)."""
        
        # Call LLM
        llm_model = state.get("planner_model") or "gpt-4o-mini"
        llm_provider = state.get("planner_provider") or "openai"
        
        raw_response = await call_llm(
            system_prompt=system_content,
            user_prompt=user_content,
            default_model=llm_model,
            default_provider=llm_provider,
            default_temperature=0.0,
        )
        
        # Parse response
        raw_text = str(raw_response).strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()
        
        try:
            plan = json.loads(raw_text)
            plan.setdefault("calls", [])
            plan.setdefault("needs_next_iteration", False)
            plan.setdefault("needs_salesforce_data", False)
            return plan
        except json.JSONDecodeError as e:
            logging.error(f"[{service_name}] JSON decode error: {e}")
            return {"calls": [], "needs_next_iteration": False}
    
    # Unknown strategy
    logging.error(f"[{service_name}] Unknown planning strategy: {planning_strategy}")
    return {"calls": [], "needs_next_iteration": False}


from core.mcp_loader import get_preloaded_tools


def _is_batch_capable_tool(tool_meta: Dict[str, Any], tool_name: str) -> bool:
    """
    Determine if a tool supports batch operations.
    
    Detection strategies:
    1. Tool name contains 'batch' (e.g., send_batch_emails, batch_upsert_salesforce_records)
    2. Tool schema has array parameters like 'recipients' or 'records'
    3. Explicit configuration in MCP metadata
    
    Returns:
        True if the tool supports batch operations, False otherwise
    """
    # Strategy 1: Name-based detection
    if 'batch' in tool_name.lower():
        logging.info(f"✅ [{tool_name}] Detected as batch-capable (name contains 'batch')")
        return True
    
    # Strategy 2: Schema-based detection
    schema = tool_meta.get("schema", {})
    properties = schema.get("properties", {})
    
    # Check for array parameters that indicate batch support
    batch_param_names = ['recipients', 'records', 'items', 'batch_data', 'message_versions']
    for param_name, param_schema in properties.items():
        if param_name in batch_param_names:
            if param_schema.get("type") == "array":
                logging.info(f"✅ [{tool_name}] Detected as batch-capable (has '{param_name}' array parameter)")
                return True
    
    logging.info(f"ℹ️ [{tool_name}] Not batch-capable, will use iteration")
    return False


def _get_batch_parameter_name(tool_meta: Dict[str, Any]) -> Optional[str]:
    """
    Detect the batch parameter name from tool schema.
    
    Returns the name of the array parameter used for batch operations
    (e.g., 'records', 'message_versions', 'recipients', 'items')
    """
    schema = tool_meta.get("schema", {})
    properties = schema.get("properties", {})
    
    # Common batch parameter names in priority order
    batch_param_candidates = ['message_versions', 'records', 'recipients', 'items', 'batch_data']
    
    for param_name in batch_param_candidates:
        if param_name in properties:
            param_schema = properties[param_name]
            if param_schema.get("type") == "array":
                return param_name
    
    return None


def _prepare_batch_arguments(
    arguments: Dict[str, Any],
    batch_records: List[Dict[str, Any]],
    batch_param_name: str,
    tool_name: str
) -> Dict[str, Any]:
    """
    Prepare batch arguments generically based on the batch parameter name.
    
    This replaces hardcoded tool-specific logic with generic schema-based construction.
    """
    # Start with a copy of non-batch arguments
    batch_args = {}
    
    # For each argument, decide if it should be included
    for key, value in arguments.items():
        # Skip the batch parameter itself (we'll add it separately)
        if key == batch_param_name:
            continue
        
        # Skip 'recipients' if we're using 'message_versions' (Brevo specific)
        if batch_param_name == 'message_versions' and key == 'recipients':
            batch_args[key] = []  # Clear recipients when using message_versions
            continue
        
        # For template_id in batch emails, extract from first record and convert to int
        if key == 'template_id' and batch_records:
            template_id_value = batch_records[0].get("template_id", value)
            try:
                batch_args[key] = int(template_id_value)
            except (ValueError, TypeError):
                logging.warning(f"⚠️ Could not convert template_id '{template_id_value}' to int, using as-is")
                batch_args[key] = value
            continue
        
        # Include all other arguments as-is
        batch_args[key] = value
    
    # Add the batch parameter
    batch_args[batch_param_name] = batch_records
    
    return batch_args


async def call_mcp(
    service_name: str,
    config: Dict[str, Any],
    state: MarketingState,
) -> Dict[str, Any]:
    """
    Execute MCP tools with iterative execution support.
    Uses:
      - generate_all_toolinput (Salesforce MCP only, iteration 1)
      - choose_mcp_tools(..., previous_results=...)
      - resolve_tool_placeholders(...) for {{field}} replacement
    """

    server_params = build_mcp_server_params(config)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1) Initialize MCP session
            await session.initialize()

            # 2) Get tools (from cache if available, else fetch)
            tools_meta = get_preloaded_tools(service_name)
            
            if tools_meta:
                 logging.info(f"⚡ [{service_name}] Using {len(tools_meta)} preloaded tools")
            else:
                logging.info(f"📋 [{service_name}] Fetching tools list (not preloaded)...")
                
            #     tools_response = await session.list_tools()
            #     tools_meta = []
            #     for tool in tools_response.tools:
            #         tools_meta.append({
            #             "name": tool.name,
            #             "description": getattr(tool, "description", ""),
            #             "schema": getattr(tool, "inputSchema", {}),
            #         })

            # logging.info(f"📋 [{service_name}] Available tools: {[t['name'] for t in tools_meta]}")

            # 3) Iterative execution
            all_tool_results: List[Dict[str, Any]] = []
            # Track multiple named result sets for cross-tool referencing
            # Initialize from SHARED state to allow cross-agent data access
            import copy
            result_sets: Dict[str, List[Dict[str, Any]]] = copy.deepcopy(state.get("shared_result_sets", {}))
            previous_results: Optional[List[Dict[str, Any]]] = None  # Backward compatibility
            max_iterations = 10
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                logging.info("\n" + "=" * 60)
                logging.info(f"🔄 [{service_name}] ITERATION {iteration}")
                logging.info("=" * 60)
                logging.info(f"[{service_name}] state next_action...,{state}")
                salesforce_data = state.get("salesforce_data", {})
                previous_results = salesforce_data.get("previous_results", [])
                contacts = salesforce_data.get("contacts", [])
                logging.info(f"[{service_name}] contacts...,{contacts}")
                # previous_results gets populated during tool execution, starts empty on first iteration
                # if iteration == 1:
                #     previous_results = [] # Default to empty list
                
                # ✅ FIX: Ensure 'previous_result' is available in result_sets for the Planner
                if previous_results:
                     result_sets['previous_result'] = previous_results
                # ✅ UNIFIED PLANNING - no more if/else for different MCPs
             
                logging.info(f"[{service_name}] previous_results...,{previous_results}")
                tool_plan = await plan_mcp_execution(
                    service_name=service_name,
                    config=config,
                    tools_meta=tools_meta,
                    state=state,
                    session=session,
                    iteration=iteration,
                    previous_results=previous_results,
                )

                calls = tool_plan.get("calls", [])
                needs_next = bool(tool_plan.get("needs_next_iteration", False))
                   
                if not calls:
                    logging.info(f"✅ [{service_name}] No more tools to call")
                    break

                iteration_results: List[Dict[str, Any]] = []

                # 3b) Execute planned tools
                for call_idx, call in enumerate(calls, start=1):
                    tool_name = call.get("tool")
                    arguments = call.get("arguments", {}) or {}
                    iterate_over = call.get("iterate_over")
                    reason = call.get("reason", "")

                    if not tool_name:
                        logging.warning(f"⚠️ [{service_name}] Skipping call without tool name: {call}")
                        continue

                    logging.info(f"\n📌 Tool {call_idx}/{len(calls)}: {tool_name}")
                    logging.info(f"   Reason: {reason}")

                    # Case 1: bulk operation over named or previous results
                    if iterate_over:
                        iteration_source = []
                        
                        # Handle raw list (e.g. passed from Frontend Proceed logic)
                        if isinstance(iterate_over, list):
                             iteration_source = iterate_over
                             # Normalize: wrap strings as {"Id": val} for {{Id}} placeholder
                             normalized_source = []
                             for item in iteration_source:
                                 if isinstance(item, str):
                                     normalized_source.append({"Id": item})
                                 else:
                                     normalized_source.append(item)
                             iteration_source = normalized_source
                        else:
                            # Support named results: "previous_result", "contacts", "campaign", etc.
                            iteration_source = result_sets.get(iterate_over)
                        
                        if not iteration_source:
                            logging.warning(
                                f"⚠️ [{service_name}] iterate_over='{iterate_over}' not found in result_sets. Available: {list(result_sets.keys())}"
                            )
                            continue

                        logging.info(
                            f"🔁 Processing {len(iteration_source)} items from '{iterate_over}'"
                        )
                        
                        # ✅ BATCH OPTIMIZATION: Check if tool supports batch operations
                        tool_meta = next((t for t in tools_meta if t["name"] == tool_name), None)
                        supports_batch = tool_meta and _is_batch_capable_tool(tool_meta, tool_name)
                        
                        bulk_accumulated_results: List[Dict[str, Any]] = []
                        
                        if supports_batch:
                            # ✅ NEW: Batch processing path - prepare all data and make ONE call
                            logging.info(f"🚀 [{service_name}] Using BATCH mode for {tool_name}")
                            
                            # Prepare batch data by resolving placeholders for all records
                            batch_records = []
                            for item_idx, prev_item in enumerate(iteration_source, start=1):
                                resolved_args = resolve_tool_placeholders(arguments, prev_item, result_sets)
                                
                                # For batch tools, we need to extract the individual record data
                                # Different tools have different batch formats:
                                # - Brevo: expects 'recipients' array
                                # - Salesforce batch_upsert: expects 'records' array with {record_id, fields}
                                
                                # Check tool-specific batch format
                                if 'send_batch_emails' in tool_name:
                                    # Brevo format: pass resolved_args directly
                                    # The send_batch_emails function handles converting recipients with params
                                    # into messageVersions format internally (CASE 1, lines 76-117)
                                    batch_records.append(resolved_args)
                                elif 'batch_upsert' in tool_name:
                                    # Salesforce batch format: {record_id, fields}
                                    batch_records.append({
                                        "record_id": resolved_args.get("record_id", ""),
                                        "fields": resolved_args.get("fields", resolved_args)
                                    })
                                else:
                                    # Generic batch format
                                    batch_records.append(resolved_args)
                            
                            logging.info(f"📦 Prepared {len(batch_records)} records for batch call")
                            logging.info(f"   Sample record: {json.dumps(batch_records[0] if batch_records else {}, indent=2)}")
                            
                            # Construct batch arguments based on tool type
                            if 'send_batch_emails' in tool_name:
                                # Brevo: Collect all recipients from batch_records into a single array
                                # The send_batch_emails function will convert recipients with params
                                # into messageVersions internally (CASE 1, lines 76-117)
                                
                                all_recipients = []
                                all_cc = []
                                all_bcc = []
                                
                                # Extract template_id from first record
                                template_id_value = batch_records[0].get("template_id") if batch_records else arguments.get("template_id")
                                try:
                                    template_id_int = int(template_id_value)
                                except (ValueError, TypeError):
                                    logging.error(f"❌ Invalid template_id: {template_id_value}")
                                    template_id_int = 0
                                
                                # Collect all recipients, cc, and bcc from each batch record
                                for record in batch_records:
                                    if "recipients" in record:
                                        all_recipients.extend(record["recipients"])
                                    if "cc" in record:
                                        all_cc.extend(record["cc"])
                                    if "bcc" in record:
                                        all_bcc.extend(record["bcc"])
                                
                                batch_args = {
                                    "template_id": template_id_int,
                                    "sender_email": arguments.get("sender_email", "aleenamathews2001@gmail.com"),
                                    "sender_name": arguments.get("sender_name", "Aleena Mathews"),
                                    "recipients": all_recipients
                                }
                                
                                # Add cc and bcc if present
                                if all_cc:
                                    batch_args["cc"] = all_cc
                                if all_bcc:
                                    batch_args["bcc"] = all_bcc
                            elif 'batch_upsert' in tool_name:
                                # Salesforce batch_upsert expects records array
                                batch_args = {
                                    "object_name": arguments.get("object_name", ""),
                                    "records": batch_records
                                }
                            else:
                                # Generic batch format
                                batch_args = {
                                    **arguments,
                                    "batch_data": batch_records
                                }
                            
                            try:
                                logging.info(f"🎯 Making SINGLE batch call with {len(batch_records)} records")
                                result = await session.call_tool(tool_name, batch_args)
                                
                                # Check if result indicates an error
                                is_error = getattr(result, 'isError', False)
                                
                                # Defensive check: Also parse content for error status
                                if not is_error and hasattr(result, 'content') and result.content:
                                    for item in result.content:
                                        if hasattr(item, 'text'):
                                            try:
                                                content_json = json.loads(item.text)
                                                if isinstance(content_json, dict) and content_json.get('status') == 'error':
                                                    is_error = True
                                                    logging.warning(f"   ⚠️ Detected error in JSON content despite isError=False")
                                                    break
                                            except (json.JSONDecodeError, AttributeError):
                                                pass
                                
                                if is_error:
                                    error_msg = "Unknown error"
                                    if hasattr(result, 'content') and result.content:
                                        for item in result.content:
                                            if hasattr(item, 'text'):
                                                error_msg = item.text
                                                break
                                    
                                    logging.error(f"   ❌ Batch call returned error: {error_msg[:200]}...")
                                    iteration_results.append({
                                        "tool_name": tool_name,
                                        "request": batch_args,
                                        "error": error_msg,
                                        "status": "error",
                                        "batch_size": len(batch_records)
                                    })
                                else:
                                    logging.info(f"   ✅ Batch call SUCCESS for {len(batch_records)} records")
                                    logging.info(f"   ✅ Result: {result}")
                                    
                                    iteration_results.append({
                                        "tool_name": tool_name,
                                        "request": batch_args,
                                        "response": result,
                                        "status": "success",
                                        "batch_size": len(batch_records)
                                    })
                                    
                                    # Extract results from batch response
                                    rows = extract_rows_from_result(result)
                                    if rows:
                                        bulk_accumulated_results.extend(rows)
                                        logging.info(f"   📦 Extracted {len(rows)} records from batch call")
                                    else:
                                        logging.info("   ℹ️  No records extracted from batch call")
                                        
                            except Exception as e:
                                logging.error(f"   ❌ Batch call failed: {e}")
                                iteration_results.append({
                                    "tool_name": tool_name,
                                    "request": batch_args,
                                    "error": str(e),
                                    "status": "error",
                                    "batch_size": len(batch_records)
                                })
                        
                        else:
                            # ✅ EXISTING: Individual iteration path (backward compatibility)
                            logging.info(f"🔁 [{service_name}] Using ITERATION mode for {tool_name}")
                            
                            for item_idx, prev_item in enumerate(iteration_source, start=1):
                                logging.info(f"Before placeholder replacement, arguments: {json.dumps(arguments, indent=2)}")

                                # ✅ Replace {{field}} placeholders from each record and result_sets
                                resolved_args = resolve_tool_placeholders(arguments, prev_item, result_sets)

                                logging.info(
                                    f"   [{item_idx}/{len(iteration_source)}] Calling with: "
                                    f"{json.dumps(resolved_args, indent=2)}"
                                )
                                
                                try:
                                    result = await session.call_tool(tool_name, resolved_args)
                                    
                                    # ✅ Check if result indicates an error
                                    is_error = getattr(result, 'isError', False)
                                    
                                    # Defensive check: Also parse content for error status
                                    if not is_error and hasattr(result, 'content') and result.content:
                                        for item in result.content:
                                            if hasattr(item, 'text'):
                                                try:
                                                    content_json = json.loads(item.text)
                                                    if isinstance(content_json, dict) and content_json.get('status') == 'error':
                                                        is_error = True
                                                        logging.warning(f"   ⚠️ Detected error in JSON content despite isError=False")
                                                        break
                                                except (json.JSONDecodeError, AttributeError):
                                                    pass
                                    
                                    if is_error:
                                        # Extract error message from content
                                        error_msg = "Unknown error"
                                        if hasattr(result, 'content') and result.content:
                                            for item in result.content:
                                                if hasattr(item, 'text'):
                                                    error_msg = item.text
                                                    break
                                        
                                        logging.error(f"   ❌ Tool returned error: {error_msg[:200]}...")
                                        iteration_results.append({
                                            "tool_name": tool_name,
                                            "request": resolved_args,
                                            "error": error_msg,
                                            "status": "error",
                                            "source_item": prev_item,
                                        })
                                        continue  # Skip to next iteration item
                                    
                                    logging.info("   ✅ Success")
                                    logging.info(f"   ✅ Success: {result}")
                                     

                                    iteration_results.append({
                                        "tool_name": tool_name,
                                        "request": resolved_args,
                                        "response": result,
                                        "status": "success",
                                        "source_item": prev_item,
                                    })
                                    
                                    rows = extract_rows_from_result(result)
                                    if rows:
                                        bulk_accumulated_results.extend(rows)  # 🔧 EXTEND, not replace
                                        logging.info(f"   📦 Extracted {len(rows)} records from this call")
                                        logging.info(f"   📋 Sample record: {json.dumps(rows[0] if rows else {}, indent=2)}")
                                    else:
                                        logging.info("   ℹ️  No records extracted from this call")
                                except Exception as e:
                                    logging.error(f"   ❌ Failed: {e}")
                                    iteration_results.append({
                                        "tool_name": tool_name,
                                        "request": resolved_args,
                                        "error": str(e),
                                        "status": "error",
                                        "source_item": prev_item,
                                    })
                        
                        # Store accumulated results (same for both batch and iteration modes)
                        if bulk_accumulated_results:
                            # Store accumulated results
                            store_as = call.get("store_as", f"tool_{call_idx}")
                            result_sets[store_as] = bulk_accumulated_results
                            result_sets["previous_result"] = bulk_accumulated_results  # Backward compat
                            previous_results = bulk_accumulated_results
                            logging.info(f"📦 Stored {len(bulk_accumulated_results)} records as '{store_as}'")

                        # After a bulk write, usually stop:
                        needs_next = False  # safety override

                    # Case 2: single execution (query or single write)
                    else:
                        logging.info(
                            f"   Calling with: {json.dumps(arguments, indent=2)}"
                        )

                        try:
                            # ✅ Fix: Resolve placeholders even for single execution
                            resolved_args = resolve_tool_placeholders(arguments, {}, result_sets)
                            logging.info(f"   Calling with: {json.dumps(resolved_args, indent=2)}")
                            
                            result = await session.call_tool(tool_name, resolved_args)
                            
                            # ✅ Check if result indicates an error
                            is_error = getattr(result, 'isError', False)
                            
                            # Defensive check: Also parse content for error status
                            if not is_error and hasattr(result, 'content') and result.content:
                                for item in result.content:
                                    if hasattr(item, 'text'):
                                        try:
                                            content_json = json.loads(item.text)
                                            if isinstance(content_json, dict) and content_json.get('status') == 'error':
                                                is_error = True
                                                logging.warning(f"   ⚠️ Detected error in JSON content despite isError=False")
                                                break
                                        except (json.JSONDecodeError, AttributeError):
                                            pass
                            
                            if is_error:
                                # Extract error message from content
                                error_msg = "Unknown error"
                                if hasattr(result, 'content') and result.content:
                                    for item in result.content:
                                        if hasattr(item, 'text'):
                                            error_msg = item.text
                                            break
                                
                                logging.error(f"   ❌ Tool returned error: {error_msg[:200]}...")
                                iteration_results.append({
                                    "tool_name": tool_name,
                                    "request": arguments,
                                    "error": error_msg,
                                    "status": "error",
                                })
                                # Don't extract rows or store results for errors
                            else:
                                logging.info("   ✅ Success")
                                logging.info(f"   ✅ Success: {result}")
                                iteration_results.append({
                                    "tool_name": tool_name,
                                    "request": arguments,
                                    "response": result,
                                    "status": "success",
                                })
                                
                                # ✅ CRITICAL FIX: Extract rows and store with name
                                rows = extract_rows_from_result(result)
                                if rows:
                                    # Store with explicit name or auto-generated name
                                    store_as = call.get("store_as", f"tool_{call_idx}")
                                    result_sets[store_as] = rows
                                    result_sets["previous_result"] = rows  # Backward compatibility
                                    previous_results = rows
                                    logging.info(
                                        f"   📦 Extracted {len(rows)} records, stored as '{store_as}'"
                                    )
                                    logging.info(f"   📋 Sample record: {json.dumps(rows[0] if rows else {}, indent=2)}")
                                else:
                                    logging.info("   ℹ️  No records extracted (might be a write operation)")
                             
                        except Exception as e:
                            logging.error(f"   ❌ Failed: {e}")
                            iteration_results.append({
                                "tool_name": tool_name,
                                "request": arguments,
                                "error": str(e),
                                "status": "error",
                            })

                all_tool_results.extend(iteration_results)
                
                # ✅ Auto-stop logic: If planner said "no more work" OR we executed tools without iteration
                if not needs_next:
                    logging.info(f"[{service_name}] Planner indicated completion (needs_next_iteration=False)")
                elif not any(call.get("iterate_over") == "previous_result" for call in calls):
                    # Single execution completed, stop unless planner explicitly wants next iteration
                    needs_next = False
                    logging.info(f"[{service_name}] Single tool execution complete, stopping")

                # 3c) Decide whether to continue
                if not needs_next:
                    logging.info(
                        f"\n✅ [{service_name}] Workflow complete "
                        f"(needs_next_iteration={needs_next})"
                    )
                    break

            # 4) Summary
            logging.info("\n" + "=" * 60)
            logging.info(f"📊 [{service_name}] EXECUTION SUMMARY")
            logging.info("=" * 60)
            logging.info(f"Total iterations: {iteration}")
            logging.info(f"Total tool calls: {len(all_tool_results)}")
            logging.info(
                f"Successful: {len([r for r in all_tool_results if r.get('status') == 'success'])}"
            )
            logging.info(
                f"Failed: {len([r for r in all_tool_results if r.get('status') == 'error'])}"
            )

            # DEBUG LOGGING FOR DATA PERSISTENCE
            logging.info(f"📤 [call_mcp] Returning result_sets with keys: {list(result_sets.keys())}")
            
            return {
                "service": service_name,
                "tools_meta": tools_meta,
                "iterations": iteration,
                "previous_results": previous_results,
                "tool_results": all_tool_results,
                "result_sets": result_sets, # ✅ Expose named results for persistence
                "execution_summary": {
                    "total_iterations": iteration,
                    "total_calls": len(all_tool_results),
                    "successful_calls": len(
                        [r for r in all_tool_results if r.get("status") == "success"]
                    ),
                    "failed_calls": len(
                        [r for r in all_tool_results if r.get("status") == "error"]
                    ),
                },
            }


 

def extract_rows_from_result(result) -> Optional[List[Dict[str, Any]]]:
    """
    Extract record rows from MCP tool result.
    Handles various response formats from different MCP servers.
    """
    try:
        logging.info(f"[extract_rows] result: {result!r}")
        # 1) Handle MCP result with content attribute (common pattern)
        if hasattr(result, 'content'):
            for item in result.content:
                if hasattr(item, 'text'):
                    raw = item.text
                    logging.debug(f"[extract_rows] raw text: {raw!r}")
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        logging.debug("[extract_rows] Not JSON, skipping this content item")
                        continue

                    # ---- CASE A: SOQL-style dict with 'records' ----
                    if isinstance(data, dict):
                        # Salesforce query style: {"records": [...], "total": N}
                        if 'records' in data and isinstance(data['records'], list):
                            records = data['records']
                            logging.debug(f"[extract_rows] Found {len(records)} records in 'records'")
                            return records or None

                        # Generic result wrappers
                        if 'result' in data:
                            if isinstance(data['result'], list):
                                logging.debug(f"[extract_rows] Found {len(data['result'])} records in 'result'")
                                return data['result'] or None
                            if isinstance(data['result'], dict) and 'records' in data['result']:
                                records = data['result']['records']
                                logging.debug(f"[extract_rows] Found {len(records)} in 'result.records'")
                                return records or None

                        if 'data' in data and isinstance(data['data'], list):
                            logging.debug(f"[extract_rows] Found {len(data['data'])} records in 'data'")
                            return data['data'] or None

                        # ---- CASE B: single create/update result with id ----
                        # e.g. {"success": true, "id": "003..."}
                        if 'id' in data and 'records' not in data:
                            rec: Dict[str, Any] = dict(data)
                            # normalise Id so {{Id}} works in the planner
                            rec['Id'] = rec.get('Id') or rec['id']
                            logging.debug(f"[extract_rows] Normalized single record with Id={rec['Id']}")
                            return [rec]

                    # ---- CASE C: direct list ----
                    if isinstance(data, list) and data:
                        logging.debug(f"[extract_rows] Found {len(data)} records as direct list")
                        return data

        # 2) Handle structuredContent attribute (fallback)
        if hasattr(result, 'structuredContent'):
            structured = result.structuredContent
            logging.debug(f"[extract_rows] structuredContent: {structured!r}")

            if isinstance(structured, dict):
                for key in ['records', 'result', 'data', 'rows']:
                    if key in structured and isinstance(structured[key], list):
                        records = structured[key]
                        if records:
                            logging.debug(f"[extract_rows] Found {len(records)} records in structuredContent['{key}']")
                            return records

        logging.debug("[extract_rows] No records found in result")
        return None

    except Exception as e:
        logging.debug(f"[extract_rows] Could not extract rows from result: {e}")
        return None


# def resolve_tool_placeholders(arguments: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Recursively replace {{field}} placeholders in arguments with values from record.
    
#     Example:
#         arguments = {"ContactId": "{{Id}}"}
#         record = {"Id": "003xx000004TmiQAAS"}
#         returns = {"ContactId": "003xx000004TmiQAAS"}
#     """
#     def replace_value(value):
#         if isinstance(value, str):
#             # Check if it's a placeholder like {{Id}}
#             if value.startswith("{{") and value.endswith("}}"):
#                 field_name = value[2:-2].strip()
#                 if field_name in record:
#                     return record[field_name]
#                 else:
#                     logging.warning(f"⚠️ Placeholder {{{{field_name}}}} not found in record: {record}")
#                     return value
#             return value
#         elif isinstance(value, dict):
#             return {k: replace_value(v) for k, v in value.items()}
#         elif isinstance(value, list):
#             return [replace_value(item) for item in value]
#         else:
#             return value
    
#     return replace_value(arguments)
def resolve_tool_placeholders(
    arguments: Dict[str, Any], 
    record: Dict[str, Any],
    result_sets: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> Dict[str, Any]:
    """Recursively replace {{field}} placeholders in arguments with values from record or result_sets.
    
    Supports:
    - {{Id}} - from current iteration record
    - {{campaign.Id}} - from named result set 'campaign'
    """
    result_sets = result_sets or {}
    logging.info(f"🔍 [resolve_placeholders] Available result_sets keys: {list(result_sets.keys())}")
    
    def replace_value(value, is_sql_context=False):
        if isinstance(value, str):
            # Check if this looks like a SQL query
            is_sql = any(keyword in value.upper() for keyword in ['SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE'])
            
            def replacer(match):
                full_match = match.group(1).strip()
                logging.info(f"🔍 [replacer] Found match: '{full_match}'")
                
                # Check for dotted notation: result_name.field
                if '.' in full_match:
                    result_name, field_name = full_match.split('.', 1)
                    
                    # Case-insensitive lookup for result_name
                    # Find the actual key in result_sets that matches result_name (ignoring case)
                    actual_result_key = next((k for k in result_sets.keys() if k.lower() == result_name.lower()), None)
                    
                    if actual_result_key:
                        # Get first item from named result set
                        named_record = result_sets[actual_result_key][0]
                        if field_name in named_record:
                            replacement = named_record[field_name]
                            
                            # 🧹 CLEANING HEURISTIC: Fix "3 - Name" format for IDs
                            # If value looks like "Integer - String", extract the integer.
                            if isinstance(replacement, str) and " - " in replacement:
                                import re
                                match_id = re.match(r'^(\d+)\s+-\s+.*', replacement)
                                if match_id:
                                    cleaned_id = match_id.group(1)
                                    logging.info(f"🧹 Cleaned '{replacement}' to '{cleaned_id}'")
                                    replacement = int(cleaned_id) # Return as int to satisfy pydantic if possible, or str info
                                    # Pydantic will accept int for int field. If we return str, it tries to parse.
                                    # But `resolve_tool_placeholders` returns STR usually for regex replacement.
                                    # Wait, `re.sub` expects string return.
                                    # If we return int, `re.sub` will crash?
                                    # YES. replacer MUST return string.
                                    replacement = cleaned_id

                            logging.info(f"Replacing {{{{result_name}}.{{field_name}}}}: {replacement}")
                            if is_sql and isinstance(replacement, str):
                                return f"'{replacement}'"
                            return str(replacement)
                        else:
                            logging.warning(f"⚠️ Field '{field_name}' not found in result set '{actual_result_key}'")
                            return match.group(0)
                    else:
                        logging.warning(f"⚠️ Result set '{result_name}' (normalized: {result_name.lower()}) not found. Available: {list(result_sets.keys())}")
                        return match.group(0)
                
                # Fall back to current iteration record
                field_name = full_match
                logging.info(f"Replacing placeholder: {field_name} with value: {record.get(field_name)}")
                if field_name in record:
                    replacement = record[field_name]
                    # Only add quotes if it's a SQL context AND the value is a string
                    if is_sql and isinstance(replacement, str):
                        return f"'{replacement}'"
                    return str(replacement)
                else:
                    logging.warning(f"⚠️ Placeholder {field_name} not found in record: {record}")
                    return match.group(0)
            
            return re.sub(r'\{\{([^}]+)\}\}', replacer, value)
        
        elif isinstance(value, dict):
            return {k: replace_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [replace_value(item) for item in value]
        else:
            return value
    
    return replace_value(arguments)

def extract_json_response_from_tool_result(result) -> Optional[str]:
    """
    Extract json_response field from Salesforce MCP generate_all_toolinput result.
    """
    try:
        # Check structuredContent first
        if hasattr(result, 'structuredContent'):
            structured = result.structuredContent
            if isinstance(structured, dict):
                if 'result' in structured and isinstance(structured['result'], dict):
                    if 'json_response' in structured['result']:
                        return structured['result']['json_response']
        
        # Check content attribute
        if hasattr(result, 'content'):
            for item in result.content:
                if hasattr(item, 'text'):
                    try:
                        data = json.loads(item.text)
                        if isinstance(data, dict) and 'json_response' in data:
                            return data['json_response']
                    except json.JSONDecodeError:
                        continue
        
        logging.error("Could not find json_response in tool result")
        return None
        
    except Exception as e:
        logging.error(f"Error extracting json_response: {e}")
        return None
    

