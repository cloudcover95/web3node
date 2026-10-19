"""19:00 second-slice age gate: receipt-age verdict + side-commit + rate lock.

Roadmap item: JuniorHome docs/ROADMAP.md, Automations (current) ON,
"19:00 - second slice if receipt >45 min old", as named for pair B by Quant
Chief on 2026-10-19 14:12 MT (BETA_TO_OS Live beta steps 4-5 are already
filed by BitNet-mlx 9244444 and JuniorQuant adfb204). The matching handshake
or port check belongs to Handshake & Ports in a different file.

The gap it fills: LLC's JuniorHome web3node/advance_second_slice_receipt.py
stamps the item as constant flags; nothing evaluates the condition itself.
This file never imports, runs, wraps, tests, rewrites, or re-derives that file
or any other team file, including my own earlier ledgers. New capability:
  1. Age gate: from caller-declared receipt times (ISO 8601, timezone
     required) it takes the newest receipt at or before the 19:00 slot and
     computes its age in seconds. Strictly older than 45 min (2700 s) means
     due (+1); 0..2700 s means not due (0); a naive or unparseable time, or a
     slot that is not 19:00 local, is invalid (-1). No receipt at all is due
     (+1, cause "no_receipt"). Receipts after the slot are counted, not used.
  2. Action check: the declared fired flag against the gate:
     fired and due, or skipped and not due, is +1; fired while fresh is -1
     "double_fire"; skipped while stale is -1 "missed"; undeclared is 0.
  3. Paused-slot guard: a declared fire at 07:00 or 13:00 (paused per the
     roadmap, "Do not recreate paused slots") is a breach.
  4. Receipt chain: each day's receipt is a trit vector closed as
     sha256(prev || pack || text)[:16] with a rate lock beside it.
  5. backfill_check: verifies the chain, recomputes every verdict, and lists
     gap days in a declared date range, duplicate days, misses, double fires,
     invalid gates, paused-slot breaches, and guard breaches.
Offline: no clock reads, no subprocess, no file reads, no network, no sockets,
no model pull, no GGUF download, no UE5 launch. The caller declares all times.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Ports touched: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1.

Run: python3 second_slice_age_gate_ledger.py --selftest
     python3 second_slice_age_gate_ledger.py --gate '{"slot":"2026-10-19T19:00:00-06:00","receipts":["2026-10-19T18:00:00-06:00"],"fired":true}'
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from typing import Any, Iterable, Mapping

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
ROADMAP_ITEM = (
    "JuniorHome docs/ROADMAP.md Automations ON: "
    "19:00 - second slice if receipt >45 min old"
)
THRESHOLD_S = 45 * 60
SLOT_HOUR = 19
PAUSED_SLOTS = ("07:00", "13:00")

MINT = False
SOCKET = False
LAYER_ONE = False
FETCH = False
UE5_LAUNCH = False
MODEL_PULL = False
SUBPROCESS = False
CLOCK_READ = False
RELEASED = 0
BIND = "127.0.0.1"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
COMPATIBLE_ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")

# Trit order inside every receipt.
FIELDS = ("slot", "tz", "receipt", "due", "action", "paused", "bind", "guard")

_ENC = {0: 0, 1: 1, -1: 2}
_DEC = {0: 0, 1: 1, 2: -1}


def pack(trits: Iterable[int]) -> bytes:
    """Balanced trits as 2-bit i2s codes (0->0, 1->1, -1->2), MSB first, zero-padded."""
    acc = bits = 0
    out = bytearray()
    for t in trits:
        if t not in _ENC or isinstance(t, bool):
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


def rate_lock_commit(prev: str, pk: bytes) -> str:
    """Rate lock: sha256(prev || pack || b"0.05") full hexdigest."""
    return hashlib.sha256(prev.encode() + pk + RATE_BYTES).hexdigest()


def guard() -> list[str]:
    bad = []
    for name, val in (("mint", MINT), ("socket", SOCKET), ("layer_one", LAYER_ONE),
                      ("fetch", FETCH), ("ue5_launch", UE5_LAUNCH),
                      ("model_pull", MODEL_PULL), ("subprocess", SUBPROCESS),
                      ("clock_read", CLOCK_READ)):
        if val:
            bad.append(name)
    if RELEASED != 0:
        bad.append("released")
    if BIND != "127.0.0.1":
        bad.append("bind")
    if RATE != 0.05:
        bad.append("rate")
    return bad


def parse_time(s: Any) -> _dt.datetime | None:
    """ISO 8601 with an explicit offset; naive or bad input gives None."""
    if not isinstance(s, str) or not s:
        return None
    try:
        t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None or t.utcoffset() is None:
        return None
    return t


def gate(decl: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One day's verdict from declared slot, receipts, fired, and paused_fired."""
    d = dict(decl or {})
    slot = parse_time(d.get("slot"))
    causes: list[str] = []
    tz_t = 1 if slot is not None else -1
    slot_t = 1 if slot is not None and slot.hour == SLOT_HOUR and slot.minute == 0 else -1
    if slot is None:
        causes.append("bad_slot")
    elif slot_t == -1:
        causes.append("slot_not_19:00")

    raw = d.get("receipts") or []
    if isinstance(raw, str):
        raw = [raw]
    parsed = [parse_time(r) for r in raw]
    bad_rx = sum(1 for p in parsed if p is None)
    if bad_rx:
        tz_t = -1
        causes.append("bad_receipt_time")
    before = [p for p in parsed if p is not None and slot is not None and p <= slot]
    after = [p for p in parsed if p is not None and slot is not None and p > slot]

    age_s: float | None = None
    if slot is None or slot_t == -1 or bad_rx:
        due, rx_t = -1, -1
        causes.append("gate_invalid")
    elif not before:
        due, rx_t = 1, 0
        causes.append("no_receipt")
    else:
        newest = max(before)
        age_s = (slot - newest).total_seconds()
        rx_t = 1
        due = 1 if age_s > THRESHOLD_S else 0
        causes.append("stale" if due == 1 else "fresh")

    fired = d.get("fired")
    if due == -1 or fired is None or not isinstance(fired, bool):
        action = 0 if due != -1 else -1
        if due != -1:
            causes.append("fired_undeclared")
    elif fired and due == 1:
        action = 1
    elif not fired and due == 0:
        action = 1
    elif fired:
        action = -1
        causes.append("double_fire")
    else:
        action = -1
        causes.append("missed")

    paused = [p for p in (d.get("paused_fired") or []) if p in PAUSED_SLOTS]
    paused_t = -1 if paused else 1
    if paused:
        causes.append("paused_slot_recreated")
    g = guard()
    trits = [slot_t, tz_t, rx_t, due, action, paused_t,
             1 if BIND == "127.0.0.1" else -1, -1 if g else 1]
    day = slot.date().isoformat() if slot is not None else None
    return {
        "day": day,
        "slot": d.get("slot"),
        "age_s": age_s,
        "threshold_s": THRESHOLD_S,
        "receipts_used": len(before),
        "receipts_after_slot": len(after),
        "fired": fired if isinstance(fired, bool) else None,
        "due": due,
        "action": action,
        "paused_fired": paused,
        "causes": causes,
        "trits": dict(zip(FIELDS, trits)),
        "vector": trits,
        "guard": g,
        "rate": RATE,
        "bind": BIND,
        "ports": list(PORTS),
    }


def _text(v: Mapping[str, Any]) -> str:
    body = {k: v[k] for k in ("day", "slot", "age_s", "fired", "due", "action",
                              "paused_fired", "causes")}
    body["item"] = ROADMAP_ITEM
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def append(ledger: list[dict[str, Any]], decl: Mapping[str, Any]) -> dict[str, Any]:
    """Gate one day and chain it onto the ledger (returns the new entry)."""
    prev = ledger[-1]["commit"] if ledger else GENESIS
    v = gate(decl)
    pk = pack(v["vector"])
    text = _text(v)
    entry = {"decl": dict(decl), "prev": prev, "vector": v["vector"], "text": text,
             "commit": side_commit(prev, pk, text), "rate_lock": rate_lock_commit(prev, pk),
             "verdict": v}
    ledger.append(entry)
    return entry


def backfill_check(ledger: list[Mapping[str, Any]], start: str | None = None,
                   end: str | None = None) -> dict[str, Any]:
    """Verify chain + recompute verdicts; list gaps, dupes, misses, doubles, breaches."""
    prev = GENESIS
    tamper: list[int] = []
    days: dict[str, int] = {}
    missed, double, invalid, paused, breaches = [], [], [], [], []
    for i, e in enumerate(ledger):
        v = gate(e.get("decl"))
        pk = pack(v["vector"])
        text = _text(v)
        if (e.get("prev") != prev or e.get("vector") != v["vector"] or e.get("text") != text
                or e.get("commit") != side_commit(prev, pk, text)
                or e.get("rate_lock") != rate_lock_commit(prev, pk)):
            tamper.append(i)
        prev = e.get("commit", prev)
        if v["day"]:
            days[v["day"]] = days.get(v["day"], 0) + 1
        if "missed" in v["causes"]:
            missed.append(v["day"])
        if "double_fire" in v["causes"]:
            double.append(v["day"])
        if v["due"] == -1:
            invalid.append(i)
        if v["paused_fired"]:
            paused.append(v["day"])
        if v["guard"]:
            breaches.append(i)
    dupes = sorted(k for k, n in days.items() if n > 1)
    gaps: list[str] = []
    if start and end:
        try:
            a, b = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
        except ValueError:
            a = b = None
            invalid.append("range")
        while a is not None and b is not None and a <= b:
            if a.isoformat() not in days:
                gaps.append(a.isoformat())
            a += _dt.timedelta(days=1)
    ok = not (tamper or missed or double or invalid or paused or breaches or dupes or gaps)
    return {"ok": ok, "n": len(ledger), "tip": prev, "tamper": tamper, "gaps": gaps,
            "dupes": dupes, "missed": missed, "double_fire": double, "invalid": invalid,
            "paused_breach": paused, "breaches": breaches, "rate": RATE}


def self_check() -> dict[str, Any]:
    """Flags, vector 4a44, known close, gate boundaries, actions, paused, chain, tamper, gaps."""
    assert BIND == "127.0.0.1" and not guard(), guard()
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert RELEASED == 0 and RATE == 0.05
    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    assert unpack(vec, 7) == [1, 0, -1, -1, 1, 0, 1]
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known
    assert len(rate_lock_commit(GENESIS, vec)) == 64

    slot = "2026-10-19T19:00:00-06:00"
    g = gate({"slot": slot, "receipts": ["2026-10-19T18:15:00-06:00"], "fired": False})
    assert g["age_s"] == 2700 and g["due"] == 0 and g["action"] == 1, g  # exactly 45 min: fresh
    g = gate({"slot": slot, "receipts": ["2026-10-19T18:14:59-06:00"], "fired": True})
    assert g["due"] == 1 and g["action"] == 1 and "stale" in g["causes"], g
    g = gate({"slot": slot, "receipts": ["2026-10-20T00:30:00Z"], "fired": True})
    assert g["age_s"] == 1800 and g["due"] == 0 and g["action"] == -1, g  # UTC offset honored
    assert "double_fire" in g["causes"]
    g = gate({"slot": slot, "receipts": ["2026-10-19T17:00:00-06:00",
                                         "2026-10-19T19:30:00-06:00"], "fired": False})
    assert g["due"] == 1 and "missed" in g["causes"] and g["receipts_after_slot"] == 1, g
    g = gate({"slot": slot, "receipts": [], "fired": True})
    assert g["due"] == 1 and "no_receipt" in g["causes"] and g["trits"]["receipt"] == 0, g
    g = gate({"slot": slot, "receipts": ["2026-10-19T18:00:00"], "fired": True})
    assert g["due"] == -1 and g["trits"]["tz"] == -1, g  # naive time rejected
    g = gate({"slot": "2026-10-19T13:00:00-06:00", "receipts": [], "fired": True})
    assert g["trits"]["slot"] == -1 and "slot_not_19:00" in g["causes"], g
    g = gate({"slot": slot, "receipts": ["2026-10-19T18:50:00-06:00"]})
    assert g["action"] == 0 and "fired_undeclared" in g["causes"], g
    g = gate({"slot": slot, "receipts": [], "fired": True, "paused_fired": ["07:00"]})
    assert g["trits"]["paused"] == -1 and "paused_slot_recreated" in g["causes"], g

    led: list[dict[str, Any]] = []
    append(led, {"slot": "2026-10-17T19:00:00-06:00",
                 "receipts": ["2026-10-17T01:40:00-06:00"], "fired": True})
    append(led, {"slot": "2026-10-18T19:00:00-06:00",
                 "receipts": ["2026-10-18T18:40:00-06:00"], "fired": False})
    append(led, {"slot": "2026-10-19T19:00:00-06:00",
                 "receipts": ["2026-10-19T01:35:00-06:00"], "fired": True})
    bc = backfill_check(led, "2026-10-17", "2026-10-19")
    assert bc["ok"] and bc["n"] == 3 and bc["tip"] == led[-1]["commit"], bc
    assert led[1]["prev"] == led[0]["commit"]

    bad = json.loads(json.dumps(led))
    bad[1]["decl"]["fired"] = True
    bc = backfill_check(bad)
    assert not bc["ok"] and bc["tamper"] == [1] and bc["double_fire"] == ["2026-10-18"], bc
    bc = backfill_check(led[:1] + led[2:], "2026-10-17", "2026-10-19")
    assert bc["gaps"] == ["2026-10-18"] and 1 in bc["tamper"], bc

    led2: list[dict[str, Any]] = []
    append(led2, {"slot": slot, "receipts": ["2026-10-19T17:00:00-06:00"], "fired": False})
    append(led2, {"slot": slot, "receipts": [], "fired": True, "paused_fired": ["13:00"]})
    bc = backfill_check(led2)
    assert bc["missed"] == ["2026-10-19"] and bc["dupes"] == ["2026-10-19"], bc
    assert bc["paused_breach"] == ["2026-10-19"] and not bc["tamper"], bc

    return {"ok": True, "item": ROADMAP_ITEM, "rate": RATE, "threshold_s": THRESHOLD_S,
            "close": "sha256(prev || pack || text)[:16]", "close_home_4a44": known,
            "tip": led[-1]["commit"], "bind": BIND, "ports": list(PORTS),
            "engines": list(COMPATIBLE_ENGINES)}


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--gate":
        out = gate(json.loads(argv[1]))
        print(json.dumps(out, indent=2))
        return 0 if out["action"] == 1 and not out["guard"] else 1
    out = self_check()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] if sys.argv[1:] != ["--selftest"] else []))
