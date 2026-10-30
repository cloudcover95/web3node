"""Trit delta deadband commit for web3node. Pure math: step-to-step change trits per port, then side_commit.

Each port feeds a real-valued signal. For every step t >= 1 the delta d = x[t] - x[t-1]
becomes +1 when d > band, -1 when d < -band, else 0. The delta lane is packed with the
shared 2-bit i2s layout (0->0, 1->1, -1->2) and closed with sha256(prev || pack || text)[:16],
chained port to port in PORTS order. A drift score (net up minus down steps per step) is
rate-locked at RATE.
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


def delta_trits(signal, band: float) -> list[int]:
    """Deadband sign of x[t] - x[t-1]. band >= 0. Lane length is len(signal) - 1 (empty if < 2)."""
    if not band >= 0:
        raise ValueError("band must be >= 0")
    xs = [float(x) for x in signal]
    out = []
    for a, b in zip(xs, xs[1:]):
        d = b - a
        out.append(1 if d > band else (-1 if d < -band else 0))
    return out


def drift(lane) -> float:
    """(ups - downs) / steps, rate-locked at RATE. In [-RATE, RATE]; 0 for an empty lane."""
    lane = list(lane)
    if not lane:
        return 0.0
    return rate_step(sum(lane) / len(lane))


def delta_commit(port_signals, band: float, prev: str = GENESIS) -> list[dict]:
    """port_signals: mapping port -> signal. Ports run in PORTS order; each tip feeds the next prev."""
    unknown = set(port_signals) - set(PORTS)
    if unknown:
        raise ValueError(f"unknown ports: {sorted(unknown)}")
    out = []
    for port in PORTS:
        if port not in port_signals:
            continue
        lane = delta_trits(port_signals[port], band)
        pk = pack(lane)
        c = side_commit(prev, pk, port)
        out.append({
            "port": port,
            "prev": prev,
            "lane": lane,
            "pack": pk.hex(),
            "text": port,
            "commit": c,
            "drift": drift(lane),
        })
        prev = c
    return out


def verify(rows, prev: str = GENESIS) -> dict:
    for i, r in enumerate(rows):
        if r["prev"] != prev:
            return {"ok": False, "at": i, "reason": "prev"}
        if side_commit(prev, pack(r["lane"]), r["text"]) != r["commit"]:
            return {"ok": False, "at": i, "reason": "commit"}
        prev = r["commit"]
    return {"ok": True, "n": len(rows), "tip": prev}


def self_check() -> dict:
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH)
    assert abs(RATE - 0.05) < 1e-12 and abs(rate_step(1.0) - 0.05) < 1e-12
    # shared engine vector
    ref = [1, 0, -1, -1, 1, 0, 1]
    rp = pack(ref)
    assert rp.hex() == "4a44" and unpack(rp, 7) == ref
    assert side_commit(GENESIS, rp, "ladder") == "17094da0816dfd3a"
    # deadband behaviour
    sig = [1.0, 1.5, 1.55, 1.2, 1.2, 0.5, 0.9]
    lane = delta_trits(sig, band=0.1)
    assert lane == [1, 0, -1, 0, -1, 1], lane
    assert drift(lane) == 0.0 and abs(drift([1, 0, -1, 1]) - RATE * 0.25) < 1e-12
    assert delta_trits([0.0, 0.1], 0.1) == [0]
    assert delta_trits([0.0, 0.1], 0.0) == [1]
    assert delta_trits([3.0], 0.1) == [] and delta_trits([], 0.1) == []
    assert drift([]) == 0.0 and abs(drift([1, 1]) - RATE) < 1e-12 and abs(drift([-1]) + RATE) < 1e-12
    sigs = {
        "Home": sig,
        "OSai": [0.0, 0.5, 1.0, 1.5],
        "FieldCore": [2.0, 1.0, 0.0],
        "Flagstaff": [0.0, 0.0, 0.0, 0.0],
        "JuniorLLM": [1.0, -1.0, 1.0, 1.05],
    }
    rows = delta_commit(sigs, 0.1)
    assert [r["port"] for r in rows] == list(PORTS)
    assert rows[0]["commit"] == side_commit(GENESIS, pack(lane), "Home")
    assert all(len(r["commit"]) == 16 and -RATE <= r["drift"] <= RATE for r in rows)
    v = verify(rows)
    assert v["ok"] and v["n"] == 5 and v["tip"] == rows[-1]["commit"]
    bad = [dict(r) for r in rows]
    bad[1]["lane"] = [0] * len(bad[1]["lane"])
    assert verify(bad) == {"ok": False, "at": 1, "reason": "commit"}
    try:
        delta_trits([0.0, 1.0], -0.1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative band accepted")
    try:
        delta_commit({"Mainnet": [0.0]}, 0.1)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown port accepted")
    return {
        "ok": True,
        "rate": RATE,
        "close": "sha256(prev || pack || text)[:16]",
        "bind": BIND,
        "ports": list(PORTS),
        "home_lane": lane,
        "home_pack": pack(lane).hex(),
        "tip": v["tip"],
    }


if __name__ == "__main__":
    print(self_check())
