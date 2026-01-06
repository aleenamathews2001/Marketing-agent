
from typing import Optional
from simple_salesforce import Salesforce
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(parent_dir))

from config import get_salesforce_config
import sys
import logging
logging.basicConfig( 
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stderr # CRITICAL! 
    ) 
logger = logging.getLogger(__name__)

class SalesforceClient:
    """Handles Salesforce authentication for ANY org (marketing or prompt)."""

    # Class-level cache for singleton instances
    _instances = {}

    def __new__(cls, org_type: str):
        # Singleton pattern: verify if we already have an instance for this org_type
        if org_type in cls._instances:
            return cls._instances[org_type]
        
        instance = super(SalesforceClient, cls).__new__(cls)
        cls._instances[org_type] = instance
        return instance

    def __init__(self, org_type: str):
        # Avoid re-initialization if already set
        if hasattr(self, "sf") and self.sf is not None:
            return
            
        self.sf: Optional[Salesforce] = None
        self.org_type = org_type
        self.config = get_salesforce_config(org_type)

    def connect(self) -> bool:
        """Create a Salesforce session using credentials for selected org."""
        # Check if already connected (session valid?) - simple check for existence
        if self.sf:
            return True

        try:
            username = self.config.get("SALESFORCE_USERNAME")
            password = self.config.get("SALESFORCE_PASSWORD")
            security_token = self.config.get("SALESFORCE_SECURITY_TOKEN")
            domain = self.config.get("SALESFORCE_DOMAIN", "login")
            if not (username and password and security_token):
                print(f"[{self.org_type}] Missing Salesforce credentials!")
                return False

            self.sf = Salesforce(
                username=username,
                password=password,
                security_token=security_token,
                domain=domain
            )
            return True

        except Exception as e:
            logger.exception(f"❌ [{self.org_type}] Salesforce authentication failed: {e}")
            return False
if __name__ == "__main__":
    sf_client = SalesforceClient("agent")
    sf_client.connect()
        
 

