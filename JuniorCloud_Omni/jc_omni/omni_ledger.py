# jc_omni/omni_ledger.py
import os, json, datetime
import numpy as np

class OmniLedger:
    def __init__(self, root_dir):
        self.vault = os.path.join(root_dir, "Omni_Vault")
        self.mint_dir = os.path.join(self.vault, "Minted_Artifacts")
        self.deep_dir = os.path.join(self.vault, "Deep_History")
        os.makedirs(self.mint_dir, exist_ok=True)
        os.makedirs(self.deep_dir, exist_ok=True)

    def mint_artifact(self, ticker, price, q_data, oracle_data, spatial_data):
        ts = datetime.datetime.now()
        art_id = f"SOV_{ticker.replace('-','')}_{ts.strftime('%Y%m%d_%H%M%S')}"
        
        metadata = {
            "name": f"Discovery: {ticker}",
            "description": f"Sovereign Kinematics Analysis for {ticker} at ${price}",
            "image": "ipfs://Qm_placeholder_sovereign_orb", 
            "external_url": "https://juniorcloudllc.com",
            "properties": {
                "timestamp": ts.isoformat(),
                "node_version": "V134 Spatial Edition"
            },
            "attributes": [
                {"trait_type": "Asset", "value": ticker},
                {"trait_type": "Spot Price", "value": price},
                {"trait_type": "Quantum Mark", "value": round(q_data.get('q_mark', 0), 4)},
                {"trait_type": "Action Strategy", "value": oracle_data.get('tax_strategy_call', 'WATCHING')},
                
                # The New Spatial Tiers
                {"trait_type": "Mesh Fold", "value": round(spatial_data.get('mesh_fold', 0), 4)},
                {"trait_type": "Gravity Well", "value": round(spatial_data.get('gravity_well', 0), 4)},
                {"trait_type": "Structural Deviation", "value": round(spatial_data.get('svd_deviation', 0), 4)},
                {"trait_type": "Fluid Impact", "value": round(spatial_data.get('splash_impact', 0), 4)}
            ]
        }
        
        path = os.path.join(self.mint_dir, f"{art_id}.json")
        with open(path, 'w') as f:
            json.dump(metadata, f, indent=4)
        return art_id