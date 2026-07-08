"""The router (spec sections 2-3; brief step 3).

One asyncio event loop. Receive instruction -> resolve IDs -> fire whole
tree -> return output to the demander. No locks, no queues, no overlap
checking, no coordination machinery: firings never await, so each fires
whole and indivisible, which is also what makes the emit-disk terminal
(bound to this single router) atomic over shared world-state.

Persistence is not implemented here because it is not implemented anywhere
(brief step 5): unsent instructions are files under the world root, a
reference is a path, and demanding one -- the DEMAND grammar node below --
is reading the file and firing it. No store, no index, no read-file
structure in the library.
"""

import argparse
import asyncio
import os
import sys

from .instruction import Incomplete, Refusal, err, fire, lit, shape, skip
from .structures import make_registry, resolve_ref


class Stats:
    """Instrumentation only -- outside the model (brief: Measurements).

    One line per instruction fired (from the wire or from a demanded
    file): source, composition signature, size. One line per completed
    top-level firing: grammar nodes evaluated and the outcome.
    """

    def __init__(self, path):
        self._f = open(path, "a") if path else None

    def instruction(self, source, buf):
        if self._f:
            sig, _ = shape(buf, 0)
            self._f.write("I\t%s\t%s\t%d\n" % (source, sig, len(buf)))
            self._f.flush()

    def firing(self, nodes, outcome):
        if self._f:
            self._f.write("F\t%d\t%s\n" % (nodes, outcome))
            self._f.flush()


class Ctx:
    """Per-firing context: the resident registry plus the demand node's
    world access. Holds no state that survives the firing."""

    def __init__(self, structures, world_root, stats):
        self.structures = structures
        self.world_root = world_root
        self.stats = stats
        self.nodes_fired = 0
        self._active = []  # references currently firing, to refuse cycles

    def demand(self, ref):
        # The DEMAND grammar node: fire the unsent instruction named by a
        # held, literal reference. Reading the file IS the demand -- it is
        # not a terminal and not a library structure (brief step 4).
        if ref in self._active:
            raise Refusal(b"cyclic demand: " + ref)
        path = resolve_ref(self.world_root, ref)
        if not os.path.isfile(path):
            raise Refusal(b"no such reference: " + ref)
        with open(path, "rb") as f:
            stored = f.read()
        self.stats.instruction("ref:" + ref.decode(), stored)
        self._active.append(ref)
        try:
            try:
                value, end = fire(stored, 0, self)
            except Incomplete:
                raise Refusal(b"truncated stored instruction: " + ref)
            if end != len(stored):
                raise Refusal(b"trailing bytes in stored instruction: " + ref)
            return value
        finally:
            self._active.pop()


async def handle(reader, writer, structures, world_root, stats):
    buf = b""
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                return
            buf += data
            while True:
                try:
                    end = skip(buf, 0)
                except Incomplete:
                    break  # instruction still arriving
                except Refusal as r:
                    writer.write(err(r.payload))
                    await writer.drain()
                    return  # stream is not instructions; drop it
                instr, buf = buf[:end], buf[end:]
                stats.instruction("wire", instr)
                ctx = Ctx(structures, world_root, stats)
                try:
                    value, _ = fire(instr, 0, ctx)
                    response = lit(value)
                    stats.firing(ctx.nodes_fired, "value")
                except Refusal as r:
                    response = err(r.payload)
                    stats.firing(ctx.nodes_fired, "error")
                # The output returns to the demander -- the demand is the
                # return path, and the output is itself an instruction.
                writer.write(response)
                await writer.drain()
    finally:
        writer.close()


async def serve(host, port, world_root, stats_path):
    structures = make_registry(world_root)
    stats = Stats(stats_path)
    server = await asyncio.start_server(
        lambda r, w: handle(r, w, structures, world_root, stats), host, port)
    print("router listening on %s:%d, world=%s" % (host, port, world_root),
          file=sys.stderr, flush=True)
    async with server:
        await server.serve_forever()


def main():
    ap = argparse.ArgumentParser(description="Activation-model router")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7799)
    ap.add_argument("--world", default="world")
    ap.add_argument("--stats", default="stats.log")
    args = ap.parse_args()
    os.makedirs(args.world, exist_ok=True)
    # A thread is a chain of nested demands; depth grows with its length.
    sys.setrecursionlimit(50000)
    try:
        asyncio.run(serve(args.host, args.port, args.world, args.stats))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
