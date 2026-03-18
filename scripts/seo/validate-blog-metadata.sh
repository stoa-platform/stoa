#!/usr/bin/env bash
# validate-blog-metadata.sh — Validates blog post front-matter against SEO rules
# Reference: .claude/rules/seo-content.md
#
# Usage:
#   ./scripts/seo/validate-blog-metadata.sh <file|directory>
#   ./scripts/seo/validate-blog-metadata.sh ../stoa-docs/blog/
#   ./scripts/seo/validate-blog-metadata.sh ../stoa-docs/blog/2026-03-15-my-article.md
#
# Exit codes: 0 = all pass, 1 = validation errors found

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ERRORS=0
WARNINGS=0
FILES_CHECKED=0

# Valid tags from seo-content.md
VALID_TAGS="release announcement feature security breaking-change mcp community roadmap architecture migration compliance comparison ai open-source tutorial education docker quickstart api-gateway"

# Content type minimum word counts
MIN_WORDS_TUTORIAL=1500
MIN_WORDS_COMPARISON=1200
MIN_WORDS_GLOSSARY=2000
MIN_WORDS_NEWS=800
MIN_WORDS_DEFAULT=800

error() {
  echo -e "  ${RED}ERROR${NC}: $1"
  ((ERRORS++))
}

warn() {
  echo -e "  ${YELLOW}WARN${NC}: $1"
  ((WARNINGS++))
}

ok() {
  echo -e "  ${GREEN}OK${NC}: $1"
}

# Extract YAML front-matter value (simple single-line extraction)
get_frontmatter_value() {
  local file="$1" key="$2"
  sed -n '/^---$/,/^---$/p' "$file" | grep "^${key}:" | head -1 | sed "s/^${key}:[[:space:]]*//" | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/"
}

# Extract YAML array values (handles both inline [a, b] and multi-line - a)
get_frontmatter_array() {
  local file="$1" key="$2"
  local value
  value=$(get_frontmatter_value "$file" "$key")
  if [[ "$value" == "["* ]]; then
    echo "$value" | tr -d '[]' | tr ',' '\n' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/"
  else
    # Multi-line array: read lines starting with "  - " after the key
    sed -n '/^---$/,/^---$/p' "$file" | awk "/^${key}:/{found=1; next} found && /^[[:space:]]*- /{gsub(/^[[:space:]]*- /, \"\"); print} found && /^[a-z]/{exit}"
  fi
}

validate_file() {
  local file="$1"
  local basename
  basename=$(basename "$file")

  # Skip non-markdown
  [[ "$file" != *.md && "$file" != *.mdx ]] && return

  # Check it has front-matter
  if ! head -1 "$file" | grep -q '^---$'; then
    echo -e "\n${RED}SKIP${NC}: $basename — no front-matter"
    return
  fi

  ((FILES_CHECKED++))
  echo -e "\n--- ${basename} ---"

  # 1. Required fields
  local slug title description authors tags keywords
  slug=$(get_frontmatter_value "$file" "slug")
  title=$(get_frontmatter_value "$file" "title")
  description=$(get_frontmatter_value "$file" "description")
  authors=$(get_frontmatter_value "$file" "authors")
  tags=$(get_frontmatter_array "$file" "tags")
  keywords=$(get_frontmatter_array "$file" "keywords")

  [[ -z "$slug" ]] && error "Missing 'slug'" || ok "slug: $slug"
  [[ -z "$title" ]] && error "Missing 'title'" || ok "title present"
  [[ -z "$description" ]] && error "Missing 'description'" || ok "description present"
  [[ -z "$authors" ]] && error "Missing 'authors'" || ok "authors present"
  [[ -z "$tags" ]] && error "Missing 'tags'" || ok "tags present"
  [[ -z "$keywords" ]] && warn "Missing 'keywords' (recommended for SEO)" || ok "keywords present"

  # 2. Title length (max 60 chars)
  if [[ -n "$title" ]]; then
    local title_len=${#title}
    if ((title_len > 60)); then
      error "Title too long: ${title_len} chars (max 60)"
    else
      ok "Title length: ${title_len}/60"
    fi
  fi

  # 3. Description length (max 155 chars)
  if [[ -n "$description" ]]; then
    local desc_len=${#description}
    if ((desc_len > 155)); then
      error "Description too long: ${desc_len} chars (max 155)"
    elif ((desc_len < 50)); then
      warn "Description very short: ${desc_len} chars (aim for 120-155)"
    else
      ok "Description length: ${desc_len}/155"
    fi
  fi

  # 4. Slug format (kebab-case)
  if [[ -n "$slug" ]]; then
    if echo "$slug" | grep -qP '[^a-z0-9-]'; then
      error "Slug not kebab-case: '$slug'"
    else
      ok "Slug format valid"
    fi
  fi

  # 5. Tag validation
  if [[ -n "$tags" ]]; then
    local tag_count=0
    local invalid_tags=""
    while IFS= read -r tag; do
      [[ -z "$tag" ]] && continue
      ((tag_count++))
      if ! echo "$VALID_TAGS" | grep -qw "$tag"; then
        invalid_tags="${invalid_tags} ${tag}"
      fi
    done <<< "$tags"

    if ((tag_count < 2)); then
      warn "Only ${tag_count} tag(s) — aim for 2-5"
    elif ((tag_count > 5)); then
      warn "${tag_count} tags — aim for 2-5"
    else
      ok "Tag count: ${tag_count}"
    fi

    if [[ -n "$invalid_tags" ]]; then
      error "Invalid tags:${invalid_tags} — must be from tags.yml"
    fi
  fi

  # 6. Filename format (YYYY-MM-DD-slug.md)
  if [[ "$basename" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}-.+\.mdx?$ ]]; then
    ok "Filename format valid"
  else
    warn "Filename doesn't match YYYY-MM-DD-<slug>.md pattern"
  fi

  # 7. Word count
  local body_text
  body_text=$(sed '1{/^---$/!q}; 1,/^---$/d' "$file" | sed 's/<[^>]*>//g' | sed '/^```/,/^```/d' | sed '/^import /d')
  local word_count
  word_count=$(echo "$body_text" | wc -w | tr -d ' ')

  # Detect content type from tags
  local min_words=$MIN_WORDS_DEFAULT
  local content_type="default"
  if echo "$tags" | grep -qw "tutorial"; then
    min_words=$MIN_WORDS_TUTORIAL
    content_type="tutorial"
  elif echo "$tags" | grep -qw "comparison"; then
    min_words=$MIN_WORDS_COMPARISON
    content_type="comparison"
  fi

  if ((word_count < min_words)); then
    error "Word count: ${word_count} (min ${min_words} for ${content_type})"
  else
    ok "Word count: ${word_count} (min ${min_words})"
  fi

  # 8. Last-verified tag on comparisons
  if echo "$tags" | grep -qw "comparison"; then
    if ! grep -q 'last verified:' "$file"; then
      error "Comparison article missing '<!-- last verified: YYYY-MM -->' tag"
    else
      local verified_date
      verified_date=$(grep -oP 'last verified: \K[0-9]{4}-[0-9]{2}' "$file" | head -1)
      if [[ -n "$verified_date" ]]; then
        local verified_epoch current_epoch six_months_ago
        verified_epoch=$(date -j -f "%Y-%m" "$verified_date" "+%s" 2>/dev/null || date -d "${verified_date}-01" "+%s" 2>/dev/null || echo "0")
        current_epoch=$(date "+%s")
        six_months_ago=$((current_epoch - 15552000))
        if [[ "$verified_epoch" != "0" ]] && ((verified_epoch < six_months_ago)); then
          warn "Last verified date is >6 months old: ${verified_date}"
        else
          ok "Last verified: ${verified_date}"
        fi
      fi
    fi
  fi

  # 9. Internal links (min 3)
  local internal_links
  internal_links=$(grep -coP '\[.*?\]\(/[^)]+\)' "$file" 2>/dev/null || echo "0")
  if ((internal_links < 3)); then
    warn "Only ${internal_links} internal link(s) — aim for 3+"
  else
    ok "Internal links: ${internal_links}"
  fi

  # 10. Hub link check (spoke must link to its pillar hub)
  local has_hub_link=false
  if grep -q 'api-gateway-migration-guide-2026' "$file"; then has_hub_link=true; fi
  if grep -q 'what-is-mcp-gateway' "$file"; then has_hub_link=true; fi
  if grep -q 'open-source-api-gateway-2026' "$file"; then has_hub_link=true; fi
  if $has_hub_link; then
    ok "Hub link found"
  else
    warn "No pillar hub link found (migration/mcp/open-source hub)"
  fi
}

# --- Main ---

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <file|directory>"
  echo "  Validates blog post front-matter against SEO quality gates."
  echo ""
  echo "Examples:"
  echo "  $0 ../stoa-docs/blog/"
  echo "  $0 ../stoa-docs/blog/2026-03-15-my-article.md"
  exit 1
fi

TARGET="$1"

echo "=== SEO Blog Metadata Validator ==="
echo ""

if [[ -d "$TARGET" ]]; then
  for f in "$TARGET"/*.md "$TARGET"/*.mdx; do
    [[ -f "$f" ]] && validate_file "$f"
  done
elif [[ -f "$TARGET" ]]; then
  validate_file "$TARGET"
else
  echo -e "${RED}Error${NC}: '$TARGET' is not a file or directory"
  exit 1
fi

echo ""
echo "=== Summary ==="
echo "Files checked: ${FILES_CHECKED}"
echo -e "Errors: ${RED}${ERRORS}${NC}"
echo -e "Warnings: ${YELLOW}${WARNINGS}${NC}"

if ((ERRORS > 0)); then
  echo -e "\n${RED}FAIL${NC} — ${ERRORS} error(s) must be fixed before publishing."
  exit 1
else
  echo -e "\n${GREEN}PASS${NC} — all checks passed."
  exit 0
fi
