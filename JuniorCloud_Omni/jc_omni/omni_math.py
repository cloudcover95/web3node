# OVERWRITE jc_omni/omni_math.py
"""
===========================================================================
             [ JC-SDK V146 : OMNI QUANT BRAIN (PROPRIETARY VAULT) ]
===========================================================================
All core kinematics, quantum inference, and tensor math must reside here.
"""
import numpy as np
import math
import torch
from scipy.linalg import svd
import warnings
from .sandbox_config import SandboxConfig

warnings.filterwarnings("ignore")

class OmniQuantBrain:
    def __init__(self, config=SandboxConfig("A")):
        self.cfg = config

    # --- 1. THE NEW MACRO MESH LOGIC ---
    def build_ssa_matrix(self, clean_prices: list) -> np.ndarray:
        """Constructs the higher-dimensional trajectory mesh to pierce noise."""
        L = len(clean_prices)
        M = min(40, L // 2)
        if L > M + 10:
            trajectory = np.zeros((L - M + 1, M))
            for i in range(L - M + 1):
                trajectory[i] = clean_prices[i:i + M]
            return trajectory
        return np.column_stack((clean_prices, np.diff(clean_prices, prepend=clean_prices[0])))

    def compute_gradient_layer(self, p_tensor: torch.Tensor, device: torch.device) -> float:
        """Fx[A,b] Explicit Linear Mesh Gradient (Targeted CPU Offload for Apple M4)."""
        L = len(p_tensor)
        
        # 1. Temporarily bounce the tensor to the CPU
        cpu_tensor = p_tensor.cpu()
        cpu_device = torch.device('cpu')
        
        # 2. Build the time matrix explicitly on the CPU
        times = torch.arange(L, device=cpu_device, dtype=torch.float32).view(-1, 1)
        A = torch.cat([times, torch.ones_like(times)], dim=1)
        
        # 3. Execute least-squares natively on the CPU
        # FIX: torch.linalg.lstsq returns a namedtuple of 4 elements.
        lstsq_result = torch.linalg.lstsq(A, cpu_tensor, driver='gels')
        sol = lstsq_result.solution
        
        return float(sol[0][0])

    def compute_entropy_and_phase(self, p_tensor: torch.Tensor, velocity: torch.Tensor, mean_v: float, mean_a: float):
        """Extracts System Entropy and the 8-Phase Cycle State."""
        entropy = float(torch.std(p_tensor[-10:]) * torch.std(velocity))
        theta = math.atan2(mean_v, mean_a)
        if theta < 0: theta += 2 * math.pi
        phases = ["EARLY_RECOVERY", "BULL_MARKET", "MARKET_TOP", "EARLY_RECESSION",
                  "FULL_RECESSION", "BEAR_MARKET", "LATE_BEAR_MARKET", "MARKET_BOTTOM"]
        phase_idx = min(int(theta / (math.pi / 4)), 7)
        return entropy, phases[phase_idx], phase_idx

    # --- 2. EXISTING QUANTUM & FLUID LOGIC ---
    def compute_quantum_mark(self, z_score, current_vol, base_vol):
        psi = (2 * np.pi)**(-0.25) * np.exp(-(z_score**2) / 4.0)
        delta = max(current_vol - base_vol, 0.0)
        a_hat = (delta / max(base_vol, 1e-9)) + (abs(self.cfg.z_buy) * 0.1)
        q_mark = 1.0 - np.exp(-(abs(z_score) * a_hat))
        return {
            "q_mark": round(float(q_mark), 4),
            "psi_amplitude": round(float(psi), 4),
            "horizon": q_mark >= self.cfg.q_threshold
        }

    def compute_topological_state(self, p_array, v_array, a_array):
        mean_v = np.mean(v_array)
        sigma_v = np.std(v_array) + 1e-9
        return {"mesh_fold": sigma_v / (abs(mean_v) + 1e-9)}

    def compute_svd_mesh_restoration(self, dense_matrix):
        try:
            U, S, VT = svd(dense_matrix, full_matrices=False)
            bit_signature = (U[:, 0] > np.median(U[:, 0])).astype(int).tolist()[:8]
            
            S_clean = np.zeros_like(S)
            S_clean[0] = S[0]
            restored = np.dot(U, np.dot(np.diag(S_clean), VT))
            
            deviation = np.linalg.norm(dense_matrix - restored) / (np.linalg.norm(dense_matrix) + 1e-9)
            return {
                "gravity_well": float(S[0] / (np.sum(S) + 1e-9)),
                "structural_deviation": float(deviation),
                "bit_signature": bit_signature
            }
        except Exception: 
            return {"gravity_well": 0.0, "structural_deviation": 0.0, "bit_signature": []}

    def compute_liquidity_splash(self, volumes, velocities, rvol=None):
        if len(volumes) < 5: return {"splash_ratio": 0.0, "viscosity": 0.0}
        impact_energy = volumes[-1] * abs(velocities[-1])
        if rvol is not None and len(rvol) > 0:
            impact_energy *= (rvol[-1] + 1e-9)
        base_viscosity = np.std(volumes[-5:]) / (np.mean(volumes[-5:]) + 1e-9)
        return {
            "splash_ratio": float(impact_energy / (np.mean(volumes) + 1e-9)),
            "viscosity": float(base_viscosity)
        }