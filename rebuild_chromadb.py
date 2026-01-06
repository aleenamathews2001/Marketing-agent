import json
import sys
import os

# Add the project root to the path
sys.path.insert(0, r"c:\Users\ALEENA\OneDrive\Desktop\backup 29 dec 2025(campaignmemberstatus ,email sending)\Marketing agent")

from mcp_module.Salesforcemcp.chromadbutils import chroma_manager, initialize_schema

print("🔄 Resetting ChromaDB collections...")
chroma_manager.reset_collections()
print("✅ Collections reset successfully\n")

print("🔄 Rebuilding database with updated schema...")
result = initialize_schema(force=True)

if result:
    print("\n✅ Database rebuild completed successfully!")
    print("📊 The LLM will now see the updated field descriptions")
    print("\n📝 Key changes:")
    print("   - Contact.Start_Date__c: Now clearly explains employment start date filtering")
    print("   - Contact.End_Date__c: Now clearly explains employment end date filtering")  
    print("   - CampaignMember.Status: Now clarifies it's for campaign engagement, NOT employment")
else:
    print("\n❌ Database rebuild failed!")
    sys.exit(1)
