import pandas as pd
import os
from datetime import datetime

class ReportEngine:
    def __init__(self, root_dir):
        self.ledger_path = os.path.join(root_dir, "Omni_Vault", "performance_audit.csv")
        if not os.path.exists(self.ledger_path):
            df = pd.DataFrame(columns=['timestamp', 'branch', 'ticker', 'spot', 'q_mark', 'pnl_7d'])
            df.to_csv(self.ledger_path, index=False)

    def log_inference(self, branch, ticker, spot, q_mark, pnl=0.0):
        df = pd.DataFrame([{
            'timestamp': datetime.now(), 'branch': branch, 
            'ticker': ticker, 'spot': spot, 'q_mark': q_mark, 'pnl_7d': pnl
        }])
        df.to_csv(self.ledger_path, mode='a', header=False, index=False)

    def get_performance_report(self):
        df = pd.read_csv(self.ledger_path, parse_dates=['timestamp'])
        if df.empty: return {}
        
        # Performance Windows
        now = datetime.now()
        windows = {
            "monthly": df[df['timestamp'] > now - pd.Timedelta(days=30)],
            "quarterly": df[df['timestamp'] > now - pd.Timedelta(days=90)],
            "annual": df[df['timestamp'] > now - pd.Timedelta(days=365)]
        }
        
        report = {}
        for key, data in windows.items():
            if not data.empty:
                report[key] = {
                    "avg_q": float(data['q_mark'].mean()),
                    "total_pnl": float(data['pnl_7d'].sum()),
                    "signals": len(data)
                }
        return report
