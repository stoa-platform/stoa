# Internal and Historical Documentation

This directory collects maintainer-only contracts, dated plans, decision logs,
audit artifacts, performance baselines, and component working reports relocated
from the repository root and top-level component directories.

Nothing was deleted during relocation (`git mv` only). Files encrypted with
`git-crypt` (`audit/`, `context-packs/`, `learning/`, `file-map.json`,
`stoa-impact.db`) retain their original encrypted blobs and `.gitattributes`
filters.

## Contents

| Path | Category | Review note |
|------|----------|-------------|
| `DEVELOPER.md` | Archived dev guide | Consolidated into root [`DEVELOPMENT.md`](../../DEVELOPMENT.md) |
| `audit/`, `specs/audits/` | Audits and runtime verification | Encrypted artifacts (`audit/`) and verification specs; plaintext audit reports are archived privately |
| `plans/`, `decisions/`, `archive/` | Dated plans, decisions, archives | Review historical records and internal tracking identifiers |
| `baselines/gateway.json`, `BENCHMARKS_FREEZE_*.md`, `PROD_BASELINE_*.md`, `SMOKE_TEST_*.md` | Dated baselines and snapshots | Keep active baseline or prune stale snapshots |
| `context-packs/`, `learning/`, `file-map.json`, `stoa-impact.db` | Impact-analysis database and artifacts | Encrypted via `git-crypt`; decide long-term hosting |
| `control-plane-api/`, `control-plane-ui/`, `stoa-gateway/` | Component bug reports and fix plans | Working artifacts; decide whether to archive externally |
| `infra/`, `ci/`, `templates/`, `tests/` | Internal infrastructure notes, templates, and test plans | Review internal naming before further publication |
