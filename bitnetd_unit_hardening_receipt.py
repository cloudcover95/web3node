"""bitnetd.service hardening receipt: per-directive unit audit + side-commit + rate lock.

BETA_TO_OS item: JuniorLLM docs/BETA_TO_OS.md "JuniorOS overlay" (Debian/Alpine
+ os-release.junior + hardened bitnetd.service + juniorctl on PATH). This file
covers only the "hardened bitnetd.service" part: it parses a systemd unit as
text and records, directive by directive, whether the hardening the overlay
expects is present, plus whether the bind stays on 127.0.0.1:8765. It is a new
capability; it does not import, wrap, or re-derive any other team file.
Advances live-beta receipt chains / backfill_check at rate 0.05.

Read-only: the unit is read as text (a path you pass, or the built-in
reference sample). It never writes a unit, never calls systemctl, never opens
a socket, never fetches, never launches anything.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Run: python3 bitnetd_unit_hardening_receipt.py --selftest
     python3 bitnetd_unit_hardening_receipt.py --unit /path/to/bitnetd.service
"""
from __future__ import annotations

import hashlib
import json
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
MODEL_PULL = False
RELEASED = 0
BIND = "127.0.0.1"
BITNETD_BIND = "127.0.0.1:8765"
PORTS = ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
COMPATIBLE_ENGINES = ("web3node", "stocksnode", "JuniorLLM", "BitNet-mlx")

# Expected [Service] hardening for the overlay's bitnetd unit (key, required value).
# Value None means "key present with an empty value" (capability sets cleared).
HARDENING: tuple[tuple[str, str | None], ...] = (
    ("NoNewPrivileges", "yes"),
    ("ProtectSystem", "strict"),
    ("ProtectHome", "yes"),
    ("PrivateTmp", "yes"),
    ("PrivateDevices", "yes"),
    ("ProtectKernelTunables", "yes"),
    ("ProtectKernelModules", "yes"),
    ("ProtectControlGroups", "yes"),
    ("RestrictSUIDSGID", "yes"),
    ("RestrictNamespaces", "yes"),
    ("LockPersonality", "yes"),
    ("MemoryDenyWriteExecute", "yes"),
    ("CapabilityBoundingSet", None),
    ("AmbientCapabilities", None),
)

REFERENCE_UNIT = """[Unit]
Description=Junior BitNet local inference (loopback)

[Service]
Type=simple
User=nobody
ExecStart=/usr/local/bin/junior-bitnetd
Environment=JUNIOR_OFFLINE=1
Environment=JUNIOR_BIND=127.0.0.1:8765
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
CapabilityBoundingSet=
AmbientCapabilities=
MemoryMax=2G
TasksMax=256

[Install]
WantedBy=multi-user.target
"""

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


def parse_service_section(unit_text: str) -> dict[str, list[str]]:
    """Parse the [Service] section into key -> list of values (last wins for checks)."""
    section = ""
    out: dict[str, list[str]] = {}
    for raw in unit_text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Service" or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out.setdefault(key.strip(), []).append(val.strip())
    return out


def bind_state(svc: dict[str, list[str]]) -> dict[str, Any]:
    """Find JUNIOR_BIND in Environment= lines; loopback 8765 only is ok."""
    binds: list[str] = []
    for env in svc.get("Environment", []):
        for tok in env.replace('"', " ").split():
            if tok.startswith("JUNIOR_BIND="):
                binds.append(tok.split("=", 1)[1])
    bind = binds[-1] if binds else ""
    return {
        "bind": bind,
        "bind_ok": bind == BITNETD_BIND,
        "wildcard": any(b.startswith("0.0.0.0") or b.startswith("[::]") for b in binds),
    }


def audit_unit(unit_text: str) -> dict[str, Any]:
    """Per-directive hardening audit. Trit per directive: 1 ok, 0 wrong value, -1 missing."""
    svc = parse_service_section(unit_text)
    directives: dict[str, int] = {}
    for key, want in HARDENING:
        vals = svc.get(key)
        if vals is None:
            directives[key] = -1
        else:
            got = vals[-1]
            directives[key] = 1 if got == (want or "") else 0
    b = bind_state(svc)
    return {
        "unit": "bitnetd.service",
        "directives": directives,
        "bind": b["bind"],
        "bind_ok": b["bind_ok"],
        "wildcard_bind": b["wildcard"],
        "hardened": all(v == 1 for v in directives.values()) and b["bind_ok"] and not b["wildcard"],
        "socket": SOCKET,
        "fetch": FETCH,
    }


def audit_trits(audit: dict[str, Any]) -> list[int]:
    """Directive trits in HARDENING order, then bind trit (1 loopback, -1 wildcard, 0 other)."""
    trits = [audit["directives"][k] for k, _ in HARDENING]
    if audit["wildcard_bind"]:
        trits.append(-1)
    else:
        trits.append(1 if audit["bind_ok"] else 0)
    return trits


def audit_text(audit: dict[str, Any]) -> str:
    return json.dumps(audit, sort_keys=True, separators=(",", ":"))


def append_hardening_receipt(
    ledger: list[dict[str, Any]], prev: str, unit_text: str
) -> dict[str, Any]:
    """Audit a unit text and append one receipt with side-commit and rate_commit."""
    audit = audit_unit(unit_text)
    trits = audit_trits(audit)
    text = audit_text(audit)
    pk = pack(trits)
    link = {
        "prev": prev,
        "trits": trits,
        "text": text,
        "hardened": audit["hardened"],
        "commit": side_commit(prev, pk, text),
        "rate_commit": rate_lock_commit(prev, pk),
        "rate": RATE,
    }
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Live-beta backfill gate: contiguous chain; gaps lists broken indices; soft lists unhardened."""
    gaps: list[int] = []
    soft: list[int] = []
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
        try:
            if not json.loads(link["text"]).get("hardened"):
                soft.append(i)
        except (ValueError, KeyError, AttributeError):
            gaps.append(i)
        cur = link.get("commit", cur)
    return {"ok": not gaps, "gaps": sorted(set(gaps)), "unhardened": soft, "tip": cur, "n": len(ledger)}


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, known close, audits, tamper and gap detection."""
    assert BIND == "127.0.0.1" and BITNETD_BIND.startswith("127.0.0.1:")
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL)
    assert RELEASED == 0 and RATE == 0.05

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known

    good = audit_unit(REFERENCE_UNIT)
    assert good["hardened"] is True and good["bind"] == BITNETD_BIND

    missing = REFERENCE_UNIT.replace("NoNewPrivileges=yes\n", "")
    weak = REFERENCE_UNIT.replace("ProtectSystem=strict", "ProtectSystem=full")
    wild = REFERENCE_UNIT.replace("JUNIOR_BIND=127.0.0.1:8765", "JUNIOR_BIND=0.0.0.0:8765")
    other_section = REFERENCE_UNIT.replace("[Install]", "[Install]\nPrivateTmp=no")
    assert audit_unit(missing)["directives"]["NoNewPrivileges"] == -1
    assert audit_unit(weak)["directives"]["ProtectSystem"] == 0
    wa = audit_unit(wild)
    assert wa["wildcard_bind"] and not wa["hardened"] and audit_trits(wa)[-1] == -1
    assert audit_unit(other_section)["hardened"] is True  # only [Service] counts
    caps = REFERENCE_UNIT.replace("CapabilityBoundingSet=\n", "CapabilityBoundingSet=CAP_NET_RAW\n")
    assert audit_unit(caps)["directives"]["CapabilityBoundingSet"] == 0

    ledger: list[dict[str, Any]] = []
    a = append_hardening_receipt(ledger, GENESIS, REFERENCE_UNIT)
    b = append_hardening_receipt(ledger, a["commit"], missing)
    c = append_hardening_receipt(ledger, b["commit"], wild)
    bf = backfill_check(ledger)
    assert bf["ok"] and bf["gaps"] == [] and bf["n"] == 3 and bf["tip"] == c["commit"]
    assert bf["unhardened"] == [1, 2]

    t = [dict(x) for x in ledger]
    t[0] = dict(t[0], text=t[0]["text"].replace("127.0.0.1:8765", "127.0.0.1:9999"))
    assert 0 in backfill_check(t)["gaps"]
    r = [dict(x) for x in ledger]
    r[1] = dict(r[1], rate_commit=hashlib.sha256(b"x").hexdigest())
    assert 1 in backfill_check(r)["gaps"]
    d = [ledger[0], ledger[2]]
    assert 1 in backfill_check(d)["gaps"]

    return {
        "ok": True,
        "bind": BIND,
        "bitnetd_bind": BITNETD_BIND,
        "ports": list(PORTS),
        "rate": RATE,
        "pack_vector": vec.hex(),
        "close_home_4a44": known,
        "directives": len(HARDENING),
        "engines": list(COMPATIBLE_ENGINES),
        "tip": bf["tip"],
        "flags": {"mint": MINT, "socket": SOCKET, "layer_one": LAYER_ONE,
                  "fetch": FETCH, "ue5_launch": UE5_LAUNCH, "released": RELEASED},
    }


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    if "--unit" in argv:
        i = argv.index("--unit")
        if i + 1 >= len(argv):
            print("usage: --unit /path/to/bitnetd.service", file=sys.stderr)
            return 2
        with open(argv[i + 1], "r", encoding="utf-8") as fh:
            unit_text = fh.read()
    else:
        unit_text = REFERENCE_UNIT
    ledger: list[dict[str, Any]] = []
    link = append_hardening_receipt(ledger, GENESIS, unit_text)
    print(json.dumps({"receipt": link, "backfill": backfill_check(ledger)}, sort_keys=True))
    return 0 if link["hardened"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
