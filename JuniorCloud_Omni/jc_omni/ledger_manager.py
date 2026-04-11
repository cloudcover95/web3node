# jc_omni/ledger_manager.py
import sqlite3
import pandas as pd
import logging
import os
import mlx.core as mx
import torch

device = torch.device("mps")
U_t = torch.tensor(U, device=device)
S_clean_t = torch.diag(torch.tensor(S_clean, device=device))
VT_t = torch.tensor(VT, device=device)

restored = torch.matmul(U_t, torch.matmul(S_clean_t, VT_t))
# Assuming U, S_clean, VT are isolated from the mesh
U_mx = mx.array(U)
S_clean_mx = mx.diag(mx.array(S_clean))
VT_mx = mx.array(VT)

restored = mx.matmul(U_mx, mx.matmul(S_clean_mx, VT_mx))
logger = logging.getLogger("LedgerManager")

class SovereignLedger:
    def __init__(self, db_name="trend_logic_core.db"):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        vault_dir = os.path.abspath(os.path.join(current_dir, '..', 'Omni_Vault'))
        os.makedirs(vault_dir, exist_ok=True)
        self.db_path = os.path.join(vault_dir, db_name)
        self.init_schemas()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_schemas(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Expanded Schema for V134 Spatial Metrics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inference_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                velocity REAL,
                acceleration REAL,
                mesh_fold REAL,
                gravity_well REAL,
                svd_deviation REAL,
                splash_impact REAL,
                is_anomaly BOOLEAN DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

    def save_inferences(self, asset_id: str, payload: dict):
        """Catches the real-time node dict and pushes to SQLite."""
        conn = self._get_connection()
        
        is_anomaly = payload.get('svd_deviation', 0) > 0.15 or payload.get('splash_impact', 0) > 3.0
        
        df = pd.DataFrame([{
            "asset_id": asset_id,
            "velocity": payload.get('velocity', 0.0),
            "acceleration": payload.get('acceleration', 0.0),
            "mesh_fold": payload.get('mesh_fold', 0.0),
            "gravity_well": payload.get('gravity_well', 0.0),
            "svd_deviation": payload.get('svd_deviation', 0.0),
            "splash_impact": payload.get('splash_impact', 0.0),
            "is_anomaly": is_anomaly
        }])
        
        df.to_sql('inference_ledger', conn, if_exists='append', index=False)
        conn.close()