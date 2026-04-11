# OVERWRITE run_jcllc_node.py
"""
===========================================================================
             [ JC-SDK V150.3 : YF-MULTIINDEX FIX & CG-THROTTLE ]
===========================================================================
"""
import os
import sys
import json
import asyncio
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional, Set
import pandas as pd
import numpy as np
import aiohttp
from aiohttp import web
import logging
import yfinance as yf

def sanitize_for_json(obj):
    if isinstance(obj, (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)): return int(obj)
    elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)): return float(obj)
    elif isinstance(obj, (np.bool_)): return bool(obj)
    elif isinstance(obj, np.ndarray): return obj.tolist()
    elif isinstance(obj, dict): return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list): return [sanitize_for_json(i) for i in obj]
    return obj

def generate_workspace_audit(startpath):
    tree = {}
    for root, _, files in os.walk(startpath):
        if any(x in root for x in ['.git', '__pycache__', 'venv', 'Omni_Vault/Legacy_Archive', 'Omni_Vault/Legacy_Code']): continue
        folder = root.replace(startpath, '').strip(os.sep)
        tree[folder if folder else 'ROOT'] = files
    return tree

from jc_omni.omni_hunter import OmniHunter
from jc_omni.hegemon_sdk import SovereignHegemonSDK, KinematicState

logger = logging.getLogger("JCLLC_FACTORY")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FactoryNode:
    def __init__(self):
        self.sdk = SovereignHegemonSDK()
        self.hunter = OmniHunter()
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.vault_dir = os.path.join(self.root_dir, "Omni_Vault")
        self.db_path = os.getenv("DB_PATH", os.path.join(self.vault_dir, "hegemon_core.db"))
        self.deep_dir = os.path.join(self.vault_dir, "Deep_History")

        self.live_state = {
            "status": "LIVE", "drift": 0.0, "daily_mints": 0, "assets": [],
            "forks": {"A": [], "B": [], "C": []}, "version": "V150-STABLE",
            "last_pulse": 0.0, "ws_clients": 0, "backfilled": 0
        }

        os.makedirs(self.vault_dir, exist_ok=True)
        os.makedirs(self.deep_dir, exist_ok=True)
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_clients: Set[web.WebSocketResponse] = set()
        self.state_lock = asyncio.Lock()
        
        # Traffic Controllers for API Fallbacks
        self.cg_lock = asyncio.Lock()
        self.last_cg_call = 0.0
        
        self.backfilled_tickers = set()
        self._ensure_db_schema()

    def _ensure_db_schema(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''CREATE TABLE IF NOT EXISTS inference_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, stance TEXT, cycle_phase TEXT)''')

        cols = ['spot_price REAL', 'svd_deviation REAL', 'splash_impact REAL', 'system_entropy REAL',
                'agent_edge REAL', 'topological_signature TEXT', 'void_gravity REAL',
                'relative_trajectory REAL', 'viz_x REAL', 'viz_y REAL', 'robust_z REAL', 'q_mark REAL',
                'psi_amplitude REAL', 'splash_ratio REAL', 'viscosity REAL', 'gravity_well REAL',
                'structural_deviation REAL', 'mesh_fold REAL', 'gradient_layer REAL', 'confidence REAL',
                'horizon BOOLEAN', 'bit_signature TEXT']
        for col in cols:
            try: conn.execute(f"ALTER TABLE inference_ledger ADD COLUMN {col}")
            except: pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_ts ON inference_ledger (ticker, timestamp DESC)")
        conn.commit()
        conn.close()

    async def _create_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))

    def _save_deep_history(self, df: pd.DataFrame, sym: str, suffix: str = "DEEP"):
        base = f"{sym.replace('-', '_')}_{suffix}"
        parquet_path = os.path.join(self.deep_dir, f"{base}.parquet")
        try:
            import pyarrow
            df.to_parquet(parquet_path, compression='snappy', engine='pyarrow')
        except:
            df.to_csv(os.path.join(self.deep_dir, f"{base}.csv"), index=True)

    async def _backfill_full_history(self, sym: str):
        full_path = os.path.join(self.deep_dir, f"{sym.replace('-', '_')}_FULL.parquet")
        if os.path.exists(full_path):
            self.backfilled_tickers.add(sym)
            return

        try:
            full_df = await asyncio.to_thread(yf.download, sym, period="max", interval="1d", progress=False)
            if full_df.empty or len(full_df.dropna(subset=['Close'])) < 30: return
            self._save_deep_history(full_df, sym, suffix="FULL")
            self.backfilled_tickers.add(sym)
        except Exception:
            pass

    async def _process_ticker(self, target: dict, macro_baseline: list, df_multi=None, is_multi: bool = False):
        sym = target['yf']
        df = None

        # 1. Try YFinance Batch First (Direct Column Access - Avoids MultiIndex KeyError)
        if df_multi is not None and not df_multi.empty:
            try:
                if is_multi:
                    # Explicitly check if the ticker exists in the top-level 'Close' columns
                    if 'Close' in df_multi.columns and sym in df_multi['Close'].columns:
                        c = df_multi['Close'][sym]
                        v = df_multi['Volume'][sym]
                        df = pd.DataFrame({'price': c, 'volume': v}).dropna(subset=['price']).copy()
                else:
                    if 'Close' in df_multi.columns:
                        df = df_multi[['Close', 'Volume']].rename(columns={'Close':'price', 'Volume':'volume'}).dropna().copy()
            except Exception:
                df = None 

        # 2. Try YFinance Individual (Only for minor gaps)
        if df is None or df.empty or len(df) < 30:
            try:
                df_ind = await asyncio.to_thread(yf.download, sym, period="100d", interval="1d", progress=False)
                df_ind = df_ind.dropna(subset=['Close'])
                if not df_ind.empty and len(df_ind) >= 30:
                    df = df_ind[['Close', 'Volume']].copy()
                    df.columns = ['price', 'volume']
            except: pass

        # 3. THE COINGECKO BYPASS (Strictly Throttled Async Queue)
        if df is None or df.empty or len(df) < 30:
            cg_id = target.get('cg_id')
            if cg_id:
                async with self.cg_lock:
                    now = time.time()
                    elapsed = now - self.last_cg_call
                    if elapsed < 2.5: # Max 24 requests per minute to guarantee no 429
                        await asyncio.sleep(2.5 - elapsed)
                    self.last_cg_call = time.time()
                
                logger.info(f"[*] {sym} missing from YF. Engaging CoinGecko API Bypass...")
                url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days=100"
                try:
                    async with self.session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'prices' in data and len(data['prices']) > 0:
                                p_df = pd.DataFrame(data['prices'], columns=['Timestamp', 'price'])
                                v_df = pd.DataFrame(data['total_volumes'], columns=['Timestamp', 'volume'])
                                df = pd.merge(p_df, v_df, on='Timestamp')
                                df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='ms')
                                df.set_index('Timestamp', inplace=True)
                                df = df.resample('1D').mean().dropna()
                        elif resp.status == 429:
                            logger.error(f"[!] CoinGecko Global Limit Breached. Sleeping node for 15s...")
                            await asyncio.sleep(15)
                except Exception:
                    pass

        # Final check
        if df is None or df.empty or len(df) < 30: return None

        df['volume'] = df['volume'].fillna(0)
        self._save_deep_history(df, sym, suffix="DEEP")
        await self._backfill_full_history(sym) 

        prices = df['price'].values.flatten().tolist()
        volumes = df['volume'].values.flatten().tolist()
        state = KinematicState(ticker=sym, prices=prices, volumes=volumes, sector_velocities=macro_baseline)
        inf = self.sdk.infer(state)

        if "WARMING" in inf.get('stance', '') or "ERR" in inf.get('stance', ''): return None

        inf['short_tag'] = sym.split('-')[0]
        inf['tax_call'] = inf.get('stance')
        inf['velocity'] = inf.get('viz_x', 0)
        inf['acceleration'] = inf.get('viz_y', 0)
        inf['ticker'] = sym
        inf['volume_24h'] = target.get('volume_24h', 0)
        inf['change_24h'] = target.get('change_24h', 0)
        inf['market_cap'] = target.get('market_cap', 0)
        
        return inf

    def _generate_forks(self, assets):
        forks = {"A": [], "B": [], "C": []}
        for a in assets:
            forks["A"].append(a.copy())
            b = a.copy(); b['q_mark'] = min(b.get('q_mark', 0) * 1.5, 0.99); forks["B"].append(b)
            c = a.copy(); c['q_mark'] = c.get('q_mark', 0) * 0.7; forks["C"].append(c)
        return forks

    async def pulse(self):
        concurrency_limit = asyncio.Semaphore(5) 
        async def bounded_process(ticker_data, baseline, df_multi_ref, is_multi_flag):
            async with concurrency_limit:
                await asyncio.sleep(0.1) 
                return await self._process_ticker(ticker_data, baseline, df_multi_ref, is_multi_flag)

        while True:
            try:
                macro_baseline = self.hunter.get_macro_baseline()
                targets = self.hunter.scan_movers(limit=100)

                if targets:
                    yf_symbols = list({t['yf'] for t in targets})
                    df_multi, is_multi = None, False
                    try:
                        df_multi = await asyncio.to_thread(yf.download, yf_symbols, period="100d", interval="1d", progress=False)
                        is_multi = isinstance(df_multi.columns, pd.MultiIndex)
                    except Exception as e:
                        logger.warning(f"Batch YF failed: {e}")

                    tasks = [bounded_process(t, macro_baseline, df_multi, is_multi) for t in targets]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    valid_assets, insert_params = [], []
                    for r in results:
                        if isinstance(r, dict):
                            valid_assets.append(r)
                            insert_params.append((
                                r['ticker'], r.get('stance'), r.get('cycle_phase'), r.get('spot_price', 0),
                                r.get('system_entropy', 0), r.get('agent_edge', 0), r.get('topological_signature'), 
                                r.get('void_gravity', 0), r.get('relative_trajectory', 0), r.get('viz_x', 0), 
                                r.get('viz_y', 0), r.get('robust_z', 0), r.get('q_mark', 0), r.get('psi_amplitude', 0),
                                r.get('splash_ratio', 0), r.get('viscosity', 0), r.get('gravity_well', 0), 
                                r.get('structural_deviation', 0), r.get('mesh_fold', 0), r.get('gradient_layer', 0), 
                                r.get('confidence', 0), 1 if r.get('horizon') else 0, r.get('bit_signature', '[]')
                            ))

                    if insert_params:
                        conn = sqlite3.connect(self.db_path)
                        conn.executemany('''
                            INSERT INTO inference_ledger
                            (ticker, stance, cycle_phase, spot_price, system_entropy, agent_edge,
                             topological_signature, void_gravity, relative_trajectory, viz_x, viz_y,
                             robust_z, q_mark, psi_amplitude, splash_ratio, viscosity, gravity_well,
                             structural_deviation, mesh_fold, gradient_layer, confidence, horizon, bit_signature)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', insert_params)
                        conn.commit()
                        conn.close()

                    async with self.state_lock:
                        self.live_state["assets"] = valid_assets
                        self.live_state["forks"] = self._generate_forks(valid_assets)
                        self.live_state["last_pulse"] = time.time()
                        self.live_state["ws_clients"] = len(self.ws_clients)
                        self.live_state["backfilled"] = len(self.backfilled_tickers)

                    logger.info(f"[+] V150 Pulse: {len(valid_assets)} assets secured | Backfilled: {len(self.backfilled_tickers)}")

                    if self.ws_clients:
                        broadcast = sanitize_for_json(self.live_state.copy())
                        dead = []
                        for ws in list(self.ws_clients):
                            try: await ws.send_json(broadcast)
                            except: dead.append(ws)
                        for d in dead: self.ws_clients.discard(d)

            except Exception as e:
                logger.error(f"Pulse error: {e}")

            await asyncio.sleep(120)

node = FactoryNode()

async def api_state(request): 
    async with node.state_lock:
        safe_state = sanitize_for_json(node.live_state)
        return web.json_response(safe_state, headers={"Access-Control-Allow-Origin": "*"})

async def api_audit(request):
    return web.json_response({"structure": generate_workspace_audit(node.root_dir)}, headers={"Access-Control-Allow-Origin": "*"})

async def api_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    node.ws_clients.add(ws)
    try:
        safe_state = sanitize_for_json(node.live_state)
        await ws.send_json({"type": "connected", "state": safe_state})
        async for msg in ws:
            if msg.type == web.WSMsgType.CLOSE: break
    finally:
        node.ws_clients.discard(ws)
    return ws

async def api_health(request):
    return web.json_response({"status": "healthy", "version": node.live_state["version"], "backfilled": node.live_state["backfilled"]})

async def on_startup(app):
    await node._create_session()
    asyncio.create_task(node.pulse())

async def on_cleanup(app):
    if node.session and not node.session.closed:
        await node.session.close()

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get('/api/state', api_state)
    app.router.add_get('/api/audit', api_audit)
    app.router.add_get('/api/ws', api_ws)
    app.router.add_get('/api/health', api_health)
    app.router.add_static('/', path=node.root_dir, name='static', show_index=True)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 JC-SDK V150.3 starting @ http://0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port, access_log=None)