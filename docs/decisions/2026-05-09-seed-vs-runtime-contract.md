---
id: decision-2026-05-09-seed-vs-runtime-contract
plan_ref: docs/plans/2026-05-09-observability-data-visibility.md
phase: 1
verdict: observability-fixtures-module
---

# Decision - Seed-vs-runtime contract

## Verdict

`observability-fixtures-module`.

## Pourquoi pas un step dans le seeder core

Le seeder core reste catalog-only : tenants, gateway, APIs, plans, consumers,
MCP servers et security posture. Ajouter les evenements d'observabilite dans le
flux catalog brouillerait la frontiere entre bootstrap produit et donnees de
demo. Les verrous A5/A6 imposent en plus un marquage synthetic et une surface UI
visible, donc ces donnees doivent vivre dans un module separe, activable par
profil, et impossible a confondre avec des evenements runtime reels.

## Emplacement module

Emplacement cible Phase 2 :
`control-plane-api/scripts/seeder/observability_fixtures/audit_events.py`.

Ce module pourra etre appele par un step opt-in dedie, hors liste `STEPS`
catalog par defaut. Phase 1 ne cree pas ce fichier.

## Profile gating

| Profile         | Phase 2 fixtures                    |
|-----------------|--------------------------------------|
| dev             | enabled by default                   |
| staging-demo    | enabled by explicit opt-in env var   |
| staging-prodlike| disabled                             |
| prod            | forbidden (raise at startup)         |

## Marker structure

Marqueurs obligatoires sur la colonne JSONB existante `audit_events.details` :

- `details.synthetic = true`
- `details.source = "seed"`
- `details.fixture_batch = "observability-data-visibility-2026-05-09"`
- API exposes computed `is_synthetic` boolean.
- UI MUST surface a visible badge / chip / label / tooltip on synthetic events.

Aucune migration `audit_events` n'est autorisee par cette decision.

## Boundary

Les fixtures donnent a `dev`, `staging-demo` et aux demos une histoire
`/audit-log` lisible pendant que le pipeline runtime reste partiellement live
(`pipeline_partial` en Phase 0). Elles ne prouvent pas le chemin
`emit_audit_event -> Kafka -> consumer -> audit_events -> API -> UI`.

La preuve runtime du pipeline audit appartient a la Phase 5A, via une probe
control-plane dediee. Les fixtures Phase 2 sont donc des donnees synthetic
explicites, pas une validation end-to-end.

## Cross-refs

- Plan : `docs/plans/2026-05-09-observability-data-visibility.md`
- Decision plan : `docs/decisions/2026-05-09-observability-data-visibility.md`
- Audit findings : `docs/audits/2026-05-09-observability-data-visibility/findings.md`
- Phase 0 : `docs/audits/2026-05-09-observability-data-visibility/probe-trace-walk.md`
