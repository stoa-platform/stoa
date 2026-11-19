# Runbook — Dependabot Requirements Locks (`control-plane-api` & `stoa-bench`)

## Context

`control-plane-api/Dockerfile` and `.github/workflows/stoa-bench.yml` install Python dependencies with `pip install --require-hashes` from two hash-locked files generated from versioned `.in` inputs:

| Input | Generated lock |
|---|---|
| `control-plane-api/requirements.txt` + `control-plane-api/requirements-lock.in` | `control-plane-api/requirements-lock.txt` |
| `control-plane-api/requirements.txt` + `control-plane-api/requirements-bench.in` | `control-plane-api/requirements-bench.txt` |

The required `ci-gate` (`gate-contract`) job runs `scripts/ci/tests/test_regression_requirements_lock.py` whenever any of these files change. Because Dependabot does not re-compile transitive hashes via `uv pip compile`, `.github/workflows/dependabot-requirements-locks.yml` automatically regenerates and pushes updated locks on Dependabot pull requests using a dedicated GitHub App token (required because `GITHUB_TOKEN` on Dependabot `pull_request` events is read-only and does not re-trigger CI workflows).

## 1. Create and install the GitHub App

1. Open **Organization Settings** -> **Developer settings** -> **GitHub Apps** -> **New GitHub App** in `stoa-platform`.
2. Configure the app:
   - **GitHub App name**: e.g. `stoa-requirements-locks` (any unique slug).
   - **Homepage URL**: `https://github.com/stoa-platform/stoa`.
   - **Webhook**: uncheck **Active** (not needed).
   - **Repository permissions** (all others set to *No access*):
     - **Contents**: `Read and write`
     - **Pull requests**: `Read and write`
   - **Where can this GitHub App be installed?**: **Only on this account**.
3. Create the App, note its numeric **App ID**, and click **Generate a private key** (downloads a `.pem` file — never commit it; store it per org secret custody).
4. Open **Install App** -> install on `stoa-platform` -> **Only select repositories** -> select **`stoa` only**.

## 2. Add the Dependabot secrets on `stoa`

Dependabot `pull_request` workflows receive **Dependabot secrets**, not Actions secrets.

1. Go to `stoa-platform/stoa` -> **Settings** -> **Secrets and variables** -> **Dependabot**.
2. Create two repository secrets:
   - `STOA_LOCKS_APP_ID`: the numeric App ID from step 1.
   - `STOA_LOCKS_APP_PRIVATE_KEY`: the full contents of the generated `.pem` private key.

Once configured, any Dependabot PR touching `control-plane-api/requirements.txt`, `control-plane-api/requirements-lock.in`, or `control-plane-api/requirements-bench.in` will receive an automatic `chore(deps): regenerate requirements locks` commit and re-run `ci-gate`.

## 3. Manual fallback (without GitHub App)

If `STOA_LOCKS_APP_ID` or `STOA_LOCKS_APP_PRIVATE_KEY` is not configured, `.github/workflows/dependabot-requirements-locks.yml` succeeds without pushing and prints `régénération manuelle : scripts/ci/regenerate-requirements-locks.sh` in its job summary.

Regenerate and push manually on the PR branch:

```bash
gh pr checkout <PR_NUMBER>
scripts/ci/regenerate-requirements-locks.sh
python3 -m pytest scripts/ci/tests/test_regression_requirements_lock.py -v
git add control-plane-api/requirements-lock.txt control-plane-api/requirements-bench.txt
git commit -m "chore(deps): regenerate requirements locks"
git push
```
