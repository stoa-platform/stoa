from src.services.gitops_writer.eligibility import is_gitops_create_eligible


def test_disabled_flag_never_routes_to_gitops() -> None:
    assert (
        is_gitops_create_eligible(
            enabled=False,
            tenant_id="demo-gitops",
            eligible_tenants=["demo-gitops", "*"],
        )
        is False
    )


def test_empty_eligible_list_routes_no_tenant() -> None:
    assert is_gitops_create_eligible(enabled=True, tenant_id="demo-gitops", eligible_tenants=[]) is False


def test_explicit_tenant_routes_to_gitops() -> None:
    assert is_gitops_create_eligible(enabled=True, tenant_id="demo-gitops", eligible_tenants=["demo-gitops"]) is True


def test_wildcard_routes_all_tenants_to_gitops() -> None:
    assert is_gitops_create_eligible(enabled=True, tenant_id="__all__", eligible_tenants=["*"]) is True
    assert is_gitops_create_eligible(enabled=True, tenant_id="banking-demo", eligible_tenants=["*"]) is True
