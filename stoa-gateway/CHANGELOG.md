# Changelog

## [0.9.12](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.11...stoa-gateway-v0.9.12) (2026-04-24)


### Bug Fixes

* **gateway:** GW-1 P1 — admin input validation + OAuth2 URL parsing ([#2504](https://github.com/stoa-platform/stoa/issues/2504)) ([8401481](https://github.com/stoa-platform/stoa/commit/8401481e24ab5fbc76a64cf5f0845769c5591d79))
* **gateway:** GW-1 P1 — tactical admin audit log middleware ([#2506](https://github.com/stoa-platform/stoa/issues/2506)) ([5442a44](https://github.com/stoa-platform/stoa/commit/5442a443b904e64c6a6d38ac346c5846a043b313))

## [0.9.11](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.10...stoa-gateway-v0.9.11) (2026-04-24)


### Bug Fixes

* **gateway:** GW-1 P0 batch — constant-time admin auth + route orphan + reload leak + admin rate-limit ([#2501](https://github.com/stoa-platform/stoa/issues/2501)) ([0efc78f](https://github.com/stoa-platform/stoa/commit/0efc78f4a48753e3a38e63d9af935c7bb7493b3e))
* **gateway:** GW-1 P1 — contract consistency (bind-first upsert / unbind-first delete) ([#2502](https://github.com/stoa-platform/stoa/issues/2502)) ([23d9f72](https://github.com/stoa-platform/stoa/commit/23d9f72a707ccb84d330099d6407c4c9d598fc84))

## [0.9.10](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.9...stoa-gateway-v0.9.10) (2026-04-20)


### Bug Fixes

* **gateway:** require JWT on /mcp/* protected routes (CAB-2121) ([#2433](https://github.com/stoa-platform/stoa/issues/2433)) ([360eb1b](https://github.com/stoa-platform/stoa/commit/360eb1b9f494af8fd27d41e52a49a25083d8b783))

## [0.9.9](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.8...stoa-gateway-v0.9.9) (2026-04-19)


### Features

* **gateway:** consume /apis/expanded + path-param substitution (CAB-2113) ([#2420](https://github.com/stoa-platform/stoa/issues/2420)) ([3e57435](https://github.com/stoa-platform/stoa/commit/3e57435dff98c6d75f0c3789a54c8242c90f2ac4))
* **gateway:** tool-expansion observability + runbook (CAB-2113 PR3) ([#2422](https://github.com/stoa-platform/stoa/issues/2422)) ([cd99417](https://github.com/stoa-platform/stoa/commit/cd9941741c234f3b6fd0b6bde4afad480615aa27))


### Bug Fixes

* **gateway:** public per-op tools now surface in standard discovery (CAB-2123) ([#2426](https://github.com/stoa-platform/stoa/issues/2426)) ([3a0614b](https://github.com/stoa-platform/stoa/commit/3a0614bcadb86b032eb487d03be7f57512db1c34))
* **mcp:** restore temperature=0 + add tool-name bijection in phase05 bench (CAB-2116) ([#2428](https://github.com/stoa-platform/stoa/issues/2428)) ([0d6eccc](https://github.com/stoa-platform/stoa/commit/0d6eccc75830b29edccc79a963842982ec643b24))

## [0.9.8](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.7...stoa-gateway-v0.9.8) (2026-04-18)


### Bug Fixes

* **gateway:** drop non-dict experimental.transports from InitializeResult (CAB-2112) ([#2414](https://github.com/stoa-platform/stoa/issues/2414)) ([3570f39](https://github.com/stoa-platform/stoa/commit/3570f39193c85ae803c2fc72f3234093e061a1eb))

## [0.9.7](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.6...stoa-gateway-v0.9.7) (2026-04-17)


### Bug Fixes

* **gateway:** unblock /mcp/sse capability-negotiation discovery methods (CAB-2109) ([#2411](https://github.com/stoa-platform/stoa/issues/2411)) ([fb082f8](https://github.com/stoa-platform/stoa/commit/fb082f8cfac6c5eb5bcf6b48249653653c7beebe))

## [0.9.6](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.5...stoa-gateway-v0.9.6) (2026-04-17)


### Bug Fixes

* **gateway:** honor Accept: text/event-stream on /mcp/sse (CAB-2106) ([#2402](https://github.com/stoa-platform/stoa/issues/2402)) ([bd28686](https://github.com/stoa-platform/stoa/commit/bd2868675d744e9aa34969630a110690e5fbbe40))

## [0.9.5](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.4...stoa-gateway-v0.9.5) (2026-04-16)


### Bug Fixes

* **ci:** restore Gateway CI + Performance Gate on main ([#2388](https://github.com/stoa-platform/stoa/issues/2388)) ([fd0d1ff](https://github.com/stoa-platform/stoa/commit/fd0d1ff38e05f7137d9585b880942652fe949b75))

## [0.9.4](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.3...stoa-gateway-v0.9.4) (2026-04-15)


### Bug Fixes

* **gateway:** correct insta redaction path for mcp-capabilities ([#2322](https://github.com/stoa-platform/stoa/issues/2322)) ([96b1202](https://github.com/stoa-platform/stoa/commit/96b1202b35b6c5b575faa0a2cfaed51ee02efc7e))

## [0.9.3](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.2...stoa-gateway-v0.9.3) (2026-04-11)


### Features

* **gateway:** add tracing spans for JWKS fetch and token proxy ([#2288](https://github.com/stoa-platform/stoa/issues/2288)) ([bba9d74](https://github.com/stoa-platform/stoa/commit/bba9d74cce8029ff149974abe41c9fe1c9b17947))

## [0.9.2](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.1...stoa-gateway-v0.9.2) (2026-04-09)


### Features

* add target_gateway_url to gateway detail panel ([#2069](https://github.com/stoa-platform/stoa/issues/2069)) ([c07557f](https://github.com/stoa-platform/stoa/commit/c07557feb537c2f029909763e62cf719eacb18db))
* **api,ui,gateway:** traffic seed link/connect + Call Flow interactive filters (CAB-1997) ([#2228](https://github.com/stoa-platform/stoa/issues/2228)) ([627dcbe](https://github.com/stoa-platform/stoa/commit/627dcbe03ec0c0259ce56bbe9e40dac5f3890c53))
* **api:** gateway enabled flag + visibility + soft disable (CAB-1979) ([#2201](https://github.com/stoa-platform/stoa/issues/2201)) ([0136dd7](https://github.com/stoa-platform/stoa/commit/0136dd749acfb8b4d0e64be3a5a3388c4f6b17b8))
* **api:** OpenSearch traces router + gateway OTel spans (CAB-1997) ([#2221](https://github.com/stoa-platform/stoa/issues/2221)) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **api:** OpenSearch-first monitoring with native Prometheus metrics (CAB-1997) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **gateway,api,ui:** MCP Streamable HTTP endpoint + platform tool auto-sync ([#2245](https://github.com/stoa-platform/stoa/issues/2245)) ([fd7b408](https://github.com/stoa-platform/stoa/commit/fd7b4087ee21bfb83aa9fdc1e8d1cad1bb28abdf))
* **gateway,ui:** wire gateway metrics on all request types (CAB-1997) ([#2229](https://github.com/stoa-platform/stoa/issues/2229)) ([946a819](https://github.com/stoa-platform/stoa/commit/946a8191cb2b453184a2eb596634fe099e4172df))
* **gateway:** add github_* config fields alongside gitlab_* (CAB-1891) ([#2042](https://github.com/stoa-platform/stoa/issues/2042)) ([de4e88f](https://github.com/stoa-platform/stoa/commit/de4e88f63a6dd4ea8fe57194b7bca708f2808620))
* **gateway:** add STC compression plugin + SDK body extension (CAB-1936) ([#2108](https://github.com/stoa-platform/stoa/issues/2108)) ([68d685a](https://github.com/stoa-platform/stoa/commit/68d685abe146dc424a8d9ae17e9e282459cb9c79))
* **gateway:** dispatch shadow mode git client by git_provider config (CAB-1891) ([#2050](https://github.com/stoa-platform/stoa/issues/2050)) ([ce48b3f](https://github.com/stoa-platform/stoa/commit/ce48b3f2d5dbcbda9121c38f7d55e6621262aa95))
* **gateway:** full OTel span coverage + status codes + client IP (CAB-1997) ([#2219](https://github.com/stoa-platform/stoa/issues/2219)) ([2efbe42](https://github.com/stoa-platform/stoa/commit/2efbe42fa312852963114f82414971b5befcd886))
* **gateway:** GitHubClient + GitProvider dispatch (CAB-1891) ([#2045](https://github.com/stoa-platform/stoa/issues/2045)) ([dc9ccfb](https://github.com/stoa-platform/stoa/commit/dc9ccfbbbc27f391dbb4abb535605c816174e25a))
* **gateway:** report git_provider in health endpoint (CAB-1891) ([#2053](https://github.com/stoa-platform/stoa/issues/2053)) ([4e2c825](https://github.com/stoa-platform/stoa/commit/4e2c825c39ce6269d6e4870c7032938b744af6cf))


### Bug Fixes

* **api,gateway,go:** normalize health check payloads (CAB-1916) ([#2008](https://github.com/stoa-platform/stoa/issues/2008)) ([0366d18](https://github.com/stoa-platform/stoa/commit/0366d18066aad1610cab0cacc15e554d26ebe0de))
* **api,gateway,ui:** sequential span waterfall display (CAB-1997) ([#2223](https://github.com/stoa-platform/stoa/issues/2223)) ([68c7012](https://github.com/stoa-platform/stoa/commit/68c70125784bcd8820fdfe85af22d217eeee177b))
* **api:** bridge git_provider DI with legacy test patches ([#2076](https://github.com/stoa-platform/stoa/issues/2076)) ([a6b2a10](https://github.com/stoa-platform/stoa/commit/a6b2a1062d75644aa8b02644ab7e98a39c7982d2))
* **gateway,api:** scope API discovery by gateway mode + gateway_id filter (CAB-1940) ([#2121](https://github.com/stoa-platform/stoa/issues/2121)) ([a01b245](https://github.com/stoa-platform/stoa/commit/a01b245e69f8dc5f2574762098e8d9ed361df930))
* **gateway,ui:** broaden discovery gate + discovery banner in GatewayDetail (CAB-1949) ([#2134](https://github.com/stoa-platform/stoa/issues/2134)) ([c2c4f42](https://github.com/stoa-platform/stoa/commit/c2c4f4284109e14dd1c48e4f8a2b8786fbed5d61))
* **gateway:** add admin input validation + SSRF pre-check (CAB-1920) ([#2013](https://github.com/stoa-platform/stoa/issues/2013)) ([6e05b46](https://github.com/stoa-platform/stoa/commit/6e05b469c0e643fdffd264a5aad9bd92d9618513))
* **gateway:** add registration retry with exponential backoff (CAB-1915) ([#2005](https://github.com/stoa-platform/stoa/issues/2005)) ([2d52644](https://github.com/stoa-platform/stoa/commit/2d526441e330b518b7e6c0e835680b8ab425a366))
* **gateway:** explicit OTLP batch config for Tempo (CAB-1974) ([#2193](https://github.com/stoa-platform/stoa/issues/2193)) ([80d09cd](https://github.com/stoa-platform/stoa/commit/80d09cdf0a96b5f882ae35f0859c85e58f586368))
* **gateway:** fix trace_id in access logs + remove eprintln diagnostics (CAB-1866) ([#2024](https://github.com/stoa-platform/stoa/issues/2024)) ([770a042](https://github.com/stoa-platform/stoa/commit/770a04287026624da8430007dbea62d4a5022f2c))
* **gateway:** pass gateway_id in API catalog sync + fallback (CAB-1940) ([#2122](https://github.com/stoa-platform/stoa/issues/2122)) ([8163187](https://github.com/stoa-platform/stoa/commit/8163187b941644a730fceb276d176a5bf52790fe))
* **gateway:** re-register on heartbeat 404 after CP auto-purge ([#2103](https://github.com/stoa-platform/stoa/issues/2103)) ([12fac24](https://github.com/stoa-platform/stoa/commit/12fac2494c620cdfbbc9f0ff62dfe071dbabcd65))
* **gateway:** URL-decode path before route matching (CAB-1964) ([#2170](https://github.com/stoa-platform/stoa/issues/2170)) ([6269c5e](https://github.com/stoa-platform/stoa/commit/6269c5e4a0813862323469735b1e0de907f09b03))
* **ui:** show gateway URLs for all modes + fix stoa-link hostname (CAB-1953) ([#2160](https://github.com/stoa-platform/stoa/issues/2160)) ([3ee4c66](https://github.com/stoa-platform/stoa/commit/3ee4c66397b89d506bbfcd6829637f0bc46ee563))


### Performance

* **gateway,api:** eliminate circular proxy in tool call path ([#2230](https://github.com/stoa-platform/stoa/issues/2230)) ([61e963c](https://github.com/stoa-platform/stoa/commit/61e963c55d824600aeb8ac4168c3ca93e7452916))

## [0.9.1](https://github.com/stoa-platform/stoa/compare/stoa-gateway-v0.9.0...stoa-gateway-v0.9.1) (2026-03-25)


### Features

* **api,ui,gateway:** deployment verification — tags, route reload, test button ([#1938](https://github.com/stoa-platform/stoa/issues/1938)) ([3d81e83](https://github.com/stoa-platform/stoa/commit/3d81e8351e264196220d14b008c90887f65baf9d))
* **api,ui:** add mark deployed button for promoting promotions (CAB-1706) ([#1586](https://github.com/stoa-platform/stoa/issues/1586)) ([c2537dd](https://github.com/stoa-platform/stoa/commit/c2537dd17cf3f56f4b3179239c0c099ccc6046cf))
* **api,ui:** surface cost/token metrics in AI Factory dashboard (CAB-1666) ([#1487](https://github.com/stoa-platform/stoa/issues/1487)) ([9d385a1](https://github.com/stoa-platform/stoa/commit/9d385a16f0b11f5fc6c62abb563dde4664cde02d))
* **api:** add POST /contracts/{id}/publish endpoint ([#1906](https://github.com/stoa-platform/stoa/issues/1906)) ([87a7bcb](https://github.com/stoa-platform/stoa/commit/87a7bcb76d3d81263874501e998a1cc612eca3b5))
* **api:** adopt ArgoCD entries on gateway registration (CAB-1771) ([#1658](https://github.com/stoa-platform/stoa/issues/1658)) ([af45581](https://github.com/stoa-platform/stoa/commit/af455812305ff3cf2a89e965d54582ac9864c908))
* **api:** route chat assistant through Stoa Gateway LLM proxy (CAB-1822) ([#1759](https://github.com/stoa-platform/stoa/issues/1759)) ([83f0bfd](https://github.com/stoa-platform/stoa/commit/83f0bfd9d86178e52d4ca9f957b4b4013536d94d))
* **api:** switch LLM cost dashboard to DB-backed queries (CAB-1822) ([#1771](https://github.com/stoa-platform/stoa/issues/1771)) ([f872831](https://github.com/stoa-platform/stoa/commit/f872831f809b49e7de173e99c4826dd80e3c7089))
* **gateway,ui:** add consumer_id label to Prometheus metrics (CAB-1782) ([#1667](https://github.com/stoa-platform/stoa/issues/1667)) ([1cb43f5](https://github.com/stoa-platform/stoa/commit/1cb43f5bf4e8c5d2f5e7306cab9abc45b2661834))
* **gateway:** A2A protocol support (CAB-1754) ([#1600](https://github.com/stoa-platform/stoa/issues/1600)) ([a9a59d6](https://github.com/stoa-platform/stoa/commit/a9a59d629981f53e13a7763f114083580f094e47))
* **gateway:** add A2A v1.0 protocol with MCP tool bridge (CAB-1754) ([#1746](https://github.com/stoa-platform/stoa/issues/1746)) ([022d51f](https://github.com/stoa-platform/stoa/commit/022d51f4f5a62315540cf0b8f328ff3c11c3a44c))
* **gateway:** add dispatch status endpoint + enable HEGEMON (CAB-1709) ([#1552](https://github.com/stoa-platform/stoa/issues/1552)) ([01aec8c](https://github.com/stoa-platform/stoa/commit/01aec8c90f3b22265c85de18c298a1336d5b8c49))
* **gateway:** add error snapshot capture with PII masking (CAB-1645) ([#1875](https://github.com/stoa-platform/stoa/issues/1875)) ([c40cd7f](https://github.com/stoa-platform/stoa/commit/c40cd7f86e39ade8a9df1c61dc6f697bc0024022))
* **gateway:** add generic WebSocket proxy with governance (CAB-1758) ([#1751](https://github.com/stoa-platform/stoa/issues/1751)) ([c936e25](https://github.com/stoa-platform/stoa/commit/c936e25a926cbe366ec57d119fa9b83dc85a0854))
* **gateway:** add GraphQL + Kafka bridge (CAB-1756, CAB-1757) ([#1763](https://github.com/stoa-platform/stoa/issues/1763)) ([43d1f87](https://github.com/stoa-platform/stoa/commit/43d1f87b8704e2a59d8aff7675e7288194ad09d7))
* **gateway:** add gRPC protocol support with proto parser and MCP bridge (CAB-1755) ([#1757](https://github.com/stoa-platform/stoa/issues/1757)) ([c221fef](https://github.com/stoa-platform/stoa/commit/c221fefeb9a412b456ce63277d29166d63094e9c))
* **gateway:** add HEGEMON agent identity + registry (CAB-1710, CAB-1711) ([#1536](https://github.com/stoa-platform/stoa/issues/1536)) ([fc871cd](https://github.com/stoa-platform/stoa/commit/fc871cd8be60cb2c0f4f6b86b5631f4f9f88f218))
* **gateway:** add HEGEMON inter-agent messaging (CAB-1709 Phase 6) ([#1544](https://github.com/stoa-platform/stoa/issues/1544)) ([d237cb3](https://github.com/stoa-platform/stoa/commit/d237cb3f6fc3ed4102cda62eaf0e6d4d086bcd2e))
* **gateway:** add HEGEMON per-agent budget tracker (CAB-1716) ([#1540](https://github.com/stoa-platform/stoa/issues/1540)) ([d99628e](https://github.com/stoa-platform/stoa/commit/d99628ec4eceb6720b73a8e48aed5963a61893e8))
* **gateway:** add memory budget & backpressure (CAB-1829) ([#1779](https://github.com/stoa-platform/stoa/issues/1779)) ([dd7a565](https://github.com/stoa-platform/stoa/commit/dd7a565c8f5ab9d7111cf1f56cb1f4e60f75409f))
* **gateway:** add Plugin SDK with hot-reload (CAB-1759) ([#1764](https://github.com/stoa-platform/stoa/issues/1764)) ([fe6f9bf](https://github.com/stoa-platform/stoa/commit/fe6f9bf208705b27b08bad6266ec3f8e7e51ec2a))
* **gateway:** add Prompt Guard + RAG Injector for LLM security (CAB-1761) ([#1755](https://github.com/stoa-platform/stoa/issues/1755)) ([fd14124](https://github.com/stoa-platform/stoa/commit/fd141248d8384711e35cd6f8988120550248436a))
* **gateway:** add SOAP/XML bridge with WSDL parser and proxy (CAB-1762) ([#1752](https://github.com/stoa-platform/stoa/issues/1752)) ([d035608](https://github.com/stoa-platform/stoa/commit/d03560826d982f1e4b010e0bd6b5092eafc172a2))
* **gateway:** API proxy config + credential injection (CAB-1723, CAB-1724) ([#1516](https://github.com/stoa-platform/stoa/issues/1516)) ([f8abfd1](https://github.com/stoa-platform/stoa/commit/f8abfd11970b61db3fec6c342b203d204ebdbdaa))
* **gateway:** arena OpenSearch persistence + L1 admin endpoints (CAB-1752) ([#1576](https://github.com/stoa-platform/stoa/issues/1576)) ([bbee40e](https://github.com/stoa-platform/stoa/commit/bbee40e6c3707d5b2d93a5f10cfeaf9574a09f72))
* **gateway:** arena stoa-minimal + configurable proxy perf toggles ([#1960](https://github.com/stoa-platform/stoa/issues/1960)) ([3d2f17c](https://github.com/stoa-platform/stoa/commit/3d2f17cae26fe836f5d330e0f6a01030a5025e90))
* **gateway:** circuit breaker + rate limiter + metrics for API proxy (CAB-1726) ([#1521](https://github.com/stoa-platform/stoa/issues/1521)) ([b0818f8](https://github.com/stoa-platform/stoa/commit/b0818f8d15fd9ff7f896c7009ba07e52c16bdf7e))
* **gateway:** connection pool instrumentation + H2 ALPN (CAB-1832) ([#1784](https://github.com/stoa-platform/stoa/issues/1784)) ([bad192b](https://github.com/stoa-platform/stoa/commit/bad192b272dbaba01b55f962e394d62db153f28d))
* **gateway:** eBPF gateway admin API integration — UAC policy sync (CAB-1848) ([#1797](https://github.com/stoa-platform/stoa/issues/1797)) ([045ed8c](https://github.com/stoa-platform/stoa/commit/045ed8cd5185eb905075e422069d9facd67ac2c6))
* **gateway:** embedded pingora connection pool (CAB-1849) ([#1801](https://github.com/stoa-platform/stoa/issues/1801)) ([8bbf03a](https://github.com/stoa-platform/stoa/commit/8bbf03afa780b543ebdbc363311ab78fca21461a))
* **gateway:** enable OTEL tracing by default (CAB-1831) ([#1782](https://github.com/stoa-platform/stoa/issues/1782)) ([9009d84](https://github.com/stoa-platform/stoa/commit/9009d84e73a5595ae1e710b46250160c61a2d324))
* **gateway:** extract AgentIdentity from JWT claims (CAB-1710) ([#1517](https://github.com/stoa-platform/stoa/issues/1517)) ([d128f6a](https://github.com/stoa-platform/stoa/commit/d128f6a9bae5ea09210c6370b076e2dda573922b))
* **gateway:** flexible UAC contract deserialization for arena L1 (CAB-1706) ([#1585](https://github.com/stoa-platform/stoa/issues/1585)) ([7603e42](https://github.com/stoa-platform/stoa/commit/7603e42f5960b35722a6b59645ee48ecf95dcfb8))
* **gateway:** HEGEMON claim coordination endpoints (CAB-1718) ([#1542](https://github.com/stoa-platform/stoa/issues/1542)) ([1b3c692](https://github.com/stoa-platform/stoa/commit/1b3c692cbe029fccb309978c83de4599d055c9f4))
* **gateway:** HEGEMON dispatch + result endpoints (CAB-1713, CAB-1714) ([#1539](https://github.com/stoa-platform/stoa/issues/1539)) ([faa6c45](https://github.com/stoa-platform/stoa/commit/faa6c45a80cb7cad03ec6732082f5790ca010049))
* **gateway:** HEGEMON metering + fleet dashboard (CAB-1720, CAB-1721) ([#1543](https://github.com/stoa-platform/stoa/issues/1543)) ([0184c58](https://github.com/stoa-platform/stoa/commit/0184c58c9f0aabb23bc8fb4b34e1c22b0c3118a4))
* **gateway:** multi-span latency tracing with Server-Timing header (CAB-1790) ([#1687](https://github.com/stoa-platform/stoa/issues/1687)) ([b1ab0e6](https://github.com/stoa-platform/stoa/commit/b1ab0e60c964276de7d333b542fec9803c47cd38))
* **gateway:** multi-upstream load balancing (CAB-1833) ([#1783](https://github.com/stoa-platform/stoa/issues/1783)) ([a16ade8](https://github.com/stoa-platform/stoa/commit/a16ade8170a37daea4a956178c0f4b6ce330223f))
* **gateway:** request lifecycle phases — ProxyPhase trait + PhaseChain (CAB-1834) ([#1785](https://github.com/stoa-platform/stoa/issues/1785)) ([16a07d6](https://github.com/stoa-platform/stoa/commit/16a07d60f60d89d910255724cb49e68241f7114b))
* **gateway:** RFC 7523 JWT Bearer client authentication (CAB-1740) ([#1531](https://github.com/stoa-platform/stoa/issues/1531)) ([8973240](https://github.com/stoa-platform/stoa/commit/8973240b328815fab71da0691505584f1fbfb7b9))
* **gateway:** route hot-reload with arc-swap (CAB-1828) ([#1780](https://github.com/stoa-platform/stoa/issues/1780)) ([f89c1e7](https://github.com/stoa-platform/stoa/commit/f89c1e7753cb70a0a86f244834611f83f7404a13))
* **gateway:** security profile enforcement middleware (CAB-1744) ([#1553](https://github.com/stoa-platform/stoa/issues/1553)) ([4696d59](https://github.com/stoa-platform/stoa/commit/4696d59bf6ae3da988f9254e40609f60256a90fa))
* **gateway:** service graph call flow visualization (CAB-1842) ([#1794](https://github.com/stoa-platform/stoa/issues/1794)) ([e0dff82](https://github.com/stoa-platform/stoa/commit/e0dff8218837574419a48f3eed3414aa8642b078))
* **gateway:** TCP early filtering pre-TLS (CAB-1830) ([#1781](https://github.com/stoa-platform/stoa/issues/1781)) ([86df95c](https://github.com/stoa-platform/stoa/commit/86df95c8d389d79b26b20cdd9e6e4934b4e10711))
* **gateway:** trace propagation + guardrail headers for L1 arena score (CAB-1752) ([#1578](https://github.com/stoa-platform/stoa/issues/1578)) ([8ce9956](https://github.com/stoa-platform/stoa/commit/8ce99563886ff011a93df8ed857d98691261d091))
* **gateway:** wasm plugin runtime — wasmtime integration (CAB-1644) ([#1787](https://github.com/stoa-platform/stoa/issues/1787)) ([9d3a471](https://github.com/stoa-platform/stoa/commit/9d3a4712d3bda74f84c9b262c9628114e3b28277))
* **gateway:** wire PingoraPool into proxy path (CAB-1849) ([#1905](https://github.com/stoa-platform/stoa/issues/1905)) ([ba39741](https://github.com/stoa-platform/stoa/commit/ba397419b0eae445ccf29b7c0b8d0f0f2d4733e8))
* **helm:** resource lifecycle label taxonomy + Kyverno enforcement (CAB-1877) ([#1864](https://github.com/stoa-platform/stoa/issues/1864)) ([49c186f](https://github.com/stoa-platform/stoa/commit/49c186f9765aef2ba389fe3a99ea77ef1f5610a4))
* **infra:** migrate 4 low-risk backends to STOA Gateway proxy (CAB-1728) ([#1524](https://github.com/stoa-platform/stoa/issues/1524)) ([6615a0b](https://github.com/stoa-platform/stoa/commit/6615a0bd5ea3db263a8d8d0d5ed909c475e3b976))
* **infra:** migrate high-risk consumers to STOA Gateway proxy (CAB-1729) ([#1527](https://github.com/stoa-platform/stoa/issues/1527)) ([662ebfb](https://github.com/stoa-platform/stoa/commit/662ebfb8241dd4bf7e3088cefb24b084b65b2a5e))
* **security:** fapi 2.0 phase 1 — PAR proxy, KC unify, OTel toggle (CAB-1733) ([#1526](https://github.com/stoa-platform/stoa/issues/1526)) ([e38be76](https://github.com/stoa-platform/stoa/commit/e38be76fa78e0d1d8eadec0a17f2a33caade6a4e))
* subscription OAuth2 overhaul — remove API keys, use client_credentials flow ([#1458](https://github.com/stoa-platform/stoa/issues/1458)) ([705859f](https://github.com/stoa-platform/stoa/commit/705859f81b357f955fca1fe537d701a3bc20c80c))
* **ui:** add contextual sub-navigation for hidden pages (CAB-1785) ([#1678](https://github.com/stoa-platform/stoa/issues/1678)) ([6f2f8d1](https://github.com/stoa-platform/stoa/commit/6f2f8d1ee3caef9ae9c2c22b809bc7ce52c65acc))


### Bug Fixes

* **api,gateway:** add internal tool discovery with X-Gateway-Key auth (CAB-1817) ([#1739](https://github.com/stoa-platform/stoa/issues/1739)) ([7ca4769](https://github.com/stoa-platform/stoa/commit/7ca476956fc472fd4e88aa71d442e236e153f0b0))
* **api,gateway:** fix gateway health check + inline app creation (CAB-1907) ([#1963](https://github.com/stoa-platform/stoa/issues/1963)) ([cdc15b5](https://github.com/stoa-platform/stoa/commit/cdc15b510a88b3e619d1d4cbe7bcf030ab3ba033))
* **api:** support KEYCLOAK_ADMIN_PASSWORD env var fallback ([#1444](https://github.com/stoa-platform/stoa/issues/1444)) ([add2c97](https://github.com/stoa-platform/stoa/commit/add2c974313f43130daef0c3424388af69989ee5))
* **arena:** add gateway pre-check and cooldown between runs ([#1597](https://github.com/stoa-platform/stoa/issues/1597)) ([e5df1c4](https://github.com/stoa-platform/stoa/commit/e5df1c47f1502d5bd9669584ffbd6c7f887bd8a9))
* **auth:** add production redirect URIs to opensearch-dashboards OIDC client ([#1684](https://github.com/stoa-platform/stoa/issues/1684)) ([5f59fee](https://github.com/stoa-platform/stoa/commit/5f59fee8b6512dc7808d34d336ca7b3f1f5056dd))
* **ci:** break L3 dispatch loop — dedup + merged PR check ([#1512](https://github.com/stoa-platform/stoa/issues/1512)) ([a206d5d](https://github.com/stoa-platform/stoa/commit/a206d5da96a1b08e93deedccfbe154124fd7c114))
* **ci:** decouple Docker build/deploy from CI on main push ([#1511](https://github.com/stoa-platform/stoa/issues/1511)) ([57cedad](https://github.com/stoa-platform/stoa/commit/57cedadb51bcb21feba21fe04fd1906acbcbbe6d))
* **ci:** fix Arena L0/L2 failures and add serverless GHA benchmark ([#1950](https://github.com/stoa-platform/stoa/issues/1950)) ([0cc0548](https://github.com/stoa-platform/stoa/commit/0cc0548c24521979236471acb6cd189c8ca4c479))
* **ci:** gate docker/deploy jobs on CI success ([#1629](https://github.com/stoa-platform/stoa/issues/1629)) ([3f579ff](https://github.com/stoa-platform/stoa/commit/3f579ff633f7ae872e586b493c57da6d227a46a8))
* **ci:** promote CUJ-02 and CUJ-05 to demo blockers ([#1592](https://github.com/stoa-platform/stoa/issues/1592)) ([8160f86](https://github.com/stoa-platform/stoa/commit/8160f86965171e0ec9441f4ccb628a5f777f31a8))
* **ci:** report actual CI result in reusable workflows ([#1623](https://github.com/stoa-platform/stoa/issues/1623)) ([d65897e](https://github.com/stoa-platform/stoa/commit/d65897e036e8533ccebdb5716d9a09054208b385))
* **gateway:** add deployment_mode span attribute for Tempo service graph (CAB-1842) ([#1811](https://github.com/stoa-platform/stoa/issues/1811)) ([c2fd6db](https://github.com/stoa-platform/stoa/commit/c2fd6db1f6f3ad726e54460b9c7ca67fd758c2c3))
* **gateway:** audit remediations — SSE panic, RwLock poisoning, mode accessors ([#1633](https://github.com/stoa-platform/stoa/issues/1633)) ([d69580a](https://github.com/stoa-platform/stoa/commit/d69580a63d3985bb6bc2f682b0c4b17ebbfba7ee))
* **gateway:** diagnose OTel init failure with eprintln (CAB-1866) ([#1819](https://github.com/stoa-platform/stoa/issues/1819)) ([c593f54](https://github.com/stoa-platform/stoa/commit/c593f544919f233a15a3cec3f4d076d6b6eef534))
* **gateway:** stabilize flaky timestamp test ([#1790](https://github.com/stoa-platform/stoa/issues/1790)) ([ed2c68c](https://github.com/stoa-platform/stoa/commit/ed2c68ce4e20db1dfcc247d689e178253210f78f))
* **gateway:** use advertise URL for registration (CAB-1895) ([#1946](https://github.com/stoa-platform/stoa/issues/1946)) ([7f05e99](https://github.com/stoa-platform/stoa/commit/7f05e99933bff841d8bcfff27a4bb11f9649ad56))
* **gateway:** use internal Keycloak URL for OIDC token endpoint (CAB-1690) ([#1492](https://github.com/stoa-platform/stoa/issues/1492)) ([7781e7a](https://github.com/stoa-platform/stoa/commit/7781e7a7848be9da0b3fe717e0e0d22dbe365873))
* **gateway:** use keycloak_internal_url for OAuth proxy endpoints ([#1814](https://github.com/stoa-platform/stoa/issues/1814)) ([6151440](https://github.com/stoa-platform/stoa/commit/6151440f0d45b12f8b86694521365df438425d8e))
* **gateway:** use stable instance name for CP registration ([#1652](https://github.com/stoa-platform/stoa/issues/1652)) ([01ef203](https://github.com/stoa-platform/stoa/commit/01ef20312f288dd3e1e75ce702cbf831de434d34))
* **gateway:** wire stoa.deployment_mode to OTel Resource (CAB-1842) ([#1805](https://github.com/stoa-platform/stoa/issues/1805)) ([b4fcf3f](https://github.com/stoa-platform/stoa/commit/b4fcf3fc3cb2d367b90d398ea91e6e74a5aea7e7))
* **security:** persist opensearch security config + dashboard in git (CAB-1866) ([#1863](https://github.com/stoa-platform/stoa/issues/1863)) ([78ad9de](https://github.com/stoa-platform/stoa/commit/78ad9de2b19b144a28dacbdd087e7211298bb8aa))
* **security:** resolve 31 CodeQL and Trivy scan alerts ([#1565](https://github.com/stoa-platform/stoa/issues/1565)) ([fee5e7b](https://github.com/stoa-platform/stoa/commit/fee5e7b7fb0c550de18ad7f995ab392633fcd46c))
* **security:** resolve 7 CodeQL code scanning alerts ([#1749](https://github.com/stoa-platform/stoa/issues/1749)) ([ac9e39b](https://github.com/stoa-platform/stoa/commit/ac9e39b0d21d7eb6131e745ca27f5a6d36a845fc))
* **ui,gateway:** fix Call Flow queries + async span instrument (CAB-1866) ([#1844](https://github.com/stoa-platform/stoa/issues/1844)) ([6568f41](https://github.com/stoa-platform/stoa/commit/6568f41c1931710e63714e0c0d6bc5448f8233f4))
* **ui:** correct gateway instances API endpoint path ([#1533](https://github.com/stoa-platform/stoa/issues/1533)) ([1169783](https://github.com/stoa-platform/stoa/commit/11697832a8df442811e63571e479e7fbf5c674e8))
* **ui:** remove env guards from cross-env pages (CAB-1731) ([#1518](https://github.com/stoa-platform/stoa/issues/1518)) ([16c2dba](https://github.com/stoa-platform/stoa/commit/16c2dba9fedb360f01051f8c134f9c863c307aba))
* **ui:** resolve stoa-gateway text ambiguity in OperationsDashboard test ([#1634](https://github.com/stoa-platform/stoa/issues/1634)) ([4884664](https://github.com/stoa-platform/stoa/commit/4884664104d1a1751dc3bcd33f5798d83c186b04))


### Performance

* **gateway:** short-circuit proxy hot path (CAB-1893) ([#1924](https://github.com/stoa-platform/stoa/issues/1924)) ([b9dc6ff](https://github.com/stoa-platform/stoa/commit/b9dc6ffca512a58f23f36407dae3aea8f97fe7bc))
