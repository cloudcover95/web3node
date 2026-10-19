"""test_junior_aie per-case receipt ledger: case receipts + side-commit + rate lock.

Roadmap item: JuniorLLM docs/BETA_TO_OS.md "Live beta" step 3,
`python tests/test_junior_aie.py`, the test_junior_aie per-case part, as named
for pair B by Quant Chief on 2026-10-19 05:11 MT (live beta remaining gaps
only; step 2 night, per-step exit codes, linux security findings, and the
end-to-end exit trits already landed; pair A covers juniorctl security). The
matching handshake/port check belongs to Handshake & Ports in a different file.

This is a new capability. It never imports, runs, wraps, tests, rewrites, or
re-derives tests/test_junior_aie.py, junior_aie, juniorctl, backfill_check.py,
or any other team file, including my own earlier ledgers (those see
test_junior_aie only as one exit code; none of them look inside it per case).

The gap it fills, from the caller-declared `unittest -v` text of one run:
  1. Per-case receipts for the nine cases the suite declares (FrameworkTests:
     ask_and_cache, guard, router; StackTests: orch, mcp, consensus_escalate,
     sandbox, workflow, stream_eval_prompt_fly), each tagged with the
     junior_aie components it asserts. Case trit: +1 ok, 0 skipped / expected
     failure / not reported, -1 FAIL / ERROR / unexpected success.
  2. Case-set integrity: missing cases, extra (undeclared) cases, duplicates,
     and a case reported under the wrong class.
  3. Summary consistency: "Ran N tests" must equal the parsed case count, and
     the closing "OK" / "FAILED (failures=a, errors=b)" line must agree with
     the per-case outcomes and with the declared exit code (0 iff OK).
  4. One run receipt that folds the nine case trits plus count, summary, exit,
     set and guard trits, closing over the tip of that run's case chain.
  5. backfill_check: chain + rate lock replay, plus missing/failed/skipped/
     extras/mismatch lists and cross-run per-case regressions (+1 -> -1).
Offline: no subprocess, no file reads, no network, no sockets, no model pull,
no GGUF download, no UE5 launch.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Ports touched: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1.

Run: python3 test_junior_aie_case_receipt_ledger.py --selftest
     python3 test_junior_aie_case_receipt_ledger.py --run '{"stdout":"...","exit":0}'
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any, Mapping

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
ROADMAP_ITEM = (
    "JuniorLLM docs/BETA_TO_OS.md Live beta step 3: test_junior_aie per-case receipts"
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

# Declared case set, in suite order: (class, method, components asserted).
CASES = (
    ("FrameworkTests", "test_ask_and_cache", ("retrieval", "ask", "cache")),
    ("FrameworkTests", "test_guard", ("guard",)),
    ("FrameworkTests", "test_router", ("router",)),
    ("StackTests", "test_orch", ("orchestrator",)),
    ("StackTests", "test_mcp", ("mcp",)),
    ("StackTests", "test_consensus_escalate", ("consensus",)),
    ("StackTests", "test_sandbox", ("sandbox",)),
    ("StackTests", "test_workflow", ("workflow",)),
    ("StackTests", "test_stream_eval_prompt_fly",
     ("stream", "evalh", "contracts", "prompts", "flywheel")),
)
CASE_NAMES = tuple(m for _, m, _ in CASES)
CASE_CLASS = {m: c for c, m, _ in CASES}
CASE_COMPONENTS = {m: comps for _, m, comps in CASES}

_TRIT_TO_BITS = {0: 0, 1: 1, -1: 2}
_STATUS_TRIT = {"ok": 1, "skipped": 0, "expected failure": 0,
                "FAIL": -1, "ERROR": -1, "unexpected success": -1}
_CASE_RE = re.compile(
    r"^(?P<method>test\w+) \((?P<where>[\w.]+)\)(?: \.\.\.(?: (?P<status>.*))?)?$")
_RAN_RE = re.compile(r"^Ran (\d+) tests? in ")
_OK_RE = re.compile(r"^OK(?: \((?P<extra>[^)]*)\))?$")
_FAILED_RE = re.compile(r"^FAILED \((?P<extra>[^)]*)\)$")
_GUARD_KEYS = ("fetch", "socket", "mint", "exec", "layer_one", "model_pull", "ue5_launch")


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


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _status_word(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("skipped"):
        return "skipped"
    for word in ("expected failure", "unexpected success", "ok", "FAIL", "ERROR"):
        if raw == word:
            return word
    return "unknown"


def parse_verbose(text: str) -> dict[str, Any]:
    """Parse caller-declared `unittest -v` text into cases + summary (no exec)."""
    cases: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    ran: int | None = None
    summary: dict[str, Any] | None = None
    for line in str(text).splitlines():
        line = line.rstrip()
        m = _CASE_RE.match(line)
        if m:
            where = m.group("where").split(".")
            klass = where[-1] if where[-1] != m.group("method") else where[-2]
            case = {"method": m.group("method"), "class": klass, "status": None}
            if m.group("status"):
                case["status"] = _status_word(m.group("status"))
                cases.append(case)
                pending = None
            else:
                pending = case
            continue
        if pending is not None and line.strip():
            word = _status_word(line.split(" ... ")[-1])
            if word != "unknown":
                pending["status"] = word
                cases.append(pending)
                pending = None
                continue
        r = _RAN_RE.match(line)
        if r:
            ran = int(r.group(1))
            continue
        ok = _OK_RE.match(line)
        bad = _FAILED_RE.match(line)
        if ok or bad:
            extra = (ok or bad).group("extra") or ""
            counts = {}
            for part in extra.split(","):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    if v.isdigit():
                        counts[k] = int(v)
            summary = {"ok": bool(ok), "counts": counts}
    if pending is not None:
        pending["status"] = "unknown"
        cases.append(pending)
    return {"cases": cases, "ran": ran, "summary": summary}


def case_trit(status: Any) -> int:
    """+1 ok, 0 skipped / expected failure / not reported, -1 fail/error/unknown."""
    if status is None:
        return 0
    return _STATUS_TRIT.get(status, -1)


def fold(trits: list[int]) -> int:
    if any(t == -1 for t in trits):
        return -1
    if any(t == 0 for t in trits):
        return 0
    return 1


def _guard(run: Mapping[str, Any]) -> list[str]:
    g = run.get("guard") or {}
    bad = [k for k in _GUARD_KEYS if g.get(k)]
    bind = g.get("bind")
    if bind is not None and str(bind) != BITNETD_BIND:
        bad.append("bind")
    return bad


def audit_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """Audit one declared run: case outcomes, set integrity, summary, exit, guard."""
    parsed = parse_verbose(run.get("stdout", ""))
    seen: dict[str, dict[str, Any]] = {}
    extras: list[str] = []
    dupes: list[str] = []
    wrong_class: list[str] = []
    for c in parsed["cases"]:
        name = c["method"]
        if name not in CASE_CLASS:
            extras.append(f'{c["class"]}.{name}')
            continue
        if name in seen:
            dupes.append(name)
            continue
        if c["class"] != CASE_CLASS[name]:
            wrong_class.append(name)
        seen[name] = c
    case_trits = {n: case_trit(seen[n]["status"]) if n in seen else 0 for n in CASE_NAMES}
    missing = [n for n in CASE_NAMES if n not in seen]
    failed = [n for n in CASE_NAMES if case_trits[n] == -1]
    zero = [n for n in CASE_NAMES if n in seen and case_trits[n] == 0]

    n_parsed = len(parsed["cases"])
    ran = parsed["ran"]
    count_trit = 0 if ran is None else (1 if ran == n_parsed else -1)

    n_bad = sum(1 for c in parsed["cases"] if case_trit(c["status"]) == -1)
    s = parsed["summary"]
    if s is None:
        summary_trit = 0
    else:
        counts = s["counts"]
        bad_declared = sum(counts.get(k, 0) for k in ("failures", "errors", "unexpected_successes"))
        if s["ok"]:
            summary_trit = 1 if n_bad == 0 else -1
        else:
            summary_trit = 1 if (n_bad > 0 and bad_declared == n_bad) else -1

    code = run.get("exit")
    if code is None or s is None:
        exit_trit = 0
    elif isinstance(code, bool) or not isinstance(code, int):
        exit_trit = -1
    else:
        exit_trit = 1 if (code == 0) == s["ok"] else -1

    if n_parsed == 0 and s is None:
        set_trit = 0  # suite never ran: not exercised, not a verdict
    else:
        set_trit = 1 if not (missing or extras or dupes or wrong_class) else -1
    breach = _guard(run)
    guard_trit = -1 if breach else 1
    run_trits = [case_trits[n] for n in CASE_NAMES] + [
        count_trit, summary_trit, exit_trit, set_trit, guard_trit]
    return {
        "case_trits": case_trits,
        "missing": missing, "failed": failed, "zero": zero,
        "extras": extras, "dupes": dupes, "wrong_class": wrong_class,
        "ran": ran, "parsed": n_parsed,
        "count_trit": count_trit, "summary_trit": summary_trit,
        "exit_trit": exit_trit, "set_trit": set_trit, "guard_trit": guard_trit,
        "guard_breach": breach, "run_trits": run_trits, "verdict": fold(run_trits),
    }


def _link(prev: str, kind: str, trits: list[int], body: dict[str, Any]) -> dict[str, Any]:
    pk = pack(trits)
    text = _canon(body)
    return {"kind": kind, "prev": prev, "trits": trits, "pack": pk.hex(),
            "body": body, "close": side_commit(prev, pk, text),
            "rate_commit": rate_lock_commit(prev, pk), "rate": RATE}


def append_run(ledger: list[dict[str, Any]], prev: str, run: Mapping[str, Any]) -> dict[str, Any]:
    """Append one case receipt per declared case, then one run receipt over them."""
    a = audit_run(run)
    run_id = str(run.get("run_id", len([x for x in ledger if x["kind"] == "run"])))
    cur = prev
    for n in CASE_NAMES:
        t = a["case_trits"][n]
        body = {"run_id": run_id, "case": f"{CASE_CLASS[n]}.{n}",
                "components": list(CASE_COMPONENTS[n]), "trit": t,
                "reported": n not in a["missing"], "rate": RATE,
                "roadmap": ROADMAP_ITEM}
        link = _link(cur, "case", [t], body)
        ledger.append(link)
        cur = link["close"]
    body = {"run_id": run_id, "cases_tip": cur, "verdict": a["verdict"],
            "missing": a["missing"], "failed": a["failed"], "zero": a["zero"],
            "extras": a["extras"], "dupes": a["dupes"], "wrong_class": a["wrong_class"],
            "ran": a["ran"], "parsed": a["parsed"], "guard_breach": a["guard_breach"],
            "ports": list(PORTS), "bind": BIND, "rate": RATE, "roadmap": ROADMAP_ITEM}
    link = _link(cur, "run", a["run_trits"], body)
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Replay chain and rate lock; list gaps, failures, mismatches, and regressions.

    broken: indexes whose prev/close/rate_commit/rate do not replay;
    missing/failed/zero/extras: per run_id; mismatch: runs whose count, summary,
    or exit trit is -1; regressions: cases +1 in the previous run, -1 now;
    breaches: runs with a guard breach."""
    broken: list[int] = []
    cur = prev
    missing: dict[str, list[str]] = {}
    failed: dict[str, list[str]] = {}
    zero: dict[str, list[str]] = {}
    extras: dict[str, list[str]] = {}
    mismatch: list[str] = []
    breaches: list[str] = []
    regressions: list[str] = []
    last_cases: dict[str, int] | None = None
    this_cases: dict[str, int] = {}
    for i, link in enumerate(ledger):
        pk = bytes.fromhex(link.get("pack", ""))
        ok = (link.get("prev") == cur
              and pack(list(link.get("trits", []))) == pk
              and link.get("close") == side_commit(cur, pk, _canon(link.get("body", {})))
              and link.get("rate_commit") == rate_lock_commit(cur, pk)
              and link.get("rate") == RATE
              and link.get("body", {}).get("rate") == RATE)
        if not ok:
            broken.append(i)
        cur = link.get("close", cur)
        body = link.get("body", {})
        if link.get("kind") == "case":
            this_cases[str(body.get("case", "")).split(".")[-1]] = body.get("trit", 0)
            continue
        rid = str(body.get("run_id"))
        for key, dest in (("missing", missing), ("failed", failed),
                          ("zero", zero), ("extras", extras)):
            if body.get(key):
                dest[rid] = list(body[key])
        t = link.get("trits", [])
        if len(t) == len(CASE_NAMES) + 5 and -1 in t[len(CASE_NAMES):len(CASE_NAMES) + 3]:
            mismatch.append(rid)
        if body.get("guard_breach"):
            breaches.append(rid)
        if last_cases is not None:
            for n in CASE_NAMES:
                if last_cases.get(n) == 1 and this_cases.get(n) == -1:
                    regressions.append(f"{rid}:{n}")
        last_cases, this_cases = this_cases, {}
    return {"ok": not (broken or failed or missing or extras or mismatch or breaches),
            "broken": broken, "missing": missing, "failed": failed, "zero": zero,
            "extras": extras, "mismatch": mismatch, "regressions": regressions,
            "breaches": breaches, "tip": cur, "n": len(ledger)}


def _green_stdout(overrides: Mapping[str, str] | None = None, ran: int | None = None,
                  tail: str | None = None) -> str:
    overrides = dict(overrides or {})
    lines = []
    for c, m, _ in CASES:
        lines.append(f"{m} (__main__.{c}.{m}) ... {overrides.get(m, 'ok')}")
    lines += ["", "-" * 70, f"Ran {len(CASES) if ran is None else ran} tests in 0.042s", ""]
    lines.append(tail if tail is not None else "OK")
    return "\n".join(lines)


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, known close, parse, audit, chain, tamper."""
    assert BIND == "127.0.0.1" and BITNETD_BIND.startswith(BIND + ":")
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL or SUBPROCESS)
    assert RELEASED == 0 and RATE == 0.05
    assert len(CASES) == len(set(CASE_NAMES)) == 9

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known

    # Parse: new-style and old-style headers, skip, status on the next line.
    p = parse_verbose("test_guard (__main__.FrameworkTests) ... ok\n"
                      "test_router (__main__.FrameworkTests.test_router) ... skipped 'x'\n"
                      "test_orch (tests.test_junior_aie.StackTests.test_orch) ...\n"
                      "noise printed by the case\n"
                      "ok\nRan 3 tests in 0.001s\n\nOK (skipped=1)\n")
    got = [(c["class"], c["method"], c["status"]) for c in p["cases"]]
    assert got == [("FrameworkTests", "test_guard", "ok"),
                   ("FrameworkTests", "test_router", "skipped"),
                   ("StackTests", "test_orch", "ok")], got
    assert p["ran"] == 3 and p["summary"] == {"ok": True, "counts": {"skipped": 1}}

    green = {"run_id": "r0", "stdout": _green_stdout(), "exit": 0,
             "guard": {"bind": BITNETD_BIND}}
    a = audit_run(green)
    assert a["verdict"] == 1 and a["run_trits"] == [1] * 14, a

    bad_sb = _green_stdout({"test_sandbox": "FAIL"}, tail="FAILED (failures=1)")
    a = audit_run({"stdout": bad_sb, "exit": 1})
    assert a["failed"] == ["test_sandbox"] and a["summary_trit"] == 1 and a["exit_trit"] == 1
    assert a["verdict"] == -1
    lie = audit_run({"stdout": _green_stdout({"test_mcp": "ERROR"}), "exit": 0})
    assert lie["summary_trit"] == -1 and lie["exit_trit"] == 1
    assert audit_run({"stdout": bad_sb, "exit": 0})["exit_trit"] == -1
    assert audit_run({"stdout": _green_stdout(ran=8), "exit": 0})["count_trit"] == -1

    part = "\n".join(l for l in _green_stdout().splitlines() if "test_workflow" not in l)
    a = audit_run({"stdout": part.replace("Ran 9", "Ran 8"), "exit": 0})
    assert a["missing"] == ["test_workflow"] and a["set_trit"] == -1
    assert a["case_trits"]["test_workflow"] == 0 and a["count_trit"] == 1
    extra = _green_stdout().replace("Ran 9", "test_new (__main__.StackTests.test_new) ... ok\nRan 10")
    a = audit_run({"stdout": extra, "exit": 0})
    assert a["extras"] == ["StackTests.test_new"] and a["count_trit"] == 1
    moved = _green_stdout().replace("StackTests.test_mcp", "FrameworkTests.test_mcp")
    assert audit_run({"stdout": moved, "exit": 0})["wrong_class"] == ["test_mcp"]
    skipped = _green_stdout({"test_router": "skipped 'no astra'"}, tail="OK (skipped=1)")
    a = audit_run({"stdout": skipped, "exit": 0})
    assert a["zero"] == ["test_router"] and a["verdict"] == 0
    breach = audit_run(dict(green, guard={"fetch": True, "bind": "192.0.2.7:8765"}))
    assert breach["guard_breach"] == ["fetch", "bind"] and breach["verdict"] == -1
    assert audit_run({"stdout": "", "exit": None})["verdict"] == 0

    ledger: list[dict[str, Any]] = []
    r0 = append_run(ledger, GENESIS, green)
    r1 = append_run(ledger, r0["close"], {"run_id": "r1", "stdout": bad_sb, "exit": 1})
    assert len(ledger) == 2 * (len(CASES) + 1) and r1["prev"] == ledger[-2]["close"]
    bc = backfill_check(ledger)
    assert bc["broken"] == [] and bc["tip"] == r1["close"], bc
    assert bc["failed"] == {"r1": ["test_sandbox"]} and bc["regressions"] == ["r1:test_sandbox"]
    assert bc["mismatch"] == [] and bc["ok"] is False

    clean: list[dict[str, Any]] = []
    append_run(clean, GENESIS, green)
    assert backfill_check(clean)["ok"] is True

    t = [dict(x) for x in clean]
    t[3] = dict(t[3], body=dict(t[3]["body"], trit=-1))
    assert backfill_check(t)["broken"][:1] == [3]
    t = [dict(x) for x in clean]
    t[0] = dict(t[0], rate_commit=hashlib.sha256(b"x").hexdigest())
    assert backfill_check(t)["broken"][:1] == [0]
    t = [dict(x) for x in clean]
    t[-1] = dict(t[-1], rate=0.06)
    assert backfill_check(t)["broken"] == [len(clean) - 1]

    return {
        "ok": True,
        "roadmap": ROADMAP_ITEM,
        "known_close": known,
        "pack_vector": vec.hex(),
        "bind": BIND,
        "bitnetd_bind": BITNETD_BIND,
        "ports": list(PORTS),
        "rate": RATE,
        "cases": [f"{c}.{m}" for c, m, _ in CASES],
        "green_close": clean[-1]["close"],
        "compatible_engines": list(COMPATIBLE_ENGINES),
        "flags": {"mint": MINT, "socket": SOCKET, "layer_one": LAYER_ONE, "fetch": FETCH,
                  "ue5_launch": UE5_LAUNCH, "model_pull": MODEL_PULL,
                  "subprocess": SUBPROCESS, "released": RELEASED},
    }


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        print(json.dumps(self_check(), indent=2, sort_keys=True))
        return 0
    if "--run" in argv:
        i = argv.index("--run")
        run = json.loads(argv[i + 1])
        ledger: list[dict[str, Any]] = []
        link = append_run(ledger, GENESIS, run)
        print(json.dumps({"run": link, "backfill_check": backfill_check(ledger)},
                         indent=2, sort_keys=True))
        return 0 if link["body"]["verdict"] == 1 else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
