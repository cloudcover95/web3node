# OVERWRITE jc_omni/hegemon_sdk.py
"""
===========================================================================
             [ JC-SDK V146 : PALANTIR-GRADE OAM ORCHESTRATOR ]
===========================================================================
"""
import torch
import math
import structlog
import hashlib
import numpy as np
from pydantic import BaseModel, Field
from typing import Dict, Any, List

from .omni_math import OmniQuantBrain

try:
    from .topology_engine import SovereignTopologyNode, OAMState
    HAS_TOPOLOGY = True
except ImportError:
    HAS_TOPOLOGY = False

logger = structlog.get_logger()

class KinematicState(BaseModel):
    ticker: str
    prices: List[float]
    volumes: List[float] = Field(default_factory=list)
    sector_velocities: List[float] = Field(default_factory=list)

class SovereignHegemonSDK:
    def __init__(self):
        self.device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
        self.brain = OmniQuantBrain() 
        self.version = "V146_SECURE_VAULT"
        self.topology = SovereignTopologyNode() if HAS_TOPOLOGY else None
        logger.info("hegemon_initialized", device=str(self.device), version=self.version, topology_active=HAS_TOPOLOGY)

    def infer(self, state: KinematicState) -> Dict[str, Any]:
        if len(state.prices) < 30:
            return {"stance": "WARMING", "system_entropy": 0.0}

        try:
            # 1. DATA SCRUBBING
            clean_prices = [0.0 if math.isnan(x) else x for x in state.prices]
            clean_volumes = [1.0 if (math.isnan(x) or x <= 0) else x for x in (state.volumes or [1.0] * len(clean_prices))]
            v_np = np.array(clean_volumes)
            
            p_tensor = torch.tensor(clean_prices, device=self.device, dtype=torch.float32).view(-1, 1)
            velocity = (p_tensor[1:] - p_tensor[:-1]).flatten()
            acceleration = (velocity[1:] - velocity[:-1]).flatten()

            mean_v = float(torch.mean(velocity))
            mean_a = float(torch.mean(acceleration))

            # 2. DELEGATE TO PROPRIETARY VAULT (omni_math.py)
            dense_matrix = self.brain.build_ssa_matrix(clean_prices)
            svd_mesh = self.brain.compute_svd_mesh_restoration(dense_matrix)
            gradient_layer = self.brain.compute_gradient_layer(p_tensor, self.device)
            entropy, cycle_phase, phase_idx = self.brain.compute_entropy_and_phase(p_tensor, velocity, mean_v, mean_a)

            returns = np.diff(clean_prices)
            z_score = float((returns[-1] - np.mean(returns)) / (np.std(returns) + 1e-9)) if len(returns) > 1 else 0.0
            
            q_data = self.brain.compute_quantum_mark(z_score, clean_volumes[-1], np.mean(clean_volumes))
            rvol = (v_np / (np.mean(v_np) + 1e-9)).tolist()
            splash = self.brain.compute_liquidity_splash(clean_volumes, velocity.cpu().numpy().tolist(), rvol)
            topo_kin = self.brain.compute_topological_state(clean_prices, velocity.cpu().numpy().tolist(), acceleration.cpu().numpy().tolist())

            # 3. LAYER 2: TOPOLOGY ENGINE (Optional)
            topo_sig, void_grav, rel_traj = "UNKNOWN", 0.0, 0.0
            if HAS_TOPOLOGY and self.topology:
                oam = OAMState(
                    ticker=state.ticker, prices=clean_prices, volumes=clean_volumes,
                    velocities=velocity.cpu().numpy().tolist() + [0.0],
                    rvol=rvol, sector_velocities=state.sector_velocities
                )
                t_data = self.topology.extract_topological_voids(oam)
                topo_sig = t_data.get("topological_signature", "UNKNOWN")
                void_grav = t_data.get("void_gravity", 0.0)
                rel_traj = t_data.get("relative_trajectory", 0.0)

            # 4. SOVEREIGN ARBITRATOR
            agent_edge = float(torch.sign(velocity[-1]) * (abs(mean_v) / (entropy + 1e-9)))
            confidence = round(100 * (1.0 - svd_mesh.get("structural_deviation", 0.0)), 2)

            stance = "HOLD_POSITION"
            if entropy > 50.0 or void_grav > 0.85 or splash.get("splash_ratio", 0) > 8.0:
                stance = "GLOBAL_CIRCUIT_FREEZE"
            elif (agent_edge > 0.6 and q_data["q_mark"] > 0.75 and phase_idx in [0, 1, 7] and gradient_layer > 0):
                stance = "STRATEGIC_ACCUMULATE"
            elif splash.get("splash_ratio", 0) > 4.0 and q_data["horizon"]:
                stance = "WHALE_ENTRY"

            # 5. ONTOLOGY SERIALIZATION
            results = {
                "ticker": state.ticker,
                "stance": stance,
                "cycle_phase": cycle_phase,
                "spot_price": round(float(p_tensor[-1]), 4),
                "system_entropy": round(entropy, 4),
                "agent_edge": round(agent_edge, 4),
                "viz_x": round(mean_v, 4),
                "viz_y": round(mean_a, 4),
                "robust_z": round(z_score, 4), 
                "topological_signature": topo_sig,
                "void_gravity": round(void_grav, 4),
                "relative_trajectory": round(rel_traj, 4),
                "q_mark": q_data["q_mark"],
                "psi_amplitude": q_data["psi_amplitude"],
                "splash_ratio": round(splash.get("splash_ratio", 0), 4),
                "viscosity": round(splash.get("viscosity", 0), 4),
                "gravity_well": svd_mesh.get("gravity_well", 0),
                "structural_deviation": svd_mesh.get("structural_deviation", 0),
                "mesh_fold": topo_kin.get("mesh_fold", 0),
                "gradient_layer": round(gradient_layer, 4),
                "confidence": confidence,
                "horizon": q_data["horizon"],
                "bit_signature": str(svd_mesh.get("bit_signature", [])) 
            }

            fingerprint = hashlib.sha256(str(results).encode()).hexdigest()[:12]
            results["_metadata"] = {"version": self.version, "hash": fingerprint, "matrix_size": f"{dense_matrix.shape}"}

            return results

        except Exception as e:
            logger.error("inference_failed", ticker=state.ticker, error=str(e))
            return {"stance": f"ERR_V146: {str(e)}", "system_entropy": 0.0}