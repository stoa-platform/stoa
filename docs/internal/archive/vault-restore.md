# DO NOT USE — ARCHIVED (2026-02-15)

> **This runbook is obsolete.** HashiCorp Vault was decommissioned in February 2026 and replaced by Infisical (self-hosted at `vault.gostoa.dev`).
>
> - For secrets management: see `docs/SECRETS-ROTATION.md`
> - For Infisical configuration: see `.claude/rules/secrets-management.md`
>
> This file is preserved in `docs/archive/` for historical reference only.

---

*Original content below (historical — do not execute these commands)*

---

# Vault Snapshot Restore Runbook (ARCHIVED)

> **Severity**: Critical
> **Status**: ARCHIVED — Vault decommissioned Feb 2026

This runbook covered restoring HashiCorp Vault from Raft snapshots stored in S3. Vault, AWS S3 backups, and the Raft storage backend are no longer used. Secrets are now managed via Infisical with PostgreSQL backend.
