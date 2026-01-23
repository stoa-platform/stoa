"""Policy engine module.

Contains two policy engines:
1. OPA Client - Scope-based RBAC (who can call tools)
2. Argument Engine - Business rules (what argument values are allowed)
"""

from .opa_client import (
    OPAClient,
    PolicyDecision,
    get_opa_client,
    shutdown_opa_client,
)
from .argument_engine import (
    ArgumentPolicyEngine,
    get_argument_engine,
    shutdown_argument_engine,
)
from .argument_models import (
    Policy,
    PolicyFile,
    PolicyResult,
    Rule,
    ConditionLeaf,
    ConditionGroup,
    Operator,
)

__all__ = [
    # OPA Client (RBAC)
    "OPAClient",
    "PolicyDecision",
    "get_opa_client",
    "shutdown_opa_client",
    # Argument Engine (business rules)
    "ArgumentPolicyEngine",
    "get_argument_engine",
    "shutdown_argument_engine",
    # Models
    "Policy",
    "PolicyFile",
    "PolicyResult",
    "Rule",
    "ConditionLeaf",
    "ConditionGroup",
    "Operator",
]
