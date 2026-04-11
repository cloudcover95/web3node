"""
===========================================================================
             [ JC-SDK V138 : OMNI VAULT MANAGER ]
===========================================================================
© 2026 JuniorCloud LLC™. All Rights Reserved.
Replaces: sovereign_registry.py, report_engine.py, omni_ledger.py
===========================================================================
"""
import sqlite3
import pandas as pd
import logging
import os
import json
from datetime import datetime

logger = logging.getLogger("OmniVault")

class OmniVaultManager:
    def __init__(self, root_dir=None):
        if root_dir is None:
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            
        self.vault_dir = os.path.join(root_dir, "Omni_Vault")
        self.db_path = os.path.join(self.vault_dir, "hegemon_core.db")
        self.mint_dir = os.path.join(self.vault_dir, "Minted_Artifacts")
        self.manifest_path = os.path.join(self.vault_dir, "active_manifest.json")
        
        for d in [self.vault_dir, self.mint_dir]:
            os.makedirs(d, exist_ok=True)
            
        self._init_schemas()
        self.active_tickers = self._load_manifest()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_schemas(self):
        """Unified Master Schema for the M4 Data Lake."""
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS inference_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    stance TEXT,
                    cycle_phase TEXT,
                    svd_deviation REAL,
                    bayesian_conf REAL,
                    system_entropy REAL,
                    is_anomaly BOOLEAN
                )
            ''')
            # Table for Performance Reporting (Replaces performance_audit.csv)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS performance_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    spot_price REAL,
                    agent_edge REAL,
                    pnl_7d REAL DEFAULT 0.0
                )
            ''')
            conn.commit()

    def _load_manifest(self):
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r') as f:
                    return set(json.load(f).get("tickers", []))
            except: pass
        return set()

    # --- INFERENCE WRITER ---
    def log_inference(self, ticker: str, payload: dict):
        """Writes the M4 Ontology payload to the core database."""
        self.active_tickers.add(ticker)
        with open(self.manifest_path, 'w') as f:
            json.dump({"tickers": list(self.active_tickers)}, f)
            
        is_anomaly = payload.get('system_entropy', 0) > 45.0
        
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO inference_ledger 
                (ticker, stance, cycle_phase, svd_deviation, bayesian_conf, system_entropy, is_anomaly)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                ticker, 
                payload.get('stance', 'HOLD'), 
                payload.get('cycle_phase', 'UNKNOWN'),
                payload.get('svd_deviation', 0.0), 
                payload.get('bayesian_conf', 0.0), 
                payload.get('system_entropy', 0.0), 
                is_anomaly
            ))
            
            # Log to performance audit for PnL tracking
            if payload.get('spot'):
                conn.execute('''
                    INSERT INTO performance_audit (ticker, spot_price, agent_edge)
                    VALUES (?, ?, ?)
                ''', (ticker, payload.get('spot'), payload.get('agent_edge', 0.0)))
            
            conn.commit()

    # --- ARTIFACT MINTER ---
    def mint_artifact(self, ticker: str, spot: float, payload: dict):
        """Replaces omni_ledger.py minting logic."""
        ts = datetime.now()
        art_id = f"SOV_{ticker.replace('-','')}_{ts.strftime('%Y%m%d_%H%M%S')}"
        
        metadata = {
            "name": f"Hegemon Discovery: {ticker}",
            "description": f"Sovereign Kinematics Analysis for {ticker} at ${spot}",
            "external_url": "https://juniorcloudllc.com",
            "properties": {
                "timestamp": ts.isoformat(),
                "node_version": payload.get("_metadata", {}).get("version", "V138")
            },
            "attributes": [
                {"trait_type": "Phase", "value": payload.get("cycle_phase", "UNKNOWN")},
                {"trait_type": "Entropy (Z)", "value": payload.get("system_entropy", 0.0), "display_type": "number"},
                {"trait_type": "Agent Edge", "value": payload.get("agent_edge", 0.0), "display_type": "number"}
            ]
        }
        
        path = os.path.join(self.mint_dir, f"{art_id}.json")
        with open(path, 'w') as f:
            json.dump(metadata, f, indent=4)
        return art_id

    # --- REPORT ENGINE ---
    def get_performance_report(self):
        """Replaces report_engine.py logic."""
        with self._get_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM performance_audit ORDER BY timestamp DESC LIMIT 1000", conn)
            
        if df.empty: return {"status": "Awaiting Data"}
        
        # Calculate some basic aggregate stats
        best_performer = df.loc[df['pnl_7d'].idxmax()]['ticker'] if not df['pnl_7d'].isna().all() else "N/A"
        return {
            "total_logs": len(df),
            "unique_assets": df['ticker'].nunique(),
            "best_7d_asset": best_performer
        }