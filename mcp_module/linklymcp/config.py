# import os
# from dotenv import load_dotenv

# # Load environment variables from .env file (if present)
# load_dotenv()

# # Configuration constants for Brevo MCP Server
# CONFIG = {
    
#     "LINKLY_API_KEY": os.getenv("LINKLY_API_KEY"),
#     "LINKLY_BASE_URL": os.getenv("LINKLY_BASE_URL", "https://api.linklyhq.com"),
#     "REQUEST_TIMEOUT": int(os.getenv("REQUEST_TIMEOUT", "30000")),
#     "LINKLY_WORKSPACE":os.getenv("LINKLY_WORKSPACE")
# }
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_dir))

from vault_utils import read_secret

# Load Brevo secrets from Vault
linkly_secrets = read_secret("linkly")
 

CONFIG = {
     

    # Pull from Vault instead of .env
    "LINKLY_BASE_URL": linkly_secrets.get("LINKLY_BASE_URL", ""),
    "LINKLY_API_KEY": linkly_secrets.get("LINKLY_API_KEY", ""),
    "LINKLY_WORKSPACE":linkly_secrets.get("LINKLY_WORKSPACE")
 
 
}