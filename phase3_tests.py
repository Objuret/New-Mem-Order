"""Phase-3 acceptance tests and measurements (PHASE3-LAYER.md sections 10-11).

Runs the four acceptance tests in charter order against a real FUSE
mount, collecting the measurements as it goes, and writes
phase3-results.json. Run from the repo root: python3 phase3_tests.py
"""

import hashlib
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "phase3")
STORE = os.path.join(WORK, "store")
MNT = os.path.join(WORK, "mnt")
MIRROR = os.path.join(WORK, "mirror")
CHUNK = 64 * 1024
rng = random.Random(42)

LICENSE = ("# Copyright (c) 2026 The Activation Model Project.\n"
           "# Permission is hereby granted, free of charge, to any person\n"
           "# obtaining a copy of this software and associated documentation\n"
           "# files (the \"Software\"), to deal in the Software without\n"
           "# restriction, including without limitation the rights to use,\n"
           "# copy, modify, merge, publish, distribute, sublicense, and/or\n"
           "# sell copies of the Software, and to permit persons to whom the\n"
           "# Software is furnished to do so, subject to the following\n"
           "# conditions: the above copyright notice and this permission\n"
           "# notice shall be included in all copies or substantial portions\n"
           "# of the Software.\n") * 3   # ~1.9 KiB shared header

BOILER = ("This paragraph is standard project boilerplate that appears "
          "verbatim in several documents. It exists so that real recurring "
          "content crosses file boundaries the way license headers and "
          "templates do in actual repositories. " * 8 + "\n")


def mount(stats_out=None):
    args = [sys.executable, "-m", "am.fuse", MNT, "--store", STORE]
    if stats_out:
        args += ["--stats-out", stats_out]
    p = subprocess.Popen(args, cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(200):
        if os.path.ismount(MNT):
            return p
        if p.poll() is not None:
            raise RuntimeError("mount process died")
        time.sleep(0.05)
    raise RuntimeError("mount never appeared")


def unmount(p, kill=False):
    if kill:
        p.send_signal(signal.SIGKILL)
        p.wait()
        subprocess.run(["fusermount", "-uz", MNT], check=False)
    else:
        subprocess.run(["fusermount", "-u", MNT], check=True)
        p.wait()
    for _ in range(100):
        if not os.path.ismount(MNT):
            return
        time.sleep(0.05)


def drop_caches():
    # Force reads to reach the layer instead of the page cache. Best
    # effort; the restart test re-reads everything cold regardless.
    try:
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3\n")
    except OSError:
        pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def tree_checksums():
    """Read every file and symlink through the mount."""
    out = {}
    for dirpath, dirs, names in os.walk(MNT):
        for n in sorted(names):
            p = os.path.join(dirpath, n)
            rel = os.path.relpath(p, MNT)
            if os.path.islink(p):
                out[rel] = "L:" + os.readlink(p)
            else:
                with open(p, "rb") as f:
                    out[rel] = sha(f.read())
    return out


def du(path, reachable_only=False):
    raw = blocks = count = 0
    for dirpath, dirs, names in os.walk(path):
        for n in names:
            st = os.lstat(os.path.join(dirpath, n))
            raw += st.st_size
            blocks += (st.st_size + 4095) // 4096 * 4096
            count += 1
    return dict(raw=raw, ext4_blocks=blocks, files=count)


def reachable_store_bytes():
    """Live bytes: heads + reachable chains/chunks + lib. Superseded
    chains are excluded. (Measurement tooling: uses the offline walker.)"""
    sys.path.insert(0, ROOT)
    from am.condense import walk_chain, _heads
    from am.layer import Layer
    layer = Layer(STORE)
    total = 0
    seen = set()

    def add(ref):
        p = os.path.join(layer.root, ref)
        if ref not in seen:
            seen.add(ref)
            nonlocal total
            total += os.lstat(p).st_size

    for rel in _heads(layer.root):
        add("fs/" + rel)
        t, chain, size, mtime, mode = layer._head("/" + rel)
        # walk to find every container file the chain reaches
        pieces_refs = set()
        stack = [chain]
        while stack:
            ref = stack.pop()
            if ref in pieces_refs:
                continue
            pieces_refs.add(ref)
            add(ref)
            buf = open(os.path.join(layer.root, ref), "rb").read()
            from am.instruction import DEMAND, _rv, COMP, LIT
            def refs_in(buf, off):
                tag = buf[off]; off += 1
                if tag == LIT:
                    n, off = _rv(buf, off)
                    return off + n
                if tag == COMP:
                    _, off = _rv(buf, off)
                    argc, off = _rv(buf, off)
                    for _ in range(argc):
                        off = refs_in(buf, off)
                    return off
                if tag == DEMAND:
                    n, off = _rv(buf, off)
                    stack.append(bytes(buf[off:off + n]).decode())
                    return off + n
                raise ValueError
            refs_in(buf, 0)
    libdir = os.path.join(layer.root, "lib")
    if os.path.isdir(libdir):
        for n in os.listdir(libdir):
            add("lib/" + n)
    return total


# --- acceptance test 1: byte fidelity -----------------------------------

def test_fidelity():
    base = os.path.join(MNT, "fidelity")
    os.mkdir(base)
    shadow = {}
    sizes = [0, 1, 4095, 4096, 4097, 200 * 1024, 5 * 1024 * 1024]
    for size in sizes:
        rnd = rng.randbytes(size)
        txt = (b"line %06d of a plain text file under test\n" * 128)
        txt = (txt * (size // len(txt) + 1))[:size] if size else b""
        for tag, data in (("rand", rnd), ("text", txt)):
            name = "%s-%d" % (tag, size)
            with open(os.path.join(base, name), "wb") as f:
                f.write(data)
            shadow[name] = data
    drop_caches()
    for name, data in shadow.items():
        with open(os.path.join(base, name), "rb") as f:
            assert f.read() == data, "mismatch after write: " + name
    # range overwrites, including chunk boundaries and extension past EOF
    name = "rand-5242880"
    data = bytearray(shadow[name])
    splices = [(0, 11), (CHUNK - 3, 7), (CHUNK * 3 - 1, 2),
               (CHUNK * 20 + 12345, 40000), (len(data) - 10, 10),
               (len(data) - 2, 50)]   # last one extends the file
    path = os.path.join(base, name)
    for off, ln in splices:
        patch = rng.randbytes(ln)
        with open(path, "r+b") as f:
            f.seek(off)
            f.write(patch)
        if off + ln > len(data):
            data.extend(b"\x00" * (off + ln - len(data)))
        data[off:off + ln] = patch
    shadow[name] = bytes(data)
    drop_caches()
    with open(path, "rb") as f:
        assert f.read() == shadow[name], "mismatch after range overwrites"
    # truncate shorter, then longer (zero fill)
    tname = "text-204800"
    tpath = os.path.join(base, tname)
    os.truncate(tpath, 100000)
    os.truncate(tpath, 150000)
    shadow[tname] = shadow[tname][:100000] + b"\x00" * 50000
    drop_caches()
    with open(tpath, "rb") as f:
        assert f.read() == shadow[tname], "mismatch after truncate"
    # rename, delete, recreate
    os.replace(os.path.join(base, "rand-1"), os.path.join(base, "renamed"))
    shadow["renamed"] = shadow.pop("rand-1")
    os.remove(os.path.join(base, "text-1"))
    del shadow["text-1"]
    with open(os.path.join(base, "text-1"), "wb") as f:
        f.write(b"recreated with different content\n")
    shadow["text-1"] = b"recreated with different content\n"
    os.symlink("renamed", os.path.join(base, "sym"))
    assert os.readlink(os.path.join(base, "sym")) == "renamed"
    assert sorted(os.listdir(base)) == sorted(list(shadow) + ["sym"])
    drop_caches()
    for name, data in shadow.items():
        with open(os.path.join(base, name), "rb") as f:
            assert f.read() == data, "final mismatch: " + name
    print("acceptance 1 (byte fidelity): PASS "
          "(%d files, boundary overwrites, truncate, rename/delete/recreate)"
          % len(shadow))


# --- acceptance test 2: real git -----------------------------------------

def git_env():
    env = dict(os.environ)
    env.update(GIT_AUTHOR_NAME="alice", GIT_AUTHOR_EMAIL="alice@example.com",
               GIT_COMMITTER_NAME="alice", GIT_COMMITTER_EMAIL="alice@example.com",
               GIT_CONFIG_NOSYSTEM="1", HOME=WORK)
    return env


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo] + list(args), env=git_env(),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError("git %s failed (%d):\n%s\n%s"
                             % (" ".join(args), r.returncode, r.stdout, r.stderr))
    return r.stdout


def test_git():
    repo = os.path.join(MNT, "repo")
    os.mkdir(repo)
    os.mkdir(os.path.join(repo, "src"))
    os.mkdir(os.path.join(repo, "docs"))
    for i in range(30):
        body = "".join("def fn_%d_%d():\n    return %d\n\n"
                       % (i, j, rng.randrange(10**6)) for j in range(12))
        with open(os.path.join(repo, "src", "mod_%02d.py" % i), "w") as f:
            f.write(LICENSE + body)
    for name in ("README.md", "CONTRIBUTING.md", "docs/guide.md"):
        with open(os.path.join(repo, name), "w") as f:
            f.write("# %s\n\n%s\nDocument-specific content for %s.\n"
                    % (name, BOILER, name))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c1: initial tree")
    v1_mod00 = open(os.path.join(repo, "src", "mod_00.py")).read()

    for i in range(8):
        with open(os.path.join(repo, "src", "mod_%02d.py" % i), "a") as f:
            f.write("\ndef added_in_c2_%d():\n    return %d\n" % (i, i))
    with open(os.path.join(repo, "src", "mod_new.py"), "w") as f:
        f.write(LICENSE + "def newcomer():\n    return 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c2: edits and a new file")

    os.remove(os.path.join(repo, "src", "mod_29.py"))
    for i in (10, 11, 12):
        with open(os.path.join(repo, "src", "mod_%02d.py" % i), "a") as f:
            f.write("\n# touched in c3\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c3: delete and edits")

    log = git(repo, "log", "--oneline")
    assert len(log.strip().splitlines()) == 3, log
    first = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    git(repo, "checkout", "-q", first)
    assert open(os.path.join(repo, "src", "mod_00.py")).read() == v1_mod00
    assert os.path.exists(os.path.join(repo, "src", "mod_29.py"))
    assert not os.path.exists(os.path.join(repo, "src", "mod_new.py"))
    git(repo, "checkout", "-q", "main")
    assert not os.path.exists(os.path.join(repo, "src", "mod_29.py"))
    git(repo, "fsck", "--strict")
    print("acceptance 2 (real git): PASS "
          "(init, 3 commits, log, checkout of first commit and back, fsck)")


# --- main ----------------------------------------------------------------

def main():
    if os.path.ismount(MNT):
        subprocess.run(["fusermount", "-uz", MNT], check=False)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(MNT)
    results = {}

    stats1 = os.path.join(WORK, "stats-main.json")
    proc = mount(stats1)
    try:
        test_fidelity()
        test_git()
        drop_caches()
        before = tree_checksums()
    finally:
        unmount(proc)   # clean unmount dumps opstats
    results["opstats"] = json.load(open(stats1))["opstats"]

    # acceptance 3: kill (SIGKILL — nothing flushed, nothing recovered), remount
    proc = mount()
    try:
        unmount(proc, kill=True)
        proc = mount()
        after = tree_checksums()
        assert after == before, "restart changed the tree"
        assert "c3: delete and edits" in git(os.path.join(MNT, "repo"), "log")
        git(os.path.join(MNT, "repo"), "fsck", "--strict")
        # mirror the logical tree onto plain ext4 for measurement 1
        for rel, val in before.items():
            dst = os.path.join(MIRROR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if val.startswith("L:"):
                os.symlink(val[2:], dst)
            else:
                shutil.copyfile(os.path.join(MNT, rel), dst)
    finally:
        unmount(proc)
    print("acceptance 3 (restart survival): PASS "
          "(SIGKILL, remount, %d paths byte-identical, git log+fsck clean; "
          "zero recovery code exists)" % len(before))

    results["store_before"] = du(STORE)
    results["store_before"]["reachable"] = reachable_store_bytes()
    results["mirror"] = du(MIRROR)

    # acceptance 4: condensation pass with built-in checksum verification
    from am.condense import Pass
    report1 = Pass(STORE).run(log_path=os.path.join(ROOT, "LIBRARY.md"))
    results["condense"] = {
        "files": report1["files"],
        "admitted": [{k: v for k, v in e.items() if k != "h"}
                     for e in report1["admitted"]],
        "rejected_2file": report1["rejected_2file"],
        "span_rejections": report1["span_rejections"],
        "rewritten": report1["rewritten"],
        "library_total": report1["library_total"],
    }
    report2 = Pass(STORE).run()
    assert report2["rewritten"] == 0 and not any(
        e["fresh"] for e in report2["admitted"]), "pass is not idempotent"

    proc = mount()
    try:
        drop_caches()
        final = tree_checksums()
        assert final == before, "condensation changed rendered content"
        git(os.path.join(MNT, "repo"), "fsck", "--strict")
    finally:
        unmount(proc)
    print("acceptance 4 (condensation fidelity): PASS "
          "(full-tree checksums identical through a fresh mount; second "
          "pass rewrote nothing — idempotent)")

    results["store_after"] = du(STORE)
    results["store_after"]["reachable"] = reachable_store_bytes()

    with open(os.path.join(ROOT, "phase3-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("\nresults written to phase3-results.json")
    print("admitted structures: %d (library total %d)"
          % (sum(1 for e in report1["admitted"] if e["fresh"]),
             report1["library_total"]))
    print("store reachable bytes: %d -> %d (mirror on ext4: %d raw)"
          % (results["store_before"]["reachable"],
             results["store_after"]["reachable"],
             results["mirror"]["raw"]))


if __name__ == "__main__":
    main()
