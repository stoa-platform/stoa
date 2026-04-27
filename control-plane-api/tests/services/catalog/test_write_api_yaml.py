"""Tests for the ``write_api_yaml`` CLI helper.

Spec §7 (CAB-2185 B-FLOW test scaffolding). Helper is pure: no DB, no Git.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.services.catalog.write_api_yaml import main, render_api_yaml

_VALID_UUID = "12345678-1234-1234-1234-123456789012"


class TestRenderApiYaml:
    def test_minimal_yaml_parses(self) -> None:
        content = render_api_yaml(
            tenant_id="demo-gitops",
            api_name="manual-test",
            version="1.0.0",
            backend_url="http://mock-backend:9090",
        )
        parsed = yaml.safe_load(content)
        assert parsed["id"] == "manual-test"
        assert parsed["name"] == "manual-test"
        assert parsed["display_name"] == "manual-test"
        assert parsed["version"] == "1.0.0"
        assert parsed["backend_url"] == "http://mock-backend:9090"
        assert parsed["status"] == "active"
        assert parsed["deployments"] == {"dev": True, "staging": False}
        assert "tags" not in parsed
        assert "category" not in parsed
        assert "description" not in parsed

    def test_uuid_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="UUID-shaped"):
            render_api_yaml(
                tenant_id="demo",
                api_name=_VALID_UUID,
                version="1.0.0",
                backend_url="http://x",
            )

    def test_status_constant_active(self) -> None:
        content = render_api_yaml(
            tenant_id="demo",
            api_name="petstore",
            version="1.0.0",
            backend_url="http://x",
        )
        parsed = yaml.safe_load(content)
        assert parsed["status"] == "active"

    def test_deployments_default(self) -> None:
        content = render_api_yaml(
            tenant_id="demo",
            api_name="petstore",
            version="1.0.0",
            backend_url="http://x",
        )
        parsed = yaml.safe_load(content)
        assert parsed["deployments"] == {"dev": True, "staging": False}

    def test_optional_fields_when_provided(self) -> None:
        content = render_api_yaml(
            tenant_id="demo",
            api_name="petstore",
            version="2.0.0",
            backend_url="https://api.example.org",
            display_name="Pet Store API",
            description="A description.",
            category="Banking",
            tags=["portal:published", "banking"],
        )
        parsed = yaml.safe_load(content)
        assert parsed["display_name"] == "Pet Store API"
        assert parsed["description"] == "A description."
        assert parsed["category"] == "Banking"
        assert parsed["tags"] == ["portal:published", "banking"]

    def test_empty_tenant_rejected(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            render_api_yaml(
                tenant_id="",
                api_name="petstore",
                version="1.0.0",
                backend_url="http://x",
            )

    def test_empty_version_rejected(self) -> None:
        with pytest.raises(ValueError, match="version"):
            render_api_yaml(
                tenant_id="demo",
                api_name="petstore",
                version="",
                backend_url="http://x",
            )

    def test_idempotent_render(self) -> None:
        # Same inputs → same output (yaml.safe_dump is deterministic with our flags).
        out1 = render_api_yaml(
            tenant_id="demo",
            api_name="petstore",
            version="1.0.0",
            backend_url="http://x",
        )
        out2 = render_api_yaml(
            tenant_id="demo",
            api_name="petstore",
            version="1.0.0",
            backend_url="http://x",
        )
        assert out1 == out2

    def test_round_trip_yaml(self) -> None:
        content = render_api_yaml(
            tenant_id="demo",
            api_name="petstore",
            version="1.0.0",
            backend_url="http://x",
            tags=["portal:published"],
        )
        parsed = yaml.safe_load(content)
        re_rendered = yaml.safe_dump(parsed, sort_keys=False, default_flow_style=False, allow_unicode=True)
        assert yaml.safe_load(re_rendered) == parsed


class TestCli:
    def test_cli_happy_path(self, tmp_path: Path) -> None:
        output = tmp_path / "api.yaml"
        rc = main(
            [
                "--tenant",
                "demo-gitops",
                "--name",
                "manual-test",
                "--version",
                "1.0.0",
                "--backend",
                "http://mock-backend:9090",
                "--output",
                str(output),
            ]
        )
        assert rc == 0
        assert output.exists()
        parsed = yaml.safe_load(output.read_text())
        assert parsed["name"] == "manual-test"
        assert parsed["status"] == "active"

    def test_cli_uuid_name_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        output = tmp_path / "api.yaml"
        rc = main(
            [
                "--tenant",
                "demo",
                "--name",
                _VALID_UUID,
                "--version",
                "1.0.0",
                "--backend",
                "http://x",
                "--output",
                str(output),
            ]
        )
        assert rc == 2
        captured = capsys.readouterr()
        assert "UUID-shaped" in captured.err
        assert not output.exists()

    def test_cli_with_tags_and_category(self, tmp_path: Path) -> None:
        output = tmp_path / "api.yaml"
        rc = main(
            [
                "--tenant",
                "demo",
                "--name",
                "petstore",
                "--version",
                "1.0.0",
                "--backend",
                "http://x",
                "--category",
                "Banking",
                "--tag",
                "portal:published",
                "--tag",
                "banking",
                "--output",
                str(output),
            ]
        )
        assert rc == 0
        parsed = yaml.safe_load(output.read_text())
        assert parsed["category"] == "Banking"
        assert parsed["tags"] == ["portal:published", "banking"]

    def test_cli_refuses_symlink_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target = tmp_path / "real-target.yaml"
        target.write_text("placeholder\n")
        symlink = tmp_path / "link.yaml"
        symlink.symlink_to(target)
        rc = main(
            [
                "--tenant",
                "demo",
                "--name",
                "petstore",
                "--version",
                "1.0.0",
                "--backend",
                "http://x",
                "--output",
                str(symlink),
            ]
        )
        assert rc == 2
        captured = capsys.readouterr()
        assert "symlink" in captured.err
        # Original target unchanged
        assert target.read_text() == "placeholder\n"

    def test_cli_refuses_directory_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target_dir = tmp_path / "subdir"
        target_dir.mkdir()
        rc = main(
            [
                "--tenant",
                "demo",
                "--name",
                "petstore",
                "--version",
                "1.0.0",
                "--backend",
                "http://x",
                "--output",
                str(target_dir),
            ]
        )
        assert rc == 2
        captured = capsys.readouterr()
        assert "not a regular file" in captured.err
