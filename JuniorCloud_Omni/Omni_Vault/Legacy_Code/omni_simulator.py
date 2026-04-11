import os
import pandas as pd
import numpy as np
from jc_omni.omni_math import OmniQuantBrain
from jc_omni.juniorcloud_sdk import JuniorCloudSDK

class OmniSimulator:
    def __init__(self, root_dir):
        self.deep_dir = os.path.join(root_dir, "Omni_Vault", "Deep_History")
        self.brain = OmniQuantBrain()
        self.math_engine = JuniorCloudSDK()

    def run_backtest_audit(self):
        files = [f for f in os.listdir(self.deep_dir) if f.endswith(".csv")]
        if not files: return {"scanned": 0, "q_win": 0, "t_win": 0, "alpha": 0}

        q_wins, q_total = 0, 0
        t_wins, t_total = 0, 0

        for file in files:
            try:
                df = pd.read_csv(os.path.join(self.deep_dir, file))
                if len(df) < 50: continue
                
                # Standardize columns
                close = df['Close'].values
                z = df['Robust_Z'].values
                # We define "TradFi Industry Standard" as a 2-Sigma drop (-2.0 Z)
                
                for i in range(20, len(df) - 7):
                    future_p = close[i+7]
                    current_p = close[i]
                    
                    # Model A: Sovereign (Wave Collapse + Accel)
                    if z[i] < -1.2 and self.brain.compute_quantum_mark(z[i], 0.1, 0.05)['q_mark'] > 0.8:
                        q_total += 1
                        if future_p > current_p: q_wins += 1
                    
                    # Model B: TradFi (Raw 2-Sigma Bollinger Drop)
                    if z[i] < -2.0:
                        t_total += 1
                        if future_p > current_p: t_wins += 1
            except: continue

        qw = round((q_wins / q_total * 100), 2) if q_total > 0 else 0
        tw = round((t_wins / t_total * 100), 2) if t_total > 0 else 0
        return {"scanned": len(files), "q_win": qw, "t_win": tw, "alpha": round(qw - tw, 2)}
