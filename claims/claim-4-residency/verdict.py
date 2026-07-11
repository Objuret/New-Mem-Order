#!/usr/bin/env python3
"""Coded conditions for claim 4 (MACHINE.md).

Claim: "Arrangement-residency fits. Resident bytes per shape; a
~1000-shape road network fits hot in L2 where equivalent branchy code
plus predictor state cannot."

Measurable halves, both from real artifacts:
  road network = engine's self-accounted resident_network_bytes
                 (arrangements + paved plans) + the engine's .text
                 (vocabulary + firing machinery, shared by all roads).
  branchy      = .text bytes of the 1024-shape switch dispatcher
                 compiled -O2 (bodies inlined).

Unmeasurable half: predictor/BTB state is hardware-internal; no
software reads it. The claim's "cannot fit" clause therefore CANNOT be
scored PASS/FAIL here; it is recorded as unmeasured.

  PASS:        network+engine_text <= L2  AND  network+engine_text <
               branchy_text (the network is smaller than the branchy
               code alone, before predictor state is even counted).
  FALSIFIED:   network+engine_text > L2 (the residency premise fails).
  INCONCLUSIVE: fits L2 but is not smaller than branchy .text.
"""
import json
import sys


def main():
    engine_json, branchy_text, engine_text, l2, out_path = (
        sys.argv[1], int(sys.argv[2]), int(sys.argv[3]),
        int(sys.argv[4]), sys.argv[5])
    e = json.load(open(engine_json))
    network = e["network_bytes"] + engine_text
    fits = network <= l2
    smaller = network < branchy_text

    if not fits:
        verdict = "FALSIFIED"
        reason = f"road network ({network}B) does not fit L2 ({l2}B)"
    elif smaller:
        verdict = "PASS"
        reason = (f"{e['roads']}-shape network resident in "
                  f"{network} bytes ({e['bytes_per_road']:.0f}B/road + "
                  f"{engine_text}B shared machinery) = "
                  f"{network / l2 * 100:.1f}% of L2; smaller than the "
                  f"equivalent branchy dispatcher's code alone "
                  f"({branchy_text}B) before predictor state is counted")
    else:
        verdict = "INCONCLUSIVE"
        reason = (f"fits L2 ({network}B) but not smaller than branchy "
                  f".text ({branchy_text}B)")

    result = {
        "claim": "4 - arrangement-residency fits",
        "verdict": verdict,
        "reason": reason,
        "unmeasured": "predictor/BTB state (hardware-internal; the "
                      "claim's 'cannot fit' clause is not scored)",
        "network_bytes": e["network_bytes"],
        "engine_text_bytes": engine_text,
        "bytes_per_road": e["bytes_per_road"],
        "branchy_text_bytes": branchy_text,
        "l2_bytes": l2,
        "state_bytes_note": {
            "value": e["state_bytes"],
            "meaning": "queues + register files + jit landing zones - "
                       "working state, sized by batch config, not part "
                       "of the road network",
        },
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nCLAIM 4 VERDICT: {verdict}")
    print(reason)


if __name__ == "__main__":
    main()
