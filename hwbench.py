"""hwbench — the memory-path experiment on YOUR hardware.

Phase 16 proved the mechanism (fewer bytes, fewer misses) under a
cache SIMULATOR because the build container exposes no performance
counters. This is the same experiment packaged to run anywhere:

    git clone <repo> && cd <repo>
    python3 hwbench.py            # needs: a C compiler, python3.
    python3 hwbench.py 1000000    # smaller run for a weak machine

On an Android phone (Termux from F-Droid):
    pkg install python clang git
    git clone <repo> && cd <repo> && python3 hwbench.py
A phone is a BETTER venue than a server for this question: mobile
SoCs are bandwidth- and energy-scarce by construction — exactly the
conditions spec section 0 is about. Counters come from Android's own
simpleperf if the OS allows it; stock builds usually don't until you
run  `adb shell setprop security.perf_harden 0`  from a PC (bytes,
time and the contended verdict work regardless).

What it does, in order:
  1. compiles native/membench.c (portable C, no dependencies);
  2. streams the SAME logical records through the SAME task kernel in
     two representations — conventional contiguous records vs the real
     instruction grammar with an L1-resident template table — and
     asserts the answers identical at every point;
  3. measures bytes moved and wall time, single core, at recurrence
     p = 0/50/90/99 (p=0 is the pre-stated falsification case: there
     the grammar is pure overhead and SHOULD lose);
  4. reads REAL hardware counters (cache misses, instructions,
     cycles) via `perf` or Android's `simpleperf` where available;
  5. saturates every core with the memory-bound kernel — the
     bandwidth-scarce condition where traffic should become time —
     interleaved ABBA so thermal throttling (phones!) cannot favor
     either representation; RAPL package joules where readable;
  6. on a phone running on battery (UNPLUG IT), measures the energy
     tiebreaker directly: sustained all-core runs of each
     representation while sampling the battery's own current x
     voltage, idle baseline subtracted, ABBA order;
  7. prints an honest verdict for THIS machine and writes
     hwbench-results.json.

If perf is installed but blocked on Linux:
    sudo sysctl kernel.perf_event_paranoid=1
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(ROOT, "native", "membench")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4_000_000
PASSES = 3
SWEEP = [0, 50, 90, 99]
EVENTS = ["cache-misses", "cache-references", "instructions", "cycles",
          "cpu-cycles"]                     # cpu-cycles = simpleperf's name


def compiler():
    for c in (os.environ.get("CC"), "cc", "clang", "gcc"):
        if c and shutil.which(c):
            return c
    sys.exit("no C compiler found — install one (Termux: pkg install clang;"
             " Debian/Ubuntu: apt install gcc; mac: xcode-select --install)")


def run(mode, p, n=N, passes=PASSES, kernel=None):
    cmd = [BIN, mode, str(p), str(n), str(passes)]
    if kernel:
        cmd.append(kernel)
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def cpu_name():
    try:                                    # x86 linux
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    for probe in (["getprop", "ro.product.model"],          # android
                  ["getprop", "ro.soc.model"],
                  ["sysctl", "-n", "machdep.cpu.brand_string"]):   # mac
        try:
            out = subprocess.run(probe, capture_output=True,
                                 text=True).stdout.strip()
            if out:
                return out
        except OSError:
            pass
    return "unknown CPU"


def counter_tool():
    """Returns (kind, why-not): kind is 'perf', 'simpleperf', or None."""
    true_bin = shutil.which("true") or "/system/bin/true"
    if shutil.which("perf"):
        r = subprocess.run(["perf", "stat", "-e", "cycles", "--", true_bin],
                           capture_output=True, text=True)
        if r.returncode == 0 and "cycles" in r.stderr:
            return "perf", ""
        return None, ("perf blocked — try: "
                      "sudo sysctl kernel.perf_event_paranoid=1")
    sp = shutil.which("simpleperf") or (
        "/system/bin/simpleperf" if os.path.exists("/system/bin/simpleperf")
        else None)
    if sp:
        r = subprocess.run([sp, "stat", "-e", "cpu-cycles", true_bin],
                           capture_output=True, text=True)
        if r.returncode == 0 and "cpu-cycles" in r.stdout + r.stderr:
            return sp, ""
        return None, ("simpleperf blocked — from a PC run: "
                      "adb shell setprop security.perf_harden 0")
    return None, "no perf/simpleperf (linux-tools package, or Android)"


def counters(tool, mode, p):
    """Real PMU counters over one pass of the heavy kernel."""
    out = {}
    if tool == "perf":
        cmd = ["perf", "stat", "-x", ",", "-e",
               "cache-misses,cache-references,instructions,cycles", "--",
               BIN, mode, str(p), str(N), "1"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        for line in r.stderr.splitlines():
            parts = line.split(",")
            if len(parts) >= 3:
                ev = parts[2].split(":")[0]   # perf may suffix ':u' non-root
                if ev in EVENTS:
                    try:
                        out[ev] = int(float(parts[0]))
                    except ValueError:
                        pass                  # <not supported>/<not counted>
    else:                                     # simpleperf path
        cmd = [tool, "stat", "-e",
               "cache-misses,cache-references,instructions,cpu-cycles",
               BIN, mode, str(p), str(N), "1"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        for line in (r.stdout + r.stderr).splitlines():
            toks = line.split()
            if len(toks) >= 2 and toks[1].split(":")[0] in EVENTS:
                try:
                    out[toks[1].split(":")[0]] = \
                        int(toks[0].replace(",", ""))
                except ValueError:
                    pass
    if "cycles" not in out and "cpu-cycles" in out:
        out["cycles"] = out.pop("cpu-cycles")
    return out


def rapl_paths():
    """Readable RAPL package domains (intel-rapl:0, intel-rapl:1, ...)."""
    base = "/sys/class/powercap"
    found = []
    try:                    # android: dir visible but listing denied
        entries = sorted(os.listdir(base)) if os.path.isdir(base) else []
    except OSError:
        return []
    for d in entries:
        if d.count(":") != 1:                 # packages only, not subzones
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


NOMINAL_V = 3.85     # used only when the battery reports current, not voltage


def battery_state():
    """(kind, base, status, interval) for whatever battery telemetry this
    machine allows; kind None if none. Measurements mean something only
    when status is Discharging."""
    base = "/sys/class/power_supply"
    try:
        cands = [os.path.join(base, d) for d in sorted(os.listdir(base))]
    except OSError:                       # android: listing often denied
        cands = [os.path.join(base, n)
                 for n in ("battery", "BAT0", "BAT1", "bms")]
    for b in cands:
        try:
            abs(int(open(b + "/current_now").read()))
            status = open(b + "/status").read().strip()
        except (OSError, ValueError):
            continue
        try:
            int(open(b + "/voltage_now").read())
            return "sysfs", b, status, 0.2
        except (OSError, ValueError):
            return "sysfs-novolt", b, status, 0.2
    # android denies raw sysfs to apps; the Termux:API bridge still works
    if shutil.which("termux-battery-status"):
        try:
            j = json.loads(subprocess.run(
                ["termux-battery-status"], capture_output=True,
                text=True, timeout=15).stdout)
            if "current" in j and j.get("status"):
                return "termux", None, j["status"].capitalize(), 1.0
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return None, None, None, None


def make_power_reader(kind, base):
    """Returns a zero-arg callable -> instantaneous watts (or None)."""
    if kind == "sysfs":
        def rd():
            i = abs(int(open(base + "/current_now").read()))
            v = int(open(base + "/voltage_now").read())
            return i / 1e6 * v / 1e6          # uA x uV -> W
    elif kind == "sysfs-novolt":
        def rd():
            i = abs(int(open(base + "/current_now").read()))
            return i / 1e6 * NOMINAL_V
    else:                                     # termux-battery-status
        def rd():
            j = json.loads(subprocess.run(
                ["termux-battery-status"], capture_output=True,
                text=True, timeout=15).stdout)
            i = abs(float(j["current"]))
            if i < 20000:                     # some devices report mA
                i *= 1000
            return i / 1e6 * NOMINAL_V
    return rd


class PowerSampler(threading.Thread):
    """Samples battery power -> mean watts over the sampled window."""

    def __init__(self, reader, interval):
        super().__init__(daemon=True)
        self.reader = reader
        self.interval = interval
        self.samples = []
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                w = self.reader()
                if w is not None:
                    self.samples.append(w)
            except Exception:
                pass
            self._stop.wait(self.interval)

    def watts(self):
        self._stop.set()
        self.join()
        return sum(self.samples) / len(self.samples) if self.samples else None


def watts_during(reader, interval, fn, min_seconds):
    """Mean battery watts while fn() runs repeatedly for >= min_seconds.
    Returns (watts, work_done, dt)."""
    s = PowerSampler(reader, interval)
    s.start()
    t0 = time.monotonic()
    work = 0
    while time.monotonic() - t0 < min_seconds:
        work += fn()
    dt = time.monotonic() - t0
    return s.watts(), work, dt


def battery_energy(p, streams, reader, interval, block_s=15):
    """The phone's own energy verdict: sustained all-core runs of each
    representation while the battery reports drain; idle baseline
    subtracted; ABBA (raw am am raw) so thermal/battery drift cannot
    favor either side. Includes stream generation, which is itself
    bytes-proportional work — labeled, not hidden."""

    def block(mode):
        def one():
            procs = [subprocess.Popen(
                [BIN, mode, str(p), str(N), "10", "light"],
                stdout=subprocess.PIPE, text=True) for _ in range(streams)]
            for pr in procs:
                pr.communicate()
            return N * 10 * streams
        return watts_during(reader, interval, one, block_s)

    idle_w, _, _ = watts_during(reader, interval,
                                lambda: time.sleep(0.5) or 0, 8)
    if idle_w is None:
        return {}
    runs = [(m,) + block(m) for m in ("raw", "am", "am", "raw")]
    out = {}
    for mode, pair in (("raw", (runs[0], runs[3])), ("am", (runs[1], runs[2]))):
        # joules per billion records, above idle, best (coolest) block
        js = [(w - idle_w) * dt / (work / 1e9)
              for _, w, work, dt in pair if w is not None and work]
        if js:
            out[mode] = round(min(js), 1)
    out["idle_w"] = round(idle_w, 2) if idle_w is not None else None
    return out


def contended_once(mode, p, streams, rapl):
    e0 = rapl_read(rapl) if rapl else None
    procs = [subprocess.Popen(
        [BIN, mode, str(p), str(N), "10", "light"],
        stdout=subprocess.PIPE, text=True) for _ in range(streams)]
    secs = []
    for pr in procs:
        out, _ = pr.communicate()
        secs.append(json.loads(out)["seconds"])
    e1 = rapl_read(rapl) if rapl else None
    r = dict(seconds=sum(secs) / len(secs))
    if rapl and e1 >= e0:                     # skip on counter wraparound
        r["joules"] = (e1 - e0) / 1e6
    return r


def contended(p, streams, rapl):
    """Every core runs the memory-bound kernel at once; kernel-only
    seconds from inside each process. ABBA order (raw am am raw), best
    of the two runs per mode, so thermal drift on phones cannot favor
    whichever representation happens to run cooler-first."""
    seq = [contended_once(m, p, streams, rapl)
           for m in ("raw", "am", "am", "raw")]
    res = {}
    for mode, a, b in (("raw", seq[0], seq[3]), ("am", seq[1], seq[2])):
        best = a if a["seconds"] <= b["seconds"] else b
        res[mode] = best
    return res


def main():
    cc = compiler()
    subprocess.run([cc, "-O2", "-o", BIN,
                    os.path.join(ROOT, "native", "membench.c")], check=True)
    cores = os.cpu_count() or 1
    tool, why = counter_tool()
    rapl = rapl_paths()
    bkind, bbase, batt_status, binterval = battery_state()
    on_android = os.path.exists("/system/bin")
    print("machine: %s, %d cores" % (cpu_name(), cores))
    if N < 2_000_000:
        print("CAUTION: n=%d is small — per-pass times get noise-dominated;"
              " trust the default 4M for the verdict" % N)
    energy_src = ("RAPL" if rapl else
                  "battery via %s (%s)" % (bkind, batt_status) if bkind else
                  "unavailable — install the Termux:API app (F-Droid) and "
                  "`pkg install termux-api`" if on_android else "unavailable")
    print("counters: %s   energy: %s\n"
          % ("real PMU via %s" % ("perf" if tool == "perf" else "simpleperf")
             if tool else "unavailable (%s)" % why, energy_src))

    rows = []
    for p in SWEEP:
        raw = run("raw", p)
        am = run("am", p)
        assert (raw["sum"], raw["checksum"]) == (am["sum"], am["checksum"]), \
            "representations disagree at p=%d" % p
        row = dict(p=p, raw_mb=round(raw["stream_bytes"] / 1e6, 1),
                   am_mb=round(am["stream_bytes"] / 1e6, 1),
                   raw_s=raw["seconds"], am_s=am["seconds"])
        if tool:
            rc, ac = counters(tool, "raw", p), counters(tool, "am", p)
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

    print("\nall %d cores, memory-bound kernel (the bandwidth-scarce case), "
          "ABBA-interleaved:" % cores)
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

    # ---- the energy tiebreaker (battery-powered machines) ------------------
    energy = {}
    if not rapl and bkind:
        if (batt_status or "").lower() == "discharging":
            print("\nbattery energy, all cores, memory-bound kernel "
                  "(don't touch the phone; ~3 min):")
            reader = make_power_reader(bkind, bbase)
            for p in (0, 99):
                energy[p] = battery_energy(p, cores, reader, binterval)
                e = energy[p]
                if "raw" in e and "am" in e:
                    print("p=%3d%%  J/Grec above idle (%.2f W): "
                          "raw %.1f   am %.1f   (%.2fx)"
                          % (p, e["idle_w"], e["raw"], e["am"],
                             e["am"] / e["raw"]))
                else:
                    print("p=%3d%%  battery samples unusable" % p)
        else:
            print("\nbattery energy: SKIPPED — phone is %s. Unplug it and "
                  "rerun for the energy verdict." % batt_status.lower())

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
    if 99 in energy and "raw" in energy[99] and "am" in energy[99]:
        print("  energy (battery):   %.2fx above idle"
              % (energy[99]["am"] / energy[99]["raw"]))
    if tc < 0.90 or t1 < 0.90:
        print("  -> traffic converts to TIME here: this machine is "
              "bandwidth-bound enough that moving fewer bytes is faster."
              + ("" if tc < 0.90 else " (even on a single core)"))
    elif tc < 1.05:
        print("  -> too close to call on this machine (within run noise): "
              "the memory system is near the tipping point but the "
              "prefetcher still mostly keeps up. Joules, if shown above, "
              "are the tiebreaker.")
    else:
        print("  -> no time conversion on this machine: the prefetcher "
              "hides the raw stream's cost. The bytes/miss win is real "
              "but buys time only where bandwidth or energy is scarce.")

    with open(os.path.join(ROOT, "hwbench-results.json"), "w") as f:
        json.dump(dict(cpu=cpu_name(), cores=cores, n=N,
                       counters=tool or "none", rows=rows,
                       contended={str(k): v for k, v in cont.items()},
                       battery_energy={str(k): v for k, v in energy.items()}),
                  f, indent=1)
    print("\n(answers asserted identical at every point; "
          "results: hwbench-results.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
