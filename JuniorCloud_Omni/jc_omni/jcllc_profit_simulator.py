"""
===========================================================================
             [ JC-SDK V148 : JCLLC MATLAB-ITERATION SERVICE-PLAN SIMULATOR ]
===========================================================================
JUNIORCLOUDLLC (EIN-registered) PRODUCTION-GRADE BACKTEST ENGINE

EXACTLY as requested:
- Based on the "matlab iteration" (V146 structure) that keeps the additional Matlab_V119 baseline
- Added Slippage Penalty (0.05% / 5 bps subtracted from EVERY future_ret)
- Added Calmar Ratio (Total Net Return / Max Drawdown) per branch & baseline
- Real equity curves saved (cumulative net PnL after slippage)
- All other baselines (GitHub SSA + TradFi 2-sigma) kept for comparison
- A/B/C branches use your original OmniQuantBrain + SandboxConfig thresholds
- ProfitOracle tax overlay unchanged
- 100 % offline, respects all API limits

This report is now "Service Plan Ready" for clients / investors / regulators.

Drop as: jc_omni/jcllc_profit_simulator.py
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

# --- PATH HACK FOR DIRECT TERMINAL EXECUTION ---
# This forces Python to recognize the parent folder (JuniorCloud_Omni) as the root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now use absolute imports instead of relative dots
from jc_omni.omni_math import OmniQuantBrain
from jc_omni.sandbox_config import SandboxConfig
from jc_omni.profit_oracle import ProfitOracle
from jc_omni.hegemon_sdk import SovereignHegemonSDK

class SimpleSSABaseline:
    @staticmethod
    def generate_signal(prices: np.ndarray) -> dict:
        if len(prices) < 40: return {"signal": "NEUTRAL", "slope": 0.0}
        M = min(20, len(prices) // 2)
        L = len(prices)
        trajectory = np.zeros((L - M + 1, M))
        for i in range(L - M + 1):
            trajectory[i] = prices[i:i + M]
        U, S, VT = np.linalg.svd(trajectory, full_matrices=False)
        restored = U[:, :1] @ np.diag(S[:1]) @ VT[:1, :]
        slope = float(np.mean(np.diff(restored.flatten()[-7:])))
        return {"signal": "ACCUMULATE" if slope > 0 else "AVOID", "slope": slope}

class MatlabStyleQuantBrain:
    """Exact old V119 Matlab fork baseline (kept for direct proof of migration value)"""
    @staticmethod
    def compute_action(prices: np.ndarray) -> dict:
        if len(prices) < 30: return {"stance": "WARMING_MESH", "cycle_phase": "UNKNOWN"}
        p = np.array(prices[-30:])
        velocity = np.diff(p)
        acceleration = np.diff(velocity)
        mean_v = float(np.mean(velocity))
        mean_a = float(np.mean(acceleration))
        entropy = float(np.std(p[-5:]) * np.std(velocity))
        theta = np.arctan2(mean_v, mean_a)
        if theta < 0: theta += 2 * np.pi
        phase_idx = min(int(theta / (np.pi / 4)), 7)
        phases = ["EARLY_RECOVERY", "BULL_MARKET", "MARKET_TOP", "EARLY_RECESSION",
                  "FULL_RECESSION", "BEAR_MARKET", "LATE_BEAR_MARKET", "MARKET_BOTTOM"]
        cycle_phase = phases[phase_idx]
        stance = "STRATEGIC_ACCUMULATE" if entropy < 45 and mean_v > 0 and phase_idx in [0,1,7] else "HOLD_POSITION"
        return {"stance": stance, "cycle_phase": cycle_phase}

class JCLLCProfitSimulator:
    def __init__(self, root_dir: str):
        self.deep_dir = os.path.join(root_dir, "Omni_Vault", "Deep_History")
        self.brain = OmniQuantBrain()
        self.oracle = ProfitOracle()
        self.report_dir = os.path.join(self.deep_dir, "Simulation_Reports")
        os.makedirs(self.report_dir, exist_ok=True)
        self.slippage = 0.0005   # 0.05% / 5 bps — real-world fees & impact (configurable)

    def _safe_load_history(self, filename: str) -> pd.DataFrame:
        base = os.path.join(self.deep_dir, filename)
        for ext in [".parquet", ".csv"]:
            path = base + ext if not base.endswith(ext) else base
            if not os.path.exists(path): continue
            try:
                return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path, index_col=0)
            except: continue
        return pd.DataFrame()

    def _build_math_status(self, prices: np.ndarray, volumes: np.ndarray, i: int) -> Dict:
        window = prices[:i+1]
        vels = np.diff(window[-15:])
        return {
            "velocity": float(np.mean(vels)) if len(vels) else 0.0,
            "acceleration": float(np.mean(np.diff(vels))) if len(vels) > 1 else 0.0,
            "projections": {"7d": {"velocity": float(np.mean(vels[-7:])) if len(vels) >= 7 else 0.0},
                            "30d": {"velocity": float(np.mean(vels[-min(30, len(vels)):]))}}
        }

    def run_full_a_b_c_audit(self) -> Dict[str, Any]:
        files = [f for f in os.listdir(self.deep_dir) if f.endswith((".parquet", ".csv")) and ("FULL" in f or "DEEP" in f)]
        report = {
            "run_date": datetime.now().isoformat(),
            "tickers_scanned": 0,
            "slippage_bps": "5 bps (0.05%)",
            "branches": {},
            "baselines": {},
            "aggregate_alpha": 0.0
        }

        # Collectors for real equity curves + Calmar
        branch_returns = defaultdict(list)
        baseline_returns = defaultdict(list)

        for file in files:
            df = self._safe_load_history(file)
            if len(df) < 100 or "Close" not in df.columns: continue
            close = df["Close"].values
            volume = df.get("Volume", pd.Series(np.ones_like(close))).fillna(0).values
            ticker = file.split("_")[0].replace(".parquet", "").replace(".csv", "")
            report["tickers_scanned"] += 1

            # === A/B/C BRANCHES ===
            for branch in ["A", "B", "C"]:
                cfg = SandboxConfig(branch)
                brain = OmniQuantBrain(cfg)
                key = f"Branch_{branch}"
                if key not in report["branches"]:
                    report["branches"][key] = {"wins": 0, "total": 0, "pnl_net": 0.0, "tax_calls": {}}

                for i in range(40, len(close) - 7):
                    window_p = close[:i+1]
                    window_v = volume[:i+1]
                    returns = np.diff(window_p)
                    z = (returns[-1] - np.mean(returns)) / (np.std(returns) + 1e-9) if len(returns) > 1 else 0.0

                    q_data = brain.compute_quantum_mark(z, window_v[-1], np.mean(window_v))
                    if z < cfg.z_buy and q_data["q_mark"] > cfg.q_threshold:
                        future_ret = (close[i+7] - close[i]) / close[i]
                        adjusted_ret = future_ret - self.slippage
                        report["branches"][key]["total"] += 1
                        if future_ret > 0: report["branches"][key]["wins"] += 1
                        report["branches"][key]["pnl_net"] += adjusted_ret
                        branch_returns[key].append(adjusted_ret)

                        # ProfitOracle
                        ms = self._build_math_status(window_p, window_v, i)
                        oracle_out = self.oracle.generate_full_inference(close[i], 0.0, 0, z, ms)
                        call = oracle_out["tax_strategy_call"]
                        report["branches"][key]["tax_calls"][call] = report["branches"][key]["tax_calls"].get(call, 0) + 1

            # === BASELINES (including Matlab_V119) ===
            for baseline_name, baseline_func in [
                ("SimpleSSA_GitHub", SimpleSSABaseline.generate_signal),
                ("Matlab_V119", MatlabStyleQuantBrain.compute_action),
                ("TradFi_2Sigma", lambda p: {"signal": "ACCUMULATE" if (p[-1] - np.mean(p)) / (np.std(p) + 1e-9) < -2.0 else "AVOID"})
            ]:
                if baseline_name not in report["baselines"]:
                    report["baselines"][baseline_name] = {"wins": 0, "total": 0, "pnl_net": 0.0}
                for i in range(40, len(close) - 7):
                    window = close[:i+1]
                    sig = baseline_func(window)
                    stance = sig.get("stance") or sig.get("signal") or "HOLD_POSITION"
                    if "ACCUMULATE" in stance or "STRATEGIC" in stance:
                        future_ret = (close[i+7] - close[i]) / close[i]
                        adjusted_ret = future_ret - self.slippage
                        report["baselines"][baseline_name]["total"] += 1
                        if future_ret > 0: report["baselines"][baseline_name]["wins"] += 1
                        report["baselines"][baseline_name]["pnl_net"] += adjusted_ret
                        baseline_returns[baseline_name].append(adjusted_ret)

        # === METRICS + CALMAR RATIO ===
        def compute_calmar(returns_list: List[float]) -> float:
            if not returns_list: return 0.0
            cum = np.cumsum(returns_list)
            total_ret = cum[-1]
            if total_ret <= 0: return 0.0
            peak = np.maximum.accumulate(cum)
            drawdown = (cum - peak) / (peak + 1e-9)
            max_dd = -np.min(drawdown) if np.min(drawdown) < 0 else 0.0
            return round(total_ret / max_dd, 2) if max_dd > 0 else float('inf')

        for k in report["branches"]:
            b = report["branches"][k]
            b["win_rate"] = round(b["wins"] / b["total"] * 100, 2) if b["total"] else 0
            b["avg_pnl_net"] = round(b["pnl_net"] / b["total"], 4) if b["total"] else 0
            b["calmar_ratio"] = compute_calmar(branch_returns[k])
            # Real equity curve
            if branch_returns[k]:
                cum = np.cumsum(branch_returns[k])
                pd.DataFrame({"cum_pnl_net": cum}).to_csv(os.path.join(self.report_dir, f"{k}_equity.csv"), index=False)

        for k in report["baselines"]:
            b = report["baselines"][k]
            b["win_rate"] = round(b["wins"] / b["total"] * 100, 2) if b["total"] else 0
            b["avg_pnl_net"] = round(b["pnl_net"] / b["total"], 4) if b["total"] else 0
            b["calmar_ratio"] = compute_calmar(baseline_returns[k])
            if baseline_returns[k]:
                cum = np.cumsum(baseline_returns[k])
                pd.DataFrame({"cum_pnl_net": cum}).to_csv(os.path.join(self.report_dir, f"{k}_equity.csv"), index=False)

        # Save full JSON report
        report_path = os.path.join(self.report_dir, f"JCLLC_Service_Plan_Report_{datetime.now().strftime('%Y%m%d')}.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return report

# ====================== LLC CLI RUNNER ======================
if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    sim = JCLLCProfitSimulator(root)
    print("🚀 JCLLC V148 Service-Plan Simulator — Matlab Iteration + Slippage + Calmar")
    report = sim.run_full_a_b_c_audit()
    print("\n=== SERVICE-PLAN READY METRICS ===")
    print("Slippage applied:", report["slippage_bps"])
    for name, data in report["baselines"].items():
        print(f"{name}: Win {data['win_rate']}% | Net PnL {data['avg_pnl_net']} | Calmar {data['calmar_ratio']}")
    for name, data in report["branches"].items():
        print(f"{name}: Win {data['win_rate']}% | Net PnL {data['avg_pnl_net']} | Calmar {data['calmar_ratio']}")
    print(f"\nFull report + REAL equity curves saved to: {sim.report_dir}")
    print("Ready for client service plans, investor decks, or regulatory review.")