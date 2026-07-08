# Activation Model — Session Orientation

## Read first, every session
1. `activation-model.md` — the spec. It is law. Code conforms to it; it changes only by Jocke's explicit acceptance. On any conflict between files, the spec wins.
2. `build-brief.md` — process, build order, measurements, hard rules.

## Current state
- Phase 1 (message board) built, measured, and **accepted by Jocke as-is** (2026-07-08); spec unchanged. Grammar + runtime in `am/` (byte-walking instruction grammar, single router, client), workload as instructions, end-to-end demo with restart survival (`demo.py`), measurements (`report.py`, `REPORT.md`).
- Phase 2 (computation pressure: find/count/newest queries over phase-1 data) built and measured same day. Library grew 2 → 5 structures (`select`, `tally`, `last` — all pure, conditions as values); grammar unchanged at 4 nodes. No falsification event; growth curve in `REPORT.md`.
- Phase 3 (the layer, per `PHASE3-LAYER.md` — read it before touching phase-3 code) complete same day: real FUSE mount (`am/layer.py`, `am/fuse.py`), all four acceptance tests pass including unmodified git; offline condensation pass (`am/condense.py`) admitted 5 content templates; growth curve 2 → 5 → 10 (threshold hit = reported finding). `PHASE3-STATE.md` is that phase's session-state file.
- `LIBRARY.md` is the structure log (primary experimental output). `FRICTION.md` holds where the model fought back (#8 is phase 2's central finding; #15 is phase 3's). `DECISIONS.md` §2.1 (atomic posting) is **ruled closed-as-open by Jocke**: the lost-update window is an accepted trade of literal references — do not fix or reopen.

## Rules that apply before you've read anything else
- Never let a second representation of anything come into existence (spec §0).
- Nothing that fires values ever enters the library — no eval, no apply, no universal interpreter. A workload that seems to need one is a §6 falsification event: reported, not implemented.
- Structural decisions where the spec is silent: present options to Jocke and wait. If asking is blocked: STOP, write options + recommendation to DECISIONS.md, end the session. Never implement the recommendation, even reversibly.
- When the model fights convention, the model wins until it demonstrably can't — and "demonstrably can't" is a finding for the friction log, not a workaround.
