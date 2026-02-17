"""Sector-based workflow template presets (CAB-593)

Three sector presets:
  - startup: fast auto-approve for all workflow types
  - enterprise: manual review with single-step approval
  - fintech: strict approval chain with multi-step verification
"""

from ..models.workflow import Sector, WorkflowMode, WorkflowType

SECTOR_PRESETS: dict[str, list[dict]] = {
    Sector.STARTUP: [
        {
            "workflow_type": WorkflowType.USER_REGISTRATION,
            "name": "Fast User Onboarding",
            "description": "Auto-approve user registrations for agility",
            "mode": WorkflowMode.AUTO,
            "approval_steps": [],
            "auto_provision": True,
            "notification_config": {"notify_on": ["completed"]},
        },
        {
            "workflow_type": WorkflowType.CONSUMER_REGISTRATION,
            "name": "Fast Consumer Onboarding",
            "description": "Auto-approve consumer registrations",
            "mode": WorkflowMode.AUTO,
            "approval_steps": [],
            "auto_provision": True,
            "notification_config": {"notify_on": ["completed"]},
        },
        {
            "workflow_type": WorkflowType.TENANT_OWNER,
            "name": "Fast Owner Onboarding",
            "description": "Auto-approve tenant owner registrations",
            "mode": WorkflowMode.AUTO,
            "approval_steps": [],
            "auto_provision": True,
            "notification_config": {"notify_on": ["completed"]},
        },
    ],
    Sector.ENTERPRISE: [
        {
            "workflow_type": WorkflowType.USER_REGISTRATION,
            "name": "Enterprise User Review",
            "description": "Manual review for all user registrations",
            "mode": WorkflowMode.MANUAL,
            "approval_steps": [],
            "auto_provision": True,
            "notification_config": {"notify_on": ["created", "approved", "rejected"]},
        },
        {
            "workflow_type": WorkflowType.CONSUMER_REGISTRATION,
            "name": "Enterprise Consumer Review",
            "description": "Manual review for consumer registrations",
            "mode": WorkflowMode.MANUAL,
            "approval_steps": [],
            "auto_provision": True,
            "notification_config": {"notify_on": ["created", "approved", "rejected"]},
        },
        {
            "workflow_type": WorkflowType.TENANT_OWNER,
            "name": "Enterprise Owner Review",
            "description": "Manual review for tenant owner onboarding",
            "mode": WorkflowMode.MANUAL,
            "approval_steps": [],
            "auto_provision": False,
            "notification_config": {"notify_on": ["created", "approved", "rejected"]},
        },
    ],
    Sector.FINTECH: [
        {
            "workflow_type": WorkflowType.USER_REGISTRATION,
            "name": "Fintech User Compliance",
            "description": "Multi-step approval chain for regulated user onboarding",
            "mode": WorkflowMode.APPROVAL_CHAIN,
            "approval_steps": [
                {"step_index": 0, "role": "tenant-admin", "label": "Identity verification"},
                {"step_index": 1, "role": "cpi-admin", "label": "Compliance sign-off"},
            ],
            "auto_provision": False,
            "notification_config": {
                "notify_on": ["created", "step_completed", "approved", "rejected"],
            },
        },
        {
            "workflow_type": WorkflowType.CONSUMER_REGISTRATION,
            "name": "Fintech Consumer KYC",
            "description": "Strict approval chain with KYC verification for consumers",
            "mode": WorkflowMode.APPROVAL_CHAIN,
            "approval_steps": [
                {"step_index": 0, "role": "tenant-admin", "label": "KYC document review"},
                {"step_index": 1, "role": "devops", "label": "Technical integration check"},
                {"step_index": 2, "role": "cpi-admin", "label": "Final compliance approval"},
            ],
            "auto_provision": False,
            "notification_config": {
                "notify_on": ["created", "step_completed", "approved", "rejected"],
            },
        },
        {
            "workflow_type": WorkflowType.TENANT_OWNER,
            "name": "Fintech Owner Verification",
            "description": "Strict approval chain for tenant owner onboarding",
            "mode": WorkflowMode.APPROVAL_CHAIN,
            "approval_steps": [
                {"step_index": 0, "role": "cpi-admin", "label": "Background check review"},
                {"step_index": 1, "role": "cpi-admin", "label": "Board approval confirmation"},
            ],
            "auto_provision": False,
            "notification_config": {
                "notify_on": ["created", "step_completed", "approved", "rejected"],
            },
        },
    ],
}


def get_sector_templates(sector: str) -> list[dict]:
    """Return the list of template definitions for a given sector.

    Args:
        sector: One of 'startup', 'enterprise', 'fintech'.

    Returns:
        List of template dicts ready to be used with TemplateCreate schema.

    Raises:
        ValueError: If sector is not recognised.
    """
    if sector not in SECTOR_PRESETS:
        raise ValueError(f"Unknown sector: {sector}. Valid: {list(SECTOR_PRESETS.keys())}")
    return SECTOR_PRESETS[sector]
