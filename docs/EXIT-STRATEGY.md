# Exit Strategy — Vendor Independence & Migration Path

## Overview

STOA Platform is designed to eliminate vendor lock-in. This document outlines the exit strategy for organizations considering or using STOA, demonstrating our commitment to transparency and customer independence.

**Why we document this upfront**: We believe that documenting exit paths reduces perceived risk and builds trust. Organizations should never feel trapped by their infrastructure choices.

## Apache 2.0 License — Fork Rights

STOA Platform is licensed under Apache License 2.0, which guarantees:

- **Fork rights**: You can fork the codebase at any time
- **Modification rights**: Modify the code to meet your specific needs
- **Distribution rights**: Redistribute your modified version
- **Commercial use**: Use STOA commercially without restrictions
- **Patent protection**: Explicit patent grant from contributors

The license ensures that even if STOA Platform ceases to exist, your investment in the platform is protected. You can continue maintaining and operating your fork indefinitely.

## Data Export Capabilities

### Configuration Export

All STOA configuration is stored in a structured format and can be exported:

```bash
# Export all APIs
curl -H "Authorization: Bearer $TOKEN" \
  https://api.gostoa.dev/v1/portal/apis > apis.json

# Export all policies
curl -H "Authorization: Bearer $TOKEN" \
  https://api.gostoa.dev/v1/portal/policies > policies.json

# Export all applications
curl -H "Authorization: Bearer $TOKEN" \
  https://api.gostoa.dev/v1/portal/applications > applications.json
```

### Database Export

All Control Plane data is stored in PostgreSQL:

```bash
# Full database backup
pg_dump -h postgres-host -U postgres -d stoa_control_plane > stoa_backup.sql

# Schema-only export
pg_dump -h postgres-host -U postgres -d stoa_control_plane --schema-only > stoa_schema.sql
```

### Metrics & Logs Export

- **Prometheus metrics**: Standard Prometheus federation or remote write
- **Logs**: JSON format in stdout, compatible with any log aggregator
- **Kafka events**: Standard Kafka client export, JSON format

## Configuration Migration

### To Another STOA Instance

1. **Export configuration** (see above)
2. **Deploy new STOA instance** following [installation guide](./installation.md)
3. **Import configuration** via Control Plane API:
   ```bash
   cat apis.json | jq -c '.[]' | while read api; do
     curl -X POST -H "Authorization: Bearer $TOKEN" \
       -H "Content-Type: application/json" \
       -d "$api" https://new-api.gostoa.dev/v1/portal/apis
   done
   ```
4. **Verify migration**: Run smoke tests against new instance
5. **Update DNS/routing**: Point traffic to new instance

**Typical timeline**: 1-4 hours depending on configuration size.

### To Another API Gateway (Kong, Gravitee, etc.)

STOA uses OpenAPI 3.0 as the canonical API specification format. Migration path:

1. **Export APIs** (JSON format with OpenAPI specs embedded)
2. **Transform to target format** using provided migration scripts:
   - `scripts/migration/stoa-to-kong.py`
   - `scripts/migration/stoa-to-gravitee.py`
   - `scripts/migration/stoa-to-apigee.py`
3. **Import to target gateway** via their Admin API
4. **Reconfigure policies** (rate limits, CORS, auth) in target gateway
5. **Test parity**: Verify all APIs behave identically
6. **Gradual cutover**: Use DNS/load balancer for gradual traffic shift

**Typical timeline**: 2-8 weeks depending on:
- Number of APIs (1-10: 2 weeks, 10-50: 4 weeks, 50+: 8 weeks)
- Policy complexity (basic CORS/rate-limit: minimal, custom auth: extended)
- Testing requirements (smoke tests: days, full regression: weeks)

### To Self-Managed Infrastructure

For organizations wanting to replace STOA with custom infrastructure:

1. **Analyze STOA components**:
   - API Gateway: STOA Gateway (Rust) or Kong/Gravitee/nginx
   - Control Plane: FastAPI + PostgreSQL (reference implementation available)
   - Portal: React SPA (source code available)
2. **Extract data model**: Use exported schema as reference
3. **Implement custom logic**: Build your own control plane or use exported APIs directly
4. **Migrate incrementally**: Component-by-component approach

**Typical timeline**: 3-12 months depending on:
- Team size and expertise
- Custom requirements beyond STOA features
- Testing and validation rigor

## API Transition Paths

### Zero-Downtime Migration

Use STOA's built-in migration support:

1. **Deploy target gateway** alongside STOA
2. **Enable shadow mode** (ADR-024: Gateway Unified Modes)
   ```yaml
   mode: shadow
   shadow:
     target_url: https://new-gateway.example.com
     compare_responses: true
   ```
3. **Validate response parity** using built-in diff reports
4. **Switch traffic** when confidence is high
5. **Decommission STOA** after monitoring period

**Typical timeline**: 1-4 weeks depending on validation requirements.

### Gradual Cutover

For risk-averse migrations:

1. **Deploy target gateway**
2. **Migrate APIs one-by-one**: Start with low-traffic, non-critical APIs
3. **Monitor metrics**: Compare error rates, latency, throughput
4. **Expand gradually**: Increase traffic percentage (10% → 50% → 100%)
5. **Rollback plan**: Keep STOA active as fallback

**Typical timeline**: 4-12 weeks depending on API count and risk tolerance.

## Rollback Scenarios

### Rollback from Migration

If migration encounters issues, STOA supports instant rollback:

1. **DNS/Load Balancer switch**: Point traffic back to STOA (seconds)
2. **Configuration restore**: Import previous config export (minutes)
3. **Database restore**: PostgreSQL point-in-time recovery (minutes to hours)

**RTO (Recovery Time Objective)**: < 15 minutes for DNS-based rollback.

### Rollback from STOA Upgrade

Standard Kubernetes rollback:

```bash
# Rollback gateway
kubectl rollout undo deployment/stoa-gateway -n stoa-system

# Rollback control plane
kubectl rollout undo deployment/stoa-control-plane-api -n stoa-system

# Rollback UI
kubectl rollout undo deployment/stoa-control-plane-ui -n stoa-system
```

**RTO**: < 5 minutes.

## Timeline Expectations

### Realistic Migration Timelines

| Scenario | Timeline | Complexity |
|----------|----------|------------|
| STOA instance → STOA instance | 1-4 hours | Low |
| STOA → Kong/Gravitee (1-10 APIs) | 2-4 weeks | Medium |
| STOA → Kong/Gravitee (10-50 APIs) | 4-8 weeks | Medium-High |
| STOA → Custom infrastructure | 3-12 months | High |
| Shadow mode validation | 1-4 weeks | Low-Medium |

**Factors affecting timeline**:
- API count and complexity
- Custom policy logic
- Integration testing requirements
- Team size and expertise
- Risk tolerance (gradual vs big-bang)
- Regulatory constraints (DORA, NIS2)

### Support During Migration

STOA provides migration support through:

- **Documentation**: Migration guides for each target gateway
- **Migration scripts**: Open-source tools in `scripts/migration/`
- **Community support**: GitHub Discussions for migration questions
- **Professional services**: Available through STOA partners (optional)

## Operational Resilience (DORA / NIS2)

### Exit Strategy as Operational Resilience

DORA (Digital Operational Resilience Act) and NIS2 require organizations to maintain operational resilience, including:

- **Exit strategies** for critical service providers
- **Backup plans** for service disruption
- **Vendor lock-in mitigation**

STOA's exit strategy satisfies these requirements by providing:

1. **Clear documentation** of migration paths (this document)
2. **Data export capabilities** (configuration, metrics, logs)
3. **Open-source fork rights** (Apache 2.0 license)
4. **Interoperability** (OpenAPI 3.0 standard)
5. **Backup and restore** procedures

### ICT Third-Party Risk Management

For organizations subject to DORA Article 28 (ICT third-party risk management):

- **Contractual arrangements**: STOA's Apache 2.0 license provides explicit usage rights
- **Exit plan**: This document serves as the required exit plan
- **Data accessibility**: All data is accessible via standard protocols (PostgreSQL, Prometheus, Kafka)
- **Business continuity**: Fork rights ensure continuity even if STOA Platform ceases operations

## Disclaimers

### Migration Complexity

While STOA provides clear exit paths, we acknowledge:

- **Migration effort varies**: Timeline depends on your specific configuration
- **Testing is critical**: Thorough testing is required for production migrations
- **Custom code**: Any custom modifications to STOA require additional migration work
- **No instant migration**: Even with tools, proper planning and validation are essential

### Legal Disclaimer

This document describes technical capabilities and does not constitute:

- **A guarantee of migration success**: Migration success depends on proper planning and execution
- **Legal advice**: Consult qualified legal counsel for regulatory compliance
- **Professional services commitment**: Migration support is provided as-is through documentation and community

### Regulatory Compliance

STOA Platform provides technical capabilities that support regulatory compliance efforts (DORA, NIS2, GDPR). This does not constitute:

- **Compliance certification**: Organizations are responsible for their own compliance
- **Legal validation**: This document does not replace legal review of exit strategies
- **Audit guarantee**: Regulatory audits require organization-specific validation

## Next Steps

### Planning an Exit

If you're considering exiting STOA:

1. **Review your configuration**: Export APIs, policies, applications
2. **Choose target platform**: Self-hosted STOA, alternative gateway, or custom
3. **Assess timeline**: Use tables above as reference
4. **Develop migration plan**: Incremental vs big-bang approach
5. **Test thoroughly**: Validate in non-production environment first
6. **Execute migration**: Follow runbooks, maintain rollback capability

### Questions or Feedback

- **GitHub Issues**: [Report migration blockers](https://github.com/stoa-platform/stoa/issues)
- **GitHub Discussions**: [Ask migration questions](https://github.com/stoa-platform/stoa/discussions)
- **Documentation**: See [Migration Guides](https://docs.gostoa.dev/guides/migration/) for specific targets

## Conclusion

STOA Platform's exit strategy reflects our commitment to customer independence and transparency. By documenting exit paths upfront, we aim to:

- **Reduce perceived risk** of adopting STOA
- **Build trust** through transparency
- **Enable informed decisions** about platform adoption
- **Support operational resilience** requirements (DORA, NIS2)

Your data, your choice, your control.

---

**Last updated**: 2026-02-20
**License**: This document is part of STOA Platform (Apache 2.0)
**Feedback**: [Suggest improvements](https://github.com/stoa-platform/stoa/issues/new)
