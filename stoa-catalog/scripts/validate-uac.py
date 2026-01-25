#!/usr/bin/env python3
"""
UAC (Universal API Contract) Validator

Validates YAML UAC files against the JSON Schema.
Usage: python validate-uac.py <uac-file.yaml> [--schema <schema.json>]
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)

try:
    from jsonschema import validate, ValidationError, Draft202012Validator
except ImportError:
    print("Error: jsonschema is required. Install with: pip install jsonschema")
    sys.exit(1)


def find_schema_path() -> Path:
    """Find the schema file relative to script location or cwd."""
    # Try relative to script
    script_dir = Path(__file__).parent.parent
    schema_path = script_dir / "schemas" / "uac.schema.json"
    if schema_path.exists():
        return schema_path

    # Try from cwd
    cwd_path = Path.cwd() / "stoa-catalog" / "schemas" / "uac.schema.json"
    if cwd_path.exists():
        return cwd_path

    # Try direct path
    direct_path = Path("stoa-catalog/schemas/uac.schema.json")
    if direct_path.exists():
        return direct_path

    return schema_path  # Return default, will fail with clear error


def format_path(path) -> str:
    """Format validation error path for display."""
    if not path:
        return "(root)"
    return " > ".join(str(p) for p in path)


def validate_uac(uac_file: str, schema_file: str | None = None) -> tuple[bool, str]:
    """
    Validate a UAC YAML file against the schema.

    Returns:
        (is_valid, message)
    """
    uac_path = Path(uac_file)

    if not uac_path.exists():
        return False, f"File not found: {uac_file}"

    # Find schema
    if schema_file:
        schema_path = Path(schema_file)
    else:
        schema_path = find_schema_path()

    if not schema_path.exists():
        return False, f"Schema not found: {schema_path}"

    # Load schema
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON schema: {e}"

    # Load UAC YAML
    try:
        with open(uac_path, "r", encoding="utf-8") as f:
            uac = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return False, f"Invalid YAML: {e}"

    if uac is None:
        return False, "Empty YAML file"

    # Validate
    try:
        validator = Draft202012Validator(schema)
        errors = list(validator.iter_errors(uac))

        if errors:
            messages = []
            for error in errors[:5]:  # Show max 5 errors
                path = format_path(error.absolute_path)
                messages.append(f"  - Path: {path}")
                messages.append(f"    Error: {error.message}")

            if len(errors) > 5:
                messages.append(f"  ... and {len(errors) - 5} more errors")

            return False, "\n".join(messages)

        return True, "Valid"

    except Exception as e:
        return False, f"Validation error: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Validate UAC (Universal API Contract) YAML files"
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="UAC YAML file(s) to validate"
    )
    parser.add_argument(
        "--schema",
        help="Path to JSON schema (auto-detected if not provided)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only output on errors"
    )

    args = parser.parse_args()

    all_valid = True

    for uac_file in args.files:
        is_valid, message = validate_uac(uac_file, args.schema)

        if is_valid:
            if not args.quiet:
                print(f"✅ {uac_file}")
        else:
            all_valid = False
            print(f"❌ {uac_file}")
            print(message)
            print()

    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
