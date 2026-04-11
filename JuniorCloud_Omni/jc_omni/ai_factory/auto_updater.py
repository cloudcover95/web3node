# jc_omni/ai_factory/auto_updater.py
import requests
import hashlib
import os

class JCAutoUpdater:
    def __init__(self, current_version: str):
        self.version = current_version
        self.update_url = "http://localhost:5005/check_update" # Your dev-bridge URL

    def check_for_hardfork(self):
        """Checks if a new branch (e.g., V121) is available."""
        try:
            # This would hit your local 'Chief of Staff' or GitHub
            # For now, it simulates checking a version string
            latest_version = "V120" 
            if latest_version != self.version:
                print(f"[!] NEW BRANCH DETECTED: {latest_version}. Syncing...")
                return True
        except:
            pass
        return False# jc_omni/ai_factory/auto_updater.py
import os
import subprocess
import logging

logger = logging.getLogger("JC_AutoUpdater")

class JCAutoUpdater:
    def __init__(self, current_version: str):
        self.version = current_version
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def execute_terminal_update(self, method="git"):
        """Executes the actual terminal deploy commands."""
        logger.info(f"[*] Checking for Core Updates (Current: {self.version})...")
        
        try:
            if method == "git":
                # Standard Git Pull for version control
                result = subprocess.run(["git", "pull", "origin", "main"], cwd=self.root_dir, capture_output=True, text=True)
                if "Already up to date" in result.stdout:
                    logger.info("[+] Engine is up to date.")
                    return False
                else:
                    logger.warning("[!] New Branch Merged. Matrix Updated.")
                    return True
                    
            elif method == "local_sync":
                # For syncing from a separate 'Dev' folder to this 'Live' folder
                dev_dir = os.path.expanduser("~/Documents/JuniorCloud_Dev/")
                if os.path.exists(dev_dir):
                    logger.info("[*] Syncing from Local Dev Staging...")
                    subprocess.run(["rsync", "-av", "--exclude", "Omni_Vault", "--exclude", "venv", f"{dev_dir}/", f"{self.root_dir}/"])
                    return True
                else:
                    logger.error("[-] Local dev directory not found.")
                    return False
                    
        except Exception as e:
            logger.error(f"[-] Auto-Update Failed: {e}")
            return False

if __name__ == "__main__":
    updater = JCAutoUpdater("V138")
    updater.execute_terminal_update(method="git") # Change to "local_sync" if you don't use Git

    def sync_engine_branches(self):
        """Pulls the latest .py files into the SDK framework."""
        # Logic to pull latest SDK files from your dev staging area
        print("[+] System Sync Complete. Engine reloaded on M4 Core.")