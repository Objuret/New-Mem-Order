# PHASE3-STATE

Session state per PHASE3-LAYER.md §13. First act of every session: read
this. Last act: update it. This file is the plan — do not re-plan the
phase inside a session.

## Environment (checked 2026-07-08)
- **FUSE works in this container.** /dev/fuse present, `fuse` 2.9.9 +
  libfuse2 installed via apt, fusepy installed by copying its single
  module into site-packages (its setup.py trips a setuptools bug; the
  module itself is fine). §3 fallback NOT needed — real mount, real git.
- Reinstall recipe if container is recreated:
  `apt-get install -y fuse && pip download fusepy --no-binary :all: -d /tmp/f && tar xzf /tmp/f/fusepy-*.tar.gz -C /tmp/f && cp /tmp/f/fusepy-*/fuse.py $(python3 -c "import site; print(site.getsitepackages()[0])")/`

## Checklist (§10 acceptance, §11 measurements) — PHASE COMPLETE 2026-07-08
- [x] Layer core, stage 1: literal chains (am/layer.py)
- [x] FUSE binding (am/fuse.py) — real mount, tested
- [x] Acceptance 1: byte fidelity — PASS
- [x] Acceptance 2: real git init/add/commit×3/log/checkout/fsck in the mount — PASS
- [x] Acceptance 3: restart survival (SIGKILL, remount, zero recovery code) — PASS
- [x] Condensation pass, stage 2 (am/condense.py)
- [x] Acceptance 4: condensation fidelity + idempotent re-run — PASS
- [x] M1: reachable store 11.01 MB → 5.68 MB vs ext4 10.99 MB; total incl. superseded 268.9 MB (honest 24.5×)
- [x] M2: LIBRARY.md admission log (5 templates, bytes saved, span-rejections)
- [x] M3: growth curve 2 → 5 → 10 (threshold hit exactly; two-tier finding in REPORT.md)
- [x] M4: firings/syscall table (read 32.3, write 17.5, getattr 0.68, namespace ops 0)
- [x] M5: FRICTION.md #15–#21 appended
- [x] REPORT.md phase-3 section; phase3-results.json committed; pushed

## Current blocker
none — phase complete

## Next action
None within phase 3. If a later session reopens this area, candidate
directions already surfaced (NOT ruled in, do not build without Jocke):
condensation-as-history-compaction (FRICTION.md #15), the spec-licensed
identity cache (charter §8 kept it unbuilt in v1), content-defined
chunk boundaries (FRICTION.md #16).
