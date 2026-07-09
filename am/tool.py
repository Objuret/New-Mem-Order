"""amtool — snapshots, restore, verification, replication.

The model doing a real job: the phase-10 evidence says versioned trees
are where reference-sharing wins outright (beats tar.gz, beats
whole-file dedup, stays per-file demandable). This tool is that use,
made usable — and it is deliberately nothing but a WORLD-SIDE program
composing machinery that already exists: the layer's put/read API for
ingest, the chartered condensation and compaction passes after every
snapshot, the phase-5 sync for replication, the FUSE binding for
browsing. No new structures, no new grammar, no rule changes; the delta
problem (#37) is answered by ordering alone — snapshots are condensed
and compacted BEFORE they are pushed, so the wire carries references
into templates the receiver already holds plus whatever content is
genuinely new.

Layout: every snapshot is a fresh namespace fs/<label>/... — nothing is
ever overwritten, so a snapshot is immutable the moment it exists, and
"restore any version" is just rendering a subtree.

    python3 -m am.tool snap DIR --label L [--store S] [--no-passes]
    python3 -m am.tool snaps                 # list snapshots
    python3 -m am.tool ls  LABEL [PATH]      # list inside a snapshot
    python3 -m am.tool cat LABEL/PATH        # render one file to stdout
    python3 -m am.tool restore LABEL OUTDIR  # materialize a snapshot
    python3 -m am.tool verify  LABEL DIR     # compare snapshot to a tree
    python3 -m am.tool stats                 # store vs logical, templates
    python3 -m am.tool serve --port P        # be a replication target
    python3 -m am.tool push HOST:PORT        # replicate (delta by mtime)
    python3 -m am.tool mount MOUNTPOINT      # browse all snapshots (FUSE)
"""

import argparse
import hashlib
import os
import sys
import time

from .layer import Layer, LayerError


def _layer(args):
    return Layer(args.store)


def _walk_src(srcdir):
    for dirpath, dirs, names in os.walk(srcdir):
        dirs.sort()
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, srcdir), full


def cmd_snap(args):
    layer = _layer(args)
    label = args.label or time.strftime("%Y%m%d-%H%M%S")
    if os.path.exists(os.path.join(layer.root, "fs", label)):
        print("snapshot %r already exists" % label, file=sys.stderr)
        return 1
    t0 = time.monotonic()
    files = bytes_in = 0
    for rel, full in _walk_src(args.dir):
        st = os.lstat(full)
        dst = "/%s/%s" % (label, rel)
        if os.path.islink(full):
            layer.put_symlink(dst, os.readlink(full), mtime_ns=st.st_mtime_ns)
        else:
            with open(full, "rb") as f:
                data = f.read()
            layer.put(dst, data, mode=st.st_mode, mtime_ns=st.st_mtime_ns)
            bytes_in += len(data)
        files += 1
    ingest_s = time.monotonic() - t0
    line = "snap %s: %d files, %.1f MB in %.1fs" % (label, files,
                                                    bytes_in / 1e6, ingest_s)
    if not args.no_passes:
        from .compact import run as compact_run
        from .condense import Pass
        t0 = time.monotonic()
        rep = Pass(args.store).run(log_path=None)
        comp = compact_run(args.store)
        fresh = sum(1 for e in rep["admitted"] if e["fresh"])
        line += ("; condensed (+%d templates) and compacted (%.1f MB "
                 "reclaimed) in %.1fs"
                 % (fresh, comp["freed"] / 1e6, time.monotonic() - t0))
    print(line)
    return 0


def cmd_snaps(args):
    fsroot = os.path.join(_layer(args).root, "fs")
    if not os.path.isdir(fsroot):
        return 0
    for label in sorted(os.listdir(fsroot)):
        st = os.stat(os.path.join(fsroot, label))
        print("%s  (%s)" % (label, time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(st.st_mtime))))
    return 0


def cmd_ls(args):
    layer = _layer(args)
    path = "/" + args.label + ("/" + args.path if args.path else "")
    for name in sorted(layer.readdir(path)):
        print(name)
    return 0


def cmd_cat(args):
    layer = _layer(args)
    attrs = layer.getattr("/" + args.path)
    sys.stdout.buffer.write(layer.read("/" + args.path, attrs["st_size"], 0))
    return 0


def _snapshot_files(layer, label):
    base = os.path.join(layer.root, "fs", label)
    if not os.path.isdir(base):
        raise LayerError(2)
    for dirpath, dirs, names in os.walk(base):
        dirs.sort()
        for name in sorted(names):
            yield os.path.relpath(os.path.join(dirpath, name), base)


def cmd_restore(args):
    layer = _layer(args)
    n = 0
    for rel in _snapshot_files(layer, args.label):
        vpath = "/%s/%s" % (args.label, rel)
        t, chain, size, mtime_ns, mode = layer._head(vpath)
        dst = os.path.join(args.outdir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if t == b"l":
            os.symlink(layer.readlink(vpath), dst)
        else:
            with open(dst, "wb") as f:
                f.write(layer._render(chain))
            os.chmod(dst, mode)
            os.utime(dst, ns=(mtime_ns, mtime_ns))
        n += 1
    print("restored %s: %d files -> %s" % (args.label, n, args.outdir))
    return 0


def cmd_verify(args):
    layer = _layer(args)
    bad = total = 0
    for rel in _snapshot_files(layer, args.label):
        vpath = "/%s/%s" % (args.label, rel)
        t, chain, _, _, _ = layer._head(vpath)
        src = os.path.join(args.dir, rel)
        total += 1
        if t == b"l":
            ok = os.path.islink(src) and os.readlink(src) == layer.readlink(vpath)
        else:
            try:
                with open(src, "rb") as f:
                    ok = hashlib.sha256(f.read()).digest() == \
                        hashlib.sha256(layer._render(chain)).digest()
            except OSError:
                ok = False
        if not ok:
            print("MISMATCH: " + rel)
            bad += 1
    print("verify %s vs %s: %d files, %d mismatches"
          % (args.label, args.dir, total, bad))
    return 1 if bad else 0


def cmd_stats(args):
    layer = _layer(args)
    logical = files = 0
    for dirpath, _, names in os.walk(os.path.join(layer.root, "fs")):
        for name in names:
            rel = os.path.relpath(os.path.join(dirpath, name),
                                  os.path.join(layer.root, "fs"))
            _, _, size, _, _ = layer._head("/" + rel)
            logical += size
            files += 1
    stored = 0
    for dirpath, _, names in os.walk(layer.root):
        for name in names:
            stored += os.lstat(os.path.join(dirpath, name)).st_size
    print("snapshots: %d, files: %d" % (
        len(os.listdir(os.path.join(layer.root, "fs")))
        if os.path.isdir(os.path.join(layer.root, "fs")) else 0, files))
    print("logical:  %10.2f MB" % (logical / 1e6))
    print("stored:   %10.2f MB  (%.2fx)" % (stored / 1e6,
                                            stored / logical if logical else 0))
    print("templates resident: %d" % len(layer.promoted))
    return 0


def cmd_serve(args):
    import asyncio
    from .router import serve
    try:
        asyncio.run(serve(args.host, args.port, args.store, None))
    except KeyboardInterrupt:
        pass
    return 0


def cmd_push(args):
    from .sync import sync
    host, port = args.target.rsplit(":", 1)
    mark_path = os.path.realpath(args.store).rstrip("/") + \
        ".pushed-%s-%s" % (host, port)   # driver-side state, beside the store
    since = 0
    if not args.full and os.path.exists(mark_path):
        with open(mark_path) as f:
            since = int(f.read().strip() or 0)
    now_ns = time.time_ns()
    r = sync(args.store, host, int(port), since_ns=since)
    if r["refusals"]:
        for ref, err in r["refusals"]:
            print("refused: %s: %s" % (ref, err.decode(errors="replace")),
                  file=sys.stderr)
        return 1
    with open(mark_path, "w") as f:
        f.write(str(now_ns))
    print("pushed %d files, %.2f MB wire%s"
          % (r["files"], r["wire_bytes"] / 1e6,
             " (delta since last push)" if since else " (full)"))
    return 0


def cmd_mount(args):
    from fuse import FUSE
    from .fuse import LayerFS
    print("mounting %s at %s (ctrl-c or fusermount -u to stop)"
          % (args.store, args.mountpoint), file=sys.stderr)
    FUSE(LayerFS(_layer(args)), args.mountpoint, foreground=True,
         nothreads=True, attr_timeout=0, entry_timeout=0)
    return 0


def main():
    ap = argparse.ArgumentParser(prog="am.tool", description=__doc__.split("\n")[0])
    ap.add_argument("--store", default="amstore")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("snap")
    p.add_argument("dir")
    p.add_argument("--label")
    p.add_argument("--no-passes", action="store_true")
    p.set_defaults(fn=cmd_snap)
    sub.add_parser("snaps").set_defaults(fn=cmd_snaps)
    p = sub.add_parser("ls")
    p.add_argument("label")
    p.add_argument("path", nargs="?")
    p.set_defaults(fn=cmd_ls)
    p = sub.add_parser("cat")
    p.add_argument("path", help="LABEL/relative/path")
    p.set_defaults(fn=cmd_cat)
    p = sub.add_parser("restore")
    p.add_argument("label")
    p.add_argument("outdir")
    p.set_defaults(fn=cmd_restore)
    p = sub.add_parser("verify")
    p.add_argument("label")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_verify)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("push")
    p.add_argument("target", help="HOST:PORT of a serving store")
    p.add_argument("--full", action="store_true")
    p.set_defaults(fn=cmd_push)
    p = sub.add_parser("mount")
    p.add_argument("mountpoint")
    p.set_defaults(fn=cmd_mount)
    args = ap.parse_args()
    try:
        return args.fn(args)
    except LayerError as e:
        print("error: errno %d" % e.errno, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
