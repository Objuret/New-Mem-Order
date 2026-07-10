"""hwbench — the memory-path experiment on YOUR hardware.

Phase 16 proved the mechanism (fewer bytes, fewer misses) under a
cache SIMULATOR because the build container exposes no performance
counters. This is the same experiment packaged to run anywhere:

    git clone <repo> && cd <repo>
    python3 hwbench.py            # needs: cc, python3. That's all.
    python3 hwbench.py 1000000    # smaller run for a weak machine

What it does, in order:
  1. compiles native/membench.c (portable C, no dependencies);
  2. streams the SAME logical records through the SAME task kernel in
     two representations — conventional contiguous records vs the real
     instruction grammar with an L1-resident template table — and
     asserts the answers identical at every point;
  3. measures bytes moved and wall time, single core, at recurrence
     p = 0/50/90/99 (p=0 is the pre-stated falsification case: there
     the grammar is pure overhead and SHOULD lose);
  4. if `perf` works on this machine, reads the REAL hardware
     counters (cache misses, instructions, cycles) instead of a
     simulator;
  5. saturates every core with the memory-bound kernel — the
     bandwidth-scarce condition where traffic should become time —
     and, if RAPL energy counters are readable, joules too;
  6. prints an honest verdict for THIS machine and writes
     hwbench-results.json.

Linux gives the full picture (perf + RAPL). macOS/WSL still give
bytes + time + the contended run — the counters just stay blank.
If perf is installed but blocked, run:
    sudo sysctl kernel.perf_event_paranoid=1
or rerun this under sudo.
"""

import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(ROOT, "native", "membench")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4_000_000
PASSES = 3
SWEEP = [0, 50, 90, 99]
EVENTS = ["cache-misses", "cache-references", "instructions", "cycles"]


def run(mode, p, n=N, passes=PASSES, kernel=None):
    cmd = [BIN, mode, str(p), str(n), str(passes)]
    if kernel:
        cmd.append(kernel)
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def cpu_name():
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    try:
        return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                              capture_output=True, text=True).stdout.strip() \
            or "unknown CPU"
    except OSError:
        return "unknown CPU"


def perf_works():
    if not shutil.which("perf"):
        return False, "perf not installed (linux-tools / linux-perf package)"
    r = subprocess.run(["perf", "stat", "-e", "cycles", "--", "true"],
                       capture_output=True, text=True)
    if r.returncode != 0 or "cycles" not in r.stderr:
        return False, ("perf blocked — try: "
                       "sudo sysctl kernel.perf_event_paranoid=1")
    return True, ""


def perf_count(mode, p):
    """Real PMU counters over one pass of the heavy kernel."""
    cmd = ["perf", "stat", "-x", ",", "-e", ",".join(EVENTS), "--",
           BIN, mode, str(p), str(N), "1"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = {}
    for line in r.stderr.splitlines():
        parts = line.split(",")
        if len(parts) >= 3:
            ev = parts[2].split(":")[0]    # perf may suffix ':u' non-root
            if ev in EVENTS:
                try:
                    out[ev] = int(float(parts[0]))
                except ValueError:
                    pass                   # <not supported>/<not counted>
    return out


def rapl_paths():
    """Readable RAPL package domains (intel-rapl:0, intel-rapl:1, ...)."""
    base = "/sys/class/powercap"
    found = []
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            if d.count(":") != 1:          # packages only, not subzones
                continue
            f = os.path.join(base, d, "energy_uj")
            try:
                int(open(f).read())
                found.append(os.path.join(base, d))
            except (OSError, ValueError):
                pass
    return found


def rapl_read(paths):
    return sum(int(open(os.path.join(p, "energy_uj")).read()) for p in paths)


def contended(p, streams, rapl):
    """Every core runs the memory-bound kernel at once; kernel-only
    seconds reported from inside each process. Joules if readable."""
    res = {}
    for mode in ("raw", "am"):
        e0 = rapl_read(rapl) if rapl else None
        procs = [subprocess.Popen(
            [BIN, mode, str(p), str(N), "10", "light"],
            stdout=subprocess.PIPE, text=True) for _ in range(streams)]
        secs = []
        for pr in procs:
            out, _ = pr.communicate()
            secs.append(json.loads(out)["seconds"])
        e1 = rapl_read(rapl) if rapl else None
        res[mode] = dict(seconds=sum(secs) / len(secs))
        if rapl and e1 >= e0:              # skip on counter wraparound
            res[mode]["joules"] = (e1 - e0) / 1e6
    return res


def main():
    subprocess.run(["cc", "-O2", "-o", BIN,
                    os.path.join(ROOT, "native", "membench.c")], check=True)
    cores = os.cpu_count() or 1
    pmu, why = perf_works()
    rapl = rapl_paths()
    print("machine: %s, %d cores" % (cpu_name(), cores))
    if N < 2_000_000:
        print("CAUTION: n=%d is small — per-pass times get noise-dominated;"
              " trust the default 4M for the verdict" % N)
    print("counters: %s   energy: %s\n"
          % ("real PMU via perf" if pmu else "unavailable (%s)" % why,
             "RAPL" if rapl else "unavailable"))

    rows = []
    for p in SWEEP:
        raw = run("raw", p)
        am = run("am", p)
        assert (raw["sum"], raw["checksum"]) == (am["sum"], am["checksum"]), \
            "representations disagree at p=%d" % p
        row = dict(p=p, raw_mb=round(raw["stream_bytes"] / 1e6, 1),
                   am_mb=round(am["stream_bytes"] / 1e6, 1),
                   raw_s=raw["seconds"], am_s=am["seconds"])
        if pmu:
            rc, ac = perf_count("raw", p), perf_count("am", p)
            if rc.get("cache-misses") and ac.get("cache-misses") is not None:
                row["raw_miss"] = rc["cache-misses"]
                row["am_miss"] = ac["cache-misses"]
        rows.append(row)
        miss = ("   misses: %.2fx" % (row["am_miss"] / row["raw_miss"])
                if row.get("raw_miss") else "")
        print("p=%3d%%  bytes: %6.1f -> %6.1f MB (%.2fx)   "
              "time 1-core: %.3f -> %.3f s (%.2fx)%s"
              % (p, row["raw_mb"], row["am_mb"], row["am_mb"] / row["raw_mb"],
                 row["raw_s"], row["am_s"], row["am_s"] / row["raw_s"], miss))

    print("\nall %d cores, memory-bound kernel (the bandwidth-scarce case):"
          % cores)
    cont = {}
    for p in (0, 99):
        cont[p] = contended(p, cores, rapl)
        r, a = cont[p]["raw"], cont[p]["am"]
        ej = ("   joules: %.1f -> %.1f (%.2fx)"
              % (r["joules"], a["joules"], a["joules"] / r["joules"])
              if "joules" in r and "joules" in a else "")
        print("p=%3d%%  time: %.3f -> %.3f s (%.2fx)%s"
              % (p, r["seconds"], a["seconds"],
                 a["seconds"] / r["seconds"], ej))

    # ---- the verdict, for THIS machine ------------------------------------
    hi = rows[-1]
    t1 = hi["am_s"] / hi["raw_s"]
    tc = cont[99]["am"]["seconds"] / cont[99]["raw"]["seconds"]
    print("\nverdict for this machine at p=99 (high recurrence):")
    print("  bytes moved:        %.2fx (deterministic — the model's floor)"
          % (hi["am_mb"] / hi["raw_mb"]))
    if hi.get("raw_miss"):
        print("  cache misses (PMU): %.2fx" % (hi["am_miss"] / hi["raw_miss"]))
    print("  time, 1 core:       %.2fx" % t1)
    print("  time, all cores:    %.2fx  <- the number that decides it" % tc)
    if tc < 0.95:
        print("  -> traffic converts to TIME here: this machine is "
              "bandwidth-bound enough that moving fewer bytes is faster.")
    elif t1 < 0.95:
        print("  -> converts even on a single core here.")
    else:
        print("  -> no time conversion on this machine: the prefetcher "
              "hides the raw stream's cost. The bytes/miss win is real "
              "but buys time only where bandwidth or energy is scarce.")

    with open(os.path.join(ROOT, "hwbench-results.json"), "w") as f:
        json.dump(dict(cpu=cpu_name(), cores=cores, n=N, pmu=pmu,
                       rows=rows,
                       contended={str(k): v for k, v in cont.items()}),
                  f, indent=1)
    print("\n(answers asserted identical at every point; "
          "results: hwbench-results.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
