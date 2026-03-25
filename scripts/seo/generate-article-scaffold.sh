#!/usr/bin/env bash
# generate-article-scaffold.sh — Generate SEO-compliant blog article scaffolds
# Reference: .claude/rules/seo-content.md
#
# Usage:
#   ./scripts/seo/generate-article-scaffold.sh --type tutorial --slug my-article-slug \
#     --title "My Article Title" --pillar migration --output ../stoa-docs/blog/
#
# Types: tutorial, comparison, glossary, news
# Pillars: migration, mcp, opensource

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Defaults
TYPE="tutorial"
SLUG=""
TITLE=""
PILLAR=""
OUTPUT_DIR="."
KEYWORDS=""
DESCRIPTION=""

usage() {
  cat <<EOF
Usage: $0 [options]

Generate an SEO-compliant blog article scaffold for stoa-docs.

Required:
  --slug <slug>          URL slug (kebab-case, e.g., "axway-api-gateway-migration")
  --title <title>        Article title (max 60 chars, keyword-first)

Optional:
  --type <type>          Content type: tutorial|comparison|glossary|news (default: tutorial)
  --pillar <pillar>      Hub pillar: migration|mcp|opensource (adds hub link)
  --description <desc>   Meta description (max 155 chars)
  --keywords <kw>        Comma-separated keywords
  --output <dir>         Output directory (default: current dir)

Examples:
  $0 --slug axway-api-gateway-migration --title "Axway API Gateway Migration Guide" \\
     --type tutorial --pillar migration --output ../stoa-docs/blog/

  $0 --slug mcp-vs-openai-function-calling --title "MCP vs OpenAI Function Calling" \\
     --type comparison --pillar mcp --output ../stoa-docs/blog/
EOF
  exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type) TYPE="$2"; shift 2 ;;
    --slug) SLUG="$2"; shift 2 ;;
    --title) TITLE="$2"; shift 2 ;;
    --pillar) PILLAR="$2"; shift 2 ;;
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --keywords) KEYWORDS="$2"; shift 2 ;;
    --description) DESCRIPTION="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

[[ -z "$SLUG" ]] && echo -e "${RED}Error${NC}: --slug is required" && usage
[[ -z "$TITLE" ]] && echo -e "${RED}Error${NC}: --title is required" && usage

# Validate type
case "$TYPE" in
  tutorial|comparison|glossary|news) ;;
  *) echo -e "${RED}Error${NC}: Invalid type '$TYPE'. Use: tutorial|comparison|glossary|news"; exit 1 ;;
esac

# Determine tags based on type and pillar
TAGS=""
case "$TYPE" in
  tutorial) TAGS="tutorial" ;;
  comparison) TAGS="comparison" ;;
  glossary) TAGS="education" ;;
  news) TAGS="announcement" ;;
esac

case "$PILLAR" in
  migration) TAGS="$TAGS, migration, api-gateway" ;;
  mcp) TAGS="$TAGS, mcp, ai" ;;
  opensource) TAGS="$TAGS, open-source, api-gateway" ;;
esac

# Hub slugs
HUB_LINK=""
case "$PILLAR" in
  migration) HUB_LINK="/blog/api-gateway-migration-guide-2026" ;;
  mcp) HUB_LINK="/blog/what-is-mcp-gateway" ;;
  opensource) HUB_LINK="/blog/open-source-api-gateway-2026" ;;
esac

# Min word count
MIN_WORDS=800
case "$TYPE" in
  tutorial) MIN_WORDS=1500 ;;
  comparison) MIN_WORDS=1200 ;;
  glossary) MIN_WORDS=2000 ;;
  news) MIN_WORDS=800 ;;
esac

# Date
TODAY=$(date "+%Y-%m-%d")
VERIFIED_DATE=$(date "+%Y-%m")

# Output file
FILENAME="${TODAY}-${SLUG}.md"
FILEPATH="${OUTPUT_DIR}/${FILENAME}"

if [[ -f "$FILEPATH" ]]; then
  echo -e "${RED}Error${NC}: File already exists: $FILEPATH"
  exit 1
fi

# Generate scaffold based on type
generate_tutorial() {
  cat <<EOF
---
slug: ${SLUG}
title: "${TITLE}"
description: "${DESCRIPTION:-TODO: Pain point opener, max 155 chars}"
authors: [stoa-team]
tags: [${TAGS}]
keywords: [${KEYWORDS:-TODO: primary keyword, secondary1, secondary2}]
---

<!-- Target: ${MIN_WORDS}+ words -->

## Introduction

<!-- Answer-first: state the key takeaway in the first paragraph -->

TODO: What problem does this solve? Who is this for? What will they achieve?

## Prerequisites

- STOA Platform installed ([quickstart guide](/docs/guides/quickstart))
- TODO: List prerequisites

## Step 1: TODO

\`\`\`bash
# TODO: First command
\`\`\`

## Step 2: TODO

\`\`\`bash
# TODO: Second command
\`\`\`

## Step 3: TODO

\`\`\`bash
# TODO: Third command
\`\`\`

## Verification

\`\`\`bash
# TODO: How to verify it works
\`\`\`

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| TODO | TODO | TODO |

$(generate_hub_section)

## FAQ

### Q: TODO first question?

TODO: Answer

### Q: TODO second question?

TODO: Answer

### Q: TODO third question?

TODO: Answer
EOF
}

generate_comparison() {
  cat <<EOF
---
slug: ${SLUG}
title: "${TITLE}"
description: "${DESCRIPTION:-TODO: Pain point opener, max 155 chars}"
authors: [stoa-team]
tags: [${TAGS}]
keywords: [${KEYWORDS:-TODO: primary keyword, secondary1, secondary2}]
---
<!-- last verified: ${VERIFIED_DATE} -->

<!-- Target: ${MIN_WORDS}+ words -->

## Introduction

<!-- Answer-first: state the key comparison outcome in the first paragraph -->

TODO: What are we comparing? Why does this comparison matter?

## Quick Comparison

| Feature | STOA | TODO: Competitor |
|---------|------|-----------------|
| License | Apache 2.0 | TODO |
| MCP Support | Native | TODO |
| Self-Hosted | Yes | TODO |
| TODO | TODO | TODO |

## Detailed Analysis

### TODO: Dimension 1

TODO: Analysis

### TODO: Dimension 2

TODO: Analysis

### TODO: Dimension 3

TODO: Analysis

## When to Choose STOA

TODO: Objective criteria for choosing STOA

## When to Choose TODO

TODO: Objective criteria for choosing the alternative

$(generate_hub_section)

## FAQ

### Q: TODO first question?

TODO: Answer

### Q: TODO second question?

TODO: Answer

### Q: TODO third question?

TODO: Answer

---

> Feature comparisons are based on publicly available documentation as of
> ${VERIFIED_DATE}. Product capabilities change frequently. We encourage readers
> to verify current features directly with each vendor. All trademarks
> belong to their respective owners. See [trademarks](/legal/trademarks).
EOF
}

generate_glossary() {
  cat <<EOF
---
slug: ${SLUG}
title: "${TITLE}"
description: "${DESCRIPTION:-TODO: Pain point opener, max 155 chars}"
authors: [stoa-team]
tags: [${TAGS}]
keywords: [${KEYWORDS:-TODO: primary keyword, secondary1, secondary2}]
---

<!-- Target: ${MIN_WORDS}+ words -->

## Introduction

TODO: What concepts are covered? Who is this glossary for?

## A

### TODO: Term

TODO: Definition with internal links to related concepts.

## B

### TODO: Term

TODO: Definition

$(generate_hub_section)

## FAQ

### Q: TODO first question?

TODO: Answer

### Q: TODO second question?

TODO: Answer

### Q: TODO third question?

TODO: Answer
EOF
}

generate_news() {
  cat <<EOF
---
slug: ${SLUG}
title: "${TITLE}"
description: "${DESCRIPTION:-TODO: Pain point opener, max 155 chars}"
authors: [stoa-team]
tags: [${TAGS}]
keywords: [${KEYWORDS:-TODO: primary keyword, secondary1, secondary2}]
---

<!-- Target: ${MIN_WORDS}+ words -->

## What's New

TODO: Key announcement in 1-2 paragraphs.

## Key Changes

- TODO: Change 1
- TODO: Change 2
- TODO: Change 3

## Getting Started

TODO: How to use the new feature.

$(generate_hub_section)

## FAQ

### Q: TODO first question?

TODO: Answer
EOF
}

generate_hub_section() {
  if [[ -n "$HUB_LINK" ]]; then
    echo "## Related Resources"
    echo ""
    echo "This article is part of our [$(pillar_name) series](${HUB_LINK})."
    echo ""
    echo "- TODO: [Related spoke 1](link)"
    echo "- TODO: [Related spoke 2](link)"
    echo "- TODO: [Related spoke 3](link)"
  fi
}

pillar_name() {
  case "$PILLAR" in
    migration) echo "API Gateway Migration" ;;
    mcp) echo "MCP & AI Agents" ;;
    opensource) echo "Open Source API Management" ;;
    *) echo "STOA Platform" ;;
  esac
}

# Generate the file
case "$TYPE" in
  tutorial) generate_tutorial > "$FILEPATH" ;;
  comparison) generate_comparison > "$FILEPATH" ;;
  glossary) generate_glossary > "$FILEPATH" ;;
  news) generate_news > "$FILEPATH" ;;
esac

echo -e "${GREEN}Created${NC}: $FILEPATH"
echo "  Type: $TYPE"
echo "  Min words: $MIN_WORDS"
echo "  Tags: [$TAGS]"
[[ -n "$HUB_LINK" ]] && echo "  Hub: $HUB_LINK"
echo ""
echo "Next steps:"
echo "  1. Fill in TODO sections"
echo "  2. Run: ./scripts/seo/validate-blog-metadata.sh $FILEPATH"
echo "  3. Build: cd $(dirname "$OUTPUT_DIR") && npm run build"
echo "  4. Run: ./scripts/seo/audit-content.sh $(dirname "$OUTPUT_DIR")"
