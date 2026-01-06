from typing import List, Dict, Any, Optional
from Error.sf_error import SalesforceApiError
from client.sf_client import SalesforceClient
from baseagent import resolve_placeholders,call_llm,fetch_prompt_metadata
import logging
import json
import asyncio
import sys
from dotenv import load_dotenv
import os
 
load_dotenv()
from openai import AsyncOpenAI
from chromadbutils import ChromaDBManager, chroma_client, schema_data, ensure_schema_initialized

chroma_manager = None

def get_chroma_manager():
    global chroma_manager
    if not chroma_manager:
        chroma_manager = ChromaDBManager(chroma_client)
    return chroma_manager

sf_client = SalesforceClient("agent")

 
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_sf_connected = False

def ensure_sf_connected():
    """Ensure Salesforce is connected (call this at runtime, not import time)"""
    global _sf_connected
    if not _sf_connected:
        _sf_connected = sf_client.connect()
    return _sf_connected


def find_relevant_objects_and_fields(user_query: str, context_object: str = None):
    """Find relevant objects and fields using ChromaDB with detailed logging"""
    global schema_data
    
    # 💤 LAZY INIT TRIGGER
    ensure_schema_initialized()
    # Reload schema_data if it was None (since init might have populated it)
    import chromadbutils
    if hasattr(chromadbutils, 'schema_data') and chromadbutils.schema_data:
        schema_data = chromadbutils.schema_data

    logging.debug(f"Received user_query: '{user_query}' with context_object: '{context_object}'")

    if not user_query or not user_query.strip():
        logging.warning("Empty user query provided")
        return None, None

    # schema_data might still be None if init failed or DB empty, but we allow trying
    if not schema_data:
        # Try one last re-fetch from the module
        if hasattr(chromadbutils, 'schema_data'):
             schema_data = chromadbutils.schema_data
        
        if not schema_data:
            logging.error("Schema data not initialized")
            return None, None

    try:
        # Stage 1: Object search
        logging.debug("Searching for relevant objects...")
        cm = get_chroma_manager()
        object_results = cm.search_objects(user_query, top_k=2)
        logging.debug(f"Object results: {object_results}")

        if not object_results:

            logging.info("No relevant objects found")
            return None, None

        selected_object = object_results[0]['object_name']
        logging.info(f"Most relevant object: {selected_object}")

        # Stage 2: Field search
        logging.debug(f"Searching fields in selected object: {selected_object} using query: '{user_query}'")
        field_results = cm.search_fields(selected_object, user_query, top_k=10)
        logging.debug(f"Initial field results: {field_results}")
        
        # 🔑 SPECIAL HANDLING: If query mentions "active" or "currently working" and object is Contact
        # Force-include Start_Date__c and End_Date__c field descriptions
        if selected_object == "Contact" and any(keyword in user_query.lower() for keyword in ["active", "currently", "working", "employed"]):
            logging.info("🔍 Detected employment status query for Contact - searching for date fields...")
            date_field_results = cm.search_fields("Contact", "Start_Date__c End_Date__c employment active", top_k=5)
            
            # Merge date fields into field_results if not already present
            existing_field_names = {f['field_name'] for f in field_results}
            for date_field in date_field_results:
                if date_field['field_name'] in ['Start_Date__c', 'End_Date__c'] and date_field['field_name'] not in existing_field_names:
                    field_results.insert(0, date_field)  # Insert at beginning for priority
                    logging.info(f"✅ Force-added {date_field['field_name']} to field results")

        if not field_results and len(object_results) > 1:
            selected_object = object_results[1]['object_name']
            logging.info(f"No field results found. Falling back to next object: {selected_object}")
            field_results = cm.search_fields(selected_object, user_query, top_k=10)
            logging.debug(f"Field results after fallback: {field_results}")

        if field_results:
            top_field = field_results[0]
            logging.info(f"Top matched field: {top_field['field_name']} (distance: {top_field['distance']})")

            logging.debug(f"Checking for 'Name' field on {selected_object}")
            name_field_results = cm.search_fields(selected_object, "Name", top_k=1)
            has_name = len(name_field_results) > 0 and name_field_results[0]['field_name'] == 'Name'
            logging.debug(f"Has 'Name' field: {has_name}")

            # Build selected fields
            selected_fields = ['Id']
            if has_name:
                selected_fields.append('Name')

            if top_field['field_name'] not in selected_fields:
                selected_fields.append(top_field['field_name'])

            logging.debug(f"Initial selected fields: {selected_fields}")

            # Add additional fields under threshold
            distance_threshold = 1.3
            max_fields = 8

            for field_result in field_results[1:]:
                if (field_result['distance'] < distance_threshold and
                        field_result['field_name'] not in selected_fields and
                        len(selected_fields) < max_fields):
                    selected_fields.append(field_result['field_name'])
                    logging.debug(f"Added field: {field_result['field_name']} (distance: {field_result['distance']})")

            # 💉 FORCE-INCLUDE email_template__c for Campaigns
            # This allows Brevo to pick up the template ID dynamically
            if selected_object.lower() == 'campaign' and 'Email_template__c' not in selected_fields:
                 selected_fields.append('Email_template__c')
                 logging.info("💉 Force-added 'Email_template__c' to selected fields for Campaign")

            relevant_field = {
                "object": selected_object,
                "fields": selected_fields,
                "filter_field": top_field['field_name'],
                "description": top_field['description'],
                "datatype": top_field['datatype'],
                "context_object": context_object
            }

            logging.info(f"Final selected object: {selected_object}")
            logging.info(f"Final selected fields: {selected_fields}")
            return selected_object, relevant_field

        logging.info("No relevant fields found")
        return selected_object, None

    except Exception as e:
        logging.error(f"Error finding objects/fields: {e}")
        return None, None

async def generate_structured_response(
    user_query: str,
    selected_object: Optional[str],
    relevant_fields: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None
) -> str:
    """Generate structured JSON response using LLM via call_llm helper"""
    try:
        # 🔍 CRITICAL DEBUG: Log what we're working with
        logging.info(f"🔍 generate_structured_response called with:")
        logging.info(f"   - user_query: {user_query[:100]}...")
        logging.info(f"   - selected_object: {selected_object}")
        logging.info(f"   - relevant_fields: {relevant_fields}")
        
        prompt_metadata = fetch_prompt_metadata("Salesforce CRUD JSON Prompt")
        
        logging.info(f"Prompt metadata: {prompt_metadata}")
        
        resolved_prompt = resolve_placeholders(
            prompt=prompt_metadata["prompt"],
            configs=prompt_metadata["configs"],
            state=context
        )
        
        logging.info(f"Resolved prompt: {resolved_prompt}")

        # 🔑 INJECT FIELD DESCRIPTIONS FROM CHROMADB
        # This prevents LLM from hallucinating fields like "IsActive" that don't exist
        field_context = ""
        if relevant_fields and relevant_fields.get('description'):
            # Build comprehensive field information
            field_descriptions = []
            
            # Add the primary filter field
            field_descriptions.append(f"""
**Primary Filter Field:**
- Field Name: {relevant_fields.get('filter_field')}
- Data Type: {relevant_fields.get('datatype')}
- Description: {relevant_fields.get('description')}
""")
            
            # 🔑 CRITICAL: If Contact object and employment-related query, add Start_Date__c and End_Date__c
            if selected_object == "Contact" and any(keyword in user_query.lower() for keyword in ["active", "currently", "working", "employed"]):
                logging.info("🔍 Adding employment date field descriptions to prompt...")
                try:
                    cm = get_chroma_manager()
                    date_fields = cm.search_fields("Contact", "Start_Date__c End_Date__c", top_k=5)
                    for df in date_fields:
                        if df['field_name'] in ['Start_Date__c', 'End_Date__c']:
                            field_descriptions.append(f"""
**Employment Status Field:**
- Field Name: {df['field_name']}
- Data Type: {df['datatype']}
- Description: {df['description']}
""")
                            logging.info(f"✅ Added {df['field_name']} description to prompt")
                except Exception as e:
                    logging.warning(f"Could not fetch employment date fields: {e}")
            
            field_context = f"""

⚠️ CRITICAL SCHEMA INFORMATION FOR {selected_object} OBJECT:

The following field information comes from the actual Salesforce schema. DO NOT use fields that are not listed here or in your general knowledge of standard Salesforce fields.

{''.join(field_descriptions)}

**Available Fields for {selected_object}:**
{', '.join(relevant_fields.get('fields', []))}

⚠️ DO NOT HALLUCINATE FIELDS: If you need to filter for "active" or "currently working" records, you MUST use the fields and logic described above. DO NOT invent fields like "IsActive" unless they are explicitly listed in the available fields.

⚠️ MANDATORY: If filtering for "active" or "currently working" contacts, you MUST use the  End_Date__c fields with the exact logic described in their descriptions. DO NOT omit this filter.

⚠️ CRITICAL SOQL EXAMPLE FOR ACTIVE CONTACTS:
```sql
WHERE (End_Date__c = null OR End_Date__c >= TODAY)
```
The parentheses and NULL check are MANDATORY. End_Date__c = null means the person is still employed (ongoing).
"""
            resolved_prompt += field_context
            logging.info(f"✅ Injected field descriptions into prompt for {selected_object}")

        # �💉 EXTEND EXISTING PROMPT WITH NAMED RESULT SET CAPABILITY
        resolved_prompt += """

    ⚠️ ENHANCED FEATURE: Named Result Sets for Complex Multi-Step Workflows

    **WHEN TO USE NAMED RESULTS:**
    When Step 3+ needs to reference results from Step 1 (not the immediately previous step), you MUST use named result sets.

    **EXTENDED SYNTAX:**
    1. Add "store_as": "semantic_name" to ANY tool call to save its results
       - Use lowercase object names: "contacts", "campaign", "accounts", "leads"
       
    2. Use "iterate_over": "semantic_name" to iterate over a SPECIFIC saved result set
       - "iterate_over": "previous_result" → iterate over immediately previous tool (existing behavior)
       - "iterate_over": "contacts" → iterate over the saved "contacts" result set
       
    3. Use {{name.Field}} to reference fields from OTHER named result sets
       - {{campaign.Id}} → get Id from the "campaign" result set
       - {{Id}} → get Id from CURRENT iteration item (existing behavior)

    ⚠️ UNIVERSAL REVIEW PROTOCOL - MANDATORY PREVIEW:
    For ANY request that involves Creating, Updating, or Deleting records (e.g., "Create Campaign", "Update Contact", "Delete Lead"):

    RULE 1: IF THE USER HAS NOT EXPLICITLY SAID "PROCEED" (or "Confirm", "Yes go ahead"):
    - You MUST usage `propose_action` tool instead of `create/update/delete`.
    - Do NOT execute the actual change yet.
    - If you also need to fetch data (e.g. "Find contacts and create campaign"), DO BOTH:
      1. run_dynamic_soql (to find data)
      2. propose_action (to show what you WOULD create)
   
    RULE 2: SCHEMA-DRIVEN DEFAULTS (MANDATORY):
    Check the Salesforce Schema provided in the context. Look for fields that have the property `"needvalue": true` (or `"needvalue ": true`).
    If a field has this property AND the user has not provided a value, you MUST apply the following defaults:
    - If a field has this property AND the user has not provided a value, you MUST apply the defaults provided in the specific instructions below.
    - If no specific default instruction is provided, leave it blank or use "Need Value".
    
    Do NOT default fields that do not have this property (unless required for standard creation).
    
    RULE 3: IF THE USER SAYS "PROCEED" (or "Confirm"):
    - Use the ACTUAL `create_salesforce_record` (or update/delete) tools.
    - Do not use `propose_action` again.

    Example (User: "Create a campaign named Alpha"):
    {
      "calls": [
        {
          "tool": "propose_action",
          "reason": "Preview campaign creation",
          "arguments": {
            "object_name": "Campaign",
            "fields": {"Name": "Alpha", "Status": "Planned"} 
          }
        }
      ]
    }

    Example (User: "Find contacts for Acme and add to new campaign Beta"):
    {
      "calls": [
        {
          "tool": "run_dynamic_soql",
          "store_as": "contacts",
          "arguments": {"query": "SELECT Id, Name, Email FROM Contact WHERE Account.Name = 'Acme'"}
        },
        {
          "tool": "propose_action",
          "reason": "Preview campaign creation",
          "arguments": {
            "object_name": "Campaign",
            "fields": {"Name": "Beta"}
          }
        }
      ]
    }

        {
          "tool": "run_dynamic_soql",
          "store_as": "contacts",
          "arguments": {"query": "SELECT Id, Name, Email FROM Contact WHERE Id IN (SELECT ContactId FROM CampaignMember WHERE CampaignId = 'X')"}
        }
      ]
      // 🛑 STOP! Do NOT add "propose_action" for Email. The next Agent (Brevo) will handle sending.
    }

    ⚠️ EXAMPLE (User says "PROCEED" after seeing proposal):
    {
      "calls": [
        {
          "tool": "create_salesforce_record",
          "store_as": "campaign",
          "reason": "User confirmed - creating Campaign",
          "arguments": {
            "object_name": "Campaign",
            "fields": {"Name": "Beta", "Status": "Planned"}
          }
        },
        {
          "tool": "create_salesforce_record",
          "reason": "Creating CampaignMemberStatus for Draft status",
          "arguments": {
            "object_name": "CampaignMemberStatus",
            "fields": {
              "CampaignId": "{{campaign.Id}}",
              "Label": "Draft",
              "IsDefault": true,
              "HasResponded": false,
              "SortOrder": 3
            }
          }
        },
        {
          "tool": "create_salesforce_record",
          "iterate_over": ["003fo...AAC", "003fo...AA0"],
          "reason": "Creating CampaignMembers for each contact",
          "arguments": {
            "object_name": "CampaignMember",
            "fields": {
              "CampaignId": "{{campaign.Id}}",
              "ContactId": "{{Id}}"
            }
          }
        }
      ]
    }

    ⚠️ CRITICAL RULE FOR EMAIL CAMPAIGNS:
    If the user mentions a Campaign ID (e.g., "701fo00000COmslAAD") AND the request involves sending emails:
    - ALWAYS fetch the Campaign record FIRST using run_dynamic_soql
    - MUST include "Email_template__c" in the SELECT clause
    - Use "store_as": "campaign" to save the result
    - Example: SELECT Id, Name, Email_template__c FROM Campaign WHERE Id = '701fo00000COmslAAD'
    - This allows the email system (Brevo) to use the correct template

"""
        logging.info(f"About to call LLM...")  # Add this
        
        model = "gpt-4o"
        provider = "OpenAI"
        
        # 🔑 ADD SESSION CONTEXT to user query if available (FULLY GENERIC)
        session_context = context.get("session_context", {}) if context else {}
        session_info = ""
        
        if session_context:
            created_records = session_context.get("created_records", {})
            conversation_history = session_context.get("conversation_history", [])
            
            # Dynamically show ALL created object types (Campaign, Contact, Lead, etc.)
            if created_records:
                for obj_type, records in created_records.items():
                    if records:
                        record_list = "\n".join([
                            f"- {r.get('Name', 'Unnamed')} (ID: {r.get('Id')})" 
                            for r in records[-5:]  # Show last 5 of each type
                        ])
                        session_info += f"\n\n🔑 PREVIOUSLY CREATED {obj_type.upper()}(S) IN THIS SESSION:\n{record_list}"
            
            if conversation_history:
                last_action = conversation_history[-1] if conversation_history else {}
                if last_action:
                    session_info += f"\n\n🔑 PREVIOUS REQUEST: {last_action.get('user_goal', '')}"
        
        # 🔑 FETCH NEED VALUE FIELDS for defaults
        need_value_fields = []
        objects_to_check = []
        
        # 🧠 POST-EMAIL STATUS UPDATE CHECK
        brevo_results = context.get('brevo_results', {}) if context else {}
        email_sent_success = False
        if brevo_results and brevo_results.get('execution_summary', {}).get('successful_calls', 0) > 0:
             email_sent_success = True
             logging.info("🧠 Detected successful email sending. Enforcing CampaignMember status update.")
             if "CampaignMember" not in objects_to_check:
                 objects_to_check.append("CampaignMember")
             session_info += "\n\n🔑 RECENT ACTIVITY: Emails have been successfully SENT via Brevo."

        if selected_object:
            objects_to_check.append(selected_object)
            
        # 🧠 SMART CHECK: If "Campaign" is in query but not selected (e.g. "Find contacts and create campaign")
        if "campaign" in user_query.lower() and "campaign" not in [o.lower() for o in objects_to_check]:
             logging.info("🧠 Detailed query involves Campaign, fetching its defaults too.")
             objects_to_check.append("Campaign")

        # 🧠 SMART CHECK: If "CampaignMember" is in query (e.g. from Proceed message)
        if "campaignmember" in user_query.lower().replace(" ", "") and "CampaignMember" not in objects_to_check:
             logging.info("🧠 Detailed query involves CampaignMember, fetching its defaults too.")
             objects_to_check.append("CampaignMember")

        # 🧠 AUTO-ADD CampaignMember when creating Campaign with contacts
        if "Campaign" in objects_to_check:
            # Check if contacts are involved (either in query or in session context)
            has_contacts = ("contact" in user_query.lower() or 
                          "member" in user_query.lower() or
                          (session_context and session_context.get("created_records", {}).get("Contact")))
            
            if has_contacts and "CampaignMember" not in objects_to_check:
                logging.info("🧠 Campaign creation involves contacts, auto-adding CampaignMember for status setup")
                objects_to_check.append("CampaignMember")


        if objects_to_check:
            try:
                cm = get_chroma_manager()
                default_value_map = {}
                for obj in objects_to_check:
                    fields_metadata = cm.get_need_value_fields(obj)
                    for f in fields_metadata:
                        fname = f.get('field_name')
                        if fname:
                            need_value_fields.append(fname)
                            if f.get('defaultValue'):
                                default_value_map[fname] = f.get('defaultValue')
                    
                need_value_fields = list(set(need_value_fields)) # Deduplicate
                logging.info(f"🔍 Combined need value fields: {need_value_fields}")
                logging.info(f"🔍 Default Values found: {default_value_map}")
            except Exception as e:
                logging.warning(f"⚠️ Failed to fetch need value fields: {e}")
        else:
             logging.warning(f"⚠️ No objects to check for defaults")

        logging.info(f"Session info: {session_info}")
        
        # Enhance user query with session information and SMART DEFAULTS instruction
        enhanced_user_query = user_query
        defaults_instruction = ""  # ✅ Initialize to prevent UnboundLocalError
        
        if need_value_fields:
            defaults_list = ", ".join(need_value_fields)
            
            # Dynamic Default Logic
            import datetime
            today = datetime.date.today()
            
            # Helper to evaluate default string expressions like "Today + 7 days"
            def evaluate_default(val_str):
                try:
                    val_lower = str(val_str).lower()
                    if "today" in val_lower:
                        parts = val_lower.split("+")
                        base = today
                        days_add = 0
                        if len(parts) > 1 and "day" in parts[1]:
                            import re
                            nums = re.findall(r'\d+', parts[1])
                            if nums:
                                days_add = int(nums[0])
                        
                        return str(base + datetime.timedelta(days=days_add))
                    
                    if "startdate" in val_lower:
                        # Cannot evaluate dependent fields easily here without complicated parsing
                        # But we can pass the instruction to the LLM
                        return val_str 
                        
                    return val_str
                except:
                    return val_str

            defaults_instruction = f"""
\n\n⚠️ MANDATORY SCHEMA DEFAULTS - "NeedValue" Fields:
The following fields are marked as Recommended in the schema: [{defaults_list}].

🔴 CRITICAL: You MUST include these default values in your JSON output if user didn't specify otherwise:
"""
            # Generic Loop for Defaults
            # Safeguard: Ensure map exists (it should from prior logic)
            local_defaults_map = locals().get('default_value_map', {})
            
            for field, raw_default in local_defaults_map.items():
                evaluated_default = evaluate_default(raw_default)
                defaults_instruction += f"""
   - {field}: REQUIRED - Use '{evaluated_default}' if user didn't specify.
     Example: {{"{field}": "{evaluated_default}"}}
"""
            
            # Special Logic for Campaign Member Status Dependency
            if "CampaignMember" in objects_to_check:
                 defaults_instruction += f"""
🔴 CAMPAIGN MEMBER RULE:
   - EXECUTION ORDER IS CRITICAL:
     1. Create 'Campaign' record (if new).
     2. Create 'CampaignMemberStatus' record (linked to Campaign).
     3. Create 'CampaignMember' record (linked to Campaign).

   - CASE 1: If creating a NEW Campaign (Id not known yet):
     * The Campaign doesn't exist yet, so we CANNOT query for its status.
     * We MUST assume our custom 'Draft' status is missing.
     * ACTION: Schedule Creation of 'CampaignMemberStatus' as Step 2.
       - Use Placeholder for ID: "{{{{campaign.Id}}}}"
       - Set "IsDefault": true
   - CASE 2: If adding to an EXISTING Campaign (Id is known):
     * First, RUN A CHECK (SOQL): SELECT Id FROM CampaignMemberStatus WHERE CampaignId='...' AND Label='Draft'
     * If NO result found, THEN Schedule Creation as Step 1 (before Member).

   - ACTION (Create Status):
     Object: CampaignMemberStatus
     Fields: {{
       "CampaignId": "{{{{campaign.Id}}}}", 
       "Label": "Draft",
       "IsDefault": true,
       "HasResponded": false,
       "SortOrder": 3
     }}
"""

            # 🧠 POST-EMAIL UPDATE Injected Rule
            if locals().get("email_sent_success", False):
                 defaults_instruction += """
🔴 POST-EMAIL UPDATE RULE (CRITICAL OVERRIDE):
   - STATUS: Emails have ALREADY been successfully sent via Brevo.
   - 🛑 STOP: Do NOT try to "prepare" contacts or "send" emails again.
   - 🎯 YOUR ONLY GOAL: Update the 'Status' of the CampaignMember records to 'Sent'.
   
   - EXECUTION STEPS:
     1. Search for **CampaignMember** records (NOT Contacts) for the campaign.
        - Query: SELECT Id FROM CampaignMember WHERE CampaignId = '...' AND Status != 'Sent'
     2. Update these records to Status='Sent'.
   
   - EXAMPLE ACTION (Step 1):
     {
       "tool": "run_dynamic_soql",
       "store_as": "members_to_update",
       "arguments": {"query": "SELECT Id FROM CampaignMember WHERE CampaignId = '{{{{campaign.Id}}}}'"}
     }
     
   - EXAMPLE ACTION (Step 2 - Next Iteration):
      {
       "tool": "upsert_salesforce_record",
       "arguments": {
         "object_name": "CampaignMember",
         "record_id": "{{{{item.Id}}}}",
         "fields": {"Status": "Sent"}
       }
     }
"""

            defaults_instruction += f"""

EXAMPLE - Creating a Campaign (Proposal):
{{
  "tool": "propose_action",
  "reason": "Preview campaign creation with defaults",
  "arguments": {{
    "object_name": "Campaign",
    "fields": {{
      "Name": "User Provided Name",
      "StartDate": "{evaluate_default('Today + 7 days')}",
      "Status": "Planned"
    }}
  }}
}}

3. **OTHER MISSING VALUES** (For fields like Budget, Revenue, Type, etc.):
   - If the user did not provide a value, **CREATE THE RECORD ANYWAY** without them.
   - Do NOT call 'ask_user' just for missing recommended fields. The system will report them later.
   
4. **CRITICAL REQUIREMENT**:
   - You MUST include ANY defaults listed above in the "fields" object.
   - You MUST generate a 'propose_action' tool call (NOT create_salesforce_record) unless User said "Proceed".
   - If missing field, use "Need Value".
"""
            enhanced_user_query += defaults_instruction
        else:
             defaults_instruction = ""
        
        # 🔑 TEMPLATE SELECTION LOGIC - REMOVED per user request
            
        if session_info:
            enhanced_user_query = f"{user_query}{session_info}" + defaults_instruction
            
        enhanced_user_query += f"\n\n⚠️ IMPORTANT: If the user refers to 'this <object>', 'the <object>', or uses pronouns, use the ID from the session context above."
        
        # 🔍 DEBUG: Log the enhanced query to verify defaults are included
        logging.info(f"📋 Enhanced User Query Length: {len(enhanced_user_query)} chars")
        if "StartDate" in enhanced_user_query:
            logging.info("✅ StartDate default instruction FOUND in enhanced query")
        else:
            logging.warning("❌ StartDate default instruction NOT FOUND in enhanced query")
        
        # Add timeout
        try:
            raw_response = await asyncio.wait_for(
                call_llm(
                    system_prompt=resolved_prompt,
                    user_prompt=enhanced_user_query,  # 🔑 Use enhanced query with session context
                    default_model=model,
                    default_provider=provider,
                    default_temperature=0.0,
                ),
                  timeout=30.0
            )
        except asyncio.TimeoutError:
            logging.error("❌ LLM call timed out after 30 seconds")
            raise
        
        logging.info(f"✅ LLM call completed")
        logging.info(f"🤖 LLM response (raw): {raw_response}")
        # Normalize the response content
        # LangChain's response.content can be str, list, or other types
        if isinstance(raw_response, str):
            content = raw_response.strip()
        elif isinstance(raw_response, list):
            # Sometimes content is a list of content blocks
            content = " ".join(str(block) for block in raw_response).strip()
        else:
            content = str(raw_response).strip()
        
        # Remove markdown code fences if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()
        
        logging.info(f"🤖 Cleaned content: {content}")
        
        # Validate JSON
        try:
            parsed = json.loads(content)
            logging.info(f"✅ Successfully parsed JSON: {parsed}")
            
            return content
            
        except json.JSONDecodeError as e:
            logging.error(f"❌ Invalid JSON from LLM: {e}")
            logging.error(f"Content that failed to parse: {content}")
            return json.dumps({
                "type": "error",
                "message": "Failed to generate valid JSON response",
                "uiType": "ErrorMessage"
            })
    
    except Exception as e:
        logging.error(f"❌ Error generating response: {e}", exc_info=True)
        return json.dumps({
            "type": "error",
            "message": f"LLM error: {str(e)}",
            "uiType": "ErrorMessage"
        })

async def generate_all_toolinput(
    query: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main generate tool function for MCP server generate input for all the other salesforce tools need to be the inital tool
    """
    try:
        # Ensure SF connection (happens at runtime, not import)
        if not ensure_sf_connected():
            return {
                "json_response": json.dumps({
                    "type": "error",
                    "message": "Salesforce connection failed",
                    "uiType": "ErrorMessage"
                }),
                "context": context
            }
        
        logging.info(f"Generate tool called with query: {query}")
        logging.info(f"Generate tool called with context: {context}")
        # Extract context object if available
        context_object = None
        if context and isinstance(context, dict):
            context_object = context.get("object") or context.get("Object")
        # Find relevant objects and fields
        selected_object, relevant_fields = find_relevant_objects_and_fields(
            query,
            context_object
        )
        
        if not selected_object:
            return {
                "json_response": json.dumps({
                    "type": "unsupported",
                    "reason": "Could not identify relevant Salesforce object",
                    "summary": "Unable to process this request"
                }),
                "context": context
            }
        
        # Generate structured response
        response_content = await generate_structured_response(
            query,
            selected_object,
            relevant_fields,
            context
        )
        
        return {
            "json_response": response_content
        }
    
    except Exception as e:
        logging.error(f"Error in generate_query: {e}")
        return {
            "json_response": json.dumps({
                "type": "error",
                "message": f"Generate tool error: {str(e)}",
                "uiType": "ErrorMessage"
            }),
            "context": context
        }