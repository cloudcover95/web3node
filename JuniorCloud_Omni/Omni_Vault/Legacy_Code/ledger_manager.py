# /Users/nico/Documents/juniorcloud/web3node/juniorcloud_omni/jc_omni/ledger_manager.py
import sqlite3
import pandas as pd
import logging
import os

logger = logging.getLogger("LedgerManager")

class SovereignLedger:
    def __init__(self, db_name="trend_logic_core.db"):
        # Dynamically find the omni_vault directory relative to this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        vault_dir = os.path.abspath(os.path.join(current_dir, '..', 'omni_vault'))
        
        # Ensure the vault exists
        os.makedirs(vault_dir, exist_ok=True)
        
        self.db_path = os.path.join(vault_dir, db_name)
        self.init_schemas()

    # ... (rest of the class remains exactly the same)

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_schemas(self):
        """Beefed up schema including the new inference tracking."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Original state ledger (simplified for example)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                price REAL NOT NULL
            )
        ''')

        # NEW: Dedicated inference ledger to cache engine outputs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inference_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                std_dev REAL,
                velocity REAL,
                acceleration REAL,
                is_anomaly BOOLEAN DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Ledger schemas verified and initialized.")

    def save_inferences(self, asset_id: str, inference_df: pd.DataFrame):
        """Writes the calculated math outputs into the database."""
        conn = self._get_connection()
        # Drop raw price, keep only inference columns to write to inference_ledger
        write_df = inference_df[['std_dev', 'velocity', 'acceleration']].copy()
        write_df['asset_id'] = asset_id
        
        # Detect simple anomalies (e.g., crazy high acceleration)
        write_df['is_anomaly'] = write_df['acceleration'].abs() > write_df['acceleration'].std() * 3
        
        write_df.to_sql('inference_ledger', conn, if_exists='append', index=False)
        conn.close()
        logger.info(f"Saved {len(write_df)} inference records for {asset_id}.")