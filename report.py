"""Measurement reporter (brief: Measurements). Instrumentation only --
reads stats.log and the world directory, prints the numbers as markdown.
Directory listing happens here and only here, outside the model.

Run after demo.py: python3 report.py
"""

import os
from collections import Counter

from am.instruction import COMP, DEMAND, ERR, LIT, _rv

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(ROOT, "world")
STATS = os.path.join(ROOT, "stats.log")


def content_bytes(buf, off=0):
    """Bytes of actual content in an instruction: literal payloads and
    demand references. Everything else is grammar overhead."""
    tag = buf[off]
    off += 1
    if tag in (LIT, DEMAND, ERR):
        n, off = _rv(buf, off)
        return n, off + n
    if tag == COMP:
        _, off = _rv(buf, off)
        argc, off = _rv(buf, off)
        total = 0
        for _ in range(argc):
            n, off = content_bytes(buf, off)
            total += n
        return total, off
    raise ValueError("bad tag %d" % tag)


def main():
    firings = []          # (source, signature, size)
    nodes_total = 0
    outcomes = Counter()
    with open(STATS) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if parts[0] == "I":
                firings.append((parts[1], parts[2], int(parts[3])))
            elif parts[0] == "F":
                nodes_total += int(parts[1])
                outcomes[parts[2]] += 1

    sigs = Counter(sig for _, sig, _ in firings)
    print("## Repetition (spec section 6)\n")
    print("- instructions fired (wire arrivals + demanded files): %d" % len(firings))
    print("- distinct composition shapes among them: %d" % len(sigs))
    print("- grammar nodes evaluated across all top-level firings: %d" % nodes_total)
    print("- top-level outcomes: %s" % dict(outcomes))
    print("\n| shape | fired |\n|---|---|")
    for sig, n in sigs.most_common():
        print("| `%s` | %d |" % (sig, n))

    print("\n## Stored-form overhead\n")
    print("| stored instruction | file bytes | content bytes | overhead |")
    print("|---|---|---|---|")
    total_f = total_c = 0
    for dirpath, _, names in sorted(os.walk(WORLD)):
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, WORLD)
            buf = open(path, "rb").read()
            c, end = content_bytes(buf, 0)
            assert end == len(buf), rel
            total_f += len(buf)
            total_c += c
            print("| %s | %d | %d | %d |" % (rel, len(buf), c, len(buf) - c))
    print("| **total** | **%d** | **%d** | **%d** (%.1f%%) |"
          % (total_f, total_c, total_f - total_c,
             100.0 * (total_f - total_c) / total_f if total_f else 0.0))


if __name__ == "__main__":
    main()
