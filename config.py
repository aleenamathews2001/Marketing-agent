"""
Configuration management for Salesforce MCP Server
"""
# import sys
# from pathlib import Path

# # Add parent directory to path
# parent_dir = Path(__file__).parent.parent
# sys.path.insert(0, str(parent_dir))

# from vault_utils import read_secret

# # Load Brevo secrets from Vault
# # sf_secrets = read_secret("salesforce")
# marketing_org_secrets = read_secret("salesforce_crud_org")
# prompt_org_secrets = read_secret("salesforce_prompt_org")

# CONFIG = {
     

#     # Pull from Vault instead of .env
#     "SALESFORCE_USERNAME": marketing_org_secrets.get("SALESFORCE_USERNAME", ""),
#     "SALESFORCE_PASSWORD": marketing_org_secrets.get("SALESFORCE_PASSWORD", ""),
#     "SALESFORCE_INSTANCE_URL":marketing_org_secrets.get("SALESFORCE_INSTANCE_URL"),
#     "SALESFORCE_SECURITY_TOKEN": marketing_org_secrets.get("SALESFORCE_SECURITY_TOKEN", ""),
#     "SALESFORCE_DOMAIN": marketing_org_secrets.get("SALESFORCE_DOMAIN", "")
# }


from vault_utils import read_secret

# Load both org secrets only once
ORG_SECRETS = {
    "marketing": read_secret("marketing_salesforce_org"),
    "agent": read_secret("agent_salesforce_org"),
}

def get_salesforce_config(org_type: str) -> dict:
    """
    Returns the Salesforce credentials for the given org type.

    """
    if org_type not in ORG_SECRETS:
        raise ValueError(f"Unknown org_type: {org_type}. Use 'marketing' or 'prompt'.")

    secrets = ORG_SECRETS[org_type]

    return {
        "SALESFORCE_USERNAME": secrets.get("SALESFORCE_USERNAME", ""),
        "SALESFORCE_PASSWORD": secrets.get("SALESFORCE_PASSWORD", ""),
        "SALESFORCE_SECURITY_TOKEN": secrets.get("SALESFORCE_SECURITY_TOKEN", ""),
        "SALESFORCE_INSTANCE_URL": secrets.get("SALESFORCE_INSTANCE_URL", ""),
        "SALESFORCE_DOMAIN": secrets.get("SALESFORCE_DOMAIN", "login")
    }
