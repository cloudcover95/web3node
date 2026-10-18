"""juniorctl night receipt ledger: per-brief receipts + side-commit + rate lock.

Roadmap item: JuniorLLM docs/BETA_TO_OS.md "Live beta", step 2, the
`juniorctl night` lane, as named for pair B by Quant Chief on 2026-10-18 10:13 MT
(excluding LLC's JuniorHome advance_live_beta_step6/step7 and the already-landed
ask, health, security, test_junior_aie, and test_linux_security parts). The
matching handshake/port check belongs to Handshake & Ports in a different file.
This is a new capability: it never imports, runs, wraps, tests, rewrites, or
re-derives juniorctl, bitnet_night, the dream mesh, or any other team file,
including my own earlier ledgers.

What it records: the caller hands in the plain dict that `juniorctl night`
prints (the MORNING.json brief: status, at, port, queue, night{ticks,
final_drift, mean_drift, sparsity, recommendation, state}). Ten checks become
one trit each (+1 holds, 0 not declared, -1 fails):
  status_complete, at_zoned, port_named, queue_ok, ticks_in_range,
  state_ternary, sparsity_matches_state, drift_in_unit, rec_matches_drift,
  guard (no fetch/socket/mint/exec declared, bind 127.0.0.1 if declared).
rec_matches_drift uses the documented drift bands (<0.08 high_confidence,
<0.22 review_needed, else low_confidence), so a brief whose recommendation
disagrees with its own drift shows up as a mismatch. The 32-dim night state is
also packed and committed on its own (state_commit), so a later brief that
claims the same state with a different recommendation is traceable.
Offline: no subprocess, no file reads, no network, no sockets, no model pull,
no GGUF download, no UE5 launch.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Ports touched: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1.

Run: python3 juniorctl_night_receipt_ledger.py --selftest
     python3 juniorctl_night_receipt_ledger.py --brief '{"status":"complete",...}'
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Mapping

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
ROADMAP_ITEM = (
    "JuniorLLM docs/BETA_TO_OS.md Live beta step 2: juniorctl night "
    "morning-brief receipt ledger"
)

MINT = False
SOCKET = False
LAYER_ONE = False
FETCH = False
UE5_LAUNCH = False
MODEL_PULL = False
SUBPROCESS = False
RELEASED = 0
BIND = "127.0.0.1"
BITNETD_BIND = "127.0.0.1:8765"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
COMPATIBLE_ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")

NIGHT_DIM = 32
MAX_TICKS = 10_000
HIGH_BAND = 0.08
REVIEW_BAND = 0.22
RECS = ("high_confidence", "review_needed", "low_confidence")
SPARSITY_TOL = 1e-4

# Check order is fixed: it is the trit order in every receipt.
CHECKS = (
    "status_complete",
    "at_zoned",
    "port_named",
    "queue_ok",
    "ticks_in_range",
    "state_ternary",
    "sparsity_matches_state",
    "drift_in_unit",
    "rec_matches_drift",
    "guard",
)

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


def band_for(drift: float) -> str:
    """Documented drift band for a final drift value."""
    if drift < HIGH_BAND:
        return "high_confidence"
    if drift < REVIEW_BAND:
        return "review_needed"
    return "low_confidence"


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _state(night: Mapping[str, Any]) -> list[int] | None:
    s = night.get("state")
    if not isinstance(s, list):
        return None
    if any(isinstance(x, bool) or x not in (-1, 0, 1) for x in s):
        return []
    return [int(x) for x in s]


def check_trits(brief: Mapping[str, Any] | None = None) -> dict[str, int]:
    """Map one declared night brief to one trit per check. Reads only the dict it is given."""
    b = dict(brief or {})
    night = b.get("night") if isinstance(b.get("night"), Mapping) else {}

    status = b.get("status")
    status_t = 0 if status is None else (1 if status == "complete" else -1)

    at = b.get("at")
    if at is None:
        at_t = 0
    else:
        s = str(at)
        at_t = 1 if ("T" in s and (s.endswith("Z") or s[-6:-5] in ("+", "-"))) else -1

    port = b.get("port")
    port_t = 0 if port is None else (1 if isinstance(port, str) and port.strip() else -1)

    queue = b.get("queue")
    queue_t = 0 if queue is None else (-1 if str(queue) == "blocked" else 1)

    ticks = night.get("ticks")
    if ticks is None:
        ticks_t = 0
    else:
        ticks_t = 1 if (isinstance(ticks, int) and not isinstance(ticks, bool)
                        and 1 <= ticks <= MAX_TICKS) else -1

    st = _state(night)
    if st is None:
        state_t = 0
    else:
        state_t = 1 if len(st) == NIGHT_DIM else -1

    sp = _num(night.get("sparsity"))
    if sp is None or state_t != 1:
        sparsity_t = 0 if (sp is None or st is None) else -1
    else:
        sparsity_t = 1 if abs(sp - st.count(0) / NIGHT_DIM) <= SPARSITY_TOL else -1

    fd = _num(night.get("final_drift"))
    md = _num(night.get("mean_drift"))
    if fd is None and md is None:
        drift_t = 0
    else:
        vals = [v for v in (fd, md) if v is not None]
        drift_t = 1 if all(0.0 <= v <= 1.0 for v in vals) else -1

    rec = night.get("recommendation")
    if rec is None or fd is None:
        rec_t = 0
    else:
        rec_t = 1 if (rec in RECS and rec == band_for(fd)) else -1

    bad = [k for k in ("fetch", "socket", "mint", "exec", "layer_one", "model_pull")
           if b.get(k) is True]
    bind = b.get("bind")
    if bind is not None and not str(bind).startswith(BIND + ":") and str(bind) != BIND:
        bad.append("bind")
    guard_t = -1 if bad else 1

    return {
        "status_complete": status_t,
        "at_zoned": at_t,
        "port_named": port_t,
        "queue_ok": queue_t,
        "ticks_in_range": ticks_t,
        "state_ternary": state_t,
        "sparsity_matches_state": sparsity_t,
        "drift_in_unit": drift_t,
        "rec_matches_drift": rec_t,
        "guard": guard_t,
    }


def audit_brief(brief: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Per-check trits, failing/undeclared lists, drift band, and blocked flag."""
    b = dict(brief or {})
    night = b.get("night") if isinstance(b.get("night"), Mapping) else {}
    by_name = check_trits(b)
    trits = [by_name[k] for k in CHECKS]
    failing = [k for k in CHECKS if by_name[k] == -1]
    undeclared = [k for k in CHECKS if by_name[k] == 0]
    fd = _num(night.get("final_drift"))
    st = _state(night)
    reasons = b.get("reasons") if isinstance(b.get("reasons"), list) else []
    return {
        "item": ROADMAP_ITEM,
        "checks": by_name,
        "trits": trits,
        "failing": failing,
        "undeclared": undeclared,
        "band": None if fd is None else band_for(fd),
        "recommendation": night.get("recommendation"),
        "rec_mismatch": by_name["rec_matches_drift"] == -1,
        "blocked": b.get("status") == "blocked",
        "block_reasons": sorted(str(r) for r in reasons),
        "state_ok": bool(st) and len(st) == NIGHT_DIM,
        "guard_breach": by_name["guard"] == -1,
        "clean": not failing and not undeclared,
        "subprocess": SUBPROCESS,
        "fetch": FETCH,
    }


def audit_text(audit: dict[str, Any]) -> str:
    return json.dumps(audit, sort_keys=True, separators=(",", ":"))


def append_night_receipt(
    ledger: list[dict[str, Any]], prev: str, brief: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Audit one night brief and append a receipt with side-commit, rate_commit, state_commit."""
    b = dict(brief or {})
    night = b.get("night") if isinstance(b.get("night"), Mapping) else {}
    audit = audit_brief(b)
    trits = list(audit["trits"])
    text = audit_text(audit)
    pk = pack(trits)
    st = _state(night)
    state_commit = None
    if audit["state_ok"]:
        state_commit = side_commit(prev, pack(st), str(night.get("recommendation")))
    link = {
        "prev": prev,
        "trits": trits,
        "text": text,
        "clean": audit["clean"],
        "commit": side_commit(prev, pk, text),
        "rate_commit": rate_lock_commit(prev, pk),
        "state": st if audit["state_ok"] else None,
        "state_commit": state_commit,
        "rate": RATE,
    }
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Live-beta backfill gate for the night lane. gaps lists broken links; open lists
    receipts with a failing or undeclared check; mismatch lists receipts whose
    recommendation disagrees with their drift band; blocked lists guardrail-blocked
    nights; breaches lists receipts with a guard breach (fetch/socket/mint/exec or a
    non-loopback bind); conflicts lists receipts that reuse an earlier night state
    with a different recommendation."""
    gaps: list[int] = []
    open_: list[int] = []
    mismatch: list[int] = []
    blocked: list[int] = []
    breaches: list[int] = []
    conflicts: list[int] = []
    seen: dict[bytes, str] = {}
    cur = prev
    for i, link in enumerate(ledger):
        try:
            pk = pack(link["trits"])
            body = json.loads(link["text"])
        except (KeyError, ValueError, TypeError):
            gaps.append(i)
            cur = link.get("commit", cur) if isinstance(link, dict) else cur
            continue
        st = link.get("state")
        sc_ok = True
        if st is not None:
            try:
                spk = pack(st)
            except (KeyError, TypeError):
                spk = None
            rec = str(body.get("recommendation"))
            if spk is None or link.get("state_commit") != side_commit(cur, spk, rec):
                sc_ok = False
            elif spk in seen and seen[spk] != rec:
                conflicts.append(i)
            elif spk is not None:
                seen.setdefault(spk, rec)
        elif link.get("state_commit") is not None:
            sc_ok = False
        if (
            not sc_ok
            or link.get("prev") != cur
            or link.get("commit") != side_commit(cur, pk, link["text"])
            or link.get("rate_commit") != rate_lock_commit(cur, pk)
            or link.get("rate") != RATE
            or body.get("trits") != link["trits"]
            or body.get("clean") != link.get("clean")
        ):
            gaps.append(i)
        if body.get("failing") or body.get("undeclared"):
            open_.append(i)
        if body.get("rec_mismatch"):
            mismatch.append(i)
        if body.get("blocked"):
            blocked.append(i)
        if body.get("guard_breach"):
            breaches.append(i)
        cur = link.get("commit", cur)
    return {"ok": not gaps and not mismatch and not breaches and not conflicts,
            "gaps": gaps, "open": open_, "mismatch": mismatch, "blocked": blocked,
            "breaches": breaches, "conflicts": conflicts, "tip": cur, "n": len(ledger)}


def _sample_state() -> list[int]:
    return ([1, 0, -1, 0] * 8)[:NIGHT_DIM]


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, known close, brief audits, tamper and gap detection."""
    assert BIND == "127.0.0.1" and BITNETD_BIND.startswith(BIND + ":")
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL or SUBPROCESS)
    assert RELEASED == 0 and RATE == 0.05
    assert "subprocess" not in sys.modules or not SUBPROCESS

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known

    assert band_for(0.0) == "high_confidence" and band_for(0.08) == "review_needed"
    assert band_for(0.2199) == "review_needed" and band_for(0.22) == "low_confidence"

    state = _sample_state()
    green = {
        "status": "complete", "at": "2026-10-18T16:35:00+00:00", "port": "JuniorOSai",
        "queue": "queued",
        "night": {"ticks": 32, "final_drift": 0.05, "mean_drift": 0.11,
                  "sparsity": round(state.count(0) / NIGHT_DIM, 4),
                  "recommendation": "high_confidence", "state": state},
    }
    a = audit_brief(green)
    assert a["clean"] and a["trits"] == [1] * 10 and a["band"] == "high_confidence"
    blank = audit_brief()
    assert not blank["clean"] and blank["trits"] == [0] * 9 + [1]
    assert blank["undeclared"] == list(CHECKS[:9])

    def nv(**kw: Any) -> dict[str, Any]:
        return dict(green, night=dict(green["night"], **kw))

    lie = audit_brief(nv(final_drift=0.30))
    assert lie["rec_mismatch"] and lie["failing"] == ["rec_matches_drift"]
    assert lie["band"] == "low_confidence"
    sp = audit_brief(nv(sparsity=0.9))
    assert sp["failing"] == ["sparsity_matches_state"]
    short = audit_brief(nv(state=[1, 0, -1]))
    assert "state_ternary" in short["failing"] and "sparsity_matches_state" in short["failing"]
    bad_state = audit_brief(nv(state=[2] * NIGHT_DIM))
    assert "state_ternary" in bad_state["failing"] and not bad_state["state_ok"]
    over = audit_brief(nv(ticks=10_001))
    assert over["failing"] == ["ticks_in_range"]
    naive = audit_brief(dict(green, at="2026-10-18 16:35:00"))
    assert naive["failing"] == ["at_zoned"]
    wide = audit_brief(dict(green, bind="192.168.1.20:8765"))
    assert wide["guard_breach"] and wide["failing"] == ["guard"]
    fetchy = audit_brief(dict(green, fetch=True))
    assert fetchy["guard_breach"]
    stop = audit_brief({"status": "blocked", "reasons": ["prompt_injection:3"]})
    assert stop["blocked"] and stop["failing"] == ["status_complete"]
    assert stop["block_reasons"] == ["prompt_injection:3"]

    ledger: list[dict[str, Any]] = []
    r0 = append_night_receipt(ledger, GENESIS, green)
    assert r0["state_commit"] == side_commit(GENESIS, pack(state), "high_confidence")
    r1 = append_night_receipt(ledger, r0["commit"], dict(green, queue=None))
    r2 = append_night_receipt(ledger, r1["commit"],
                              {"status": "blocked", "reasons": ["prompt_injection:3"]})
    bf = backfill_check(ledger)
    assert bf["ok"] and bf["gaps"] == [] and bf["n"] == 3 and bf["tip"] == r2["commit"]
    assert bf["open"] == [1, 2] and bf["blocked"] == [2]
    assert bf["mismatch"] == [] and bf["breaches"] == [] and bf["conflicts"] == []
    assert r2["state"] is None and r2["state_commit"] is None

    lk = list(ledger)
    r3 = append_night_receipt(lk, r2["commit"], nv(final_drift=0.30))
    r4 = append_night_receipt(lk, r3["commit"], dict(green, bind="192.168.1.20:8765"))
    append_night_receipt(lk, r4["commit"],
                         nv(final_drift=0.15, recommendation="review_needed"))
    bl = backfill_check(lk)
    assert bl["mismatch"] == [3] and bl["breaches"] == [4] and bl["gaps"] == []
    assert 5 in bl["conflicts"] and not bl["ok"]

    t = [dict(x) for x in ledger]
    t[1] = dict(t[1], text=t[1]["text"].replace('"queue_ok":0', '"queue_ok":1'))
    assert 1 in backfill_check(t)["gaps"]
    r = [dict(x) for x in ledger]
    r[0] = dict(r[0], rate_commit=hashlib.sha256(b"x").hexdigest())
    assert 0 in backfill_check(r)["gaps"]
    s = [dict(x) for x in ledger]
    s[0] = dict(s[0], state=[-x for x in state])
    assert 0 in backfill_check(s)["gaps"]
    d = [ledger[0], ledger[2]]
    assert 1 in backfill_check(d)["gaps"]

    return {
        "ok": True,
        "item": ROADMAP_ITEM,
        "bind": BIND,
        "bitnetd_bind": BITNETD_BIND,
        "ports": list(PORTS),
        "rate": RATE,
        "pack_vector": vec.hex(),
        "close_home_4a44": known,
        "engines": list(COMPATIBLE_ENGINES),
        "tip": bf["tip"],
        "flags": {"mint": MINT, "socket": SOCKET, "layer_one": LAYER_ONE, "fetch": FETCH,
                  "ue5_launch": UE5_LAUNCH, "model_pull": MODEL_PULL,
                  "subprocess": SUBPROCESS, "released": RELEASED},
    }


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    brief: dict[str, Any] = {}
    if "--brief" in argv:
        i = argv.index("--brief")
        brief = json.loads(argv[i + 1]) if i + 1 < len(argv) else {}
    ledger: list[dict[str, Any]] = []
    link = append_night_receipt(ledger, GENESIS, brief)
    print(json.dumps({"receipt": link, "backfill": backfill_check(ledger)}, sort_keys=True))
    return 0 if link["clean"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
