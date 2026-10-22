"""Live beta step 6 "no deletes" for the receipt ledger itself: append-only snapshot audit.

Roadmap item: JuniorLLM docs/BETA_TO_OS.md "Live beta" step 6
("No deletes. No >8GB pull. bitnetd on `127.0.0.1:8765` only").
Quant Chief pair B pick, 2026-10-22 10:13 MT (Live beta step 6).
Side-Commit & Rate Lock piece: live-beta receipt and ledger at rate 0.05.
Handshake & Ports covers the pull-cap policy side in JuniorLLM
ports/live_beta_step6_pull_cap_policy_port_map.py; the Trit Pack side audits
git name-status / du / ss captures. Neither asks whether the receipt ledger the
live beta writes was itself kept append-only between two snapshots, which is
what "no deletes" means for the receipts. That is the new capability here.

Given an earlier and a later snapshot of a JSONL receipt ledger (one receipt
per line: prev, trits, text, commit, rate, rate_lock, optional bind), it checks:
  * P. prefix: every earlier line is present, byte-identical, at the same
    index in the later snapshot (no receipt deleted, reordered or rewritten).
  * G. growth: the later snapshot is at least as long as the earlier one.
  * C. chain: each receipt's prev is the previous commit (genesis "0"*16) and
    commit == sha256(prev || pack || text)[:16].
  * R. rate lock: rate == 0.05 and rate_lock == sha256(prev || pack || b"0.05")
    full hexdigest (JuniorHome docs/JUNIORS_RATE.md).
  * B. bind: any receipt that records a bind says 127.0.0.1 (8765 for
    bitnetd); 0.0.0.0, [::] and * are refused.
Each check becomes an audit receipt, and the audit receipts chain with the same
close rule. backfill_check() lists the broken indices per check.

Read-only: it reads two local files you point it at (or the built-in fixtures).
It never runs git, a subprocess, a socket, or the network; it never writes or
truncates a ledger. It does not import, wrap, or re-derive any other team file.

Stdlib only. Close: sha256(prev || pack || text)[:16], i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded. Compatible engines: web3node,
stocksnode, JuniorLLM, BitNet-mlx.
Ports: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1 only.

Run: python3 live_beta_step6_ledger_no_delete_receipt.py --selftest
     python3 live_beta_step6_ledger_no_delete_receipt.py --before A.jsonl --after B.jsonl
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
BIND = "127.0.0.1"
BITNETD = "127.0.0.1:8765"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")

MINT = False
SOCKET = False
LAYER_ONE = False
FETCH = False
UE5_LAUNCH = False
MODEL_PULL = False
RELEASED = 0

_ENC = {0: 0, 1: 1, -1: 2}


def pack(trits) -> bytes:
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


def side_commit(prev: str, pk: bytes, text: str) -> str:
    """sha256(prev || pack || text)[:16]."""
    return hashlib.sha256(prev.encode() + pk + text.encode()).hexdigest()[:16]


def rate_lock(prev: str, pk: bytes) -> str:
    """sha256(prev || pack || b"0.05") full hexdigest."""
    return hashlib.sha256(prev.encode() + pk + RATE_BYTES).hexdigest()


def make_receipt(prev: str, trits, text: str, bind: str | None = None) -> dict:
    pk = pack(trits)
    r = {"prev": prev, "trits": list(trits), "text": text,
         "commit": side_commit(prev, pk, text), "rate": RATE,
         "rate_lock": rate_lock(prev, pk)}
    if bind is not None:
        r["bind"] = bind
    return r


def to_jsonl(receipts) -> str:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in receipts)


def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def _bind_ok(bind: Any) -> bool:
    """Loopback only: "127.0.0.1" or "127.0.0.1:<port>". Wildcards never match."""
    return isinstance(bind, str) and (bind == BIND or bind.startswith(BIND + ":"))


def audit(before_text: str, after_text: str) -> dict:
    """Compare two ledger snapshots. Returns per-check broken indices and a verdict."""
    before, after = _lines(before_text), _lines(after_text)
    broken: dict[str, list[int]] = {"P": [], "G": [], "C": [], "R": [], "B": []}
    for i, ln in enumerate(before):
        if i >= len(after) or after[i] != ln:
            broken["P"].append(i)
    if len(after) < len(before):
        broken["G"].append(len(after))
    prev = GENESIS
    for i, ln in enumerate(after):
        try:
            r = json.loads(ln)
            pk = pack(r["trits"])
            if r["prev"] != prev or r["commit"] != side_commit(prev, pk, r["text"]):
                broken["C"].append(i)
            if r.get("rate") != RATE or r.get("rate_lock") != rate_lock(r["prev"], pk):
                broken["R"].append(i)
            if "bind" in r:
                b = r["bind"]
                ok = _bind_ok(b) and (not b.startswith(BIND + ":") or b == BITNETD)
                if not ok:
                    broken["B"].append(i)
            prev = r.get("commit", prev)
        except (ValueError, KeyError, TypeError):
            broken["C"].append(i)
            broken["R"].append(i)
    trits = [1 if not broken[k] else -1 for k in "PGCRB"]
    chain = []
    aprev = GENESIS
    for k, t in zip("PGCRB", trits):
        rec = make_receipt(aprev, [t], f"step6.ledger.{k}={t}")
        chain.append(rec)
        aprev = rec["commit"]
    return {
        "ok": all(t == 1 for t in trits),
        "before_n": len(before),
        "after_n": len(after),
        "appended": max(0, len(after) - len(before)),
        "broken": broken,
        "trits": trits,
        "audit_chain": chain,
        "tip": aprev,
        "rate": RATE,
        "close": "sha256(prev || pack || text)[:16]",
        "ports": list(PORTS),
        "engines": list(ENGINES),
    }


def backfill_check(result: dict) -> dict:
    """Indices to backfill per check; empty dict when the ledger is clean."""
    return {k: v for k, v in result["broken"].items() if v}


def _fixture() -> list[dict]:
    out, prev = [], GENESIS
    for trits, text, bind in (([1, 1, 1], "live_beta.step1.health rc=0", None),
                              ([1, 0, 1], "live_beta.step5.backfill_check rc=0", None),
                              ([1], "live_beta.step6.bitnetd", BITNETD)):
        r = make_receipt(prev, trits, text, bind)
        out.append(r)
        prev = r["commit"]
    return out


def selftest() -> dict:
    assert BIND == "127.0.0.1" and BITNETD == "127.0.0.1:8765"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL)
    assert RELEASED == 0 and abs(RATE - 0.05) < 1e-12
    # pack vector 4a44: [1,0,-1,-1,1,0,1] -> 0x4a 0x44
    assert pack([1, 0, -1, -1, 1, 0, 1]).hex() == "4a44"
    full = _fixture()
    before = to_jsonl(full[:2])
    after = to_jsonl(full)
    good = audit(before, after)
    assert good["ok"] and good["appended"] == 1 and backfill_check(good) == {}
    # deleted receipt: drop index 1 and re-chain the rest so only P/G can catch it
    dropped = [full[0], make_receipt(full[0]["commit"], [1], "live_beta.step6.bitnetd", BITNETD)]
    r = audit(after, to_jsonl(dropped))
    assert not r["ok"] and r["broken"]["P"] == [1, 2] and r["broken"]["G"] == [2]
    # rewritten text in place
    bad = [dict(x) for x in full]
    bad[0]["text"] = "live_beta.step1.health rc=1"
    r = audit(before, to_jsonl(bad))
    assert r["broken"]["P"] == [0] and 0 in r["broken"]["C"]
    # rate drift
    bad = [dict(x) for x in full]
    bad[2]["rate"] = 0.06
    r = audit(before, to_jsonl(bad))
    assert r["broken"]["R"] == [2] and not r["broken"]["P"]
    # wildcard bind refused
    wild = full[:2] + [make_receipt(full[1]["commit"], [1], "live_beta.step6.bitnetd", "0.0.0.0:8765")]
    r = audit(before, to_jsonl(wild))
    assert r["broken"]["B"] == [2]
    # wrong loopback port refused
    port = full[:2] + [make_receipt(full[1]["commit"], [1], "live_beta.step6.bitnetd", "127.0.0.1:9000")]
    assert audit(before, to_jsonl(port))["broken"]["B"] == [2]
    # audit chain is deterministic and verifies
    again = audit(before, after)
    assert again["tip"] == good["tip"] and len(good["tip"]) == 16
    p = GENESIS
    for rec in good["audit_chain"]:
        assert rec["prev"] == p and rec["commit"] == side_commit(p, pack(rec["trits"]), rec["text"])
        p = rec["commit"]
    return {"ok": True, "tip": good["tip"], "rate": RATE, "bind": BIND,
            "ports": list(PORTS), "engines": list(ENGINES),
            "close": "sha256(prev || pack || text)[:16]"}


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        print(json.dumps(selftest(), sort_keys=True))
        return 0
    if "--before" in argv and "--after" in argv:
        with open(argv[argv.index("--before") + 1], encoding="utf-8") as fh:
            b = fh.read()
        with open(argv[argv.index("--after") + 1], encoding="utf-8") as fh:
            a = fh.read()
        res = audit(b, a)
        out = {k: res[k] for k in ("ok", "before_n", "after_n", "appended", "trits", "tip")}
        out["backfill_check"] = backfill_check(res)
        print(json.dumps(out, sort_keys=True))
        return 0 if res["ok"] else 1
    print(__doc__.strip().splitlines()[-2].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
