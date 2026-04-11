#!/bin/bash
# ==============================================================================
# JC-SDK V150.2 | TETHERED BOOT & SAFE SWEEPER
# ==============================================================================
echo "=========================================================="
echo " 🚀 JUNIORCLOUD SDK | V150 TETHERED BOOT"
echo "=========================================================="

# 1. Environment & Dependency Tether
echo "[1/5] Syncing Virtual Environment & Matrix..."
source venv/bin/activate
pip install -q structlog pydantic aiohttp pandas yfinance stable-baselines3 statsmodels pyarrow
echo "[+] Matrix Synchronized."

# 2. Workspace Snapshot
echo "[2/5] Generating Workspace Snapshot..."
python3 -c "
import os, json
def audit(path):
    tree = {}
    for root, _, files in os.walk(path):
        if any(x in root for x in ['.git', '__pycache__', 'venv', 'Legacy_Archive', 'Legacy_Code']): continue
        folder = root.replace(path, '').strip(os.sep)
        tree[folder if folder else 'ROOT'] = files
    return tree
with open('Omni_Vault/workspace_snapshot.json', 'w') as f:
    json.dump({'timestamp': os.popen('date').read().strip(), 'structure': audit('.')}, f, indent=4)
"

# 3. Targeted Legacy Cleanup (Safe Mode)
echo "[3/5] Sweeping truly deprecated branches to Vault..."
mkdir -p Omni_Vault/Legacy_Code
# Moving root-level legacy files
mv registry_bridge.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv run_omni_node.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv jc_sdk_hegemon_mps.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv juniorcloud_sdk.py Omni_Vault/Legacy_Code/ 2>/dev/null
# Moving SDK components replaced by Hegemon V150
mv jc_omni/profit_oracle.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv jc_omni/omni_simulator.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv jc_omni/omni_ledger.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv jc_omni/omni_data.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv jc_omni/report_engine.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv jc_omni/ledger_manager.py Omni_Vault/Legacy_Code/ 2>/dev/null
mv jc_omni/sovereign_registry.py Omni_Vault/Legacy_Code/ 2>/dev/null
echo "[+] Workspace optimized. Dependencies protected."

# 5. Launch Node
echo "[5/5] Launching V150 M4 Node Core..."
echo "=========================================================="
python3 run_jcllc_node.py