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

A platform release is cut once per milestone, and at most once a month. Pull
requests are never released individually.

### Between releases

- Every pull request that changes user-facing behaviour adds a line to the
  **Unreleased** section of [CHANGELOG.md](CHANGELOG.md), under `Added`,
  `Fixed`, `Security` or `Breaking changes`. Internal changes (CI, tests,
  refactoring) need no entry.
- release-please is configured to open per-component release pull requests
  from conventional commits. Merging one bumps that component's version, tag
  and `CHANGELOG.md` only; it is not a platform release.

### Cutting a platform release

1. Open a release pull request that renames `## [Unreleased]` to
   `## [X.Y.0] - YYYY-MM-DD`, adds an empty `## [Unreleased]` section above
   it, and sets the same version in `version.txt`. Choose the version with the
   Versioning table above.
2. Merge it, then tag the merge commit with a signed tag and push the tag:

   ```bash
   git tag -s vX.Y.0 -m "vX.Y.0"
   git push origin vX.Y.0
   ```

3. The `v*` tag triggers the Release workflow, which creates the GitHub
   Release, and the Docker publish workflow, which builds, signs and pushes
   the images for every service.
4. Replace the generated release notes with the new CHANGELOG section, copied
   verbatim into a file:

   ```bash
   gh release edit vX.Y.0 --notes-file release-notes.md
   ```

### Out-of-band patch

A security or data-loss fix that cannot wait for the next milestone follows
the same steps with a PATCH version (`vX.Y.Z`).

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
- [ ] `Unreleased` moved to the new version section in CHANGELOG.md, `version.txt` updated
- [ ] Documentation updated
- [ ] Breaking changes documented
- [ ] Migration guide (if needed)
- [ ] GitHub Release notes equal the CHANGELOG section

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
| Platform release (`vX.Y.0`) | One per milestone, at most one per month |
| Out-of-band patch (`vX.Y.Z`) | Only for security or data-loss fixes that cannot wait |
