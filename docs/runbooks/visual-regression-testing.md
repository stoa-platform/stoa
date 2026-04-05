# Visual Regression Testing — Runbook

Operational guide for STOA's visual regression testing pipeline (Phase 2 of CAB-1989).

## Architecture

```
Playwright test → screenshot → compare against golden baseline
  ├── Match     → PASS
  └── Mismatch  → generate diff image → FAIL (review required)
```

Golden baselines live in `e2e/golden/` and are committed to git.
Dynamic values (counts, timestamps) are masked via `data-testid` suffix convention.

## Prerequisites

- Docker Desktop (for consistent rendering across dev/CI)
- Node 20+, `npm install` in `e2e/`
- `@axe-core/playwright` installed (added in CAB-1990)

## Running Visual Tests Locally

```bash
cd e2e

# Run with Docker for pixel-consistent baselines
docker run --rm -v $(pwd):/work -w /work mcr.microsoft.com/playwright:v1.58.2-jammy \
  npx playwright test --grep @visual

# Run natively (may differ from CI baselines on macOS)
npx playwright test --grep @visual
```

## Updating Golden Baselines

When a visual change is intentional (new component, redesign):

```bash
# 1. Run tests with --update-snapshots
docker run --rm -v $(pwd):/work -w /work mcr.microsoft.com/playwright:v1.58.2-jammy \
  npx playwright test --grep @visual --update-snapshots

# 2. Review the updated baselines
git diff --stat e2e/golden/

# 3. Commit
git add e2e/golden/
git commit -m "test(e2e): update visual baselines — <reason>"
```

**Never update baselines without reviewing the diff.** Each updated PNG should be visually inspected.

## Debugging CI Visual Diff Failures

### Step 1 — Download artifacts

```bash
# From GitHub Actions
gh run download <run-id> -n visual-regression-results

# Artifacts contain:
# - test-results/   (actual screenshots)
# - golden/         (expected baselines)
# - diff/           (pixel diff images — red = changed)
```

### Step 2 — Compare locally

Open the diff images in a viewer. Red pixels indicate changes.

### Step 3 — Diagnose

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Entire page shifted | Font rendering difference | Ensure Docker image matches CI |
| Dynamic value changed | Missing mask | Add `data-testid` with `-count`/`-timestamp` suffix |
| Minor anti-aliasing | OS-level rendering | Use Docker for consistency |
| New component visible | Feature PR included UI change | Update baselines |
| Dark mode diff | Theme not pinned in test | Set `colorScheme: 'light'` in test config |

### Step 4 — Fix or update

- **False positive** (no real change): update baselines via Docker
- **Real regression**: fix the code, re-run tests
- **Intentional change**: update baselines and commit with explanation

## Docker Setup for Local Visual Testing

The CI environment uses a specific Playwright Docker image for pixel-consistent rendering.
Local macOS renders fonts differently, causing false positives.

```bash
# Pull the exact CI image
docker pull mcr.microsoft.com/playwright:v1.58.2-jammy

# Run interactive shell for debugging
docker run --rm -it -v $(pwd):/work -w /work mcr.microsoft.com/playwright:v1.58.2-jammy bash

# Inside container:
npx playwright test --grep @visual --reporter=html
# Open report: npx playwright show-report
```

## Masking Convention

Dynamic values that change between runs must be masked to avoid false positives.
The `data-testid` suffix convention controls masking:

| Suffix | Masked? | Example |
|--------|---------|---------|
| `-count` | Yes | `dashboard-requests-count` |
| `-timestamp` | Yes | `activity-last-updated-timestamp` |
| `-duration` | Yes | `gateway-uptime-duration` |
| (no suffix) | No | `dashboard-title` |

Masking is applied by the visual regression helper which replaces the text content of masked elements with a placeholder before screenshot capture.

## Metrics

Track visual regression health over time:

```bash
# Current baseline count + a11y metrics
./scripts/ai-ops/ui-validation-metrics.sh --table
```

## References

- [ADR-060: AI-Verified UI Testing Framework](https://docs.gostoa.dev/architecture/adr/adr-060-ai-verified-ui-testing)
- [data-testid Convention](../DATA-TESTID-CONVENTION.md) (stoa repo)
- [CAB-1989: MEGA ticket](https://linear.app/hlfh-workspace/issue/CAB-1989)
