# Compliance Disclaimer Template

Use the appropriate disclaimer in every scenario README and scenario.yaml
that references regulatory frameworks (DORA, NIS2, RGS, SecNumCloud, PSD2, etc.).

## General Template

> This demo illustrates technical capabilities that support compliance efforts.
> It does not constitute certification or a guarantee of compliance with any
> regulatory framework. Organizations should consult qualified legal counsel
> and certified auditors for official compliance evaluation.

## Financial Services (DORA/NIS2/PSD2)

> This scenario demonstrates technical capabilities relevant to DORA and NIS2
> compliance posture, including audit logging, access control, and incident
> response readiness. STOA Platform does not provide financial regulatory
> advice. Organizations must engage qualified compliance officers and auditors
> for official DORA/NIS2 assessment.

## Public Sector (RGS/SecNumCloud)

> This scenario illustrates technical capabilities that support RGS compliance
> posture, including data sovereignty controls and secure API interoperability.
> STOA Platform is not RGS-certified or SecNumCloud-qualified. Organizations
> must consult ANSSI guidelines and qualified auditors for official evaluation.

## Usage in scenario.yaml

```yaml
compliance:
  frameworks: [DORA, NIS2]
  disclaimer: |
    This demo illustrates technical capabilities that support DORA and NIS2
    compliance posture. It does not constitute certification or a guarantee
    of compliance. Consult qualified auditors for official assessment.
```
