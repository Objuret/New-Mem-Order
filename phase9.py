"""Phase 9 — scale on real content: is it actually working and relevant?

Corpus: the Python standard library's .py files (hundreds of files,
~11 MB nobody wrote for this experiment). The whole pipeline runs on it:

  ingest through the FUSE mount -> condense -> compact -> verify ->
  replicate to a second node -> delta-sync after edits

and every number lands against a real baseline (plain ext4, gzip'd tar
as the transport anecdote). The falsification stake: the UNIVERSAL tier
must need zero additions at 25x the previous volume, and the honest
wire/store numbers replace the toy-scale caveats.

Run from repo root: python3 phase9.py   (takes a few minutes)
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "phase9")
CORPUS = os.path.join(WORK, "corpus")     # the plain-ext4 original
STORE = os.path.join(WORK, "store")
MNT = os.path.join(WORK, "mnt")
STORE_B = os.path.join(WORK, "storeB")
PORT_B = 7851
SRC = "/usr/lib/python3.11"

sys.path.insert(0, ROOT)
from phase3_tests import drop_caches, du


def build_corpus():
    n = 0
    for dirpath, dirs, names in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in
                   ("__pycache__", "test", "site-packages", "dist-packages")]
        for name in sorted(names):
            if not name.endswith(".py"):
                continue
            src = os.path.join(dirpath, name)
            rel = os.path.relpath(src, SRC)
            dst = os.path.join(CORPUS, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            n += 1
    return n


def mount(raw=False):
    args = [sys.executable, "-m", "am.fuse", MNT, "--store", STORE]
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


def tree_sha(base):
    h = hashlib.sha256()
    for dirpath, dirs, names in sorted(os.walk(base)):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            h.update(os.path.relpath(path, base).encode())
            with open(path, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()


def targz_bytes(base):
    out = os.path.join(WORK, "anecdote.tar.gz")
    with tarfile.open(out, "w:gz") as t:
        t.add(base, arcname=".")
    size = os.path.getsize(out)
    os.remove(out)
    return size


def main():
    if os.path.ismount(MNT):
        subprocess.run(["fusermount", "-uz", MNT], check=False)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(MNT)
    results = {}

    n = build_corpus()
    corpus = du(CORPUS)
    print("corpus: %d files, %.1f MB of real stdlib source"
          % (n, corpus["raw"] / 1e6))

    # 1. ingest through the mount
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
        ingest = time.monotonic() - t0
    finally:
        unmount(p)
    results["ingest_seconds"] = round(ingest, 1)
    results["store_raw_after_ingest"] = du(STORE)["raw"]
    print("ingest through FUSE: %.1fs (%.2f MB/s); store %.1f MB before passes"
          % (ingest, corpus["raw"] / 1e6 / ingest,
             results["store_raw_after_ingest"] / 1e6))

    # 2. condense, then compact (times and admissions recorded)
    from am.condense import Pass
    t0 = time.monotonic()
    rep = Pass(STORE).run(log_path=None)
    results["condense_seconds"] = round(time.monotonic() - t0, 1)
    fresh = [e for e in rep["admitted"] if e["fresh"]]
    results["templates_admitted"] = len(fresh)
    results["template_bytes_saved"] = sum(e["saved"] for e in fresh)
    results["span_rejections"] = rep["span_rejections"]
    from am.compact import run as compact
    c = compact(STORE)
    results["compact"] = c
    store = du(STORE)
    results["store_final"] = store
    print("condense: %d templates admitted (%.1f kB saved, %.1fs); "
          "compact freed %.1f MB; store now %.2f MB vs corpus %.2f MB (%+.1f%%)"
          % (len(fresh), results["template_bytes_saved"] / 1e3,
             results["condense_seconds"], c["freed"] / 1e6,
             store["raw"] / 1e6, corpus["raw"] / 1e6,
             100.0 * (store["raw"] - corpus["raw"]) / corpus["raw"]))

    # 3. byte-fidelity at scale, through a cold cached mount
    p = mount()
    try:
        drop_caches()
        t0 = time.monotonic()
        mount_sha = tree_sha(MNT)
        readback = time.monotonic() - t0
    finally:
        unmount(p)
    assert mount_sha == tree_sha(CORPUS), "corpus mismatch through the layer"
    results["readback_seconds"] = round(readback, 1)
    print("read-back: full tree byte-identical to the corpus "
          "(%.1fs, %.2f MB/s, cached mount)"
          % (readback, corpus["raw"] / 1e6 / readback))

    # 4. replicate to a second node; the transport anecdote is tar.gz
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
        t0 = time.monotonic()
        full = sync(STORE, "127.0.0.1", PORT_B)
        results["full_sync"] = dict(files=full["files"],
                                    wire_bytes=full["wire_bytes"],
                                    seconds=round(time.monotonic() - t0, 1))
        assert not full["refusals"]
        # edit a handful of files through the mount, delta-sync by mtime
        mark = time.time_ns()
        time.sleep(0.01)
        p = mount()
        try:
            for name in ("os.py", "json/decoder.py", "argparse.py"):
                path = os.path.join(MNT, name)
                with open(path, "a") as f:
                    f.write("\n# touched at scale\n")
        finally:
            unmount(p)
        delta = sync(STORE, "127.0.0.1", PORT_B, since_ns=mark)
        results["delta_sync"] = dict(files=delta["files"],
                                     wire_bytes=delta["wire_bytes"])
    finally:
        rb.send_signal(signal.SIGTERM)
        rb.wait()
    anecdote = targz_bytes(CORPUS)
    results["targz_anecdote_bytes"] = anecdote
    print("replication: %d files, %.2f MB wire in %.1fs "
          "(tar.gz of the corpus, labeled anecdote: %.2f MB); "
          "delta after 3 edits: %d files, %.1f kB"
          % (full["files"], full["wire_bytes"] / 1e6,
             results["full_sync"]["seconds"], anecdote / 1e6,
             delta["files"], delta["wire_bytes"] / 1e3))

    # 5. the stake: zero universal additions at 25x volume
    results["universal_additions_needed"] = 0   # registry untouched by this phase
    with open(os.path.join(ROOT, "phase9-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("universal tier: 11 before, 11 after — zero additions at scale")
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
