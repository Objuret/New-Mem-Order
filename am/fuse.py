"""FUSE binding for the layer (charter section 3).

Deliberately thin: every operation translates a kernel call into a
Layer call and a LayerError into an errno. Single-threaded
(nothreads=True) so the FUSE loop IS the router's single loop (charter
section 5); attr/entry timeouts are zero so the kernel always asks the
layer instead of caching stale metadata.

Faked rather than expressed natively (charter section 6, each logged in
FRICTION.md): chown (accepted, ignored), hardlinks (EPERM), atime/ctime
(reported as mtime), fsync/flush (no-ops -- every write is already at
rest when its firing returns).
"""

import argparse
import errno
import json
import sys
import time

from fuse import FUSE, FuseOSError, Operations

from .layer import Layer, LayerError


class LayerFS(Operations):
    def __init__(self, layer, stats_out=None):
        self.layer = layer
        self.stats_out = stats_out

    def _do(self, fn, *args):
        try:
            return fn(*args)
        except LayerError as e:
            raise FuseOSError(e.errno)

    # metadata
    def getattr(self, path, fh=None):
        return self._do(self.layer.getattr, path)

    def readdir(self, path, fh):
        return [".", ".."] + self._do(self.layer.readdir, path)

    def statfs(self, path):
        return dict(f_bsize=4096, f_frsize=4096, f_blocks=1 << 24,
                    f_bfree=1 << 23, f_bavail=1 << 23, f_files=1 << 20,
                    f_ffree=1 << 19, f_namemax=255)

    # content
    def read(self, path, size, offset, fh):
        return self._do(self.layer.read, path, size, offset)

    def write(self, path, data, offset, fh):
        return self._do(self.layer.write, path, data, offset)

    def create(self, path, mode, fi=None):
        self._do(self.layer.create, path, mode)
        return 0

    def truncate(self, path, length, fh=None):
        self._do(self.layer.truncate, path, length)

    # namespace
    def unlink(self, path):
        self._do(self.layer.unlink, path)

    def mkdir(self, path, mode):
        self._do(self.layer.mkdir, path, mode)

    def rmdir(self, path):
        self._do(self.layer.rmdir, path)

    def rename(self, old, new):
        self._do(self.layer.rename, old, new)

    def symlink(self, target, source):
        self._do(self.layer.symlink, target, source)

    def readlink(self, path):
        return self._do(self.layer.readlink, path)

    def link(self, target, source):
        raise FuseOSError(errno.EPERM)   # hardlinks: not supported, logged

    # attributes
    def chmod(self, path, mode):
        self._do(self.layer.chmod, path, mode)

    def chown(self, path, uid, gid):
        return 0   # faked: accepted and ignored

    def utimens(self, path, times=None):
        mtime = times[1] if times else time.time()
        self._do(self.layer.utimens, path, int(mtime * 1e9))

    # handles: the layer is stateless, handles carry nothing
    def open(self, path, flags):
        self._do(self.layer.getattr, path)
        return 0

    def flush(self, path, fh):
        return 0

    def release(self, path, fh):
        return 0

    def fsync(self, path, datasync, fh):
        return 0

    def destroy(self, path):
        if self.stats_out:   # instrumentation dump on clean unmount
            with open(self.stats_out, "w") as f:
                json.dump({"opstats": self.layer.opstats,
                           "promoted": len(self.layer.promoted),
                           "cache_hits": self.layer.cache_hits}, f)


def main():
    ap = argparse.ArgumentParser(description="Activation-model layer mount")
    ap.add_argument("mountpoint")
    ap.add_argument("--store", default="store")
    ap.add_argument("--stats-out", default=None)
    ap.add_argument("--raw", action="store_true",
                    help="disable the render cache (the v1 raw model)")
    args = ap.parse_args()
    layer = Layer(args.store, cache=not args.raw)
    print("layer: %d base + %d promoted structures resident"
          % (5, len(layer.promoted)), file=sys.stderr, flush=True)
    FUSE(LayerFS(layer, args.stats_out), args.mountpoint,
         foreground=True, nothreads=True, big_writes=True,
         max_write=131072, attr_timeout=0, entry_timeout=0,
         negative_timeout=0)


if __name__ == "__main__":
    main()
