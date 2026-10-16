"""GGUF operator receipt ledger: JUNIOR_GGUF presence receipts + side-commit + rate lock.

ROADMAP item: JuniorHome docs/ROADMAP.md #2 GGUF ("operator sets JUNIOR_GGUF.
Bots do not download. web3node/probe_future.py"). This file is a separate
receipt/ledger path; it never imports, wraps, or rewrites probe_future.py.
Advances live-beta receipt chains / backfill_check at rate 0.05.

What it records: whether the operator set JUNIOR_GGUF, the basename, whether
the path exists, its size and .gguf suffix, all from os.stat only. It never
opens, hashes, downloads, or loads a model file. No network, no sockets.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Run: python3 gguf_receipt_ledger.py --selftest
"""
from __future__ import annotations

import json
import os
import hashlib
import sys
import tempfile
from typing import Any, Mapping

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
ENV_KEY = "JUNIOR_GGUF"

MINT = False
SOCKET = False
LAYER_ONE = False
FETCH = False
UE5_LAUNCH = False
MODEL_PULL = False
RELEASED = 0
BIND = "127.0.0.1"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
COMPATIBLE_ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")

_TRIT_TO_BITS = {0: 0, 1: 1, -1: 2}


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


def side_commit(prev: str, pk: bytes, text: str) -> str:
    """Close rule: sha256(prev || pack || text)[:16]."""
    return hashlib.sha256(prev.encode() + pk + text.encode()).hexdigest()[:16]


def rate_lock_commit(prev: str, pk: bytes) -> str:
    """Rate lock: sha256(prev || pack || b"0.05") full hexdigest."""
    return hashlib.sha256(prev.encode() + pk + RATE_BYTES).hexdigest()


def gguf_observation(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Observe the operator-set JUNIOR_GGUF with os.stat only. Never opens the file."""
    env = os.environ if env is None else env
    raw = env.get(ENV_KEY, "")
    obs: dict[str, Any] = {
        "env_set": bool(raw),
        "name": os.path.basename(raw) if raw else "",
        "exists": False,
        "size": 0,
        "gguf_suffix": raw.lower().endswith(".gguf") if raw else False,
        "download": False,
        "model_pull": MODEL_PULL,
    }
    if raw:
        try:
            st = os.stat(raw)
            obs["exists"] = True
            obs["size"] = int(st.st_size)
        except OSError:
            pass
    return obs


def observation_trits(obs: Mapping[str, Any]) -> list[int]:
    """Map observation to trits: env_set, exists, suffix -> 1 yes / -1 no; size>0 -> 1 else 0."""
    yn = lambda b: 1 if b else -1  # noqa: E731
    return [
        yn(obs["env_set"]),
        yn(obs["exists"]),
        yn(obs["gguf_suffix"]),
        1 if obs["size"] > 0 else 0,
    ]


def observation_text(obs: Mapping[str, Any]) -> str:
    """Canonical receipt text: sorted compact JSON."""
    return json.dumps(dict(obs), sort_keys=True, separators=(",", ":"))


def append_gguf_receipt(
    ledger: list[dict[str, Any]], prev: str, obs: Mapping[str, Any]
) -> dict[str, Any]:
    """Append one GGUF receipt with side-commit and rate_commit."""
    trits = observation_trits(obs)
    text = observation_text(obs)
    pk = pack(trits)
    link = {
        "prev": prev,
        "trits": trits,
        "text": text,
        "commit": side_commit(prev, pk, text),
        "rate_commit": rate_lock_commit(prev, pk),
        "rate": RATE,
    }
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Live-beta backfill gate: contiguous chain; gaps lists broken indices."""
    gaps: list[int] = []
    cur = prev
    for i, link in enumerate(ledger):
        pk = pack(link["trits"])
        if (
            link.get("prev") != cur
            or link.get("commit") != side_commit(cur, pk, link["text"])
            or link.get("rate_commit") != rate_lock_commit(cur, pk)
            or link.get("rate") != RATE
        ):
            gaps.append(i)
        cur = link.get("commit", cur)
    return {"ok": not gaps, "gaps": gaps, "tip": cur, "n": len(ledger)}


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, GGUF receipts, tamper and gap detection."""
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL)
    assert RELEASED == 0 and RATE == 0.05 and RATE_BYTES == b"0.05"
    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()

    unset = gguf_observation({})
    assert unset["env_set"] is False and unset["exists"] is False
    missing = gguf_observation({ENV_KEY: "/nonexistent/junior-2b4t.gguf"})
    assert missing["env_set"] and not missing["exists"] and missing["gguf_suffix"]

    with tempfile.TemporaryDirectory() as td:
        fake = os.path.join(td, "fake-i2s.gguf")
        with open(fake, "wb") as fh:
            fh.write(b"GGUF\x00\x00\x00\x00")
        present = gguf_observation({ENV_KEY: fake})
    assert present["exists"] and present["size"] == 8 and present["name"] == "fake-i2s.gguf"
    assert present["download"] is False

    ledger: list[dict[str, Any]] = []
    a = append_gguf_receipt(ledger, GENESIS, unset)
    b = append_gguf_receipt(ledger, a["commit"], missing)
    c = append_gguf_receipt(ledger, b["commit"], present)
    bf = backfill_check(ledger)
    assert bf["ok"] and bf["gaps"] == [] and bf["tip"] == c["commit"] and bf["n"] == 3
    assert len(c["commit"]) == 16 and len(c["rate_commit"]) == 64

    tampered = [dict(x) for x in ledger]
    tampered[1]["text"] = "TAMPER"
    assert backfill_check(tampered)["gaps"] == [1]
    gapped = [dict(x) for x in ledger]
    gapped[2]["prev"] = "deadbeefdeadbeef"
    assert 2 in backfill_check(gapped)["gaps"]
    relock = [dict(x) for x in ledger]
    relock[0]["rate"] = 0.06
    assert 0 in backfill_check(relock)["gaps"]

    return {
        "ok": True,
        "item": "ROADMAP #2 GGUF",
        "bind": BIND,
        "ports": list(PORTS),
        "rate": RATE,
        "pack_vector": vec.hex(),
        "engines": list(COMPATIBLE_ENGINES),
        "tip": bf["tip"],
    }


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        try:
            print(self_check())
            return 0
        except AssertionError as e:
            print({"ok": False, "error": str(e) or "assertion failed"})
            return 1
    obs = gguf_observation()
    ledger: list[dict[str, Any]] = []
    append_gguf_receipt(ledger, GENESIS, obs)
    print(json.dumps({"receipt": ledger[0], "backfill": backfill_check(ledger)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
