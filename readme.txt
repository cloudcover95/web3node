setup_m4.sh (Deployment Automator)

jc_omni/__init__.py (Package Init)

jc_omni/omni_math.py (Quantum & SVD Engine)

jc_omni/omni_data.py (Real Market Archivist)

jc_omni/omni_ledger.py (Storage & Alpha Minting)

jc_omni/omni_hunter.py (CoinGecko Volume Scanner)

jc_omni/omni_simulator.py (Historical PnL Backtester)

run_omni_node.py (The Live Execution Server)

run_quantum_sim.py (The Backtest Execution Script)

# JuniorCloud Sovereign SDK (V141)

A proprietary, high-dimensional quantitative analysis engine designed for Web3 and TradFi capital flow tracking. 

## Core Architecture
* **Apple Silicon Native (MPS):** Bypasses standard CPU limitations by compiling tensor mathematics directly to Apple's Metal Performance Shaders via Unified Memory.
* **OAM Topology Engine:** Utilizes Takens' Embedding and Persistent Homology (`giotto-tda`) to map market momentum as Orbital Angular Momentum (OAM), classifying capital flows into noise-immune geometric signatures.
* **Asynchronous Data Lake:** Features an internal SQLite mesh that autonomously audits, archives, and self-cleans using an Alpha-Decay algorithm.
* **A/C Dual-Reality Sandbox:** A web-based visual mesh interface separating the SDK's autonomous executions (Reality A) from user-simulated environments (Reality C).

## Deployment
1. Ensure Python 3.9+ is installed.
2. Run the master bootstrap tether:
```bash
chmod +x jc_deploy.sh
./jc_deploy.sh
3. Access the Sovereign Mesh Dashboard at: http://localhost:8080/sovereign_mesh.html
© 2026 JuniorCloud LLC. All Rights Reserved.
