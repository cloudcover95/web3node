# OVERWRITE jc_omni/omni_hunter.py
import requests
import logging
import time
import numpy as np
import yfinance as yf
from .credential_bridge import get_polygon_key

logger = logging.getLogger("OmniHunter")

class OmniHunter:
    def __init__(self, poly_key=None):
        self.poly_key = poly_key or get_polygon_key()
        self.cg_api = "https://api.coingecko.com/api/v3/coins/markets"
        self.poly_api = "https://api.polygon.io/v2/snapshot/locale/global/markets/crypto/tickers"
        
        # Extended Web3 blacklist (stripping out pegs and wrappers)
        self.blacklist = ['USDT', 'USDC', 'DAI', 'WBTC', 'FDUSD', 'STETH', 'WETH', 'USD1', 'BUSD', 'TUSD', 'USDD']
        
        self.cached_targets = []
        self.last_scan_time = 0
        self.cache_ttl = 900  # 15 Minute Cache = Saves Polygon Quota
        self.macro_baseline_cache = []

    def get_macro_baseline(self) -> list:
        now = time.time()
        if self.macro_baseline_cache and (now - self.last_scan_time < self.cache_ttl): 
            return self.macro_baseline_cache
        try:
            logger.info("[*] Generating Sector Consensus Baseline (BTC Beta)...")
            df = yf.download("BTC-USD", period="40d", interval="1d", progress=False)
            if not df.empty and len(df) >= 30:
                self.macro_baseline_cache = np.gradient(df['Close'].dropna().values.flatten()).tolist()
                return self.macro_baseline_cache
        except Exception as e:
            logger.debug(f"Baseline generation failed: {e}")
        return []

    def scan_movers(self, limit=100):
        now = time.time()
        if now - self.last_scan_time < self.cache_ttl and self.cached_targets:
            return self.cached_targets

        targets = []
        
        # --- PIPELINE A: POLYGON (Primary Snapshot + TradFi Metrics) ---
        if self.poly_key and "YOUR_POLYGON_KEY" not in self.poly_key:
            try:
                logger.info("[*] Hunter Pipeline A: Polygon Snapshot...")
                url = f"{self.poly_api}?apiKey={self.poly_key}"
                r = requests.get(url, timeout=10)
                
                if r.status_code == 200:
                    data = r.json()
                    # Sort by daily volume (v) to mimic a stock market screener
                    sorted_tickers = sorted(data['tickers'], key=lambda x: x.get('day', {}).get('v', 0), reverse=True)
                    
                    for t in sorted_tickers:
                        sym = t['ticker'].replace('X:', '').split('USD')[0]
                        day_data = t.get('day', {})
                        
                        if sym not in self.blacklist and len(targets) < limit:
                            targets.append({
                                "yf": f"{sym}-USD",               # For YFinance 100d history
                                "poly_id": f"X:{sym}USD",         # For Polygon slow-drip history
                                "cg_id": sym.lower(),             # For CoinGecko fallback
                                "price": t.get('lastTrade', {}).get('p', 0),
                                "volume_24h": day_data.get('v', 0),
                                "change_24h": t.get('todaysChangePerc', 0),
                                "vwap_24h": day_data.get('vw', 0) # Volume Weighted Average Price
                            })
                    if targets:
                        self.cached_targets = targets
                        self.last_scan_time = now
                        logger.info(f"[+] Polygon Hunter Secured {len(targets)} Targets.")
                        return targets
                else:
                    logger.warning(f"[-] Polygon Snapshot Limit Hit ({r.status_code}).")
            except Exception as e:
                logger.warning(f"[-] Polygon pipeline failed ({e}). Shifting to Web3 Fallback.")

        # --- PIPELINE B: COINGECKO (Web3 Fallback) ---
        try:
            logger.info("[*] Hunter Pipeline B: CoinGecko Fallback...")
            params = {"vs_currency": "usd", "order": "volume_desc", "per_page": min(limit, 250), "page": 1}
            r = requests.get(self.cg_api, params=params, timeout=10)
            
            if r.status_code == 200:
                for c in r.json():
                    sym = c['symbol'].upper()
                    if sym not in self.blacklist and len(targets) < limit:
                        targets.append({
                            "yf": f"{sym}-USD",               # For YFinance
                            "poly_id": f"X:{sym}USD",         # For Polygon slow-drip
                            "cg_id": c['id'],                 # For CoinGecko
                            "price": c['current_price'],
                            "market_cap": c.get('market_cap', 0),
                            "volume_24h": c.get('total_volume', 0),
                            "change_24h": c.get('price_change_percentage_24h', 0)
                        })
                self.cached_targets = targets
                self.last_scan_time = now
                logger.info(f"[+] CoinGecko Hunter Secured {len(targets)} Targets.")
        except Exception as e:
            logger.error(f"[-] Hunter CG Error: {e}")
            
        return self.cached_targets