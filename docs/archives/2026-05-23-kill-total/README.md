# STOA Shutdown — Archive pointers (2026-05-23)

This directory in the repo contains ONLY pointers and metadata. The actual encrypted backups live locally at `~/Backups/stoa-shutdown/` (gitignored).

- Plan : `docs/plans/2026-05-23-stoa-kill-total.md`
- Decision : `docs/decisions/2026-05-23-stoa-kill-total.md` (Gate #12 GO)
- Manifest : `MANIFEST.md` (in this dir) — sha256 + restore procedures
- Operator memory : `~/.claude/.../memory/project_stoa_shutdown.md`

The backup files themselves MUST NEVER be committed to git (`.env*` write-guard would catch some, but operator vigilance is the real defence).
