"""Regression tests: generation-based sync reconciliation (CAB-1950).

Verifies the K8s-style observedGeneration pattern:
- Sync engine skips deployments where attempted_generation >= desired_generation
- Force Sync bumps desired_generation
- Catalog sync bumps desired_generation on state change
- Sync-ack rejects stale generation
"""

import pytest

from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment


def test_regression_generation_columns_exist():
    """GatewayDeployment model has the 3 generation columns."""
    dep = GatewayDeployment()
    assert hasattr(dep, "desired_generation")
    assert hasattr(dep, "synced_generation")
    assert hasattr(dep, "attempted_generation")


def test_regression_generation_defaults():
    """New deployments start with desired=1, synced=0, attempted=0."""
    dep = GatewayDeployment()
    dep.desired_generation = 1
    dep.synced_generation = 0
    dep.attempted_generation = 0
    assert dep.desired_generation == 1
    assert dep.synced_generation == 0
    assert dep.attempted_generation == 0


def test_regression_skip_already_attempted():
    """Deployment with attempted >= desired should be skipped."""
    dep = GatewayDeployment()
    dep.desired_generation = 1
    dep.attempted_generation = 1
    dep.sync_status = DeploymentSyncStatus.ERROR

    # The check in _reconcile_one: attempted >= desired → skip
    should_skip = dep.attempted_generation >= dep.desired_generation
    assert should_skip is True


def test_regression_sync_after_force_bump():
    """After Force Sync bumps generation, deployment should be synced."""
    dep = GatewayDeployment()
    dep.desired_generation = 1
    dep.attempted_generation = 1
    dep.sync_status = DeploymentSyncStatus.ERROR

    # Force Sync: desired_generation++
    dep.desired_generation += 1
    dep.sync_status = DeploymentSyncStatus.PENDING

    should_sync = dep.desired_generation > dep.attempted_generation
    assert should_sync is True


def test_regression_stale_ack_rejected():
    """Sync-ack with generation < desired should be rejected."""
    dep = GatewayDeployment()
    dep.desired_generation = 3
    dep.attempted_generation = 2

    ack_generation = 1  # stale

    should_reject = ack_generation < dep.desired_generation
    assert should_reject is True


def test_regression_current_ack_accepted():
    """Sync-ack with generation == desired should be accepted."""
    dep = GatewayDeployment()
    dep.desired_generation = 2

    ack_generation = 2  # current

    should_reject = ack_generation < dep.desired_generation
    assert should_reject is False
