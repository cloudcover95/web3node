"""Side-commit chain + rate lock for web3node. Pure math; does not call a chain RPC."""
from __future__ import annotations

import hashlib

RATE = 0.05
MINT = False
SOCKET = False
LAYER_ONE = False
FETCH = False
UE5_LAUNCH = False
BIND = "127.0.0.1"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
GENESIS = "0" * 16

_ENC = {0: 0, 1: 1, -1: 2}
_DEC = {0: 0, 1: 1, 2: -1}


def pack(trits) -> bytes:
    """Balanced trits (-1/0/1) as 2-bit i2s codes (0->0, 1->1, -1->2), MSB first, zero-padded."""
    acc = bits = 0
    out = bytearray()
    for t in trits:
        if t not in _ENC:
            raise ValueError("trit must be -1, 0 or 1")
        acc = (acc << 2) | _ENC[t]
        bits += 2
        if bits == 8:
            out.append(acc)
            acc = bits = 0
    if bits:
        out.append(acc << (8 - bits))
    return bytes(out)


def unpack(data: bytes, n: int) -> list[int]:
    out = []
    for b in data:
        for s in (6, 4, 2, 0):
            out.append(_DEC[(b >> s) & 3])
    return out[:n]


def side_commit(prev: str, pk: bytes, text: str) -> str:
    """sha256(prev || pack || text)[:16]. Matches other engines."""
    return hashlib.sha256(prev.encode() + pk + text.encode()).hexdigest()[:16]


def rate_lock(x: float) -> float:
    """Lock step at RATE (0.05)."""
    return x * RATE


def build_chain(links, prev: str = GENESIS) -> list[dict]:
    """links: iterable of (trits, text). Each tip = sha256(prev || pack || text)[:16]."""
    out = []
    for trits, text in links:
        pk = pack(trits)
        c = side_commit(prev, pk, text)
        out.append({"prev": prev, "trits": list(trits), "text": text, "commit": c})
        prev = c
    return out


def verify_chain(chain, prev: str = GENESIS) -> dict:
    for i, link in enumerate(chain):
        if link["prev"] != prev:
            return {"ok": False, "at": i, "reason": "prev"}
        if side_commit(prev, pack(link["trits"]), link["text"]) != link["commit"]:
            return {"ok": False, "at": i, "reason": "commit"}
        prev = link["commit"]
    return {"ok": True, "n": len(chain), "tip": prev}


def self_check() -> dict:
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH)
    assert abs(RATE - 0.05) < 1e-12 and abs(rate_lock(1.0) - 0.05) < 1e-12
    t = [1, 0, -1, -1, 1, 0, 1]
    p = pack(t)
    assert unpack(p, len(t)) == t
    c = side_commit(GENESIS, p, "web3")
    assert len(c) == 16 and c == side_commit(GENESIS, p, "web3")
    ch = build_chain([(t, "web3"), ([0, 1, -1], "lock")])
    v = verify_chain(ch)
    assert v["ok"] and v["n"] == 2
    bad = [dict(link) for link in ch]
    bad[0]["trits"] = [0, 0, 0, 0, 0, 0, 0]
    assert verify_chain(bad) == {"ok": False, "at": 0, "reason": "commit"}
    return {
        "ok": True,
        "rate": RATE,
        "close": "sha256(prev || pack || text)[:16]",
        "bind": BIND,
        "ports": list(PORTS),
        "tip": v["tip"],
        "engines": ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx"),
    }


if __name__ == "__main__":
    print(self_check())
