"""The layer (PHASE3-LAYER.md): unmodified programs above, the runtime below.

Every file in the mounted namespace is stored as an instruction chain
over the resident library; reading a file demands its head and FIRES the
chain to render the bytes. This module is the layer's whole logic behind
a plain function API; am/fuse.py binds it to FUSE.

Storage mapping (charter section 4, pre-ruled):

- head for mount path /a/b  ->  store/fs/a/b, an instruction rendering a
  five-field record (type, chain ref, size, mtime_ns, mode -- each field
  a literal, "\n"-terminated; the record convention is the layer's own,
  entering and leaving as values, phase-2 pattern)
- content chain             ->  store/chains/<id>: a literal node for
  files of one chunk (<= 64 KiB), else a composition demanding chunk
  files store/chains/<id>.<i>. Condensed chunks are compositions over
  promoted structures instead of plain literals.
- directories               ->  real directories of head files; a plain
  listing IS readdir. No index, no manifest, no database.

Content operations fire instructions on the single in-process router
context (charter section 5: one mount = one router = the owner of the
emit-disk terminal; firings never yield, so each operation is atomic).
Namespace operations -- readdir, unlink, rename, mkdir, rmdir -- are
reference management in the world, the same act as deleting a file is
today (spec section 4).

The live layer never inspects stored instruction bytes structurally; it
only constructs instructions and fires them. (The offline condensation
pass is chartered to walk stored chains; the layer is not.)

Every write stores fresh chunks for the whole new content: reusing an
old version's chunk files would require knowing their references, which
only the stored chain holds, and the layer may not parse it. Superseded
chains stay on disk unreachable (charter: no reclamation; space is a
measurement). Emits inside a write fire left-to-right with the head
LAST, so an interrupted operation leaves the old head pointing at the
old complete chain -- crash consistency by construction, not by code.
"""

import errno
import os
import stat as stat_m
import time
from types import MappingProxyType

from .instruction import Refusal, comp, demand, fire, lit
from .router import Ctx
from .structures import CONCAT, EMIT_DISK, make_registry, resolve_ref

CHUNK = 64 * 1024

# Promoted structures (condensation admissions) get IDs from here up;
# 1-5 are the frozen phase-1/2 library.
PROMOTED_BASE = 100


class LayerError(Exception):
    """A POSIX-shaped refusal at the layer's edge."""

    def __init__(self, err):
        super().__init__(err)
        self.errno = err


class _CountingStats:
    """Instrumentation only (charter section 11.4): counts instruction
    firings -- top-level fires plus demanded stored files -- per
    layer operation. Model behavior does not depend on it."""

    def __init__(self, layer):
        self._layer = layer

    def instruction(self, source, buf):
        op = self._layer._cur_op
        if op is not None:
            self._layer.opstats[op][1] += 1

    def firing(self, nodes, outcome):
        pass


def _const(block):
    def template(values):
        if values:
            raise Refusal(b"content template takes no operands")
        return block
    return template


class Layer:
    def __init__(self, store_root, cache=True):
        # The render cache is the demander's own memory of outputs it
        # received — the model is not consulted and not changed; delete
        # the cache and nothing differs but time (DECISIONS.md 1.15).
        # Sound because this mount is the store's only writer and every
        # write goes to a FRESH chain reference (append+swap), so a
        # chain ref's render can never change while mounted; across
        # mounts, the condensation pass is render-identity-verified.
        # Heads are mutable and are never cached.
        self._render_cache = {} if cache else None
        self._cache_bytes = 0
        self.cache_hits = 0
        self.root = os.path.realpath(store_root)
        os.makedirs(os.path.join(self.root, "fs"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "chains"), exist_ok=True)
        self.opstats = {}   # op -> [calls, instruction firings]
        self._cur_op = None
        self._stats = _CountingStats(self)
        self._seq = 0
        registry = dict(make_registry(self.root))
        # Load the promoted library: each admission is an unsent literal
        # instruction under store/lib/<sid>, fired once here and resident
        # for the life of the mount (A1: immutable at runtime; growth
        # happens only in the offline condensation pass).
        self.promoted = {}
        libdir = os.path.join(self.root, "lib")
        if os.path.isdir(libdir):
            for name in sorted(os.listdir(libdir)):
                sid = int(name)
                block = self._fire(demand("lib/" + name), registry)
                registry[sid] = _const(block)
                self.promoted[sid] = len(block)
        self.registry = MappingProxyType(registry)

    # --- the router side: constructing and firing instructions ---

    def _fire(self, instr, registry=None):
        if self._cur_op is not None:
            self.opstats[self._cur_op][1] += 1
        ctx = Ctx(registry or self.registry, self.root, self._stats)
        try:
            value, _ = fire(instr, 0, ctx)
        except Refusal as r:
            if r.payload.startswith(b"no such reference"):
                raise LayerError(errno.ENOENT)
            raise LayerError(errno.EIO)
        return value

    def _op(self, name):
        self.opstats.setdefault(name, [0, 0])[0] += 1
        self._cur_op = name

    # --- reference plumbing (the world's namespace of heads) ---

    def _ref(self, path):
        parts = [p for p in path.split("/") if p]
        if any(p in (".", "..") or "\x00" in p for p in parts):
            raise LayerError(errno.EINVAL)
        return "/".join(["fs"] + parts)

    def _backing(self, path):
        return resolve_ref(self.root, self._ref(path).encode())

    def _head(self, path):
        """Demand the head; split its five-field record (the layer owns
        this convention -- it wrote it). Returns (type, chain_ref, size,
        mtime_ns, mode)."""
        rendered = self._fire(demand(self._ref(path)))
        t, chain, size, mtime, mode = rendered.split(b"\n")[:5]
        return t, chain.decode(), int(size), int(mtime), int(mode)

    def _head_bytes(self, ftype, chain_ref, size, mtime_ns, mode):
        return comp(CONCAT,
                    lit(ftype + b"\n"),
                    lit(chain_ref.encode() + b"\n"),
                    lit(b"%d\n" % size),
                    lit(b"%d\n" % mtime_ns),
                    lit(b"%d\n" % mode))

    def _store(self, path, content, mode, ftype=b"f", mtime_ns=None):
        """One indivisible firing: emit fresh chunk files, the chain,
        and (last) the head. Charter section 4 write = append + swap."""
        if mtime_ns is None:
            mtime_ns = time.time_ns()     # the world supplies what varies
        cid = "chains/%d-%d" % (time.time_ns(), self._seq)
        self._seq += 1
        emits = []
        if len(content) <= CHUNK:
            emits.append(comp(EMIT_DISK, lit(cid), lit(lit(content))))
        else:
            refs = []
            for i in range(0, len(content), CHUNK):
                ref = "%s.%d" % (cid, i // CHUNK)
                refs.append(ref)
                emits.append(comp(EMIT_DISK, lit(ref),
                                  lit(lit(content[i:i + CHUNK]))))
            chain = comp(CONCAT, *[demand(r) for r in refs])
            emits.append(comp(EMIT_DISK, lit(cid), lit(chain)))
        head = self._head_bytes(ftype, cid, len(content), mtime_ns, mode)
        emits.append(comp(EMIT_DISK, lit(self._ref(path)), lit(head)))
        self._fire(comp(CONCAT, *emits))

    CACHE_CAP = 256 * 1024 * 1024

    def _render(self, chain_ref):
        cache = self._render_cache
        if cache is not None:
            hit = cache.get(chain_ref)
            if hit is not None:
                self.cache_hits += 1
                return hit
        value = self._fire(demand(chain_ref))
        if cache is not None and self._cache_bytes + len(value) <= self.CACHE_CAP:
            cache[chain_ref] = value
            self._cache_bytes += len(value)
        return value

    # --- whole-file API for world-side tools (no FUSE required) ---

    def put(self, path, data, mode=0o644, mtime_ns=None):
        """Store a file's whole content (create or replace)."""
        self._op("put")
        self._store(path, data, mode & 0o7777, mtime_ns=mtime_ns)

    def put_symlink(self, path, target, mtime_ns=None):
        self._op("put")
        self._store(path, target.encode(), 0o777, ftype=b"l",
                    mtime_ns=mtime_ns)

    # --- the API programs see ---

    def getattr(self, path):
        self._op("getattr")
        backing = self._backing(path)
        if os.path.isdir(backing):
            st = os.lstat(backing)
            return dict(st_mode=stat_m.S_IFDIR | 0o755, st_nlink=2,
                        st_size=0, st_mtime=st.st_mtime,
                        st_atime=st.st_mtime, st_ctime=st.st_mtime)
        if not os.path.isfile(backing):
            raise LayerError(errno.ENOENT)
        t, _, size, mtime_ns, mode = self._head(path)
        kind = stat_m.S_IFLNK | 0o777 if t == b"l" else stat_m.S_IFREG | mode
        mtime = mtime_ns / 1e9
        return dict(st_mode=kind, st_nlink=1, st_size=size,
                    st_mtime=mtime, st_atime=mtime, st_ctime=mtime)

    def readdir(self, path):
        self._op("readdir")
        backing = self._backing(path)
        if not os.path.isdir(backing):
            raise LayerError(errno.ENOTDIR)
        return os.listdir(backing)

    def read(self, path, size, offset):
        self._op("read")
        _, chain, _, _, _ = self._head(path)
        rendered = self._render(chain)   # fire the whole chain, slice after
        return rendered[offset:offset + size]

    def create(self, path, mode):
        self._op("create")
        backing = self._backing(path)
        if not os.path.isdir(os.path.dirname(backing)):
            raise LayerError(errno.ENOENT)
        if os.path.isdir(backing):
            raise LayerError(errno.EISDIR)
        self._store(path, b"", mode & 0o7777)

    def write(self, path, data, offset):
        self._op("write")
        _, chain, size, _, mode = self._head(path)
        if offset == 0 and len(data) >= size:
            content = data
        else:
            cur = self._render(chain)
            if offset > len(cur):
                cur = cur + b"\x00" * (offset - len(cur))
            content = cur[:offset] + data + cur[offset + len(data):]
        self._store(path, content, mode)
        return len(data)

    def truncate(self, path, length):
        self._op("truncate")
        _, chain, size, _, mode = self._head(path)
        if length == size:
            return
        if length == 0:
            content = b""
        else:
            cur = self._render(chain)
            content = (cur[:length] if length <= len(cur)
                       else cur + b"\x00" * (length - len(cur)))
        self._store(path, content, mode)

    def unlink(self, path):
        self._op("unlink")
        backing = self._backing(path)
        if os.path.isdir(backing):
            raise LayerError(errno.EISDIR)
        if not os.path.isfile(backing):
            raise LayerError(errno.ENOENT)
        os.remove(backing)   # delete = remove the head reference

    def mkdir(self, path, mode):
        self._op("mkdir")
        backing = self._backing(path)
        try:
            os.mkdir(backing)
        except FileExistsError:
            raise LayerError(errno.EEXIST)
        except FileNotFoundError:
            raise LayerError(errno.ENOENT)

    def rmdir(self, path):
        self._op("rmdir")
        backing = self._backing(path)
        if not os.path.isdir(backing):
            raise LayerError(errno.ENOTDIR)
        try:
            os.rmdir(backing)
        except OSError:
            raise LayerError(errno.ENOTEMPTY)

    def rename(self, old, new):
        self._op("rename")
        src, dst = self._backing(old), self._backing(new)
        if not os.path.exists(src):
            raise LayerError(errno.ENOENT)
        try:
            os.replace(src, dst)   # move the head reference
        except OSError as e:
            raise LayerError(e.errno or errno.EIO)

    def symlink(self, path, target):
        self._op("symlink")
        # A symlink is a file whose chain renders the target (charter
        # section 6: the target is a value; readlink renders it).
        self._store(path, target.encode(), 0o777, ftype=b"l")

    def readlink(self, path):
        self._op("readlink")
        t, chain, _, _, _ = self._head(path)
        if t != b"l":
            raise LayerError(errno.EINVAL)
        return self._render(chain).decode()

    def chmod(self, path, mode):
        self._op("chmod")
        t, chain, size, mtime_ns, _ = self._head(path)
        head = self._head_bytes(t, chain, size, mtime_ns, mode & 0o7777)
        self._fire(comp(EMIT_DISK, lit(self._ref(path)), lit(head)))

    def utimens(self, path, mtime_ns):
        self._op("utimens")
        t, chain, size, _, mode = self._head(path)
        head = self._head_bytes(t, chain, size, mtime_ns, mode)
        self._fire(comp(EMIT_DISK, lit(self._ref(path)), lit(head)))
