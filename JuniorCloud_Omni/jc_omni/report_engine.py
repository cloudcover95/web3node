# jc_omni/report_engine.py
import pandas as pd
import os
from datetime import datetime

class ReportEngine:
    def __init__(self, root_dir):
        self.ledger_path = os.path.join(root_dir, "Omni_Vault", "performance_audit.csv")
        self.columns = [
            'timestamp', 'branch', 'ticker', 'spot', 'q_mark', 
            'mesh_fold', 'gravity_well', 'svd_deviation', 'splash_impact', 'pnl_7d'
        ]
        if not os.path.exists(self.ledger_path):
            df = pd.DataFrame(columns=self.columns)
            df.to_csv(self.ledger_path, index=False)

    def log_inference(self, branch, ticker, spot, q_mark, spatial_data, pnl=0.0):
        df = pd.DataFrame([{
            'timestamp': datetime.now(), 
            'branch': branch, 
            'ticker': ticker, 
            'spot': spot, 
            'q_mark': q_mark,
            'mesh_fold': spatial_data.get('mesh_fold', 0),
            'gravity_well': spatial_data.get('gravity_well', 0),
            'svd_deviation': spatial_data.get('svd_deviation', 0),
            'splash_impact': spatial_data.get('splash_impact', 0),
            'pnl_7d': pnl
        }])
        df.to_csv(self.ledger_path, mode='a', header=False, index=False)