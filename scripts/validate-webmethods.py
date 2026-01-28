#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
validate-webmethods.py
Validates webMethods GitOps YAML files against JSON Schema.

Usage:
    python validate-webmethods.py [--dir PATH]

Exit codes:
    0: All files valid
    1: Validation errors found
    2: Script error
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

try:
    import yaml
    from jsonschema import validate, ValidationError, Draft7Validator
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install pyyaml jsonschema")
    sys.exit(2)


def load_schema(schema_path: Path) -> dict:
    """Load JSON Schema from file."""
    with open(schema_path) as f:
        return json.load(f)


def validate_yaml_file(file_path: Path, schema: dict) -> List[str]:
    """Validate a single YAML file against the schema."""
    errors = []
    
    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"YAML syntax error: {e}"]
    
    if data is None:
        return ["Empty file"]
    
    validator = Draft7Validator(schema)
    for error in validator.iter_errors(data):
        path = " -> ".join(str(p) for p in error.absolute_path) or "root"
        errors.append(f"{path}: {error.message}")
    
    return errors


def validate_references(base_dir: Path) -> List[Tuple[str, str]]:
    """Validate cross-references between APIs, policies, and aliases."""
    errors = []
    
    # Collect all defined policies
    policies_dir = base_dir / "policies"
    defined_policies = set()
    if policies_dir.exists():
        for f in policies_dir.glob("*.yaml"):
            with open(f) as file:
                data = yaml.safe_load(file)
                if data and "metadata" in data:
                    defined_policies.add(data["metadata"].get("name"))
    
    # Collect all defined aliases per environment
    aliases_dir = base_dir / "aliases"
    defined_aliases = {}  # env -> set of alias names
    if aliases_dir.exists():
        for f in aliases_dir.glob("*.yaml"):
            with open(f) as file:
                data = yaml.safe_load(file)
                if data and "metadata" in data and "aliases" in data:
                    env = data["metadata"].get("environment", f.stem)
                    defined_aliases[env] = set(data.get("aliases", {}).keys())
    
    # Check API references
    apis_dir = base_dir / "apis"
    if apis_dir.exists():
        for f in apis_dir.glob("*.yaml"):
            with open(f) as file:
                data = yaml.safe_load(file)
                if not data or "spec" not in data:
                    continue
                
                api_name = data.get("metadata", {}).get("name", f.name)
                spec = data["spec"]
                
                # Check policy references
                for policy in spec.get("policies", []):
                    if policy not in defined_policies:
                        errors.append((
                            str(f),
                            f"API '{api_name}' references undefined policy '{policy}'"
                        ))
                
                # Check alias reference
                backend = spec.get("backend", {})
                alias = backend.get("alias")
                if alias:
                    # Check if alias exists in at least one environment
                    alias_found = any(
                        alias in aliases 
                        for aliases in defined_aliases.values()
                    )
                    if not alias_found:
                        errors.append((
                            str(f),
                            f"API '{api_name}' references undefined alias '{alias}'"
                        ))
    
    return errors


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate webMethods GitOps files")
    parser.add_argument(
        "--dir", 
        type=Path, 
        default=Path("gitops/webmethods"),
        help="Base directory for webMethods GitOps files"
    )
    args = parser.parse_args()
    
    base_dir = args.dir
    schema_path = base_dir / "schema" / "api-schema.json"
    
    if not schema_path.exists():
        print(f"ERROR: Schema not found at {schema_path}")
        sys.exit(2)
    
    print(f"📋 Validating webMethods GitOps in: {base_dir}")
    print("=" * 60)
    
    schema = load_schema(schema_path)
    all_errors = []
    files_checked = 0
    
    # Validate all YAML files
    for subdir in ["apis", "policies", "aliases"]:
        dir_path = base_dir / subdir
        if not dir_path.exists():
            print(f"⚠️  Directory not found: {subdir}/")
            continue
        
        for yaml_file in dir_path.glob("*.yaml"):
            files_checked += 1
            errors = validate_yaml_file(yaml_file, schema)
            
            if errors:
                all_errors.append((str(yaml_file), errors))
                print(f"❌ {yaml_file.relative_to(base_dir)}")
                for e in errors:
                    print(f"   └─ {e}")
            else:
                print(f"✅ {yaml_file.relative_to(base_dir)}")
    
    # Validate cross-references
    print("\n📎 Checking cross-references...")
    ref_errors = validate_references(base_dir)
    if ref_errors:
        for file_path, error in ref_errors:
            all_errors.append((file_path, [error]))
            print(f"❌ {error}")
    else:
        print("✅ All references valid")
    
    # Summary
    print("\n" + "=" * 60)
    if all_errors:
        print(f"❌ FAILED: {len(all_errors)} file(s) with errors")
        sys.exit(1)
    else:
        print(f"✅ PASSED: {files_checked} file(s) validated")
        sys.exit(0)


if __name__ == "__main__":
    main()
