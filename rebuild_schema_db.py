import sys
import os

# Add the project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mcp_module.Salesforcemcp.chromadbutils import initialize_schema, chroma_manager
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def rebuild():
    logger.info("🚀 Starting Schema DB Rebuild...")
    try:
        # Reset existing
        chroma_manager.reset_collections()
        logger.info("🧹 Collections reset.")
        
        # Force Initialize
        success = initialize_schema(force=True)
        
        if success:
            logger.info("✅ Schema DB Rebuilt Successfully!")
        else:
            logger.error("❌ Schema DB Rebuild Failed.")
            
    except Exception as e:
        logger.error(f"❌ Error: {e}")

if __name__ == "__main__":
    rebuild()
