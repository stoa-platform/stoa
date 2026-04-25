# Changelog

## [1.5.5](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.5.4...control-plane-ui-v1.5.5) (2026-04-25)


### Bug Fixes

* **demo:** bridge route sync for smoke ([#2553](https://github.com/stoa-platform/stoa/issues/2553)) ([f6d6497](https://github.com/stoa-platform/stoa/commit/f6d649728ae04412ea454d68d5c4f003192dffe9))

## [1.5.4](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.5.3...control-plane-ui-v1.5.4) (2026-04-24)


### Bug Fixes

* **ui:** close CAB-2164 UI-3 cleanup — zombies doc + any hardening ([#2527](https://github.com/stoa-platform/stoa/issues/2527)) ([31f00b7](https://github.com/stoa-platform/stoa/commit/31f00b79d4254fd3ae1d3e7a65e90399d22c7bfe))

## [1.5.3](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.5.2...control-plane-ui-v1.5.3) (2026-04-24)


### Bug Fixes

* **ui-1:** close UI-1 Wave 1 bug hunt batch (8 items) ([#2525](https://github.com/stoa-platform/stoa/issues/2525)) ([83abcf7](https://github.com/stoa-platform/stoa/commit/83abcf7a28cb797800f875853fda27a49a00e372))

## [1.5.2](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.5.1...control-plane-ui-v1.5.2) (2026-04-24)


### Bug Fixes

* **ui-2:** P1 batch — 14 P1 fixes across dashboards, auth, http, skills ([#2519](https://github.com/stoa-platform/stoa/issues/2519)) ([63a3010](https://github.com/stoa-platform/stoa/commit/63a3010f075a532a02a191aca2a4cb4163f42d32))
* **ui-2:** P2 cleanup batch — close UI-2 module (8 code fixes + 3 WONT-FIX + 2 deferred) ([#2521](https://github.com/stoa-platform/stoa/issues/2521)) ([b35039a](https://github.com/stoa-platform/stoa/commit/b35039a0943a2fab3f16de1abfebc3acd619c160))

## [1.5.1](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.5.0...control-plane-ui-v1.5.1) (2026-04-24)


### Bug Fixes

* **ui-2:** close 10 P0 critical bugs (refresh token cascade + SSE + fetch bypass + path encoding) ([#2514](https://github.com/stoa-platform/stoa/issues/2514)) ([5247f22](https://github.com/stoa-platform/stoa/commit/5247f22c51a405693a7f58f44fa041e46ce91e3d))

## [1.5.0](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.4.2...control-plane-ui-v1.5.0) (2026-04-22)


### Features

* **ui:** migrate critical entities to OpenAPI-generated types (Wave 1) ([#2471](https://github.com/stoa-platform/stoa/issues/2471)) ([ce505b0](https://github.com/stoa-platform/stoa/commit/ce505b0acdd8cf08a51b9eb4686ce4f406cb252f))


### Bug Fixes

* **ui:** align Application alias with regenerated schema (CAB-2159) ([#2476](https://github.com/stoa-platform/stoa/issues/2476)) ([d41ba1c](https://github.com/stoa-platform/stoa/commit/d41ba1c0028662729cccd97626f9045cd155e47c))

## [1.4.2](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.4.1...control-plane-ui-v1.4.2) (2026-04-20)


### Bug Fixes

* **api:** scrub stack traces + axios/follow-redirects bumps (CAB-2138) ([#2441](https://github.com/stoa-platform/stoa/issues/2441)) ([ab2a26b](https://github.com/stoa-platform/stoa/commit/ab2a26b303c7baf86a8eea77f62edd3d8a534b8c))

## [1.4.1](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.4.0...control-plane-ui-v1.4.1) (2026-04-19)


### Bug Fixes

* **mcp:** restore temperature=0 + add tool-name bijection in phase05 bench (CAB-2116) ([#2428](https://github.com/stoa-platform/stoa/issues/2428)) ([0d6eccc](https://github.com/stoa-platform/stoa/commit/0d6eccc75830b29edccc79a963842982ec643b24))

## [1.4.0](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.3.0...control-plane-ui-v1.4.0) (2026-04-16)


### Features

* **mcp:** stoa-impact MCP + SDD L1 (CAB-2066) ([#2377](https://github.com/stoa-platform/stoa/issues/2377)) ([551d330](https://github.com/stoa-platform/stoa/commit/551d330e5af0251e544c62317bc5e2fb1ddfa738))


### Bug Fixes

* **ui:** chown /usr/share/nginx/html for sed -i index.html ([#2375](https://github.com/stoa-platform/stoa/issues/2375)) ([17a693b](https://github.com/stoa-platform/stoa/commit/17a693b94d81e3b940ad24d119a39b9a0c13398e))

## [1.3.0](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.2.2...control-plane-ui-v1.3.0) (2026-04-16)


### Features

* **local:** Tilt + k3d local environment + Alembic migration fixes ([#2359](https://github.com/stoa-platform/stoa/issues/2359)) ([86392f8](https://github.com/stoa-platform/stoa/commit/86392f891154071cc2201a26a85967fd91065c62))


### Bug Fixes

* **ci:** resolve Helm lint and ESLint SAST pre-existing failures (CAB-2053) ([#2351](https://github.com/stoa-platform/stoa/issues/2351)) ([530fafa](https://github.com/stoa-platform/stoa/commit/530fafa8fdc8c28bd8ce5765ac51e608febf53eb))
* **ui:** Gateway Dashboard Inconsistencies — unified status, remove mocks, aggregated multi-gateway overview (CAB-1887) ([#2365](https://github.com/stoa-platform/stoa/issues/2365)) ([db2c4af](https://github.com/stoa-platform/stoa/commit/db2c4aff42b583251a02570368b92c6b3f6fadb6))
* **ui:** prevent stale runtime-config.js browser cache ([#2294](https://github.com/stoa-platform/stoa/issues/2294)) ([3a65210](https://github.com/stoa-platform/stoa/commit/3a6521094d7e29c724f11018e6e83a55562ff257))

## [1.2.2](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.2.1...control-plane-ui-v1.2.2) (2026-04-11)


### Bug Fixes

* **deps:** revert Vite 8, Tailwind 4, plugin-react 6 breaking bumps (CAB-2034) ([#2292](https://github.com/stoa-platform/stoa/issues/2292)) ([4b65694](https://github.com/stoa-platform/stoa/commit/4b656942ec5b814ceae41735179f3b185604a8bc))
* **security:** remove default credentials, enforce Vault (CAB-2052) ([#2296](https://github.com/stoa-platform/stoa/issues/2296)) ([c953ae3](https://github.com/stoa-platform/stoa/commit/c953ae3cc63f74aebb7dad2fbe8546ced52cde0c))
* **ui:** skip broken MCPServers tests + remove orphaned test (CAB-2034) ([#2289](https://github.com/stoa-platform/stoa/issues/2289)) ([655f16b](https://github.com/stoa-platform/stoa/commit/655f16bf93e7ca5c36cb891a9a4bd222f0694c78))

## [1.2.1](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.2.0...control-plane-ui-v1.2.1) (2026-04-09)


### Bug Fixes

* **ui:** revert ESLint 10→8 + pin TypeScript 5.7 (CAB-2034) ([#2286](https://github.com/stoa-platform/stoa/issues/2286)) ([cac86c3](https://github.com/stoa-platform/stoa/commit/cac86c3c000f1aac25d8c8e7430b0ee909dfcded))

## [1.2.0](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.1.0...control-plane-ui-v1.2.0) (2026-04-09)


### Features

* add target_gateway_url to gateway detail panel ([#2069](https://github.com/stoa-platform/stoa/issues/2069)) ([c07557f](https://github.com/stoa-platform/stoa/commit/c07557feb537c2f029909763e62cf719eacb18db))
* **api,ui,gateway:** traffic seed link/connect + Call Flow interactive filters (CAB-1997) ([#2228](https://github.com/stoa-platform/stoa/issues/2228)) ([627dcbe](https://github.com/stoa-platform/stoa/commit/627dcbe03ec0c0259ce56bbe9e40dac5f3890c53))
* **api,ui:** add ui_url field to GatewayInstance for admin UI links (CAB-1953) ([#2149](https://github.com/stoa-platform/stoa/issues/2149)) ([725dffa](https://github.com/stoa-platform/stoa/commit/725dffa72e55e05d2befe77644d3985f18ae865d))
* **api,ui:** gitops tenant auto-provision + admin cross-tenant API view ([#2114](https://github.com/stoa-platform/stoa/issues/2114)) ([8cebf8b](https://github.com/stoa-platform/stoa/commit/8cebf8b5352c20a215c10414a2762e67b69bfbc4))
* **api,ui:** proxy gateway MCP tools to Console via CP API (CAB-1962) ([#2154](https://github.com/stoa-platform/stoa/issues/2154)) ([11e3d90](https://github.com/stoa-platform/stoa/commit/11e3d9023d114abd8dd518cdeb51e88e35f7e3a9))
* **api:** gateway enabled flag + visibility + soft disable (CAB-1979) ([#2201](https://github.com/stoa-platform/stoa/issues/2201)) ([0136dd7](https://github.com/stoa-platform/stoa/commit/0136dd749acfb8b4d0e64be3a5a3388c4f6b17b8))
* **api:** OpenSearch traces router + gateway OTel spans (CAB-1997) ([#2221](https://github.com/stoa-platform/stoa/issues/2221)) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **api:** OpenSearch-first monitoring with native Prometheus metrics (CAB-1997) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **e2e:** subscription auth audit + observability fixes ([#2194](https://github.com/stoa-platform/stoa/issues/2194)) ([a77c0a2](https://github.com/stoa-platform/stoa/commit/a77c0a2bc4c0133df61ed8503ac18022f46eb349))
* **gateway,api,ui:** MCP Streamable HTTP endpoint + platform tool auto-sync ([#2245](https://github.com/stoa-platform/stoa/issues/2245)) ([fd7b408](https://github.com/stoa-platform/stoa/commit/fd7b4087ee21bfb83aa9fdc1e8d1cad1bb28abdf))
* **gateway,ui:** wire gateway metrics on all request types (CAB-1997) ([#2229](https://github.com/stoa-platform/stoa/issues/2229)) ([946a819](https://github.com/stoa-platform/stoa/commit/946a8191cb2b453184a2eb596634fe099e4172df))
* **ui,portal:** add data-testid + ARIA roles to 6 pages (CAB-1991) ([#2207](https://github.com/stoa-platform/stoa/issues/2207)) ([4a968dd](https://github.com/stoa-platform/stoa/commit/4a968dda0f75ddb9e974c0be958affc430d3cf5e))
* **ui:** add Backend API detail/edit view + deploy dialog search (CAB-1922) ([#2016](https://github.com/stoa-platform/stoa/issues/2016)) ([1f82ecd](https://github.com/stoa-platform/stoa/commit/1f82ecda20b2559469f37912154e57cebcdd1837))
* **ui:** chat usage dashboard with Recharts (CAB-1868) ([#2026](https://github.com/stoa-platform/stoa/issues/2026)) ([4b3fe35](https://github.com/stoa-platform/stoa/commit/4b3fe35fb2756565b8e0b9ce7f5caa5fd259c58d))
* **ui:** EU Public API Catalog browser with 1-click deploy (CAB-1639) ([#2032](https://github.com/stoa-platform/stoa/issues/2032)) ([480b6d3](https://github.com/stoa-platform/stoa/commit/480b6d35e55041bce267d74d462f5c09de21a7b9))
* **ui:** gateway detail page with status + config + actions (CAB-1981) ([#2203](https://github.com/stoa-platform/stoa/issues/2203)) ([37eea28](https://github.com/stoa-platform/stoa/commit/37eea28ba8e55e80bf46cc39eba73cc9813580fd))
* **ui:** make git provider labels dynamic (CAB-1892) ([#2064](https://github.com/stoa-platform/stoa/issues/2064)) ([55ff72c](https://github.com/stoa-platform/stoa/commit/55ff72c81895db8821a1ba7463452bfd62fb3c3c))
* **ui:** MCP server/tool enable/disable toggles (CAB-1978) ([#2197](https://github.com/stoa-platform/stoa/issues/2197)) ([70840af](https://github.com/stoa-platform/stoa/commit/70840af5d86bfa234965507a0e90ea3e42a29253))
* **ui:** platform MCP server tab, source badges, permissions matrix (CAB-2003) ([#2243](https://github.com/stoa-platform/stoa/issues/2243)) ([5d70feb](https://github.com/stoa-platform/stoa/commit/5d70feb80d263bced585e1b4d22612fb40a9a03e))
* **ui:** tool permissions matrix per tenant (CAB-1982) ([#2204](https://github.com/stoa-platform/stoa/issues/2204)) ([1ccea3c](https://github.com/stoa-platform/stoa/commit/1ccea3ceadfae62f44bb6224507089f0f969949d))
* **ui:** update locales + tests for dynamic git provider (CAB-1892) ([#2066](https://github.com/stoa-platform/stoa/issues/2066)) ([39fe155](https://github.com/stoa-platform/stoa/commit/39fe1555e4ff2dbb9228baeb222b91faf194bac9))
* **ui:** wire Kafka deploy workflow into deployment detail drawer (CAB-1951) ([#2141](https://github.com/stoa-platform/stoa/issues/2141)) ([57de865](https://github.com/stoa-platform/stoa/commit/57de8653891a56fd37966dddb180e521d5edc06c))


### Bug Fixes

* **api,gateway,ui:** sequential span waterfall display (CAB-1997) ([#2223](https://github.com/stoa-platform/stoa/issues/2223)) ([68c7012](https://github.com/stoa-platform/stoa/commit/68c70125784bcd8820fdfe85af22d217eeee177b))
* **api,ui:** server-side route filter for Call Flow top routes (CAB-1997) ([#2231](https://github.com/stoa-platform/stoa/issues/2231)) ([9218089](https://github.com/stoa-platform/stoa/commit/92180897bc229c60dd8f550e1d6ed4531d6679f1))
* **api:** Observability RBAC — tenant isolation Phase 1 (CAB-2027) ([#2272](https://github.com/stoa-platform/stoa/issues/2272)) ([2e71af6](https://github.com/stoa-platform/stoa/commit/2e71af6ffa7042db4a5ededae75e409dff0ec1f3))
* **api:** observability RBAC phase 2 (CAB-2031, CAB-2032) ([#2274](https://github.com/stoa-platform/stoa/issues/2274)) ([407438b](https://github.com/stoa-platform/stoa/commit/407438ba3ad1761e3d53f31219389164ee15afba))
* **api:** preserve health_details on failed gateway health check ([#1999](https://github.com/stoa-platform/stoa/issues/1999)) ([ac32c96](https://github.com/stoa-platform/stoa/commit/ac32c96f0aae3844eccd2cdd979b2c2382c98b66))
* **api:** unblock CI — health test imports + prettier + mypy ([#2071](https://github.com/stoa-platform/stoa/issues/2071)) ([9ed93d0](https://github.com/stoa-platform/stoa/commit/9ed93d03060d5d03112659f309e2852dfcf2e124))
* **ci:** move skills to directory format for slash command detection (CAB-2005) ([#2242](https://github.com/stoa-platform/stoa/issues/2242)) ([37b0e02](https://github.com/stoa-platform/stoa/commit/37b0e02e694c1afce2da663b8f98c11268b523ab))
* **deps:** patch 11 security alerts — node-forge, picomatch, go-jose ([#2187](https://github.com/stoa-platform/stoa/issues/2187)) ([0be880e](https://github.com/stoa-platform/stoa/commit/0be880e232e9c6caa968c6a5295e54ed3967d654))
* **gateway,api:** scope API discovery by gateway mode + gateway_id filter (CAB-1940) ([#2121](https://github.com/stoa-platform/stoa/issues/2121)) ([a01b245](https://github.com/stoa-platform/stoa/commit/a01b245e69f8dc5f2574762098e8d9ed361df930))
* **gateway,ui:** broaden discovery gate + discovery banner in GatewayDetail (CAB-1949) ([#2134](https://github.com/stoa-platform/stoa/issues/2134)) ([c2c4f42](https://github.com/stoa-platform/stoa/commit/c2c4f4284109e14dd1c48e4f8a2b8786fbed5d61))
* **gateway:** explicit OTLP batch config for Tempo (CAB-1974) ([#2193](https://github.com/stoa-platform/stoa/issues/2193)) ([80d09cd](https://github.com/stoa-platform/stoa/commit/80d09cdf0a96b5f882ae35f0859c85e58f586368))
* **ui:** add missing i18n keys for security + guardrails nav items ([#2196](https://github.com/stoa-platform/stoa/issues/2196)) ([3af62a4](https://github.com/stoa-platform/stoa/commit/3af62a412098c86b580df4aeb69d023bdd75e274))
* **ui:** add missing mocks for deploy drawer tests (CAB-1951) ([#2147](https://github.com/stoa-platform/stoa/issues/2147)) ([b2ba3ba](https://github.com/stoa-platform/stoa/commit/b2ba3bad7d4a5ff5cc89c07719fcb413553720bc))
* **ui:** CallFlow empty state + TraceDetail error UX (CAB-2039) ([#2277](https://github.com/stoa-platform/stoa/issues/2277)) ([de2cd5b](https://github.com/stoa-platform/stoa/commit/de2cd5b2f062fd5412bc0674865e1b4b4e3b204f))
* **ui:** connect RegisterApiModal submit button to form (CAB-1918) ([#2011](https://github.com/stoa-platform/stoa/issues/2011)) ([4dbb904](https://github.com/stoa-platform/stoa/commit/4dbb904010e5f44865ca99578b71367ddf00fd52))
* **ui:** correct API backend port 80 → 8000 in k8s deployment ([#2077](https://github.com/stoa-platform/stoa/issues/2077)) ([77a3254](https://github.com/stoa-platform/stoa/commit/77a32542a4bbd67d26d66761c1d01d842cc7859e))
* **ui:** fix broken imports in tenants-msw integration test (CAB-1951) ([#2148](https://github.com/stoa-platform/stoa/issues/2148)) ([d0ed6bd](https://github.com/stoa-platform/stoa/commit/d0ed6bd68982adf0fd479411a9b8c1fe0c2cd1ce))
* **ui:** hide health check button for connect-mode gateways ([#1996](https://github.com/stoa-platform/stoa/issues/1996)) ([e003dee](https://github.com/stoa-platform/stoa/commit/e003deea5067f63983647324865e630c0c2bcdba))
* **ui:** remove Call-Flow demo data fallback + fix seeder tenant (CAB-2034) ([#2273](https://github.com/stoa-platform/stoa/issues/2273)) ([e295bce](https://github.com/stoa-platform/stoa/commit/e295bcee9443982b9b27dd2b3368dabce7ddc189))
* **ui:** replace broken apis.gostoa.dev with api.gostoa.dev ([#2225](https://github.com/stoa-platform/stoa/issues/2225)) ([1ca0278](https://github.com/stoa-platform/stoa/commit/1ca0278b5a136ae16fb05727b47974fb6e36cd20))
* **ui:** replace SSE/Kafka wiring with sync_steps from REST (CAB-1951) ([#2153](https://github.com/stoa-platform/stoa/issues/2153)) ([3e392fc](https://github.com/stoa-platform/stoa/commit/3e392fc5296859b8c611acbd093e326eb2c5c159))
* **ui:** serialize openapi_spec as JSON string in API form (CAB-1941) ([#2120](https://github.com/stoa-platform/stoa/issues/2120)) ([1572cc9](https://github.com/stoa-platform/stoa/commit/1572cc98d8bb96136b00518e96ac48e57ac0c601))
* **ui:** show gateway URLs for all modes + fix stoa-link hostname (CAB-1953) ([#2160](https://github.com/stoa-platform/stoa/issues/2160)) ([3ee4c66](https://github.com/stoa-platform/stoa/commit/3ee4c66397b89d506bbfcd6829637f0bc46ee563))
* **ui:** update TraceDetail test to match renamed section header ([#2226](https://github.com/stoa-platform/stoa/issues/2226)) ([17c4ccc](https://github.com/stoa-platform/stoa/commit/17c4cccc9fc1258e05260f23cd1e1fdf7438a1a4))

## [1.1.0](https://github.com/stoa-platform/stoa/compare/control-plane-ui-v1.0.0...control-plane-ui-v1.1.0) (2026-03-25)


### Features

* **api,ui,gateway:** deployment verification — tags, route reload, test button ([#1938](https://github.com/stoa-platform/stoa/issues/1938)) ([3d81e83](https://github.com/stoa-platform/stoa/commit/3d81e8351e264196220d14b008c90887f65baf9d))
* **api,ui,portal:** MCP tool observability — gateway binding + usage stats (CAB-1821) ([#1766](https://github.com/stoa-platform/stoa/issues/1766)) ([f370331](https://github.com/stoa-platform/stoa/commit/f3703312dfdc485b1397b9f0911a74ade0ba5d28))
* **api,ui:** add AI Factory dashboard — Hegemon observability (CAB-1666) ([#1442](https://github.com/stoa-platform/stoa/issues/1442)) ([8afd9dc](https://github.com/stoa-platform/stoa/commit/8afd9dcc982e736cae8936b607c99715754a4592))
* **api,ui:** add error source attribution to monitoring transactions ([#1675](https://github.com/stoa-platform/stoa/issues/1675)) ([cc0e4c8](https://github.com/stoa-platform/stoa/commit/cc0e4c87122f93e94fd70d6edc5eae1ec639d2d0))
* **api,ui:** add mark deployed button for promoting promotions (CAB-1706) ([#1586](https://github.com/stoa-platform/stoa/issues/1586)) ([c2537dd](https://github.com/stoa-platform/stoa/commit/c2537dd17cf3f56f4b3179239c0c099ccc6046cf))
* **api,ui:** api deployment pipeline — define once, expose everywhere (CAB-1888) ([#1893](https://github.com/stoa-platform/stoa/issues/1893)) ([79e13da](https://github.com/stoa-platform/stoa/commit/79e13da4c4a7d22ca8972faa7b2ddc3d7a1a09a0))
* **api,ui:** applications multi-env display + FAPI key management (CAB-1748) ([#1566](https://github.com/stoa-platform/stoa/issues/1566)) ([70a1702](https://github.com/stoa-platform/stoa/commit/70a17024af8ea55bf77c4cd22b239aec59535ce7))
* **api,ui:** deployment observability — error enrichment + detail drawer ([#1931](https://github.com/stoa-platform/stoa/issues/1931)) ([2e0719b](https://github.com/stoa-platform/stoa/commit/2e0719bcdd810411e81a85fe3986d8ff54c67152))
* **api,ui:** environment scoping for Console — traces, policies, deployments (CAB-1664) ([#1439](https://github.com/stoa-platform/stoa/issues/1439)) ([c21f988](https://github.com/stoa-platform/stoa/commit/c21f988be608e62f45034e044bd96595db725e65))
* **api,ui:** environment scoping for gateway deployments (CAB-1664) ([#1554](https://github.com/stoa-platform/stoa/issues/1554)) ([fb91aee](https://github.com/stoa-platform/stoa/commit/fb91aee88cbecaf6abcbdb4d47027044b4b1706f))
* **api,ui:** environment-aware MCP servers with catalog feature flag (CAB-1791) ([#1689](https://github.com/stoa-platform/stoa/issues/1689)) ([efbcb96](https://github.com/stoa-platform/stoa/commit/efbcb965cf0cbae06de3372898a063d43576a756))
* **api,ui:** full environment scoping (CAB-1665) ([#1443](https://github.com/stoa-platform/stoa/issues/1443)) ([4dcf132](https://github.com/stoa-platform/stoa/commit/4dcf13241837327cd76d093fb0f4df1bb9335c4d))
* **api,ui:** persist signed certificates for lifecycle management ([#1907](https://github.com/stoa-platform/stoa/issues/1907)) ([bfb2b38](https://github.com/stoa-platform/stoa/commit/bfb2b3844a2d7a947578b964fd97b84d71e695ff))
* **api,ui:** surface cost/token metrics in AI Factory dashboard (CAB-1666) ([#1487](https://github.com/stoa-platform/stoa/issues/1487)) ([9d385a1](https://github.com/stoa-platform/stoa/commit/9d385a16f0b11f5fc6c62abb563dde4664cde02d))
* **api:** adopt ArgoCD entries on gateway registration (CAB-1771) ([#1658](https://github.com/stoa-platform/stoa/issues/1658)) ([af45581](https://github.com/stoa-platform/stoa/commit/af455812305ff3cf2a89e965d54582ac9864c908))
* **auth:** add Google social login identity provider (CAB-1873) ([#1867](https://github.com/stoa-platform/stoa/issues/1867)) ([e82a0e1](https://github.com/stoa-platform/stoa/commit/e82a0e11731020364d09c9c5983944f4db5090d6))
* **ci:** add linear ticket sync to session brief pipeline ([#1482](https://github.com/stoa-platform/stoa/issues/1482)) ([3e1fa8d](https://github.com/stoa-platform/stoa/commit/3e1fa8d7148b33fedbff153d03cbb805611b7e71))
* **ci:** Phase 2 — coverage gate, contract testing, mocked E2E (CAB-1696) ([#1498](https://github.com/stoa-platform/stoa/issues/1498)) ([833c184](https://github.com/stoa-platform/stoa/commit/833c184bd1a1c38dae2fe34fa9dd5076905b594c))
* **gateway,ui:** add consumer_id label to Prometheus metrics (CAB-1782) ([#1667](https://github.com/stoa-platform/stoa/issues/1667)) ([1cb43f5](https://github.com/stoa-platform/stoa/commit/1cb43f5bf4e8c5d2f5e7306cab9abc45b2661834))
* **gateway:** add gRPC protocol support with proto parser and MCP bridge (CAB-1755) ([#1757](https://github.com/stoa-platform/stoa/issues/1757)) ([c221fef](https://github.com/stoa-platform/stoa/commit/c221fefeb9a412b456ce63277d29166d63094e9c))
* **gateway:** API proxy config + credential injection (CAB-1723, CAB-1724) ([#1516](https://github.com/stoa-platform/stoa/issues/1516)) ([f8abfd1](https://github.com/stoa-platform/stoa/commit/f8abfd11970b61db3fec6c342b203d204ebdbdaa))
* **gateway:** wire PingoraPool into proxy path (CAB-1849) ([#1905](https://github.com/stoa-platform/stoa/issues/1905)) ([ba39741](https://github.com/stoa-platform/stoa/commit/ba397419b0eae445ccf29b7c0b8d0f0f2d4733e8))
* **helm:** resource lifecycle label taxonomy + Kyverno enforcement (CAB-1877) ([#1864](https://github.com/stoa-platform/stoa/issues/1864)) ([49c186f](https://github.com/stoa-platform/stoa/commit/49c186f9765aef2ba389fe3a99ea77ef1f5610a4))
* **portal:** inline app creation + quota bars (CAB-1907) ([#1962](https://github.com/stoa-platform/stoa/issues/1962)) ([edd0b31](https://github.com/stoa-platform/stoa/commit/edd0b31af4e7c0826a86f720b8a55e0c77ed58f2))
* **ui:** add Call Flow dashboard page + sidebar menu (CAB-1842) ([#1802](https://github.com/stoa-platform/stoa/issues/1802)) ([9abcd08](https://github.com/stoa-platform/stoa/commit/9abcd080a68748571ba3f2bc7b26a20f496c20a6))
* **ui:** add call-flow nav + observability recharts (CAB-1885) ([#1887](https://github.com/stoa-platform/stoa/issues/1887)) ([34b79a8](https://github.com/stoa-platform/stoa/commit/34b79a86bd63d1883453d8ef9eeea0bfee984ba8))
* **ui:** add certificate generation wizard with WebCrypto + PKCS12 (CAB-1788) ([#1682](https://github.com/stoa-platform/stoa/issues/1682)) ([4784cf3](https://github.com/stoa-platform/stoa/commit/4784cf3b4ff1e2282db8c1032c0111779d06c1c9))
* **ui:** add certificate management page (CAB-1786) ([#1680](https://github.com/stoa-platform/stoa/issues/1680)) ([986a757](https://github.com/stoa-platform/stoa/commit/986a75784af9537e0129aed0161421c8567d5c7b))
* **ui:** add connect mode to gateway dashboard + list (CAB-1819) ([#1742](https://github.com/stoa-platform/stoa/issues/1742)) ([1d46b39](https://github.com/stoa-platform/stoa/commit/1d46b3931b87e92ad59a44d37cfc7e2bd9507aee))
* **ui:** add contextual sub-navigation for hidden pages (CAB-1785) ([#1678](https://github.com/stoa-platform/stoa/issues/1678)) ([6f2f8d1](https://github.com/stoa-platform/stoa/commit/6f2f8d1ee3caef9ae9c2c22b809bc7ce52c65acc))
* **ui:** add Internal APIs page (CAB-1727) ([#1522](https://github.com/stoa-platform/stoa/issues/1522)) ([ea5916d](https://github.com/stoa-platform/stoa/commit/ea5916dc408ff0281cc80e8c7057e285711a7596))
* **ui:** add OAuth setup dialog for MCP connectors (CAB-1790) ([#1704](https://github.com/stoa-platform/stoa/issues/1704)) ([83f4b0c](https://github.com/stoa-platform/stoa/commit/83f4b0cceb0215ef8224e7a3f1705955a6bf9b7a))
* **ui:** add span waterfall timeline to transaction detail (CAB-1790) ([#1690](https://github.com/stoa-platform/stoa/issues/1690)) ([1b25c0f](https://github.com/stoa-platform/stoa/commit/1b25c0f6bf81a137fb55cc32f1400d50b0648d2c))
* **ui:** add trace detail drill-down view for call flow (CAB-1869) ([#1848](https://github.com/stoa-platform/stoa/issues/1848)) ([5921137](https://github.com/stoa-platform/stoa/commit/59211374bfd379420d0e7f1fa94df8691a4bdb4f))
* **ui:** API detail page with lifecycle management (CAB-1813) ([#1736](https://github.com/stoa-platform/stoa/issues/1736)) ([843ef2e](https://github.com/stoa-platform/stoa/commit/843ef2e95361ddbbaa7ef2685ef0143066c70255))
* **ui:** API Traffic dashboard + Grafana provisioning (CAB-1730) ([#1529](https://github.com/stoa-platform/stoa/issues/1529)) ([9cfd8d5](https://github.com/stoa-platform/stoa/commit/9cfd8d503bad2c882e98ec4617a2743bf751e04c))
* **ui:** call flow dashboard v2 with recharts + live traces (CAB-1869) ([#1847](https://github.com/stoa-platform/stoa/issues/1847)) ([b5a52bd](https://github.com/stoa-platform/stoa/commit/b5a52bd8df66c0ba26af44b45d1fecd9ac6e649b))
* **ui:** chat usage dashboard — per-app token breakdown + daily budget (CAB-1868) ([#1822](https://github.com/stoa-platform/stoa/issues/1822)) ([e691f8d](https://github.com/stoa-platform/stoa/commit/e691f8d721bd9e75884a9cf1df237d7642c4fdc8))
* **ui:** Console chat settings UI + X-Chat-Source header (CAB-1852) ([#1807](https://github.com/stoa-platform/stoa/issues/1807)) ([a0b8a88](https://github.com/stoa-platform/stoa/commit/a0b8a889a45caad9495cc1925e89a0fc13dd6d00))
* **ui:** consolidate observability dashboard with MCP, arena, and CUJ metrics ([#1659](https://github.com/stoa-platform/stoa/issues/1659)) ([63741e8](https://github.com/stoa-platform/stoa/commit/63741e850ca726b7f027c96d5d629528bf39a56d))
* **ui:** enable MCP Catalog tab by default ([#1701](https://github.com/stoa-platform/stoa/issues/1701)) ([986b68d](https://github.com/stoa-platform/stoa/commit/986b68d4f4c76edea11d8ec4fbc3b14c9705f508))
* **ui:** environment registry integration in Console + Portal (CAB-1661, CAB-1662) ([#1432](https://github.com/stoa-platform/stoa/issues/1432)) ([afca552](https://github.com/stoa-platform/stoa/commit/afca55248168ea90ee4b34a2b0557a928682b759))
* **ui:** extract FloatingChat + useChatService to shared/ (CAB-1836) ([#1788](https://github.com/stoa-platform/stoa/issues/1788)) ([db7c3e0](https://github.com/stoa-platform/stoa/commit/db7c3e02367974a7e64d34996b1ae6d2bca3d3bf))
* **ui:** gateway overview panel + read-only guards (CAB-1705) ([#1510](https://github.com/stoa-platform/stoa/issues/1510)) ([210ea6c](https://github.com/stoa-platform/stoa/commit/210ea6c0551c741c9b06ee409026c693d0cbf39b))
* **ui:** gateway soft-delete UI (CAB-1749) ([#1569](https://github.com/stoa-platform/stoa/issues/1569)) ([f91eb0d](https://github.com/stoa-platform/stoa/commit/f91eb0da9ed52bbb3ce5febb271b8fe19f6018d6))
* **ui:** GitOps source badges and ArgoCD sync info in gateway list (CAB-1771) ([#1656](https://github.com/stoa-platform/stoa/issues/1656)) ([a6d593c](https://github.com/stoa-platform/stoa/commit/a6d593c02726287ea5700b32e0125748a4b76da3))
* **ui:** multi-env promote + badges for connectors (CAB-1812) ([#1734](https://github.com/stoa-platform/stoa/issues/1734)) ([b338bc6](https://github.com/stoa-platform/stoa/commit/b338bc6317a1398c53b36ec379461c7bfa8322bc))
* **ui:** multi-environment UX harmonization (CAB-1705) ([#1507](https://github.com/stoa-platform/stoa/issues/1507)) ([63eefdf](https://github.com/stoa-platform/stoa/commit/63eefdf837b1a848a2a7365000bb6cf962686cf1))
* **ui:** progressive streaming + tool rendering in FloatingChat (CAB-1816) ([#1738](https://github.com/stoa-platform/stoa/issues/1738)) ([2463e63](https://github.com/stoa-platform/stoa/commit/2463e636770aafe10dc8d76898c6c58978272a95))
* **ui:** promotion dialog + history + pipeline indicator (CAB-1706 W4) ([#1577](https://github.com/stoa-platform/stoa/issues/1577)) ([8e292c8](https://github.com/stoa-platform/stoa/commit/8e292c82255abe632b5ddad02ae5ccd6c190dc0a))
* **ui:** rationalize Console + Portal navigation (CAB-1764) ([#1869](https://github.com/stoa-platform/stoa/issues/1869)) ([89ce5a7](https://github.com/stoa-platform/stoa/commit/89ce5a769ead1985264189511d40bf04263810ba))
* **ui:** rationalize Portal + Console navigation for demo (CAB-1764) ([#1601](https://github.com/stoa-platform/stoa/issues/1601)) ([c7b54f5](https://github.com/stoa-platform/stoa/commit/c7b54f5c162ee56ea3afa0f0ded02d30cb59c32a))
* **ui:** replace fake Operations panels with Grafana embeds (CAB-1766) ([#1632](https://github.com/stoa-platform/stoa/issues/1632)) ([31488db](https://github.com/stoa-platform/stoa/commit/31488db9dfde6ab5373102edbfb1428ce81fdfa3))
* **ui:** show demo mode warning in transaction detail panel ([#1679](https://github.com/stoa-platform/stoa/issues/1679)) ([9aa09eb](https://github.com/stoa-platform/stoa/commit/9aa09eb1eb01b0b77647f43f3b552bce5b5a26f8))
* **ui:** unify API pages into tabbed view (CAB-1727) ([#1525](https://github.com/stoa-platform/stoa/issues/1525)) ([3c6c978](https://github.com/stoa-platform/stoa/commit/3c6c978a9a7285eeaefccfc7a5be7a97dd0260f2))


### Bug Fixes

* **api,ui:** 2-eyes for staging, 4-eyes for production only (CAB-1706) ([#1581](https://github.com/stoa-platform/stoa/issues/1581)) ([9053a1e](https://github.com/stoa-platform/stoa/commit/9053a1e8ca5727a1a48c50a786544c69b0572599))
* **api,ui:** add demo_mode flag, surface errors, fix tenant storage (CAB-1774) ([#1648](https://github.com/stoa-platform/stoa/issues/1648)) ([e703e1d](https://github.com/stoa-platform/stoa/commit/e703e1df5cdab0f27459acfd4e9d4c3a2c93c7f7))
* **api,ui:** align contracts router with tenant-scoped URL pattern ([#1899](https://github.com/stoa-platform/stoa/issues/1899)) ([a8afb25](https://github.com/stoa-platform/stoa/commit/a8afb250bde1262c99ac8b7d4aad83721cc35fca))
* **api,ui:** align metrics contract and fix polling bug (CAB-1774) ([#1646](https://github.com/stoa-platform/stoa/issues/1646)) ([bad5bd0](https://github.com/stoa-platform/stoa/commit/bad5bd0244eb0aef9615d73bfbbba14ac8dc319c))
* **api,ui:** fix AI Factory dashboard data quality (CAB-1666) ([#1457](https://github.com/stoa-platform/stoa/issues/1457)) ([f4864b8](https://github.com/stoa-platform/stoa/commit/f4864b8f613c80a1a1d384c385fda72e05c94ad4))
* **api,ui:** Keycloak password grant + stabilize flaky tests ([#1447](https://github.com/stoa-platform/stoa/issues/1447)) ([ee65c09](https://github.com/stoa-platform/stoa/commit/ee65c09518fe2382debdf7efc48061a796adb5a3))
* **api,ui:** return 503 when GitLab not configured + Button loading state (CAB-1790) ([#1705](https://github.com/stoa-platform/stoa/issues/1705)) ([72fa545](https://github.com/stoa-platform/stoa/commit/72fa5457e23dc9e845f0c10890352a8f05414a8f))
* **api,ui:** test button shows amber for 4xx, green only for 2xx ([#1945](https://github.com/stoa-platform/stoa/issues/1945)) ([8baf152](https://github.com/stoa-platform/stoa/commit/8baf15279b4ff52bfa0cde36408232b4650c8f2d))
* **api,ui:** use API name for GitLab deployment lookup (CAB-1803) ([#1731](https://github.com/stoa-platform/stoa/issues/1731)) ([201c3d9](https://github.com/stoa-platform/stoa/commit/201c3d972d4d9845a56a01805f77f2bd5802aa61))
* **api:** enrich chat assistant with accurate platform knowledge ([#1846](https://github.com/stoa-platform/stoa/issues/1846)) ([c171c6b](https://github.com/stoa-platform/stoa/commit/c171c6b900035bad82d9e61206d332312ef65a25))
* **api:** support KEYCLOAK_ADMIN_PASSWORD env var fallback ([#1444](https://github.com/stoa-platform/stoa/issues/1444)) ([add2c97](https://github.com/stoa-platform/stoa/commit/add2c974313f43130daef0c3424388af69989ee5))
* **api:** use full revision slug in migration 057 ([#1488](https://github.com/stoa-platform/stoa/issues/1488)) ([81ecce3](https://github.com/stoa-platform/stoa/commit/81ecce36dbe380f7164e638cb9558b1630b4620d))
* **auth:** add production redirect URIs to opensearch-dashboards OIDC client ([#1684](https://github.com/stoa-platform/stoa/issues/1684)) ([5f59fee](https://github.com/stoa-platform/stoa/commit/5f59fee8b6512dc7808d34d336ca7b3f1f5056dd))
* **ci:** add CACHEBUST ARG to prevent stale Vite builds from GHA Docker cache ([#1664](https://github.com/stoa-platform/stoa/issues/1664)) ([e6d64d4](https://github.com/stoa-platform/stoa/commit/e6d64d471b2b62da4d8bb54dbd662e3bf6091a6a))
* **ci:** break L3 dispatch loop — dedup + merged PR check ([#1512](https://github.com/stoa-platform/stoa/issues/1512)) ([a206d5d](https://github.com/stoa-platform/stoa/commit/a206d5da96a1b08e93deedccfbe154124fd7c114))
* **ci:** decouple Docker build/deploy from CI on main push ([#1511](https://github.com/stoa-platform/stoa/issues/1511)) ([57cedad](https://github.com/stoa-platform/stoa/commit/57cedadb51bcb21feba21fe04fd1906acbcbbe6d))
* **ci:** fix Arena L0/L2 failures and add serverless GHA benchmark ([#1950](https://github.com/stoa-platform/stoa/issues/1950)) ([0cc0548](https://github.com/stoa-platform/stoa/commit/0cc0548c24521979236471acb6cd189c8ca4c479))
* **ci:** gate docker/deploy jobs on CI success ([#1629](https://github.com/stoa-platform/stoa/issues/1629)) ([3f579ff](https://github.com/stoa-platform/stoa/commit/3f579ff633f7ae872e586b493c57da6d227a46a8))
* **ci:** increase Dashboard test timeout for CI runners ([#1933](https://github.com/stoa-platform/stoa/issues/1933)) ([2a3d307](https://github.com/stoa-platform/stoa/commit/2a3d307573df2c674638fe6fa4faa78241d607a1))
* **ci:** report actual CI result in reusable workflows ([#1623](https://github.com/stoa-platform/stoa/issues/1623)) ([d65897e](https://github.com/stoa-platform/stoa/commit/d65897e036e8533ccebdb5716d9a09054208b385))
* **docs:** replace npm start with npm run dev in UI documentation ([#1624](https://github.com/stoa-platform/stoa/issues/1624)) ([79e694d](https://github.com/stoa-platform/stoa/commit/79e694d0426107f740f54988de57ef75f69d20d3))
* **gateway:** stabilize flaky timestamp test ([#1790](https://github.com/stoa-platform/stoa/issues/1790)) ([ed2c68c](https://github.com/stoa-platform/stoa/commit/ed2c68ce4e20db1dfcc247d689e178253210f78f))
* **security:** persist opensearch security config + dashboard in git (CAB-1866) ([#1863](https://github.com/stoa-platform/stoa/issues/1863)) ([78ad9de](https://github.com/stoa-platform/stoa/commit/78ad9de2b19b144a28dacbdd087e7211298bb8aa))
* **security:** resolve 31 CodeQL and Trivy scan alerts ([#1565](https://github.com/stoa-platform/stoa/issues/1565)) ([fee5e7b](https://github.com/stoa-platform/stoa/commit/fee5e7b7fb0c550de18ad7f995ab392633fcd46c))
* **security:** resolve all GitHub security scan alerts ([#1555](https://github.com/stoa-platform/stoa/issues/1555)) ([190c44e](https://github.com/stoa-platform/stoa/commit/190c44e21d6f5737013540d86cb8c3c36008dd4c))
* **ui,api:** add gateway_type filter to drift detection (CAB-1887) ([#1892](https://github.com/stoa-platform/stoa/issues/1892)) ([63d15e7](https://github.com/stoa-platform/stoa/commit/63d15e7a8720f7aee2c3d80513c2548ff5f6deff))
* **ui,gateway:** fix Call Flow queries + async span instrument (CAB-1866) ([#1844](https://github.com/stoa-platform/stoa/issues/1844)) ([6568f41](https://github.com/stoa-platform/stoa/commit/6568f41c1931710e63714e0c0d6bc5448f8233f4))
* **ui,portal:** resolve React version conflict from shared/ peer deps ([#1477](https://github.com/stoa-platform/stoa/issues/1477)) ([32d3f58](https://github.com/stoa-platform/stoa/commit/32d3f58d480668a805721f9d6b2c1d21382fd662))
* **ui:** add Chat Settings to sidebar navigation ([#1821](https://github.com/stoa-platform/stoa/issues/1821)) ([0e18580](https://github.com/stoa-platform/stoa/commit/0e185809401ee0cddefc6d85b16c5d1a67941406))
* **ui:** add markdown rendering and conversation history to FloatingChat ([#1753](https://github.com/stoa-platform/stoa/issues/1753)) ([b5dbc90](https://github.com/stoa-platform/stoa/commit/b5dbc90ec7a2c3495953e151f192392f0fcbb3fc))
* **ui:** add multi-env promote to unified MCP servers page (CAB-1812) ([#1754](https://github.com/stoa-platform/stoa/issues/1754)) ([609e486](https://github.com/stoa-platform/stoa/commit/609e486410c135e0eb64d9435a21551d214df407))
* **ui:** align drift detection env filter with registry/overview (CAB-1887) ([#1894](https://github.com/stoa-platform/stoa/issues/1894)) ([7d8cf68](https://github.com/stoa-platform/stoa/commit/7d8cf68aa3433340f332d5dbfbfa975111d94ea3))
* **ui:** auto-generate tenant CA before signing certificate ([#1900](https://github.com/stoa-platform/stoa/issues/1900)) ([cda5501](https://github.com/stoa-platform/stoa/commit/cda5501ca1e0678f6632f7c8950342eba767f53c))
* **ui:** auto-redirect to login when KC session expires ([#1706](https://github.com/stoa-platform/stoa/issues/1706)) ([6869885](https://github.com/stoa-platform/stoa/commit/6869885243d5a1d5fa3e4ddb2491e3df2ceb3dff))
* **ui:** correct gateway instances API endpoint path ([#1533](https://github.com/stoa-platform/stoa/issues/1533)) ([1169783](https://github.com/stoa-platform/stoa/commit/11697832a8df442811e63571e479e7fbf5c674e8))
* **ui:** deploy dialog sends API name instead of Git UUID (CAB-1888) ([#1904](https://github.com/stoa-platform/stoa/issues/1904)) ([c653084](https://github.com/stoa-platform/stoa/commit/c653084d190714494885936f4f628e6b9b111272))
* **ui:** fix PromQL queries and add API backend metrics to Operations dashboard ([#1649](https://github.com/stoa-platform/stoa/issues/1649)) ([c085289](https://github.com/stoa-platform/stoa/commit/c0852896167a210204f0593dcba717d133888615))
* **ui:** Gateway Dashboard Inconsistencies — remove mock data, unify status (CAB-1887) ([#1889](https://github.com/stoa-platform/stoa/issues/1889)) ([4246a21](https://github.com/stoa-platform/stoa/commit/4246a2175a57850958fbe17cf1f607389a1c3a7d))
* **ui:** Gateway Overview multi-gateway aggregated view (CAB-1887) ([#1891](https://github.com/stoa-platform/stoa/issues/1891)) ([b3ae42a](https://github.com/stoa-platform/stoa/commit/b3ae42ae9870941853885968d98d55549fa60f50))
* **ui:** global status banner for drift detection clarity (CAB-1887) ([#1897](https://github.com/stoa-platform/stoa/issues/1897)) ([523a693](https://github.com/stoa-platform/stoa/commit/523a69383b1f992e14cc9123e8cf5fa6bd03c800))
* **ui:** grafana iframe JWT auth_token embedding (CAB-1773) ([#1645](https://github.com/stoa-platform/stoa/issues/1645)) ([ea9ff2b](https://github.com/stoa-platform/stoa/commit/ea9ff2b9571bb43d950aaeb288e35e85a0ac7883))
* **ui:** handle Grafana redirect in service health check ([#1637](https://github.com/stoa-platform/stoa/issues/1637)) ([09b604c](https://github.com/stoa-platform/stoa/commit/09b604cab830046589368b10a25ed54ef968557e))
* **ui:** hide empty state when issued certificates exist ([#1912](https://github.com/stoa-platform/stoa/issues/1912)) ([a0a19a8](https://github.com/stoa-platform/stoa/commit/a0a19a82c409069010e9d9568cffefc4ecd8dcb6))
* **ui:** lower coverage thresholds after recharts migration ([#1888](https://github.com/stoa-platform/stoa/issues/1888)) ([58491a5](https://github.com/stoa-platform/stoa/commit/58491a53095af63131c81b11ce4af9cda45d40b0))
* **ui:** prevent OIDC interception of MCP connector OAuth callback (CAB-1790) ([#1720](https://github.com/stoa-platform/stoa/issues/1720)) ([ec5d957](https://github.com/stoa-platform/stoa/commit/ec5d957f6a98622c599364480b3952e1529da5a4))
* **ui:** redesign Gateway Registry with environment tabs ([#1495](https://github.com/stoa-platform/stoa/issues/1495)) ([f2d610c](https://github.com/stoa-platform/stoa/commit/f2d610ca373a3c0342db89f295cc1d315435c03a))
* **ui:** remove .env.local from Docker build context ([#1639](https://github.com/stoa-platform/stoa/issues/1639)) ([714d8c9](https://github.com/stoa-platform/stoa/commit/714d8c955644e7d98e396d788e4dd254c4c399f0))
* **ui:** remove env guards from cross-env pages (CAB-1731) ([#1518](https://github.com/stoa-platform/stoa/issues/1518)) ([16c2dba](https://github.com/stoa-platform/stoa/commit/16c2dba9fedb360f01051f8c134f9c863c307aba))
* **ui:** remove fake data and ghost endpoints from dashboards (CAB-1774) ([#1647](https://github.com/stoa-platform/stoa/issues/1647)) ([5e39b95](https://github.com/stoa-platform/stoa/commit/5e39b950946b32255bd8227afe68eb9b3af9d12a))
* **ui:** rename Sidecar to STOA Link across Console ([#1654](https://github.com/stoa-platform/stoa/issues/1654)) ([65e7a25](https://github.com/stoa-platform/stoa/commit/65e7a25fd8f35676b94cf1b0cafcb4440fd1b7c4))
* **ui:** repair 8 broken tests blocking Console CI ([#1896](https://github.com/stoa-platform/stoa/issues/1896)) ([d299acb](https://github.com/stoa-platform/stoa/commit/d299acb9a85290fb7e9ab2bf3826dd80d3996885))
* **ui:** repair Layout + GatewayList tests blocking Console CI (CAB-1884) ([#1886](https://github.com/stoa-platform/stoa/issues/1886)) ([665b254](https://github.com/stoa-platform/stoa/commit/665b254a8f6ff91574afb2a54d851522077f277a))
* **ui:** resolve stoa-gateway text ambiguity in OperationsDashboard test ([#1634](https://github.com/stoa-platform/stoa/issues/1634)) ([4884664](https://github.com/stoa-platform/stoa/commit/4884664104d1a1751dc3bcd33f5798d83c186b04))
* **ui:** resolve TypeScript errors in GatewayList health_details ([#1661](https://github.com/stoa-platform/stoa/issues/1661)) ([247f9cd](https://github.com/stoa-platform/stoa/commit/247f9cd641935205035154d82d6a1af793755e60))
* **ui:** revert Grafana URL to /grafana proxy path ([#1535](https://github.com/stoa-platform/stoa/issues/1535)) ([7d7277b](https://github.com/stoa-platform/stoa/commit/7d7277b55c639d0ab9ae51cac78aaa4269ec8394))
* **ui:** stabilize flaky ProxyOwner test on CI runner ([#1446](https://github.com/stoa-platform/stoa/issues/1446)) ([77e3273](https://github.com/stoa-platform/stoa/commit/77e327339a7dfea747813838356c9e77e497cf92))
* **ui:** trigger catalog sync after portal toggle and deploy (CAB-1813) ([#1747](https://github.com/stoa-platform/stoa/issues/1747)) ([d44c81d](https://github.com/stoa-platform/stoa/commit/d44c81dde42d3fbe9a54a6352a8525dfd4eaf19d))
* **ui:** use API name instead of UUID for detail page navigation (CAB-1813) ([#1737](https://github.com/stoa-platform/stoa/issues/1737)) ([96e243b](https://github.com/stoa-platform/stoa/commit/96e243bc3622aeed25c58cc0cf1dd7445fc27f51))
* **ui:** use BASE_DOMAIN for Grafana URL instead of relative path ([#1534](https://github.com/stoa-platform/stoa/issues/1534)) ([d6b5e8d](https://github.com/stoa-platform/stoa/commit/d6b5e8d8d501eca624fbd32e56e871505db4e814))
* **ui:** use username for promotion 4-eyes check (CAB-1706) ([#1580](https://github.com/stoa-platform/stoa/issues/1580)) ([319b683](https://github.com/stoa-platform/stoa/commit/319b68341a410e92475795c14e50115ce6f6e13a))
* **ui:** wire call flow to authenticated monitoring API + fix heatmap (CAB-1869) ([#1850](https://github.com/stoa-platform/stoa/issues/1850)) ([db73d39](https://github.com/stoa-platform/stoa/commit/db73d39989ea5c41ed8935b59873971cedc277ef))
