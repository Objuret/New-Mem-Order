# Instruction format — the ONE representation (spec §2, brief step 1).
#
# An instruction is a nested composition tree, encoded as bytes:
#
#   node   := value | fire | demand | error
#   value  := 0x00 uvarint(len) bytes
#   fire   := 0x01 uvarint(structure_id) uvarint(argc) node*
#   demand := 0x02 uvarint(len) reference-bytes
#   error  := 0x03 uvarint(len) message-bytes
#   uvarint := LEB128, unsigned, little-groups-first
#
# demand is core machinery, not a library structure (spec §3 step 1, A4):
# firing it reads the unsent instruction at the reference and fires it —
# demanding = reading = firing. The reference is a literal name, never
# computed: the demander HOLDS it (A4).
#
# error is the reserved form for a firing the world refused (see
# spec-amendments.md #2): a firing returns a value or an error,
# distinguishable by construction, never by content convention.
#
# This encoding is simultaneously the file format, the wire format, and the
# executable form. It is self-delimiting, so the wire needs no framing layer
# and files need no headers: a reader consumes exactly one node and stops.
#
# There is deliberately NO decode-to-object-tree function in this project.
# Execution walks the bytes directly (structures.fire); this module only
# offers the encoder plus grammar walkers that never build a second
# representation (node_end finds a node boundary, shape summarizes a tree
# for the measurement harness, value_of extracts a literal's payload).

VALUE = 0x00
FIRE = 0x01
DEMAND = 0x02
ERROR = 0x03

# Tags whose body is uvarint(len) + bytes, like VALUE's.
_LEN_PREFIXED = (VALUE, DEMAND, ERROR)


def uvarint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def read_uvarint(buf, pos):
    """Decode a uvarint at pos. Returns (value, new_pos) or None if the
    buffer ends mid-number (incomplete stream)."""
    n = 0
    shift = 0
    while True:
        if pos >= len(buf):
            return None
        b = buf[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, pos
        shift += 7


def V(payload):
    """Encode a literal value node."""
    return bytes([VALUE]) + uvarint(len(payload)) + payload


def F(structure_id, *arg_nodes):
    """Encode a fire node: structure_id applied to already-encoded child nodes."""
    return (
        bytes([FIRE])
        + uvarint(structure_id)
        + uvarint(len(arg_nodes))
        + b"".join(arg_nodes)
    )


def D(ref):
    """Encode a demand node: fire the unsent instruction at this reference."""
    return bytes([DEMAND]) + uvarint(len(ref)) + ref


def E(message):
    """Encode an error node: the reserved form for a refused firing."""
    return bytes([ERROR]) + uvarint(len(message)) + message


class BadTag(Exception):
    """A byte pattern that selects no grammar rule. Per spec §4 malformed
    input is unexpressible rather than rejected; at the software edge that
    means the stream carrying it simply ends here."""


def node_end(buf, pos=0):
    """Return the end offset of the node starting at pos, or None if the
    buffer does not yet contain the whole node. Raises BadTag on a byte
    that is neither VALUE nor FIRE."""
    if pos >= len(buf):
        return None
    tag = buf[pos]
    pos += 1
    if tag in _LEN_PREFIXED:
        r = read_uvarint(buf, pos)
        if r is None:
            return None
        length, pos = r
        end = pos + length
        return end if end <= len(buf) else None
    if tag == FIRE:
        r = read_uvarint(buf, pos)
        if r is None:
            return None
        _sid, pos = r
        r = read_uvarint(buf, pos)
        if r is None:
            return None
        argc, pos = r
        for _ in range(argc):
            end = node_end(buf, pos)
            if end is None:
                return None
            pos = end
        return pos
    raise BadTag(f"0x{tag:02x}")


def value_of(node):
    """Payload of a literal value node (used by demanders to unwrap outputs).
    Raises BadTag on any other node kind — an error node must be looked at
    with payload_of, never mistaken for content."""
    if node[0] != VALUE:
        raise BadTag("expected value node")
    length, pos = read_uvarint(node, 1)
    return node[pos : pos + length]


def payload_of(node):
    """(tag, payload) of a length-prefixed node (value, demand, or error)."""
    tag = node[0]
    if tag not in _LEN_PREFIXED:
        raise BadTag("node has no payload")
    length, pos = read_uvarint(node, 1)
    return tag, node[pos : pos + length]


def shape(buf, pos=0):
    """Composition shape of a node: structure IDs with values elided
    (values '·', demands 'D', errors 'E'). Measurement instrumentation only
    (brief: repetition metric) — not part of the model.
    Returns (shape_string, end_pos)."""
    tag = buf[pos]
    pos += 1
    if tag in _LEN_PREFIXED:
        length, pos = read_uvarint(buf, pos)
        return {VALUE: "·", DEMAND: "D", ERROR: "E"}[tag], pos + length
    sid, pos = read_uvarint(buf, pos)
    argc, pos = read_uvarint(buf, pos)
    parts = []
    for _ in range(argc):
        s, pos = shape(buf, pos)
        parts.append(s)
    return f"{sid}({','.join(parts)})", pos
