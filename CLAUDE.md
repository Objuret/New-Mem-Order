# Activation Model — Session Orientation

## Read first, every session
1. `activation-model.md` — the spec. It is law. Code conforms to it; it changes only by Jocke's explicit acceptance. On any conflict between files, the spec wins.
2. `build-brief.md` — process, build order, measurements, hard rules.

## Current state
- Nothing is built. This is a clean start: follow the brief's build order from step 1. Any code found in git history is from a discarded earlier attempt — do not restore, reference, or build on it.

## Rules that apply before you've read anything else
- Never let a second representation of anything come into existence (spec §0).
- Nothing that fires values ever enters the library — no eval, no apply, no universal interpreter. A workload that seems to need one is a §6 falsification event: reported, not implemented.
- Structural decisions where the spec is silent: present options to Jocke and wait. If asking is blocked: STOP, write options + recommendation to DECISIONS.md, end the session. Never implement the recommendation, even reversibly.
- When the model fights convention, the model wins until it demonstrably can't — and "demonstrably can't" is a finding for the friction log, not a workaround.
