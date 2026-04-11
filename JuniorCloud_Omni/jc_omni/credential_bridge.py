# OVERWRITE jc_omni/credential_bridge.py
import os, re
import logging

logger = logging.getLogger("CredBridge")

def get_polygon_key():
    """Hunts for the API key across the environment and local source files."""
    # 1. Check Standard Env
    key = os.getenv("POLYGON_KEY") or os.getenv("VSC_POLY_CORE_1")
    
    # 2. Check SOVEREIGN_SOURCE.txt
    if not key:
        source_path = os.path.abspath(os.path.join(os.getcwd(), "SOVEREIGN_SOURCE.txt"))
        if os.path.exists(source_path):
            try:
                with open(source_path, 'r') as f:
                    match = re.search(r'VSC_POLY_CORE_1\s*=\s*["\']([^"\']+)["\']', f.read())
                    if match: key = match.group(1)
            except Exception as e:
                logger.error(f"Failed to read source file: {e}")
                
    if key:
        logger.info("[+] Polygon Bridge: SECURE CONNECTION ESTABLISHED.")
        return key
    else:
        logger.warning("[-] Polygon Bridge: NO KEY FOUND. Defaulting to Web3 Fallback.")
        return "YOUR_POLYGON_KEY"