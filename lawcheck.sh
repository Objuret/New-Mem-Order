#!/usr/bin/env bash
# lawcheck - mechanical enforcement of BUILD-LAW.md.
#
# Exit 0 only if every gate passes. Every measurement harness that
# reports anything "of the machine" MUST run this first and refuse
# (nonzero exit, no output tables) on failure. No agent judgment is
# consulted: these are greps and structural asserts, and the lint
# lists are expected to GROW whenever a new scaffolding species is
# discovered - append, never trim, and log the addition in git.
#
# The layout contract this checker enforces (v1+):
#   engine/fabric/   - the machine proper. What MACHINE.md describes,
#                      and nothing else, lives here.
#   engine/edge/     - every silicon compromise, conversion, and
#                      emulation shim. Named in engine/EMULATION.md
#                      with its measured cost.
#   engine/harness/  - measurement harnesses (two-ledger output).
#   engine/EMULATION.md - the register of compromises.
#
# A v0-style monolith (engine sources outside fabric/+edge/) fails G6
# outright: the separation must be structural, not aspirational.
set -u
cd "$(dirname "$0")"

FABRIC_DIR=engine/fabric
EDGE_DIR=engine/edge
HARNESS_DIR=engine/harness
EMU_MD=engine/EMULATION.md

fail=0
note() { printf '%s\n' "$*"; }
gate() { # gate <name> <0|1 pass> <detail>
    if [ "$2" -eq 0 ]; then
        note "PASS  $1"
    else
        note "FAIL  $1 - $3"
        fail=1
    fi
}

fabric_files=$(find "$FABRIC_DIR" -name '*.[ch]' 2>/dev/null || true)
edge_files=$(find "$EDGE_DIR" -name '*.[ch]' 2>/dev/null || true)
harness_files=$(find "$HARNESS_DIR" -name '*.[ch]' 2>/dev/null || true)
stray=$(find engine -maxdepth 1 -name '*.[ch]' 2>/dev/null || true)

# helper: grep fabric for banned tokens; prints matches
lint_fabric() {
    [ -n "$fabric_files" ] || return 0
    grep -nEw "$1" $fabric_files 2>/dev/null
}
# helper: a required marker must appear in harness sources
marker() {
    [ -n "$harness_files" ] && grep -lq "$1" $harness_files 2>/dev/null
}

if [ -z "$fabric_files" ]; then
    note "fabric absent: $FABRIC_DIR does not exist or is empty."
    note "An ungated build (v0 monolith or nothing) fails every gate."
    gate G1 1 "no fabric to check"
    gate G2 1 "no fabric to check"
    gate G3 1 "no fabric to check"
    gate G4 1 "no fabric to check"
    gate G5 1 "no edge entropy accounting to check"
    gate G6 1 "fabric/edge separation does not exist"
    note ""
    note "LAWCHECK: FAIL - Law 0 in force. No number produced by what"
    note "exists here may be reported as a result of the machine."
    exit 1
fi

# ---- G1: no manager -------------------------------------------------
# Administration has names. If one appears in fabric, a manager is
# growing there. Grow this list; never trim it.
G1_BAN='queue|buffer|callback|sink|sched|scheduler|drain|batch|backlog|pending|dispatch_table_walk'
m=$(lint_fabric "$G1_BAN")
d="banned manager constructs in fabric:"$'\n'"$m"
[ -z "$m" ] && marker LAW_G1_DISPATCH_BUDGET \
    && gate G1 0 "" \
    || { [ -z "$m" ] && d="harness lacks LAW_G1_DISPATCH_BUDGET assert (instructions from edge handoff to road entry <= stated constant)"; gate G1 1 "$d"; }

# ---- G2: per-arrival, order untouched -------------------------------
G2_BAN='seq|sequence|provenance|reorder|resort|sort_by|arrival_index'
m=$(lint_fabric "$G2_BAN")
d="order-reconstruction constructs in fabric:"$'\n'"$m"
[ -z "$m" ] && marker LAW_G2_EXIT_BYTES \
    && gate G2 0 "" \
    || { [ -z "$m" ] && d="harness lacks LAW_G2_EXIT_BYTES assert (exit = name + value, nothing else)"; gate G2 1 "$d"; }

# ---- G3: identity carried, never computed ---------------------------
G3_BAN='hash|mix64|memcmp|strcmp|strncmp|fnv|crc|probe|rehash|bucket'
m=$(lint_fabric "$G3_BAN")
if [ -n "$m" ]; then
    gate G3 1 "identity-computation in fabric (allowed only in edge):"$'\n'"$m"
else
    gate G3 0 ""
fi

# ---- G4: circulation is real ----------------------------------------
G4_BAN='malloc|calloc|realloc|free\(|serialize|marshal'
m=$(lint_fabric "$G4_BAN")
d="allocation/serialization in fabric:"$'\n'"$m"
[ -z "$m" ] && marker LAW_G4_NOALLOC \
    && gate G4 0 "" \
    || { [ -z "$m" ] && d="harness lacks LAW_G4_NOALLOC hook (zero heap allocation in steady-state firing, asserted at runtime)"; gate G4 1 "$d"; }

# ---- G5: the edge preserves shape -----------------------------------
if [ -n "$edge_files" ] \
   && grep -lq 'entropy_before' $edge_files 2>/dev/null \
   && grep -lq 'entropy_after' $edge_files 2>/dev/null; then
    gate G5 0 ""
else
    gate G5 1 "edge must compute and emit entropy_before and entropy_after of every conversion (side by side, always)"
fi

# ---- G6: two ledgers, structurally separated ------------------------
g6=0; g6d=""
if [ -n "$stray" ]; then
    g6=1; g6d="engine sources outside fabric/+edge/: $stray"
fi
if [ -n "$fabric_files" ]; then
    m=$(grep -nE '#include.*(edge/|emulation)' $fabric_files 2>/dev/null)
    if [ -n "$m" ]; then g6=1; g6d="$g6d fabric includes edge:"$'\n'"$m"; fi
fi
if [ ! -f "$EMU_MD" ]; then
    g6=1; g6d="$g6d $EMU_MD missing"
else
    for f in $edge_files; do
        base=$(basename "$f")
        grep -q "$base" "$EMU_MD" \
            || { g6=1; g6d="$g6d edge module $base not named in EMULATION.md;"; }
    done
fi
if ! marker machine_account || ! marker emulation_account; then
    g6=1; g6d="$g6d harness output lacks the two labeled ledgers (machine_account / emulation_account)"
fi
gate G6 $g6 "$g6d"

note ""
if [ $fail -eq 0 ]; then
    note "LAWCHECK: PASS - measurements may be reported under both ledgers."
else
    note "LAWCHECK: FAIL - Law 0 in force. No number produced by this"
    note "build may be reported, recorded, or summarized as the machine's."
fi
exit $fail
