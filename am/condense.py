"""Offline condensation pass (charter section 7, stage 2).

Scans all stored chains, finds recurring content blocks, promotes the
fat ones to library structures (content templates -- zero-operand pure
structures whose definition is an unsent literal instruction under
store/lib/<sid>), and rewrites chains to reference them. Append+swap
throughout: rewritten chunks and chains get fresh references, heads are
swapped last, old files stay unreachable.

Run with the mount STOPPED: this pass is the offline library-growth
event, and there must be exactly one process owning the store's
terminals at a time.

Method, and why it is idempotent:

- Candidates are mined from the RENDERED content of every file
  (content-defined chunking with a fixed, deterministic hash table).
  Rendering is invariant under rewrites, so every run sees the same
  candidates; blocks already promoted are recognized by content and
  reuse their structure ID, and occurrences already stored as a
  composition over that ID are left untouched. A second run therefore
  rewrites nothing.
- A candidate is admitted only if it recurs in >= 3 distinct files
  (charter admission rule) and is at least MIN_BLOCK bytes (never
  atoms). Fattest first: candidates are admitted in order of total
  bytes saved.
- An occurrence is only replaceable if it falls entirely inside one
  stored literal; blocks spanning chunk boundaries are counted and
  logged as rejections (the charter's fixed-boundary caveat).
- Nothing that fires values: a template renders one constant block.

This pass -- and only this pass -- walks stored instruction bytes
structurally (chartered in section 7: "scans all stored chains"). The
live layer never does.

Verification is built in: every affected file's new chain is rendered
and checksum-compared against its pre-rewrite rendering BEFORE the head
is swapped; the pass aborts on any mismatch, and a full-tree checksum
comparison runs at the end.
"""

import argparse
import hashlib
import os
import sys
import time

from .instruction import COMP, DEMAND, ERR, LIT, _rv, comp, demand, lit
from .layer import CHUNK, PROMOTED_BASE, Layer
from .structures import CONCAT, EMIT_DISK

MIN_BLOCK = 512          # never atoms: floor for a promotable block
CDC_MIN, CDC_MASK, CDC_MAX = 512, 0x7FF, 16384   # ~2 KiB average segments
_WIN = 48

# Deterministic hash table: no randomness at runtime, same table forever.
_TAB = [int.from_bytes(hashlib.sha256(b"cdc-%d" % i).digest()[:8], "big")
        for i in range(256)]
_M64 = (1 << 64) - 1


def cdc_segments(data):
    """Content-defined segment boundaries (buzhash). Deterministic:
    same bytes always split the same way, which is what makes both
    recurrence detection and the whole pass idempotent."""
    n = len(data)
    if n <= CDC_MIN:
        return [(0, n)] if n else []
    segs = []
    start = 0
    h = 0
    for i in range(n):
        h = (((h << 1) | (h >> 63)) & _M64) ^ _TAB[data[i]]
        if i - start + 1 >= _WIN:
            out = data[i - _WIN + 1]
            # buzhash remove: undo the oldest byte's rotated contribution
            rot = _WIN - 1
            h ^= (((_TAB[out] << rot) | (_TAB[out] >> (64 - rot))) & _M64)
        length = i - start + 1
        if (length >= CDC_MIN and (h & CDC_MASK) == CDC_MASK) or length >= CDC_MAX:
            segs.append((start, i + 1))
            start = i + 1
            h = 0
    if start < n:
        segs.append((start, n))
    return segs


# --- structural walk of stored chains (offline only, chartered) ---------

def _walk_node(buf, off, pieces, container, root):
    tag = buf[off]
    off += 1
    if tag == LIT:
        n, off = _rv(buf, off)
        pieces.append([container, "lit", bytes(buf[off:off + n])])
        return off + n
    if tag == COMP:
        sid, off = _rv(buf, off)
        argc, off = _rv(buf, off)
        if sid == CONCAT:
            for _ in range(argc):
                off = _walk_node(buf, off, pieces, container, root)
            return off
        if sid >= PROMOTED_BASE and argc == 0:
            pieces.append([container, "sid", sid])
            return off
        raise ValueError("unexpected composition sid=%d in stored chain" % sid)
    if tag == DEMAND:
        n, off = _rv(buf, off)
        ref = bytes(buf[off:off + n]).decode()
        sub = open(os.path.join(root, ref), "rb").read()
        end = _walk_node(sub, 0, pieces, ref, root)
        assert end == len(sub), ref
        return off + n
    raise ValueError("unexpected node tag %d in stored chain" % tag)


def walk_chain(root, chain_ref):
    """Flatten a stored chain into ordered pieces:
    [container_ref, "lit", bytes] | [container_ref, "sid", id]."""
    pieces = []
    buf = open(os.path.join(root, chain_ref), "rb").read()
    end = _walk_node(buf, 0, pieces, chain_ref, root)
    assert end == len(buf), chain_ref
    return pieces


def _heads(root):
    fsroot = os.path.join(root, "fs")
    for dirpath, _, names in os.walk(fsroot):
        for name in sorted(names):
            yield os.path.relpath(os.path.join(dirpath, name), fsroot)


class Pass:
    def __init__(self, store_root):
        self.layer = Layer(store_root)
        self.root = self.layer.root
        # The pass IS the offline library-growth event: it may extend the
        # registry it fires with as it admits structures. Mounted layers
        # load the result read-only.
        self.registry = dict(self.layer.registry)
        self.layer.registry = self.registry
        self.by_hash = {}   # template-block sha -> sid, for reuse/idempotency
        for sid, size in self.layer.promoted.items():
            block = self.registry[sid]([])
            self.by_hash[hashlib.sha256(block).digest()] = sid
        self.next_sid = PROMOTED_BASE + len(self.layer.promoted)
        self._seq = 0

    def _fresh_ref(self, suffix=""):
        self._seq += 1
        return "chains/%d-c%d%s" % (time.time_ns(), self._seq, suffix)

    def scan(self):
        """Per file: meta, rendered checksum, stored pieces with offsets,
        and CDC candidates over the rendered bytes."""
        files = []
        occurrences = {}   # block sha -> list of (file idx, start, end)
        seen_in = {}       # block sha -> set of file paths
        for rel in _heads(self.root):
            t, chain, size, mtime, mode = self.layer._head("/" + rel)
            rendered = self.layer._render(chain)
            pieces = walk_chain(self.root, chain)
            # pieces must re-render identically (sanity of the walk)
            joined = b"".join(p[2] if p[1] == "lit"
                              else self.registry[p[2]]([]) for p in pieces)
            assert joined == rendered, rel
            idx = len(files)
            files.append(dict(rel=rel, type=t, chain=chain, size=size,
                              mtime=mtime, mode=mode, sha=hashlib.sha256(rendered).digest(),
                              rendered=rendered, pieces=pieces))
            for s, e in cdc_segments(rendered):
                if e - s < MIN_BLOCK:
                    continue
                h = hashlib.sha256(rendered[s:e]).digest()
                occurrences.setdefault(h, []).append((idx, s, e))
                seen_in.setdefault(h, set()).add(rel)
        return files, occurrences, seen_in

    def admit(self, files, occurrences, seen_in):
        """Charter admission: >= 3 distinct files, fattest first."""
        admitted, rejected = [], []
        for h, occ in occurrences.items():
            size = occ[0][2] - occ[0][1]
            nfiles = len(seen_in[h])
            saved = size * (len(occ) - 1)
            entry = dict(h=h, size=size, files=nfiles, hits=len(occ),
                         saved=saved, examples=sorted(seen_in[h])[:4])
            if nfiles >= 3:
                admitted.append(entry)
            elif nfiles > 1:
                rejected.append(entry)
        admitted.sort(key=lambda e: -e["saved"])
        rejected.sort(key=lambda e: -e["saved"])
        return admitted, rejected

    def promote(self, entry, block):
        sha = hashlib.sha256(block).digest()
        if sha in self.by_hash:
            return self.by_hash[sha], False
        sid = self.next_sid
        self.next_sid += 1
        self.layer._fire(comp(EMIT_DISK, lit("lib/%d" % sid), lit(lit(block))))
        self.registry[sid] = (lambda b: lambda values: b)(block)
        self.by_hash[sha] = sid
        return sid, True

    def rewrite_file(self, f, replacements):
        """replacements: list of (start, end, sid) in rendered offsets,
        non-overlapping, sorted, each wholly inside one stored literal.

        The file's chunk TOPOLOGY is preserved: only containers whose
        pieces change are re-emitted (fresh refs, append+swap); the new
        chain reuses unchanged chunk references. Keeping boundaries
        where they are is what makes the pass idempotent -- regrouping
        would move the fixed boundaries and turn span-rejections into
        next-run rewrites."""
        per = {}      # container ref -> rebuilt node list
        order = []    # containers in chain order
        changed = set()
        pos = 0
        ri = 0
        for container, kind, payload in f["pieces"]:
            if container not in per:
                per[container] = []
                order.append(container)
            nodes = per[container]
            if kind == "sid":
                nodes.append(("sid", payload))
                pos += len(self.registry[payload]([]))
                continue
            plen = len(payload)
            cut = 0
            while ri < len(replacements) and replacements[ri][0] < pos + plen:
                s, e, sid = replacements[ri]
                if not (pos <= s and e <= pos + plen):
                    break
                if s - pos > cut:
                    nodes.append(("lit", payload[cut:s - pos]))
                nodes.append(("sid", sid))
                changed.add(container)
                cut = e - pos
                ri += 1
            if cut < plen:
                nodes.append(("lit", payload[cut:]))
            pos += plen
        if not changed:
            return False

        def body_of(nodes):
            merged = []
            for kind, val in nodes:
                if kind == "lit" and merged and merged[-1][0] == "lit":
                    merged[-1] = ("lit", merged[-1][1] + val)
                else:
                    merged.append((kind, val))
            enc = [lit(v) if k == "lit" else comp(v) for k, v in merged]
            return enc[0] if len(enc) == 1 else comp(CONCAT, *enc)

        emits = []
        chain_ref = self._fresh_ref()
        if order == [f["chain"]]:
            # single-chunk file: the chain file is the only container
            emits.append(comp(EMIT_DISK, lit(chain_ref),
                              lit(body_of(per[f["chain"]]))))
        else:
            refs = []
            for i, container in enumerate(order):
                if container in changed:
                    ref = "%s.%d" % (chain_ref, i)
                    emits.append(comp(EMIT_DISK, lit(ref),
                                      lit(body_of(per[container]))))
                    refs.append(ref)
                else:
                    refs.append(container)   # reuse the untouched chunk
            emits.append(comp(EMIT_DISK, lit(chain_ref),
                              lit(comp(CONCAT, *[demand(r) for r in refs]))))
        self.layer._fire(comp(CONCAT, *emits))
        # verify BEFORE the head swap: the new chain must render identically
        if hashlib.sha256(self.layer._render(chain_ref)).digest() != f["sha"]:
            raise RuntimeError("render mismatch for %s -- head NOT swapped"
                               % f["rel"])
        head = self.layer._head_bytes(f["type"], chain_ref, f["size"],
                                      f["mtime"], f["mode"])
        self.layer._fire(comp(EMIT_DISK, lit("fs/" + f["rel"]), lit(head)))
        return True

    def run(self, log_path=None):
        files, occurrences, seen_in = self.scan()
        admitted, rejected = self.admit(files, occurrences, seen_in)
        plans = {}       # file idx -> list of (start, end, sid)
        results = []
        spans = 0
        for entry in admitted:
            occ = occurrences[entry["h"]]
            idx0, s0, e0 = occ[0]
            block = files[idx0]["rendered"][s0:e0]
            sid, fresh = self.promote(entry, block)
            entry["sid"] = sid
            entry["fresh"] = fresh
            replaced = 0
            for idx, s, e in occ:
                # replaceable only if wholly inside one stored literal
                pos = 0
                ok = False
                already = False
                for container, kind, payload in files[idx]["pieces"]:
                    plen = (len(payload) if kind == "lit"
                            else len(self.registry[payload]([])))
                    if kind == "sid" and pos == s and pos + plen == e \
                            and payload == sid:
                        already = True
                        break
                    if kind == "lit" and pos <= s and e <= pos + plen:
                        ok = True
                        break
                    pos += plen
                if already:
                    continue
                if ok:
                    plans.setdefault(idx, []).append((s, e, sid))
                    replaced += 1
                else:
                    spans += 1
            entry["replaced"] = replaced
            results.append(entry)
        rewritten = 0
        for idx, reps in sorted(plans.items()):
            reps.sort()
            if self.rewrite_file(files[idx], reps):
                rewritten += 1
        # full-tree verification (charter section 7, mandatory)
        for f in files:
            _, chain, _, _, _ = self.layer._head("/" + f["rel"])
            if hashlib.sha256(self.layer._render(chain)).digest() != f["sha"]:
                raise RuntimeError("POST-PASS MISMATCH: " + f["rel"])
        report = dict(files=len(files),
                      admitted=results, rejected_2file=len(rejected),
                      rejected_top=rejected[:5], span_rejections=spans,
                      rewritten=rewritten,
                      library_total=5 + len(self.by_hash))
        if log_path and any(e["fresh"] for e in results):
            self._append_log(log_path, report)
        return report

    def _append_log(self, log_path, report):
        with open(log_path, "a") as f:
            f.write("\n### Condensation pass admissions (%s)\n\n"
                    % time.strftime("%Y-%m-%d"))
            f.write("| sid | block bytes | files | hits | bytes saved | example files |\n")
            f.write("|---|---|---|---|---|---|\n")
            for e in report["admitted"]:
                if not e["fresh"]:
                    continue
                f.write("| %d | %d | %d | %d | %d | %s |\n"
                        % (e["sid"], e["size"], e["files"], e["hits"],
                           e["saved"], ", ".join(e["examples"])))
            f.write("\nRejected: %d recurring blocks seen in only 2 files; "
                    "%d admitted-block occurrences unreplaceable because they "
                    "span stored chunk boundaries (fixed 64 KiB boundaries "
                    "-- charter's noted caveat).\n"
                    % (report["rejected_2file"], report["span_rejections"]))


def main():
    ap = argparse.ArgumentParser(description="Offline condensation pass")
    ap.add_argument("--store", default="store")
    ap.add_argument("--log", default=None, help="LIBRARY.md path to append to")
    args = ap.parse_args()
    report = Pass(args.store).run(args.log)
    fresh = [e for e in report["admitted"] if e["fresh"]]
    print("files scanned: %d" % report["files"])
    print("structures admitted this run: %d (library total now %d)"
          % (len(fresh), report["library_total"]))
    for e in report["admitted"]:
        print("  sid=%d size=%dB files=%d hits=%d saved=%dB%s"
              % (e["sid"], e["size"], e["files"], e["hits"], e["saved"],
                 "" if e["fresh"] else " (already promoted)"))
    print("chains rewritten: %d; span-rejected occurrences: %d; "
          "2-file rejections: %d"
          % (report["rewritten"], report["span_rejections"],
             report["rejected_2file"]))
    print("full-tree render verification: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
