"""i2sd receipt ledger — append-only side-commit chains + rate lock + backfill_check.

ROADMAP item: JuniorHome docs/ROADMAP.md — i2sd userspace (127.0.0.1:8767)
Advances live-beta receipt chains / backfill_check (JuniorLLM docs/BETA_TO_OS.md
Live beta #5) at rate 0.05.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded. Rate lock commits rate 0.05 beside
the pack as sha256(prev || pack || b"0.05") full hexdigest.
"""
from __future__ import annotations

import hashlib
import sys
from typing import Any

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16

MINT = False
SOCKET = False
LAYER_ONE = False
FETCH = False
UE5_LAUNCH = False
RELEASED = 0
BIND = "127.0.0.1"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")

_TRIT_TO_BITS = {0: 0, 1: 1, -1: 2}
_BITS_TO_TRIT = {0: 0, 1: 1, 2: -1}


def pack(trits: list[int]) -> bytes:
    """Pack trits to bytes: 2-bit i2s (0->0, 1->1, -1->2), MSB first, zero-padded."""
    bits = 0
    n = 0
    out = bytearray()
    for t in trits:
        bits = (bits << 2) | _TRIT_TO_BITS[t]
        n += 2
        while n >= 8:
            n -= 8
            out.append((bits >> n) & 0xFF)
            bits &= (1 << n) - 1 if n else 0
    if n:
        out.append((bits << (8 - n)) & 0xFF)
    return bytes(out)


def unpack(data: bytes, count: int | None = None) -> list[int]:
    """Unpack i2s 2-bit bytes back to trits. count limits trit count if given."""
    trits: list[int] = []
    for b in data:
        for shift in (6, 4, 2, 0):
            bits = (b >> shift) & 0x3
            if bits == 3:
                continue  # padding / invalid; skip
            trits.append(_BITS_TO_TRIT[bits])
            if count is not None and len(trits) >= count:
                return trits
    if count is not None:
        return trits[:count]
    return trits


def side_commit(prev: str, pk: bytes, text: str) -> str:
    """Close rule: sha256(prev || pack || text)[:16]."""
    h = hashlib.sha256(prev.encode() + pk + text.encode())
    return h.hexdigest()[:16]


def rate_lock_commit(prev: str, pk: bytes) -> str:
    """Rate lock: sha256(prev || pack || rate_bytes) full hexdigest (JUNIORS_RATE)."""
    return hashlib.sha256(prev.encode() + pk + RATE_BYTES).hexdigest()


def append_receipt(
    ledger: list[dict[str, Any]],
    prev: str,
    trits: list[int],
    text: str,
) -> dict[str, Any]:
    """Append one receipt link; returns the new link dict."""
    pk = pack(trits)
    commit = side_commit(prev, pk, text)
    rate_commit = rate_lock_commit(prev, pk)
    link = {
        "prev": prev,
        "trits": list(trits),
        "text": text,
        "commit": commit,
        "rate_commit": rate_commit,
    }
    ledger.append(link)
    return link


def verify_ledger(
    ledger: list[dict[str, Any]],
    prev: str = GENESIS,
) -> dict[str, Any]:
    """Verify contiguous side-commit chain from prev/GENESIS."""
    cur = prev
    for i, link in enumerate(ledger):
        if link.get("prev") != cur:
            return {"ok": False, "at": i, "reason": "prev_mismatch"}
        pk = pack(link["trits"])
        expected = side_commit(cur, pk, link["text"])
        if link.get("commit") != expected:
            return {"ok": False, "at": i, "reason": "commit_mismatch"}
        rc = rate_lock_commit(cur, pk)
        if link.get("rate_commit") != rc:
            return {"ok": False, "at": i, "reason": "rate_commit_mismatch"}
        cur = link["commit"]
    return {"ok": True, "tip": cur}


def backfill_check(
    ledger: list[dict[str, Any]],
    prev: str = GENESIS,
) -> dict[str, Any]:
    """Live-beta backfill gate: contiguous chain, all commits match.

    Returns ok True when chain is contiguous and commits match; gaps lists
    indices where the prev link is broken.
    """
    gaps: list[int] = []
    cur = prev
    tip = cur
    for i, link in enumerate(ledger):
        if link.get("prev") != cur:
            gaps.append(i)
            # still advance tip from claimed commit if present
            tip = link.get("commit", tip)
            cur = link.get("commit", cur)
            continue
        pk = pack(link["trits"])
        expected = side_commit(cur, pk, link["text"])
        if link.get("commit") != expected:
            gaps.append(i)
        rc = rate_lock_commit(cur, pk)
        if link.get("rate_commit") != rc and i not in gaps:
            gaps.append(i)
        tip = link["commit"]
        cur = link["commit"]
    return {"ok": len(gaps) == 0, "gaps": gaps, "tip": tip, "n": len(ledger)}


def self_check() -> dict[str, Any]:
    """Assert bind/ports/flags/rate, pack vector, ledger verify, backfill."""
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert MINT is False and SOCKET is False and LAYER_ONE is False
    assert FETCH is False and UE5_LAUNCH is False and RELEASED == 0
    assert RATE == 0.05

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    assert unpack(vec, 7) == [1, 0, -1, -1, 1, 0, 1]

    ledger: list[dict[str, Any]] = []
    a = append_receipt(ledger, GENESIS, [1, 0, -1], "alpha")
    b = append_receipt(ledger, a["commit"], [0, 1, 1], "beta")
    v = verify_ledger(ledger)
    assert v["ok"] is True and v["tip"] == b["commit"]

    tampered = [dict(ledger[0]), dict(ledger[1])]
    tampered[1]["text"] = "TAMPER"
    assert verify_ledger(tampered)["ok"] is False

    bf = backfill_check(ledger)
    assert bf["ok"] is True and bf["gaps"] == [] and bf["n"] == 2

    gapped = [dict(ledger[0]), dict(ledger[1])]
    gapped[1]["prev"] = "deadbeefdeadbeef"
    bf2 = backfill_check(gapped)
    assert bf2["ok"] is False and 1 in bf2["gaps"]

    pk = pack([1, 0, -1])
    r1 = rate_lock_commit(GENESIS, pk)
    r2 = rate_lock_commit(GENESIS, pk)
    assert r1 == r2 and len(r1) == 64

    engines = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")
    return {
        "ok": True,
        "bind": BIND,
        "ports": list(PORTS),
        "rate": RATE,
        "pack_vector": vec.hex(),
        "engines": list(engines),
        "tip": v["tip"],
        "backfill_ok": bf["ok"],
    }


if __name__ == "__main__":
    try:
        result = self_check()
        print(result)
        sys.exit(0)
    except AssertionError as e:
        print({"ok": False, "error": str(e) or "assertion failed"})
        sys.exit(1)
    except Exception as e:
        print({"ok": False, "error": repr(e)})
        sys.exit(1)
