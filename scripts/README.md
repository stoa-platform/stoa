# License Headers Tool

Scripts to add and verify Apache 2.0 license headers in STOA source files.

## Header Format

### Python / Shell / YAML
```python
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
```

### TypeScript / JavaScript / Go / Rust
```typescript
// Copyright 2026 STOA Platform Authors
// SPDX-License-Identifier: Apache-2.0
```

### CSS
```css
/* Copyright 2026 STOA Platform Authors
   SPDX-License-Identifier: Apache-2.0 */
```

## Usage

### Add headers to all files
```bash
python scripts/add-license-headers.py .
```

### Check mode (for CI)
```bash
python scripts/add-license-headers.py --check src/
```

### Preview changes (dry run)
```bash
python scripts/add-license-headers.py --dry-run .
```

### Verbose mode
```bash
python scripts/add-license-headers.py --verbose .
```

## Supported File Types

| Extension | Comment Style |
|-----------|---------------|
| `.py`, `.sh`, `.yml`, `.yaml`, `.toml` | `#` |
| `.ts`, `.tsx`, `.js`, `.jsx` | `//` |
| `.go`, `.rs`, `.java`, `.kt` | `//` |
| `.c`, `.cpp`, `.h`, `.hpp` | `//` |
| `.css` | `/* */` |
| `.sql` | `--` |

## Skipped Directories

- `.git`, `node_modules`, `__pycache__`
- `.venv`, `venv`, `dist`, `build`
- `.next`, `.nuxt`, `coverage`
- `vendor`, `target`

## CI Integration

### GitHub Actions

```yaml
- name: Check license headers
  run: python scripts/add-license-headers.py --check .
```

### Pre-commit Hook

```yaml
repos:
  - repo: local
    hooks:
      - id: license-headers
        name: Check license headers
        entry: python scripts/add-license-headers.py --check
        language: python
        pass_filenames: false
```

## Notes

- Shebangs (`#!/usr/bin/env python3`) are preserved
- Files with existing headers are skipped
- SPDX identifier is used for machine-readability
