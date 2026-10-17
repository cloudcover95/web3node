"""Asahi MLX probe receipt ledger: offline probe receipts + side-commit + rate lock.

ROADMAP item: JuniorHome docs/ROADMAP.md #4 Asahi MLX ("probe only from
automations"). This is pair B's receipt and ledger piece for that item; the
matching handshake/port check is Handshake & Ports' JuniorHome
ports/asahi_mlx_probe_handshake.py. This file is a new capability: it never
imports, wraps, tests, rewrites, or re-derives that file,
JuniorHome web3node/advance_asahi_mlx.py, or any other team file.
Advances live-beta receipt chains / backfill_check at rate 0.05.

What it records: one receipt per probe snapshot that an automation hands in
(a plain dict of declared facts). Each fact becomes one trit, and the receipt
says whether the probe counts (origin "automation", operator opt-in, no leak)
and whether the declared box is MLX-ready (Asahi kernel, Metal/AGX GPU, mlx
package present). Offline and probe only: no hardware calls, no platform or
sysfs reads, no subprocess, never imports mlx, no model load, no model pull,
no download, no network, no sockets, no UE5 launch.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Ports touched: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1.

Run: python3 asahi_mlx_probe_receipt_ledger.py --selftest
     python3 asahi_mlx_probe_receipt_ledger.py --facts '{"origin":"automation",...}'
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Mapping

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
ROADMAP_ITEM = "JuniorHome docs/ROADMAP.md #4 Asahi MLX - probe only from automations"
PROBE_ORIGIN = "automation"

MINT = False
SOCKET = False
LAYER_ONE = False
FETCH = False
UE5_LAUNCH = False
MODEL_PULL = False
MLX_IMPORT = False
HARDWARE_CALL = False
RELEASED = 0
BIND = "127.0.0.1"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
COMPATIBLE_ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")

# Declared readiness facts: True -> 1, None/missing -> 0 (unknown), False -> -1.
READY_KEYS = ("asahi_kernel", "agx_gpu", "metal_declared", "mlx_present")
# Probe-only guards: these must be False (or absent). True is a leak.
LEAK_KEYS = ("mlx_imported", "model_loaded", "model_pulled", "downloaded", "ue5_launched")

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


def _declared(v: Any) -> int:
    if v is True:
        return 1
    if v is False:
        return -1
    return 0


def audit_probe(facts: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Turn a declared probe snapshot into trits. Reads only the dict it is given."""
    facts = dict(facts or {})
    origin = str(facts.get("origin", ""))
    bind = str(facts.get("bind", BIND))
    origin_t = 1 if origin == PROBE_ORIGIN else -1
    opt_t = 1 if facts.get("opt_in") is True else -1
    bind_t = 1 if bind == BIND else -1
    ready_trits = [_declared(facts.get(k)) for k in READY_KEYS]
    leaks = [k for k in LEAK_KEYS if facts.get(k) is True]
    if bind_t != 1:
        leaks.append("bind")
    guard_t = -1 if leaks else 1
    trits = [origin_t, opt_t, bind_t, guard_t] + ready_trits
    counted = origin_t == 1 and opt_t == 1 and guard_t == 1
    return {
        "item": ROADMAP_ITEM,
        "origin": origin,
        "bind": bind,
        "ready": {k: facts.get(k) for k in READY_KEYS},
        "leaks": leaks,
        "trits": trits,
        "counted": counted,
        "mlx_ready": counted and all(t == 1 for t in ready_trits),
        "mlx_import": MLX_IMPORT,
        "model_pull": MODEL_PULL,
        "hardware_call": HARDWARE_CALL,
        "fetch": FETCH,
    }


def audit_text(audit: dict[str, Any]) -> str:
    return json.dumps(audit, sort_keys=True, separators=(",", ":"))


def append_probe_receipt(
    ledger: list[dict[str, Any]], prev: str, facts: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Audit one probe snapshot and append a receipt with side-commit and rate_commit."""
    audit = audit_probe(facts)
    trits = list(audit["trits"])
    text = audit_text(audit)
    pk = pack(trits)
    link = {
        "prev": prev,
        "trits": trits,
        "text": text,
        "counted": audit["counted"],
        "mlx_ready": audit["mlx_ready"],
        "commit": side_commit(prev, pk, text),
        "rate_commit": rate_lock_commit(prev, pk),
        "rate": RATE,
    }
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Live-beta backfill gate: contiguous chain; gaps lists broken links,
    manual lists probes not run from an automation or not opted in,
    leaks lists probes that imported, loaded, pulled, launched, or left 127.0.0.1."""
    gaps: list[int] = []
    manual: list[int] = []
    leaks: list[int] = []
    cur = prev
    for i, link in enumerate(ledger):
        try:
            pk = pack(link["trits"])
            body = json.loads(link["text"])
        except (KeyError, ValueError, TypeError):
            gaps.append(i)
            cur = link.get("commit", cur)
            continue
        if (
            link.get("prev") != cur
            or link.get("commit") != side_commit(cur, pk, link["text"])
            or link.get("rate_commit") != rate_lock_commit(cur, pk)
            or link.get("rate") != RATE
            or body.get("trits") != link["trits"]
            or body.get("counted") != link.get("counted")
        ):
            gaps.append(i)
        if body.get("origin") != PROBE_ORIGIN or link["trits"][1] != 1:
            manual.append(i)
        if body.get("leaks"):
            leaks.append(i)
        cur = link.get("commit", cur)
    return {"ok": not gaps and not leaks, "gaps": gaps, "manual": manual,
            "leaks": leaks, "tip": cur, "n": len(ledger)}


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, known close, probe audits, tamper and gap detection."""
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL
                or MLX_IMPORT or HARDWARE_CALL)
    assert RELEASED == 0 and RATE == 0.05
    assert "mlx" not in sys.modules or not MLX_IMPORT

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known

    ready = {"origin": "automation", "opt_in": True, "asahi_kernel": True,
             "agx_gpu": True, "metal_declared": True, "mlx_present": True}
    a = audit_probe(ready)
    assert a["counted"] and a["mlx_ready"] and a["trits"] == [1, 1, 1, 1, 1, 1, 1, 1]
    blank = audit_probe()
    assert not blank["counted"] and blank["trits"][4:] == [0, 0, 0, 0]
    manual = audit_probe(dict(ready, origin="chat"))
    assert not manual["counted"] and manual["trits"][0] == -1
    loaded = audit_probe(dict(ready, model_loaded=True, mlx_imported=True))
    assert loaded["leaks"] == ["mlx_imported", "model_loaded"] and not loaded["counted"]
    wide = audit_probe(dict(ready, bind="192.168.1.20"))
    assert wide["trits"][2] == -1 and "bind" in wide["leaks"]
    no_mlx = audit_probe(dict(ready, mlx_present=False))
    assert no_mlx["counted"] and not no_mlx["mlx_ready"] and no_mlx["trits"][7] == -1

    ledger: list[dict[str, Any]] = []
    r0 = append_probe_receipt(ledger, GENESIS, ready)
    r1 = append_probe_receipt(ledger, r0["commit"], dict(ready, mlx_present=None))
    r2 = append_probe_receipt(ledger, r1["commit"], dict(ready, origin="chat"))
    bf = backfill_check(ledger)
    assert bf["ok"] and bf["gaps"] == [] and bf["n"] == 3 and bf["tip"] == r2["commit"]
    assert bf["manual"] == [2] and bf["leaks"] == []

    lk = list(ledger)
    append_probe_receipt(lk, r2["commit"], dict(ready, model_pulled=True))
    bl = backfill_check(lk)
    assert bl["leaks"] == [3] and not bl["ok"] and bl["gaps"] == []

    t = [dict(x) for x in ledger]
    t[1] = dict(t[1], text=t[1]["text"].replace('"mlx_present":null', '"mlx_present":true'))
    assert 1 in backfill_check(t)["gaps"]
    r = [dict(x) for x in ledger]
    r[0] = dict(r[0], rate_commit=hashlib.sha256(b"x").hexdigest())
    assert 0 in backfill_check(r)["gaps"]
    d = [ledger[0], ledger[2]]
    assert 1 in backfill_check(d)["gaps"]

    return {
        "ok": True,
        "item": ROADMAP_ITEM,
        "bind": BIND,
        "ports": list(PORTS),
        "rate": RATE,
        "pack_vector": vec.hex(),
        "close_home_4a44": known,
        "engines": list(COMPATIBLE_ENGINES),
        "tip": bf["tip"],
        "flags": {"mint": MINT, "socket": SOCKET, "layer_one": LAYER_ONE, "fetch": FETCH,
                  "ue5_launch": UE5_LAUNCH, "model_pull": MODEL_PULL,
                  "mlx_import": MLX_IMPORT, "hardware_call": HARDWARE_CALL,
                  "released": RELEASED},
    }


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    facts: dict[str, Any] = {}
    if "--facts" in argv:
        i = argv.index("--facts")
        facts = json.loads(argv[i + 1]) if i + 1 < len(argv) else {}
    ledger: list[dict[str, Any]] = []
    link = append_probe_receipt(ledger, GENESIS, facts)
    print(json.dumps({"receipt": link, "backfill": backfill_check(ledger)}, sort_keys=True))
    return 0 if link["counted"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
