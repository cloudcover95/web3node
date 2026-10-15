"""Trit rate ladder for web3node. Pure math; does not call a chain RPC.

Integer accrual ladder at RATE (0.05), each rung written in balanced ternary,
packed with the shared 2-bit i2s trit pack, and chained with the close rule
sha256(prev || pack || text)[:16]. Same pack and side_commit as
juniors_trit_side.py and side_commit_rate_lock.py.
"""
from __future__ import annotations

import hashlib
from fractions import Fraction

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

# Shared engine vector: pack([1,0,-1,-1,1,0,1]) and side_commit(GENESIS, pack, "ladder").
_REF_PACK = "4a44"
_REF_COMMIT = "17094da0816dfd3a"


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


def to_trits(n: int) -> list[int]:
    """Balanced-ternary digits of n, least significant first."""
    if n == 0:
        return [0]
    out = []
    while n:
        r = n % 3
        if r == 2:
            r = -1
        out.append(r)
        n = (n - r) // 3
    return out


def from_trits(trits) -> int:
    total = 0
    for i, t in enumerate(trits):
        if t not in _ENC:
            raise ValueError("trit must be -1, 0 or 1")
        total += t * 3 ** i
    return total


def ladder(units: int, steps: int, rate: float = RATE) -> list[int]:
    """Integer rungs: each rung = floor(prev * (1 + rate)), exact rational math."""
    r = Fraction(str(rate))
    rungs = [int(units)]
    v = Fraction(int(units))
    for _ in range(steps):
        v = Fraction((v * (1 + r)).__floor__())
        rungs.append(int(v))
    return rungs


def ladder_chain(rungs, prev: str = GENESIS) -> list[dict]:
    """Chain each rung: trits = to_trits(rung), text = 'rung<i>'."""
    out = []
    for i, v in enumerate(rungs):
        trits = to_trits(v)
        text = f"rung{i}"
        c = side_commit(prev, pack(trits), text)
        out.append({"prev": prev, "rung": v, "trits": trits, "text": text, "commit": c})
        prev = c
    return out


def verify_ladder(chain, prev: str = GENESIS) -> dict:
    for i, link in enumerate(chain):
        if link["prev"] != prev:
            return {"ok": False, "at": i, "reason": "prev"}
        if from_trits(link["trits"]) != link["rung"]:
            return {"ok": False, "at": i, "reason": "trits"}
        if side_commit(prev, pack(link["trits"]), link["text"]) != link["commit"]:
            return {"ok": False, "at": i, "reason": "commit"}
        prev = link["commit"]
    return {"ok": True, "n": len(chain), "tip": prev}


def self_check() -> dict:
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH)
    assert abs(RATE - 0.05) < 1e-12
    for n in range(-729, 730):
        assert from_trits(to_trits(n)) == n
    t = [1, 0, -1, -1, 1, 0, 1]
    p = pack(t)
    assert unpack(p, len(t)) == t
    assert p.hex() == _REF_PACK
    assert side_commit(GENESIS, p, "ladder") == _REF_COMMIT
    rungs = ladder(1000, 4)
    assert rungs == [1000, 1050, 1102, 1157, 1214], rungs
    ch = ladder_chain(rungs)
    v = verify_ladder(ch)
    assert v["ok"] and v["n"] == 5
    bad = [dict(link) for link in ch]
    bad[2]["rung"] = 1103
    assert verify_ladder(bad) == {"ok": False, "at": 2, "reason": "trits"}
    return {
        "ok": True,
        "rate": RATE,
        "close": "sha256(prev || pack || text)[:16]",
        "bind": BIND,
        "ports": list(PORTS),
        "rungs": rungs,
        "tip": v["tip"],
    }


if __name__ == "__main__":
    print(self_check())
