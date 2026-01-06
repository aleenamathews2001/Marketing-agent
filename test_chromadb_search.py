import sys
sys.path.insert(0, r"c:\Users\ALEENA\OneDrive\Desktop\backup 29 dec 2025(campaignmemberstatus ,email sending)\Marketing agent")

from mcp_module.Salesforcemcp.chromadbutils import chroma_manager

# Test: Search for "active" or "currently working" in Contact fields
print("🔍 Testing ChromaDB field search for Contact object...\n")

# Search for fields related to "active contacts"
results = chroma_manager.search_fields("Contact", "active currently working employment", top_k=5)

print(f"Found {len(results)} fields:\n")
for i, field in enumerate(results, 1):
    print(f"{i}. Field: {field['field_name']}")
    print(f"   Description: {field['description'][:200]}...")
    print(f"   Distance: {field['distance']}\n")

# Also check if Start_Date__c and End_Date__c are in the database
print("\n" + "="*80)
print("🔍 Searching specifically for Start_Date__c and End_Date__c...\n")

start_date_results = chroma_manager.search_fields("Contact", "Start_Date__c employment start", top_k=3)
for field in start_date_results:
    if field['field_name'] == 'Start_Date__c':
        print(f"✅ Found Start_Date__c")
        print(f"   Description: {field['description']}\n")

end_date_results = chroma_manager.search_fields("Contact", "End_Date__c employment end", top_k=3)
for field in end_date_results:
    if field['field_name'] == 'End_Date__c':
        print(f"✅ Found End_Date__c")
        print(f"   Description: {field['description']}\n")
