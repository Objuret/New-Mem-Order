"""The instruction grammar (spec section 2; brief step 1).

An instruction is a self-delimiting byte string: simultaneously the wire
format, the stored format, and the executable form. There is no other
representation of anything: firing walks the bytes directly, and no
decode-to-tree step exists in this file or anywhere in the codebase.

Grammar nodes -- exactly these four, part of the model core, not the
library (spec section 2). Adding one is a spec amendment.

    LIT     0x01  varint(len)  payload                literal value
    COMP    0x02  varint(sid)  varint(argc)  children structure composition
    DEMAND  0x03  varint(len)  reference              demand (literal ref only)
    ERR     0x04  varint(len)  payload                error

Varints are unsigned LEB128.
"""

LIT = 0x01
COMP = 0x02
DEMAND = 0x03
ERR = 0x04


class Incomplete(Exception):
    """More bytes are needed before one whole node is present.

    Framing only: raised while a stream is still arriving. Never a
    verdict on stored or complete bytes.
    """


class Refusal(Exception):
    """A firing refused (spec section 2, Error).

    Aborts the whole indivisible firing and propagates to the demander.
    Distinguishable from a value by construction -- it is an exception in
    flight and an ERR node on the wire, never a content convention.
    """

    def __init__(self, payload):
        if isinstance(payload, str):
            payload = payload.encode()
        super().__init__(payload)
        self.payload = payload


# --- varints ---------------------------------------------------------------

def _uv(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _rv(buf, off):
    n = 0
    shift = 0
    while True:
        if off >= len(buf):
            raise Incomplete()
        b = buf[off]
        off += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, off
        shift += 7


# --- construction: the one encoder (brief step 1) --------------------------

def lit(payload):
    if isinstance(payload, str):
        payload = payload.encode()
    return bytes([LIT]) + _uv(len(payload)) + payload


def comp(sid, *children):
    return bytes([COMP]) + _uv(sid) + _uv(len(children)) + b"".join(children)


def demand(ref):
    # The reference is literal by construction -- there is no way to build
    # a demand node around a value computed inside a firing (spec section 2).
    if isinstance(ref, str):
        ref = ref.encode()
    return bytes([DEMAND]) + _uv(len(ref)) + ref


def err(payload):
    if isinstance(payload, str):
        payload = payload.encode()
    return bytes([ERR]) + _uv(len(payload)) + payload


# --- framing ----------------------------------------------------------------

def skip(buf, off=0):
    """Return the end offset of the single node starting at off.

    This is the self-delimiting property exercised: it walks the same
    bytes fire() walks and builds nothing. Used to frame instructions
    arriving on a stream. Raises Incomplete if the node is still arriving,
    Refusal if the bytes are not an instruction at all.
    """
    if off >= len(buf):
        raise Incomplete()
    tag = buf[off]
    off += 1
    if tag in (LIT, DEMAND, ERR):
        n, off = _rv(buf, off)
        if off + n > len(buf):
            raise Incomplete()
        return off + n
    if tag == COMP:
        _, off = _rv(buf, off)
        argc, off = _rv(buf, off)
        for _ in range(argc):
            off = skip(buf, off)
        return off
    raise Refusal(b"not an instruction (tag %d)" % tag)


# --- firing (spec section 3) -------------------------------------------------

def fire(buf, off, ctx):
    """Fire the node at off, whole. Returns (value, end_offset).

    ctx supplies the resident structure registry (ctx.structures) and the
    demand grammar node's world access (ctx.demand). Raises Refusal on any
    refusal at any depth -- the whole firing aborts.
    """
    if off >= len(buf):
        raise Refusal(b"truncated instruction")
    tag = buf[off]
    off += 1
    ctx.nodes_fired += 1
    if tag == LIT:
        n, off = _rv(buf, off)
        if off + n > len(buf):
            raise Refusal(b"truncated literal")
        return bytes(buf[off:off + n]), off + n
    if tag == COMP:
        sid, off = _rv(buf, off)
        argc, off = _rv(buf, off)
        values = []
        for _ in range(argc):
            v, off = fire(buf, off, ctx)
            values.append(v)
        fn = ctx.structures.get(sid)
        if fn is None:
            raise Refusal(b"unknown structure id %d" % sid)
        return fn(values), off
    if tag == DEMAND:
        n, off = _rv(buf, off)
        if off + n > len(buf):
            raise Refusal(b"truncated reference")
        return ctx.demand(bytes(buf[off:off + n])), off + n
    if tag == ERR:
        n, off = _rv(buf, off)
        raise Refusal(bytes(buf[off:off + n]))
    raise Refusal(b"not an instruction (tag %d)" % tag)


# --- the return path (spec section 2, Output) --------------------------------

def outcome(buf):
    """Receive an output at the demander.

    The router returns a LIT node (value) or an ERR node (refusal) -- an
    output is itself an instruction. This unwraps the return, the same as
    a function return today. Returns ("value", payload) or ("error", payload).
    """
    if buf and buf[0] == LIT:
        n, off = _rv(buf, 1)
        return "value", bytes(buf[off:off + n])
    if buf and buf[0] == ERR:
        n, off = _rv(buf, 1)
        return "error", bytes(buf[off:off + n])
    return "error", b"unexpected output node"


# --- instrumentation only (spec section 6 measurement) ------------------------

def shape(buf, off=0):
    """The composition shape of a node, literal contents and references
    abstracted away. Measurement instrumentation, not part of the model:
    used to count distinct structure-compositions vs. total fired work.
    Returns (signature, end_offset).
    """
    tag = buf[off]
    off += 1
    if tag == LIT:
        n, off = _rv(buf, off)
        return "L", off + n
    if tag == DEMAND:
        n, off = _rv(buf, off)
        return "D", off + n
    if tag == ERR:
        n, off = _rv(buf, off)
        return "E", off + n
    if tag == COMP:
        sid, off = _rv(buf, off)
        argc, off = _rv(buf, off)
        parts = []
        for _ in range(argc):
            s, off = shape(buf, off)
            parts.append(s)
        return "C%d(%s)" % (sid, ",".join(parts)), off
    raise Refusal(b"not an instruction (tag %d)" % tag)
