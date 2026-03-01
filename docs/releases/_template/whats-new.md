# What's New in STOA Platform vX.Y.Z

> Release date: YYYY-MM-DD
> Previous version: vX.Y.W

## Highlights

<!-- 3-5 bullet points summarizing the most impactful changes. Written in user language, not commit messages. -->

- **Feature name**: 1-2 sentence description of what it does and why it matters
- **Feature name**: 1-2 sentence description

## Gateway

<!-- Changes to stoa-gateway (Rust). Skip section if no changes. -->

### New Capabilities

- Description of new gateway feature

### Improvements

- Description of improvement

## Control Plane API

<!-- Changes to control-plane-api (Python/FastAPI). Skip section if no changes. -->

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/example` | What it does |

### Changed Endpoints

| Method | Path | Change |
|--------|------|--------|
| `GET` | `/v1/example` | What changed |

### Improvements

- Description

## Console UI

<!-- Changes to control-plane-ui (React). Skip section if no changes. -->

- Description of UI change

## Developer Portal

<!-- Changes to portal (React). Skip section if no changes. -->

- Description of portal change

## Helm Chart

<!-- Changes to charts/stoa-platform. Skip section if no changes. -->

### New Values

| Key | Default | Description |
|-----|---------|-------------|
| `example.key` | `value` | What it controls |

### Changed Values

| Key | Old Default | New Default | Migration |
|-----|-------------|-------------|-----------|
| `example.key` | `old` | `new` | Action required |

## Dependencies

<!-- Major dependency updates that users should be aware of. -->

| Component | Dependency | From | To |
|-----------|-----------|------|-----|
| gateway | tokio | 1.x | 1.y |

## Full Changelog

See [CHANGELOG.md](../../CHANGELOG.md) for the complete list of changes including internal improvements, refactoring, and test additions.
