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

# Runbook: Vault - Sealed State (ARCHIVED)

> **Severity**: Critical
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Status**: ARCHIVED — Vault decommissioned Feb 2026

This runbook covered unsealing HashiCorp Vault when auto-unseal via AWS KMS failed. Vault has been replaced by Infisical (self-hosted, Docker Compose on Hetzner). AWS KMS, IRSA, and External Secrets Operator are no longer used.
