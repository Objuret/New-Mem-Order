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
        CONCAT: _concat,      # pure
        EMIT_DISK: _emit_disk,  # TERMINAL
    })
