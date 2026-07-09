"""Phase 12 — the tool (am.tool): the model doing a real job, end to end.

A user-shaped workflow, exercised exactly as a user would run it:

  snap a real source tree three times with edits between; restore every
  version byte-identical; verify against the originals; browse via ls
  and cat and a FUSE mount; replicate to a second store over the wire
  and restore from the replica; push a delta after a fourth snapshot.

Everything under the hood is chartered machinery composed by a
world-side CLI: layer puts for ingest, condensation + compaction after
every snapshot, phase-5 sync for replication. Zero new structures, zero
grammar changes, zero rule changes.

Run from repo root: python3 phase12.py
"""

import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "phase12")
STORE = os.path.join(WORK, "amstore")
REPLICA = os.path.join(WORK, "replica")
SRC = "/usr/lib/python3.11"
PORT = 7871
rng = random.Random(12)


def tool(*args, store=STORE, expect=0):
    r = subprocess.run([sys.executable, "-m", "am.tool", "--store", store,
                        *args], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != expect:
        raise AssertionError("am.tool %s -> %d\n%s\n%s"
                             % (" ".join(args), r.returncode, r.stdout, r.stderr))
    return r.stdout


def build_tree(dst, tree):
    shutil.rmtree(dst, ignore_errors=True)
    for rel, data in tree.items():
        path = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def tree_sha(base):
    import hashlib
    h = hashlib.sha256()
    for dirpath, dirs, names in sorted(os.walk(base)):
        dirs.sort()
        for name in sorted(names):
            p = os.path.join(dirpath, name)
            h.update(os.path.relpath(p, base).encode())
            with open(p, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)

    # a real corpus evolving over four generations
    tree = {}
    for dirpath, dirs, names in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in
                   ("__pycache__", "test", "site-packages", "dist-packages")]
        for name in sorted(names):
            if name.endswith(".py") and len(tree) < 80:
                with open(os.path.join(dirpath, name), "rb") as f:
                    tree["src/" + name] = f.read()
    gens = []
    for g in range(4):
        gens.append(dict(tree))
        for rel in rng.sample(sorted(tree), 6):
            lines = tree[rel].split(b"\n")
            lines.insert(rng.randrange(len(lines)),
                         b"# edited before generation %d" % (g + 1))
            tree[rel] = b"\n".join(lines)
        tree["src/new_%d.py" % g] = b"# new in generation %d\n" % g + \
            tree[rng.choice(sorted(tree))]

    srcdirs = []
    for g, snapshot_tree in enumerate(gens[:3]):
        src = os.path.join(WORK, "src-g%d" % (g + 1))
        build_tree(src, snapshot_tree)
        srcdirs.append(src)
        out = tool("snap", src, "--label", "g%d" % (g + 1))
        print("  " + out.strip())

    # list, browse, verify, restore each generation byte-identical
    labels = tool("snaps").split()
    assert [l for l in labels if l.startswith("g")] == ["g1", "g2", "g3"], labels
    assert "new_0.py" in tool("ls", "g2", "src")
    cat = tool("cat", "g1/src/" + sorted(gens[0])[0].split("/")[1])
    assert cat.encode() == gens[0][sorted(gens[0])[0]].decode(errors="replace").encode()
    for g in range(3):
        outdir = os.path.join(WORK, "restore-g%d" % (g + 1))
        tool("restore", "g%d" % (g + 1), outdir)
        assert tree_sha(outdir) == tree_sha(srcdirs[g]), "restore differs g%d" % (g + 1)
        assert "0 mismatches" in tool("verify", "g%d" % (g + 1), srcdirs[g])
    print("restore + verify: PASS (3 generations byte-identical)")
    print(tool("stats").strip().replace("\n", "; "))

    # replicate to a second store over the wire, restore from the replica
    os.makedirs(REPLICA)
    server = subprocess.Popen(
        [sys.executable, "-m", "am.tool", "--store", REPLICA,
         "serve", "--port", str(PORT)], cwd=ROOT, stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT), 0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    try:
        full = tool("push", "127.0.0.1:%d" % PORT)
        print("  " + full.strip())
        rdir = os.path.join(WORK, "restore-replica-g2")
        tool("restore", "g2", rdir, store=REPLICA)
        assert tree_sha(rdir) == tree_sha(srcdirs[1]), "replica restore differs"
        print("replication: PASS (g2 restored from the replica, byte-identical)")

        # fourth snapshot, delta push
        src4 = os.path.join(WORK, "src-g4")
        build_tree(src4, gens[3])
        tool("snap", src4, "--label", "g4")
        delta = tool("push", "127.0.0.1:%d" % PORT)
        print("  " + delta.strip())
        assert "delta" in delta
        rdir4 = os.path.join(WORK, "restore-replica-g4")
        tool("restore", "g4", rdir4, store=REPLICA)
        assert tree_sha(rdir4) == tree_sha(src4), "replica g4 differs"
        print("delta push: PASS (g4 on the replica, byte-identical)")
    finally:
        server.send_signal(signal.SIGTERM)
        server.wait()

    # browse the store through a FUSE mount, like a filesystem of history
    mnt = os.path.join(WORK, "mnt")
    os.makedirs(mnt)
    m = subprocess.Popen([sys.executable, "-m", "am.tool", "--store", STORE,
                          "mount", mnt], cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if os.path.ismount(mnt):
            break
        time.sleep(0.05)
    try:
        name = sorted(gens[0])[0].split("/")[1]
        with open(os.path.join(mnt, "g1", "src", name), "rb") as f:
            assert f.read() == gens[0]["src/" + name]
        assert sorted(os.listdir(mnt)) == ["g1", "g2", "g3", "g4"]
    finally:
        subprocess.run(["fusermount", "-u", mnt], check=True)
        m.wait()
    print("mount: PASS (all four snapshots browsable as directories)")
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
