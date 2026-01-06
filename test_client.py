import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_server():
    """Test the MCP server properly."""
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_module/Brevomcp/brevo_server.py"],
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()
            print("✅ Server initialized\n")
            
            # List tools
            tools = await session.list_tools()
             
            # for tool in tools.tools:
            #     print("\n=== TOOL ===")
            #     print("Name:", tool.name)
            #     print("Description:", tool.description)
            #     print("Schema:", tool.inputSchema)
            # print("🔧 Testing send_batch_emails tool...")
            try:
                result = await session.call_tool( 
                    "send_batch_emails",
                    
                arguments= {
                    "template_id": 3,
                    "sender_email": "aleenamathews2001@gmail.com",
                    "sender_name": " Aleena Mathews",
                    "recipients": [
                        {
                            "email": "aleenamathews2001@gmail.com",
                             "name": "Aleena",
                            "params": {
                                "FirstName": "Aleena",
                   
                            }
                        }]
                }
                )
                
                # result = await session.call_tool( 
                #     "send_batch_emails",
                    
                # arguments= {
                #     "template_id": 3,
                #     "sender_email": " aleenamathews2001@gmail.com",
                #     "sender_name": " Aleena Mathews",
                #     "recipients": [
                #         {
                #             "email": "aleenamathews558@gmail.com",
                #             "name": "Aleena Mathews",
                #             "params": {
                #                 "FirstName": "Aleena",
                                
                #             }
                #         }],
                #         "cc":[
                #         {
                #             "email": "aleenamathews227@gmail.com",
                #             "name": "Aleena Mathews",
                #             "params": {
                #                 "FirstName": "Aleena",
                                
                #             }
                #         },
                #         {
                #             "email": "iamaparnasurendran@gmail.com",
                #             "name": "Aparna Surendran",
                #             "params": {
                #                 "FirstName": "Aparna",
                                 
                #             }
                #         },
                #         {
                #             "email": "mehrinbasheer01@gmail.com",
                #             "name": "Mehrin Basheer",
                #             "params": {
                #                 "FirstName": "Mehrin",
                                 
                #             }
                #         }],
                #         "bcc":[
                #         {
                #             "email": "parvathy9719@gmail.com",
                #             "name": "Parvathy S",
                #             "params": {
                #                 "FirstName": "Parvathy",
                               
                #             }
                #         }
                #     ]
                # }
             
                # )
 

#                 result = await session.call_tool( 
#                     "send_batch_emails",
                    
#                 arguments=  {
#   "sender_email": "aleenamathews2001@gmail.com",
#   "sender_name": "Aleena Mathews",
#   "subject": "This is my default subject line",
#   "html_content": "<!DOCTYPE html><html><body><h1>My First Heading</h1><p>My first paragraph.</p></body></html>",
#   "message_versions": [
#     {
#       "to": [
#         {
#           "email": "aleenamathews558@gmail.com",
#           "name": "Aleena Mathews"
#         } 
#       ]
#     }
#   ]
# }) 
#                 result = await session.call_tool(
#     "track_email_engagement",
#     arguments={
#         "emails": [
#             "parvathy9719@gmail.com"
        
#         ]
        

#     }
# )

#                 result = await session.call_tool(
#     "generate_uniqueurl",
#     arguments={
#         "campaign_id": "CAMP-2025-WINTER",
#         "template_url": 
#             ["https://www.crmantra.com","https://app.linklyhq.com/swaggerui#/"],
        
#         "contacts": [
#             {"email": "aleenamathews558@gmail.com", "name": "Aleena Mathews 1" },
#             {"email": "aleenamathews2001@gmail.com", "name": "Aleena Mathews 2" }
#         ]
#     }
# )
                 
 
                # Track clicks for a specific campaign
#                 result = await session.call_tool(
#     "track_link_clicks",
#     arguments={
#         "campaign_id": "CAMP-2025-WINTER" 
#     }
# )

                # Track clicks for specific links only
                # result = await session.call_tool(
                #     "track_link_clicks",
                #     arguments={
                #         # "campaign_id": "CAMP-2025-AUTUMN",
                #         "link_ids": ["34597997"],
                #         "debug":True
                #     }
                # )

# # Track clicks with country filter
# result = await session.call_tool(
#     "track_link_clicks",
#     arguments={
#         "campaign_id": "CAMP-2025-AUTUMN",
#         "country": "IN",
#         "unique_only": True
#     }
# )
                # Preview what would be deleted (dry run)
 

                # result = await session.call_tool(
                #     "delete_links",
                #     arguments={
                #         "campaign_id": "CAMP-2025-WINTER"
                         
                #     }
                # )
#                 result = await session.call_tool(
#     "run_dynamic_soql",
#     arguments={
#         "query": "SELECT Id, Name FROM Contact LIMIT 5"
#     }
# ) 
#                 result = await session.call_tool(
#     "upsert_salesforce_record",
#     arguments={
#         "object_name": "Account",
        
#         "fields": {
            
#             "Name": "Ajay Testing Account99963",
#             "Phone": "99999999444",
#             "Website": "https://crmantra.com"
#         },
#         "record_id":"",
       
#     }
# )

#                 result = await session.call_tool(
#     "generate_all_toolinput",
#     arguments={
#         #   "query":"delete a account with id 001fo00000BvwycAAB  "
#         # "query":"send an email to all contact in this 701fo00000C9bfmAAB campaign saying hi contactname welcome to the event"
#         "query":"filter out the contact name start with 'A' and assign those contact to this 701fo00000C9bfmAAB campaign",
       
#     }
# )
                print("✅ Tool executed successfully!")
                for content in result.content:
                    print(f"\n{content.text}")            
            except Exception as e:
                print(f"❌ Error calling tool: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_server())


 

