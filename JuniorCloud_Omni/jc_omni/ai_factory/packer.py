import os, time, zipfile
from datetime import datetime

class JCPacker:
    def __init__(self, vault_dir: str):
        self.vault = vault_dir
        self.archive_dir = os.path.join(self.vault, "Legacy_Archive")
        os.makedirs(self.archive_dir, exist_ok=True)
        # Protect core system files from being archived or deleted
        self.protected = [
            'hegemon_core.db', 
            'active_manifest.json', 
            'dynamic_blacklist.json', 
            'workspace_snapshot.json'
        ]

    def execute_audit(self):
        print(f"[!] Packer V140: Auditing {self.vault}...")
        for root, _, files in os.walk(self.vault):
            if "Legacy_Archive" in root: continue 
            for file in files:
                if file in self.protected: continue # SAFETY LOCK
                
                file_path = os.path.join(root, file)
                age_days = (time.time() - os.stat(file_path).st_mtime) / 86400
                
                if age_days > 7 or file.endswith(".tmp"):
                    os.remove(file_path)
                elif age_days > 3:
                    self._archive(file_path, file)

    def _archive(self, file_path, file_name):
        archive_path = os.path.join(self.archive_dir, f"{datetime.now().strftime('%Y%m')}_DeepLog.zip")
        with zipfile.ZipFile(archive_path, 'a') as zipf:
            zipf.write(file_path, arcname=file_name)
        os.remove(file_path)