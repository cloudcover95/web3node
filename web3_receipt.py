"""Read the Home web3 receipt. Does not call a chain."""
from __future__ import annotations

import json
from pathlib import Path

MESH = Path.home() / ".juniorhome" / "gaia_mesh" / "web3_receipt.jsonl"


def last() -> dict:
    if not MESH.exists():
        return {"ok": False, "reason": "no receipt", "rpc": False, "address": False}
    row = json.loads(MESH.read_text(encoding="utf-8").strip().splitlines()[-1])
    row["ok"] = True
    row["rpc"] = False
    row["address"] = False
    return row


if __name__ == "__main__":
    print(json.dumps(last(), indent=2))
