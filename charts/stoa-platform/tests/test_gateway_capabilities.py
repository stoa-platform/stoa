"""Offline gateway capability contracts; run with unittest discovery."""
import pathlib
import subprocess
import unittest

import yaml

CHART = pathlib.Path(__file__).resolve().parents[1]


def render(values):
    return subprocess.run(
        ["helm", "template", "capabilities", str(CHART), "-f", "-"],
        input=yaml.safe_dump({"stoaGateway": values}),
        text=True, capture_output=True,
    )


def gateway_env(values):
    result = render(values)
    assert result.returncode == 0, result.stderr
    deployment = next(d for d in yaml.safe_load_all(result.stdout)
                      if d and d.get("kind") == "Deployment"
                      and d["metadata"]["name"] == "stoa-gateway")
    variables = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    assert len({v["name"] for v in variables}) == len(variables)
    return {v["name"]: v for v in variables}


class GatewayCapabilitiesTests(unittest.TestCase):
    def test_runtime_defaults(self):
        variables = gateway_env({})
        expected = {
            "STOA_ROUTE_RELOAD_ENABLED": "false",
            "STOA_ROUTE_RELOAD_INTERVAL_SECS": "30",
            "STOA_FEDERATION_ENABLED": "false",
            "STOA_FEDERATION_CACHE_TTL_SECS": "300",
            "STOA_FEDERATION_CACHE_MAX_ENTRIES": "10000",
            "STOA_API_PROXY__ENABLED": "false",
            "STOA_API_PROXY__REQUIRE_AUTH": "true",
        }
        for name, value in expected.items():
            self.assertEqual(variables[name], {"name": name, "value": value})
        self.assertNotIn("STOA_FEDERATION_UPSTREAMS", variables)
        self.assertFalse(any("__BACKENDS__" in name for name in variables))

    def test_enabled_capabilities_and_secret_reference(self):
        variables = gateway_env({
            "routing": {"reloadEnabled": True, "reloadIntervalSecs": 45},
            "federation": {
                "enabled": True, "cacheTtlSecs": 60, "cacheMaxEntries": 50,
                "upstreamsSecretRef": {"name": "existing-upstreams", "key": "servers"},
            },
            "apiProxy": {"enabled": True, "requireAuth": False, "backends": {
                "catalog": {"enabled": True, "base_url": "https://catalog.example.test",
                            "auth_type": "none", "public": True,
                            "allowed_paths": ["/items"], "timeout_secs": 15},
            }},
        })
        for name, value in {
            "STOA_ROUTE_RELOAD_ENABLED": "true", "STOA_ROUTE_RELOAD_INTERVAL_SECS": "45",
            "STOA_FEDERATION_ENABLED": "true", "STOA_FEDERATION_CACHE_TTL_SECS": "60",
            "STOA_FEDERATION_CACHE_MAX_ENTRIES": "50", "STOA_API_PROXY__ENABLED": "true",
            "STOA_API_PROXY__REQUIRE_AUTH": "false",
            "STOA_API_PROXY__BACKENDS__CATALOG__BASE_URL": "https://catalog.example.test",
            "STOA_API_PROXY__BACKENDS__CATALOG__ALLOWED_PATHS": '["/items"]',
            "STOA_API_PROXY__BACKENDS__CATALOG__TIMEOUT_SECS": "15",
        }.items():
            self.assertEqual(variables[name]["value"], value)
        self.assertEqual(variables["STOA_FEDERATION_UPSTREAMS"], {
            "name": "STOA_FEDERATION_UPSTREAMS",
            "valueFrom": {"secretKeyRef": {"name": "existing-upstreams", "key": "servers"}},
        })

    def test_zero_and_false_are_preserved(self):
        variables = gateway_env({
            "routing": {"reloadEnabled": False},
            "federation": {"cacheTtlSecs": 0},
            "apiProxy": {"backends": {"catalog": {
                "enabled": False, "base_url": "https://catalog.example.test",
                "rate_limit_rpm": 0, "circuit_breaker_enabled": False,
            }}},
        })
        self.assertEqual(variables["STOA_FEDERATION_CACHE_TTL_SECS"]["value"], "0")
        self.assertEqual(variables["STOA_API_PROXY__BACKENDS__CATALOG__ENABLED"]["value"], "false")
        self.assertEqual(variables["STOA_API_PROXY__BACKENDS__CATALOG__RATE_LIMIT_RPM"]["value"], "0")

    def test_federation_requires_existing_secret(self):
        result = render({"federation": {"enabled": True}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upstreamsSecretRef", result.stderr)

    def test_rejects_plaintext_credentials_and_ambiguous_backend_names(self):
        for backend in (
            {"catalog": {"auth_token": "REPLACE_FROM_VAULT"}},
            {"catalog__nested": {"base_url": "https://catalog.example.test"}},
        ):
            with self.subTest(backend=backend):
                result = render({"apiProxy": {"backends": backend}})
                self.assertNotEqual(result.returncode, 0)

    def test_secret_reference_requires_key(self):
        result = render({"federation": {
            "upstreamsSecretRef": {"name": "existing-upstreams"},
        }})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upstreamsSecretRef.key", result.stderr)


if __name__ == "__main__":
    unittest.main()
