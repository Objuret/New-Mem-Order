"""Phase 6 — compaction and the render cache: pricing the two answers.

Phase 3 measured the raw model's two operational costs on purpose:
superseded history at 24.5x the logical tree, and whole-chain renders
at 32.3 firings per read syscall. This phase builds the two answers the
findings pointed at and measures before/after on the phase-3 store:

- am/compact.py deletes unreachable chains (world-side deletion by
  reachability from heads; render-verified).
- the layer's render cache (am/layer.py) memoizes chain renders --
  demander-side memory, sound because chains are write-once per mount
  and condensation is render-identity-verified across mounts. Heads are
  never cached. --raw reproduces the v1 numbers.

Precondition: phase3/store populated by phase3_tests.py.
Run from repo root: python3 phase6.py
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(ROOT, "phase3", "store")
MNT = os.path.join(ROOT, "phase3", "mnt")

sys.path.insert(0, ROOT)
from phase3_tests import drop_caches, du, git, tree_checksums


def mount(stats_out, raw):
    args = [sys.executable, "-m", "am.fuse", MNT, "--store", STORE,
            "--stats-out", stats_out]
    if raw:
        args.append("--raw")
    p = subprocess.Popen(args, cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(200):
        if os.path.ismount(MNT):
            return p
        time.sleep(0.05)
    raise RuntimeError("mount never appeared")


def unmount(p):
    subprocess.run(["fusermount", "-u", MNT], check=True)
    p.wait()


def read_everything():
    """Stat storm + full read of every file, twice (the second pass is
    where a cache can help; page cache is dropped between passes)."""
    t0 = time.monotonic()
    sums = {}
    for _ in range(2):
        drop_caches()
        sums = tree_checksums()
    return sums, time.monotonic() - t0


def bench(raw):
    stats = os.path.join(ROOT, "phase3", "stats-p6-%s.json" % ("raw" if raw else "cached"))
    p = mount(stats, raw)
    try:
        sums, elapsed = read_everything()
        git(os.path.join(MNT, "repo"), "fsck", "--strict")
    finally:
        unmount(p)
    s = json.load(open(stats))
    reads = s["opstats"].get("read", [0, 0])
    return dict(elapsed=round(elapsed, 2), read_calls=reads[0],
                read_firings=reads[1],
                firings_per_read=round(reads[1] / reads[0], 2) if reads[0] else 0,
                cache_hits=s.get("cache_hits", 0)), sums


def main():
    if not os.path.isdir(os.path.join(STORE, "fs")):
        print("phase3/store missing — run phase3_tests.py first", file=sys.stderr)
        return 1
    if os.path.ismount(MNT):
        subprocess.run(["fusermount", "-uz", MNT], check=False)
    results = {}

    # compaction: before/after sizes, render-verified inside the pass
    results["store_before"] = du(STORE)
    from am.compact import run as compact
    c = compact(STORE)
    results["compact"] = c
    results["store_after"] = du(STORE)
    print("compaction: %d files removed, %.1f MB freed (store %.1f MB -> %.1f MB), "
          "%d live files render-verified"
          % (c["removed"], c["freed"] / 1e6,
             results["store_before"]["raw"] / 1e6,
             results["store_after"]["raw"] / 1e6, c["files"]))

    # the same workload, raw vs cached
    raw_stats, raw_sums = bench(raw=True)
    cached_stats, cached_sums = bench(raw=False)
    assert raw_sums == cached_sums, "cache changed rendered content"
    results["raw"] = raw_stats
    results["cached"] = cached_stats
    print("raw:    %(read_calls)d reads, %(read_firings)d firings "
          "(%(firings_per_read).2f/read), %(elapsed).2fs" % raw_stats)
    print("cached: %(read_calls)d reads, %(read_firings)d firings "
          "(%(firings_per_read).2f/read), %(elapsed).2fs, %(cache_hits)d hits"
          % cached_stats)

    # writes still correct under the cache: overwrite, read back, cold-check
    p = mount(os.devnull, raw=False)
    try:
        path = os.path.join(MNT, "fidelity", "text-1")
        with open(path, "r+b") as f:
            f.write(b"cache sees fresh chains")
        drop_caches()
        with open(path, "rb") as f:
            got = f.read()
        assert got.startswith(b"cache sees fresh chains"), got
    finally:
        unmount(p)
    p = mount(os.devnull, raw=True)   # cold, uncached remount agrees
    try:
        with open(path, "rb") as f:
            assert f.read() == got
    finally:
        unmount(p)
    print("write-through under cache: PASS (fresh chain ref = natural miss; "
          "cold raw remount agrees)")

    with open(os.path.join(ROOT, "phase6-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
