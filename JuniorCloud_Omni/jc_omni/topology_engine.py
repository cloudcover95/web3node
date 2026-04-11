# OVERWRITE jc_omni/topology_engine.py
"""
===========================================================================
             [ JC-SDK V141 : OAM TOPOLOGICAL ENGINE ]
===========================================================================
"""
import torch
import numpy as np
import structlog
import hashlib
from pydantic import BaseModel, Field
from typing import Dict, Any, List

from gtda.time_series import TakensEmbedding
from gtda.homology import VietorisRipsPersistence
from gtda.diagrams import PersistenceEntropy, BettiCurve

logger = structlog.get_logger("OAM_Topology")

class OAMState(BaseModel):
    ticker: str
    prices: List[float]
    volumes: List[float]
    velocities: List[float]
    rvol: List[float]
    sector_velocities: List[float] = Field(default_factory=list) # The industry counterpart baseline

class SovereignTopologyNode:
    def __init__(self):
        self.device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
        self.version = "V141_OAM_TDA_CORE"
        self.embedder = TakensEmbedding(time_delay=2, dimension=48)
        self.vr_persistence = VietorisRipsPersistence(homology_dimensions=[0, 1], n_jobs=-1)
        self.entropy_extractor = PersistenceEntropy()
        self.betti_curve = BettiCurve(n_bins=100)

    def extract_topological_voids(self, state: OAMState) -> Dict[str, Any]:
        if len(state.prices) < 50:
            return {"status": "insufficient_manifold_data"}

        try:
            p_tensor = torch.tensor(state.prices, device=self.device, dtype=torch.float32)
            v_tensor = torch.tensor(state.velocities, device=self.device, dtype=torch.float32)
            vol_tensor = torch.tensor(state.volumes, device=self.device, dtype=torch.float32)
            rvol_tensor = torch.tensor(state.rvol, device=self.device, dtype=torch.float32)

            # --- ISOLATE LOCALIZED VOIDS VS INDUSTRY ---
            # If sector data is provided, subtract the industry momentum to isolate true alpha
            if len(state.sector_velocities) == len(state.velocities):
                sec_v_tensor = torch.tensor(state.sector_velocities, device=self.device, dtype=torch.float32)
                v_tensor = v_tensor - sec_v_tensor # Relative Kinematics

            center_of_mass = torch.mean(p_tensor[-30:])
            r_vector = p_tensor - center_of_mass
            p_vector = v_tensor * vol_tensor * (rvol_tensor + 1e-5)

            oam_synthetic = (r_vector * p_vector).cpu().numpy().reshape(1, -1)
            point_cloud = self.embedder.fit_transform(oam_synthetic)
            persistence_diagrams = self.vr_persistence.fit_transform(point_cloud)

            pers_entropy = self.entropy_extractor.fit_transform(persistence_diagrams)[0]
            betti_features = self.betti_curve.fit_transform(persistence_diagrams)[0]

            h0_entropy = float(pers_entropy[0])
            h1_entropy = float(pers_entropy[1]) if len(pers_entropy) > 1 else 0.0
            
            # This density represents the depth of the localized capital vacuum
            void_density = float(np.sum(betti_features[1]))

            alphabet_hash = abs(hash((round(h0_entropy, 3), round(h1_entropy, 3)))) % 17000
            topological_signature = f"OAM-{alphabet_hash:04d}"

            results = {
                "ticker": state.ticker,
                "topological_signature": topological_signature,
                "h0_entropy": round(h0_entropy, 4),      
                "h1_void_entropy": round(h1_entropy, 4), 
                "void_gravity": round(void_density, 4),  
                "relative_trajectory": round(float(p_vector[-1]), 4)
            }
            results["_hash"] = hashlib.sha256(str(results).encode()).hexdigest()[:8]
            return results

        except Exception as e:
            return {"status": "SYS_ERR", "error": str(e)}