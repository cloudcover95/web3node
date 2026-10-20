"""Trit quorum commit for web3node. Pure math: lane-wise trit majority, then side_commit.

Several trit lanes (one per port) vote position by position. The quorum trit is the
sign of the column sum, held at 0 unless |sum| reaches the quorum. The quorum vector
is packed with the shared 2-bit i2s layout and closed with sha256(prev || pack || text)[:16].
Does not call a chain, open a socket, or mint.
"""
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
    """sha256(prev || pack || text)[:16]. Matches juniors_trit_side and side_commit_rate_lock."""
    return hashlib.sha256(prev.encode() + pk + text.encode()).hexdigest()[:16]


def rate_step(x: float) -> float:
    return x * RATE


def quorum(lanes, need: int | None = None) -> list[int]:
    """Lane-wise trit vote. need defaults to a strict majority of the lanes."""
    lanes = [list(l) for l in lanes]
    if not lanes:
        raise ValueError("need at least one lane")
    n = len(lanes[0])
    if any(len(l) != n for l in lanes):
        raise ValueError("lanes must be the same length")
    for l in lanes:
        for t in l:
            if t not in _ENC:
                raise ValueError("trit must be -1, 0 or 1")
    k = len(lanes)
    need = k // 2 + 1 if need is None else need
    if not 1 <= need <= k:
        raise ValueError("need must be in 1..lanes")
    out = []
    for i in range(n):
        s = sum(l[i] for l in lanes)
        out.append(0 if abs(s) < need else (1 if s > 0 else -1))
    return out


def margin(lanes) -> float:
    """Mean |column sum| / lanes, then rate-locked at RATE. 0 when lanes cancel."""
    lanes = [list(l) for l in lanes]
    n, k = len(lanes[0]), len(lanes)
    if n == 0:
        return 0.0
    m = sum(abs(sum(l[i] for l in lanes)) for i in range(n)) / (n * k)
    return rate_step(m)


def quorum_commit(lanes, prev: str = GENESIS, text: str = "quorum", need: int | None = None) -> dict:
    q = quorum(lanes, need)
    pk = pack(q)
    return {
        "prev": prev,
        "quorum": q,
        "pack": pk.hex(),
        "text": text,
        "commit": side_commit(prev, pk, text),
        "margin": margin(lanes),
    }


def chain(rounds, prev: str = GENESIS) -> list[dict]:
    """rounds: iterable of (lanes, text). Each tip feeds the next prev."""
    out = []
    for lanes, text in rounds:
        r = quorum_commit(lanes, prev, text)
        out.append(r)
        prev = r["commit"]
    return out


def verify(rounds_out, prev: str = GENESIS) -> dict:
    for i, r in enumerate(rounds_out):
        if r["prev"] != prev:
            return {"ok": False, "at": i, "reason": "prev"}
        if side_commit(prev, pack(r["quorum"]), r["text"]) != r["commit"]:
            return {"ok": False, "at": i, "reason": "commit"}
        prev = r["commit"]
    return {"ok": True, "n": len(rounds_out), "tip": prev}


def self_check() -> dict:
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH)
    assert abs(RATE - 0.05) < 1e-12 and abs(rate_step(1.0) - 0.05) < 1e-12
    lanes = [
        [1, 0, -1, -1, 1, 0, 1],   # Home
        [1, 1, -1, 0, 1, 0, -1],   # OSai
        [1, 0, -1, -1, 0, 1, 1],   # FieldCore
        [0, 0, 1, -1, 1, 0, 1],    # Flagstaff
        [1, -1, -1, 1, 1, 0, 0],   # JuniorLLM
    ]
    assert len(lanes) == len(PORTS)
    q = quorum(lanes)
    assert q == [1, 0, -1, 0, 1, 0, 0], q
    assert quorum(lanes, need=1) == [1, 0, -1, -1, 1, 1, 1]
    assert quorum(lanes, need=5) == [0, 0, 0, 0, 0, 0, 0]
    assert quorum([[1, -1], [-1, 1]]) == [0, 0]
    assert quorum([[1, 0, -1]]) == [1, 0, -1]
    p = pack(q)
    assert unpack(p, len(q)) == q
    r = quorum_commit(lanes, text="web3")
    assert r["commit"] == side_commit(GENESIS, p, "web3") and len(r["commit"]) == 16
    assert 0.0 <= r["margin"] <= RATE
    assert margin([[1, -1], [-1, 1]]) == 0.0 and abs(margin([[1], [1]]) - RATE) < 1e-12
    ch = chain([(lanes, "web3"), ([[0, 1, -1], [0, 1, -1], [1, 1, 0]], "quorum")])
    v = verify(ch)
    assert v["ok"] and v["n"] == 2 and ch[1]["prev"] == ch[0]["commit"]
    bad = [dict(x) for x in ch]
    bad[0]["quorum"] = [0] * 7
    assert verify(bad) == {"ok": False, "at": 0, "reason": "commit"}
    for bad_lanes in ([], [[1, 0], [1]], [[2, 0]]):
        try:
            quorum(bad_lanes)
        except ValueError:
            pass
        else:
            raise AssertionError("bad lanes accepted")
    return {
        "ok": True,
        "rate": RATE,
        "close": "sha256(prev || pack || text)[:16]",
        "bind": BIND,
        "ports": list(PORTS),
        "quorum": q,
        "pack": p.hex(),
        "commit": r["commit"],
        "tip": v["tip"],
    }


if __name__ == "__main__":
    print(self_check())
