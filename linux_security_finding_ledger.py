"""Linux security finding ledger: per-finding receipts + side-commit + rate lock.

Roadmap item: JuniorLLM docs/BETA_TO_OS.md "Live beta", exit-code side
(steps 1-3: `juniorctl security` and `tests/test_linux_security.py`), as named
for pair B by Quant Chief on 2026-10-18. The step-level exit codes are already
chained elsewhere; this file covers the uncovered gap below them: one receipt
per individual security finding, so a green or red test_linux_security exit
code can be traced back to the exact check that moved it. The matching
handshake/port check belongs to Handshake & Ports in a different file.
This is a new capability: it never imports, runs, wraps, tests, rewrites, or
re-derives juniorctl, test_linux_security, or any other team file, including
my own earlier ledgers.

What it records: the caller hands in a plain dict of declared findings, for
example the JSON printed by `juniorctl security` plus a few file facts:
  unit_ok, missing, seccomp, bind, privileged, docker_socket,
  seccomp_default_action, installer_present, container_doc_present.
Each finding becomes one trit (+1 holds, 0 not declared, -1 fails). The receipt
also maps the findings onto the three test_linux_security cases
(test_unit_hardened, test_seccomp_default_deny, test_installer_exists) and
predicts the suite exit code (0 when every case holds, 1 otherwise), so a
declared exit code that disagrees with its findings shows up as a mismatch.
Offline: no subprocess, no file reads, no network, no sockets, no model pull,
no GGUF download, no UE5 launch.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Ports touched: Home, OSai, FieldCore, Flagstaff, JuniorLLM. Bind 127.0.0.1.

Run: python3 linux_security_finding_ledger.py --selftest
     python3 linux_security_finding_ledger.py --findings '{"unit_ok":true,...}'
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
    "JuniorLLM docs/BETA_TO_OS.md Live beta, exit-code side: juniorctl security "
    "+ tests/test_linux_security.py per-finding ledger"
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
SECCOMP_DENY = "SCMP_ACT_ERRNO"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
COMPATIBLE_ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")

# Finding order is fixed: it is the trit order in every receipt.
FINDINGS = (
    "unit_ok",
    "missing_empty",
    "seccomp",
    "bind",
    "privileged",
    "docker_socket",
    "seccomp_default_deny",
    "installer_present",
    "container_doc_present",
)
# Which findings each test_linux_security case depends on.
CASES = {
    "test_unit_hardened": ("unit_ok", "missing_empty", "seccomp", "privileged", "docker_socket"),
    "test_seccomp_default_deny": ("seccomp_default_deny",),
    "test_installer_exists": ("installer_present", "container_doc_present"),
}

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


def _holds_true(v: Any) -> int:
    if v is True:
        return 1
    if v is False:
        return -1
    return 0


def _holds_false(v: Any) -> int:
    """For flags that must be False (privileged, docker_socket)."""
    if v is False:
        return 1
    if v is True:
        return -1
    return 0


def finding_trits(findings: Mapping[str, Any] | None = None) -> dict[str, int]:
    """Map declared findings to one trit each. Reads only the dict it is given."""
    f = dict(findings or {})
    missing = f.get("missing")
    if missing is None:
        missing_t = 0
    else:
        missing_t = 1 if isinstance(missing, list) and not missing else -1
    bind = f.get("bind")
    bind_t = 0 if bind is None else (1 if str(bind) == BITNETD_BIND else -1)
    action = f.get("seccomp_default_action")
    deny_t = 0 if action is None else (1 if str(action) == SECCOMP_DENY else -1)
    return {
        "unit_ok": _holds_true(f.get("unit_ok")),
        "missing_empty": missing_t,
        "seccomp": _holds_true(f.get("seccomp")),
        "bind": bind_t,
        "privileged": _holds_false(f.get("privileged")),
        "docker_socket": _holds_false(f.get("docker_socket")),
        "seccomp_default_deny": deny_t,
        "installer_present": _holds_true(f.get("installer_present")),
        "container_doc_present": _holds_true(f.get("container_doc_present")),
    }


def audit_findings(findings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Per-finding trits, per-case verdicts, predicted exit code, and mismatch flag."""
    f = dict(findings or {})
    by_name = finding_trits(f)
    trits = [by_name[k] for k in FINDINGS]
    cases: dict[str, int] = {}
    for case, deps in CASES.items():
        ts = [by_name[d] for d in deps]
        cases[case] = -1 if -1 in ts else (0 if 0 in ts else 1)
    failing = [k for k in FINDINGS if by_name[k] == -1]
    undeclared = [k for k in FINDINGS if by_name[k] == 0]
    predicted = None if any(v == 0 for v in cases.values()) else (
        0 if all(v == 1 for v in cases.values()) else 1)
    declared = f.get("exit_code")
    declared = declared if isinstance(declared, int) and not isinstance(declared, bool) else None
    mismatch = declared is not None and predicted is not None and declared != predicted
    missing = f.get("missing") if isinstance(f.get("missing"), list) else []
    return {
        "item": ROADMAP_ITEM,
        "findings": by_name,
        "trits": trits,
        "cases": cases,
        "failing": failing,
        "undeclared": undeclared,
        "missing_directives": sorted(str(m) for m in missing),
        "predicted_exit": predicted,
        "declared_exit": declared,
        "mismatch": mismatch,
        "bind_leak": by_name["bind"] == -1,
        "secure": not failing and not undeclared and not mismatch,
        "subprocess": SUBPROCESS,
        "fetch": FETCH,
    }


def audit_text(audit: dict[str, Any]) -> str:
    return json.dumps(audit, sort_keys=True, separators=(",", ":"))


def append_finding_receipt(
    ledger: list[dict[str, Any]], prev: str, findings: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Audit one findings snapshot and append a receipt with side-commit and rate_commit."""
    audit = audit_findings(findings)
    trits = list(audit["trits"])
    text = audit_text(audit)
    pk = pack(trits)
    link = {
        "prev": prev,
        "trits": trits,
        "text": text,
        "secure": audit["secure"],
        "commit": side_commit(prev, pk, text),
        "rate_commit": rate_lock_commit(prev, pk),
        "rate": RATE,
    }
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Live-beta backfill gate. gaps lists broken links; open lists receipts with a
    failing or undeclared finding; mismatch lists receipts whose declared exit code
    disagrees with their findings; leaks lists receipts with bitnetd off 127.0.0.1:8765."""
    gaps: list[int] = []
    open_: list[int] = []
    mismatch: list[int] = []
    leaks: list[int] = []
    cur = prev
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
            or body.get("secure") != link.get("secure")
        ):
            gaps.append(i)
        if body.get("failing") or body.get("undeclared"):
            open_.append(i)
        if body.get("mismatch"):
            mismatch.append(i)
        if body.get("bind_leak"):
            leaks.append(i)
        cur = link.get("commit", cur)
    return {"ok": not gaps and not mismatch and not leaks, "gaps": gaps, "open": open_,
            "mismatch": mismatch, "leaks": leaks, "tip": cur, "n": len(ledger)}


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, known close, finding audits, tamper and gap detection."""
    assert BIND == "127.0.0.1" and BITNETD_BIND.startswith(BIND + ":")
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL or SUBPROCESS)
    assert RELEASED == 0 and RATE == 0.05
    assert "subprocess" not in sys.modules or not SUBPROCESS

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known

    green = {"unit_ok": True, "missing": [], "seccomp": True, "bind": "127.0.0.1:8765",
             "privileged": False, "docker_socket": False,
             "seccomp_default_action": "SCMP_ACT_ERRNO", "installer_present": True,
             "container_doc_present": True, "exit_code": 0}
    a = audit_findings(green)
    assert a["secure"] and a["predicted_exit"] == 0 and a["trits"] == [1] * 9
    assert all(v == 1 for v in a["cases"].values())
    blank = audit_findings()
    assert not blank["secure"] and blank["trits"] == [0] * 9 and blank["predicted_exit"] is None
    soft = audit_findings(dict(green, unit_ok=False, missing=["NoNewPrivileges"], exit_code=1))
    assert soft["cases"]["test_unit_hardened"] == -1 and soft["predicted_exit"] == 1
    assert soft["failing"] == ["unit_ok", "missing_empty"] and not soft["mismatch"]
    lie = audit_findings(dict(green, privileged=True, exit_code=0))
    assert lie["mismatch"] and lie["failing"] == ["privileged"]
    allow = audit_findings(dict(green, seccomp_default_action="SCMP_ACT_ALLOW", exit_code=1))
    assert allow["cases"]["test_seccomp_default_deny"] == -1 and not allow["mismatch"]
    wide = audit_findings(dict(green, bind="192.168.1.20:8765"))
    assert wide["bind_leak"] and wide["trits"][3] == -1
    # bind is not a test_linux_security case, so the suite still predicts exit 0.
    assert wide["predicted_exit"] == 0

    ledger: list[dict[str, Any]] = []
    r0 = append_finding_receipt(ledger, GENESIS, green)
    r1 = append_finding_receipt(ledger, r0["commit"], dict(green, installer_present=None))
    r2 = append_finding_receipt(ledger, r1["commit"], dict(green, docker_socket=True, exit_code=1))
    bf = backfill_check(ledger)
    assert bf["ok"] and bf["gaps"] == [] and bf["n"] == 3 and bf["tip"] == r2["commit"]
    assert bf["open"] == [1, 2] and bf["mismatch"] == [] and bf["leaks"] == []

    lk = list(ledger)
    r3 = append_finding_receipt(lk, r2["commit"], dict(green, privileged=True, exit_code=0))
    append_finding_receipt(lk, r3["commit"], dict(green, bind="192.168.1.20:8765"))
    bl = backfill_check(lk)
    assert bl["mismatch"] == [3] and bl["leaks"] == [4] and not bl["ok"] and bl["gaps"] == []

    t = [dict(x) for x in ledger]
    t[1] = dict(t[1], text=t[1]["text"].replace('"installer_present":0', '"installer_present":1'))
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
    findings: dict[str, Any] = {}
    if "--findings" in argv:
        i = argv.index("--findings")
        findings = json.loads(argv[i + 1]) if i + 1 < len(argv) else {}
    ledger: list[dict[str, Any]] = []
    link = append_finding_receipt(ledger, GENESIS, findings)
    print(json.dumps({"receipt": link, "backfill": backfill_check(ledger)}, sort_keys=True))
    return 0 if link["secure"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
