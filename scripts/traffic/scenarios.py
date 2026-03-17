"""Traffic seeder scenario definitions.

Defines the 12 API targets across 5 auth tiers and 4 deployment modes,
plus weighted scenario profiles for realistic traffic patterns.

Note: NewsAPI free tier is for development only — their ToS prohibits
production use with free API keys. Use a paid key for continuous seeding.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# API Definitions
# ---------------------------------------------------------------------------


@dataclass
class ApiTarget:
    """Single API endpoint target for traffic generation."""

    name: str
    url_path: str  # relative path appended to base URL
    auth_type: str  # none, api_key_query, api_key_header, oauth2_cc, bearer, fapi_baseline, fapi_advanced
    mode: str  # edge-mcp, sidecar, connect, connect-wm
    expected_latency_ms: int = 100
    methods: list[str] = field(default_factory=lambda: ["GET"])
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    auth_key_env: str | None = None  # env var name for API key
    auth_param: str | None = None  # query param or header name for API key
    category: str = "general"
    error_injectable: bool = False  # supports X-Simulate-Error header


# --- Tier 1: No Auth (baseline + EU public) ---

ECHO_FALLBACK = ApiTarget(
    name="echo-fallback",
    url_path="/",
    auth_type="none",
    mode="edge-mcp",
    expected_latency_ms=2,
    category="internal",
)

EXCHANGE_RATE = ApiTarget(
    name="exchange-rate",
    url_path="/v4/latest/EUR",
    auth_type="none",
    mode="edge-mcp",
    expected_latency_ms=100,
    category="finance",
)

ECB_FINANCIAL = ApiTarget(
    name="ecb-financial-data",
    url_path="/EXR/D.USD.EUR.SP00.A?lastNObservations=5&format=jsondata",
    auth_type="none",
    mode="sidecar",
    expected_latency_ms=200,
    category="finance",
)

EUROSTAT = ApiTarget(
    name="eurostat",
    url_path="/nama_10_gdp?geo=FR&geo=DE&unit=CLV10_MEUR&na_item=B1GQ&time=2024&format=JSON&lang=en",
    auth_type="none",
    mode="connect",
    expected_latency_ms=300,
    category="statistics",
)

# --- Tier 2: API Key ---

OPENWEATHERMAP = ApiTarget(
    name="openweathermap",
    url_path="/weather",
    auth_type="api_key_query",
    auth_param="appid",
    auth_key_env="OPENWEATHERMAP_API_KEY",
    mode="edge-mcp",
    expected_latency_ms=120,
    query_params={"q": "Paris,FR", "units": "metric"},
    category="weather",
)

NEWSAPI = ApiTarget(
    name="newsapi",
    url_path="/top-headlines",
    auth_type="api_key_header",
    auth_param="X-Api-Key",
    auth_key_env="NEWSAPI_KEY",
    mode="edge-mcp",
    expected_latency_ms=180,
    query_params={"country": "fr", "pageSize": "5"},
    category="news",
)

ALPHAVANTAGE = ApiTarget(
    name="alphavantage",
    url_path="",
    auth_type="api_key_query",
    auth_param="apikey",
    auth_key_env="ALPHAVANTAGE_KEY",
    mode="sidecar",
    expected_latency_ms=250,
    query_params={"function": "GLOBAL_QUOTE", "symbol": "BNPP.PA"},
    category="finance",
)

# --- Tier 3: OAuth2 Client Credentials ---

ECHO_OAUTH2 = ApiTarget(
    name="echo-oauth2",
    url_path="/",
    auth_type="oauth2_cc",
    mode="edge-mcp",
    expected_latency_ms=15,
    category="internal",
    error_injectable=True,
)

ECHO_BEARER = ApiTarget(
    name="echo-bearer",
    url_path="/api/v1/accounts",
    auth_type="bearer",
    mode="connect",
    expected_latency_ms=10,
    category="internal",
    error_injectable=True,
)

# --- Tier 4: FAPI (Banking Demo) ---

FAPI_ACCOUNTS = ApiTarget(
    name="fapi-accounts",
    url_path="/api/v1/accounts",
    auth_type="fapi_baseline",
    mode="edge-mcp",
    expected_latency_ms=20,
    category="banking",
    error_injectable=True,
)

FAPI_TRANSFERS = ApiTarget(
    name="fapi-transfers",
    url_path="/api/v1/transfers",
    auth_type="fapi_advanced",
    mode="edge-mcp",
    expected_latency_ms=25,
    methods=["GET", "POST"],
    category="banking",
    error_injectable=True,
)

# --- Tier 5: Connect → webMethods (optional) ---

WM_API_PROXY = ApiTarget(
    name="wm-api-proxy",
    url_path="/rest/default/stoa/v1/echo",
    auth_type="basic",
    mode="connect-wm",
    expected_latency_ms=80,
    category="enterprise",
)

WM_OAUTH2_SCOPE = ApiTarget(
    name="wm-oauth2-scope",
    url_path="/rest/default/stoa/v1/protected",
    auth_type="oauth2_cc",
    mode="connect-wm",
    expected_latency_ms=120,
    category="enterprise",
)

WM_RATE_LIMITED = ApiTarget(
    name="wm-rate-limited",
    url_path="/rest/default/stoa/v1/echo",
    auth_type="basic",
    mode="connect-wm",
    expected_latency_ms=80,
    category="enterprise",
)


# ---------------------------------------------------------------------------
# API Registry by Mode
# ---------------------------------------------------------------------------

ALL_APIS: list[ApiTarget] = [
    ECHO_FALLBACK,
    EXCHANGE_RATE,
    ECB_FINANCIAL,
    EUROSTAT,
    OPENWEATHERMAP,
    NEWSAPI,
    ALPHAVANTAGE,
    ECHO_OAUTH2,
    ECHO_BEARER,
    FAPI_ACCOUNTS,
    FAPI_TRANSFERS,
]

WEBMETHODS_APIS: list[ApiTarget] = [
    WM_API_PROXY,
    WM_OAUTH2_SCOPE,
    WM_RATE_LIMITED,
]


def get_apis_for_mode(mode: str) -> list[ApiTarget]:
    """Return APIs filtered by deployment mode."""
    if mode == "connect-wm":
        return WEBMETHODS_APIS
    return [a for a in ALL_APIS if a.mode == mode]


def get_all_apis(include_webmethods: bool = False) -> list[ApiTarget]:
    """Return all APIs, optionally including webMethods targets."""
    apis = list(ALL_APIS)
    if include_webmethods:
        apis.extend(WEBMETHODS_APIS)
    return apis


# ---------------------------------------------------------------------------
# Traffic Scenarios
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    """Traffic scenario with weight and request parameters."""

    name: str
    weight: float  # 0.0 - 1.0, sum of all weights should be ~1.0
    requests_per_second: float
    duration_seconds: int
    description: str
    error_injection: bool = False
    error_rate: float = 0.0  # fraction of requests that inject errors
    error_codes: list[int] = field(default_factory=list)
    burst: bool = False


SCENARIOS = [
    Scenario(
        name="steady_state",
        weight=0.40,
        requests_per_second=2.5,
        duration_seconds=120,
        description="Normal traffic — 95% success, dashboard shows healthy state",
    ),
    Scenario(
        name="burst",
        weight=0.15,
        requests_per_second=12.0,
        duration_seconds=30,
        description="Burst traffic — triggers rate limiting, shows eBPF XDP drops",
        burst=True,
    ),
    Scenario(
        name="degraded_backend",
        weight=0.10,
        requests_per_second=2.0,
        duration_seconds=60,
        description="Slow backends — circuit breaker transitions, upstream.cb_state",
        error_injection=True,
        error_rate=0.3,
        error_codes=[503],
    ),
    Scenario(
        name="auth_variety",
        weight=0.25,
        requests_per_second=4.0,
        duration_seconds=90,
        description="Auth type variety — 5 different trace shapes per auth type",
    ),
    Scenario(
        name="error_storm",
        weight=0.10,
        requests_per_second=6.0,
        duration_seconds=30,
        description="Error storm — 401/429/502 patterns for error breakdown panel",
        error_injection=True,
        error_rate=0.6,
        error_codes=[401, 429, 502, 500],
    ),
]


# ---------------------------------------------------------------------------
# Traffic Distribution by Mode
# ---------------------------------------------------------------------------

MODE_WEIGHTS = {
    "edge-mcp": 0.40,
    "sidecar": 0.25,
    "connect": 0.20,
    "connect-wm": 0.15,
}

MODE_WEIGHTS_EDGE_ONLY = {
    "edge-mcp": 1.0,
}

# Backend base URLs per mode (configurable via env)
DEFAULT_BACKENDS = {
    "edge-mcp": "http://stoa-gateway.stoa-system.svc:80",
    "sidecar": "http://stoa-gateway-sidecar:80",
    "connect": "http://stoa-connect:8090",
    "connect-wm": "http://stoa-connect-wm:8090",
}
