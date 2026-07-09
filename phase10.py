"""Phase 10 — the recurrence-shaped corpus: snapshots, where dedup lives.

Phase 9 recorded honestly that gzip beats the model 4x on unique
content. This phase runs the rematch on the corpus shape the model's
compression story is actually about: VERSION HISTORY. Eight snapshot
generations of an evolving source tree (the backup workload), stored
whole, side by side — the thing people keep 10x copies of.

The mechanics are the point: gzip's 32 KiB window cannot dedup a file
against its identical twin one generation (megabytes) away in the
stream. Condensation dedups across the entire store by construction —
a block recurring in >= 3 snapshot copies becomes one resident template
and every occurrence a reference. Prediction: the condensed+compacted
store lands near the unique-content floor while tar.gz stays near
"entropy-coded but duplicated".

Run from repo root: python3 phase10.py   (a few minutes)
"""

import hashlib
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import tarfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "phase10")
CORPUS = os.path.join(WORK, "corpus")
STORE = os.path.join(WORK, "store")
MNT = os.path.join(WORK, "mnt")
STORE_B = os.path.join(WORK, "storeB")
PORT_B = 7861
SRC = "/usr/lib/python3.11"
GENERATIONS = 8

sys.path.insert(0, ROOT)
from phase3_tests import drop_caches, du
from phase9 import mount as _mount, tree_sha, targz_bytes

rng = random.Random(7)


def mount():
    args = [sys.executable, "-m", "am.fuse", MNT, "--store", STORE]
    p = subprocess.Popen(args, cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(200):
        if os.path.ismount(MNT):
            return p
        time.sleep(0.05)
    raise RuntimeError("mount never appeared")


def unmount(p):
    subprocess.run(["fusermount", "-u", MNT], check=True)
    p.wait()


def build_generations():
    """gen0: ~150 real stdlib files. Each next generation: ~8 files get
    a line inserted, 2 files are added, 1 is deleted. Deterministic."""
    picked = []
    for dirpath, dirs, names in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in
                   ("__pycache__", "test", "site-packages", "dist-packages")]
        for name in sorted(names):
            if name.endswith(".py"):
                size = os.path.getsize(os.path.join(dirpath, name))
                if 1024 <= size <= 100 * 1024:
                    picked.append(os.path.join(dirpath, name))
    picked = picked[:150]
    tree = {}
    for path in picked:
        with open(path, "rb") as f:
            tree["src/" + os.path.basename(path)] = f.read()
    for gen in range(GENERATIONS):
        base = os.path.join(CORPUS, "gen%d" % gen)
        for rel, data in tree.items():
            dst = os.path.join(base, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
        # evolve for the next generation
        names = sorted(tree)
        for rel in rng.sample(names, 8):
            lines = tree[rel].split(b"\n")
            at = rng.randrange(len(lines))
            lines.insert(at, b"# generation %d touched this line" % gen)
            tree[rel] = b"\n".join(lines)
        for i in range(2):
            tree["src/new_g%d_%d.py" % (gen, i)] = (
                ("# born in generation %d\n" % gen).encode()
                + tree[rng.choice(names)])
        del tree[rng.choice(sorted(tree))]
    return sum(1 for _ in os.walk(CORPUS))


def unique_content_bytes():
    seen = {}
    for dirpath, _, names in os.walk(CORPUS):
        for n in names:
            with open(os.path.join(dirpath, n), "rb") as f:
                data = f.read()
            seen[hashlib.sha256(data).digest()] = len(data)
    return sum(seen.values())


def main():
    if os.path.ismount(MNT):
        subprocess.run(["fusermount", "-uz", MNT], check=False)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(MNT)
    results = {}

    build_generations()
    corpus = du(CORPUS)
    unique = unique_content_bytes()
    results["corpus"] = corpus
    results["unique_content_bytes"] = unique
    print("corpus: %d snapshot generations, %d files, %.1f MB logical "
          "(unique content: %.1f MB — the perfect-dedup floor)"
          % (GENERATIONS, corpus["files"], corpus["raw"] / 1e6, unique / 1e6))

    p = mount()
    t0 = time.monotonic()
    try:
        for dirpath, dirs, names in os.walk(CORPUS):
            rel = os.path.relpath(dirpath, CORPUS)
            base = MNT if rel == "." else os.path.join(MNT, rel)
            for d in sorted(dirs):
                os.makedirs(os.path.join(base, d), exist_ok=True)
            for name in sorted(names):
                shutil.copyfile(os.path.join(dirpath, name),
                                os.path.join(base, name))
    finally:
        unmount(p)
    print("ingest: %.1fs; store %.1f MB before passes"
          % (time.monotonic() - t0, du(STORE)["raw"] / 1e6))

    from am.condense import Pass
    t0 = time.monotonic()
    rep = Pass(STORE).run(log_path=None)
    condense_s = time.monotonic() - t0
    fresh = [e for e in rep["admitted"] if e["fresh"]]
    from am.compact import run as compact
    c = compact(STORE)
    store = du(STORE)
    results["templates"] = len(fresh)
    results["template_bytes_saved"] = sum(e["saved"] for e in fresh)
    results["store_final"] = store
    print("condense: %d templates, %.1f MB saved (%.1fs); compact freed "
          "%.1f MB" % (len(fresh), results["template_bytes_saved"] / 1e6,
                       condense_s, c["freed"] / 1e6))

    p = mount()
    try:
        drop_caches()
        assert tree_sha(MNT) == tree_sha(CORPUS), "fidelity broken"
    finally:
        unmount(p)

    anecdote = targz_bytes(CORPUS)
    results["targz_anecdote_bytes"] = anecdote

    os.makedirs(STORE_B)
    rb = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", STORE_B,
         "--port", str(PORT_B), "--stats", os.devnull],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT_B), 0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    try:
        from am.sync import sync
        full = sync(STORE, "127.0.0.1", PORT_B)
        assert not full["refusals"]
        results["full_sync_wire_bytes"] = full["wire_bytes"]
    finally:
        rb.send_signal(signal.SIGTERM)
        rb.wait()

    logical = corpus["raw"]
    print()
    print("== the rematch (%.1f MB logical, %d generations) ==" % (logical / 1e6, GENERATIONS))
    print("  plain ext4:                 %8.2f MB   (1.00x)" % (logical / 1e6))
    print("  tar.gz (labeled anecdote):  %8.2f MB   (%.2fx)"
          % (anecdote / 1e6, anecdote / logical))
    print("  store, condensed+compacted: %8.2f MB   (%.2fx)"
          % (store["raw"] / 1e6, store["raw"] / logical))
    print("  wire, full replication:     %8.2f MB   (%.2fx)"
          % (full["wire_bytes"] / 1e6, full["wire_bytes"] / logical))
    print("  unique-content floor:       %8.2f MB   (%.2fx)"
          % (unique / 1e6, unique / logical))
    with open(os.path.join(ROOT, "phase10-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
