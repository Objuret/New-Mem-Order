# PHASE3-STATE

Session state per PHASE3-LAYER.md §13. First act of every session: read
this. Last act: update it. This file is the plan — do not re-plan the
phase inside a session.

## Environment (checked 2026-07-08)
- **FUSE works in this container.** /dev/fuse present, `fuse` 2.9.9 +
  libfuse2 installed via apt, fusepy installed by copying its single
  module into site-packages (its setup.py trips a setuptools bug; the
  module itself is fine). Loopback mount smoke-tested OK.
- §3 environment fallback NOT needed. Real mount, real git.
- Reinstall recipe if container is recreated:
  `apt-get install -y fuse && pip download fusepy --no-binary :all: -d /tmp/f && tar xzf /tmp/f/fusepy-*.tar.gz -C /tmp/f && cp /tmp/f/fusepy-*/fuse.py $(python3 -c "import site; print(site.getsitepackages()[0])")/`

## Checklist (§10 acceptance, §11 measurements)
- [ ] Layer core, stage 1: literal chains (am/layer.py)
- [ ] FUSE binding (am/fuse.py)
- [ ] Acceptance 1: byte fidelity (sizes 0..5MiB, boundary overwrites, rename/delete/recreate)
- [ ] Acceptance 2: real git init/add/commit×3/log/checkout in the mount
- [ ] Acceptance 3: restart survival (kill mount, remount, zero recovery code)
- [ ] Condensation pass, stage 2 (am/condense.py)
- [ ] Acceptance 4: condensation fidelity (checksums) + idempotent re-run
- [ ] M1: store bytes vs plain ext4, before/after condensation
- [ ] M2: LIBRARY.md admission/rejection log with bytes saved
- [ ] M3: growth curve 2 → 5 → N
- [ ] M4: firings per syscall (read/write/stat/readdir)
- [ ] M5: FRICTION.md appended
- [ ] REPORT.md phase-3 section; STATE updated; committed and pushed

## Current blocker
none

## Next action
Build am/layer.py (stage-1 layer core).
