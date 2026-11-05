# Contributor Getting Started

The shortest path from a fresh clone to a merged pull request. This page links
the existing material instead of repeating it: product overview and Docker
quick start in [README.md](../../README.md), one-page component setup in
[DEVELOPMENT.md](../../DEVELOPMENT.md), the longer developer guide with
troubleshooting in [DEVELOPER.md](../../DEVELOPER.md), and the conventions in
[CONTRIBUTING.md](../../CONTRIBUTING.md). Every command below exists in the
repository; the file that defines it is cited next to it.

## 1. Before you start

- Read [CONTRIBUTING.md](../../CONTRIBUTING.md): issue standard, English-only
  rule, branch naming, commit format, DCO, code style.
- Pick or open an issue with one of the templates in
  [`.github/ISSUE_TEMPLATE/`](../../.github/ISSUE_TEMPLATE/) (bug report,
  feature request, docs improvement, question). Security findings go to the
  address in [SECURITY.md](../../SECURITY.md), never to a public issue.
- Every pull request needs one maintainer approval
  ([GOVERNANCE.md](../../GOVERNANCE.md#code-changes)); reviewers are assigned
  through [`.github/CODEOWNERS`](../../.github/CODEOWNERS).
- Keep changes small. The maintainers' working rules in
  [CLAUDE.md](../../CLAUDE.md#qualité--ci) cap a pull request at 300 changed
  lines; split larger work into several pull requests.

## 2. Prepare your environment

### Fork and clone

Fork `stoa-platform/stoa` on GitHub, then run from the parent directory
where you want the clone:

```bash
git clone https://github.com/<your-account>/stoa.git
cd stoa
git remote add upstream https://github.com/stoa-platform/stoa.git
git fetch upstream main
```

All subsequent command blocks start at the repository root unless stated
otherwise. Parenthesized commands run in a subshell and leave your shell at
the root; return there before running a block from another terminal.

### Toolchain

| Component | Runtime | Source |
|---|---|---|
| `control-plane-api/`, `cli/` | Python 3.11 | [CLAUDE.md](../../CLAUDE.md#runtime-versions) |
| `control-plane-ui/`, `portal/`, `e2e/` | Node.js 20 | [CLAUDE.md](../../CLAUDE.md#runtime-versions) |
| `stoa-gateway/` | Rust stable; `cmake` and `librdkafka` only for the Kafka feature | [stoa-gateway/README.md](../../stoa-gateway/README.md#prerequisites) |
| `stoa-go/` | Go 1.25 | [stoa-go/go.mod](../../stoa-go/go.mod) |
| Full stack | Docker Desktop 4.x+ with 8 GB RAM, Docker Compose v2 | [deploy/docker-compose/README.md](../../deploy/docker-compose/README.md#prerequisites) |

Install commands per tool are in the
[prerequisites table of CONTRIBUTING.md](../../CONTRIBUTING.md#prerequisites).

### Git hooks (once, at the repository root)

```bash
# From the repository root
npm install
```

The `prepare` script of the root [package.json](../../package.json) installs
Husky, which enables the two hooks in [`.husky/`](../../.husky/): `commit-msg`
runs commitlint with [commitlint.config.js](../../commitlint.config.js), and
`pre-commit` runs lint-staged with [.lintstagedrc.json](../../.lintstagedrc.json)
(ESLint and Prettier on staged TypeScript, Ruff on staged Python).

### Dependencies and configuration

```bash
# From the repository root
make setup
```

The `setup` target of the [Makefile](../../Makefile) installs the API, both
front ends, the gateway and the Python CLI. CI installs the API with its dev
extras ([`.github/actions/setup-python-env/action.yml`](../../.github/actions/setup-python-env/action.yml));
do the same before running its tests:

```bash
# From the repository root; installation runs inside control-plane-api
(cd control-plane-api && pip install -r requirements.txt && pip install -e ".[dev]")
```

Each component ships a `.env.example`; copy it to the env file named in the
[Environment Variables table of DEVELOPMENT.md](../../DEVELOPMENT.md#environment-variables).
`.env` files are ignored by [.gitignore](../../.gitignore); never commit
credentials, the `Secret Scan (Gitleaks)` job of
[security-scan.yml](../../.github/workflows/security-scan.yml) scans every
pull request with [.gitleaks.toml](../../.gitleaks.toml).

### Git identity and signing

Use the name and email of your GitHub account, and enable commit signing:

```bash
# From the repository root
git config user.name "Your Name"
git config user.email "you@example.com"
git config commit.gpgsign true
```

`commit.gpgsign` is the setting recommended in
[CLA.md](../../CLA.md#configure-git-for-automatic-sign-off). The
`Verify Signed Commits` job of
[required-checks.yml](../../.github/workflows/required-checks.yml) inspects
human commits authored on or after 2026-04-25 with `git verify-commit`; it is
warning-only today, and the project asks for GPG-signed commits. Matching your
GitHub identity also keeps the DCO trailer consistent after the squash merge
(see [CONTRIBUTING.md](../../CONTRIBUTING.md#the-dco-check-and-squash-merges)).

## 3. Start the components locally

**Full stack with Docker Compose.** Follow the
[Quick start of README.md](../../README.md#quick-start): from
`deploy/docker-compose/`, `cp .env.example .env`, `docker compose up -d`, then
`../../scripts/demo/check-health.sh --wait`. Service URLs and troubleshooting
are in [deploy/docker-compose/README.md](../../deploy/docker-compose/README.md).
Return to the repository root afterward.

**Component by component.** Follow the
[Component Setup of DEVELOPMENT.md](../../DEVELOPMENT.md#component-setup), or
use the `run-*` targets of the [Makefile](../../Makefile) from the repository root:

| Target | Starts | Port (Makefile comment) |
|---|---|---|
| `make run-ui` | Console UI dev server | 5173 |
| `make run-portal` | Developer Portal dev server | 5174 |
| `make run-gateway` | STOA Gateway (`cargo run`) | 8080 |
| `make run-api` | Control Plane API, maintainers only (see below) | 8000 |

> `make run-api` runs [scripts/dev/run-api-local.sh](../../scripts/dev/run-api-local.sh),
> which needs the Vault CLI and a token for the maintainers' Vault. From a
> fork, start the API by hand as in
> [control-plane-api/README.md](../../control-plane-api/README.md#quick-start):
>
> ```bash
> # From the repository root; both commands run beside alembic.ini
> (
>   cd control-plane-api || exit
>   cp .env.example .env               # set DATABASE_URL, KEYCLOAK_URL
>   alembic upgrade head && uvicorn src.main:app --reload --port 8000
> )
> ```

The Go CLI and agent build with `make build` and `make build-connect` in
[stoa-go/Makefile](../../stoa-go/Makefile).

## 4. Run the tests and linters

Available local checks from the repository root, with the corresponding CI
workflows for reference. These targets do not reproduce every CI check:

| Component | Tests | Lint | CI workflow |
|---|---|---|---|
| Control Plane API | `make test-api` (pytest, coverage ≥ 70 %) | `make lint-api` (ruff, black) | [control-plane-api-ci.yml](../../.github/workflows/control-plane-api-ci.yml) |
| Console UI | `make test-ui` (vitest) | `make lint-ui` (eslint ≤ 110 warnings, prettier, tsc) | [control-plane-ui-ci.yml](../../.github/workflows/control-plane-ui-ci.yml) |
| Developer Portal | `make test-portal` (vitest) | `make lint-portal` (eslint 0 warnings, prettier, tsc) | [stoa-portal-ci.yml](../../.github/workflows/stoa-portal-ci.yml) |
| STOA Gateway | `make test-gateway` (`cargo test`); `make test-gateway-all-features` adds Kafka and checks `cmake` first | `make lint-gateway` (fmt, clippy `-D warnings`) | [stoa-gateway-ci.yml](../../.github/workflows/stoa-gateway-ci.yml) |
| Python CLI | `make test-cli` | `make lint-cli` | not wired in `ci-gate` |
| stoactl, stoa-connect | `make -C stoa-go test` | `make -C stoa-go lint` (needs `golangci-lint`) | [stoa-go-ci.yml](../../.github/workflows/stoa-go-ci.yml) |

`make test` and `make lint` cover the API, Console UI, Portal, Rust gateway
and Python CLI sequentially; `make test-all` and `make lint-all` cover those
same five components in parallel. They exclude Go. Run its checks separately
from the repository root with `make -C stoa-go test` and `make -C stoa-go lint`.
The ESLint thresholds are the `lint` scripts
of [control-plane-ui/package.json](../../control-plane-ui/package.json) and
[portal/package.json](../../portal/package.json).

CI also runs API `mypy src/ --ignore-missing-imports` as a warning-only check
([reusable-python-ci.yml](../../.github/workflows/reusable-python-ci.yml));
pre-existing diagnostics do not require cleanup for an unrelated change. Rust
CI enables `kafka,pingora,phases` for Clippy and tests in
[stoa-gateway-ci.yml](../../.github/workflows/stoa-gateway-ci.yml), whereas
`make lint-gateway` uses default features. The reusable Rust workflow defaults
to `--all-features` when no override is supplied and also runs nextest and
doctests ([reusable-rust-ci.yml](../../.github/workflows/reusable-rust-ci.yml)).
Consult these workflows for the full CI configuration.

Two more checks you can run locally before pushing:

```bash
# From the repository root
# Apache 2.0 headers on source files (CONTRIBUTING.md, "License Headers")
python scripts/add-license-headers.py --check .

# Container image pinning on changed files (required-checks.yml, "Image Pinning Guard")
python3 -B scripts/ci/check_image_pinning.py \
  --base "$(git rev-parse upstream/main)" --head "$(git rev-parse HEAD)"
```

End-to-end tests need a running stack and a browser: see
[docs/E2E-TESTING.md](../E2E-TESTING.md) and [e2e/README.md](../../e2e/README.md)
(`npm run test:smoke`, `npm run test:e2e` from [e2e/package.json](../../e2e/package.json)).

## 5. Propose a contribution

### Branch

Branch from an up-to-date `main`, with a prefix from
[CONTRIBUTING.md](../../CONTRIBUTING.md#branch-naming):

```bash
# From the repository root
git fetch upstream
git checkout -b feat/short-description upstream/main
```

### Commit

One logical change per commit, in
[Conventional Commits](../../CONTRIBUTING.md#commit-messages) format, signed
off (`-s`, DCO) and signed (`-S`, GPG):

```bash
# From the repository root, with your changes staged
git commit -s -S -m "feat(gateway): add rate limiting per tenant"
```

- Allowed types and scopes, subject up to 72 characters, header up to 100:
  [commitlint.config.js](../../commitlint.config.js). The `commit-msg` hook
  rejects anything else.
- The `Signed-off-by:` trailer is mandatory and verified during review; no CI
  check enforces it since 2026-03-05
  ([CONTRIBUTING.md](../../CONTRIBUTING.md#the-dco-check-and-squash-merges)).
  Forgot it? `git commit --amend -s --no-edit` ([CLA.md](../../CLA.md#faq)).
- Fixing a bug? Add a regression test or the `Regression Test Guard` fails: a
  Python file named `test_regression_*.py`, a TypeScript test under a
  `regression/` directory, a Rust `fn regression_*` test, a Go
  `TestRegression*` function, or an `@regression` Gherkin tag
  ([regression-guard.yml](../../.github/workflows/regression-guard.yml)).

### Pull request

Push the branch to your fork and open a pull request against `main`. Fill in
[`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md);
the "Linear Ticket" section is for maintainers, link the GitHub issue instead.
Write the title as a conventional commit: pull requests are squash-merged, the
title becomes the commit subject and the body its message (repository merge
settings, read 2026-11-05), and release-please builds the changelog from them
([RELEASING.md](../../RELEASING.md#release-process)).

### Checks on a pull request

Required by the branch protection of `main` (read 2026-11-05):

| Check | Defined in | What it does |
|---|---|---|
| `ci-gate` | [ci-gate.yml](../../.github/workflows/ci-gate.yml) | Runs the CI of each touched component (paths in [ci-gate-changes.sh](../../.github/scripts/ci-gate-changes.sh)) and [security-scan.yml](../../.github/workflows/security-scan.yml), then aggregates the results and enforces image pinning |
| `License Compliance`, `SBOM Generation`, `Verify Signed Commits` | [required-checks.yml](../../.github/workflows/required-checks.yml) | Offline licence check, SBOM artefacts, commit signature report (warning-only) |
| `Regression Test Guard` | [regression-guard.yml](../../.github/workflows/regression-guard.yml) | Fix pull requests must add a regression test |
| `purged-paths-guard` | [purged-paths-guard.yml](../../.github/workflows/purged-paths-guard.yml) | Blocks the return of paths removed from the repository |

Advisory only: `STOA PR Guardian`
([pr-guardian.yml](../../.github/workflows/pr-guardian.yml)) posts an AI
review; it skips draft pull requests and pull requests from forks. The required
workflows also run in the merge queue (`merge_group` trigger) before the squash
commit lands on `main`.

### After the merge

The branch is deleted automatically. If you later backport or cherry-pick a
squash commit, re-sign it as described in
[CONTRIBUTING.md](../../CONTRIBUTING.md#the-dco-check-and-squash-merges).

## 6. Getting help

[SUPPORT.md](../../SUPPORT.md) lists GitHub Discussions and issues; the Discord
invite is in [CONTRIBUTING.md](../../CONTRIBUTING.md#community). Known CI
quirks are tracked in [docs/releases/known-issues.md](../releases/known-issues.md).
