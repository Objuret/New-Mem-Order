"""Replication between worlds (phase 5): the wire, at last.

A sync is a world-side program (a demander) that moves unsent
instructions from one world to another by firing emit instructions at
the destination router. Nothing new exists for the wire because the
stored form IS the wire form (spec section 8): every file travels as an
opaque value inside an ordinary emit — the driver never interprets the
bytes it moves, the same way cp never has. Interpretation happens in
exactly one place, as always: the destination firing it on demand.

Discovery is namespace enumeration — the same act as readdir over the
reference tree (phase-3 precedent). A manifest of "what exists" would be
the banned index; the directory of head references already is the
catalog. Incremental sync selects by backing mtime, which is world
metadata about references, not model state; the high-water mark lives
with the driver (its own state, like rsync's).

If the destination refuses with "unknown structure id N", the sender is
holding condensed instructions the receiver has no residence for. The
refusal names what's missing; shipping the library files under lib/ and
reloading the destination router heals it. The dictionary distributes
itself through the machinery that already exists — refusals and emits —
with no negotiation protocol. (Whether a router may load a structure
lazily at first reference instead of at start is an OPEN question for
Jocke — DECISIONS.md section 2.2. Until ruled, residency changes only at
router start, so a lib delivery is followed by a restart.)
"""

import os
import socket

from .instruction import Incomplete, comp, demand, lit, outcome, skip
from .structures import EMIT_DISK


def call(host, port, instr):
    with socket.create_connection((host, port)) as s:
        s.sendall(instr)
        buf = b""
        while True:
            try:
                end = skip(buf, 0)
                break
            except Incomplete:
                data = s.recv(65536)
                if not data:
                    return "error", b"router closed the connection"
                buf += data
    return outcome(buf[:end])


def sync(src_world, dst_host, dst_port, since_ns=0, lib="include",
         prefixes=None):
    """Copy unsent instructions newer than since_ns from src_world into
    the world behind the destination router. lib: "include" | "skip" |
    "only". prefixes: optional list of reference prefixes to ship —
    replication must respect write ownership (a node ships only what its
    writer owns), or a stale copy of a foreign head clobbers a fresh one
    and the lost-update window reopens at the copy layer (FRICTION.md
    #31). Returns wire/file accounting."""
    src = os.path.realpath(src_world)
    wire_bytes = 0
    content_bytes = 0
    files = 0
    refusals = []
    for dirpath, _, names in sorted(os.walk(src)):
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            ref = os.path.relpath(path, src)
            is_lib = ref.split(os.sep)[0] == "lib"
            if (lib == "skip" and is_lib) or (lib == "only" and not is_lib):
                continue
            if prefixes is not None and not any(ref.startswith(p) for p in prefixes):
                continue
            st = os.lstat(path)
            if st.st_mtime_ns <= since_ns:
                continue
            with open(path, "rb") as f:
                data = f.read()   # opaque: moved, never interpreted
            instr = comp(EMIT_DISK, lit(ref), lit(data))
            kind, out = call(dst_host, dst_port, instr)
            if kind == "error":
                refusals.append((ref, out))
                continue
            wire_bytes += len(instr)
            content_bytes += len(data)
            files += 1
    return dict(files=files, wire_bytes=wire_bytes,
                content_bytes=content_bytes, refusals=refusals)
