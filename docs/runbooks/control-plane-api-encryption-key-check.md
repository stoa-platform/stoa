# Runbook: Control Plane API - Backend Encryption Key Check

> **Last updated**: 2026-11-25
> **Owner**: Platform Team

Run this check before deploying or promoting the Control Plane API to an
environment. It confirms that `BACKEND_ENCRYPTION_KEY` is set in the
`stoa-control-plane-api-secrets` Secret.

## Why

Without the key, production falls back to the public development key and logs
an error; a key set to that public development key is treated the same way.
Setting `BACKEND_ENCRYPTION_KEY_REQUIRED=true` makes the API refuse to start
instead, and also refuses a key that is not a valid Fernet key. The setting is off by default: enable it only once this check
passes in every environment.

## Check

The script prints only a status (`present`, `absent`, `empty`, public
development key), never the value. kubectl renders a go-template that returns
only the requested field, so the other fields of the Secret are not read. The
script does not write any file and does not echo kubectl errors.

```bash
python3 control-plane-api/scripts/check_backend_encryption_key.py \
  --namespace stoa-system --secret stoa-control-plane-api-secrets --context <target-context>
```

| Exit code | Meaning | Action |
|-----------|---------|--------|
| 0 | `BACKEND_ENCRYPTION_KEY` present, non-empty, not the public development key | Deploy |
| 1 | Key absent from the Secret | Stop; have the key added to the Secret |
| 2 | Key empty or not valid base64 | Stop; have the key set |
| 3 | Secret not found | Stop; check namespace, context and Secret name |
| 4 | kubectl failed (access, context, timeout) or invalid key name | Fix access or arguments and rerun |
| 5 | Key is the public development key | Stop; have a private key generated and set |

Do not inspect the value with `kubectl get secret -o yaml` or `-o jsonpath`:
both print it.
