#!/usr/bin/env python3
"""16:45 daily audit: per-automation-row drift ledger (web3node engine).

Roadmap item: JuniorHome docs/ROADMAP.md, Automations, "16:45 daily audit"
(the remaining-engines part: BitNet-mlx, web3node, JuniorQuant). This is the
web3node piece. stocksnode 4eb7e33 receipts each audit *day section*; this file
adds a different capability: it receipts each *automation row* (Name, Schedule)
across days and flags schedule drift, rows that appear or vanish between days,
and audit run times that wander off 16:45 MDT. It does not import, wrap, test
or re-derive any other team file.

Side-Commit & Rate Lock piece: live-beta receipt and ledger at rate 0.05.

Input: the text of JuniorHome docs/AUTOMATION_AUDIT.md (local path or stdin).
Each "# Automation audit YYYY-MM-DD HH:MM MDT" section has a markdown table
| Name | Schedule (MDT) | Notes |. Per row per day it emits a receipt with
trits:
  present   +1 row is in this day's table, -1 missing vs. the previous day
  schedule  +1 same schedule as the previous day, 0 first sighting, -1 drift
  run_time  +1 section header says 16:45, 0 approximate ("~16:45"), -1 other
backfill_check lists missing calendar days, rows dropped, rows added, schedule
drifts and off-time runs.

Stdlib only. Close: sha256(prev || pack || text)[:16], i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded. Rate lock: rate 0.05 committed
beside the pack, sha256(prev || pack || b"0.05") (JuniorHome
docs/JUNIORS_RATE.md). Genesis "0"*16. Compatible engines: web3node,
stocksnode, JuniorLLM, BitNet-mlx, JuniorQuant.
Ports: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1 only.
mint/socket/layer_one/fetch/ue5_launch false. released 0. No network.

Usage:
  python3 daily_audit_1645_row_drift_ledger.py --selftest
  python3 daily_audit_1645_row_drift_ledger.py PATH/TO/AUTOMATION_AUDIT.md
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
BIND = "127.0.0.1"
ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx", "JuniorQuant")
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
FLAGS = {"mint": False, "socket": False, "layer_one": False,
         "fetch": False, "ue5_launch": False, "released": 0}
ITEM = "JuniorHome docs/ROADMAP.md Automations: 16:45 daily audit (web3node)"

_HDR = re.compile(r"^#\s*Automation audit\s+(\d{4}-\d{2}-\d{2})(.*)$")
_TIME = re.compile(r"(~?)(\d{1,2}):(\d{2})")


def pack(trits) -> bytes:
    """i2s 2-bit pack, 0->0, 1->1, -1->2, MSB first, zero-padded."""
    code = {0: 0, 1: 1, -1: 2}
    out, acc, n = bytearray(), 0, 0
    for t in trits:
        acc = (acc << 2) | code[int(t)]
        n += 1
        if n == 4:
            out.append(acc)
            acc, n = 0, 0
    if n:
        out.append(acc << (2 * (4 - n)))
    return bytes(out)


def side_commit(prev: str, pk: bytes, text: str) -> str:
    """sha256(prev || pack || text)[:16]."""
    return hashlib.sha256(prev.encode() + pk + text.encode()).hexdigest()[:16]


def rate_lock(prev: str, pk: bytes) -> str:
    """sha256(prev || pack || b"0.05")."""
    return hashlib.sha256(prev.encode() + pk + RATE_BYTES).hexdigest()


def receipt(prev: str, trits, text: str) -> dict:
    pk = pack(trits)
    return {"prev": prev, "trits": list(trits), "text": text,
            "commit": side_commit(prev, pk, text), "rate": RATE,
            "rate_lock": rate_lock(prev, pk)}


def parse(text: str):
    """Return [(day, header_tail, {name: schedule})] in file order."""
    sections, cur, in_tbl = [], None, False
    for line in text.splitlines():
        m = _HDR.match(line.strip())
        if m:
            cur = (m.group(1), m.group(2).strip(), {})
            sections.append(cur)
            in_tbl = False
            continue
        if cur is None or not line.strip().startswith("|"):
            in_tbl = False
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == "Name" and cells[1].startswith("Schedule"):
            in_tbl = True
            continue
        if not in_tbl or len(cells) < 2 or not cells[0] or set(cells[0]) <= set("-: "):
            continue
        cur[2].setdefault(cells[0], cells[1])
    return sections


def run_trit(tail: str) -> int:
    m = _TIME.search(tail)
    if not m:
        return -1
    if (int(m.group(2)), int(m.group(3))) != (16, 45):
        return -1
    return 0 if m.group(1) else 1


def build(text: str) -> dict:
    sections = parse(text)
    prev, chain = GENESIS, []
    last_rows: dict | None = None
    dropped, added, drift, off_time = [], [], [], []
    for day, tail, rows in sections:
        rt = run_trit(tail)
        if rt != 1:
            off_time.append(f"{day} {tail}".strip())
        names = list(rows)
        if last_rows is not None:
            for gone in last_rows:
                if gone not in rows:
                    dropped.append(f"{day}:{gone}")
                    r = receipt(prev, [-1, 0, rt], f"{day}|{gone}|-")
                    chain.append(r)
                    prev = r["commit"]
            for new in names:
                if new not in last_rows:
                    added.append(f"{day}:{new}")
        for name in names:
            sched = rows[name]
            if last_rows is None or name not in last_rows:
                st = 0
            elif last_rows[name] == sched:
                st = 1
            else:
                st = -1
                drift.append(f"{day}:{name}:{last_rows[name]}->{sched}")
            r = receipt(prev, [1, st, rt], f"{day}|{name}|{sched}")
            chain.append(r)
            prev = r["commit"]
        last_rows = rows
    days = sorted({d for d, _, _ in sections})
    missing = []
    if days:
        d0 = _dt.date.fromisoformat(days[0])
        d1 = _dt.date.fromisoformat(days[-1])
        have = set(days)
        while d0 <= d1:
            if d0.isoformat() not in have:
                missing.append(d0.isoformat())
            d0 += _dt.timedelta(days=1)
    return {
        "item": ITEM, "rate": RATE, "close": "sha256(prev || pack || text)[:16]",
        "rate_lock": "sha256(prev || pack || b'0.05')", "genesis": GENESIS,
        "bind": BIND, "engines": list(ENGINES), "ports": list(PORTS),
        "flags": FLAGS, "sections": len(sections), "receipts": len(chain),
        "tip": prev, "chain": chain,
        "backfill_check": {"missing_days": missing, "rows_dropped": dropped,
                           "rows_added": added, "schedule_drift": drift,
                           "off_time_runs": off_time,
                           "ok": not (missing or dropped or drift)},
    }


def verify(chain) -> bool:
    prev = GENESIS
    for r in chain:
        pk = pack(r["trits"])
        if r["prev"] != prev or r["commit"] != side_commit(prev, pk, r["text"]):
            return False
        if r["rate"] != RATE or r["rate_lock"] != rate_lock(prev, pk):
            return False
        prev = r["commit"]
    return True


_SAMPLE = """# Automation audit 2026-10-12 16:45 MDT
| Name | Schedule (MDT) | Notes |
|---|---|---|
| daily audit | daily 16:45 | this run |
| slot 19:00 | daily 19:00 | guard |

# Automation audit 2026-10-13 16:45 MDT
| Name | Schedule (MDT) | Notes |
|---|---|---|
| daily audit | daily 16:45 | this run |
| slot 19:00 | daily 19:00 | guard |

# Automation audit 2026-10-15 ~16:45 MDT (tip f88784e5)
| Name | Schedule (MDT) | Notes |
|---|---|---|
| daily audit | daily 16:50 | this run |
| weekly audit | Mon 17:00 | WEEKLY_AUDIT.md |

| Check | Result |
|---|---|
| layer_one | false |
"""


def selftest() -> int:
    assert pack([1, -1, 0, 1]) == bytes([0b01100001])
    assert pack([-1]) == bytes([0b10000000])
    assert side_commit(GENESIS, pack([1]), "x") == hashlib.sha256(
        GENESIS.encode() + bytes([0x40]) + b"x").hexdigest()[:16]
    out = build(_SAMPLE)
    bc = out["backfill_check"]
    assert out["sections"] == 3 and out["receipts"] == 7, out["receipts"]
    assert bc["missing_days"] == ["2026-10-14"]
    assert bc["rows_dropped"] == ["2026-10-15:slot 19:00"]
    assert bc["rows_added"] == ["2026-10-15:weekly audit"]
    assert bc["schedule_drift"] == ["2026-10-15:daily audit:daily 16:45->daily 16:50"]
    assert len(bc["off_time_runs"]) == 1 and bc["ok"] is False
    assert verify(out["chain"])
    assert all(r["rate"] == 0.05 for r in out["chain"])
    bad = [dict(r) for r in out["chain"]]
    bad[2]["text"] += "!"
    assert not verify(bad)
    assert out["bind"] == "127.0.0.1" and "0.0.0.0" not in json.dumps(out)
    assert not any(v for k, v in FLAGS.items())
    assert build("")["tip"] == GENESIS
    print(json.dumps({"selftest": "pass", "tip": out["tip"],
                      "receipts": out["receipts"], "rate": RATE,
                      "engines": list(ENGINES)}))
    return 0


def main(argv) -> int:
    if "--selftest" in argv:
        return selftest()
    src = argv[1] if len(argv) > 1 else "-"
    text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    out = build(text)
    if "--full" not in argv:
        out = {k: v for k, v in out.items() if k != "chain"}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
