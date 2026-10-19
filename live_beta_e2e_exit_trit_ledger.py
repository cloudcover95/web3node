"""Live beta end-to-end exit-code trit ledger: one run receipt + side-commit + rate lock.

Roadmap item: JuniorLLM docs/BETA_TO_OS.md "Live beta", the end-to-end
exit-code trits plus test_linux_security, as named for pair B by Quant Chief on
2026-10-18 18:08 MT (gaps only; steps 2/4/5/6, night, ask, and health already
landed). The matching handshake/port check belongs to Handshake & Ports in a
different file. This is a new capability: it never imports, runs, wraps, tests,
rewrites, or re-derives juniorctl, the tests, the stonefield probe,
backfill_check.py, or any other team file, including my own earlier ledgers
(stocksnode live_beta_receipt_ledger.py maps exit codes only as 0 vs nonzero,
per step; web3node linux_security_finding_ledger.py is per finding).

The gap it fills:
  1. A full exit-code-to-trit table (+1 holds, 0 not exercised, -1 fails):
       0 -> +1 pass;  None -> 0 not run;  5 -> 0 unittest "no tests ran";
       77 -> 0 skip;  127 -> 0 command not found (env, not a verdict);
       1 -> -1 fail;  2 -> -1 usage;  124 -> -1 timeout;  126 -> -1 not exec;
       128+N -> -1 killed by signal N;  any other nonzero -> -1.
     Each step keeps its cause label, so a skip is never confused with a pass.
  2. One end-to-end run receipt across the fresh-clone sequence (health, ask,
     night, security, test_junior_aie, test_linux_security, stonefield probe,
     backfill_check) with a folded run trit (-1 if any step fails, else 0 if
     any step is not exercised, else +1).
  3. Health taint: a step reported +1 after `juniorctl health` failed or never
     ran is listed as suspect, since every later step assumes a healthy rail.
  4. test_linux_security consistency: the declared unittest summary
     (tests_run, failures, errors, skipped) must agree with its exit code
     (0 iff no failures/errors and tests_run > 0; 5 iff tests_run == 0).
  5. Cross-run regression: backfill_check lists runs where a step that was +1
     in the previous run is now -1.
Offline: no subprocess, no file reads, no network, no sockets, no model pull,
no GGUF download, no UE5 launch.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Ports touched: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1.

Run: python3 live_beta_e2e_exit_trit_ledger.py --selftest
     python3 live_beta_e2e_exit_trit_ledger.py --run '{"exits":{"health":0,...}}'
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
    "JuniorLLM docs/BETA_TO_OS.md Live beta: end-to-end exit-code trits "
    "plus test_linux_security"
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

# Fixed fresh-clone order; it is the trit order in every run receipt.
STEPS = (
    "health",
    "ask",
    "night",
    "security",
    "test_junior_aie",
    "test_linux_security",
    "stonefield_probe",
    "backfill_check",
)

_ZERO_CODES = {5: "no_tests", 77: "skip", 127: "not_found"}
_FAIL_CODES = {1: "fail", 2: "usage", 124: "timeout", 126: "not_exec"}
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


def exit_trit(code: Any) -> tuple[int, str]:
    """Map one declared exit code to (trit, cause)."""
    if code is None:
        return 0, "not_run"
    if isinstance(code, bool) or not isinstance(code, int):
        return -1, "bad_code"
    if code == 0:
        return 1, "pass"
    if code in _ZERO_CODES:
        return 0, _ZERO_CODES[code]
    if code in _FAIL_CODES:
        return -1, _FAIL_CODES[code]
    if 128 < code < 160:
        return -1, "signal_%d" % (code - 128)
    if code < 0 and code > -32:
        return -1, "signal_%d" % (-code)
    return -1, "nonzero_%d" % code


def fold(trits: list[int]) -> int:
    """End-to-end run trit: -1 if any step fails, 0 if any not exercised, else +1."""
    if any(t == -1 for t in trits):
        return -1
    if any(t == 0 for t in trits):
        return 0
    return 1


def lsec_consistent(code: Any, summary: Mapping[str, Any] | None) -> int:
    """test_linux_security summary vs exit code: +1 agree, 0 undeclared, -1 disagree."""
    if not summary or code is None or isinstance(code, bool) or not isinstance(code, int):
        return 0
    try:
        run = int(summary.get("tests_run", -1))
        bad = int(summary.get("failures", 0)) + int(summary.get("errors", 0))
    except (TypeError, ValueError):
        return -1
    if run < 0:
        return 0
    if run == 0:
        return 1 if code == 5 else -1
    if bad > 0:
        return 1 if code == 1 else -1
    return 1 if code == 0 else -1


def audit_run(run: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Per-step trits and causes, folded run trit, suspects, lsec consistency, guard."""
    r = dict(run or {})
    exits = r.get("exits") if isinstance(r.get("exits"), Mapping) else {}
    steps: dict[str, dict[str, Any]] = {}
    trits: list[int] = []
    for name in STEPS:
        code = exits.get(name)
        t, cause = exit_trit(code)
        steps[name] = {"exit": code if isinstance(code, int) else None, "trit": t,
                       "cause": cause}
        trits.append(t)
    health_ok = steps["health"]["trit"] == 1
    suspect = [] if health_ok else [n for n in STEPS[1:] if steps[n]["trit"] == 1]
    lsec = lsec_consistent(exits.get("test_linux_security"), r.get("lsec_summary"))

    bad = [k for k in ("fetch", "socket", "mint", "exec", "layer_one", "model_pull")
           if r.get(k) is True]
    bind = r.get("bind")
    if bind is not None and str(bind) != BITNETD_BIND:
        bad.append("bind")
    guard_t = -1 if bad else 1

    run_t = fold(trits)
    full = trits + [lsec, guard_t, run_t]
    return {
        "item": ROADMAP_ITEM,
        "steps": steps,
        "trits": full,
        "step_trits": trits,
        "run_trit": run_t,
        "failing": [n for n in STEPS if steps[n]["trit"] == -1],
        "unexercised": [n for n in STEPS if steps[n]["trit"] == 0],
        "suspect": suspect,
        "lsec_consistent": lsec,
        "lsec_mismatch": lsec == -1,
        "guard": guard_t,
        "guard_breach": sorted(bad),
        "clean": run_t == 1 and lsec == 1 and guard_t == 1 and not suspect,
        "subprocess": SUBPROCESS,
        "fetch": FETCH,
    }


def audit_text(audit: dict[str, Any]) -> str:
    return json.dumps(audit, sort_keys=True, separators=(",", ":"))


def append_run_receipt(
    ledger: list[dict[str, Any]], prev: str, run: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Audit one end-to-end live-beta run and append a chained receipt."""
    audit = audit_run(run)
    trits = list(audit["trits"])
    text = audit_text(audit)
    pk = pack(trits)
    link = {
        "prev": prev,
        "trits": trits,
        "text": text,
        "run_trit": audit["run_trit"],
        "clean": audit["clean"],
        "commit": side_commit(prev, pk, text),
        "rate_commit": rate_lock_commit(prev, pk),
        "rate": RATE,
    }
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Live-beta backfill gate across runs. gaps: broken links; open: runs not clean;
    failed: runs whose folded trit is -1; suspect: runs with steps passing after a
    failed or missing health; mismatch: test_linux_security summary disagrees with
    its exit code; regressions: (run, step) pairs that went +1 -> -1 since the prior
    run; breaches: guard breaches (fetch/socket/mint/exec or bind != 127.0.0.1:8765)."""
    gaps: list[int] = []
    open_: list[int] = []
    failed: list[int] = []
    suspect: list[int] = []
    mismatch: list[int] = []
    regressions: list[list[Any]] = []
    breaches: list[int] = []
    last: list[int] | None = None
    cur = prev
    n_steps = len(STEPS)
    for i, link in enumerate(ledger):
        try:
            pk = pack(link["trits"])
            body = json.loads(link["text"])
        except (KeyError, ValueError, TypeError):
            gaps.append(i)
            cur = link.get("commit", cur) if isinstance(link, dict) else cur
            continue
        if (
            link.get("prev") != cur
            or link.get("commit") != side_commit(cur, pk, link["text"])
            or link.get("rate_commit") != rate_lock_commit(cur, pk)
            or link.get("rate") != RATE
            or body.get("trits") != link["trits"]
            or body.get("run_trit") != link.get("run_trit")
            or body.get("clean") != link.get("clean")
            or fold(list(link["trits"][:n_steps])) != link.get("run_trit")
        ):
            gaps.append(i)
        if not body.get("clean"):
            open_.append(i)
        if body.get("run_trit") == -1:
            failed.append(i)
        if body.get("suspect"):
            suspect.append(i)
        if body.get("lsec_mismatch"):
            mismatch.append(i)
        if body.get("guard_breach"):
            breaches.append(i)
        st = list(link["trits"][:n_steps])
        if last is not None:
            for k, name in enumerate(STEPS):
                if last[k] == 1 and st[k] == -1:
                    regressions.append([i, name])
        last = st
        cur = link.get("commit", cur)
    return {"ok": not gaps and not mismatch and not breaches and not suspect,
            "gaps": gaps, "open": open_, "failed": failed, "suspect": suspect,
            "mismatch": mismatch, "regressions": regressions, "breaches": breaches,
            "tip": cur, "n": len(ledger)}


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, known close, exit table, runs, tamper, gaps."""
    assert BIND == "127.0.0.1" and BITNETD_BIND.startswith(BIND + ":")
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL or SUBPROCESS)
    assert RELEASED == 0 and RATE == 0.05

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known

    table = [(None, (0, "not_run")), (0, (1, "pass")), (1, (-1, "fail")),
             (2, (-1, "usage")), (5, (0, "no_tests")), (77, (0, "skip")),
             (124, (-1, "timeout")), (126, (-1, "not_exec")), (127, (0, "not_found")),
             (137, (-1, "signal_9")), (-15, (-1, "signal_15")), (3, (-1, "nonzero_3")),
             (True, (-1, "bad_code")), ("0", (-1, "bad_code"))]
    for code, want in table:
        assert exit_trit(code) == want, (code, exit_trit(code))
    assert fold([1, 1]) == 1 and fold([1, 0]) == 0 and fold([0, -1]) == -1

    good_sum = {"tests_run": 6, "failures": 0, "errors": 0, "skipped": 0}
    assert lsec_consistent(0, good_sum) == 1
    assert lsec_consistent(0, dict(good_sum, failures=1)) == -1
    assert lsec_consistent(1, dict(good_sum, errors=2)) == 1
    assert lsec_consistent(5, dict(good_sum, tests_run=0)) == 1
    assert lsec_consistent(0, dict(good_sum, tests_run=0)) == -1
    assert lsec_consistent(0, None) == 0

    green = {"exits": {n: 0 for n in STEPS}, "lsec_summary": good_sum,
             "bind": BITNETD_BIND}
    a = audit_run(green)
    assert a["clean"] and a["trits"] == [1] * (len(STEPS) + 3) and a["run_trit"] == 1
    blank = audit_run()
    assert blank["run_trit"] == 0 and blank["unexercised"] == list(STEPS)
    assert blank["trits"] == [0] * len(STEPS) + [0, 1, 0] and not blank["clean"]

    def ex(**kw: Any) -> dict[str, Any]:
        return dict(green, exits=dict(green["exits"], **kw))

    skip = audit_run(ex(stonefield_probe=77))
    assert skip["run_trit"] == 0 and skip["steps"]["stonefield_probe"]["cause"] == "skip"
    killed = audit_run(ex(night=137))
    assert killed["failing"] == ["night"] and killed["run_trit"] == -1
    taint = audit_run(ex(health=1))
    assert taint["suspect"] == list(STEPS[1:]) and not taint["clean"]
    nohealth = audit_run(ex(health=None))
    assert nohealth["suspect"] == list(STEPS[1:])
    lie = audit_run(dict(green, lsec_summary=dict(good_sum, failures=2)))
    assert lie["lsec_mismatch"] and lie["run_trit"] == 1 and not lie["clean"]
    wide = audit_run(dict(green, bind="0.0.0.0:8765"))
    assert wide["guard_breach"] == ["bind"] and wide["guard"] == -1
    fetchy = audit_run(dict(green, fetch=True))
    assert fetchy["guard_breach"] == ["fetch"]

    ledger: list[dict[str, Any]] = []
    r0 = append_run_receipt(ledger, GENESIS, green)
    r1 = append_run_receipt(ledger, r0["commit"], ex(stonefield_probe=77))
    r2 = append_run_receipt(ledger, r1["commit"],
                            dict(ex(test_linux_security=1, backfill_check=1),
                                 lsec_summary=dict(good_sum, failures=1)))
    bf = backfill_check(ledger)
    assert bf["ok"] and bf["gaps"] == [] and bf["n"] == 3 and bf["tip"] == r2["commit"]
    assert bf["open"] == [1, 2] and bf["failed"] == [2]
    assert bf["regressions"] == [[2, "test_linux_security"], [2, "backfill_check"]]
    assert bf["suspect"] == [] and bf["mismatch"] == [] and bf["breaches"] == []

    lk = list(ledger)
    r3 = append_run_receipt(lk, r2["commit"], ex(health=1))
    r4 = append_run_receipt(lk, r3["commit"], dict(green, lsec_summary=dict(good_sum,
                            errors=1)))
    append_run_receipt(lk, r4["commit"], dict(green, bind="0.0.0.0:8765"))
    bl = backfill_check(lk)
    assert bl["suspect"] == [3] and bl["mismatch"] == [4] and bl["breaches"] == [5]
    assert bl["gaps"] == [] and not bl["ok"] and [3, "health"] in bl["regressions"]

    t = [dict(x) for x in ledger]
    t[1] = dict(t[1], text=t[1]["text"].replace('"cause":"skip"', '"cause":"pass"'))
    assert 1 in backfill_check(t)["gaps"]
    r = [dict(x) for x in ledger]
    r[0] = dict(r[0], rate_commit=hashlib.sha256(b"x").hexdigest())
    assert 0 in backfill_check(r)["gaps"]
    f = [dict(x) for x in ledger]
    f[2] = dict(f[2], run_trit=1)
    assert 2 in backfill_check(f)["gaps"]
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
    run: dict[str, Any] = {}
    if "--run" in argv:
        i = argv.index("--run")
        run = json.loads(argv[i + 1]) if i + 1 < len(argv) else {}
    ledger: list[dict[str, Any]] = []
    link = append_run_receipt(ledger, GENESIS, run)
    print(json.dumps({"receipt": link, "backfill": backfill_check(ledger)}, sort_keys=True))
    return 0 if link["clean"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
