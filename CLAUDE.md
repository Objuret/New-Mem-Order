# Activation Model — Session Orientation

## Read first, every session
1. `activation-model.md` — the spec. It is law. Code conforms to it; it changes only by Jocke's explicit acceptance. On any conflict between files, the spec wins.
2. `build-brief.md` — process, build order, measurements, hard rules.

## Current state
- Prototype built and measured (2026-07-08); spec unchanged. Grammar + runtime in `am/` (byte-walking instruction grammar, 2-structure library, single router, client), message-board workload as instructions, end-to-end demo with restart survival (`demo.py`), measurements (`report.py`, `REPORT.md`).
- `LIBRARY.md` is the structure log (primary experimental output). `FRICTION.md` holds where the model fought back. `DECISIONS.md` holds judgment calls made under the brief's delegation plus open structural questions awaiting Jocke — its §2.1 (atomic posting) is open and nothing for it was implemented.

## Rules that apply before you've read anything else
- Never let a second representation of anything come into existence (spec §0).
- Nothing that fires values ever enters the library — no eval, no apply, no universal interpreter. A workload that seems to need one is a §6 falsification event: reported, not implemented.
- Structural decisions where the spec is silent: present options to Jocke and wait. If asking is blocked: STOP, write options + recommendation to DECISIONS.md, end the session. Never implement the recommendation, even reversibly.
- When the model fights convention, the model wins until it demonstrably can't — and "demonstrably can't" is a finding for the friction log, not a workaround.
