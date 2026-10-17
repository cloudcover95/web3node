"""GGUF header receipt: fixed 24-byte header audit + side-commit + rate lock.

ROADMAP item: JuniorHome docs/ROADMAP.md #2 GGUF ("operator sets JUNIOR_GGUF.
Bots do not download. web3node/probe_future.py"). This file covers a different
part of that item than gguf_receipt_ledger.py (which records env presence via
os.stat): it records whether the operator-set file actually carries a sane
GGUF header (magic b"GGUF", version 2 or 3, tensor and kv counts within
bounds). It is a new capability; it never imports, wraps, rewrites, or
re-derives probe_future.py, gguf_receipt_ledger.py, or any other team file.
Advances live-beta receipt chains / backfill_check at rate 0.05.

Read-only and bounded: header bytes come from the caller, or with --read-header
at most 24 bytes are read from the local path the operator put in JUNIOR_GGUF.
It never downloads, never loads tensors, never hashes the model, no network,
no sockets, no launches.

Stdlib only. Close: sha256(prev || pack || text)[:16] with i2s 2-bit pack
(0->0, 1->1, -1->2), MSB first, zero-padded (pack vector 4a44). Rate lock
commits rate 0.05 beside the pack as sha256(prev || pack || b"0.05") full
hexdigest (JuniorHome docs/JUNIORS_RATE.md).

Run: python3 gguf_header_receipt.py --selftest
     JUNIOR_GGUF=/path/model.gguf python3 gguf_header_receipt.py --read-header
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from typing import Any, Mapping

RATE = 0.05
RATE_BYTES = b"0.05"
GENESIS = "0" * 16
ENV_KEY = "JUNIOR_GGUF"
HEADER_LEN = 24  # magic(4) + version u32 + tensor_count u64 + kv_count u64, little-endian
MAGIC = b"GGUF"
VERSIONS = (2, 3)
MAX_TENSORS = 1 << 20
MAX_KV = 1 << 16

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


def audit_header(head: bytes, name: str = "") -> dict[str, Any]:
    """Audit up to the first 24 bytes. Trits: 1 ok, 0 out of range, -1 missing/bad."""
    head = bytes(head[:HEADER_LEN])
    full = len(head) == HEADER_LEN
    magic_t = 1 if head[:4] == MAGIC else -1
    version = tensors = kvs = None
    ver_t = cnt_t = kv_t = -1
    if full:
        version, tensors, kvs = struct.unpack("<IQQ", head[4:])
        ver_t = 1 if version in VERSIONS else 0
        cnt_t = 1 if 0 < tensors <= MAX_TENSORS else 0
        kv_t = 1 if kvs <= MAX_KV else 0
    trits = [1 if full else -1, magic_t, ver_t, cnt_t, kv_t]
    return {
        "name": os.path.basename(name),
        "header_len": len(head),
        "magic_ok": magic_t == 1,
        "version": version,
        "tensor_count": tensors,
        "kv_count": kvs,
        "trits": trits,
        "sane": all(t == 1 for t in trits),
        "model_pull": MODEL_PULL,
        "fetch": FETCH,
    }


def read_operator_header(env: Mapping[str, str] | None = None) -> tuple[str, bytes]:
    """Read at most 24 bytes from the operator-set JUNIOR_GGUF path. Never downloads."""
    env = os.environ if env is None else env
    path = env.get(ENV_KEY, "")
    if not path or "://" in path or not os.path.isfile(path):
        return path, b""
    with open(path, "rb") as fh:
        return path, fh.read(HEADER_LEN)


def audit_text(audit: dict[str, Any]) -> str:
    return json.dumps(audit, sort_keys=True, separators=(",", ":"))


def append_header_receipt(
    ledger: list[dict[str, Any]], prev: str, head: bytes, name: str = ""
) -> dict[str, Any]:
    """Audit header bytes and append one receipt with side-commit and rate_commit."""
    audit = audit_header(head, name)
    trits = list(audit["trits"])
    text = audit_text(audit)
    pk = pack(trits)
    link = {
        "prev": prev,
        "trits": trits,
        "text": text,
        "sane": audit["sane"],
        "commit": side_commit(prev, pk, text),
        "rate_commit": rate_lock_commit(prev, pk),
        "rate": RATE,
    }
    ledger.append(link)
    return link


def backfill_check(ledger: list[dict[str, Any]], prev: str = GENESIS) -> dict[str, Any]:
    """Live-beta backfill gate: contiguous chain; gaps lists broken links; insane lists bad headers."""
    gaps: list[int] = []
    insane: list[int] = []
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
        ):
            gaps.append(i)
        if not body.get("sane"):
            insane.append(i)
        cur = link.get("commit", cur)
    return {"ok": not gaps, "gaps": gaps, "insane": insane, "tip": cur, "n": len(ledger)}


def _header(version: int = 3, tensors: int = 332, kvs: int = 24, magic: bytes = MAGIC) -> bytes:
    return magic + struct.pack("<IQQ", version, tensors, kvs)


def self_check() -> dict[str, Any]:
    """Flags, bind, ports, pack vector 4a44, known close, header audits, tamper and gap detection."""
    assert BIND == "127.0.0.1"
    assert PORTS == ("Home", "OSai", "FieldCore", "Flagstaff", "JuniorLLM")
    assert not (MINT or SOCKET or LAYER_ONE or FETCH or UE5_LAUNCH or MODEL_PULL)
    assert RELEASED == 0 and RATE == 0.05

    vec = pack([1, 0, -1, -1, 1, 0, 1])
    assert vec.hex() == "4a44", vec.hex()
    known = side_commit(GENESIS, vec, "home")
    assert known == "dd07dea74a142604", known

    good = audit_header(_header(), "/models/junior-2b.gguf")
    assert good["sane"] and good["version"] == 3 and good["name"] == "junior-2b.gguf"
    assert audit_header(_header(magic=b"GGML"))["trits"][1] == -1
    assert audit_header(_header(version=1))["trits"][2] == 0
    assert audit_header(_header(tensors=0))["trits"][3] == 0
    assert audit_header(_header(kvs=MAX_KV + 1))["trits"][4] == 0
    short = audit_header(b"GGUF\x03")
    assert short["trits"] == [-1, 1, -1, -1, -1] and not short["sane"]

    # Operator path: unset, URL, and a missing file all yield no bytes; nothing is fetched.
    assert read_operator_header({}) == ("", b"")
    assert read_operator_header({ENV_KEY: "https://x/y.gguf"})[1] == b""
    assert read_operator_header({ENV_KEY: "/nonexistent/junior.gguf"})[1] == b""

    ledger: list[dict[str, Any]] = []
    a = append_header_receipt(ledger, GENESIS, _header(), "junior-2b.gguf")
    b = append_header_receipt(ledger, a["commit"], _header(magic=b"GGML"), "old.bin")
    c = append_header_receipt(ledger, b["commit"], b"", "")
    bf = backfill_check(ledger)
    assert bf["ok"] and bf["gaps"] == [] and bf["n"] == 3 and bf["tip"] == c["commit"]
    assert bf["insane"] == [1, 2]

    t = [dict(x) for x in ledger]
    t[0] = dict(t[0], text=t[0]["text"].replace('"version":3', '"version":2'))
    assert 0 in backfill_check(t)["gaps"]
    r = [dict(x) for x in ledger]
    r[1] = dict(r[1], rate_commit=hashlib.sha256(b"x").hexdigest())
    assert 1 in backfill_check(r)["gaps"]
    d = [ledger[0], ledger[2]]
    assert 1 in backfill_check(d)["gaps"]

    return {
        "ok": True,
        "bind": BIND,
        "ports": list(PORTS),
        "rate": RATE,
        "pack_vector": vec.hex(),
        "close_home_4a44": known,
        "header_len": HEADER_LEN,
        "engines": list(COMPATIBLE_ENGINES),
        "tip": bf["tip"],
        "flags": {"mint": MINT, "socket": SOCKET, "layer_one": LAYER_ONE, "fetch": FETCH,
                  "ue5_launch": UE5_LAUNCH, "model_pull": MODEL_PULL, "released": RELEASED},
    }


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    if "--read-header" in argv:
        name, head = read_operator_header()
    else:
        name, head = "", b""
    ledger: list[dict[str, Any]] = []
    link = append_header_receipt(ledger, GENESIS, head, name)
    print(json.dumps({"receipt": link, "backfill": backfill_check(ledger)}, sort_keys=True))
    return 0 if link["sane"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
