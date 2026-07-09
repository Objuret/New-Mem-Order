"""The structure library (spec A1; brief step 2).

Started EMPTY. Every structure here was forced by the message-board
workload; LIBRARY.md is the running log and the two must not drift.

Rules held by review, not machinery:
- pure structures are deterministic: no clock reads, no randomness, no I/O
- terminals are the only structures with side effects, marked TERMINAL
- nothing here fires values: no eval, no apply, no interpreter

The registry is built once at router start and never mutated (A1 --
immutability; the mmap'd-native realization in spec section 8 is
approximated here by a read-only mapping).
"""

import os
from types import MappingProxyType

from .instruction import Refusal

CONCAT = 1
EMIT_DISK = 2
SELECT = 3
TALLY = 4
LAST = 5
SUM = 6
SORT = 7
DIV = 8
SUB = 9
PICK = 10
UNIQ = 11

# Promoted shapes (phase 4): structure ids >= PROMOTED_BASE are loaded
# from <root>/lib at router start. A shape body may contain operand-slot
# markers comp(HOLE_BASE + k) that resolve to the k-th operand VALUE at
# fire time -- value holes only, never structure or reference holes, so
# nothing a shape does can fire a value or compute a demand.
HOLE_BASE = 90
PROMOTED_BASE = 100


def resolve_ref(world_root, ref):
    """A reference is a relative path inside the world root (spec section 2,
    Reference). Anything else is unexpressible -- refused, not sanitized.
    Shared by the demand grammar node and the emit-disk terminal."""
    try:
        rel = ref.decode()
    except UnicodeDecodeError:
        raise Refusal(b"bad reference: " + ref)
    if not rel or rel.startswith(("/", "\\")) or ".." in rel.split("/"):
        raise Refusal(b"bad reference: " + ref)
    path = os.path.realpath(os.path.join(world_root, rel))
    if not path.startswith(os.path.realpath(world_root) + os.sep):
        raise Refusal(b"bad reference: " + ref)
    return path


def _concat(values):
    return b"".join(values)


# Phase-2 structures: computation over a value, with every condition a
# comparison operand (a value), never a sub-instruction that gets fired.
# The record convention (what delimits a segment, what marks a user) is
# NOT resident here -- it arrives as values from the demander, who owns
# the rendering it is querying.

def _segments(haystack, delim):
    # A delimiter is a terminator, not a separator: "a\nb\n" is two
    # segments. Pinned once, deterministically (FRICTION.md #12).
    if not delim:
        raise Refusal(b"empty delimiter")
    parts = haystack.split(delim)
    if parts and parts[-1] == b"":
        parts.pop()
    return parts


def _select(values):
    if len(values) != 3:
        raise Refusal(b"select takes (value, delimiter, needle)")
    hay, delim, needle = values
    return b"".join(p + delim for p in _segments(hay, delim) if needle in p)


def _tally(values):
    if len(values) != 3:
        raise Refusal(b"tally takes (value, delimiter, needle)")
    hay, delim, needle = values
    n = sum(1 for p in _segments(hay, delim) if needle in p)
    # Values are bytes; counts leave as decimal ASCII -- the library's
    # one shared number convention (FRICTION.md #11).
    return b"%d" % n


def _last(values):
    if len(values) != 3:
        raise Refusal(b"last takes (value, delimiter, count)")
    hay, delim, n = values
    if not n.isdigit():
        raise Refusal(b"last: count must be decimal digits, got " + n)
    k = int(n)
    parts = _segments(hay, delim)
    if k == 0:
        return b""
    return b"".join(p + delim for p in parts[-k:])


# Phase-4 structures: arithmetic and reordering. Numbers ride as decimal
# ASCII (the phase-2 convention); a non-numeric segment where a number is
# required is a refusal, not a coercion.

def _int(b):
    if b.isdigit() or (b[:1] == b"-" and b[1:].isdigit()):
        return int(b)
    raise Refusal(b"not a number: " + b)


def _sum(values):
    if len(values) != 2:
        raise Refusal(b"sum takes (value, delimiter)")
    hay, delim = values
    return b"%d" % sum(_int(p) for p in _segments(hay, delim))


def _sort(values):
    # mode is a VALUE: "num" | "numdesc" | "text" | "textdesc"
    if len(values) != 3:
        raise Refusal(b"sort takes (value, delimiter, mode)")
    hay, delim, mode = values
    if mode not in (b"num", b"numdesc", b"text", b"textdesc"):
        raise Refusal(b"sort: unknown mode " + mode)
    parts = _segments(hay, delim)
    key = _int if mode.startswith(b"num") else None
    parts.sort(key=key, reverse=mode.endswith(b"desc"))
    return b"".join(p + delim for p in parts)


def _div(values):
    if len(values) != 2:
        raise Refusal(b"div takes (numerator, denominator)")
    a, b = _int(values[0]), _int(values[1])
    if b == 0:
        raise Refusal(b"division by zero")
    return b"%d" % (a // b)


def _sub(values):
    if len(values) != 2:
        raise Refusal(b"sub takes (a, b)")
    return b"%d" % (_int(values[0]) - _int(values[1]))


def _uniq(values):
    # collapse ADJACENT duplicate segments (pair with sort for a key set)
    if len(values) != 2:
        raise Refusal(b"uniq takes (value, delimiter)")
    hay, delim = values
    out = []
    for p in _segments(hay, delim):
        if not out or out[-1] != p:
            out.append(p)
    return b"".join(p + delim for p in out)


_CMP = {b"ge": lambda a, b: a >= b, b"gt": lambda a, b: a > b,
        b"le": lambda a, b: a <= b, b"lt": lambda a, b: a < b,
        b"eq": lambda a, b: a == b}


def _pick(values):
    # numeric filter; the comparison operator and threshold are VALUES
    if len(values) != 4:
        raise Refusal(b"pick takes (value, delimiter, op, threshold)")
    hay, delim, op, threshold = values
    if op not in _CMP:
        raise Refusal(b"pick: unknown op " + op)
    t = _int(threshold)
    return b"".join(p + delim for p in _segments(hay, delim)
                    if _CMP[op](_int(p), t))


# --- promoted shapes: loading and firing --------------------------------

class _ShapeCtx:
    """Firing context for a shape body: operand-slot markers resolve to
    the operand values; everything else resolves via the base registry.
    Shape bodies hold no demand nodes -- a shape is a pure transform."""

    def __init__(self, registry, operands):
        self._base = registry
        self._operands = operands
        self.nodes_fired = 0
        self.structures = self

    def get(self, sid):
        if HOLE_BASE <= sid < PROMOTED_BASE:
            k = sid - HOLE_BASE
            if k >= len(self._operands):
                return None
            val = self._operands[k]
            return lambda vv: val if not vv else _hole_refuse()
        return self._base.get(sid)

    def demand(self, ref):
        raise Refusal(b"shape bodies cannot demand")


def _hole_refuse():
    raise Refusal(b"operand slots take no operands")


def make_shape_fn(body, registry):
    from .instruction import Refusal as _R, fire

    def shape(operands):
        ctx = _ShapeCtx(registry, operands)
        value, end = fire(body, 0, ctx)
        if end != len(body):
            raise _R(b"trailing bytes in shape body")
        return value
    return shape


def load_promoted(root, registry):
    """Load lib/<sid> shape bodies as resident structures. A body with no
    operand slots is a content template (phase 3); with slots it is a
    promoted composition shape (phase 4). One mechanism for both."""
    libdir = os.path.join(root, "lib")
    if not os.path.isdir(libdir):
        return registry
    for name in sorted(os.listdir(libdir)):
        with open(os.path.join(libdir, name), "rb") as f:
            registry[int(name)] = make_shape_fn(f.read(), registry)
    return registry


def make_registry(world_root):
    world_root = os.path.realpath(world_root)

    def _emit_disk(values):
        # TERMINAL -- the model's edge (spec section 2, Terminal structure).
        # Hands a value off to the world as a file at a reference. Touches
        # shared world-state, so it binds to exactly one router; its
        # atomicity comes from fires-whole (the single event loop never
        # yields inside a firing).
        if len(values) != 2:
            raise Refusal(b"emit-disk takes (reference, value)")
        ref, content = values
        path = resolve_ref(world_root, ref)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return ref

    return MappingProxyType({
        CONCAT: _concat,        # pure
        EMIT_DISK: _emit_disk,  # TERMINAL
        SELECT: _select,        # pure
        TALLY: _tally,          # pure
        LAST: _last,            # pure
        SUM: _sum,              # pure
        SORT: _sort,            # pure
        DIV: _div,              # pure
        SUB: _sub,              # pure
        PICK: _pick,            # pure
        UNIQ: _uniq,            # pure
    })
