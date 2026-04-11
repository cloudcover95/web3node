# jc_omni/juniorcloud_sdk.py
import numpy as np
import pandas as pd
from .omni_math import OmniQuantBrain

class JuniorCloudSDK:
    def __init__(self):
        self.brain = OmniQuantBrain()
        self.horizons = {'1d': 96, '7d': 672, '30d': 2880}

    def execute_inference_pipeline(self, asset_id, historical_data):
        df = pd.DataFrame(historical_data)
        
        # Schema Standardization
        if 'Close' in df.columns and 'price' not in df.columns:
            df = df.rename(columns={'Close': 'price'})
        if 'Volume' in df.columns and 'volume' not in df.columns:
            df = df.rename(columns={'Volume': 'volume'})
            
        if df.empty or 'price' not in df.columns or len(df) < 30: 
            return {"current_status": {}}

        # 1. Base Kinematics (Vectorized)
        prices = df['price'].values
        df['velocity'] = np.gradient(prices)
        df['acceleration'] = np.gradient(df['velocity'].values)
        
        # 2. Market Cap Normalization via RVOL (Relative Volume)
        if 'volume' in df.columns:
            # 30-period rolling mean normalizes the asset's specific size/market cap
            df['rvol'] = df['volume'] / (df['volume'].rolling(window=30).mean() + 1e-9)
            df['rvol'] = df['rvol'].fillna(1.0) # Default to 1 if not enough data
        
        # 3. Multi-Horizon Projections
        projections = {}
        for label, window in self.horizons.items():
            if len(df) >= window:
                projections[label] = {"velocity": float(df['velocity'].tail(window).mean())}

        # 4. Spatial & Topological Matrix
        topo = self.brain.compute_topological_state(prices, df['velocity'].values, df['acceleration'].values)
        
        # 5. SVD Mesh Restoration (10k Density Prep)
        window = min(len(prices), 100) 
        dense_matrix = np.column_stack((
            prices[-window:], 
            df['velocity'].values[-window:], 
            df['acceleration'].values[-window:]
        ))
        svd_res = self.brain.compute_svd_mesh_restoration(dense_matrix)
        
        # 6. Fluid Dynamics (Now passing RVOL)
        fluid = {}
        if 'volume' in df.columns and 'rvol' in df.columns:
            fluid = self.brain.compute_liquidity_splash(
                df['volume'].values, 
                df['velocity'].values,
                df['rvol'].values  # <--- NEW: Passing the Relative Market Impact
            )

        latest = df.iloc[-1]
        
        return {
            "current_status": {
                "velocity": float(latest['velocity']),
                "acceleration": float(latest['acceleration']),
                "projections": projections,
                
                # V134 Spatial & Fluid Extensions
                "theta": topo.get('theta', 0),
                "mesh_fold": topo.get('mesh_fold', 0),
                "gravity_well": svd_res.get('gravity_well', 0),
                "svd_deviation": svd_res.get('structural_deviation', 0),
                "bit_signature": svd_res.get('bit_signature', []),
                "splash_impact": fluid.get('splash_ratio', 0),
                "pool_viscosity": fluid.get('viscosity', 0)
            },
            "full_df": df 
        }