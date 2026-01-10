#!/usr/bin/env python3
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0

"""
add-license-headers.py - Add Apache 2.0 license headers to source files.

Usage:
    python add-license-headers.py [OPTIONS] [PATHS...]

Options:
    --check         Check mode: report files missing headers (exit 1 if any)
    --dry-run       Show what would be changed without modifying files
    --verbose       Show all files processed
    --year YEAR     Copyright year (default: 2026)
    --holder NAME   Copyright holder (default: STOA Platform Authors)

Examples:
    # Add headers to all files in current directory
    python add-license-headers.py .

    # Check mode for CI
    python add-license-headers.py --check src/

    # Dry run to preview changes
    python add-license-headers.py --dry-run .
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# File extensions and their comment styles
COMMENT_STYLES = {
    # Hash comments
    ".py": {"start": "#", "end": None, "block": False},
    ".sh": {"start": "#", "end": None, "block": False},
    ".bash": {"start": "#", "end": None, "block": False},
    ".zsh": {"start": "#", "end": None, "block": False},
    ".yml": {"start": "#", "end": None, "block": False},
    ".yaml": {"start": "#", "end": None, "block": False},
    ".toml": {"start": "#", "end": None, "block": False},
    ".dockerfile": {"start": "#", "end": None, "block": False},
    
    # Slash comments
    ".ts": {"start": "//", "end": None, "block": False},
    ".tsx": {"start": "//", "end": None, "block": False},
    ".js": {"start": "//", "end": None, "block": False},
    ".jsx": {"start": "//", "end": None, "block": False},
    ".go": {"start": "//", "end": None, "block": False},
    ".rs": {"start": "//", "end": None, "block": False},
    ".java": {"start": "//", "end": None, "block": False},
    ".kt": {"start": "//", "end": None, "block": False},
    ".swift": {"start": "//", "end": None, "block": False},
    ".c": {"start": "//", "end": None, "block": False},
    ".cpp": {"start": "//", "end": None, "block": False},
    ".h": {"start": "//", "end": None, "block": False},
    ".hpp": {"start": "//", "end": None, "block": False},
    
    # CSS/HTML style
    ".css": {"start": "/*", "end": "*/", "block": True},
    ".scss": {"start": "//", "end": None, "block": False},
    ".less": {"start": "//", "end": None, "block": False},
    
    # SQL
    ".sql": {"start": "--", "end": None, "block": False},
}

# Directories to skip
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    "vendor",
    "target",
}

# Files to skip
SKIP_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
}

# SPDX identifier for Apache 2.0
SPDX_ID = "Apache-2.0"


def generate_header(style: dict, year: str, holder: str) -> str:
    """Generate the license header for a given comment style."""
    copyright_line = f"Copyright {year} {holder}"
    spdx_line = f"SPDX-License-Identifier: {SPDX_ID}"
    
    if style["block"]:
        # Block comment style (/* ... */)
        return f'{style["start"]} {copyright_line}\n   {spdx_line} {style["end"]}\n'
    else:
        # Line comment style (# or //)
        prefix = style["start"]
        return f"{prefix} {copyright_line}\n{prefix} {spdx_line}\n"


def has_license_header(content: str) -> bool:
    """Check if the file already has a license header."""
    # Check first 20 lines for SPDX identifier
    lines = content.split("\n")[:20]
    header_area = "\n".join(lines).lower()
    
    return "spdx-license-identifier" in header_area or "apache-2.0" in header_area


def has_shebang(content: str) -> bool:
    """Check if the file starts with a shebang."""
    return content.startswith("#!")


def add_header_to_content(content: str, header: str) -> str:
    """Add the license header to file content, preserving shebang if present."""
    if has_shebang(content):
        # Split at first newline to preserve shebang
        lines = content.split("\n", 1)
        shebang = lines[0]
        rest = lines[1] if len(lines) > 1 else ""
        
        # Add blank line after shebang, then header
        return f"{shebang}\n{header}\n{rest}"
    else:
        return f"{header}\n{content}"


def process_file(
    filepath: Path,
    year: str,
    holder: str,
    check_only: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> Optional[bool]:
    """
    Process a single file.
    
    Returns:
        True if header was added/needed
        False if header already present
        None if file was skipped
    """
    # Get file extension
    ext = filepath.suffix.lower()
    
    # Handle Dockerfile specially
    if filepath.name.lower() == "dockerfile":
        ext = ".dockerfile"
    
    # Skip if not a supported file type
    if ext not in COMMENT_STYLES:
        return None
    
    # Skip specific files
    if filepath.name in SKIP_FILES:
        return None
    
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        if verbose:
            print(f"  SKIP (read error): {filepath}")
        return None
    
    # Check if header already exists
    if has_license_header(content):
        if verbose:
            print(f"  OK: {filepath}")
        return False
    
    # Generate header for this file type
    style = COMMENT_STYLES[ext]
    header = generate_header(style, year, holder)
    
    if check_only:
        print(f"  MISSING: {filepath}")
        return True
    
    if dry_run:
        print(f"  WOULD ADD: {filepath}")
        return True
    
    # Add header
    new_content = add_header_to_content(content, header)
    filepath.write_text(new_content, encoding="utf-8")
    print(f"  ADDED: {filepath}")
    return True


def find_files(paths: list[str]) -> list[Path]:
    """Find all source files in the given paths."""
    files = []
    
    for path_str in paths:
        path = Path(path_str)
        
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for root, dirs, filenames in os.walk(path):
                # Skip directories
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                
                for filename in filenames:
                    filepath = Path(root) / filename
                    files.append(filepath)
    
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description="Add Apache 2.0 license headers to source files."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Paths to process (default: current directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: report files missing headers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all files processed",
    )
    parser.add_argument(
        "--year",
        default="2026",
        help="Copyright year (default: 2026)",
    )
    parser.add_argument(
        "--holder",
        default="STOA Platform Authors",
        help="Copyright holder (default: STOA Platform Authors)",
    )
    
    args = parser.parse_args()
    
    print(f"License Header Tool")
    print(f"  Year: {args.year}")
    print(f"  Holder: {args.holder}")
    print(f"  Mode: {'check' if args.check else 'dry-run' if args.dry_run else 'apply'}")
    print()
    
    files = find_files(args.paths)
    print(f"Found {len(files)} files to process\n")
    
    missing_count = 0
    added_count = 0
    ok_count = 0
    
    for filepath in files:
        result = process_file(
            filepath,
            args.year,
            args.holder,
            check_only=args.check,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        
        if result is True:
            if args.check:
                missing_count += 1
            else:
                added_count += 1
        elif result is False:
            ok_count += 1
    
    print()
    print(f"Summary:")
    print(f"  Already OK: {ok_count}")
    
    if args.check:
        print(f"  Missing headers: {missing_count}")
        if missing_count > 0:
            print("\n❌ Some files are missing license headers!")
            sys.exit(1)
        else:
            print("\n✅ All files have license headers!")
            sys.exit(0)
    else:
        action = "Would add" if args.dry_run else "Added"
        print(f"  {action}: {added_count}")
        
        if added_count > 0 and not args.dry_run:
            print("\n✅ License headers added!")
        elif args.dry_run and added_count > 0:
            print("\n⚠️  Dry run - no files were modified")


if __name__ == "__main__":
    main()
