"""Offline compaction (phase 6): delete what nothing references.

Superseded chains accumulate because every write is append+swap and
nothing is ever overwritten (phase-3 measurement: 24.5x the logical
tree). Reclaiming them needs no GC machinery, no refcounts, no roots
beyond what already exists: the heads ARE the roots, reachability IS
the demand graph, and deletion is the world act the spec already
sanctions ("deleting an unsent instruction = deleting a file, same as
now", spec section 4).

The pass walks every head to its chain and every demand inside it
(offline structural walk, the chartered exception), then removes any
file under chains/ that nothing reached. Renders are checksum-verified
before and after. Run with the mount stopped -- one owner of the
store's terminals at a time, as always.
"""

import argparse
import hashlib
import os
import sys

from .condense import _heads
from .instruction import COMP, DEMAND, ERR, LIT, _rv
from .layer import Layer


def _refs_in(root, ref, seen):
    if ref in seen:
        return
    seen.add(ref)
    with open(os.path.join(root, ref), "rb") as f:
        buf = f.read()

    def walk(off):
        tag = buf[off]
        off += 1
        if tag in (LIT, ERR):
            n, off = _rv(buf, off)
            return off + n
        if tag == DEMAND:
            n, off = _rv(buf, off)
            _refs_in(root, bytes(buf[off:off + n]).decode(), seen)
            return off + n
        if tag == COMP:
            _, off = _rv(buf, off)
            argc, off = _rv(buf, off)
            for _ in range(argc):
                off = walk(off)
            return off
        raise ValueError("bad tag %d" % tag)

    end = walk(0)
    assert end == len(buf), ref


def run(store_root):
    layer = Layer(store_root, cache=False)
    root = layer.root
    reachable = set()
    checks = {}
    for rel in _heads(root):
        _, chain, _, _, _ = layer._head("/" + rel)
        _refs_in(root, chain, reachable)
        checks[rel] = hashlib.sha256(layer._render(chain)).digest()

    removed = freed = 0
    chains_dir = os.path.join(root, "chains")
    for dirpath, _, names in os.walk(chains_dir):
        for name in names:
            path = os.path.join(dirpath, name)
            ref = os.path.relpath(path, root)
            if ref not in reachable:
                freed += os.lstat(path).st_size
                os.remove(path)   # delete = delete a file, same as now
                removed += 1

    for rel, sha in checks.items():
        _, chain, _, _, _ = layer._head("/" + rel)
        if hashlib.sha256(layer._render(chain)).digest() != sha:
            raise RuntimeError("render changed after compaction: " + rel)
    return dict(files=len(checks), removed=removed, freed=freed)


def main():
    ap = argparse.ArgumentParser(description="Offline compaction pass")
    ap.add_argument("--store", default="store")
    args = ap.parse_args()
    r = run(args.store)
    print("compaction: %d unreachable chain files removed, %d bytes freed; "
          "%d live files render-verified" % (r["removed"], r["freed"], r["files"]))


if __name__ == "__main__":
    main()
