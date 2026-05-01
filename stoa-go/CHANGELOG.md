# Changelog

## [0.3.9](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.8...stoa-go-v0.3.9) (2026-05-01)


### Bug Fixes

* **stoa-connect:** normalize webMethods externalDocs payload ([7cec6c8](https://github.com/stoa-platform/stoa/commit/7cec6c892915c03042bfccf8cd1c444b9d5bbc5b))
* **sync:** enforce route ack step consistency ([#2654](https://github.com/stoa-platform/stoa/issues/2654)) ([4c7e1e6](https://github.com/stoa-platform/stoa/commit/4c7e1e641b5bf4497a349dc9e40c90a02b98290f))

## [0.3.8](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.7...stoa-go-v0.3.8) (2026-04-23)


### Bug Fixes

* **stoa-go:** close GO-1 P0 — 6 critical webMethods adapter bugs ([#2492](https://github.com/stoa-platform/stoa/issues/2492)) ([afaef4b](https://github.com/stoa-platform/stoa/commit/afaef4bf9ef2148efe129de31fd2bab72fa640ed))
* **stoa-go:** GO-1 P1 — externalDocs walk + jwt/ipFilter mapping ([#2494](https://github.com/stoa-platform/stoa/issues/2494)) ([d9f9089](https://github.com/stoa-platform/stoa/commit/d9f90895b3866610e40241d2e08e4878b72718b0))
* **stoa-go:** GO-1 P2 — defensive hardening + cleanup (7 bugs) ([#2495](https://github.com/stoa-platform/stoa/issues/2495)) ([f9542cf](https://github.com/stoa-platform/stoa/commit/f9542cf6738ae2cfadd8cd6bdd9045f38047d318))

## [0.3.7](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.6...stoa-go-v0.3.7) (2026-04-19)


### Features

* **cli:** support Tool kind in stoactl apply + global --namespace flag ([#2407](https://github.com/stoa-platform/stoa/issues/2407)) ([a2b28cc](https://github.com/stoa-platform/stoa/commit/a2b28cc4321ca5a519955003c090d243fd1802d6))


### Bug Fixes

* **cli:** plumb --admin flag through all stoactl commands (CAB-2107) ([#2413](https://github.com/stoa-platform/stoa/issues/2413)) ([c124691](https://github.com/stoa-platform/stoa/commit/c124691691d7f8541f0a8b7efa9fcf53e7b10a4f))
* **mcp:** restore temperature=0 + add tool-name bijection in phase05 bench (CAB-2116) ([#2428](https://github.com/stoa-platform/stoa/issues/2428)) ([0d6eccc](https://github.com/stoa-platform/stoa/commit/0d6eccc75830b29edccc79a963842982ec643b24))

## [0.3.6](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.5...stoa-go-v0.3.6) (2026-04-17)


### Bug Fixes

* **cli:** scope stoactl API CRUD to tenant paths + audit docs (CAB-2095) ([#2398](https://github.com/stoa-platform/stoa/issues/2398)) ([aca8fc5](https://github.com/stoa-platform/stoa/commit/aca8fc5319e728c0ce813c879ca573f83066bd67))

## [0.3.5](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.4...stoa-go-v0.3.5) (2026-04-15)


### Features

* **cli:** add full resource CRUD to stoactl (CAB-2053 phase 3) ([#2345](https://github.com/stoa-platform/stoa/issues/2345)) ([be1ac62](https://github.com/stoa-platform/stoa/commit/be1ac625c10f9a7ce1a0985c7344211084da212d))
* **cli:** unified schema registry gostoa.dev/v1beta1 (CAB-2053 phase 4) ([#2348](https://github.com/stoa-platform/stoa/issues/2348)) ([f70c12d](https://github.com/stoa-platform/stoa/commit/f70c12d8a9cf5560f49a0031756f8e6ce0f12f6c))

## [0.3.4](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.3...stoa-go-v0.3.4) (2026-04-09)


### Features

* **gateway:** stoactl catalog sync + audit export (CAB-2021, CAB-2022) ([#2268](https://github.com/stoa-platform/stoa/issues/2268)) ([e48a365](https://github.com/stoa-platform/stoa/commit/e48a3650fdfc27c5778a6bb49679b4ba14c0597d))


### Bug Fixes

* **cli:** align stoactl mcp with gateway response formats (CAB-2006) ([#2248](https://github.com/stoa-platform/stoa/issues/2248)) ([fc56a32](https://github.com/stoa-platform/stoa/commit/fc56a324b3caa4c401f03f1598b71047d31bb05a))

## [0.3.3](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.2...stoa-go-v0.3.3) (2026-04-08)


### Features

* add target_gateway_url to gateway detail panel ([#2069](https://github.com/stoa-platform/stoa/issues/2069)) ([c07557f](https://github.com/stoa-platform/stoa/commit/c07557feb537c2f029909763e62cf719eacb18db))
* **api,gateway:** generation-based sync reconciliation (CAB-1950) ([#2132](https://github.com/stoa-platform/stoa/issues/2132)) ([d78db2b](https://github.com/stoa-platform/stoa/commit/d78db2b087becfd7a8ae4bf6862f23f5fbb5545e))
* **api:** gateway enabled flag + visibility + soft disable (CAB-1979) ([#2201](https://github.com/stoa-platform/stoa/issues/2201)) ([0136dd7](https://github.com/stoa-platform/stoa/commit/0136dd749acfb8b4d0e64be3a5a3388c4f6b17b8))
* **api:** outbound-only connect — webmethods lifecycle + OpenAPI spec delivery (CAB-1929) ([#2025](https://github.com/stoa-platform/stoa/issues/2025)) ([0fb3266](https://github.com/stoa-platform/stoa/commit/0fb326683f159da2da42aa16f9f145d8f48bc6e3))
* **api:** promotion deploy chain — state machine, route-sync-ack, verify+activate ([#2034](https://github.com/stoa-platform/stoa/issues/2034)) ([fe242c8](https://github.com/stoa-platform/stoa/commit/fe242c821b2a412b94b84614f607f0d8f3ade21a))
* **cli:** stoactl mcp subcommand + shell completions (CAB-2006) ([#2247](https://github.com/stoa-platform/stoa/issues/2247)) ([c1f339a](https://github.com/stoa-platform/stoa/commit/c1f339ad1c8607c970208dd6549cce608692b4d6))
* **e2e:** subscription auth audit + observability fixes ([#2194](https://github.com/stoa-platform/stoa/issues/2194)) ([a77c0a2](https://github.com/stoa-platform/stoa/commit/a77c0a2bc4c0133df61ed8503ac18022f46eb349))
* **gateway:** add ui_url + public_url to stoa-connect registration (CAB-1953) ([#2167](https://github.com/stoa-platform/stoa/issues/2167)) ([0bdbe08](https://github.com/stoa-platform/stoa/commit/0bdbe08bf0f17827e4fd6be645aed0adeffc9341))
* **gateway:** agent-side sync step tracking (CAB-1947) ([#2130](https://github.com/stoa-platform/stoa/issues/2130)) ([5eaa4e4](https://github.com/stoa-platform/stoa/commit/5eaa4e4e710787b6745f3cbcc482f145254dd7ce))
* **gateway:** SSE deployment stream client for stoa-connect (CAB-1932) ([#2073](https://github.com/stoa-platform/stoa/issues/2073)) ([cd4a7e3](https://github.com/stoa-platform/stoa/commit/cd4a7e3bd963eea37aa73542ebac420f51ab318d))
* **gateway:** STOA Connect webMethods bridge — POC March 31 ([#1992](https://github.com/stoa-platform/stoa/issues/1992)) ([ccd1c3c](https://github.com/stoa-platform/stoa/commit/ccd1c3cafa7911c08912f0e113fbf9c3090d51a0))
* **gateway:** webMethods robustness — route sync ack + tests (CAB-1927) ([#2031](https://github.com/stoa-platform/stoa/issues/2031)) ([12b51af](https://github.com/stoa-platform/stoa/commit/12b51af19bb8aeb76663d7d8c80907680b7057d7))
* **go:** add webMethods OIDC + alias support (CAB-1926) ([#2021](https://github.com/stoa-platform/stoa/issues/2021)) ([28d6cb6](https://github.com/stoa-platform/stoa/commit/28d6cb68749f94bf75969758b8da00960711b0ea))
* **go:** add webMethods telemetry collection + config sync (CAB-1928) ([#2020](https://github.com/stoa-platform/stoa/issues/2020)) ([d645456](https://github.com/stoa-platform/stoa/commit/d64545607c894fccaba90e55f0750736f817466a))


### Bug Fixes

* **api,gateway,go:** normalize health check payloads (CAB-1916) ([#2008](https://github.com/stoa-platform/stoa/issues/2008)) ([0366d18](https://github.com/stoa-platform/stoa/commit/0366d18066aad1610cab0cacc15e554d26ebe0de))
* **api:** send openapi_spec as JSON object to stoa-connect ([#2036](https://github.com/stoa-platform/stoa/issues/2036)) ([a1fdec1](https://github.com/stoa-platform/stoa/commit/a1fdec199eff563bb9abf6d4e7be3c014548500e))
* **deps:** patch 11 security alerts — node-forge, picomatch, go-jose ([#2187](https://github.com/stoa-platform/stoa/issues/2187)) ([0be880e](https://github.com/stoa-platform/stoa/commit/0be880e232e9c6caa968c6a5295e54ed3967d654))
* **gateway,api:** resolve sync drift errors 400/401/500 (CAB-1944) ([#2126](https://github.com/stoa-platform/stoa/issues/2126)) ([65e2384](https://github.com/stoa-platform/stoa/commit/65e2384931d4c2ee5c28508de720a6e0c17920a8))
* **gateway:** re-register on heartbeat 404 after CP auto-purge ([#2103](https://github.com/stoa-platform/stoa/issues/2103)) ([12fac24](https://github.com/stoa-platform/stoa/commit/12fac2494c620cdfbbc9f0ff62dfe071dbabcd65))
* **gateway:** strip Swagger 2.0 $ref in responses + per-route sync-ack (CAB-1944) ([#2131](https://github.com/stoa-platform/stoa/issues/2131)) ([8c9f6a5](https://github.com/stoa-platform/stoa/commit/8c9f6a5dbc3e8ce6aa7f3c668ceaa47915eb31d1))
* **gateway:** uppercase securityScheme types + continue on sync error (CAB-1944) ([#2127](https://github.com/stoa-platform/stoa/issues/2127)) ([5598f62](https://github.com/stoa-platform/stoa/commit/5598f62aff005cfe8cd1debf2a4495b58eb42fd4))
* **gateway:** wM sync — swagger detection + spec-only payload ([#2037](https://github.com/stoa-platform/stoa/issues/2037)) ([e3a85c3](https://github.com/stoa-platform/stoa/commit/e3a85c36421562481aac85119c76c40c5754b714))
* **go:** fix webMethods adapter critical bugs (CAB-1925) ([#2019](https://github.com/stoa-platform/stoa/issues/2019)) ([a9d4a37](https://github.com/stoa-platform/stoa/commit/a9d4a37061198906aecfbb39103a7aa9c1307e32))
* **ui:** show gateway URLs for all modes + fix stoa-link hostname (CAB-1953) ([#2160](https://github.com/stoa-platform/stoa/issues/2160)) ([3ee4c66](https://github.com/stoa-platform/stoa/commit/3ee4c66397b89d506bbfcd6829637f0bc46ee563))

## [0.3.2](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.1...stoa-go-v0.3.2) (2026-03-25)


### Bug Fixes

* **ci:** fix Arena L0/L2 failures and add serverless GHA benchmark ([#1950](https://github.com/stoa-platform/stoa/issues/1950)) ([0cc0548](https://github.com/stoa-platform/stoa/commit/0cc0548c24521979236471acb6cd189c8ca4c479))
* **security:** persist opensearch security config + dashboard in git (CAB-1866) ([#1863](https://github.com/stoa-platform/stoa/issues/1863)) ([78ad9de](https://github.com/stoa-platform/stoa/commit/78ad9de2b19b144a28dacbdd087e7211298bb8aa))

## [0.3.1](https://github.com/stoa-platform/stoa/compare/stoa-go-v0.3.0...stoa-go-v0.3.1) (2026-03-23)


### Features

* **api,ui:** surface cost/token metrics in AI Factory dashboard (CAB-1666) ([#1487](https://github.com/stoa-platform/stoa/issues/1487)) ([9d385a1](https://github.com/stoa-platform/stoa/commit/9d385a16f0b11f5fc6c62abb563dde4664cde02d))
* **api:** adopt ArgoCD entries on gateway registration (CAB-1771) ([#1658](https://github.com/stoa-platform/stoa/issues/1658)) ([af45581](https://github.com/stoa-platform/stoa/commit/af455812305ff3cf2a89e965d54582ac9864c908))
* **connect:** credential relay — Vault consumer secret injection (CAB-1900) ([#1954](https://github.com/stoa-platform/stoa/issues/1954)) ([1fa00d1](https://github.com/stoa-platform/stoa/commit/1fa00d19ec5010d355382e336a7456183233048f))
* **connect:** route sync loop — fetch CP routes, push to local gateway (CAB-1898) ([#1953](https://github.com/stoa-platform/stoa/issues/1953)) ([81015c6](https://github.com/stoa-platform/stoa/commit/81015c6c96b2d3aaee002520eb36e470cc5601c1))
* **gateway:** add gRPC protocol support with proto parser and MCP bridge (CAB-1755) ([#1757](https://github.com/stoa-platform/stoa/issues/1757)) ([c221fef](https://github.com/stoa-platform/stoa/commit/c221fefeb9a412b456ce63277d29166d63094e9c))
* **gateway:** add OpenTelemetry instrumentation to stoa-connect (CAB-1870) ([#1853](https://github.com/stoa-platform/stoa/issues/1853)) ([7551a93](https://github.com/stoa-platform/stoa/commit/7551a93329551cec4843ef938d80067958de97af))
* **gateway:** API proxy config + credential injection (CAB-1723, CAB-1724) ([#1516](https://github.com/stoa-platform/stoa/issues/1516)) ([f8abfd1](https://github.com/stoa-platform/stoa/commit/f8abfd11970b61db3fec6c342b203d204ebdbdaa))
* **gateway:** expose OTLP ingress + HTTP exporter for VPS tracing (CAB-1870) ([#1855](https://github.com/stoa-platform/stoa/issues/1855)) ([283ee67](https://github.com/stoa-platform/stoa/commit/283ee673bb4f8bc664340b4c536d2493d9cf23eb))
* **gateway:** wire PingoraPool into proxy path (CAB-1849) ([#1905](https://github.com/stoa-platform/stoa/issues/1905)) ([ba39741](https://github.com/stoa-platform/stoa/commit/ba397419b0eae445ccf29b7c0b8d0f0f2d4733e8))
* **ui:** add contextual sub-navigation for hidden pages (CAB-1785) ([#1678](https://github.com/stoa-platform/stoa/issues/1678)) ([6f2f8d1](https://github.com/stoa-platform/stoa/commit/6f2f8d1ee3caef9ae9c2c22b809bc7ce52c65acc))


### Bug Fixes

* **api:** support KEYCLOAK_ADMIN_PASSWORD env var fallback ([#1444](https://github.com/stoa-platform/stoa/issues/1444)) ([add2c97](https://github.com/stoa-platform/stoa/commit/add2c974313f43130daef0c3424388af69989ee5))
* **auth:** add production redirect URIs to opensearch-dashboards OIDC client ([#1684](https://github.com/stoa-platform/stoa/issues/1684)) ([5f59fee](https://github.com/stoa-platform/stoa/commit/5f59fee8b6512dc7808d34d336ca7b3f1f5056dd))
* **ci:** break L3 dispatch loop — dedup + merged PR check ([#1512](https://github.com/stoa-platform/stoa/issues/1512)) ([a206d5d](https://github.com/stoa-platform/stoa/commit/a206d5da96a1b08e93deedccfbe154124fd7c114))
* **ci:** decouple Docker build/deploy from CI on main push ([#1511](https://github.com/stoa-platform/stoa/issues/1511)) ([57cedad](https://github.com/stoa-platform/stoa/commit/57cedadb51bcb21feba21fe04fd1906acbcbbe6d))
* **ci:** gate docker/deploy jobs on CI success ([#1629](https://github.com/stoa-platform/stoa/issues/1629)) ([3f579ff](https://github.com/stoa-platform/stoa/commit/3f579ff633f7ae872e586b493c57da6d227a46a8))
* **ci:** report actual CI result in reusable workflows ([#1623](https://github.com/stoa-platform/stoa/issues/1623)) ([d65897e](https://github.com/stoa-platform/stoa/commit/d65897e036e8533ccebdb5716d9a09054208b385))
* **ui:** correct gateway instances API endpoint path ([#1533](https://github.com/stoa-platform/stoa/issues/1533)) ([1169783](https://github.com/stoa-platform/stoa/commit/11697832a8df442811e63571e479e7fbf5c674e8))
* **ui:** resolve stoa-gateway text ambiguity in OperationsDashboard test ([#1634](https://github.com/stoa-platform/stoa/issues/1634)) ([4884664](https://github.com/stoa-platform/stoa/commit/4884664104d1a1751dc3bcd33f5798d83c186b04))
