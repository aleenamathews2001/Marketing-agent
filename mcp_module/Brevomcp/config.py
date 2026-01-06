# import os
# from dotenv import load_dotenv

# # Load environment variables from .env file (if present)
# load_dotenv()

# # Configuration constants for Brevo MCP Server
# CONFIG = {
#     "DEFAULT_BATCH_SIZE": 100,
#     "MAX_BATCH_SIZE": 1000,
#     "DEFAULT_LIMIT": 50,
#     "MAX_CAMPAIGNS_SEARCH": 1000,
#     "REQUEST_TIMEOUT": 30000,
#     "API_BASE_URL": os.getenv("BREVO_BASE_URL", "https://api.brevo.com/v3"),
#     "BREVO_API_KEY": os.getenv("BREVO_API_KEY", ""),
#     "BREVO_SENDER_EMAIL": os.getenv("BREVO_SENDER_EMAIL", ""),
#     "BREVO_SENDER_NAME": os.getenv("BREVO_SENDER_NAME", ""),
# }
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_dir))

from vault_utils import read_secret

# Load Brevo secrets from Vault
brevo_secrets = read_secret("brevo")
 

CONFIG = {
    "DEFAULT_BATCH_SIZE": 100,
    "MAX_BATCH_SIZE": 1000,
    "DEFAULT_LIMIT": 50,
    "MAX_CAMPAIGNS_SEARCH": 1000,
    "REQUEST_TIMEOUT": 30000, 

    # Pull from Vault instead of .env
    "API_BASE_URL": brevo_secrets.get("BREVO_BASE_URL", ""),
    "BREVO_API_KEY": brevo_secrets.get("BREVO_API_KEY", "")
     
 
}