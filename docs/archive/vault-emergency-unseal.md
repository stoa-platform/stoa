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

# Runbook: Vault Emergency Unseal + Credentials Integrity (ARCHIVED)

> **Severity**: Critical
> **Status**: ARCHIVED — Vault decommissioned Feb 2026

This runbook covered two scenarios: (1) Vault sealed state when AWS KMS auto-unseal failed, and (2) DB credentials drift between Vault and PostgreSQL. Both are no longer applicable — secrets are managed via Infisical, and External Secrets Operator is decommissioned.
