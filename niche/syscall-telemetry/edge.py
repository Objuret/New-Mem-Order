#!/usr/bin/env python3
"""The edge (MACHINE.md: "converts the outside world's bytes exactly
once at the edge"). strace text -> binary tagged records:
    record = (tag u32, pad u32, val u64)
tag  = dense id of the syscall name, assigned in first-appearance order
val  = the syscall's return value as u64 (two's complement)

Also reports what reality says about this traffic - tag entropy and
value recurrence - because those numbers decide whether the machine's
regime exists in the wild (the kill-condition probe).
"""
import glob
import json
import math
import re
import struct
import sys
from collections import Counter

CALL = re.compile(r"^(?:\d+\s+)?(\w+)\(.*\)\s+=\s+(-?\d+|\?)")
RESUMED = re.compile(r"^(?:\d+\s+)?<\.\.\.\s+(\w+)\s+resumed.*\)\s+=\s+(-?\d+|\?)")


def main():
    out_bin, out_stats = sys.argv[1], sys.argv[2]
    tags, records = {}, []
    per_file = {}
    for path in sorted(glob.glob("traces/*.txt")):
        n0 = len(records)
        for line in open(path, errors="replace"):
            m = CALL.match(line) or RESUMED.match(line)
            if not m or m.group(2) == "?":
                continue
            name, ret = m.group(1), int(m.group(2))
            tag = tags.setdefault(name, len(tags))
            records.append((tag, ret & 0xFFFFFFFFFFFFFFFF))
        per_file[path] = len(records) - n0

    with open(out_bin, "wb") as f:
        for tag, val in records:
            f.write(struct.pack("<IIQ", tag, 0, val))

    tag_counts = Counter(t for t, _ in records)
    total = len(records)
    entropy = -sum((c / total) * math.log2(c / total)
                   for c in tag_counts.values())
    pair_counts = Counter(records)
    distinct_pairs = len(pair_counts)
    recurrence = 1.0 - distinct_pairs / total

    names = sorted(tags, key=tags.get)
    stats = {
        "events": total,
        "distinct_syscalls": len(tags),
        "tag_entropy_bits": round(entropy, 3),
        "max_entropy_bits": round(math.log2(len(tags)), 3),
        "value_recurrence": round(recurrence, 4),
        "distinct_tag_value_pairs": distinct_pairs,
        "per_trace_events": per_file,
        "top10": [{"syscall": names[t], "count": c, "share": round(c / total, 4)}
                  for t, c in tag_counts.most_common(10)],
        "tag_names": names,
    }
    with open(out_stats, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"{total} events, {len(tags)} syscalls, "
          f"entropy {entropy:.2f}/{math.log2(len(tags)):.2f} bits, "
          f"value recurrence {recurrence:.1%}")


if __name__ == "__main__":
    main()
