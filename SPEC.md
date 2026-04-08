# Spec: CAB-2007 — K8s Job Manifests for Unified Seeder (Staging + Prod)

## Problem

The unified seeder (`control-plane-api/scripts/seeder/`) has no K8s execution path for staging or prod. After deploy, the control plane is empty — no tenant, no gateway. The only K8s seeder is a legacy CronJob using deprecated `seed_demo_tenant.py`.

## Goal

Two standalone K8s Job manifests (`job-staging.yaml`, `job-prod.yaml`) that seed the correct data for each environment using the unified seeder. Manual `kubectl apply` triggers execution. Jobs are idempotent (safe to re-run).

## API Contract

No API changes. The seeder connects directly to PostgreSQL via `DATABASE_URL`.

```
CLI: python -m scripts.seeder --profile staging
CLI: python -m scripts.seeder --profile prod
```

## Acceptance Criteria

- [ ] AC1: `k8s/seeder/job-staging.yaml` exists and passes `kubectl apply --dry-run=client`
- [ ] AC2: `k8s/seeder/job-prod.yaml` exists and passes `kubectl apply --dry-run=client`
- [ ] AC3: Both Jobs use image `ghcr.io/stoa-platform/control-plane-api:latest`
- [ ] AC4: Both Jobs read `DATABASE_URL` from Secret `stoa-control-plane-api` via `secretKeyRef`
- [ ] AC5: Both Jobs have `backoffLimit: 1` and `activeDeadlineSeconds: 120`
- [ ] AC6: Both Jobs have Kyverno-compliant securityContext (`privileged: false`, `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`)
- [ ] AC7: Staging Job runs `--profile staging` (6 steps)
- [ ] AC8: Prod Job runs `--profile prod` (2 steps: tenants, gateway)
- [ ] AC9: Neither Job uses `--reset` flag
- [ ] AC10: Jobs have standard K8s labels (`app.kubernetes.io/component: seeder`, `app.kubernetes.io/part-of: stoa-platform`, `stoa.dev/environment: staging|prod`)

## Edge Cases

| Case | Input | Expected | Priority |
|------|-------|----------|----------|
| Job re-run after seed | `kubectl apply` again | Job replaced (same name), seeder skips existing data | Must |
| DB unreachable | Wrong secret / no PG | Job fails, backoffLimit=1 prevents retry loop | Must |
| Missing secret | Secret `stoa-control-plane-api` absent | Pod in `CreateContainerConfigError`, no crash loop | Should |
| Migrations not applied | Seeder before Alembic | Seeder fails on missing tables, Job exits 1 | Should |

## Out of Scope

- Helm chart integration (lives in stoa-infra, separate ticket)
- Migrating legacy `demo-tenant-reset` CronJob to unified seeder
- CI/CD automation (seeder triggered by deploy pipeline)
- CronJob for periodic reset (staging only, future ticket)
- New seeder steps or profile changes

## Security Considerations

- [ ] No credentials hardcoded — `DATABASE_URL` from K8s Secret only
- [ ] No `--reset` flag in manifests (destructive = manual only)
- [ ] `readOnlyRootFilesystem: true` (seeder writes nothing to disk)
- [ ] `runAsNonRoot: true`, UID 1000 (matches control-plane-api Dockerfile)
- [ ] No RBAC needed (seeder uses DB, not K8s API)

## Dependencies

- Secret `stoa-control-plane-api` must exist in `stoa-system` namespace with `DATABASE_URL` key
- Alembic migrations must be applied before running seeder
- Image `ghcr.io/stoa-platform/control-plane-api:latest` must be available

## Notes

- Pattern follows existing `k8s/demo/cronjob-reset.yaml` (same image, same secret, same securityContext)
- Manual trigger: `kubectl apply -f k8s/seeder/job-prod.yaml`
- Re-run: `kubectl delete job stoa-seeder-prod -n stoa-system && kubectl apply -f k8s/seeder/job-prod.yaml`
- Verify: `kubectl logs -n stoa-system job/stoa-seeder-prod`
