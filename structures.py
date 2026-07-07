# The structure library (brief step 2) and the firing walk (spec §3).
#
# The library started EMPTY. Every structure below was added only when the
# message-board workload could not be expressed without it; the reason and
# date for each is in structure-log.md, which is the primary experimental
# output of this project.
#
# Run-2 revision (post-review, see friction-log.md #6): `eval` was a
# universal interpreter and would have frozen the §6 count forever — it is
# GONE, and nothing in the library can fire in-flight bytes. Demanding a
# stored instruction by reference is core machinery (a grammar node, spec
# §3 step 1 / A4), handled by the firing walk below, which also subsumed
# `read-file`. The library is now 3 structures.
#
# Rules enforced here:
#   - Structures are immutable after load: the registry is populated once at
#     import and never touched again (MappingProxyType makes that physical).
#   - Non-terminal structures are pure and deterministic: bytes in, bytes
#     out, no clock, no randomness, no I/O.
#   - WRITE_FILE is the only terminal — the only structure allowed to touch
#     the world on the way out. The way in (demand) is core machinery.
#   - A firing the world refuses returns the reserved error form, never a
#     value that merely says "error" (spec-amendments.md #2).
#
# Firing walks the instruction bytes directly — there is no decoded tree.
# Same structure + same values = same result, always (spec §2 "Firing").

import os
import types

import instruction
from instruction import DEMAND, ERROR, FIRE, VALUE, read_uvarint

# Structure IDs — frozen. Wire compatibility is by construction (spec A1).
CONCAT = 1
QUOTE = 2
WRITE_FILE = 3

# Root against which references resolve — for demand nodes and the
# write-file terminal alike. Set once by the router at startup. A path
# value in an instruction is a reference relative to this root (spec §2
# "Reference" — equivalent role to a file path today).
_root = None


class FiringError(Exception):
    """The world refused this firing (missing reference, escaping
    reference, no such structure). Becomes an error node at the edge."""


def set_root(path):
    global _root
    _root = os.path.abspath(path)
    os.makedirs(_root, exist_ok=True)


def _resolve(ref):
    p = os.path.abspath(os.path.join(_root, ref.decode()))
    if not p.startswith(_root + os.sep):
        raise FiringError("reference escapes the terminal root")
    return p


def _concat(args):
    return b"".join(args)


def _quote(args):
    return instruction.V(args[0])


def _write_file(args):
    path = _resolve(args[0])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(args[1])
    return args[0]  # output is the reference, demandable onward


REGISTRY = types.MappingProxyType(
    {
        CONCAT: ("concat", False, _concat),
        QUOTE: ("quote", False, _quote),
        WRITE_FILE: ("write-file", True, _write_file),
    }
)


def fire(buf, counter=None):
    """Fire one instruction whole (spec §3 step 4) and return its output
    bytes; raise FiringError if the world refuses anywhere in the tree
    (the whole firing aborts — it is indivisible, so it cannot half-land).
    `counter` is measurement instrumentation: a one-element list
    incremented per structure invocation, including those reached through
    demand. It has no effect on results."""

    def walk(pos):
        tag = buf[pos]
        pos += 1
        if tag == VALUE:
            length, pos = read_uvarint(buf, pos)
            end = pos + length
            return buf[pos:end], end
        if tag == DEMAND:
            # Demanding = reading = firing (brief step 5). Core machinery,
            # not a library structure: the reference names an unsent
            # instruction; its arrival here IS the event (spec A3).
            length, pos = read_uvarint(buf, pos)
            end = pos + length
            ref = buf[pos:end]
            try:
                with open(_resolve(ref), "rb") as f:
                    stored = f.read()
            except FileNotFoundError:
                raise FiringError(f"nothing at reference {ref.decode()!r}")
            return fire(stored, counter), end
        if tag == ERROR:
            # A demanded instruction may itself carry a refusal; it
            # propagates — the tree containing it cannot produce a value.
            length, pos = read_uvarint(buf, pos)
            raise FiringError(buf[pos : pos + length].decode())
        if tag == FIRE:
            sid, pos = read_uvarint(buf, pos)
            argc, pos = read_uvarint(buf, pos)
            args = []
            for _ in range(argc):
                out, pos = walk(pos)
                args.append(out)
            if sid not in REGISTRY:
                # A firing pattern that selects no resident capability
                # selects nothing (spec §4: malformed is unexpressible).
                raise FiringError(f"no structure {sid}")
            if counter is not None:
                counter[0] += 1
            _name, _terminal, fn = REGISTRY[sid]
            return fn(args), pos
        raise instruction.BadTag(f"0x{tag:02x}")

    out, _end = walk(0)
    return out
