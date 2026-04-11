# OVERWRITE jc_omni/train_agent.py
"""
===========================================================================
             [ JC-SDK V141 : TOPOLOGICAL AGENT TRAINER ]
===========================================================================
"""
import os
import sqlite3
import pandas as pd
from stable_baselines3 import PPO
from jc_omni.r1_environment import OmniSovereignEnv

def start_training():
    print("====================================================")
    print(" 🧠 JUNIORCLOUD V141 | OPEN-SOURCE WEB3 NODE")
    print("      Architecture: Relative Topological Alpha")
    print("====================================================\n")
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(root_dir, "..", "Omni_Vault", "hegemon_core.db")
    model_path = os.path.join(root_dir, "..", "Omni_Vault", "sovereign_ppo_v141.zip")
    
    if not os.path.exists(db_path):
        print(f"[!] Critical Error: {db_path} not found. Run M4 Node first.")
        return

    print("[*] Siphoning Matrix from inference_ledger...")
    conn = sqlite3.connect(db_path)
    
    # Left Join inference and performance audits. 
    # Use COALESCE to gracefully handle missing columns if testing legacy DB files
    query = """
        SELECT 
            i.ticker, i.timestamp, i.cycle_phase, i.system_entropy, i.agent_edge, 
            i.svd_deviation, 
            COALESCE(i.topological_signature, 'OAM-0000') as topological_signature, 
            COALESCE(i.void_gravity, 0.0) as void_gravity, 
            COALESCE(i.relative_trajectory, 0.0) as relative_trajectory,
            i.viz_x, i.viz_y,
            p.spot_price
        FROM inference_ledger i
        LEFT JOIN performance_audit p ON i.ticker = p.ticker AND ABS(STRFTIME('%s', i.timestamp) - STRFTIME('%s', p.timestamp)) < 60
        ORDER BY i.timestamp ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty or len(df) < 50:
        print(f"[!] Insufficient Data: Found {len(df)} points. Need 100+ to collapse the manifold.")
        return

    print("[*] Encoding 48-Dimensional Phase Levers...")
    phase_map = {
        "MARKET_BOTTOM": 0, "EARLY_RECOVERY": 1, "BULL_MARKET": 2, 
        "MARKET_TOP": 3, "EARLY_RECESSION": 4, "FULL_RECESSION": 5, 
        "BEAR_MARKET": 6, "LATE_BEAR_MARKET": 7
    }
    df['phase_encoded'] = df['cycle_phase'].map(phase_map).fillna(0)
    df['spot_price'] = df['spot_price'].ffill().fillna(1.0)
    df['price_norm'] = df['spot_price'] / df['spot_price'].iloc[0]

    print(f"[*] Initializing V141 Environment with {len(df)} active pulses...")
    env = OmniSovereignEnv(df)
    
    model = PPO(
        "MlpPolicy", env, verbose=1, 
        learning_rate=0.0002, n_steps=1024, batch_size=64,
        gamma=0.98, device="cpu" 
    )
    
    print("[*] Collapsing Neural Matrix (Learning Started)...")
    model.learn(total_timesteps=50000)
    
    model.save(model_path)
    print(f"\n[+] V141 Agent weights secured: {model_path}")

if __name__ == "__main__":
    start_training()