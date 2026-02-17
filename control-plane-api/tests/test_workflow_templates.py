"""Tests for sector-based workflow template presets (CAB-593)"""

import pytest

from src.services.workflow_templates import SECTOR_PRESETS, get_sector_templates


class TestSectorPresets:
    """Validate sector preset definitions."""

    def test_all_sectors_defined(self) -> None:
        assert set(SECTOR_PRESETS.keys()) == {"startup", "enterprise", "fintech"}

    @pytest.mark.parametrize("sector", ["startup", "enterprise", "fintech"])
    def test_each_sector_has_three_workflow_types(self, sector: str) -> None:
        templates = get_sector_templates(sector)
        types = {t["workflow_type"] for t in templates}
        assert types == {"user_registration", "consumer_registration", "tenant_owner"}

    def test_startup_all_auto(self) -> None:
        templates = get_sector_templates("startup")
        for t in templates:
            assert t["mode"] == "auto"
            assert t["approval_steps"] == []
            assert t["auto_provision"] is True

    def test_enterprise_all_manual(self) -> None:
        templates = get_sector_templates("enterprise")
        for t in templates:
            assert t["mode"] == "manual"
            assert t["approval_steps"] == []

    def test_fintech_all_approval_chain(self) -> None:
        templates = get_sector_templates("fintech")
        for t in templates:
            assert t["mode"] == "approval_chain"
            assert len(t["approval_steps"]) >= 2

    def test_fintech_consumer_has_three_steps(self) -> None:
        templates = get_sector_templates("fintech")
        consumer = next(t for t in templates if t["workflow_type"] == "consumer_registration")
        assert len(consumer["approval_steps"]) == 3
        assert consumer["approval_steps"][0]["role"] == "tenant-admin"
        assert consumer["approval_steps"][2]["role"] == "cpi-admin"

    def test_fintech_auto_provision_disabled(self) -> None:
        templates = get_sector_templates("fintech")
        for t in templates:
            assert t["auto_provision"] is False

    def test_unknown_sector_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown sector"):
            get_sector_templates("gaming")

    def test_notification_config_present(self) -> None:
        for sector in SECTOR_PRESETS:
            for t in get_sector_templates(sector):
                assert "notify_on" in t["notification_config"]
                assert isinstance(t["notification_config"]["notify_on"], list)
