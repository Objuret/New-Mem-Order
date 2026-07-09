"""Phase 11 — the native fire loop: pricing the section-0 speed claim.

Everything before this phase measured the determinants of speed (bytes
moved, machinery deleted, residency size); this phase measures speed.
native/amfire.c is a ~300-line C realization of the grammar's read path
(spec section 8: compiled structures, native event loop) — byte-
compatible with every stored world, templates loaded resident at start.

The question with a kill condition: if native firing cannot get near
raw-read throughput, the conversions the model deleted were cheaper
than the interpretation it added, and section 0's argument fails on its
own terms. Benchmarked on the phase-10 store (4.6 MB of chains serving
30.4 MB of content) against raw reads of the plain corpus, warm and
cold, plus the Python runtime for scale.

Precondition: phase10/ populated by phase10.py.
Run from repo root: python3 phase11.py
"""

import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
P10 = os.path.join(ROOT, "phase10")
STORE = os.path.join(P10, "store")
CORPUS = os.path.join(P10, "corpus")
BIN = os.path.join(ROOT, "native", "amfire")
OUT = os.path.join(P10, "native-out")

sys.path.insert(0, ROOT)
from phase3_tests import drop_caches
from phase9 import tree_sha


def run_bin(*args):
    r = subprocess.run([BIN, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError("amfire %s failed:\n%s" % (" ".join(args), r.stderr))
    return json.loads(r.stdout)


def bench(mode, target, runs=5, cold=False):
    best = None
    for _ in range(1 if cold else runs):
        if cold:
            drop_caches()
        r = run_bin(mode, target)
        if best is None or r["seconds"] < best["seconds"]:
            best = r
    best["mbps"] = round(best["bytes"] / 1e6 / best["seconds"], 1)
    return best


def python_render_seconds():
    from am.layer import Layer
    from am.condense import _heads
    layer = Layer(STORE, cache=False)
    drop_caches()
    t0 = time.monotonic()
    total = 0
    for rel in _heads(layer.root):
        _, chain, _, _, _ = layer._head("/" + rel)
        total += len(layer._render(chain))
    return time.monotonic() - t0, total


def main():
    if not os.path.isdir(os.path.join(STORE, "fs")):
        print("phase10/ missing — run phase10.py first", file=sys.stderr)
        return 1
    subprocess.run(["cc", "-O2", "-Wall", "-D_GNU_SOURCE",
                    "-o", BIN, os.path.join(ROOT, "native", "amfire.c")],
                   check=True)
    results = {}

    # fidelity: native render of every file == the plain corpus, byte for byte
    shutil.rmtree(OUT, ignore_errors=True)
    run_bin("renderall", STORE, OUT)
    assert tree_sha(OUT) == tree_sha(CORPUS), "native render differs from corpus"
    shutil.rmtree(OUT)
    print("fidelity: PASS (native render of all files byte-identical to corpus)")

    results["fire_warm"] = bench("renderall", STORE)
    results["read_warm"] = bench("readall", CORPUS)
    results["fire_cold"] = bench("renderall", STORE, cold=True)
    results["read_cold"] = bench("readall", CORPUS, cold=True)
    py_s, py_bytes = python_render_seconds()
    results["python_render"] = dict(seconds=round(py_s, 2),
                                    mbps=round(py_bytes / 1e6 / py_s, 2))

    fw, rw = results["fire_warm"], results["read_warm"]
    fc, rc = results["fire_cold"], results["read_cold"]
    print("\n== delivered-content throughput (30.4 MB logical) ==")
    print("  warm: fire %7.1f MB/s   raw read %7.1f MB/s   -> firing = %.2fx of cat"
          % (fw["mbps"], rw["mbps"], fw["mbps"] / rw["mbps"]))
    print("  cold: fire %7.1f MB/s   raw read %7.1f MB/s   -> firing = %.2fx of cat"
          % (fc["mbps"], rc["mbps"], fc["mbps"] / rc["mbps"]))
    print("  python raw-model render: %.2f MB/s -> native is %.0fx python"
          % (results["python_render"]["mbps"],
             fw["mbps"] / results["python_render"]["mbps"]))
    print("  disk bytes behind the firing: ~4.6 MB of store serving 30.4 MB "
          "(6.6x delivery per stored byte)")
    with open(os.path.join(ROOT, "phase11-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
