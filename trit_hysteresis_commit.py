"""Trit hysteresis commit for web3node. Pure math: Schmitt-style trit state per port, then side_commit.

Each port feeds a real-valued signal. The trit state only flips to +1 when the signal
reaches +enter, only flips to -1 when it reaches -enter, and only falls back to 0 once
|signal| drops under exit (exit <= enter). That band keeps chatter off the trit lane.
Each port's state lane is packed with the shared 2-bit i2s layout and closed with
sha256(prev || pack || text)[:16], chained port to port.
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


def hysteresis(signal, enter: float, exit: float, start: int = 0) -> list[int]:
    """Schmitt trit lane. enter > 0, 0 <= exit <= enter. start is the state before the first sample."""
    if not enter > 0:
        raise ValueError("enter must be > 0")
    if not 0 <= exit <= enter:
        raise ValueError("exit must be in 0..enter")
    if start not in _ENC:
        raise ValueError("start must be a trit")
    state = start
    out = []
    for x in signal:
        x = float(x)
        if x >= enter:
            state = 1
        elif x <= -enter:
            state = -1
        elif abs(x) < exit:
            state = 0
        out.append(state)
    return out


def flips(lane) -> int:
    """Number of state changes along a trit lane."""
    lane = list(lane)
    return sum(1 for a, b in zip(lane, lane[1:]) if a != b)


def chatter(lane) -> float:
    """Flip rate per step, rate-locked at RATE. 0 for a steady lane."""
    lane = list(lane)
    if len(lane) < 2:
        return 0.0
    return rate_step(flips(lane) / (len(lane) - 1))


def hysteresis_commit(port_signals, enter: float, exit: float, prev: str = GENESIS) -> list[dict]:
    """port_signals: mapping port -> signal. Ports run in PORTS order; each tip feeds the next prev."""
    unknown = set(port_signals) - set(PORTS)
    if unknown:
        raise ValueError(f"unknown ports: {sorted(unknown)}")
    out = []
    for port in PORTS:
        if port not in port_signals:
            continue
        lane = hysteresis(port_signals[port], enter, exit)
        pk = pack(lane)
        c = side_commit(prev, pk, port)
        out.append({
            "port": port,
            "prev": prev,
            "lane": lane,
            "pack": pk.hex(),
            "text": port,
            "commit": c,
            "chatter": chatter(lane),
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
    # band behaviour
    sig = [0.0, 0.6, 1.0, 0.7, 0.4, 0.2, -0.6, -1.2, -0.5, 0.1]
    lane = hysteresis(sig, enter=1.0, exit=0.3)
    assert lane == [0, 0, 1, 1, 1, 0, 0, -1, -1, 0], lane
    assert flips(lane) == 4 and abs(chatter(lane) - RATE * 4 / 9) < 1e-12
    assert hysteresis([0.5, 0.5], 1.0, 0.3, start=1) == [1, 1]
    assert hysteresis([0.5, 0.5], 1.0, 0.3, start=-1) == [-1, -1]
    assert hysteresis([0.9, -0.9], 1.0, 1.0, start=1) == [0, 0]
    assert chatter([1]) == 0.0 and chatter([1, 1, 1]) == 0.0
    assert abs(chatter([1, -1]) - RATE) < 1e-12
    sigs = {
        "Home": sig,
        "OSai": [0.2, 1.1, 0.9, 0.5, -0.1],
        "FieldCore": [-1.0, -0.8, -0.2, 0.0],
        "Flagstaff": [0.0, 0.0, 0.0],
        "JuniorLLM": [1.5, -1.5, 1.5, 0.29],
    }
    rows = hysteresis_commit(sigs, 1.0, 0.3)
    assert [r["port"] for r in rows] == list(PORTS)
    assert rows[0]["commit"] == side_commit(GENESIS, pack(lane), "Home")
    assert all(len(r["commit"]) == 16 and 0.0 <= r["chatter"] <= RATE for r in rows)
    v = verify(rows)
    assert v["ok"] and v["n"] == 5 and v["tip"] == rows[-1]["commit"]
    bad = [dict(r) for r in rows]
    bad[2]["lane"] = [0] * len(bad[2]["lane"])
    assert verify(bad) == {"ok": False, "at": 2, "reason": "commit"}
    for args in ((0.0, 0.0), (1.0, 1.5), (1.0, -0.1)):
        try:
            hysteresis([0.0], *args)
        except ValueError:
            pass
        else:
            raise AssertionError("bad band accepted")
    try:
        hysteresis_commit({"Mainnet": [0.0]}, 1.0, 0.3)
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
