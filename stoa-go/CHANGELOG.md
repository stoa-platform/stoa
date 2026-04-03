# Changelog

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
