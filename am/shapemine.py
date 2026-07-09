"""Offline shape-condensation pass (phase 4).

Mines stored instructions for recurring COMPOSITION SHAPES and promotes
them: a shape whose tree recurs in >= 3 distinct files becomes a
resident structure whose body is the tree with its per-instance-constant
literals folded in and its varying positions (literals and demand
outputs) turned into operand slots. Instances are rewritten from
"spelled-out tree" to "shape reference + operands" -- the shape moves
from the traffic into the residence, so an arriving or stored
instruction's shape is known by ID, not discovered by walking.

Constraints that keep this model-pure:
- slots are VALUE holes only; a demand node stays outside the shape, in
  the instruction, as an ordinary operand subtree (no computed refs);
- a shape body contains no demand nodes and fires nothing (pure
  transform, phase-3 admission rules);
- instances are rewritten IN PLACE at the same reference, because other
  instructions hold literal demands on these files -- fresh refs would
  cascade through every demander (FRICTION.md #23). Render-identity is
  verified per file before the pass counts as done.

Idempotent: rewritten instances have a promoted shape at the root and
are excluded from mining, and re-admission is keyed on the same
signature groups, so a second run admits and rewrites nothing.

Like am/condense.py, this pass -- and only this pass -- walks stored
instruction bytes structurally (offline, the chartered exception). Run
it with no router serving the same world.
"""

import argparse
import os
import sys
import time

from .instruction import COMP, DEMAND, ERR, LIT, Refusal, _rv, _uv, comp, demand, lit
from .router import Ctx
from .structures import (EMIT_DISK, HOLE_BASE, PROMOTED_BASE, load_promoted,
                         make_registry)



def _scan(buf, off, slots):
    """Walk one node; append (kind, payload, raw_node_bytes) per leaf in
    preorder to slots; return (signature, end)."""
    tag = buf[off]
    if tag == LIT:
        n, o = _rv(buf, off + 1)
        slots.append(("L", bytes(buf[o:o + n]), bytes(buf[off:o + n])))
        return "L", o + n
    if tag == DEMAND:
        n, o = _rv(buf, off + 1)
        slots.append(("D", None, bytes(buf[off:o + n])))
        return "D", o + n
    if tag == COMP:
        sid, o = _rv(buf, off + 1)
        argc, o = _rv(buf, o)
        parts = []
        for _ in range(argc):
            s, o = _scan(buf, o, slots)
            parts.append(s)
        return "C%d(%s)" % (sid, ",".join(parts)), o
    if tag == ERR:
        n, o = _rv(buf, off + 1)
        slots.append(("E", bytes(buf[o:o + n]), bytes(buf[off:o + n])))
        return "E", o + n
    raise ValueError("bad tag %d" % tag)


def _root_sid(buf):
    if buf[:1] != bytes([COMP]):
        return None
    sid, _ = _rv(buf, 1)
    return sid


def _build_body(buf, off, is_hole, counter):
    """Re-emit the tree with varying leaves replaced by operand slots."""
    tag = buf[off]
    if tag in (LIT, DEMAND, ERR):
        n, o = _rv(buf, off + 1)
        idx = counter[0]
        counter[0] += 1
        if is_hole[idx]:
            hole = comp(HOLE_BASE + sum(is_hole[:idx]))
            return hole, o + n
        return bytes(buf[off:o + n]), o + n
    if tag == COMP:
        sid, o = _rv(buf, off + 1)
        argc, o = _rv(buf, o)
        children = []
        for _ in range(argc):
            child, o = _build_body(buf, o, is_hole, counter)
            children.append(child)
        return (bytes([COMP]) + _uv(sid) + _uv(argc) + b"".join(children)), o
    raise ValueError("bad tag %d" % tag)


def run(world_root, log_path=None):
    root = os.path.realpath(world_root)
    registry = load_promoted(root, dict(make_registry(root)))
    next_sid = PROMOTED_BASE
    while next_sid in registry:
        next_sid += 1

    def fire_emit(ref, content):
        ctx = Ctx(registry, root, _NoStats())
        from .instruction import fire
        fire(comp(EMIT_DISK, lit(ref), lit(content)), 0, ctx)

    def render(ref):
        ctx = Ctx(registry, root, _NoStats())
        from .instruction import fire
        value, _ = fire(demand(ref), 0, ctx)
        return value

    # scan every stored instruction file (skip lib/ -- those ARE the shapes)
    groups = {}
    for dirpath, dirs, names in os.walk(root):
        if os.path.basename(dirpath) == "lib" and dirpath == os.path.join(root, "lib"):
            continue
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            ref = os.path.relpath(path, root)
            if ref.startswith("lib" + os.sep):
                continue
            with open(path, "rb") as f:
                buf = f.read()
            rs = _root_sid(buf)
            if rs is None or rs >= PROMOTED_BASE:
                continue   # bare literals/demands, or already shape-rooted
            slots = []
            try:
                sig, end = _scan(buf, 0, slots)
            except ValueError:
                continue
            if end != len(buf) or not any(k == "L" for k, _, _ in slots):
                continue
            groups.setdefault(sig, []).append((ref, buf, slots))

    admitted = []
    rewritten = 0
    for sig, instances in sorted(groups.items()):
        if len(instances) < 3:
            continue
        nslots = len(instances[0][2])
        # constant where every instance's literal payload is identical
        is_hole = []
        folded = 0
        for i in range(nslots):
            kind = instances[0][2][i][0]
            if kind != "L":
                is_hole.append(True)
                continue
            payloads = {inst[2][i][1] for inst in instances}
            if len(payloads) == 1:
                is_hole.append(False)
                folded += len(instances[0][2][i][1])
            else:
                is_hole.append(True)
        if not any(is_hole):
            continue
        # admission: the shape must pay for itself — projected stored
        # bytes saved across instances, net of the resident body, > 0
        body, _ = _build_body(instances[0][1], 0, is_hole, [0])
        projected = 0
        for ref, buf, slots in instances:
            operands = [raw for hole, (k, p, raw) in zip(is_hole, slots) if hole]
            new_len = len(bytes([COMP]) + _uv(next_sid) + _uv(len(operands))) \
                + sum(len(r) for r in operands)
            projected += len(buf) - new_len
        if projected - len(body) <= 0:
            continue
        # verify renders, promote, rewrite in place, verify again
        before = {ref: render(ref) for ref, _, _ in instances}
        sid = next_sid
        next_sid += 1
        fire_emit("lib/%d" % sid, body)
        registry[sid] = None   # placeholder; reload below
        load_promoted(root, registry)
        old_bytes = new_bytes = 0
        for ref, buf, slots in instances:
            operands = [raw for hole, (k, p, raw) in zip(is_hole, slots) if hole]
            new = bytes([COMP]) + _uv(sid) + _uv(len(operands)) + b"".join(operands)
            fire_emit(ref, new)
            rewritten += 1
            old_bytes += len(buf)
            new_bytes += len(new)
        for ref in before:
            if render(ref) != before[ref]:
                raise RuntimeError("render changed for %s -- shape %d bad"
                                   % (ref, sid))
        admitted.append(dict(
            sid=sid, sig=sig, instances=len(instances),
            holes=sum(is_hole), folded=folded,
            saved=old_bytes - new_bytes - len(body),
            examples=[ref for ref, _, _ in instances[:3]]))

    if log_path and admitted:
        with open(log_path, "a") as f:
            f.write("\n### Shape-condensation pass admissions (%s)\n\n"
                    % time.strftime("%Y-%m-%d"))
            f.write("| sid | shape | instances | operand slots | folded const bytes/inst | example files |\n")
            f.write("|---|---|---|---|---|---|\n")
            for a in admitted:
                f.write("| %d | `%s` | %d | %d | %d | %s |\n"
                        % (a["sid"], a["sig"], a["instances"], a["holes"],
                           a["folded"], ", ".join(a["examples"])))
    return dict(admitted=admitted, rewritten=rewritten)


class _NoStats:
    def instruction(self, source, buf):
        pass

    def firing(self, nodes, outcome):
        pass


def main():
    ap = argparse.ArgumentParser(description="Offline shape-condensation pass")
    ap.add_argument("--world", default="world")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    r = run(args.world, args.log)
    print("shapes admitted: %d, instances rewritten: %d"
          % (len(r["admitted"]), r["rewritten"]))
    for a in r["admitted"]:
        print("  sid=%d %s ×%d, %d slots, %dB constants folded"
              % (a["sid"], a["sig"], a["instances"], a["holes"], a["folded"]))
    print("render verification: OK")


if __name__ == "__main__":
    main()
