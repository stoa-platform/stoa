# Releasing STOA Platform

This document describes the release process for STOA Platform.

## Versioning

We follow [Semantic Versioning](https://semver.org/):

```
v{MAJOR}.{MINOR}.{PATCH}[-{PRERELEASE}]
```

| Increment | When |
|-----------|------|
| MAJOR | Breaking API changes |
| MINOR | New features (backward compatible) |
| PATCH | Bug fixes |
| PRERELEASE | alpha, beta, rc |

## Release Process

### Automated (via release-please)

1. **Merge PRs** with conventional commits to `main`
2. **release-please** automatically creates/updates a Release PR
3. **Review** the Release PR (CHANGELOG, version bump)
4. **Merge** the Release PR
5. **Automatic**:
   - Git tag created (e.g., `v2.3.0`)
   - GitHub Release created with notes
   - Docker images built, signed, pushed to GHCR
   - Helm chart updated

### Manual (emergency)

```bash
# 1. Create tag
git tag -s v2.3.1 -m "v2.3.1: Emergency hotfix for CVE-XXXX"
git push origin v2.3.1

# 2. GitHub Actions triggers automatically
# - docker-publish.yml builds and pushes images
# - release.yml creates GitHub Release
```

## Artifacts

Each release produces:

| Artifact | Location |
|----------|----------|
| Docker images | `ghcr.io/stoa-platform/*:vX.Y.Z` |
| SBOM | Attached to Docker images (SPDX) |
| Signatures | Cosign keyless (GitHub OIDC) |

## Verifying Releases

### Verify Docker Image Signature

```bash
cosign verify \
  --certificate-identity-regexp="https://github.com/stoa-platform/*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/stoa-platform/control-plane-api:v2.3.0
```

### Verify SBOM

```bash
cosign download sbom ghcr.io/stoa-platform/control-plane-api:v2.3.0
```

### Verify SBOM Attestation

```bash
cosign verify-attestation \
  --certificate-identity-regexp="https://github.com/stoa-platform/*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  --type spdxjson \
  ghcr.io/stoa-platform/control-plane-api:v2.3.0
```

## Release Checklist

- [ ] All tests passing on `main`
- [ ] CHANGELOG.md accurate
- [ ] Documentation updated
- [ ] Breaking changes documented
- [ ] Migration guide (if needed)
- [ ] Release notes reviewed

## Rollback

```bash
# Via kubectl
kubectl set image deployment/control-plane-api \
  control-plane-api=ghcr.io/stoa-platform/control-plane-api:v2.2.0

# Via Helm
helm rollback stoa-prod 1

# Via ArgoCD
argocd app rollback stoa-prod
```

## Environments

| Environment | Helm Values | Domain |
|-------------|-------------|--------|
| Dev | `values.yaml` + `values-dev.yaml` | dev.gostoa.dev |
| Staging | `values.yaml` + `values-staging.yaml` | staging.gostoa.dev |
| Production | `values.yaml` + `values-prod.yaml` | gostoa.dev |

```bash
# Deploy to specific environment
helm upgrade --install stoa-dev ./charts/stoa-platform \
  -f charts/stoa-platform/values.yaml \
  -f charts/stoa-platform/values-dev.yaml \
  -n stoa-dev
```

## Release Schedule

| Type | Frequency |
|------|-----------|
| Patch | As needed |
| Minor | Bi-weekly |
| Major | Quarterly (announced) |
