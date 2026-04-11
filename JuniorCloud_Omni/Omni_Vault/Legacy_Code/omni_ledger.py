import os, json, datetime
import numpy as np

class OmniLedger:
    def __init__(self, root_dir):
        self.vault = os.path.join(root_dir, "Omni_Vault")
        self.mint_dir = os.path.join(self.vault, "Minted_Artifacts")
        self.deep_dir = os.path.join(self.vault, "Deep_History")
        self.logs_dir = os.path.join(self.vault, "System_Logs")
        for d in [self.mint_dir, self.deep_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)

    def mint_artifact(self, ticker, price, q_data, oracle_data):
        """Mints an ERC-1155 Compliant Metadata Artifact. Append-Only Logic."""
        ts = datetime.datetime.now()
        art_id = f"SOV_{ticker.replace('-','')}_{ts.strftime('%Y%m%d_%H%M%S')}"
        
        # ERC-1155 Strict Standard Metadata Structure
        metadata = {
            "name": f"Discovery: {ticker}",
            "description": f"Sovereign Kinematics Analysis for {ticker} at ${price}",
            "image": "ipfs://Qm_placeholder_sovereign_orb", 
            "external_url": "https://juniorcloudllc.com",
            "properties": {
                "timestamp": ts.isoformat(),
                "node_version": "V125 Unbound Alpha"
            },
            "attributes": [
                {"trait_type": "Asset", "value": ticker},
                {"trait_type": "Spot Price", "value": price, "display_type": "number"},
                {"trait_type": "Quantum Mark", "value": round(q_data.get('q_mark', 0), 4), "display_type": "number"},
                {"trait_type": "Action Strategy", "value": oracle_data.get('tax_strategy_call', 'WATCHING')},
                {"trait_type": "Market Regime", "value": oracle_data.get('short_term_inference', 'STABLE')},
                {"trait_type": "Z-Score", "value": round(q_data.get('z_score', 0), 2), "display_type": "number"},
                {"trait_type": "Fairness (Alpha)", "value": "Sovereign Tier"}
            ]
        }
        
        path = os.path.join(self.mint_dir, f"{art_id}.json")
        with open(path, 'w') as f:
            json.dump(metadata, f, indent=4)
        return art_id

    def save_deep_ledger(self, ticker, df):
        # Always overwrite the deep matrix to maintain the rolling 60d window
        path = os.path.join(self.deep_dir, f"{ticker.replace('-','_')}_DEEP.csv")
        df.to_csv(path)

    def get_daily_mint_count(self):
        try:
            today = datetime.datetime.now().strftime('%Y%m%d')
            return len([f for f in os.listdir(self.mint_dir) if today in f])
        except: return 0

    def get_latest_mint(self):
        try:
            files = [f for f in os.listdir(self.mint_dir) if f.endswith('.json')]
            if not files: return None
            latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(self.mint_dir, x)))
            with open(os.path.join(self.mint_dir, latest_file), 'r') as f:
                data = json.load(f)
                return {
                    "id": latest_file.replace('.json', ''),
                    "asset": data['attributes'][0]['value'],
                    "attributes": data['attributes']
                }
        except: return None