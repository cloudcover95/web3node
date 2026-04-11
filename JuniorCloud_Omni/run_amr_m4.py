# run_amr_m4.py
import os, sys, time, json, asyncio
from aiohttp import web
import pandas as pd
import logging

from jc_omni.omni_hunter import OmniHunter
from jc_omni.omni_data import OmniDataLayer
from jc_omni.juniorcloud_sdk import JuniorCloudSDK
from jc_omni.hegemon_mps import HegemonMPS
from jc_omni.sovereign_registry import SovereignRegistry
from jc_omni.credential_bridge import get_polygon_key

logger = logging.getLogger("M4_AMR_Node")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class SovereignM4Node:
    def __init__(self):
        logger.info("--- JUNIORCLOUD SDK V135 [M4 SOVEREIGN DATA LAKE] ---")
        self.hunter = OmniHunter(poly_key=get_polygon_key())
        self.registry = SovereignRegistry()
        self.data_layer = OmniDataLayer(self.registry.vault)
        self.sdk = JuniorCloudSDK() # Handles V134 Fluid / SVD Topology
        self.hegemon = HegemonMPS() # Handles V119 Apple Silicon Tensors
        
        self.live_state = {"assets": [], "drift": 0.0, "status": "BOOTING"}

    async def _process_ticker(self, ticker: dict):
        """Async inference pipeline for a single asset."""
        sym = ticker['yf']
        history = self.data_layer.fetch_robust_history(sym, ticker.get('cg_id'))
        if not history: return None
        
        df, _ = history
        prices = df['price'].values
        
        # 1. SDK Core (Fluid Dynamics, SVD, Q-Mark)
        sdk_inf = self.sdk.execute_inference_pipeline(sym, df.reset_index())
        ms = sdk_inf.get('current_status', {})
        
        # 2. Hegemon MPS Core (M4 Tensor Math)
        h_inf = self.hegemon.execute_tensor_arbitrator(prices)
        
        # 3. Payload Packing for Snow Globe Dashboard
        payload = {
            "ticker": sym,
            "spot": ticker['price'],
            "stance": h_inf.get('stance', 'UNKNOWN'),
            "cycle_phase": h_inf.get('cycle_phase', 'UNKNOWN'),
            "svd_deviation": ms.get('svd_deviation', 0),
            "splash_impact": ms.get('splash_impact', 0),
            "system_entropy": h_inf.get('system_entropy', 0),
            "viz_x": h_inf.get('viz_x', 0),
            "viz_y": h_inf.get('viz_y', 0),
            "hardware": h_inf.get('hardware_state', 'UNKNOWN')
        }
        
        # Write to SQLite UMA directly
        self.registry.update_matrix_state(sym, payload)
        return payload

    async def pulse(self):
        targets = self.hunter.scan_movers(limit=15)
        if not targets: return

        # Parallelize the inference loop asynchronously
        tasks = [self._process_ticker(t) for t in targets]
        results = await asyncio.gather(*tasks)
        
        self.live_state["assets"] = [r for r in results if r]
        self.live_state["status"] = "LIVE"
        logger.info(f"[+] Pulse Complete: Processed {len(self.live_state['assets'])} assets via Apple MPS.")

# --- C2 DASHBOARD SERVER ---
async def api_state(request):
    """Replaces SimpleHTTPRequestHandler do_GET"""
    return web.json_response(node.live_state, headers={"Access-Control-Allow-Origin": "*"})

async def background_pulse(app):
    """The Ralph Loop"""
    while True:
        await node.pulse()
        await asyncio.sleep(60)

async def background_audit(app):
    """Triggers the Packer / Entropy Scrub every 12 hours"""
    while True:
        node.registry.execute_entropy_scrub(retention_days=7)
        await asyncio.sleep(43200)

if __name__ == "__main__":
    node = SovereignM4Node()
    
    # Setup Asyncio Web Server
    app = web.Application()
    app.router.add_get('/api/state', api_state)
    
    # Attach background tasks
    app.on_startup.append(background_pulse)
    app.on_startup.append(background_audit)
    
    logger.info("[*] Booting C2 Handler on port 8080...")
    web.run_app(app, port=8080, access_log=None)