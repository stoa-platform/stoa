#!/usr/bin/env python3
"""
Validate platform configuration files.

Validates:
- YAML syntax
- Required fields for each resource type
- Variable references
- Cross-references between resources
"""

import argparse
import sys
from pathlib import Path
import yaml
import re
from typing import Any


class ConfigValidator:
    """Validates platform configuration files."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.apis: dict[str, Any] = {}
        self.applications: dict[str, Any] = {}
        self.policies: dict[str, Any] = {}
        self.scopes: dict[str, Any] = {}

    def validate(self) -> bool:
        """Run all validations."""
        print(f"Validating configs in: {self.base_dir}")
        print("=" * 60)

        # Load and validate each type
        self._validate_apis()
        self._validate_applications()
        self._validate_policies()
        self._validate_scopes()

        # Cross-reference validation
        self._validate_cross_references()

        # Print results
        print("\n" + "=" * 60)
        if self.errors:
            print(f"\n❌ Validation FAILED with {len(self.errors)} error(s):")
            for err in self.errors:
                print(f"  - {err}")
        else:
            print("\n✅ All validations passed!")

        if self.warnings:
            print(f"\n⚠️  {len(self.warnings)} warning(s):")
            for warn in self.warnings:
                print(f"  - {warn}")

        return len(self.errors) == 0

    def _validate_apis(self):
        """Validate API configuration files."""
        apis_dir = self.base_dir / "apis"
        if not apis_dir.exists():
            self.warnings.append("No apis/ directory found")
            return

        print("\n📋 Validating APIs...")
        for file in apis_dir.glob("*.yaml"):
            self._validate_api_file(file)

    def _validate_api_file(self, file: Path):
        """Validate a single API config file."""
        print(f"  - {file.name}")
        try:
            with open(file) as f:
                config = yaml.safe_load(f)

            if not config:
                self.errors.append(f"{file.name}: Empty file")
                return

            # Required fields
            required = ["apiVersion", "metadata", "spec"]
            for field in required:
                if field not in config:
                    self.errors.append(f"{file.name}: Missing required field '{field}'")

            # Metadata validation
            metadata = config.get("metadata", {})
            if not metadata.get("name"):
                self.errors.append(f"{file.name}: Missing metadata.name")

            # Spec validation
            spec = config.get("spec", {})
            if not spec.get("basePath"):
                self.errors.append(f"{file.name}: Missing spec.basePath")
            if not spec.get("backend"):
                self.errors.append(f"{file.name}: Missing spec.backend")

            # Store for cross-reference
            name = metadata.get("name", file.stem)
            self.apis[name] = config

            # Validate policies reference
            policies = spec.get("policies", [])
            for policy in policies:
                if policy not in ["jwt-validation", "rate-limit-standard",
                                  "cors-platform", "logging-standard"]:
                    self.warnings.append(
                        f"{file.name}: Unknown policy '{policy}' (may be custom)"
                    )

        except yaml.YAMLError as e:
            self.errors.append(f"{file.name}: YAML syntax error: {e}")
        except Exception as e:
            self.errors.append(f"{file.name}: Error: {e}")

    def _validate_applications(self):
        """Validate application configuration files."""
        apps_dir = self.base_dir / "applications"
        if not apps_dir.exists():
            self.warnings.append("No applications/ directory found")
            return

        print("\n📱 Validating Applications...")
        for file in apps_dir.glob("*.yaml"):
            self._validate_application_file(file)

    def _validate_application_file(self, file: Path):
        """Validate a single application config file."""
        print(f"  - {file.name}")
        try:
            with open(file) as f:
                config = yaml.safe_load(f)

            if not config:
                self.errors.append(f"{file.name}: Empty file")
                return

            # Required fields
            if "metadata" not in config:
                self.errors.append(f"{file.name}: Missing metadata")
            if "spec" not in config:
                self.errors.append(f"{file.name}: Missing spec")

            spec = config.get("spec", {})

            # OAuth2 config required
            if "oauth2" not in spec:
                self.errors.append(f"{file.name}: Missing spec.oauth2")
            else:
                oauth2 = spec["oauth2"]
                if not oauth2.get("clientId"):
                    self.errors.append(f"{file.name}: Missing oauth2.clientId")
                if not oauth2.get("grantTypes"):
                    self.warnings.append(f"{file.name}: No grantTypes specified")

            # Store for cross-reference
            name = config.get("metadata", {}).get("name", file.stem)
            self.applications[name] = config

        except yaml.YAMLError as e:
            self.errors.append(f"{file.name}: YAML syntax error: {e}")
        except Exception as e:
            self.errors.append(f"{file.name}: Error: {e}")

    def _validate_policies(self):
        """Validate policy configuration files."""
        policies_dir = self.base_dir / "policies"
        if not policies_dir.exists():
            self.warnings.append("No policies/ directory found")
            return

        print("\n🛡️  Validating Policies...")
        for file in policies_dir.glob("*.yaml"):
            self._validate_policy_file(file)

    def _validate_policy_file(self, file: Path):
        """Validate a single policy config file."""
        print(f"  - {file.name}")
        try:
            with open(file) as f:
                config = yaml.safe_load(f)

            if not config:
                self.errors.append(f"{file.name}: Empty file")
                return

            # Required fields
            if "metadata" not in config:
                self.errors.append(f"{file.name}: Missing metadata")

            spec = config.get("spec", {})
            if not spec.get("type"):
                self.errors.append(f"{file.name}: Missing spec.type")

            # Store for cross-reference
            name = config.get("metadata", {}).get("name", file.stem)
            self.policies[name] = config

        except yaml.YAMLError as e:
            self.errors.append(f"{file.name}: YAML syntax error: {e}")
        except Exception as e:
            self.errors.append(f"{file.name}: Error: {e}")

    def _validate_scopes(self):
        """Validate scope configuration files."""
        scopes_dir = self.base_dir / "scopes"
        if not scopes_dir.exists():
            self.warnings.append("No scopes/ directory found")
            return

        print("\n🔐 Validating Scopes...")
        for file in scopes_dir.glob("*.yaml"):
            self._validate_scope_file(file)

    def _validate_scope_file(self, file: Path):
        """Validate a single scope config file."""
        print(f"  - {file.name}")
        try:
            with open(file) as f:
                config = yaml.safe_load(f)

            if not config:
                self.errors.append(f"{file.name}: Empty file")
                return

            spec = config.get("spec", {})
            scopes = spec.get("scopes", [])

            if not scopes:
                self.warnings.append(f"{file.name}: No scopes defined")

            for scope in scopes:
                if not scope.get("name"):
                    self.errors.append(f"{file.name}: Scope missing name")

            # Store for cross-reference
            name = config.get("metadata", {}).get("name", file.stem)
            self.scopes[name] = config

        except yaml.YAMLError as e:
            self.errors.append(f"{file.name}: YAML syntax error: {e}")
        except Exception as e:
            self.errors.append(f"{file.name}: Error: {e}")

    def _validate_cross_references(self):
        """Validate cross-references between resources."""
        print("\n🔗 Validating Cross-References...")

        # Check application subscriptions reference valid APIs
        for app_name, app_config in self.applications.items():
            subscriptions = app_config.get("spec", {}).get("subscriptions", [])
            for sub in subscriptions:
                api_name = sub.get("apiName")
                if api_name and api_name not in self.apis:
                    self.warnings.append(
                        f"Application '{app_name}' subscribes to unknown API '{api_name}'"
                    )

        # Check API policies reference valid policies
        for api_name, api_config in self.apis.items():
            policies = api_config.get("spec", {}).get("policies", [])
            for policy in policies:
                if policy not in self.policies and policy not in [
                    "jwt-validation", "rate-limit-standard",
                    "cors-platform", "logging-standard"
                ]:
                    self.warnings.append(
                        f"API '{api_name}' uses unknown policy '{policy}'"
                    )

        print("  Cross-reference check complete")

    def _check_undefined_variables(self, content: str, filename: str):
        """Check for undefined variables without defaults."""
        # Pattern for ${VAR} without default
        pattern = r'\$\{([A-Z_]+)\}'
        matches = re.findall(pattern, content)

        # Filter out variables with defaults (${VAR:default})
        for var in matches:
            if f"${{{var}:" not in content and f"${{{var}:-" not in content:
                self.warnings.append(
                    f"{filename}: Variable ${{{var}}} has no default value"
                )


def main():
    parser = argparse.ArgumentParser(description="Validate platform configuration files")
    parser.add_argument(
        "--dir", "-d",
        type=Path,
        default=Path("deploy/platform-bootstrap"),
        help="Directory containing config files"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )
    args = parser.parse_args()

    if not args.dir.exists():
        print(f"Error: Directory not found: {args.dir}")
        sys.exit(1)

    validator = ConfigValidator(args.dir)
    success = validator.validate()

    if args.strict and validator.warnings:
        print("\n❌ Strict mode: treating warnings as errors")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
