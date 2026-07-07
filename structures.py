# The structure library (brief step 2) and the firing walk (spec §3).
#
# The library started EMPTY. Every structure below was added only when the
# message-board workload could not be expressed without it; the reason and
# date for each is in structure-log.md, which is the primary experimental
# output of this project.
#
# Rules enforced here:
#   - Structures are immutable after load: the registry is populated once at
#     import and never touched again (MappingProxyType makes that physical).
#   - Non-terminal structures are pure and deterministic: bytes in, bytes
#     out, no clock, no randomness, no I/O.
#   - Terminals (READ_FILE, WRITE_FILE) are the only structures allowed to
#     touch the world, and they are flagged as such.
#
# Firing walks the instruction bytes directly — there is no decoded tree.
# Same structure + same values = same result, always (spec §2 "Firing").

import os
import types

import instruction
from instruction import FIRE, VALUE, read_uvarint

# Structure IDs — frozen. Wire compatibility is by construction (spec A1).
CONCAT = 1
QUOTE = 2
EVAL = 3
READ_FILE = 4
WRITE_FILE = 5

# Root under which the file terminals operate. Set once by the router at
# startup; a path value in an instruction is a reference relative to this
# root (spec §2 "Reference" — equivalent role to a file path today).
_root = None


def set_root(path):
    global _root
    _root = os.path.abspath(path)
    os.makedirs(_root, exist_ok=True)


def _resolve(ref):
    p = os.path.abspath(os.path.join(_root, ref.decode()))
    if not p.startswith(_root + os.sep):
        raise ValueError("reference escapes the terminal root")
    return p


def _concat(args, _fire):
    return b"".join(args)


def _quote(args, _fire):
    return instruction.V(args[0])


def _eval(args, fire):
    return fire(args[0])


def _read_file(args, _fire):
    with open(_resolve(args[0]), "rb") as f:
        return f.read()


def _write_file(args, _fire):
    path = _resolve(args[0])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(args[1])
    return args[0]  # output is the reference, demandable onward


REGISTRY = types.MappingProxyType(
    {
        CONCAT: ("concat", False, _concat),
        QUOTE: ("quote", False, _quote),
        EVAL: ("eval", False, _eval),
        READ_FILE: ("read-file", True, _read_file),
        WRITE_FILE: ("write-file", True, _write_file),
    }
)


def fire(buf, counter=None):
    """Fire one instruction whole (spec §3 step 4) and return its output
    bytes. `counter` is measurement instrumentation: a one-element list
    incremented per structure invocation, including those reached through
    EVAL. It has no effect on results."""

    def walk(pos):
        tag = buf[pos]
        pos += 1
        if tag == VALUE:
            length, pos = read_uvarint(buf, pos)
            end = pos + length
            return buf[pos:end], end
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
                raise instruction.BadTag(f"no structure {sid}")
            if counter is not None:
                counter[0] += 1
            _name, _terminal, fn = REGISTRY[sid]
            return fn(args, lambda b: fire(b, counter)), pos
        raise instruction.BadTag(f"0x{tag:02x}")

    out, _end = walk(0)
    return out
