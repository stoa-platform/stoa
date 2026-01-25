# STOA Platform Governance

This document describes the governance model for STOA Platform.

## Project Leadership

### BDFL (Benevolent Dictator For Life)

**Christophe ABOULICAM** ([@PotoMitan](https://github.com/PotoMitan))

- Final decision authority on project direction
- Can veto any change (used sparingly)
- Responsible for maintaining project vision
- Ensures alignment with [STOA's mission](README.md)

The BDFL model is common for early-stage open source projects (Python, Linux).
As the community grows, governance may evolve toward a foundation model.

## Roles & Responsibilities

| Role | Rights | How to Obtain |
|------|--------|---------------|
| **Contributor** | Submit PRs, open Issues, join Discussions | First merged PR |
| **Triager** | Manage labels, assign issues, triage bugs | ~5 quality PRs + maintainer invitation |
| **Maintainer** | Merge PRs, manage releases, review RFCs | Sustained contribution + maintainer vote |
| **BDFL** | Veto, strategic direction, final authority | Founder only |

### Active Maintainers

| Name | GitHub | Area | Since |
|------|--------|------|-------|
| Christophe ABOULICAM | [@PotoMitan](https://github.com/PotoMitan) | All | 2024 |

## Decision Making

### Code Changes
- Requires PR review + **1 maintainer approval**
- CI must pass (tests, lint, security scan)

### Architecture Changes
- Requires **ADR (Architecture Decision Record)** in `docs/adr/`
- BDFL approval required

### Breaking Changes
- Requires **RFC process**:
  1. Open GitHub Discussion with `[RFC]` prefix
  2. Minimum 7-day community feedback period
  3. BDFL final decision

### Roadmap & Strategy
- BDFL decides with community input via GitHub Discussions
- Public roadmap in Linear (read-only access)

## Conflict Resolution

1. **Discussion** — Resolve in the issue/PR thread
2. **Escalation** — Ping maintainers if stuck
3. **Final Call** — BDFL decides if no consensus after reasonable discussion

All participants must follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Becoming a Maintainer

### Criteria

- [ ] 10+ merged PRs demonstrating code quality
- [ ] Active in code reviews (helpful, constructive feedback)
- [ ] 3+ months of consistent contribution
- [ ] Understanding of STOA architecture and vision

### Process

1. **Nomination** — Any maintainer can nominate a contributor
2. **Discussion** — Private maintainer discussion (1 week)
3. **Vote** — Requires unanimous approval from existing maintainers
4. **Probation** — 3-month trial period with full merge rights

### Stepping Down

Maintainers may step down at any time by notifying the BDFL.
Inactive maintainers (>6 months no activity) may be moved to emeritus status.

## Future Evolution

As STOA grows, we may evolve toward:
- **Technical Steering Committee (TSC)** for major decisions
- **Working Groups** for specific areas (Gateway, MCP, Security)
- **Foundation model** (similar to CNCF/Linux Foundation)

This governance document will be updated to reflect any changes.

## References

- [Kubernetes Governance](https://github.com/kubernetes/community/blob/master/governance.md)
- [Rust Governance](https://www.rust-lang.org/governance)
- [Node.js Governance](https://github.com/nodejs/node/blob/main/GOVERNANCE.md)

---

*Last updated: January 2025*
