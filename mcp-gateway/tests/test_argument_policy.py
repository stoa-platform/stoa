"""Tests for Argument Policy Engine.

CAB-876: Tests for YAML-based argument validation policies.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

import yaml

from src.policy.argument_engine import (
    ArgumentPolicyEngine,
    get_argument_engine,
    shutdown_argument_engine,
)
from src.policy.argument_models import (
    Policy,
    PolicyFile,
    PolicyResult,
    Rule,
    ConditionLeaf,
    ConditionGroup,
    Operator,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_policy_dir():
    """Create temporary directory for test policies."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def marchemalo_policy_yaml():
    """Marchemalo test policy YAML content."""
    return {
        "policies": [
            {
                "name": "marchemalo-cycle-required",
                "description": "P1/P2 issues must be in a cycle",
                "tool": "Linear:create_issue",
                "enabled": True,
                "priority": 100,
                "rules": [
                    {
                        "condition": {
                            "all": [
                                {"field": "priority", "operator": "in", "value": [1, 2]},
                                {"field": "cycle", "operator": "is_null"},
                            ]
                        },
                        "action": "deny",
                        "message": "Marchemalo: Les tickets Urgent/High doivent etre dans un cycle",
                    }
                ],
            }
        ]
    }


@pytest.fixture
def mock_settings():
    """Mock settings for tests."""
    mock = MagicMock()
    mock.argument_policy_enabled = True
    mock.argument_policy_path = "."
    mock.argument_policy_fail_closed = True
    return mock


@pytest.fixture
async def engine_with_marchemalo(temp_policy_dir, marchemalo_policy_yaml, mock_settings):
    """Create engine with marchemalo policy loaded."""
    policy_file = temp_policy_dir / "marchemalo.yaml"
    with open(policy_file, "w") as f:
        yaml.dump(marchemalo_policy_yaml, f)

    mock_settings.argument_policy_path = str(temp_policy_dir)

    with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
        engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
        await engine.startup()
        yield engine
        await engine.shutdown()


# =============================================================================
# Model Tests
# =============================================================================


class TestArgumentModels:
    """Tests for policy model validation."""

    def test_condition_leaf_valid(self):
        """Test valid condition leaf."""
        cond = ConditionLeaf(field="priority", operator=Operator.IN, value=[1, 2])
        assert cond.field == "priority"
        assert cond.operator == Operator.IN
        assert cond.value == [1, 2]

    def test_condition_leaf_is_null(self):
        """Test is_null operator doesn't need value."""
        cond = ConditionLeaf(field="cycle", operator=Operator.IS_NULL)
        assert cond.operator == Operator.IS_NULL
        assert cond.value is None

    def test_condition_group_all(self):
        """Test condition group with all (AND)."""
        group = ConditionGroup(
            all=[
                ConditionLeaf(field="priority", operator=Operator.EQ, value=1),
                ConditionLeaf(field="cycle", operator=Operator.IS_NULL),
            ]
        )
        assert len(group.all) == 2
        assert group.any is None

    def test_condition_group_any(self):
        """Test condition group with any (OR)."""
        group = ConditionGroup(
            any=[
                ConditionLeaf(field="status", operator=Operator.EQ, value="draft"),
                ConditionLeaf(field="status", operator=Operator.EQ, value="pending"),
            ]
        )
        assert group.all is None
        assert len(group.any) == 2

    def test_condition_group_requires_all_or_any(self):
        """Test that condition group requires either all or any."""
        with pytest.raises(ValueError, match="Must specify either"):
            ConditionGroup()

    def test_condition_group_rejects_both(self):
        """Test that condition group rejects both all and any."""
        with pytest.raises(ValueError, match="Cannot specify both"):
            ConditionGroup(
                all=[ConditionLeaf(field="a", operator=Operator.EQ, value=1)],
                any=[ConditionLeaf(field="b", operator=Operator.EQ, value=2)],
            )

    def test_policy_validation(self):
        """Test policy model validation."""
        policy = Policy(
            name="test-policy",
            tool="Test:*",
            rules=[
                Rule(
                    condition=ConditionLeaf(field="x", operator=Operator.EQ, value=1),
                    action="deny",
                    message="Denied",
                )
            ],
        )
        assert policy.enabled is True
        assert policy.priority == 0
        assert len(policy.rules) == 1

    def test_policy_file_parsing(self):
        """Test PolicyFile model."""
        data = {
            "policies": [
                {
                    "name": "test",
                    "tool": "Test:action",
                    "rules": [
                        {
                            "condition": {"field": "x", "operator": "eq", "value": 1},
                            "action": "deny",
                            "message": "Test",
                        }
                    ],
                }
            ]
        }
        policy_file = PolicyFile.model_validate(data)
        assert len(policy_file.policies) == 1
        assert policy_file.policies[0].name == "test"


# =============================================================================
# Engine Tests
# =============================================================================


class TestArgumentPolicyEngine:
    """Tests for ArgumentPolicyEngine."""

    @pytest.mark.asyncio
    async def test_engine_disabled(self, mock_settings):
        """Test engine when disabled."""
        mock_settings.argument_policy_enabled = False

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine()
            await engine.startup()

            result = engine.evaluate("any:tool", {"any": "args"})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_engine_empty_policies(self, temp_policy_dir, mock_settings):
        """Test engine with no policies loaded."""
        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            assert engine.policy_count == 0
            result = engine.evaluate("any:tool", {})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_engine_loads_policies(self, engine_with_marchemalo):
        """Test that engine loads policies from YAML."""
        assert engine_with_marchemalo.policy_count == 1


# =============================================================================
# Marchemalo Use Case Tests
# =============================================================================


class TestMarchemaloPolicy:
    """Tests for the Marchemalo use case.

    Marchemalo rule: P1/P2 issues must be in a cycle.
    """

    @pytest.mark.asyncio
    async def test_p1_without_cycle_denied(self, engine_with_marchemalo):
        """P1 issue without cycle should be denied."""
        result = engine_with_marchemalo.evaluate(
            "Linear:create_issue",
            {"title": "Critical Bug", "priority": 1, "cycle": None},
        )
        assert result.allowed is False
        assert result.policy_name == "marchemalo-cycle-required"
        assert "Marchemalo" in result.message

    @pytest.mark.asyncio
    async def test_p2_without_cycle_denied(self, engine_with_marchemalo):
        """P2 issue without cycle should be denied."""
        result = engine_with_marchemalo.evaluate(
            "Linear:create_issue",
            {"title": "High Priority", "priority": 2, "cycle": None},
        )
        assert result.allowed is False
        assert result.policy_name == "marchemalo-cycle-required"

    @pytest.mark.asyncio
    async def test_p1_with_cycle_allowed(self, engine_with_marchemalo):
        """P1 issue with cycle should be allowed."""
        result = engine_with_marchemalo.evaluate(
            "Linear:create_issue",
            {"title": "Critical Bug", "priority": 1, "cycle": "sprint-42"},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_p2_with_cycle_allowed(self, engine_with_marchemalo):
        """P2 issue with cycle should be allowed."""
        result = engine_with_marchemalo.evaluate(
            "Linear:create_issue",
            {"title": "High Priority", "priority": 2, "cycle": "sprint-42"},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_p3_without_cycle_allowed(self, engine_with_marchemalo):
        """P3 issue without cycle should be allowed (no policy match)."""
        result = engine_with_marchemalo.evaluate(
            "Linear:create_issue",
            {"title": "Minor Issue", "priority": 3, "cycle": None},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_p4_without_cycle_allowed(self, engine_with_marchemalo):
        """P4 issue without cycle should be allowed."""
        result = engine_with_marchemalo.evaluate(
            "Linear:create_issue",
            {"title": "Nice to have", "priority": 4, "cycle": None},
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_cycle_key_absent_treated_as_null(self, engine_with_marchemalo):
        """Absent cycle key should be treated as null (denied for P1)."""
        result = engine_with_marchemalo.evaluate(
            "Linear:create_issue",
            {"title": "Critical Bug", "priority": 1},  # No 'cycle' key at all
        )
        assert result.allowed is False
        assert "Marchemalo" in result.message

    @pytest.mark.asyncio
    async def test_different_tool_not_matched(self, engine_with_marchemalo):
        """Policy should not match different tools."""
        result = engine_with_marchemalo.evaluate(
            "GitHub:create_issue",
            {"title": "Test", "priority": 1, "cycle": None},
        )
        assert result.allowed is True  # No matching policy


# =============================================================================
# Operator Tests
# =============================================================================


class TestOperators:
    """Tests for condition operators."""

    @pytest.mark.asyncio
    async def test_eq_operator(self, temp_policy_dir, mock_settings):
        """Test 'eq' operator."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-eq",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {"field": "status", "operator": "eq", "value": "blocked"},
                            "action": "deny",
                            "message": "Blocked status not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match
            result = engine.evaluate("test:action", {"status": "blocked"})
            assert result.allowed is False

            # Should not match
            result = engine.evaluate("test:action", {"status": "open"})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_ne_operator(self, temp_policy_dir, mock_settings):
        """Test 'ne' operator."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-ne",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {"field": "env", "operator": "ne", "value": "production"},
                            "action": "deny",
                            "message": "Only production allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match (staging != production)
            result = engine.evaluate("test:action", {"env": "staging"})
            assert result.allowed is False

            # Should not match (production == production)
            result = engine.evaluate("test:action", {"env": "production"})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_in_operator(self, temp_policy_dir, mock_settings):
        """Test 'in' operator."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-in",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {
                                "field": "status",
                                "operator": "in",
                                "value": ["draft", "pending"],
                            },
                            "action": "deny",
                            "message": "Status not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match
            result = engine.evaluate("test:action", {"status": "draft"})
            assert result.allowed is False

            result = engine.evaluate("test:action", {"status": "pending"})
            assert result.allowed is False

            # Should not match
            result = engine.evaluate("test:action", {"status": "published"})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_gt_operator(self, temp_policy_dir, mock_settings):
        """Test 'gt' (greater than) operator."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-gt",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {"field": "amount", "operator": "gt", "value": 1000},
                            "action": "deny",
                            "message": "Amount too high",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match (1500 > 1000)
            result = engine.evaluate("test:action", {"amount": 1500})
            assert result.allowed is False

            # Should not match (1000 is not > 1000)
            result = engine.evaluate("test:action", {"amount": 1000})
            assert result.allowed is True

            # Should not match (500 < 1000)
            result = engine.evaluate("test:action", {"amount": 500})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_contains_operator(self, temp_policy_dir, mock_settings):
        """Test 'contains' operator."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-contains",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {"field": "email", "operator": "contains", "value": "@test.com"},
                            "action": "deny",
                            "message": "Test emails not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match
            result = engine.evaluate("test:action", {"email": "user@test.com"})
            assert result.allowed is False

            # Should not match
            result = engine.evaluate("test:action", {"email": "user@company.com"})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_regex_operator(self, temp_policy_dir, mock_settings):
        """Test 'regex' operator."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-regex",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {
                                "field": "code",
                                "operator": "regex",
                                "value": "^TEST-[0-9]+$",
                            },
                            "action": "deny",
                            "message": "Test codes not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match
            result = engine.evaluate("test:action", {"code": "TEST-123"})
            assert result.allowed is False

            # Should not match
            result = engine.evaluate("test:action", {"code": "PROD-123"})
            assert result.allowed is True

            await engine.shutdown()


# =============================================================================
# Nested Field Tests
# =============================================================================


class TestNestedFields:
    """Tests for nested field access."""

    @pytest.mark.asyncio
    async def test_nested_field_access(self, temp_policy_dir, mock_settings):
        """Test nested field path access (user.role)."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-nested",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {"field": "user.role", "operator": "eq", "value": "guest"},
                            "action": "deny",
                            "message": "Guests not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match
            result = engine.evaluate("test:action", {"user": {"role": "guest"}})
            assert result.allowed is False

            # Should not match
            result = engine.evaluate("test:action", {"user": {"role": "admin"}})
            assert result.allowed is True

            # Missing nested path returns None
            result = engine.evaluate("test:action", {"user": {}})
            assert result.allowed is True  # is_null would match, eq doesn't

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_deeply_nested_field(self, temp_policy_dir, mock_settings):
        """Test deeply nested field access (a.b.c.d)."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-deep-nested",
                    "tool": "test:*",
                    "rules": [
                        {
                            "condition": {
                                "field": "data.metadata.labels.env",
                                "operator": "eq",
                                "value": "test",
                            },
                            "action": "deny",
                            "message": "Test env not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match
            result = engine.evaluate(
                "test:action",
                {"data": {"metadata": {"labels": {"env": "test"}}}},
            )
            assert result.allowed is False

            # Should not match
            result = engine.evaluate(
                "test:action",
                {"data": {"metadata": {"labels": {"env": "prod"}}}},
            )
            assert result.allowed is True

            await engine.shutdown()


# =============================================================================
# Fail-Closed Tests
# =============================================================================


class TestFailClosed:
    """Tests for fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_fail_closed_on_load_error(self, temp_policy_dir, mock_settings):
        """Test fail-closed when policy load fails."""
        # Create invalid YAML
        invalid_file = temp_policy_dir / "invalid.yaml"
        with open(invalid_file, "w") as f:
            f.write("invalid: yaml: content: [")

        mock_settings.argument_policy_path = str(temp_policy_dir)
        mock_settings.argument_policy_fail_closed = True

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            result = engine.evaluate("any:tool", {})
            assert result.allowed is False
            assert "error" in result.message.lower()

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_fail_open_on_load_error(self, temp_policy_dir, mock_settings):
        """Test fail-open when configured and policy load fails."""
        # Create invalid YAML
        invalid_file = temp_policy_dir / "invalid.yaml"
        with open(invalid_file, "w") as f:
            f.write("invalid: yaml: content: [")

        mock_settings.argument_policy_path = str(temp_policy_dir)
        mock_settings.argument_policy_fail_closed = False  # Fail-open

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Fail-open allows through on error
            result = engine.evaluate("any:tool", {})
            assert result.allowed is True

            await engine.shutdown()


# =============================================================================
# Wildcard Pattern Tests
# =============================================================================


class TestWildcardPatterns:
    """Tests for tool name wildcard matching."""

    @pytest.mark.asyncio
    async def test_wildcard_suffix(self, temp_policy_dir, mock_settings):
        """Test wildcard suffix pattern (Linear:*)."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-wildcard",
                    "tool": "Linear:*",
                    "rules": [
                        {
                            "condition": {"field": "restricted", "operator": "eq", "value": True},
                            "action": "deny",
                            "message": "Restricted operations not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match any Linear tool
            result = engine.evaluate("Linear:create_issue", {"restricted": True})
            assert result.allowed is False

            result = engine.evaluate("Linear:update_issue", {"restricted": True})
            assert result.allowed is False

            # Should not match other tools
            result = engine.evaluate("GitHub:create_issue", {"restricted": True})
            assert result.allowed is True

            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_wildcard_prefix(self, temp_policy_dir, mock_settings):
        """Test wildcard prefix pattern (*:delete_*)."""
        policy_yaml = {
            "policies": [
                {
                    "name": "test-delete-protection",
                    "tool": "*:delete_*",
                    "rules": [
                        {
                            "condition": {"field": "force", "operator": "eq", "value": True},
                            "action": "deny",
                            "message": "Force delete not allowed",
                        }
                    ],
                }
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # Should match any delete operation
            result = engine.evaluate("Linear:delete_issue", {"force": True})
            assert result.allowed is False

            result = engine.evaluate("GitHub:delete_repo", {"force": True})
            assert result.allowed is False

            # Should not match non-delete operations
            result = engine.evaluate("Linear:create_issue", {"force": True})
            assert result.allowed is True

            await engine.shutdown()


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests for singleton management."""

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self, mock_settings):
        """Test get_argument_engine returns singleton."""
        await shutdown_argument_engine()

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine1 = await get_argument_engine()
            engine2 = await get_argument_engine()
            assert engine1 is engine2

            await shutdown_argument_engine()

    @pytest.mark.asyncio
    async def test_shutdown_clears_singleton(self, mock_settings):
        """Test shutdown clears the singleton."""
        await shutdown_argument_engine()

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine1 = await get_argument_engine()
            await shutdown_argument_engine()
            engine2 = await get_argument_engine()
            assert engine1 is not engine2

            await shutdown_argument_engine()


# =============================================================================
# Policy Priority Tests
# =============================================================================


class TestPolicyPriority:
    """Tests for policy priority ordering."""

    @pytest.mark.asyncio
    async def test_higher_priority_evaluated_first(self, temp_policy_dir, mock_settings):
        """Test that higher priority policies are evaluated first."""
        policy_yaml = {
            "policies": [
                {
                    "name": "low-priority",
                    "tool": "test:action",
                    "priority": 10,
                    "rules": [
                        {
                            "condition": {"field": "x", "operator": "eq", "value": 1},
                            "action": "deny",
                            "message": "Low priority denied",
                        }
                    ],
                },
                {
                    "name": "high-priority",
                    "tool": "test:action",
                    "priority": 100,
                    "rules": [
                        {
                            "condition": {"field": "x", "operator": "eq", "value": 1},
                            "action": "allow",
                            "message": "High priority allowed",
                        }
                    ],
                },
            ]
        }
        with open(temp_policy_dir / "test.yaml", "w") as f:
            yaml.dump(policy_yaml, f)

        mock_settings.argument_policy_path = str(temp_policy_dir)

        with patch("src.policy.argument_engine.get_settings", return_value=mock_settings):
            engine = ArgumentPolicyEngine(policy_path=str(temp_policy_dir))
            await engine.startup()

            # High priority (allow) should win over low priority (deny)
            result = engine.evaluate("test:action", {"x": 1})
            assert result.allowed is True
            assert result.policy_name == "high-priority"

            await engine.shutdown()
