#!/bin/bash
# ==============================================================================
# JC-SDK V138 | SYSTEM BOOTSTRAPPER (M4 SILICON)
# ==============================================================================

echo "[*] Initiating JuniorCloud Omni Node..."

# 1. Enforce Virtual Environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "[!] Virtual Environment not active. Engaging tether..."
    if [ -d "venv" ]; then
        source venv/bin/activate
        echo "[+] Venv active: $VIRTUAL_ENV"
    else
        echo "[!] FATAL: No 'venv' directory found. Run 'python3 -m venv venv' first."
        exit 1
    fi
fi

# 2. Enforce Dependencies
echo "[*] Verifying Library Matrix..."
pip install -q aiohttp pandas yfinance stable-baselines3 statsmodels pydantic structlog
echo "[+] Matrix Verified."

# 3. Launch the Unified Factory Node
echo "[*] Handing off to Apple Silicon (MPS). Engaging caffeinate..."
caffeinate -is python3 run_jcllc_node.py