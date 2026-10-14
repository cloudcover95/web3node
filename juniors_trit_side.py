"""Juniors trit side commit. Pure math: trit pack + side_commit. Does not call a chain."""
from __future__ import annotations

import hashlib

RATE = 0.05
MINT = False
SOCKET = False
LAYER_ONE = False

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
    """sha256(prev || pack || text)[:16]."""
    return hashlib.sha256(prev.encode() + pk + text.encode()).hexdigest()[:16]


def rate_step(x: float) -> float:
    return x * RATE


if __name__ == "__main__":
    t = [1, 0, -1, -1, 1, 0, 1]
    p = pack(t)
    assert unpack(p, len(t)) == t
    c = side_commit("0" * 16, p, "juniors")
    assert len(c) == 16 and c == side_commit("0" * 16, p, "juniors")
    assert not (MINT or SOCKET or LAYER_ONE) and abs(rate_step(1.0) - 0.05) < 1e-12
    print({"pack": p.hex(), "commit": c, "ok": True})
