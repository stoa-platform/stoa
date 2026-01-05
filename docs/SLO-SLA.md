# STOA Platform - Service Level Objectives (SLO) & Service Level Agreements (SLA)

> **Phase**: 9.5 - Production Readiness
> **Ticket**: CAB-110
> **Version**: 1.0
> **Last Updated**: 2026-01-05
> **Owner**: Platform Team

---

## Executive Summary

This document defines the Service Level Objectives (SLOs) and Service Level Agreements (SLAs) for the STOA API Management Platform. SLOs are internal performance targets, while SLAs represent contractual commitments to customers.

---

## 1. Service Level Objectives (SLOs)

### 1.1 Availability

| Metric | SLO Target | Measurement Period |
|--------|------------|-------------------|
| Platform Availability | 99.9% | Monthly |
| Control-Plane API Uptime | 99.9% | Monthly |
| MCP Gateway Uptime | 99.9% | Monthly |
| API Gateway Runtime | 99.95% | Monthly |

**Definition**: Percentage of time the service responds with non-5xx status codes.

```
Availability = (Total Requests - 5xx Errors) / Total Requests × 100
```

**Error Budget**: At 99.9% SLO, we allow:
- 43.2 minutes downtime per month
- 8.76 hours downtime per year

### 1.2 Latency

| Metric | p50 Target | p95 Target (SLO) | p99 Target (SLO) |
|--------|------------|------------------|------------------|
| API Response Time | < 100ms | < 500ms | < 1000ms |
| MCP Tool Invocation | < 200ms | < 1000ms | < 2000ms |
| Authentication (Keycloak) | < 150ms | < 500ms | < 1000ms |

**Definition**: Time from request received to response sent.

### 1.3 Throughput

| Metric | SLO Target | Notes |
|--------|------------|-------|
| Sustained Request Rate | > 100 req/s | Per API Gateway instance |
| Peak Request Rate | > 500 req/s | With autoscaling |
| Concurrent Connections | > 1000 | Per instance |

### 1.4 Error Rate

| Metric | SLO Target |
|--------|------------|
| Client Errors (4xx) | < 5% | (Excluding expected 401/403) |
| Server Errors (5xx) | < 0.1% |
| Total Error Rate | < 1% |

---

## 2. Service Level Agreements (SLAs)

SLAs are contractual commitments. They are intentionally less aggressive than SLOs to provide buffer.

### 2.1 Contractual SLAs

| Metric | SLA Commitment | Consequence |
|--------|----------------|-------------|
| Availability | 99.5% monthly | Service credit |
| API Latency p95 | < 1000ms | - |
| API Latency p99 | < 2000ms | - |
| Error Rate | < 1% | - |

### 2.2 Service Credits

| Availability | Credit |
|--------------|--------|
| 99.0% - 99.5% | 10% |
| 95.0% - 99.0% | 25% |
| < 95.0% | 50% |

---

## 3. Operational Objectives

### 3.1 Incident Response

| Severity | Response Time | Resolution Time (MTTR) |
|----------|---------------|------------------------|
| P1 - Critical | < 15 minutes | < 1 hour |
| P2 - High | < 30 minutes | < 4 hours |
| P3 - Medium | < 2 hours | < 24 hours |
| P4 - Low | < 8 hours | < 1 week |

**P1 Definition**: Complete service outage affecting all customers.
**P2 Definition**: Partial outage or significant degradation.
**P3 Definition**: Minor issue, workaround available.
**P4 Definition**: Cosmetic or enhancement request.

### 3.2 Deployment

| Metric | Target |
|--------|--------|
| Deployment Success Rate | > 99% |
| Rollback Time | < 5 minutes |
| Deployment Frequency | Daily (Dev/Staging) |
| Change Lead Time | < 24 hours |

### 3.3 Recovery

| Metric | Target |
|--------|--------|
| RTO (Recovery Time Objective) | < 1 hour |
| RPO (Recovery Point Objective) | < 1 hour (Vault/AWX backups) |
| Disaster Recovery Test | Quarterly |

---

## 4. Monitoring & Alerting

### 4.1 Key Metrics

```yaml
# Prometheus queries for SLO metrics

# Availability
slo:api_availability:ratio =
  sum(rate(http_requests_total{status!~"5.."}[5m])) /
  sum(rate(http_requests_total[5m]))

# Latency p95
slo:api_latency_p95:seconds =
  histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Latency p99
slo:api_latency_p99:seconds =
  histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Error Rate
slo:api_error_rate:ratio =
  sum(rate(http_requests_total{status=~"5.."}[5m])) /
  sum(rate(http_requests_total[5m]))
```

### 4.2 Alert Thresholds

| Alert | Condition | Severity |
|-------|-----------|----------|
| SLOAvailabilityBreach | availability < 99.9% for 5m | Critical |
| SLOLatencyP95Breach | p95 > 500ms for 5m | Warning |
| SLOLatencyP99Breach | p99 > 1000ms for 5m | Warning |
| SLOErrorRateBreach | error_rate > 0.1% for 5m | Critical |
| ErrorBudgetLow | budget_remaining < 20% | Warning |
| ErrorBudgetExhausted | budget_remaining < 5% | Critical |

### 4.3 Notification Channels

| Severity | Channel |
|----------|---------|
| Critical | Slack #ops-alerts + PagerDuty |
| Warning | Slack #ops-alerts |
| Info | Slack #platform-team |

---

## 5. Error Budget Policy

### 5.1 Error Budget Calculation

```
Monthly Error Budget = (1 - SLO) × Total Minutes in Month
                     = (1 - 0.999) × 43,200
                     = 43.2 minutes
```

### 5.2 Error Budget Spending Rules

| Budget Remaining | Action |
|-----------------|--------|
| > 50% | Normal operations, new features OK |
| 20-50% | Caution, prioritize reliability |
| 5-20% | Freeze non-critical deployments |
| < 5% | All hands on reliability |

---

## 6. SLO by Component

### 6.1 Control-Plane API

| Endpoint | Availability | Latency p95 |
|----------|--------------|-------------|
| `/health` | 99.99% | < 100ms |
| `/v1/apis` | 99.9% | < 500ms |
| `/v1/tenants` | 99.9% | < 500ms |
| `/v1/deployments` | 99.9% | < 1000ms |

### 6.2 MCP Gateway

| Endpoint | Availability | Latency p95 |
|----------|--------------|-------------|
| `/health` | 99.99% | < 100ms |
| `/mcp/v1/tools` | 99.9% | < 500ms |
| `/mcp/v1/tools/{}/invoke` | 99.5% | < 2000ms |

### 6.3 API Gateway Runtime

| Metric | Target |
|--------|--------|
| Availability | 99.95% |
| Latency p95 | < 300ms overhead |
| Rate Limiting Accuracy | 99% |

### 6.4 Supporting Services

| Service | Availability |
|---------|--------------|
| Keycloak (Auth) | 99.9% |
| PostgreSQL (RDS) | 99.95% |
| Vault | 99.9% |
| Kafka/Redpanda | 99.9% |

---

## 7. Reporting

### 7.1 SLO Dashboard

- **Location**: Grafana → STOA → SLO Dashboard
- **Refresh**: Real-time (5s)
- **Historical**: 30-day rolling window

### 7.2 Monthly Report Contents

1. Availability percentage
2. Latency percentiles trend
3. Error budget consumption
4. Incident count by severity
5. MTTR analysis
6. Top 5 error sources

### 7.3 Review Cadence

| Meeting | Frequency | Participants |
|---------|-----------|--------------|
| SLO Review | Weekly | Platform Team |
| SLA Review | Monthly | Engineering + Product |
| Quarterly Business Review | Quarterly | All Stakeholders |

---

## 8. Appendix

### 8.1 Glossary

| Term | Definition |
|------|------------|
| **SLI** | Service Level Indicator - The metric being measured |
| **SLO** | Service Level Objective - Internal target |
| **SLA** | Service Level Agreement - Contractual commitment |
| **MTTR** | Mean Time To Recovery |
| **MTTD** | Mean Time To Detection |
| **RTO** | Recovery Time Objective |
| **RPO** | Recovery Point Objective |

### 8.2 References

- [Google SRE Book - SLOs](https://sre.google/sre-book/service-level-objectives/)
- [STOA Runbooks](./runbooks/README.md)
- [Load Testing Guide](../tests/load/README.md)

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-12-28 | Platform Team | Initial release |
