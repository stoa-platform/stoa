# HEGEMON Cost Analysis — VPS vs GitHub Actions vs Mac Studio

> **Ticket**: CAB-1518 (parent: CAB-1514)
> **Last updated**: 2026-02-26

## Executive Summary

HEGEMON replaces GitHub Actions CI with OVH VPS workers running Claude Code CLI natively.
Break-even at ~15 tickets/month. Cost advantage grows linearly with volume.

## Provider Comparison

### OVH VPS 2026 Generation (Selected)

| Offer | vCPU | RAM | Storage | Price/mo | Notes |
|-------|------|-----|---------|----------|-------|
| **VPS-1** | 4 | 8 GB | 75 GB NVMe | **EUR 4.49** | Selected for HEGEMON workers |
| VPS-2 | 4 | 8 GB | 150 GB NVMe | EUR 7.49 | Extra storage only |
| VPS-3 | 6 | 16 GB | 200 GB NVMe | EUR 14.99 | If memory leak worsens |

**Datacenter**: GRA (Gravelines, France) — same as existing OVH MKS cluster.

### Hetzner Cloud (Blocked — 5 server limit reached)

| Model | vCPU | RAM | Storage | Price/mo |
|-------|------|-----|---------|----------|
| CX22 | 2 | 4 GB | 40 GB | EUR 3.29 |
| CX32 | 4 | 8 GB | 80 GB | EUR 6.80 |
| CX42 | 8 | 16 GB | 160 GB | EUR 14.80 |

Hetzner is cheaper per-spec but STOA has reached the 5-server account limit.

## Cost Model: VPS vs GitHub Actions

### GitHub Actions Current Cost

| Resource | Spec | Price | Monthly Est. |
|----------|------|-------|-------------|
| Ubuntu runner | 4 vCPU, 16 GB | $0.008/min | ~$50-80 |
| Storage | 500 MB included | Free | $0 |
| API tokens | Per-call (Anthropic) | ~$13/ticket avg | Dominant cost |

**Key insight**: The Anthropic API token cost (~$13/ticket) dominates. Runner cost is minor.
With VPS, runner cost drops to near-zero (fixed monthly), tokens remain the same.

### HEGEMON VPS Fixed Cost

| Item | Monthly Cost |
|------|-------------|
| 1x OVH VPS-1 (8GB) | EUR 4.49 |
| Bandwidth (included) | EUR 0 |
| Monitoring (Pushgateway shared) | EUR 0 |
| **Total per worker** | **EUR 4.49** |

### Break-Even Analysis

GitHub Actions runner cost per ticket (excluding API tokens):
- Average job: ~15 min = $0.12/ticket
- With queue wait + retries: ~$0.15-0.20/ticket

VPS amortized per ticket (at different volumes):
- 10 tickets/mo: EUR 4.49/10 = EUR 0.45/ticket (MORE expensive)
- 15 tickets/mo: EUR 4.49/15 = EUR 0.30/ticket (break-even)
- 30 tickets/mo: EUR 4.49/30 = EUR 0.15/ticket (equivalent)
- 50 tickets/mo: EUR 4.49/50 = EUR 0.09/ticket (3x cheaper)

**Break-even: ~15 tickets/month per VPS worker.**

### Additional VPS Advantages (Not Priced)

| Advantage | Value |
|-----------|-------|
| No queue wait | GHA runners have cold-start latency (~30s) |
| Persistent cache | git clone once, npm/cargo cache persists |
| tmux persistence | Sessions survive SSH disconnects |
| Custom tooling | Pre-installed MCP servers, watchers |
| No minute billing | VPS runs 24/7 regardless of usage |
| EU data sovereignty | Code stays in France (GRA datacenter) |

## Sizing Matrix by Worker Role

| Role | Min RAM | Recommended | VPS Offer | Notes |
|------|---------|-------------|-----------|-------|
| Single-task worker | 4 GB | 8 GB | VPS-1 | With swap + watchdog |
| Multi-session (stoa-parallel) | 8 GB | 16 GB | VPS-3 | 3-5 Claude instances |
| Build worker (Docker/Rust) | 8 GB | 16 GB | VPS-3 | cargo build is RAM-hungry |
| Light worker (docs, config) | 4 GB | 8 GB | VPS-1 | Minimal memory pressure |

## Claude Code CLI Memory Profile

| Metric | Value | Source |
|--------|-------|--------|
| Base RSS (idle) | 270-370 MB | Community benchmarks |
| Working set (active) | 1-3 GB | Typical coding session |
| Peak (memory leak) | 15-17 GB | GitHub issue #21403 |
| Time to peak | 30-120 min | Varies by task complexity |

### Mitigation Layers (in setup-claude.sh)

| Layer | Mechanism | Threshold | Effect |
|-------|-----------|-----------|--------|
| 1. Swap | 4 GB swap, swappiness=10 | N/A | Prevents OOM on spikes |
| 2. Watchdog | systemd user service | 7 GB RSS | kill -9, auto-restart |
| 3. cgroup | `claude-limited` wrapper | 6 GB MemoryMax | Kernel OOM-kills scope |
| 4. Session rotation | 45 min max sessions | Timeout | Fresh process, clean RSS |

## TCO Projection (12 months)

### Scenario A: 1 Worker, 30 tickets/month

| Item | Monthly | Annual |
|------|---------|--------|
| OVH VPS-1 | EUR 4.49 | EUR 53.88 |
| Anthropic API (~$13/ticket) | EUR 360 | EUR 4,320 |
| **Total** | **EUR 365** | **EUR 4,374** |

### Scenario B: 3 Workers, 100 tickets/month

| Item | Monthly | Annual |
|------|---------|--------|
| 3x OVH VPS-1 | EUR 13.47 | EUR 161.64 |
| Anthropic API (~$13/ticket) | EUR 1,200 | EUR 14,400 |
| **Total** | **EUR 1,214** | **EUR 14,562** |

### Scenario C: Mac Studio (comparison baseline)

| Item | One-time | Monthly (amortized 3yr) |
|------|----------|------------------------|
| Mac Studio M4 Max (64GB) | EUR 3,699 | EUR 102.75 |
| Electricity (~50W avg) | — | EUR 7 |
| **Total** | — | **EUR 110/mo** |

Mac Studio advantages: zero API cost (Max subscription), handles 5+ parallel sessions.
Mac Studio disadvantages: single point of failure, no geographic distribution, high upfront.

## Fleet Scaling Plan

| Phase | Workers | Monthly Infra | Tickets/mo | Target |
|-------|---------|---------------|------------|--------|
| Spike (now) | 1 | EUR 4.49 | 10-15 | Validate setup |
| Ramp (month 2) | 2 | EUR 8.98 | 30-50 | L3 pipeline + autopilot |
| Cruise (month 3+) | 3 | EUR 13.47 | 50-100 | Full autonomous factory |

## Existing OVH VPS Fleet

| VPS | IP | Purpose | Cost/mo |
|-----|-----|---------|---------|
| kong-standalone-gra | 51.83.45.13 | Kong DB-less + arena | EUR 4.49 |
| gravitee-standalone-gra | 54.36.209.237 | Gravitee APIM | EUR 4.49 |
| webmethods-standalone | 51.255.201.17 | webMethods trial | EUR 4.49 |
| n8n-healthchecks | 51.254.139.205 | n8n + Healthchecks | EUR 4.49 |
| **hegemon-worker-1** | TBD | **HEGEMON worker** | **EUR 4.49** |
| **Total fleet** | | | **EUR 22.45** |

## Decision

**Selected: OVH VPS-1 (EUR 4.49/mo)** — best value for HEGEMON spike.
- 4 vCPU, 8 GB RAM, 75 GB NVMe
- Datacenter: GRA (Gravelines)
- OS: Debian 12
- Sufficient for single-task worker with 4-layer memory mitigation
- Scale to VPS-3 (16 GB, EUR 14.99) if multi-session needed
