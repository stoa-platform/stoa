# Changelog

## [1.1.2](https://github.com/stoa-platform/stoa/compare/portal-v1.1.1...portal-v1.1.2) (2026-04-11)


### Bug Fixes

* **portal:** restore local dev build (TS6, peer deps, react-is) ([#2295](https://github.com/stoa-platform/stoa/issues/2295)) ([92be112](https://github.com/stoa-platform/stoa/commit/92be11222e4b6d93f13a321e1acedac607cba9e7))
* **security:** remove default credentials, enforce Vault (CAB-2052) ([#2296](https://github.com/stoa-platform/stoa/issues/2296)) ([c953ae3](https://github.com/stoa-platform/stoa/commit/c953ae3cc63f74aebb7dad2fbe8546ced52cde0c))

## [1.1.1](https://github.com/stoa-platform/stoa/compare/portal-v1.1.0...portal-v1.1.1) (2026-04-09)


### Bug Fixes

* **api:** observability RBAC phase 2 (CAB-2031, CAB-2032) ([#2274](https://github.com/stoa-platform/stoa/issues/2274)) ([407438b](https://github.com/stoa-platform/stoa/commit/407438ba3ad1761e3d53f31219389164ee15afba))

## [1.1.0](https://github.com/stoa-platform/stoa/compare/portal-v1.0.0...portal-v1.1.0) (2026-04-08)


### Features

* **api,portal:** admin visibility for seeded portal data ([#2232](https://github.com/stoa-platform/stoa/issues/2232)) ([3531aa5](https://github.com/stoa-platform/stoa/commit/3531aa544a326c1b9e4f87975d6e6364f640dd16))
* **api,portal:** catalog shows all APIs with deployment environment badges ([#1955](https://github.com/stoa-platform/stoa/issues/1955)) ([0295ad1](https://github.com/stoa-platform/stoa/commit/0295ad1aec8c23de54fc30a79f0e20595af40e74))
* **api,portal:** filter portal APIs by deployment environment ([#1951](https://github.com/stoa-platform/stoa/issues/1951)) ([b85dc00](https://github.com/stoa-platform/stoa/commit/b85dc004bc7d5f4e70a55e0e5f13edf30fc529ba))
* **api,ui,portal:** MCP tool observability — gateway binding + usage stats (CAB-1821) ([#1766](https://github.com/stoa-platform/stoa/issues/1766)) ([f370331](https://github.com/stoa-platform/stoa/commit/f3703312dfdc485b1397b9f0911a74ade0ba5d28))
* **api:** gateway enabled flag + visibility + soft disable (CAB-1979) ([#2201](https://github.com/stoa-platform/stoa/issues/2201)) ([0136dd7](https://github.com/stoa-platform/stoa/commit/0136dd749acfb8b4d0e64be3a5a3388c4f6b17b8))
* **api:** OpenSearch traces router + gateway OTel spans (CAB-1997) ([#2221](https://github.com/stoa-platform/stoa/issues/2221)) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **api:** OpenSearch-first monitoring with native Prometheus metrics (CAB-1997) ([0c30d06](https://github.com/stoa-platform/stoa/commit/0c30d068d7d95990aa47810c4978af39a6c14396))
* **e2e:** subscription auth audit + observability fixes ([#2194](https://github.com/stoa-platform/stoa/issues/2194)) ([a77c0a2](https://github.com/stoa-platform/stoa/commit/a77c0a2bc4c0133df61ed8503ac18022f46eb349))
* **gateway:** add gRPC protocol support with proto parser and MCP bridge (CAB-1755) ([#1757](https://github.com/stoa-platform/stoa/issues/1757)) ([c221fef](https://github.com/stoa-platform/stoa/commit/c221fefeb9a412b456ce63277d29166d63094e9c))
* **gateway:** wire PingoraPool into proxy path (CAB-1849) ([#1905](https://github.com/stoa-platform/stoa/issues/1905)) ([ba39741](https://github.com/stoa-platform/stoa/commit/ba397419b0eae445ccf29b7c0b8d0f0f2d4733e8))
* **helm:** resource lifecycle label taxonomy + Kyverno enforcement (CAB-1877) ([#1864](https://github.com/stoa-platform/stoa/issues/1864)) ([49c186f](https://github.com/stoa-platform/stoa/commit/49c186f9765aef2ba389fe3a99ea77ef1f5610a4))
* **portal,api:** enriched API cards + faceted search with sort and tag filters (CAB-1906) ([#1959](https://github.com/stoa-platform/stoa/issues/1959)) ([c03bd4c](https://github.com/stoa-platform/stoa/commit/c03bd4c6d98f2bb7a9c72ccfaa748433cb1524e2))
* **portal:** add governance page with approval queue and lifecycle management (CAB-1525) ([#1874](https://github.com/stoa-platform/stoa/issues/1874)) ([f8dfa5c](https://github.com/stoa-platform/stoa/commit/f8dfa5c7c29e582580e3a292a0661167d41e3f9b))
* **portal:** add service catalog page with category grouping (CAB-1760) ([#1872](https://github.com/stoa-platform/stoa/issues/1872)) ([bb0adb8](https://github.com/stoa-platform/stoa/commit/bb0adb8b560ddee2f3f58ef0da83c2b6b035c10c))
* **portal:** inline app creation + quota bars (CAB-1907) ([#1962](https://github.com/stoa-platform/stoa/issues/1962)) ([edd0b31](https://github.com/stoa-platform/stoa/commit/edd0b31af4e7c0826a86f720b8a55e0c77ed58f2))
* **portal:** Portal chat settings page + source header (CAB-1853) ([#1809](https://github.com/stoa-platform/stoa/issues/1809)) ([5712298](https://github.com/stoa-platform/stoa/commit/5712298e785f62db06bb631e43391b9527960f31))
* **portal:** unified Discover page — merge 3 discovery surfaces (CAB-1905) ([#1958](https://github.com/stoa-platform/stoa/issues/1958)) ([e06b406](https://github.com/stoa-platform/stoa/commit/e06b406790e6bcd5d807267b5c86475cf3d2da8d))
* **portal:** wire FloatingChat in Portal App (CAB-1838) ([#1792](https://github.com/stoa-platform/stoa/issues/1792)) ([d7ca5f8](https://github.com/stoa-platform/stoa/commit/d7ca5f808213a7cb239a4cfbf36cbd24d0d4d4d6))
* **ui,portal:** add data-testid + ARIA roles to 6 pages (CAB-1991) ([#2207](https://github.com/stoa-platform/stoa/issues/2207)) ([4a968dd](https://github.com/stoa-platform/stoa/commit/4a968dda0f75ddb9e974c0be958affc430d3cf5e))
* **ui:** extract FloatingChat + useChatService to shared/ (CAB-1836) ([#1788](https://github.com/stoa-platform/stoa/issues/1788)) ([db7c3e0](https://github.com/stoa-platform/stoa/commit/db7c3e02367974a7e64d34996b1ae6d2bca3d3bf))
* **ui:** rationalize Console + Portal navigation (CAB-1764) ([#1869](https://github.com/stoa-platform/stoa/issues/1869)) ([89ce5a7](https://github.com/stoa-platform/stoa/commit/89ce5a769ead1985264189511d40bf04263810ba))


### Bug Fixes

* **auth:** add production redirect URIs to opensearch-dashboards OIDC client ([#1684](https://github.com/stoa-platform/stoa/issues/1684)) ([5f59fee](https://github.com/stoa-platform/stoa/commit/5f59fee8b6512dc7808d34d336ca7b3f1f5056dd))
* **ci:** fix Arena L0/L2 failures and add serverless GHA benchmark ([#1950](https://github.com/stoa-platform/stoa/issues/1950)) ([0cc0548](https://github.com/stoa-platform/stoa/commit/0cc0548c24521979236471acb6cd189c8ca4c479))
* **deps:** patch 11 security alerts — node-forge, picomatch, go-jose ([#2187](https://github.com/stoa-platform/stoa/issues/2187)) ([0be880e](https://github.com/stoa-platform/stoa/commit/0be880e232e9c6caa968c6a5295e54ed3967d654))
* **gateway:** explicit OTLP batch config for Tempo (CAB-1974) ([#2193](https://github.com/stoa-platform/stoa/issues/2193)) ([80d09cd](https://github.com/stoa-platform/stoa/commit/80d09cdf0a96b5f882ae35f0859c85e58f586368))
* **portal:** add missing shared FloatingChat peer dependencies ([#1796](https://github.com/stoa-platform/stoa/issues/1796)) ([5378d5c](https://github.com/stoa-platform/stoa/commit/5378d5cb5b6dfdcd43357efb2bf44eea479f2fd2))
* **portal:** correct API backend URL in deployment manifest ([#1813](https://github.com/stoa-platform/stoa/issues/1813)) ([21c31d0](https://github.com/stoa-platform/stoa/commit/21c31d05a73d23ff4db495caa13de9e6d169fbbc))
* **security:** persist opensearch security config + dashboard in git (CAB-1866) ([#1863](https://github.com/stoa-platform/stoa/issues/1863)) ([78ad9de](https://github.com/stoa-platform/stoa/commit/78ad9de2b19b144a28dacbdd087e7211298bb8aa))
* **security:** resolve 7 CodeQL code scanning alerts ([#1749](https://github.com/stoa-platform/stoa/issues/1749)) ([ac9e39b](https://github.com/stoa-platform/stoa/commit/ac9e39b0d21d7eb6131e745ca27f5a6d36a845fc))
* **ui:** show gateway URLs for all modes + fix stoa-link hostname (CAB-1953) ([#2160](https://github.com/stoa-platform/stoa/issues/2160)) ([3ee4c66](https://github.com/stoa-platform/stoa/commit/3ee4c66397b89d506bbfcd6829637f0bc46ee563))
