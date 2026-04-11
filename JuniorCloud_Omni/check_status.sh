#!/bin/bash
echo "--- JUNIORCLOUD NODE HEALTH (V139) ---"
NODE_PROC=$(lsof -ti:8080 | wc -l)
echo "PORT 8080 (M4 NODE): $NODE_PROC process(es)"

if [ -f "Omni_Vault/hegemon_core.db" ]; then
    echo "LEDGER STATE:        FOUND (Live)"
else
    echo "LEDGER STATE:        MISSING (Check Legacy_Archive)"
fi
echo "-------------------------------"

if [ "$NODE_PROC" -gt 0 ]; then
    curl -s http://localhost:8080/api/state | python3 -m json.tool | grep -E "status|assets|version"
else
    echo "[!] OFFLINE: Restart via ./jc_deploy.sh"
fi
echo "-------------------------------"