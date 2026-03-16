# ADR-058: Pingora Integration — Embedded Connection Pool

**Status**: Accepted (Embed Pingora connector, keep axum for routing)
**Date**: 2026-03-16 (revised)
**Tickets**: CAB-1847, CAB-1849

## Context

Cloudflare's Pingora (Rust, Apache 2.0) replaced nginx and handles 1+ trillion requests/day. STOA Gateway is built on axum + reqwest + tokio. The question: how should STOA leverage Pingora?

## Why Pingora

### The Business Case (decisive factor)

| Signal | axum-only | With Pingora |
|--------|-----------|-------------|
| Enterprise pitch | "Custom Rust gateway" | **"Built on Pingora — Cloudflare's proxy framework"** |
| Competitive position | Same tier as custom proxies | **Same tier as Cloudflare Workers, Fastly Compute** |
| CISO checkbox | Unknown stack | **Battle-tested at 1T+ req/day** |
| OSS credibility | Generic framework | **Infrastructure-grade pedigree** |
| Market uniqueness | None | **Only API gateway built on Pingora** |

No API gateway vendor — Kong, Gravitee, Envoy, agentgateway — uses Pingora. This is a first-mover advantage in positioning.

### The Technical Case

| Feature | reqwest (current) | Pingora Connector |
|---------|-------------------|-------------------|
| Connection pool | Per-client instance | **Shared across all workers** (Cloudflare's key win) |
| H2 multiplexing | Per-connection | **Global stream multiplexing** |
| Pool reuse at scale | Degrades >10K RPS | **Designed for 1T+ req/day** |
| Zero-copy proxy | No (userspace copy) | Kernel splice/sendfile (future) |

At <1K RPS the difference is 0.5ms p95. At 50K+ RPS, shared pooling avoids connection exhaustion that per-client pools hit.

## Options Evaluated

| Option | Description | Effort | Verdict |
|--------|-------------|--------|---------|
| A: Full migration | Replace axum with Pingora server | 55+ pts | Rejected — rewrites 400+ routes |
| B: Sidecar | Pingora front-proxy → stoa-gateway | 21 pts | Rejected — extra hop, thin value |
| **C: Embedded** | **Pingora connector inside stoa-gateway** | **13 pts** | **Accepted** |
| D: Patterns only | Copy Pingora patterns, don't use crate | 0 pts | Superseded by C |

### Why Embedded (Option C) Won

- **One binary** — no sidecar, no extra hop, no deployment complexity
- **Same marketing claim** — "Built on Pingora" is equally true for embedded connector
- **Genuine value** — Pingora's shared pool is the actual Cloudflare advantage, not the server
- **Feature-gated** — `--features pingora` enables it; default build stays reqwest (no cmake dependency)
- **Incremental** — proxy path migrates to PingoraPool gradually; MCP/admin/auth stay on axum untouched

## Decision

**Embed `pingora-core::connectors::http::Connector` inside stoa-gateway behind a `pingora` feature flag.**

### Architecture

```
Client → stoa-gateway (:8080)
              │
              ├─ MCP / admin / auth / OAuth → axum handlers (unchanged)
              │
              └─ Proxy routes → PingoraPool.send_request()
                                    │
                                    └─ pingora-core shared connection pool
                                         → Backend (H1/H2, TLS, keepalive)
```

One binary. One port. One deployment. Pingora manages upstream connections; axum manages HTTP routing.

### Implementation (delivered in CAB-1849)

| PR | What |
|-----|------|
| #1799 | `stoa-pingora/` standalone binary (sidecar POC — superseded) |
| #1801 | `PingoraPool` embedded in stoa-gateway (production path) |
| #1803 | CI/CD: `FEATURES=kafka,pingora` in Docker build |

### Phase Compatibility

Our `ProxyPhase` trait (CAB-1834) maps 1:1 to Pingora's `ProxyHttp`:

| STOA ProxyPhase | Pingora ProxyHttp | Status |
|-----------------|-------------------|--------|
| `request_filter` | `request_filter` | Match |
| `upstream_select` | `upstream_peer` | Match |
| `upstream_request_filter` | `upstream_request_filter` | Match |
| `response_filter` | `upstream_response_filter` | Match |
| `logging` | `logging` | Match |
| `error_handler` | `error_while_proxy` | Match |

If a full Pingora migration is needed at v2.0, phase implementations port directly.

## What STOA Has That Pingora Doesn't

| Capability | STOA | Pingora |
|-----------|------|---------|
| eBPF kernel-level HTTP parsing | XDP + TC (CAB-1841/1843) | Not built-in |
| UAC policy enforcement at kernel level | BPF maps synced from gateway (CAB-1848) | Not built-in |
| WASM plugin runtime | wasmtime 42 (CAB-1644) | Not built-in |
| MCP protocol (AI agent gateway) | Full SSE/WS/JSON-RPC | Not applicable |
| Multi-gateway federation | 7 adapter types | Not applicable |

STOA uses Pingora for what it does best (connection pooling) and adds layers Pingora doesn't offer.

## Consequences

- Production image built with `FEATURES=kafka,pingora` (cmake required in Docker)
- `PingoraPool` available for proxy path; reqwest remains as fallback
- Default build (no features) still works without cmake dependency
- Marketing: **"STOA Gateway — powered by Pingora's connection engine"**
- NOTICE file includes Pingora Apache 2.0 attribution
- Re-evaluate full migration at v2.0 or 50K+ RPS

---

# ADR-058 : Intégration Pingora — Pool de Connexions Embarqué

**Statut** : Accepté (Intégrer le connecteur Pingora, conserver axum pour le routage)
**Date** : 2026-03-16 (révisé)
**Tickets** : CAB-1847, CAB-1849

## Contexte

Le framework Pingora de Cloudflare (Rust, Apache 2.0) a remplacé nginx et gère plus d'un trillion de requêtes/jour. STOA Gateway est construit sur axum + reqwest + tokio. La question : comment STOA doit-il exploiter Pingora ?

## Pourquoi Pingora

### L'argument commercial (facteur décisif)

| Signal | axum seul | Avec Pingora |
|--------|-----------|-------------|
| Pitch entreprise | "Gateway Rust custom" | **"Construit sur Pingora — le framework proxy de Cloudflare"** |
| Positionnement concurrentiel | Même niveau que les proxies custom | **Même niveau que Cloudflare Workers, Fastly Compute** |
| Checkbox RSSI | Stack inconnue | **Éprouvé en production à 1T+ req/jour** |
| Crédibilité OSS | Framework générique | **Pedigree infrastructure de niveau mondial** |
| Unicité marché | Aucune | **Seule API gateway construite sur Pingora** |

Aucun éditeur de gateway API — Kong, Gravitee, Envoy, agentgateway — n'utilise Pingora. C'est un avantage de premier entrant en positionnement.

### L'argument technique

| Fonctionnalité | reqwest (actuel) | Connecteur Pingora |
|----------------|------------------|--------------------|
| Pool de connexions | Par instance client | **Partagé entre tous les workers** (avantage clé de Cloudflare) |
| Multiplexage H2 | Par connexion | **Multiplexage global des streams** |
| Réutilisation à l'échelle | Se dégrade >10K RPS | **Conçu pour 1T+ req/jour** |
| Proxy zero-copy | Non (copie userspace) | Kernel splice/sendfile (futur) |

À <1K RPS la différence est de 0.5ms p95. À 50K+ RPS, le pool partagé évite l'épuisement de connexions que les pools par client rencontrent.

## Options évaluées

| Option | Description | Effort | Verdict |
|--------|-------------|--------|---------|
| A : Migration complète | Remplacer axum par le serveur Pingora | 55+ pts | Rejeté — réécrit 400+ routes |
| B : Sidecar | Pingora front-proxy → stoa-gateway | 21 pts | Rejeté — hop supplémentaire, valeur faible |
| **C : Embarqué** | **Connecteur Pingora dans stoa-gateway** | **13 pts** | **Accepté** |
| D : Patterns seulement | Copier les patterns Pingora sans le crate | 0 pts | Remplacé par C |

### Pourquoi l'approche embarquée (Option C) a gagné

- **Un seul binaire** — pas de sidecar, pas de hop supplémentaire, pas de complexité de déploiement
- **Même claim marketing** — "Construit sur Pingora" est tout aussi vrai pour le connecteur embarqué
- **Valeur réelle** — le pool partagé de Pingora est le vrai avantage de Cloudflare, pas le serveur
- **Feature-gated** — `--features pingora` l'active ; le build par défaut reste reqwest (pas de dépendance cmake)
- **Incrémental** — le chemin proxy migre vers PingoraPool graduellement ; MCP/admin/auth restent sur axum

## Décision

**Embarquer `pingora-core::connectors::http::Connector` dans stoa-gateway derrière un feature flag `pingora`.**

### Architecture

```
Client → stoa-gateway (:8080)
              │
              ├─ MCP / admin / auth / OAuth → handlers axum (inchangés)
              │
              └─ Routes proxy → PingoraPool.send_request()
                                    │
                                    └─ pool de connexions partagé pingora-core
                                         → Backend (H1/H2, TLS, keepalive)
```

Un binaire. Un port. Un déploiement. Pingora gère les connexions upstream ; axum gère le routage HTTP.

### Compatibilité des phases

Notre trait `ProxyPhase` (CAB-1834) correspond 1:1 au `ProxyHttp` de Pingora :

| STOA ProxyPhase | Pingora ProxyHttp | Statut |
|-----------------|-------------------|--------|
| `request_filter` | `request_filter` | Correspondance |
| `upstream_select` | `upstream_peer` | Correspondance |
| `upstream_request_filter` | `upstream_request_filter` | Correspondance |
| `response_filter` | `upstream_response_filter` | Correspondance |
| `logging` | `logging` | Correspondance |
| `error_handler` | `error_while_proxy` | Correspondance |

Si une migration complète vers Pingora est nécessaire en v2.0, les implémentations de phases se portent directement.

## Ce que STOA apporte en plus de Pingora

| Capacité | STOA | Pingora |
|----------|------|---------|
| Parsing HTTP kernel-level via eBPF | XDP + TC (CAB-1841/1843) | Non intégré |
| Enforcement de politiques UAC au niveau kernel | BPF maps synchronisées depuis la gateway (CAB-1848) | Non intégré |
| Runtime de plugins WASM | wasmtime 42 (CAB-1644) | Non intégré |
| Protocole MCP (gateway pour agents IA) | SSE/WS/JSON-RPC complet | Non applicable |
| Fédération multi-gateway | 7 types d'adaptateurs | Non applicable |

STOA utilise Pingora pour ce qu'il fait de mieux (pool de connexions) et ajoute des couches que Pingora n'offre pas.

## Conséquences

- Image de production construite avec `FEATURES=kafka,pingora` (cmake requis dans Docker)
- `PingoraPool` disponible pour le chemin proxy ; reqwest reste en fallback
- Le build par défaut (sans features) fonctionne toujours sans dépendance cmake
- Marketing : **"STOA Gateway — propulsé par le moteur de connexions Pingora"**
- Fichier NOTICE inclut l'attribution Apache 2.0 de Pingora
- Réévaluer la migration complète en v2.0 ou à 50K+ RPS
