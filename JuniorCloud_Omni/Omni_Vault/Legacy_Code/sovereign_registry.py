"""
===========================================================================
               [ JC-SDK V135 : SOVEREIGN REGISTRY & LEDGER ]
===========================================================================
© 2026 JuniorCloud LLC™. All Rights Reserved.
Unified SQLite Ledger, Alpha-Decay Auditor, and Active Ticker Manifest.
===========================================================================
"""
import sqlite3
import pandas as pd
import logging
import os
import json
import time

logger = logging.getLogger("SovereignRegistry")

class SovereignRegistry:
    def __init__(self, vault_dir="Omni_Vault", db_name="hegemon_core.db"):
        self.vault = os.path.abspath(vault_dir)
        self.db_path = os.path.join(self.vault, db_name)
        self.manifest_path = os.path.join(self.vault, "active_manifest.json")
        
        os.makedirs(self.vault, exist_ok=True)
        self.active_tickers = set()
        
        self._init_schemas()
        self._load_manifest()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_schemas(self):
        """Unifies the discovery registry and inference ledger into one DB."""
        conn = self._get_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inference_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                stance TEXT,
                cycle_phase TEXT,
                svd_deviation REAL,
                splash_impact REAL,
                system_entropy REAL,
                is_anomaly BOOLEAN DEFAULT 0
            )
        ''')
        # Replaces the Flask /update_matrix SQLite table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS active_matrix (
                ticker TEXT PRIMARY KEY,
                data TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def _load_manifest(self):
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, 'r') as f:
                self.active_tickers = set(json.load(f).get("tickers", []))

    def update_matrix_state(self, ticker: str, payload: dict):
        """Replaces the HTTP POST. Writes directly to UMA shared DB."""
        self.active_tickers.add(ticker)
        with open(self.manifest_path, 'w') as f:
            json.dump({"tickers": list(self.active_tickers)}, f)
            
        conn = self._get_connection()
        # 1. Update live dashboard state
        conn.execute("INSERT OR REPLACE INTO active_matrix (ticker, data, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
                     (ticker, json.dumps(payload)))
        
        # 2. Append to deep historical ledger
        is_anomaly = payload.get('svd_deviation', 0) > 1.0 or payload.get('system_entropy', 0) > 40.0
        conn.execute('''
            INSERT INTO inference_ledger 
            (ticker, stance, cycle_phase, svd_deviation, splash_impact, system_entropy, is_anomaly)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ticker, payload.get('stance', 'HOLD'), payload.get('cycle_phase', 'UNKNOWN'),
              payload.get('svd_deviation', 0), payload.get('splash_impact', 0), 
              payload.get('system_entropy', 0), is_anomaly))
        conn.commit()
        conn.close()

    def execute_entropy_scrub(self, retention_days=7):
        """The built-in Packer: Cleans up orphaned CSVs and DB bloat."""
        logger.info("[!] Executing Entropy Scrub on Data Lake...")
        conn = self._get_connection()
        # Scrub old non-anomalous ledger entries
        conn.execute(f"DELETE FROM inference_ledger WHERE is_anomaly = 0 AND timestamp <= date('now', '-{retention_days} day')")
        conn.commit()
        conn.close()