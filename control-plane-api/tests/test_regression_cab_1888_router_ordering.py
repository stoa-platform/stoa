"""Regression test: api_gateway_assignments routes must not 404 due to router ordering.

PR: #1899 (or next)
Ticket: CAB-1888
Root cause: FastAPI resolves routes in registration order. The apis router
  (prefix /v1/tenants/{tenant_id}/apis) was registered before
  api_gateway_assignments (prefix /v1/tenants/{tenant_id}/apis/{api_id}).
  /deploy and /deployable-environments were swallowed by the apis /{api_id} catch-all.
Invariant: /deploy and /deployable-environments must be reachable (not 404).
"""
import pytest


class TestRegressionCAB1888RouterOrdering:
    """Ensure deployment endpoints are routable (not masked by apis router)."""

    def test_deploy_route_exists_in_app(self):
        """The /deploy route must exist in the FastAPI app routes."""
        from src.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        deploy_route = "/v1/tenants/{tenant_id}/apis/{api_id}/deploy"
        assert deploy_route in routes, (
            f"Route {deploy_route} not found in app. "
            f"Ensure api_gateway_assignments.router is registered BEFORE apis.router."
        )

    def test_deployable_environments_route_exists_in_app(self):
        """The /deployable-environments route must exist in the FastAPI app routes."""
        from src.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        env_route = "/v1/tenants/{tenant_id}/apis/{api_id}/deployable-environments"
        assert env_route in routes, (
            f"Route {env_route} not found in app. "
            f"Ensure api_gateway_assignments.router is registered BEFORE apis.router."
        )

    def test_gateway_assignments_route_exists_in_app(self):
        """The /gateway-assignments route must exist in the FastAPI app routes."""
        from src.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assignments_route = "/v1/tenants/{tenant_id}/apis/{api_id}/gateway-assignments"
        assert assignments_route in routes

    def test_deploy_route_registered_before_apis_catchall(self):
        """The deploy route must appear BEFORE the apis /{api_id} route in registration order."""
        from src.main import app

        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        deploy_idx = None
        apis_catchall_idx = None

        for i, path in enumerate(route_paths):
            if path == "/v1/tenants/{tenant_id}/apis/{api_id}/deploy" and deploy_idx is None:
                deploy_idx = i
            if path == "/v1/tenants/{tenant_id}/apis/{api_id}" and apis_catchall_idx is None:
                apis_catchall_idx = i

        assert deploy_idx is not None, "/deploy route not found"
        assert apis_catchall_idx is not None, "apis /{api_id} route not found"
        assert deploy_idx < apis_catchall_idx, (
            f"/deploy route (index {deploy_idx}) must be registered BEFORE "
            f"apis/{{api_id}} catch-all (index {apis_catchall_idx}). "
            f"Move api_gateway_assignments.router include_router() before apis.router."
        )
