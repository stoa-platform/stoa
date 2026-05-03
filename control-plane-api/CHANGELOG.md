# Changelog

## [1.12.2](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.12.1...control-plane-api-v1.12.2) (2026-05-02)


### Bug Fixes

* adopt catalog git identity collisions ([#2665](https://github.com/stoa-platform/stoa/issues/2665)) ([8a28158](https://github.com/stoa-platform/stoa/commit/8a2815886a35dd7412d8d0c4a6829e26558deffa))
* allow catalog identity reuse after soft delete ([9b1026a](https://github.com/stoa-platform/stoa/commit/9b1026a7a36af3e27b408e5fc932900f682c2e20))
* **api:** block webMethods-incompatible OpenAPI schemas ([11b519a](https://github.com/stoa-platform/stoa/commit/11b519a84db7ca1ea5eb1a1b2d84eb8ebcac22f3))
* **api:** preserve deployment status during gateway outages ([2275757](https://github.com/stoa-platform/stoa/commit/227575753281387150abe4891421e7c58a7067bd))
* **gateways:** expose webMethods URLs for all envs ([#2668](https://github.com/stoa-platform/stoa/issues/2668)) ([e23f5e2](https://github.com/stoa-platform/stoa/commit/e23f5e26756abf276063bcf7545fee0a0b96ff42))
* **gateways:** isolate webMethods staging target ([#2664](https://github.com/stoa-platform/stoa/issues/2664)) ([15ed930](https://github.com/stoa-platform/stoa/commit/15ed930ee77e8269ddc2655533f8b4ee97c521c3))
* project catalog OpenAPI specs from Git ([754a687](https://github.com/stoa-platform/stoa/commit/754a687c6e8e3c6579ce24e37df84c493cd9b15b))
* reconcile prod promotion migrations ([149396c](https://github.com/stoa-platform/stoa/commit/149396c0ecae26ea3129e6592072c43ba72ee332))
* **ui:** clarify gateway URL surfaces (CAB-2240) ([0665591](https://github.com/stoa-platform/stoa/commit/0665591e0e0e8d11b544ab560a683d94ddbd4041))
* use Git OpenAPI specs as API truth ([0f6c2ca](https://github.com/stoa-platform/stoa/commit/0f6c2cae7d9ae0e83e696bdf3c5525a8839280a7))

## [1.12.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.12.0...control-plane-api-v1.12.1) (2026-05-02)


### Bug Fixes

* **api:** backfill gateway external urls ([#2662](https://github.com/stoa-platform/stoa/issues/2662)) ([7871024](https://github.com/stoa-platform/stoa/commit/7871024a67752779a442b036d63cd240df1fc5f7))

## [1.12.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.11.3...control-plane-api-v1.12.0) (2026-05-01)


### Features

* **api:** add catalog release versioning ([e3bd495](https://github.com/stoa-platform/stoa/commit/e3bd4956623003945f4b7443f1e60af998ad6b18))


### Bug Fixes

* **api:** reconcile gateway deployment targets ([#2651](https://github.com/stoa-platform/stoa/issues/2651)) ([47ea94c](https://github.com/stoa-platform/stoa/commit/47ea94c81cbf71f2c4bf98c909eb6c4d398d9a70))
* **gateway:** isolate webMethods URLs by environment ([c804b9b](https://github.com/stoa-platform/stoa/commit/c804b9b6b37fb3cf4d7cbc9aa74d107df40c4499))
* **gateways:** surface external URLs for link and connect ([#2642](https://github.com/stoa-platform/stoa/issues/2642)) ([132de10](https://github.com/stoa-platform/stoa/commit/132de10d7515fc15d7c03a70ab38fa3753ee6a42))
* **portal:** expose provider plans for subscriptions ([#2652](https://github.com/stoa-platform/stoa/issues/2652)) ([497bb7d](https://github.com/stoa-platform/stoa/commit/497bb7dbb674b829c06734ad4bc800aa10c8837e))
* **sync:** enforce route ack step consistency ([#2654](https://github.com/stoa-platform/stoa/issues/2654)) ([4c7e1e6](https://github.com/stoa-platform/stoa/commit/4c7e1e641b5bf4497a349dc9e40c90a02b98290f))

## [1.11.3](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.11.2...control-plane-api-v1.11.3) (2026-05-01)


### Bug Fixes

* **api:** fail-closed env + base_domain validators (cab-2199 3-a) ([1e4d845](https://github.com/stoa-platform/stoa/commit/1e4d8454eb4bb2c8c65f3849abb45641fc699623))
* **api:** harden snapshot conflict scanner (cab-2199 3-b) ([3e08fef](https://github.com/stoa-platform/stoa/commit/3e08fef35ddf8a3e2b16e294f4b4b101185f4a91))
* **subscriptions:** align Portal Console Gateway UAC flow ([61b8f2e](https://github.com/stoa-platform/stoa/commit/61b8f2edf5a8b40c714c39e938505d7198e94d72))

## [1.11.2](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.11.1...control-plane-api-v1.11.2) (2026-05-01)


### Bug Fixes

* **api:** backfill API catalog GitOps state ([c16c0ae](https://github.com/stoa-platform/stoa/commit/c16c0aee7c85967e947b2fac04409c9361db57f4))
* **api:** preflight admin gateway deployments ([#2628](https://github.com/stoa-platform/stoa/issues/2628)) ([6df062c](https://github.com/stoa-platform/stoa/commit/6df062c55ad56422c27595286eabd17f7fc299fc))
* **api:** preserve synced route steps on failed re-ack ([#2626](https://github.com/stoa-platform/stoa/issues/2626)) ([f9e812d](https://github.com/stoa-platform/stoa/commit/f9e812d50aff0a3a4bf79e34de2baf32b50b1d73))
* **api:** reconcile catalog gateway deployments ([#2632](https://github.com/stoa-platform/stoa/issues/2632)) ([6c01cae](https://github.com/stoa-platform/stoa/commit/6c01cae603d2a786189355923dc43eb0567b9727))

## [1.11.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.11.0...control-plane-api-v1.11.1) (2026-04-27)


### Bug Fixes

* **api:** allow recreating archived tenant after failed bootstrap (CAB-2196) ([#2611](https://github.com/stoa-platform/stoa/issues/2611)) ([677787e](https://github.com/stoa-platform/stoa/commit/677787ee4240e75cf0654e93170975e0cb186d96))
* **api:** pin KC auth to master realm via user_realm_name (CAB-2195) ([#2610](https://github.com/stoa-platform/stoa/issues/2610)) ([22e1723](https://github.com/stoa-platform/stoa/commit/22e172336c33269615d650153bea9fc6764fbfe7))

## [1.11.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.10.2...control-plane-api-v1.11.0) (2026-04-27)


### Features

* **api-creation-gitops:** Phase 4-2 — orchestration (create_api flow + reconciler + handler) ([#2608](https://github.com/stoa-platform/stoa/issues/2608)) ([a8fc1ae](https://github.com/stoa-platform/stoa/commit/a8fc1ae5defa198523e95b754a52c7705694332b))
* **api:** phase 3 scaffold for gitops create-api rewrite ([#2605](https://github.com/stoa-platform/stoa/issues/2605)) ([d4a182e](https://github.com/stoa-platform/stoa/commit/d4a182e4e94476c53645765d7d9b54af90d3f9f7))
* **api:** phase 4-1 primitives for gitops create-api rewrite ([#2607](https://github.com/stoa-platform/stoa/issues/2607)) ([115e433](https://github.com/stoa-platform/stoa/commit/115e4339ad2cc8dae95bc8c3641656fe6e419ec5))

## [1.10.2](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.10.1...control-plane-api-v1.10.2) (2026-04-27)


### Bug Fixes

* **uac:** remove stale spec_hash from hand-authored demo contract ([#2598](https://github.com/stoa-platform/stoa/issues/2598)) ([e9af40c](https://github.com/stoa-platform/stoa/commit/e9af40c9a37d35767b90d286b4e06cb78cf0c023))

## [1.10.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.10.0...control-plane-api-v1.10.1) (2026-04-26)


### Bug Fixes

* **deployments:** materialize UAC catalog contract ([880682d](https://github.com/stoa-platform/stoa/commit/880682dc7a9ac4a7e39456e7309f4907abd5d83f))

## [1.10.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.9.0...control-plane-api-v1.10.0) (2026-04-26)


### Features

* **uac:** enrich MCP tool description with endpoint.llm metadata ([#2585](https://github.com/stoa-platform/stoa/issues/2585)) ([82c5ebb](https://github.com/stoa-platform/stoa/commit/82c5ebb4934b25e4ee0ee3d32d8679a513b2139f))


### Bug Fixes

* **deployments:** expose Git desired state freshness ([#2583](https://github.com/stoa-platform/stoa/issues/2583)) ([0da3768](https://github.com/stoa-platform/stoa/commit/0da37680380f8bd4ef554470ff677a5364a1c222))

## [1.9.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.7...control-plane-api-v1.9.0) (2026-04-26)


### Features

* **api:** add Console deployment contract endpoint ([#2565](https://github.com/stoa-platform/stoa/issues/2565)) ([4f1996d](https://github.com/stoa-platform/stoa/commit/4f1996d3d49d0ab993d0ae1601e8d3f0f2d60bf7))


### Bug Fixes

* **api:** keep synced route ack stable ([#2567](https://github.com/stoa-platform/stoa/issues/2567)) ([f25e79a](https://github.com/stoa-platform/stoa/commit/f25e79abd69ce9f89d2182fe064230593416eaeb))
* **api:** preflight gateway deployment specs ([#2577](https://github.com/stoa-platform/stoa/issues/2577)) ([549470b](https://github.com/stoa-platform/stoa/commit/549470b79c42a9ec02172f742342ca8abb09ce2e))

## [1.8.7](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.6...control-plane-api-v1.8.7) (2026-04-25)


### Bug Fixes

* **demo:** bridge route sync for smoke ([#2553](https://github.com/stoa-platform/stoa/issues/2553)) ([f6d6497](https://github.com/stoa-platform/stoa/commit/f6d649728ae04412ea454d68d5c4f003192dffe9))

## [1.8.6](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.5...control-plane-api-v1.8.6) (2026-04-25)


### Bug Fixes

* **cp-api:** deliver routes to self-registered agents by hostname ([7926b0d](https://github.com/stoa-platform/stoa/commit/7926b0de07439ab02a6a9aecabb3804a92663f6e))
* **demo:** align smoke payloads with runtime models ([#2549](https://github.com/stoa-platform/stoa/issues/2549)) ([0e49393](https://github.com/stoa-platform/stoa/commit/0e4939343ec349b31880caac912f3c61f841e033))

## [1.8.5](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.4...control-plane-api-v1.8.5) (2026-04-24)


### Bug Fixes

* **demo:** add bounded auth bypass for smoke ([#2546](https://github.com/stoa-platform/stoa/issues/2546)) ([1e55659](https://github.com/stoa-platform/stoa/commit/1e55659546aeab2ed59abed985138b126fcc09b2))

## [1.8.4](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.3...control-plane-api-v1.8.4) (2026-04-24)


### Bug Fixes

* **api:** prevent GET /v1/admin/gateways 500 on enum drift (CAB-2169) ([#2544](https://github.com/stoa-platform/stoa/issues/2544)) ([6719957](https://github.com/stoa-platform/stoa/commit/671995743105d8c4cf0b3f41c70b242de84fc976))

## [1.8.3](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.2...control-plane-api-v1.8.3) (2026-04-24)


### Bug Fixes

* **demo:** make AT-0 health probes observable ([#2541](https://github.com/stoa-platform/stoa/issues/2541)) ([90ef5a7](https://github.com/stoa-platform/stoa/commit/90ef5a7deafdaa2aed8117427ae27282b9902b9f))

## [1.8.2](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.1...control-plane-api-v1.8.2) (2026-04-24)


### Bug Fixes

* **demo:** return one-time api key for smoke ([#2535](https://github.com/stoa-platform/stoa/issues/2535)) ([a18ed9a](https://github.com/stoa-platform/stoa/commit/a18ed9a7c4266d8addeb095a2939cbbd6a463e9e))

## [1.8.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.8.0...control-plane-api-v1.8.1) (2026-04-24)


### Bug Fixes

* **cp-1:** close 5 P2 cleanup findings (CP-1 CLOSED) ([#2500](https://github.com/stoa-platform/stoa/issues/2500)) ([48360db](https://github.com/stoa-platform/stoa/commit/48360dbb851d49a7bb971a3a4cabb134eb9623f7))
* **cp-api:** close CP-1 P0 batch on git provider rewrite ([#2496](https://github.com/stoa-platform/stoa/issues/2496)) ([4ed8085](https://github.com/stoa-platform/stoa/commit/4ed80850b066a160e2b3fe501db9efa497599728))
* **cp-api:** close CP-1 P1 hardening batch ([#2499](https://github.com/stoa-platform/stoa/issues/2499)) ([b58bdca](https://github.com/stoa-platform/stoa/commit/b58bdca4084c31458ec29a11ae8b6939ff3d88b8))

## [1.8.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.7.0...control-plane-api-v1.8.0) (2026-04-22)


### Features

* **api:** demo reset CLI entry point (CAB-2149 c/3) ([#2468](https://github.com/stoa-platform/stoa/issues/2468)) ([f26a03b](https://github.com/stoa-platform/stoa/commit/f26a03b1a73043418cf10942ba755780b406b4c1))
* **api:** demo reset service with tenant isolation (CAB-2149 b/3) ([#2467](https://github.com/stoa-platform/stoa/issues/2467)) ([4674fbf](https://github.com/stoa-platform/stoa/commit/4674fbf8625173e964abc0d2fc6912711c7749a6))

## [1.7.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.6.4...control-plane-api-v1.7.0) (2026-04-22)


### Features

* **api:** demo seed fixtures (CAB-2149 a/3) ([#2466](https://github.com/stoa-platform/stoa/issues/2466)) ([1c28332](https://github.com/stoa-platform/stoa/commit/1c283329d6184347114cc66a7794f3e5eaac62a7))


### Bug Fixes

* **api:** close GitProvider leaks in iam_sync + deployment orch (CAB-1889) ([#2469](https://github.com/stoa-platform/stoa/issues/2469)) ([b6607f3](https://github.com/stoa-platform/stoa/commit/b6607f35050d38bd38605653de765640e6312d56))
* **api:** close OpenAPI contract gaps blocking UI-1-Wave2 (CAB-2159) ([#2473](https://github.com/stoa-platform/stoa/issues/2473)) ([c6abef8](https://github.com/stoa-platform/stoa/commit/c6abef8f2cef776d09db34f8a3ea1c9628416b5d))

## [1.6.4](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.6.3...control-plane-api-v1.6.4) (2026-04-22)


### Bug Fixes

* **security:** tighten CORS methods/headers + strip localhost in prod (CAB-2142) ([#2450](https://github.com/stoa-platform/stoa/issues/2450)) ([cd0635a](https://github.com/stoa-platform/stoa/commit/cd0635aec2bdbd0cc28c1a52c596d05ade6f7160))

## [1.6.3](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.6.2...control-plane-api-v1.6.3) (2026-04-21)


### Bug Fixes

* **security:** gate sensitive debug flags on prod boot (CAB-2145) ([#2452](https://github.com/stoa-platform/stoa/issues/2452)) ([811e8ec](https://github.com/stoa-platform/stoa/commit/811e8ecfeff502d879f2810e10296cba700c2d94))
* **security:** rate-limit keying collapses all JWT users (CAB-2146) ([#2449](https://github.com/stoa-platform/stoa/issues/2449)) ([1c99a62](https://github.com/stoa-platform/stoa/commit/1c99a62188aec0344634a0853aa1dbbf3a019391))

## [1.6.2](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.6.1...control-plane-api-v1.6.2) (2026-04-20)


### Bug Fixes

* **api:** honor github catalog repo for override lookup (CAB-1889) ([#2445](https://github.com/stoa-platform/stoa/issues/2445)) ([a69da30](https://github.com/stoa-platform/stoa/commit/a69da302ceec34fadc3006b172bea1f08cc6aee6))
* **api:** preserve spec.tags and spec.category in catalog normalization (CAB-2135) ([#2447](https://github.com/stoa-platform/stoa/issues/2447)) ([3519aa7](https://github.com/stoa-platform/stoa/commit/3519aa73dacf9f5fc119b215da6c7376650ed8c4))

## [1.6.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.6.0...control-plane-api-v1.6.1) (2026-04-20)


### Bug Fixes

* **api:** drop gitlab _project deref in catalog sync (CAB-1889) ([#2439](https://github.com/stoa-platform/stoa/issues/2439)) ([0c01ba3](https://github.com/stoa-platform/stoa/commit/0c01ba318e0794b7a5deb1281110746e5e38ba62))
* **api:** scrub stack traces + axios/follow-redirects bumps (CAB-2138) ([#2441](https://github.com/stoa-platform/stoa/issues/2441)) ([ab2a26b](https://github.com/stoa-platform/stoa/commit/ab2a26b303c7baf86a8eea77f62edd3d8a534b8c))

## [1.6.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.5.1...control-plane-api-v1.6.0) (2026-04-19)


### Features

* **cp-api:** /v1/internal/catalog/apis/expanded overlay (CAB-2113) ([#2415](https://github.com/stoa-platform/stoa/issues/2415)) ([28a3a17](https://github.com/stoa-platform/stoa/commit/28a3a17fccfbd8c571f8b628dd1b1f2ee9168287))
* **gateway:** tool-expansion observability + runbook (CAB-2113 PR3) ([#2422](https://github.com/stoa-platform/stoa/issues/2422)) ([cd99417](https://github.com/stoa-platform/stoa/commit/cd9941741c234f3b6fd0b6bde4afad480615aa27))


### Bug Fixes

* **mcp:** restore temperature=0 + add tool-name bijection in phase05 bench (CAB-2116) ([#2428](https://github.com/stoa-platform/stoa/issues/2428)) ([0d6eccc](https://github.com/stoa-platform/stoa/commit/0d6eccc75830b29edccc79a963842982ec643b24))

## [1.5.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.5.0...control-plane-api-v1.5.1) (2026-04-17)


### Bug Fixes

* **api:** restore CP API Integration Tests (unblock release 1.5.1) ([#2406](https://github.com/stoa-platform/stoa/issues/2406)) ([3f05a00](https://github.com/stoa-platform/stoa/commit/3f05a00547fef8cc10e1822e18666bdd387cff9c))
* **api:** split Keycloak public vs internal URL (CAB-2094) ([#2399](https://github.com/stoa-platform/stoa/issues/2399)) ([d300949](https://github.com/stoa-platform/stoa/commit/d300949ba9317cae4d5fed238156b67d47f5e4e6))

## [1.5.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.4.1...control-plane-api-v1.5.0) (2026-04-16)


### Features

* **api:** drop execution_logs table (CAB-1977) [MIGRATION ONLY] ([#2297](https://github.com/stoa-platform/stoa/issues/2297)) ([a3b8454](https://github.com/stoa-platform/stoa/commit/a3b84545b0986f96fc5671df1dfb0fe643151969))


### Bug Fixes

* **api:** alembic 094 paramstyle — CAST(:desired_state AS JSONB) (CAB-1977) ([#2390](https://github.com/stoa-platform/stoa/issues/2390)) ([e95e64a](https://github.com/stoa-platform/stoa/commit/e95e64a324afe803736a8fc8bdc8004b4c790866))
* **api:** alembic merge migration 095 to reconcile heads 092 + 094 (CAB-1977) ([#2386](https://github.com/stoa-platform/stoa/issues/2386)) ([d0c7ca8](https://github.com/stoa-platform/stoa/commit/d0c7ca838b51a4c9da7790f7f9f4abb1e2d44bfc))
* **api:** enforce JWT issuer + cache Keycloak public key (CAB-2082) ([#2393](https://github.com/stoa-platform/stoa/issues/2393)) ([9fef152](https://github.com/stoa-platform/stoa/commit/9fef15230c065f8e8fc2113c53d9776a74ce4655))
* **api:** exclude CHANGELOG.md from Parzival literal scan (CAB-2083) ([#2396](https://github.com/stoa-platform/stoa/issues/2396)) ([d0744d1](https://github.com/stoa-platform/stoa/commit/d0744d19f537d6359a396e914071622d24af328f))
* **api:** isolate Kafka consumers from test boot path (CAB-2085) ([#2395](https://github.com/stoa-platform/stoa/issues/2395)) ([1b7daf8](https://github.com/stoa-platform/stoa/commit/1b7daf882d83235bd6f71d5008cedf8de996a4fe))
* **api:** restore CP API CI green — schema + seeder + test fixtures ([#2387](https://github.com/stoa-platform/stoa/issues/2387)) ([61dcf56](https://github.com/stoa-platform/stoa/commit/61dcf5671be2c57041f03b1610a71eeb54c1dd91))
* **e2e:** kill Parzival@2026! hardcoded fallback (CAB-2083) ([#2394](https://github.com/stoa-platform/stoa/issues/2394)) ([4b211e0](https://github.com/stoa-platform/stoa/commit/4b211e08d3a9fdf74ae75f5e703edbda3c2f590d))

## [1.4.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.4.0...control-plane-api-v1.4.1) (2026-04-15)


### Bug Fixes

* **ui:** Gateway Dashboard Inconsistencies — unified status, remove mocks, aggregated multi-gateway overview (CAB-1887) ([#2365](https://github.com/stoa-platform/stoa/issues/2365)) ([db2c4af](https://github.com/stoa-platform/stoa/commit/db2c4aff42b583251a02570368b92c6b3f6fadb6))

## [1.4.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.3.1...control-plane-api-v1.4.0) (2026-04-15)


### Features

* **local:** Tilt + k3d local environment + Alembic migration fixes ([#2359](https://github.com/stoa-platform/stoa/issues/2359)) ([86392f8](https://github.com/stoa-platform/stoa/commit/86392f891154071cc2201a26a85967fd91065c62))


### Bug Fixes

* **api:** resolve mypy no-any-return in clients (CAB-2053 phase 2) ([#2329](https://github.com/stoa-platform/stoa/issues/2329)) ([75bc669](https://github.com/stoa-platform/stoa/commit/75bc669ec2220c1167359bf1705c67dd00c1ed8f))
* **api:** skip flaky openapi snapshot tests blocking CD (CAB-2055) ([#2333](https://github.com/stoa-platform/stoa/issues/2333)) ([e9e4239](https://github.com/stoa-platform/stoa/commit/e9e4239c5b4c7b3f17c142ba30ef4e2af6bb71ef))

## [1.3.1](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.3.0...control-plane-api-v1.3.1) (2026-04-11)


### Bug Fixes

* **api:** resolve 24 failing tests on main (CI P0) ([#2293](https://github.com/stoa-platform/stoa/issues/2293)) ([5e35661](https://github.com/stoa-platform/stoa/commit/5e35661421f3030d7c73751eebd72981cbba1a5f))
* **security:** follow-up to CAB-2052 — 3 remaining leaks + ArgoCD spam ([#2302](https://github.com/stoa-platform/stoa/issues/2302)) ([e6a4b38](https://github.com/stoa-platform/stoa/commit/e6a4b38d92ff209a2c51de33489ef3cdbeaa3c3a))
* **security:** remove default credentials, enforce Vault (CAB-2052) ([#2296](https://github.com/stoa-platform/stoa/issues/2296)) ([c953ae3](https://github.com/stoa-platform/stoa/commit/c953ae3cc63f74aebb7dad2fbe8546ced52cde0c))

## [1.3.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.2.0...control-plane-api-v1.3.0) (2026-04-09)


### Features

* **api:** add GitOps observability metrics (CAB-2026) ([#2266](https://github.com/stoa-platform/stoa/issues/2266)) ([23c22d7](https://github.com/stoa-platform/stoa/commit/23c22d77ca70d57bdeae8301102dcbc216a06679))
* **api:** add GitSyncWorker for async Git commits on API CRUD (CAB-2012) ([#2261](https://github.com/stoa-platform/stoa/issues/2261)) ([f1f9056](https://github.com/stoa-platform/stoa/commit/f1f9056e80aaa829b77f1025bb951405b134d7fc))
* **api:** add write methods to GitHubService (CAB-2011) ([#2258](https://github.com/stoa-platform/stoa/issues/2258)) ([0dec963](https://github.com/stoa-platform/stoa/commit/0dec963e57f1e8ccfc0f93f47ac5b7ed769c99cd))
* **api:** multi-environment support with per-API overrides (CAB-2015) ([#2265](https://github.com/stoa-platform/stoa/issues/2265)) ([a57bcf8](https://github.com/stoa-platform/stoa/commit/a57bcf8116252e273ae9a8fbbdfb3c04afff5b46))
* **api:** reverse-sync drift detection + auto-repair Git↔Gateway (CAB-2016) ([#2264](https://github.com/stoa-platform/stoa/issues/2264)) ([a7ab6bc](https://github.com/stoa-platform/stoa/commit/a7ab6bc30d52cd551fbabd1577a2d2377c9645ca))
* **api:** seed gateway_deployments for catalog APIs (CAB-2034) ([#2278](https://github.com/stoa-platform/stoa/issues/2278)) ([81bfee7](https://github.com/stoa-platform/stoa/commit/81bfee76dc07d5ebad841c2cdd456526fc994e0b))


### Bug Fixes

* **api:** add api_catalog_id to migration 094 desired_state (CAB-2034) ([#2279](https://github.com/stoa-platform/stoa/issues/2279)) ([7446f74](https://github.com/stoa-platform/stoa/commit/7446f74f8bd8b953138db8ad438c130f544fb446))
* **api:** align seeder url_path with gateway route prefix (CAB-2034) ([#2280](https://github.com/stoa-platform/stoa/issues/2280)) ([bcf2ffb](https://github.com/stoa-platform/stoa/commit/bcf2ffb2fa58c2fb03cbe70e6d90cf7e02eed41e))
* **api:** Observability RBAC — tenant isolation Phase 1 (CAB-2027) ([#2272](https://github.com/stoa-platform/stoa/issues/2272)) ([2e71af6](https://github.com/stoa-platform/stoa/commit/2e71af6ffa7042db4a5ededae75e409dff0ec1f3))
* **api:** observability RBAC phase 2 (CAB-2031, CAB-2032) ([#2274](https://github.com/stoa-platform/stoa/issues/2274)) ([407438b](https://github.com/stoa-platform/stoa/commit/407438ba3ad1761e3d53f31219389164ee15afba))
* **api:** use 'online' enum value for gateway status (CAB-2007) ([#2254](https://github.com/stoa-platform/stoa/issues/2254)) ([f2d4753](https://github.com/stoa-platform/stoa/commit/f2d47533e4966db825b2b93cb344dcdf4fd5a5f8))
* **api:** use JSON object for gateway visibility column (CAB-2007) ([#2252](https://github.com/stoa-platform/stoa/issues/2252)) ([c3a4676](https://github.com/stoa-platform/stoa/commit/c3a4676e1a1909fd7f75aa73c10a1016d2b2c973))
* **security:** upgrade base image packages to fix OpenSSL CVEs ([#2256](https://github.com/stoa-platform/stoa/issues/2256)) ([c451415](https://github.com/stoa-platform/stoa/commit/c45141526e567c3357e61b24d4f14ea8abd645fc))

## [1.2.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.1.0...control-plane-api-v1.2.0) (2026-04-08)


### Features

* add target_gateway_url to gateway detail panel ([#2069](https://github.com/stoa-platform/stoa/issues/2069)) ([c07557f](https://github.com/stoa-platform/stoa/commit/c07557feb537c2f029909763e62cf719eacb18db))
* **api,gateway:** generation-based sync reconciliation (CAB-1950) ([#2132](https://github.com/stoa-platform/stoa/issues/2132)) ([d78db2b](https://github.com/stoa-platform/stoa/commit/d78db2b087becfd7a8ae4bf6862f23f5fbb5545e))
* **api,portal:** admin visibility for seeded portal data ([#2232](https://github.com/stoa-platform/stoa/issues/2232)) ([3531aa5](https://github.com/stoa-platform/stoa/commit/3531aa544a326c1b9e4f87975d6e6364f640dd16))
* **api,ui,gateway:** traffic seed link/connect + Call Flow interactive filters (CAB-1997) ([#2228](https://github.com/stoa-platform/stoa/issues/2228)) ([627dcbe](https://github.com/stoa-platform/stoa/commit/627dcbe03ec0c0259ce56bbe9e40dac5f3890c53))
* **api,ui:** add ui_url field to GatewayInstance for admin UI links (CAB-1953) ([#2149](https://github.com/stoa-platform/stoa/issues/2149)) ([725dffa](https://github.com/stoa-platform/stoa/commit/725dffa72e55e05d2befe77644d3985f18ae865d))
* **api,ui:** gitops tenant auto-provision + admin cross-tenant API view ([#2114](https://github.com/stoa-platform/stoa/issues/2114)) ([8cebf8b](https://github.com/stoa-platform/stoa/commit/8cebf8b5352c20a215c10414a2762e67b69bfbc4))
* **api,ui:** proxy gateway MCP tools to Console via CP API (CAB-1962) ([#2154](https://github.com/stoa-platform/stoa/issues/2154)) ([11e3d90](https://github.com/stoa-platform/stoa/commit/11e3d9023d114abd8dd518cdeb51e88e35f7e3a9))
* **api:** add GIT_PROVIDER + GITHUB_* to K8s configmap and deploy envs (CAB-1890) ([#2063](https://github.com/stoa-platform/stoa/issues/2063)) ([92c94d3](https://github.com/stoa-platform/stoa/commit/92c94d3bd68dc7f7378d794f0f4c0dfefed58a1f))
* **api:** add GitHub webhook endpoint with HMAC-SHA256 (CAB-1890) ([#2049](https://github.com/stoa-platform/stoa/issues/2049)) ([966da8c](https://github.com/stoa-platform/stoa/commit/966da8ca5a66d1bb9b1b117884b259778cf81d9d))
* **api:** add GitHubService(GitProvider) with PyGithub (CAB-1890) ([#2046](https://github.com/stoa-platform/stoa/issues/2046)) ([ef2edc5](https://github.com/stoa-platform/stoa/commit/ef2edc5876e0e690a388bcde8bfa4b5c30ab48a6))
* **api:** add GitProvider ABC + factory + GitHub config (CAB-1890) ([#2040](https://github.com/stoa-platform/stoa/issues/2040)) ([9785668](https://github.com/stoa-platform/stoa/commit/97856686241571ee0977e21b5d477fa47596104b))
* **api:** add SyncStepTracker + sync_steps column (CAB-1945) ([#2129](https://github.com/stoa-platform/stoa/issues/2129)) ([440117f](https://github.com/stoa-platform/stoa/commit/440117f3e0c90ca516bb1ad1233c33a91cbbf2c9))
* **api:** gateway enabled flag + visibility + soft disable (CAB-1979) ([#2198](https://github.com/stoa-platform/stoa/issues/2198)) ([c0a1539](https://github.com/stoa-platform/stoa/commit/c0a1539ca0b3ca03e6c47ebe526d11e1cf5ed660))
* **api:** gateway enabled flag + visibility + soft disable (CAB-1979) ([#2201](https://github.com/stoa-platform/stoa/issues/2201)) ([0136dd7](https://github.com/stoa-platform/stoa/commit/0136dd749acfb8b4d0e64be3a5a3388c4f6b17b8))
* **api:** instrument SyncEngine with SyncStepTracker (CAB-1946) ([#2128](https://github.com/stoa-platform/stoa/issues/2128)) ([de3b7b3](https://github.com/stoa-platform/stoa/commit/de3b7b35416dc1af4e4dba37ba9fa8c000866515))
* **api:** OpenSearch traces router + gateway OTel spans (CAB-1997) ([#2221](https://github.com/stoa-platform/stoa/issues/2221)) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **api:** OpenSearch-first monitoring with native Prometheus metrics (CAB-1997) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **api:** outbound-only connect — webmethods lifecycle + OpenAPI spec delivery (CAB-1929) ([#2025](https://github.com/stoa-platform/stoa/issues/2025)) ([0fb3266](https://github.com/stoa-platform/stoa/commit/0fb326683f159da2da42aa16f9f145d8f48bc6e3))
* **api:** promotion deploy chain — state machine, route-sync-ack, verify+activate ([#2034](https://github.com/stoa-platform/stoa/issues/2034)) ([fe242c8](https://github.com/stoa-platform/stoa/commit/fe242c821b2a412b94b84614f607f0d8f3ade21a))
* **api:** register STOA Gateway as platform MCP server (CAB-2003) ([#2241](https://github.com/stoa-platform/stoa/issues/2241)) ([9512340](https://github.com/stoa-platform/stoa/commit/9512340395842d5387407ed5caefb96cc7ed512f))
* **api:** remove mock data + add Tempo trace proxy (CAB-1984) ([#2199](https://github.com/stoa-platform/stoa/issues/2199)) ([f5c192b](https://github.com/stoa-platform/stoa/commit/f5c192b2b574ab34fddc85f4fbc65269ac725d7b))
* **api:** SSE deploy single path + DEPLOY_MODE flag (CAB-1931) ([#2072](https://github.com/stoa-platform/stoa/issues/2072)) ([437c9ae](https://github.com/stoa-platform/stoa/commit/437c9ae23fcc0ff6cf814185086e5ce6844b4c93))
* **api:** switch GIT_PROVIDER default to github (CAB-1889) ([#2068](https://github.com/stoa-platform/stoa/issues/2068)) ([061c20b](https://github.com/stoa-platform/stoa/commit/061c20be18d29341b7a83af9ed7b4015b6c57a22))
* **api:** tenant tool permissions model + CRUD + cache (CAB-1980) ([#2202](https://github.com/stoa-platform/stoa/issues/2202)) ([ce1c146](https://github.com/stoa-platform/stoa/commit/ce1c146550ba7656ee6229e0163a30860d4e47d8))
* **api:** unified Docker seeder with environment profiles ([#2246](https://github.com/stoa-platform/stoa/issues/2246)) ([44f51cf](https://github.com/stoa-platform/stoa/commit/44f51cf4b054fc3395f6cdec0a348ddc307adadf))
* **api:** wire git_provider_factory + FastAPI DI (CAB-1890) ([#2048](https://github.com/stoa-platform/stoa/issues/2048)) ([7b2a24c](https://github.com/stoa-platform/stoa/commit/7b2a24c58983438c1a853ca2e4850dc593bf968f))
* **api:** wrap GitLabService behind GitProvider ABC (CAB-1890) ([#2043](https://github.com/stoa-platform/stoa/issues/2043)) ([4c5c7e8](https://github.com/stoa-platform/stoa/commit/4c5c7e86e8a6b8051bf44fb00ae09d462f788483))
* **e2e:** subscription auth audit + observability fixes ([#2194](https://github.com/stoa-platform/stoa/issues/2194)) ([a77c0a2](https://github.com/stoa-platform/stoa/commit/a77c0a2bc4c0133df61ed8503ac18022f46eb349))
* **gateway,api,ui:** MCP Streamable HTTP endpoint + platform tool auto-sync ([#2245](https://github.com/stoa-platform/stoa/issues/2245)) ([fd7b408](https://github.com/stoa-platform/stoa/commit/fd7b4087ee21bfb83aa9fdc1e8d1cad1bb28abdf))
* **gateway,ui:** wire gateway metrics on all request types (CAB-1997) ([#2229](https://github.com/stoa-platform/stoa/issues/2229)) ([946a819](https://github.com/stoa-platform/stoa/commit/946a8191cb2b453184a2eb596634fe099e4172df))
* **gateway:** add ui_url + public_url to stoa-connect registration (CAB-1953) ([#2167](https://github.com/stoa-platform/stoa/issues/2167)) ([0bdbe08](https://github.com/stoa-platform/stoa/commit/0bdbe08bf0f17827e4fd6be645aed0adeffc9341))
* **gateway:** agent-side sync step tracking (CAB-1947) ([#2130](https://github.com/stoa-platform/stoa/issues/2130)) ([5eaa4e4](https://github.com/stoa-platform/stoa/commit/5eaa4e4e710787b6745f3cbcc482f145254dd7ce))
* **gateway:** STOA Connect webMethods bridge — POC March 31 ([#1992](https://github.com/stoa-platform/stoa/issues/1992)) ([ccd1c3c](https://github.com/stoa-platform/stoa/commit/ccd1c3cafa7911c08912f0e113fbf9c3090d51a0))
* **gateway:** traffic seed with all 5 auth modes (CAB-1997) ([#2216](https://github.com/stoa-platform/stoa/issues/2216)) ([9115bda](https://github.com/stoa-platform/stoa/commit/9115bda87d812dadfeb57401c43df912ba8bbec7))
* **ui:** chat usage dashboard with Recharts (CAB-1868) ([#2026](https://github.com/stoa-platform/stoa/issues/2026)) ([4b3fe35](https://github.com/stoa-platform/stoa/commit/4b3fe35fb2756565b8e0b9ce7f5caa5fd259c58d))


### Bug Fixes

* **api,gateway,go:** normalize health check payloads (CAB-1916) ([#2008](https://github.com/stoa-platform/stoa/issues/2008)) ([0366d18](https://github.com/stoa-platform/stoa/commit/0366d18066aad1610cab0cacc15e554d26ebe0de))
* **api,gateway,ui:** sequential span waterfall display (CAB-1997) ([#2223](https://github.com/stoa-platform/stoa/issues/2223)) ([68c7012](https://github.com/stoa-platform/stoa/commit/68c70125784bcd8820fdfe85af22d217eeee177b))
* **api,ui:** server-side route filter for Call Flow top routes (CAB-1997) ([#2231](https://github.com/stoa-platform/stoa/issues/2231)) ([9218089](https://github.com/stoa-platform/stoa/commit/92180897bc229c60dd8f550e1d6ed4531d6679f1))
* **api:** add generation fields to remaining test mocks (CAB-1950) ([#2143](https://github.com/stoa-platform/stoa/issues/2143)) ([a05ab98](https://github.com/stoa-platform/stoa/commit/a05ab980c9f7a1c8c565d3435fd84401ecce0b1a))
* **api:** add generation fields to sync engine test mocks (CAB-1950) ([#2135](https://github.com/stoa-platform/stoa/issues/2135)) ([70773a7](https://github.com/stoa-platform/stoa/commit/70773a765fa7114ad49bb7829aa84f66ed4dc37f))
* **api:** add missing AsyncMock for cancel-and-replace repo method in tests ([#1998](https://github.com/stoa-platform/stoa/issues/1998)) ([13dcd1a](https://github.com/stoa-platform/stoa/commit/13dcd1aafad65823a784457fea3aea71dd2c819b))
* **api:** add missing ui_url field to gateway test mocks (CAB-1953) ([#2162](https://github.com/stoa-platform/stoa/issues/2162)) ([b0acfdd](https://github.com/stoa-platform/stoa/commit/b0acfdd641a2aa5aea5d3ce591d03d0323e57507))
* **api:** align Alembic docstring Revises with down_revision values ([#2165](https://github.com/stoa-platform/stoa/issues/2165)) ([84457ae](https://github.com/stoa-platform/stoa/commit/84457ae6c784950920a776f109fcba879515ed8d))
* **api:** align tests with git provider migration and schema changes ([#2104](https://github.com/stoa-platform/stoa/issues/2104)) ([8aff704](https://github.com/stoa-platform/stoa/commit/8aff70451a251d86297987f65615c740c95bfbb9))
* **api:** align upsert conflict clauses with partial indexes (CAB-1938) ([#2112](https://github.com/stoa-platform/stoa/issues/2112)) ([c5a797c](https://github.com/stoa-platform/stoa/commit/c5a797ce502460a726c6d57b99da01b41179824c))
* **api:** auto-skip integration tests without DATABASE_URL (CAB-1939) ([#2117](https://github.com/stoa-platform/stoa/issues/2117)) ([7acb63a](https://github.com/stoa-platform/stoa/commit/7acb63aa0dac08dada82f7bd975851c4680487d4))
* **api:** bridge git_provider DI with legacy test patches ([#2076](https://github.com/stoa-platform/stoa/issues/2076)) ([a6b2a10](https://github.com/stoa-platform/stoa/commit/a6b2a1062d75644aa8b02644ab7e98a39c7982d2))
* **api:** centralized self_register guard for all gateway HTTP calls ([#2038](https://github.com/stoa-platform/stoa/issues/2038)) ([4bb9a6b](https://github.com/stoa-platform/stoa/commit/4bb9a6b981d8ecd76a719ad67c283497c5fbd241))
* **api:** correct mypy type: ignore comment ([#2133](https://github.com/stoa-platform/stoa/issues/2133)) ([f121be9](https://github.com/stoa-platform/stoa/commit/f121be9a8e6929ec34e9cecc8704bc8016f7c225))
* **api:** drift detector grace period for fresh syncs (CAB-1951) ([#2166](https://github.com/stoa-platform/stoa/issues/2166)) ([fdd12e0](https://github.com/stoa-platform/stoa/commit/fdd12e0101e204f5f26e26c8c9bac0f7fbae1676))
* **api:** eager-load tools on MCP server create (CAB-1976) ([#2222](https://github.com/stoa-platform/stoa/issues/2222)) ([126afd5](https://github.com/stoa-platform/stoa/commit/126afd58d8861b50b70989346e3a72c27b3b9813))
* **api:** enforce tenant-admin role on subscription write endpoints ([#2174](https://github.com/stoa-platform/stoa/issues/2174)) ([2282814](https://github.com/stoa-platform/stoa/commit/2282814ba7b26f1bd4a5c618ddb59f2f6f87b0f5))
* **api:** expose sync_steps in gateway deployment API response (CAB-1951) ([#2155](https://github.com/stoa-platform/stoa/issues/2155)) ([797e4a3](https://github.com/stoa-platform/stoa/commit/797e4a3235f669248794e828e68110306e78d266))
* **api:** filter routes + validate gateway_id in ack (CAB-1938) ([#2119](https://github.com/stoa-platform/stoa/issues/2119)) ([082673b](https://github.com/stoa-platform/stoa/commit/082673b32b796010624ee978f2b28332d681631a))
* **api:** fix Alembic migration chain + console KC build args ([#2200](https://github.com/stoa-platform/stoa/issues/2200)) ([25b6c81](https://github.com/stoa-platform/stoa/commit/25b6c817270a98d4dd3c2ce52c9a87f7116e6b88))
* **api:** fix API creation pipeline core issues (CAB-1919) ([#2012](https://github.com/stoa-platform/stoa/issues/2012)) ([af9150c](https://github.com/stoa-platform/stoa/commit/af9150c8f19be7c399ad58a19d24e7b84b85d298))
* **api:** improve deployment reliability — sync, drift, policies (CAB-1921) ([#2015](https://github.com/stoa-platform/stoa/issues/2015)) ([df24dff](https://github.com/stoa-platform/stoa/commit/df24dff43164c2be1c943f27066ba99e4987e3d2))
* **api:** include openapi_spec in GatewayDeployment desired_state ([#2035](https://github.com/stoa-platform/stoa/issues/2035)) ([b67eb2c](https://github.com/stoa-platform/stoa/commit/b67eb2c3352786c40d7252e8fe089f1fc4db6af1))
* **api:** include version column in portal search filter (CAB-1965) ([#2172](https://github.com/stoa-platform/stoa/issues/2172)) ([1ae66d0](https://github.com/stoa-platform/stoa/commit/1ae66d093e0b34ee2ea78b35ebe4be9677cdca79))
* **api:** make webMethods sync_api idempotent (CAB-1938) ([#2113](https://github.com/stoa-platform/stoa/issues/2113)) ([5457c6f](https://github.com/stoa-platform/stoa/commit/5457c6f6231ea38bc39185f6dbc714786a037f86))
* **api:** narrow self_register guard to gateway_type=stoa only ([#2044](https://github.com/stoa-platform/stoa/issues/2044)) ([f672453](https://github.com/stoa-platform/stoa/commit/f672453c6998a77d085d942cc137932b95090924))
* **api:** normalize webMethods list_apis + upsert sync_api (CAB-1938) ([#2115](https://github.com/stoa-platform/stoa/issues/2115)) ([c3b05ea](https://github.com/stoa-platform/stoa/commit/c3b05ea6c46e1ea2bb5898802252645ed4042884))
* **api:** patch _ensure_tenant_from_git in catalog sync tests ([#2116](https://github.com/stoa-platform/stoa/issues/2116)) ([41f3518](https://github.com/stoa-platform/stoa/commit/41f3518ff5a3d77eccc5db169b72d2fdc577e9c9))
* **api:** preserve health_details on failed gateway health check ([#1999](https://github.com/stoa-platform/stoa/issues/1999)) ([ac32c96](https://github.com/stoa-platform/stoa/commit/ac32c96f0aae3844eccd2cdd979b2c2382c98b66))
* **api:** register STOA gateway mode variants in adapter registry (CAB-1966) ([#2171](https://github.com/stoa-platform/stoa/issues/2171)) ([257599f](https://github.com/stoa-platform/stoa/commit/257599f47968aecbe69281cbc6ba6f42ca98865b))
* **api:** remove exception chaining to prevent stack trace exposure ([#2192](https://github.com/stoa-platform/stoa/issues/2192)) ([b47677f](https://github.com/stoa-platform/stoa/commit/b47677f5b0674fa7608c3184bfd77fdfeae1f74b))
* **api:** replace GitLab dependency with direct DB operations in apis router ([#2106](https://github.com/stoa-platform/stoa/issues/2106)) ([694670a](https://github.com/stoa-platform/stoa/commit/694670a1e572102b755bb10dde8c98b8834c41ea))
* **api:** resolve webMethods adapter field mismatch in sync_api ([#2102](https://github.com/stoa-platform/stoa/issues/2102)) ([9cdf64b](https://github.com/stoa-platform/stoa/commit/9cdf64bc12938b95e6942f391c08d11b6e6d4df8))
* **api:** resurrect soft-deleted gateway on re-registration (CAB-1937) ([#2105](https://github.com/stoa-platform/stoa/issues/2105)) ([da1b04a](https://github.com/stoa-platform/stoa/commit/da1b04abd764524e3b5499773e6523da7fd4db33))
* **api:** send openapi_spec as JSON object to stoa-connect ([#2036](https://github.com/stoa-platform/stoa/issues/2036)) ([a1fdec1](https://github.com/stoa-platform/stoa/commit/a1fdec199eff563bb9abf6d4e7be3c014548500e))
* **api:** skip keycloak_client_id check for api_key profile apps (CAB-1967) ([#2169](https://github.com/stoa-platform/stoa/issues/2169)) ([327c91e](https://github.com/stoa-platform/stoa/commit/327c91e52c453a4adb480efee04794c4c6cc0fbe))
* **api:** skip push sync for agent-managed gateways (CAB-1921) ([#2022](https://github.com/stoa-platform/stoa/issues/2022)) ([ed3120b](https://github.com/stoa-platform/stoa/commit/ed3120b8601eafac1fb78dc0d00247598c1a8833))
* **api:** slug api_id + name-version uniqueness (CAB-1938) ([#2109](https://github.com/stoa-platform/stoa/issues/2109)) ([d52e1a7](https://github.com/stoa-platform/stoa/commit/d52e1a74db016a67bd1dd8d0f8d204bc580ed488))
* **api:** surface error details in degraded health check response ([#1991](https://github.com/stoa-platform/stoa/issues/1991)) ([a971a1f](https://github.com/stoa-platform/stoa/commit/a971a1f1a80fe688f5e29dcd4d20612458cc658f))
* **api:** unblock CI — health test imports + prettier + mypy ([#2071](https://github.com/stoa-platform/stoa/issues/2071)) ([9ed93d0](https://github.com/stoa-platform/stoa/commit/9ed93d03060d5d03112659f309e2852dfcf2e124))
* **api:** update health check test to expect degraded instead of offline ([#2004](https://github.com/stoa-platform/stoa/issues/2004)) ([7e06ece](https://github.com/stoa-platform/stoa/commit/7e06ecef7be524a0e04b9027eb8f221d09d8af21))
* **gateway,api:** resolve sync drift errors 400/401/500 (CAB-1944) ([#2126](https://github.com/stoa-platform/stoa/issues/2126)) ([65e2384](https://github.com/stoa-platform/stoa/commit/65e2384931d4c2ee5c28508de720a6e0c17920a8))
* **gateway,api:** scope API discovery by gateway mode + gateway_id filter (CAB-1940) ([#2121](https://github.com/stoa-platform/stoa/issues/2121)) ([a01b245](https://github.com/stoa-platform/stoa/commit/a01b245e69f8dc5f2574762098e8d9ed361df930))
* **gateway:** explicit OTLP batch config for Tempo (CAB-1974) ([#2193](https://github.com/stoa-platform/stoa/issues/2193)) ([80d09cd](https://github.com/stoa-platform/stoa/commit/80d09cdf0a96b5f882ae35f0859c85e58f586368))
* **gateway:** strip Swagger 2.0 $ref in responses + per-route sync-ack (CAB-1944) ([#2131](https://github.com/stoa-platform/stoa/issues/2131)) ([8c9f6a5](https://github.com/stoa-platform/stoa/commit/8c9f6a5dbc3e8ce6aa7f3c668ceaa47915eb31d1))
* **ui:** add missing i18n keys for security + guardrails nav items ([#2196](https://github.com/stoa-platform/stoa/issues/2196)) ([3af62a4](https://github.com/stoa-platform/stoa/commit/3af62a412098c86b580df4aeb69d023bdd75e274))
* **ui:** show gateway URLs for all modes + fix stoa-link hostname (CAB-1953) ([#2160](https://github.com/stoa-platform/stoa/issues/2160)) ([3ee4c66](https://github.com/stoa-platform/stoa/commit/3ee4c66397b89d506bbfcd6829637f0bc46ee563))


### Performance

* **gateway,api:** eliminate circular proxy in tool call path ([#2230](https://github.com/stoa-platform/stoa/issues/2230)) ([61e963c](https://github.com/stoa-platform/stoa/commit/61e963c55d824600aeb8ac4168c3ca93e7452916))

## [1.1.0](https://github.com/stoa-platform/stoa/compare/control-plane-api-v1.0.0...control-plane-api-v1.1.0) (2026-03-25)


### Features

* **api,portal:** catalog shows all APIs with deployment environment badges ([#1955](https://github.com/stoa-platform/stoa/issues/1955)) ([0295ad1](https://github.com/stoa-platform/stoa/commit/0295ad1aec8c23de54fc30a79f0e20595af40e74))
* **api,portal:** filter portal APIs by deployment environment ([#1951](https://github.com/stoa-platform/stoa/issues/1951)) ([b85dc00](https://github.com/stoa-platform/stoa/commit/b85dc004bc7d5f4e70a55e0e5f13edf30fc529ba))
* **api,ui,gateway:** deployment verification — tags, route reload, test button ([#1938](https://github.com/stoa-platform/stoa/issues/1938)) ([3d81e83](https://github.com/stoa-platform/stoa/commit/3d81e8351e264196220d14b008c90887f65baf9d))
* **api,ui,portal:** MCP tool observability — gateway binding + usage stats (CAB-1821) ([#1766](https://github.com/stoa-platform/stoa/issues/1766)) ([f370331](https://github.com/stoa-platform/stoa/commit/f3703312dfdc485b1397b9f0911a74ade0ba5d28))
* **api,ui:** add AI Factory dashboard — Hegemon observability (CAB-1666) ([#1442](https://github.com/stoa-platform/stoa/issues/1442)) ([8afd9dc](https://github.com/stoa-platform/stoa/commit/8afd9dcc982e736cae8936b607c99715754a4592))
* **api,ui:** add error source attribution to monitoring transactions ([#1675](https://github.com/stoa-platform/stoa/issues/1675)) ([cc0e4c8](https://github.com/stoa-platform/stoa/commit/cc0e4c87122f93e94fd70d6edc5eae1ec639d2d0))
* **api,ui:** add mark deployed button for promoting promotions (CAB-1706) ([#1586](https://github.com/stoa-platform/stoa/issues/1586)) ([c2537dd](https://github.com/stoa-platform/stoa/commit/c2537dd17cf3f56f4b3179239c0c099ccc6046cf))
* **api,ui:** applications multi-env display + FAPI key management (CAB-1748) ([#1566](https://github.com/stoa-platform/stoa/issues/1566)) ([70a1702](https://github.com/stoa-platform/stoa/commit/70a17024af8ea55bf77c4cd22b239aec59535ce7))
* **api,ui:** deployment observability — error enrichment + detail drawer ([#1931](https://github.com/stoa-platform/stoa/issues/1931)) ([2e0719b](https://github.com/stoa-platform/stoa/commit/2e0719bcdd810411e81a85fe3986d8ff54c67152))
* **api,ui:** environment scoping for Console — traces, policies, deployments (CAB-1664) ([#1439](https://github.com/stoa-platform/stoa/issues/1439)) ([c21f988](https://github.com/stoa-platform/stoa/commit/c21f988be608e62f45034e044bd96595db725e65))
* **api,ui:** environment scoping for gateway deployments (CAB-1664) ([#1554](https://github.com/stoa-platform/stoa/issues/1554)) ([fb91aee](https://github.com/stoa-platform/stoa/commit/fb91aee88cbecaf6abcbdb4d47027044b4b1706f))
* **api,ui:** environment-aware MCP servers with catalog feature flag (CAB-1791) ([#1689](https://github.com/stoa-platform/stoa/issues/1689)) ([efbcb96](https://github.com/stoa-platform/stoa/commit/efbcb965cf0cbae06de3372898a063d43576a756))
* **api,ui:** full environment scoping (CAB-1665) ([#1443](https://github.com/stoa-platform/stoa/issues/1443)) ([4dcf132](https://github.com/stoa-platform/stoa/commit/4dcf13241837327cd76d093fb0f4df1bb9335c4d))
* **api,ui:** persist signed certificates for lifecycle management ([#1907](https://github.com/stoa-platform/stoa/issues/1907)) ([bfb2b38](https://github.com/stoa-platform/stoa/commit/bfb2b3844a2d7a947578b964fd97b84d71e695ff))
* **api,ui:** surface cost/token metrics in AI Factory dashboard (CAB-1666) ([#1487](https://github.com/stoa-platform/stoa/issues/1487)) ([9d385a1](https://github.com/stoa-platform/stoa/commit/9d385a16f0b11f5fc6c62abb563dde4664cde02d))
* **api:** add 5 DCR-capable MCP connectors to catalog (CAB-1790) ([#1729](https://github.com/stoa-platform/stoa/issues/1729)) ([e1f3b25](https://github.com/stoa-platform/stoa/commit/e1f3b25811fa8e5de5f4a8a9f570b72f9ceb8a52))
* **api:** add AI session demo endpoint for Hegemon dashboard ([#1449](https://github.com/stoa-platform/stoa/issues/1449)) ([a389033](https://github.com/stoa-platform/stoa/commit/a389033b10d6f279691655ee6a747f6f6b525253))
* **api:** add environment scoping to usage metering (CAB-1665) ([#1878](https://github.com/stoa-platform/stoa/issues/1878)) ([35370db](https://github.com/stoa-platform/stoa/commit/35370db0aeff34c735b0d14b150de06dbd2d74f0))
* **api:** add gateway telemetry adapters (CAB-1683) ([#1497](https://github.com/stoa-platform/stoa/issues/1497)) ([279b504](https://github.com/stoa-platform/stoa/commit/279b5047b5e5d993c3157eaa1ca5d29a6e0b6a2f))
* **api:** add GDPR Article 17 right to erasure endpoint (CAB-1794) ([#1695](https://github.com/stoa-platform/stoa/issues/1695)) ([0e1aba1](https://github.com/stoa-platform/stoa/commit/0e1aba1a9adfffb6a6278718691e2de9ed9c6b9b))
* **api:** add OS gateway templates + provisioner (CAB-1684, CAB-1685) ([#1499](https://github.com/stoa-platform/stoa/issues/1499)) ([eb1e62e](https://github.com/stoa-platform/stoa/commit/eb1e62e99381d7e3b00a1264e318ac8b21e40ec1))
* **api:** add POST /contracts/{id}/publish endpoint ([#1906](https://github.com/stoa-platform/stoa/issues/1906)) ([87a7bcb](https://github.com/stoa-platform/stoa/commit/87a7bcb76d3d81263874501e998a1cc612eca3b5))
* **api:** add proxy backend registry model + API endpoints (CAB-1725) ([#1519](https://github.com/stoa-platform/stoa/issues/1519)) ([9c2c4e7](https://github.com/stoa-platform/stoa/commit/9c2c4e7693bc4abcaeec70e6005967d8f2267a1f))
* **api:** add slack notifications for promotion approvals (CAB-1706) ([#1584](https://github.com/stoa-platform/stoa/issues/1584)) ([4671f96](https://github.com/stoa-platform/stoa/commit/4671f967c8c15d98cc7ea878ee311d2deb37bd7a))
* **api:** add STOA-bench v1 — CP API benchmark suite (CAB-1591) ([#1876](https://github.com/stoa-platform/stoa/issues/1876)) ([e2fc6de](https://github.com/stoa-platform/stoa/commit/e2fc6def35bfb0638b281cb8595088dca3aed18f))
* **api:** add telemetry subsystem (CAB-1682) ([#1493](https://github.com/stoa-platform/stoa/issues/1493)) ([dabc777](https://github.com/stoa-platform/stoa/commit/dabc777af541fe6044e01d085e54fcf5c138ccb9))
* **api:** add tenant chat settings, source tracking + migration (CAB-1851) ([#1806](https://github.com/stoa-platform/stoa/issues/1806)) ([5a33a17](https://github.com/stoa-platform/stoa/commit/5a33a17abf4cb31fc12d0bf1bfcb4030ccadf2b2))
* **api:** add Vault credential resolver for gateway adapters ([#1964](https://github.com/stoa-platform/stoa/issues/1964)) ([8a5a765](https://github.com/stoa-platform/stoa/commit/8a5a7656dede2607195e284b3635497601ccf733))
* **api:** add Vault/ESO ExternalSecret for ANTHROPIC_API_KEY (CAB-1837) ([#1786](https://github.com/stoa-platform/stoa/issues/1786)) ([445f816](https://github.com/stoa-platform/stoa/commit/445f81643534143173534b4dfd54b6e927ff9e3b))
* **api:** adopt ArgoCD entries on gateway registration (CAB-1771) ([#1658](https://github.com/stoa-platform/stoa/issues/1658)) ([af45581](https://github.com/stoa-platform/stoa/commit/af455812305ff3cf2a89e965d54582ac9864c908))
* **api:** argocd admin + computed diff + 4-eyes guard (CAB-1706 W3) ([#1575](https://github.com/stoa-platform/stoa/issues/1575)) ([11627ce](https://github.com/stoa-platform/stoa/commit/11627cea5428dab19044377783ecefbe57d195f0))
* **api:** ArgoCD gateway reconciler — sync gateway_instances from ArgoCD (CAB-1771) ([#1655](https://github.com/stoa-platform/stoa/issues/1655)) ([36ba986](https://github.com/stoa-platform/stoa/commit/36ba986543367ca4da0e913d611630aa83e7f986))
* **api:** auto-purge stale gateway instances after heartbeat TTL (CAB-1897) ([#1957](https://github.com/stoa-platform/stoa/issues/1957)) ([6283bc1](https://github.com/stoa-platform/stoa/commit/6283bc1039a6c1bbba7e829bd73e8a2244050afc))
* **api:** auto-resolve OAuth creds from DB/env (CAB-1790) ([#1703](https://github.com/stoa-platform/stoa/issues/1703)) ([0c88181](https://github.com/stoa-platform/stoa/commit/0c881813b275c4303bae32ef9813967673b2c04d))
* **api:** chat rate limiting + kill switch (CAB-1655) ([#1548](https://github.com/stoa-platform/stoa/issues/1548)) ([783f998](https://github.com/stoa-platform/stoa/commit/783f99863bcb7357cf918966a7d9d30dbcbb0587))
* **api:** discovery and sync-ack endpoints for stoa-connect (CAB-1817) ([#1767](https://github.com/stoa-platform/stoa/issues/1767)) ([12ff779](https://github.com/stoa-platform/stoa/commit/12ff779fe7b6258e9193d5a89ec5fa1034da9492))
* **api:** extract discovery catalog to YAML files (CAB-1639) ([#1881](https://github.com/stoa-platform/stoa/issues/1881)) ([11e4635](https://github.com/stoa-platform/stoa/commit/11e46357c1fb74e5a01c4ef323d7374608a12a1d))
* **api:** gateway soft-delete + protection + restore (CAB-1749) ([#1567](https://github.com/stoa-platform/stoa/issues/1567)) ([9c2e24d](https://github.com/stoa-platform/stoa/commit/9c2e24dc597e723740ca08c6f729c8437067db9e))
* **api:** MCP OAuth DCR for one-click connector setup (CAB-1790) ([#1714](https://github.com/stoa-platform/stoa/issues/1714)) ([341f925](https://github.com/stoa-platform/stoa/commit/341f925109309823fb68aa9472a6c41cf6d81a98))
* **api:** multi-environment connector promotion (CAB-1812) ([#1733](https://github.com/stoa-platform/stoa/issues/1733)) ([bd92d56](https://github.com/stoa-platform/stoa/commit/bd92d568f5c29d82d66fdf239922593a6070df3e))
* **api:** multi-tenant audit index isolation with DLS (CAB-1789) ([#1686](https://github.com/stoa-platform/stoa/issues/1686)) ([1b6f596](https://github.com/stoa-platform/stoa/commit/1b6f596042dc009895ce2c8303f954d0a6a14fff))
* **api:** parse Server-Timing header into multi-span transaction data (CAB-1790) ([#1688](https://github.com/stoa-platform/stoa/issues/1688)) ([8b2697b](https://github.com/stoa-platform/stoa/commit/8b2697b50a399ab013a3e876b6f3f2c207696400))
* **api:** per-tenant CA keypair generation + CSR signing (CAB-1787) ([#1681](https://github.com/stoa-platform/stoa/issues/1681)) ([b3d769f](https://github.com/stoa-platform/stoa/commit/b3d769f79be25f6a079df330bd8e3eab09071d65))
* **api:** per-worker Pushgateway metrics + cost alert dedup (CAB-1824) ([#1770](https://github.com/stoa-platform/stoa/issues/1770)) ([7fe808c](https://github.com/stoa-platform/stoa/commit/7fe808cfd47d8d8eec13395fee8075cbd2adf5e2))
* **api:** promotion model + schema + repository + migration (CAB-1706 W1) ([#1573](https://github.com/stoa-platform/stoa/issues/1573)) ([c36aa34](https://github.com/stoa-platform/stoa/commit/c36aa34866ea285e726f3b58868999403da43e6e))
* **api:** promotion router + service + RBAC + Kafka (CAB-1706 W2) ([#1574](https://github.com/stoa-platform/stoa/issues/1574)) ([8a53ea5](https://github.com/stoa-platform/stoa/commit/8a53ea5efcafd90372c9b9fc07a8866eafaa3917))
* **api:** Python SDK generation pipeline from OpenAPI spec (CAB-1880) ([#1873](https://github.com/stoa-platform/stoa/issues/1873)) ([1863dff](https://github.com/stoa-platform/stoa/commit/1863dff6eda5e44f7e6c545513eb21b9d88b7c85))
* **api:** realistic traffic seeder for Call Flow Dashboard (CAB-1869) ([#1854](https://github.com/stoa-platform/stoa/issues/1854)) ([09d564f](https://github.com/stoa-platform/stoa/commit/09d564fcc83c5fb36c56ef1b3b3d070cdebdd968))
* **api:** route chat assistant through Stoa Gateway LLM proxy (CAB-1822) ([#1759](https://github.com/stoa-platform/stoa/issues/1759)) ([83f0bfd](https://github.com/stoa-platform/stoa/commit/83f0bfd9d86178e52d4ca9f957b4b4013536d94d))
* **api:** security profile per application (CAB-1744) ([#1541](https://github.com/stoa-platform/stoa/issues/1541)) ([5c70616](https://github.com/stoa-platform/stoa/commit/5c7061690f14ba73cbc28a3f7e7e6960db3bdb9b))
* **api:** seed 5 real APIs + echo fallback for realdata traffic (CAB-1856) ([#1812](https://github.com/stoa-platform/stoa/issues/1812)) ([7186fe9](https://github.com/stoa-platform/stoa/commit/7186fe984ec241622effcdbec1b2be32950f73d5))
* **api:** seed gateway instances for multi-env platform ([#1485](https://github.com/stoa-platform/stoa/issues/1485)) ([51f0543](https://github.com/stoa-platform/stoa/commit/51f0543f1226d14b1bdbabe15eaee7ecc3385111))
* **api:** SSE transport for MCP tool discovery (CAB-1791) ([#1692](https://github.com/stoa-platform/stoa/issues/1692)) ([079a720](https://github.com/stoa-platform/stoa/commit/079a72013adf87659654485e6e9907b9b147c980))
* **api:** switch LLM cost dashboard to DB-backed queries (CAB-1822) ([#1771](https://github.com/stoa-platform/stoa/issues/1771)) ([f872831](https://github.com/stoa-platform/stoa/commit/f872831f809b49e7de173e99c4826dd80e3c7089))
* **api:** type all untyped API responses and clean OpenAPI spec (CAB-1680) ([#1871](https://github.com/stoa-platform/stoa/issues/1871)) ([34ed129](https://github.com/stoa-platform/stoa/commit/34ed1296a760d2cfa929af65348f64028752eeab))
* **api:** type response schemas + clean operationIds (CAB-1680) ([#1486](https://github.com/stoa-platform/stoa/issues/1486)) ([7c4b5d1](https://github.com/stoa-platform/stoa/commit/7c4b5d128d49bc50232de468117a146c67221c7d))
* **api:** vault graceful degradation + config settings (CAB-1792) ([#1691](https://github.com/stoa-platform/stoa/issues/1691)) ([4c8bb1e](https://github.com/stoa-platform/stoa/commit/4c8bb1e36161977ab876b0c2170bb42598fed59b))
* **ci:** multi-agent quality gate for L1 pipeline (CAB-1807) ([#1715](https://github.com/stoa-platform/stoa/issues/1715)) ([de6972d](https://github.com/stoa-platform/stoa/commit/de6972de6c1658c65661c804bbf229cc546c62dd))
* **gateway:** add gRPC protocol support with proto parser and MCP bridge (CAB-1755) ([#1757](https://github.com/stoa-platform/stoa/issues/1757)) ([c221fef](https://github.com/stoa-platform/stoa/commit/c221fefeb9a412b456ce63277d29166d63094e9c))
* **gateway:** API proxy config + credential injection (CAB-1723, CAB-1724) ([#1516](https://github.com/stoa-platform/stoa/issues/1516)) ([f8abfd1](https://github.com/stoa-platform/stoa/commit/f8abfd11970b61db3fec6c342b203d204ebdbdaa))
* **gateway:** wire PingoraPool into proxy path (CAB-1849) ([#1905](https://github.com/stoa-platform/stoa/issues/1905)) ([ba39741](https://github.com/stoa-platform/stoa/commit/ba397419b0eae445ccf29b7c0b8d0f0f2d4733e8))
* **helm:** add shared secrets template + values schema (CAB-1863) ([#1816](https://github.com/stoa-platform/stoa/issues/1816)) ([ab91918](https://github.com/stoa-platform/stoa/commit/ab919181c9131eeb92c853beed6e4cf585d5cb62))
* **helm:** resource lifecycle label taxonomy + Kyverno enforcement (CAB-1877) ([#1864](https://github.com/stoa-platform/stoa/issues/1864)) ([49c186f](https://github.com/stoa-platform/stoa/commit/49c186f9765aef2ba389fe3a99ea77ef1f5610a4))
* **portal,api:** enriched API cards + faceted search with sort and tag filters (CAB-1906) ([#1959](https://github.com/stoa-platform/stoa/issues/1959)) ([c03bd4c](https://github.com/stoa-platform/stoa/commit/c03bd4c6d98f2bb7a9c72ccfaa748433cb1524e2))
* subscription OAuth2 overhaul — remove API keys, use client_credentials flow ([#1458](https://github.com/stoa-platform/stoa/issues/1458)) ([705859f](https://github.com/stoa-platform/stoa/commit/705859f81b357f955fca1fe537d701a3bc20c80c))
* **ui:** add contextual sub-navigation for hidden pages (CAB-1785) ([#1678](https://github.com/stoa-platform/stoa/issues/1678)) ([6f2f8d1](https://github.com/stoa-platform/stoa/commit/6f2f8d1ee3caef9ae9c2c22b809bc7ce52c65acc))
* **ui:** add OAuth setup dialog for MCP connectors (CAB-1790) ([#1704](https://github.com/stoa-platform/stoa/issues/1704)) ([83f4b0c](https://github.com/stoa-platform/stoa/commit/83f4b0cceb0215ef8224e7a3f1705955a6bf9b7a))
* **ui:** API detail page with lifecycle management (CAB-1813) ([#1736](https://github.com/stoa-platform/stoa/issues/1736)) ([843ef2e](https://github.com/stoa-platform/stoa/commit/843ef2e95361ddbbaa7ef2685ef0143066c70255))
* **ui:** consolidate observability dashboard with MCP, arena, and CUJ metrics ([#1659](https://github.com/stoa-platform/stoa/issues/1659)) ([63741e8](https://github.com/stoa-platform/stoa/commit/63741e850ca726b7f027c96d5d629528bf39a56d))
* **ui:** progressive streaming + tool rendering in FloatingChat (CAB-1816) ([#1738](https://github.com/stoa-platform/stoa/issues/1738)) ([2463e63](https://github.com/stoa-platform/stoa/commit/2463e636770aafe10dc8d76898c6c58978272a95))
* **ui:** replace fake Operations panels with Grafana embeds (CAB-1766) ([#1632](https://github.com/stoa-platform/stoa/issues/1632)) ([31488db](https://github.com/stoa-platform/stoa/commit/31488db9dfde6ab5373102edbfb1428ce81fdfa3))


### Bug Fixes

* **api,gateway:** add internal tool discovery with X-Gateway-Key auth (CAB-1817) ([#1739](https://github.com/stoa-platform/stoa/issues/1739)) ([7ca4769](https://github.com/stoa-platform/stoa/commit/7ca476956fc472fd4e88aa71d442e236e153f0b0))
* **api,gateway:** fix gateway health check + inline app creation (CAB-1907) ([#1963](https://github.com/stoa-platform/stoa/issues/1963)) ([cdc15b5](https://github.com/stoa-platform/stoa/commit/cdc15b510a88b3e619d1d4cbe7bcf030ab3ba033))
* **api,portal:** harden API subscription flow with OAuth2 validation ([#1466](https://github.com/stoa-platform/stoa/issues/1466)) ([94126a7](https://github.com/stoa-platform/stoa/commit/94126a7809d995e6a778077dc5d806be4b70ad2b))
* **api,ui:** 2-eyes for staging, 4-eyes for production only (CAB-1706) ([#1581](https://github.com/stoa-platform/stoa/issues/1581)) ([9053a1e](https://github.com/stoa-platform/stoa/commit/9053a1e8ca5727a1a48c50a786544c69b0572599))
* **api,ui:** add demo_mode flag, surface errors, fix tenant storage (CAB-1774) ([#1648](https://github.com/stoa-platform/stoa/issues/1648)) ([e703e1d](https://github.com/stoa-platform/stoa/commit/e703e1df5cdab0f27459acfd4e9d4c3a2c93c7f7))
* **api,ui:** align contracts router with tenant-scoped URL pattern ([#1899](https://github.com/stoa-platform/stoa/issues/1899)) ([a8afb25](https://github.com/stoa-platform/stoa/commit/a8afb250bde1262c99ac8b7d4aad83721cc35fca))
* **api,ui:** align metrics contract and fix polling bug (CAB-1774) ([#1646](https://github.com/stoa-platform/stoa/issues/1646)) ([bad5bd0](https://github.com/stoa-platform/stoa/commit/bad5bd0244eb0aef9615d73bfbbba14ac8dc319c))
* **api,ui:** deploy dialog uses git-synced APIs, not empty catalog cache (CAB-1888) ([#1898](https://github.com/stoa-platform/stoa/issues/1898)) ([c3feb41](https://github.com/stoa-platform/stoa/commit/c3feb411e7a16590dc22cb5860257f7f886f63f9))
* **api,ui:** fix AI Factory dashboard data quality (CAB-1666) ([#1457](https://github.com/stoa-platform/stoa/issues/1457)) ([f4864b8](https://github.com/stoa-platform/stoa/commit/f4864b8f613c80a1a1d384c385fda72e05c94ad4))
* **api,ui:** Keycloak password grant + stabilize flaky tests ([#1447](https://github.com/stoa-platform/stoa/issues/1447)) ([ee65c09](https://github.com/stoa-platform/stoa/commit/ee65c09518fe2382debdf7efc48061a796adb5a3))
* **api,ui:** return 503 when GitLab not configured + Button loading state (CAB-1790) ([#1705](https://github.com/stoa-platform/stoa/issues/1705)) ([72fa545](https://github.com/stoa-platform/stoa/commit/72fa5457e23dc9e845f0c10890352a8f05414a8f))
* **api,ui:** test button shows amber for 4xx, green only for 2xx ([#1945](https://github.com/stoa-platform/stoa/issues/1945)) ([8baf152](https://github.com/stoa-platform/stoa/commit/8baf15279b4ff52bfa0cde36408232b4650c8f2d))
* **api,ui:** use API name for GitLab deployment lookup (CAB-1803) ([#1731](https://github.com/stoa-platform/stoa/issues/1731)) ([201c3d9](https://github.com/stoa-platform/stoa/commit/201c3d972d4d9845a56a01805f77f2bd5802aa61))
* **api:** add connect mode to gateway registration (CAB-1819) ([#1741](https://github.com/stoa-platform/stoa/issues/1741)) ([cb2aaa8](https://github.com/stoa-platform/stoa/commit/cb2aaa8d9bca5518c2fed962a8a5ceb466835d4b))
* **api:** add GITLAB_PROJECT_ID to k8s ConfigMap ([#1453](https://github.com/stoa-platform/stoa/issues/1453)) ([147f517](https://github.com/stoa-platform/stoa/commit/147f51710537a4079ce7f72058efa781cbf853e0))
* **api:** add missing AsyncMock for ArgoCD adoption in gateway tests (CAB-1771) ([#1662](https://github.com/stoa-platform/stoa/issues/1662)) ([7d8e93b](https://github.com/stoa-platform/stoa/commit/7d8e93b0f81b6666631dffbf992902a7deb54361))
* **api:** attribute internal/gateway calls as service actors in audit (CAB-1793) ([#1702](https://github.com/stoa-platform/stoa/issues/1702)) ([ec60338](https://github.com/stoa-platform/stoa/commit/ec60338bd60ae4bd7ad0d17c7cbbd9626c9e8206))
* **api:** connect monitoring to OpenSearch and fix tenant filter ([#1670](https://github.com/stoa-platform/stoa/issues/1670)) ([4ab10ce](https://github.com/stoa-platform/stoa/commit/4ab10ced202c0a49f0e5dc54e523d76cec995f2d))
* **api:** correct migration 058 revision chain (CAB-1725) ([#1528](https://github.com/stoa-platform/stoa/issues/1528)) ([6506886](https://github.com/stoa-platform/stoa/commit/65068864a36a0b09fdebdec9406668542d8a5efb))
* **api:** correct migration 078 revision ID format ([#1910](https://github.com/stoa-platform/stoa/issues/1910)) ([602251f](https://github.com/stoa-platform/stoa/commit/602251f687474fc394de5a1d2a35deaa3088cbc5))
* **api:** correct proxy backend health endpoints (CAB-1725) ([#1530](https://github.com/stoa-platform/stoa/issues/1530)) ([5714005](https://github.com/stoa-platform/stoa/commit/5714005e3e518346a71ed630933ab6e8e268082e))
* **api:** deployment response compatible with ORM + dict (CAB-1888) ([#1921](https://github.com/stoa-platform/stoa/issues/1921)) ([366db12](https://github.com/stoa-platform/stoa/commit/366db1257436b079cd31f315a7a36431ea4dfa65))
* **api:** derive API status from deployment flags + fix prod env filter (CAB-1803) ([#1735](https://github.com/stoa-platform/stoa/issues/1735)) ([3b53c2f](https://github.com/stoa-platform/stoa/commit/3b53c2f7f3996259b90553994a13a0d37075b5ec))
* **api:** enrich chat assistant with accurate platform knowledge ([#1846](https://github.com/stoa-platform/stoa/issues/1846)) ([c171c6b](https://github.com/stoa-platform/stoa/commit/c171c6b900035bad82d9e61206d332312ef65a25))
* **api:** extract audit actor after call_next for JWT attribution (CAB-1793) ([#1693](https://github.com/stoa-platform/stoa/issues/1693)) ([b105ca3](https://github.com/stoa-platform/stoa/commit/b105ca3e29634f22cf550d096fdb5857fae39274))
* **api:** fallback to OpenSearch _id in monitoring detail lookup ([#1676](https://github.com/stoa-platform/stoa/issues/1676)) ([5629c3b](https://github.com/stoa-platform/stoa/commit/5629c3b0b13f1063a2a98cc033c00d656e0af7d5))
* **api:** fix 2 broken test mocks blocking CI pipeline ([#1966](https://github.com/stoa-platform/stoa/issues/1966)) ([5931c17](https://github.com/stoa-platform/stoa/commit/5931c176768e9516ae326710faa519dab875b1bb))
* **api:** fix 25 test failures blocking CI Docker build on main ([#1697](https://github.com/stoa-platform/stoa/issues/1697)) ([5c24f85](https://github.com/stoa-platform/stoa/commit/5c24f85b08ffc1e4f65d05292cc6bc9180f96c36))
* **api:** fix alembic 065 down_revision breaking migration chain ([#1700](https://github.com/stoa-platform/stoa/issues/1700)) ([9f1d22a](https://github.com/stoa-platform/stoa/commit/9f1d22aa2947297f395159258b5533e21fb36afa))
* **api:** fix monitoring test + mypy errors blocking CI on main ([#1683](https://github.com/stoa-platform/stoa/issues/1683)) ([d5974ad](https://github.com/stoa-platform/stoa/commit/d5974add538112cd17cdc2334458672a23c397e0))
* **api:** handle dict-format capabilities in gateway response schema ([#1503](https://github.com/stoa-platform/stoa/issues/1503)) ([d28aa3b](https://github.com/stoa-platform/stoa/commit/d28aa3b451a91d5d459ee7b6706a9da7b83195e6))
* **api:** handle unbound response variable in audit middleware ([#1674](https://github.com/stoa-platform/stoa/issues/1674)) ([8fa4bc7](https://github.com/stoa-platform/stoa/commit/8fa4bc7e8d61d9bf71b8cc3359677efc9a78b19d))
* **api:** improve chat assistant system prompt for accuracy and tone ([#1745](https://github.com/stoa-platform/stoa/issues/1745)) ([75ada53](https://github.com/stoa-platform/stoa/commit/75ada5388c3c2abe102877827f8308ec66d0689c))
* **api:** improve JWT sub claim handling (CAB-1669) ([#1549](https://github.com/stoa-platform/stoa/issues/1549)) ([55d40f7](https://github.com/stoa-platform/stoa/commit/55d40f7505e93531408f2eda2c704dfc743cca69))
* **api:** include connect mode in gateway mode stats (CAB-1819) ([#1758](https://github.com/stoa-platform/stoa/issues/1758)) ([21d8c4a](https://github.com/stoa-platform/stoa/commit/21d8c4a12afc762a56a2be51dc8cfb5dd2738a8a))
* **api:** inline sync deployments on creation (CAB-1888) ([#1918](https://github.com/stoa-platform/stoa/issues/1918)) ([116a6f4](https://github.com/stoa-platform/stoa/commit/116a6f401be62ead3ff0e16292b82ba747bf1331))
* **api:** join gateway info in deployment list response (CAB-1888) ([#1913](https://github.com/stoa-platform/stoa/issues/1913)) ([d89894e](https://github.com/stoa-platform/stoa/commit/d89894e5ef71be0afc981a8b5cd5ed76711845d3))
* **api:** make certificate persistence resilient to missing migration ([#1909](https://github.com/stoa-platform/stoa/issues/1909)) ([b17ab2d](https://github.com/stoa-platform/stoa/commit/b17ab2ddbebbfd76b0530da57bdb53c058fbd8bb))
* **api:** make monitoring demo detail coherent with list status codes ([#1677](https://github.com/stoa-platform/stoa/issues/1677)) ([4a055c3](https://github.com/stoa-platform/stoa/commit/4a055c312e3e002695c55a9bcbc6da365b1aad73))
* **api:** make tenant_id nullable in APITransaction schema ([#1672](https://github.com/stoa-platform/stoa/issues/1672)) ([ac2bd62](https://github.com/stoa-platform/stoa/commit/ac2bd621a21329786d721bc805613ebbc1d29daf))
* **api:** mock session.commit as AsyncMock in traces ingest tests ([#1460](https://github.com/stoa-platform/stoa/issues/1460)) ([b38a572](https://github.com/stoa-platform/stoa/commit/b38a5722a89953a5c6d48bd95a92fdcde2ab6615))
* **api:** move git_service guard after trial limits in create_api (CAB-1790) ([#1708](https://github.com/stoa-platform/stoa/issues/1708)) ([7d920cc](https://github.com/stoa-platform/stoa/commit/7d920cc48a6a1cb669939c5d566e5d61dd2dc8b6))
* **api:** pass client_secret via pending session (CAB-1790) ([#1726](https://github.com/stoa-platform/stoa/issues/1726)) ([6254daa](https://github.com/stoa-platform/stoa/commit/6254daa736450d12321cbfabe64e1286ad1c1b56))
* **api:** populate request.state.user for audit actor attribution (CAB-1793) ([#1699](https://github.com/stoa-platform/stoa/issues/1699)) ([8e02460](https://github.com/stoa-platform/stoa/commit/8e0246085b4f5d2a0e822c30cfdf5d04567d4b2c))
* **api:** prevent false offline status for unreachable external gateways ([#1696](https://github.com/stoa-platform/stoa/issues/1696)) ([589bd6c](https://github.com/stoa-platform/stoa/commit/589bd6c2954a3d17a5d9603c6d4823deb22152b0))
* **api:** raise on empty credential fallback instead of silent 401 (CAB-1908) ([#1973](https://github.com/stoa-platform/stoa/issues/1973)) ([eb67c31](https://github.com/stoa-platform/stoa/commit/eb67c317521b3dd3609aac2654d0a0450d8584ad))
* **api:** register api_gateway_assignments router before apis router (CAB-1888) ([#1903](https://github.com/stoa-platform/stoa/issues/1903)) ([7f8b621](https://github.com/stoa-platform/stoa/commit/7f8b6217e7b90bed2b56aa6b9e19597509db61cc))
* **api:** repair 15 pre-existing test failures blocking CP API pipeline ([#1902](https://github.com/stoa-platform/stoa/issues/1902)) ([109f56e](https://github.com/stoa-platform/stoa/commit/109f56ec7ac21f8e95248f4fe173f01da99cf752))
* **api:** repair Alembic migration chain (059 down_revision) ([#1579](https://github.com/stoa-platform/stoa/issues/1579)) ([8b51c05](https://github.com/stoa-platform/stoa/commit/8b51c05e18b40caff470e443b066b74ed4a1681c))
* **api:** resolve deployments stuck in pending/syncing status ([#1925](https://github.com/stoa-platform/stoa/issues/1925)) ([88594ca](https://github.com/stoa-platform/stoa/commit/88594ca65aebe78a09f10df2dffb24f7c89d5b06))
* **api:** resolve mypy errors blocking CI on main ([#1914](https://github.com/stoa-platform/stoa/issues/1914)) ([98bb16b](https://github.com/stoa-platform/stoa/commit/98bb16b774e2e07b1ac9bb6c601c8f08a4794033))
* **api:** resolve pre-existing mypy errors blocking CP API deploy ([#1463](https://github.com/stoa-platform/stoa/issues/1463)) ([47cdd29](https://github.com/stoa-platform/stoa/commit/47cdd296ca9edf51b921bf0c31ab6908d9fc9e00))
* **api:** set cloudflare proxy backend health to NULL (CAB-1725) ([#1532](https://github.com/stoa-platform/stoa/issues/1532)) ([5941e06](https://github.com/stoa-platform/stoa/commit/5941e068163150f9f590f6a96708e9341d80d83a))
* **api:** set environment on app create (CAB-1667) ([#1448](https://github.com/stoa-platform/stoa/issues/1448)) ([1754ea7](https://github.com/stoa-platform/stoa/commit/1754ea726a17665028cf18eef2919ca31f26cf54))
* **api:** strip timezone from period_start in usage/record (CAB-1822) ([#1768](https://github.com/stoa-platform/stoa/issues/1768)) ([fbd8617](https://github.com/stoa-platform/stoa/commit/fbd861714e4e558df45aa25c21d14bb87b13363e))
* **api:** support KEYCLOAK_ADMIN_PASSWORD env var fallback ([#1444](https://github.com/stoa-platform/stoa/issues/1444)) ([add2c97](https://github.com/stoa-platform/stoa/commit/add2c974313f43130daef0c3424388af69989ee5))
* **api:** update contract tests and OpenAPI snapshot for tenant-scoped routes ([#1901](https://github.com/stoa-platform/stoa/issues/1901)) ([2bbee48](https://github.com/stoa-platform/stoa/commit/2bbee48ac967b049a2a68713c9d226e0cb95ce7b))
* **api:** update deployment flags in GitLab on deploy ([#1454](https://github.com/stoa-platform/stoa/issues/1454)) ([d20a7e8](https://github.com/stoa-platform/stoa/commit/d20a7e8dfb6e33190ebee497599b0b4350bc6917))
* **api:** update OpenAPI snapshot for gateway cleanup + portal enrichment ([#1961](https://github.com/stoa-platform/stoa/issues/1961)) ([129491a](https://github.com/stoa-platform/stoa/commit/129491aa47a5cb87e74b72538479001f4ed1ff49))
* **api:** update OpenAPI snapshot for promotions/complete endpoint ([#1631](https://github.com/stoa-platform/stoa/issues/1631)) ([8a8b550](https://github.com/stoa-platform/stoa/commit/8a8b550535ae49cef6c119ec7a0503877d281c9d))
* **api:** update OpenAPI snapshot for versions endpoint (CAB-1813) ([#1743](https://github.com/stoa-platform/stoa/issues/1743)) ([b8b42ef](https://github.com/stoa-platform/stoa/commit/b8b42efe6178bb3beb7e785040c29cf328c6547b))
* **api:** update platform_info tests for enriched response schema ([#1849](https://github.com/stoa-platform/stoa/issues/1849)) ([5645e62](https://github.com/stoa-platform/stoa/commit/5645e62a23b862b68237d9bbc334e3aff8477c3b))
* **api:** use CAST() for jsonb in migration 057 ([#1491](https://github.com/stoa-platform/stoa/issues/1491)) ([e17dcc6](https://github.com/stoa-platform/stoa/commit/e17dcc61c6b1398c1f3c0b6d107f347ea470de45))
* **api:** use event_id.keyword for transaction detail lookup ([#1685](https://github.com/stoa-platform/stoa/issues/1685)) ([066c71c](https://github.com/stoa-platform/stoa/commit/066c71c684ead82502a79787a1a7169e7297bc63))
* **api:** use full revision slug in migration 057 ([#1488](https://github.com/stoa-platform/stoa/issues/1488)) ([81ecce3](https://github.com/stoa-platform/stoa/commit/81ecce36dbe380f7164e638cb9558b1630b4620d))
* **api:** use getattr for optional GATEWAY_ADMIN_KEY ([#1944](https://github.com/stoa-platform/stoa/issues/1944)) ([5f04472](https://github.com/stoa-platform/stoa/commit/5f044727d3651b078b335862da68081c7b0e6aea))
* **api:** use internal ArgoCD URL and add NetworkPolicies ([#1456](https://github.com/stoa-platform/stoa/issues/1456)) ([1026e18](https://github.com/stoa-platform/stoa/commit/1026e1858a68c380e958a01cca343c473581b1e4))
* **api:** use static ArgoCD API token for platform status ([#1459](https://github.com/stoa-platform/stoa/issues/1459)) ([9ec2bfb](https://github.com/stoa-platform/stoa/commit/9ec2bfb5b6d295ab027f13511b857ced1f2b9808))
* **auth:** add production redirect URIs to opensearch-dashboards OIDC client ([#1684](https://github.com/stoa-platform/stoa/issues/1684)) ([5f59fee](https://github.com/stoa-platform/stoa/commit/5f59fee8b6512dc7808d34d336ca7b3f1f5056dd))
* **ci:** add missing SYNC_ENGINE_INTERVAL_SECONDS mock in worker tests ([#1929](https://github.com/stoa-platform/stoa/issues/1929)) ([b360a7e](https://github.com/stoa-platform/stoa/commit/b360a7e8b6ae5b4ff5fb7beb3db0c9d8e5535d68))
* **ci:** break L3 dispatch loop — dedup + merged PR check ([#1512](https://github.com/stoa-platform/stoa/issues/1512)) ([a206d5d](https://github.com/stoa-platform/stoa/commit/a206d5da96a1b08e93deedccfbe154124fd7c114))
* **ci:** decouple Docker build/deploy from CI on main push ([#1511](https://github.com/stoa-platform/stoa/issues/1511)) ([57cedad](https://github.com/stoa-platform/stoa/commit/57cedadb51bcb21feba21fe04fd1906acbcbbe6d))
* **ci:** fix Arena L0/L2 failures and add serverless GHA benchmark ([#1950](https://github.com/stoa-platform/stoa/issues/1950)) ([0cc0548](https://github.com/stoa-platform/stoa/commit/0cc0548c24521979236471acb6cd189c8ca4c479))
* **ci:** gate docker/deploy jobs on CI success ([#1629](https://github.com/stoa-platform/stoa/issues/1629)) ([3f579ff](https://github.com/stoa-platform/stoa/commit/3f579ff633f7ae872e586b493c57da6d227a46a8))
* **ci:** report actual CI result in reusable workflows ([#1623](https://github.com/stoa-platform/stoa/issues/1623)) ([d65897e](https://github.com/stoa-platform/stoa/commit/d65897e036e8533ccebdb5716d9a09054208b385))
* **ci:** suppress mypy false-positives in adapters blocking main ([#1919](https://github.com/stoa-platform/stoa/issues/1919)) ([5d25cce](https://github.com/stoa-platform/stoa/commit/5d25cce8aac9ede17cf460b07ae0537741f8737d))
* **ci:** update get_deployment test to match JOIN-based query ([#1932](https://github.com/stoa-platform/stoa/issues/1932)) ([673420e](https://github.com/stoa-platform/stoa/commit/673420e67acdff4b31b870ba3b1a6cf6a74b293b))
* **ci:** update list_deployments test mock to return dict (CAB-1888) ([#1922](https://github.com/stoa-platform/stoa/issues/1922)) ([8d4b88c](https://github.com/stoa-platform/stoa/commit/8d4b88c60f2ea4c1502d866301248fedebd9551e))
* **ci:** update OpenAPI snapshot with gateway deployment fields ([#1920](https://github.com/stoa-platform/stoa/issues/1920)) ([5f491ce](https://github.com/stoa-platform/stoa/commit/5f491ced6bbf0cc351ddddc25d0e455e9815c22b))
* **ci:** update OpenAPI snapshot with new deployment endpoints ([#1942](https://github.com/stoa-platform/stoa/issues/1942)) ([e9e722f](https://github.com/stoa-platform/stoa/commit/e9e722ff15ac7b35ba36e92034b9704f54769630))
* **ci:** update snapshot + test mocks for deployed_environments ([#1956](https://github.com/stoa-platform/stoa/issues/1956)) ([a7fbeb8](https://github.com/stoa-platform/stoa/commit/a7fbeb88786b0ac56099f548623a76425efd652a))
* **ci:** use ubuntu-latest for CP API CI (CAB-1668) ([#1450](https://github.com/stoa-platform/stoa/issues/1450)) ([b00e696](https://github.com/stoa-platform/stoa/commit/b00e6966b8c7a60ec3a1b95f9ebecf12cb0942e7))
* **security:** persist opensearch security config + dashboard in git (CAB-1866) ([#1863](https://github.com/stoa-platform/stoa/issues/1863)) ([78ad9de](https://github.com/stoa-platform/stoa/commit/78ad9de2b19b144a28dacbdd087e7211298bb8aa))
* **security:** remove central bank references from codebase ([#1622](https://github.com/stoa-platform/stoa/issues/1622)) ([67326e2](https://github.com/stoa-platform/stoa/commit/67326e274098f3cd91a802cc73757e371f2bd0ac))
* **security:** remove stack trace exposure in error responses ([#1930](https://github.com/stoa-platform/stoa/issues/1930)) ([9774744](https://github.com/stoa-platform/stoa/commit/97747445a508b196c6dd1c3bbecdd3ff0206ba19))
* **security:** resolve 31 CodeQL and Trivy scan alerts ([#1565](https://github.com/stoa-platform/stoa/issues/1565)) ([fee5e7b](https://github.com/stoa-platform/stoa/commit/fee5e7b7fb0c550de18ad7f995ab392633fcd46c))
* **security:** resolve 7 CodeQL code scanning alerts ([#1749](https://github.com/stoa-platform/stoa/issues/1749)) ([ac9e39b](https://github.com/stoa-platform/stoa/commit/ac9e39b0d21d7eb6131e745ca27f5a6d36a845fc))
* **ui,api:** add gateway_type filter to drift detection (CAB-1887) ([#1892](https://github.com/stoa-platform/stoa/issues/1892)) ([63d15e7](https://github.com/stoa-platform/stoa/commit/63d15e7a8720f7aee2c3d80513c2548ff5f6deff))
* **ui:** align drift detection env filter with registry/overview (CAB-1887) ([#1894](https://github.com/stoa-platform/stoa/issues/1894)) ([7d8cf68](https://github.com/stoa-platform/stoa/commit/7d8cf68aa3433340f332d5dbfbfa975111d94ea3))
* **ui:** correct gateway instances API endpoint path ([#1533](https://github.com/stoa-platform/stoa/issues/1533)) ([1169783](https://github.com/stoa-platform/stoa/commit/11697832a8df442811e63571e479e7fbf5c674e8))
* **ui:** prevent OIDC interception of MCP connector OAuth callback (CAB-1790) ([#1720](https://github.com/stoa-platform/stoa/issues/1720)) ([ec5d957](https://github.com/stoa-platform/stoa/commit/ec5d957f6a98622c599364480b3952e1529da5a4))
* **ui:** resolve stoa-gateway text ambiguity in OperationsDashboard test ([#1634](https://github.com/stoa-platform/stoa/issues/1634)) ([4884664](https://github.com/stoa-platform/stoa/commit/4884664104d1a1751dc3bcd33f5798d83c186b04))
