import sys
sys.path.insert(0, r"c:\Users\ALEENA\OneDrive\Desktop\backup 29 dec 2025(campaignmemberstatus ,email sending)\Marketing agent")

from mcp_module.Salesforcemcp.chromadbutils import chroma_manager

# Get the Contact fields collection
collection = chroma_manager.get_or_create_fields_collection("Contact")

# Get all fields for Contact
all_results = collection.get(include=["metadatas"])

print(f"Total Contact fields in ChromaDB: {len(all_results['ids'])}\n")

# Find Start_Date__c and End_Date__c
for i, metadata in enumerate(all_results['metadatas']):
    field_name = metadata.get('field_name', '')
    
    if field_name in ['Start_Date__c', 'End_Date__c']:
        print(f"{'='*80}")
        print(f"Field: {field_name}")
        print(f"Description: {metadata.get('description', 'NO DESCRIPTION')}")
        print(f"{'='*80}\n")
