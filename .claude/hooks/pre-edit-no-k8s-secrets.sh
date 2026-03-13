#!/bin/bash
# Pre-edit hook: Block writing real secrets in K8s Secret manifests or Docker configs.
# Detects stringData/data values that look like real credentials (not placeholders).
# Exit 0 = allow, Exit 2 = block with message

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# Only check Edit and Write tools
if [[ "$TOOL_NAME" != "Edit" && "$TOOL_NAME" != "Write" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Only check YAML files in infra-related directories
case "$FILE_PATH" in
  */deploy/*.yaml|*/deploy/*.yml|*/k8s/*.yaml|*/k8s/*.yml|*/charts/*.yaml|*/charts/*.yml|*/kafka/*.yaml)
    ;;
  *)
    exit 0
    ;;
esac

# Get the content being written
if [ "$TOOL_NAME" = "Write" ]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null)
elif [ "$TOOL_NAME" = "Edit" ]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty' 2>/dev/null)
fi

if [ -z "$CONTENT" ]; then
  exit 0
fi

# Check for bcrypt hashes (leaked in OpenSearch/htpasswd configs)
if echo "$CONTENT" | grep -qE '\$2[aby]?\$[0-9]+\$[./A-Za-z0-9]{53}'; then
  MATCH=$(echo "$CONTENT" | grep -E '\$2[aby]?\$[0-9]+\$' | head -1)
  echo "BLOCKED: Detected bcrypt hash in $FILE_PATH." >&2
  echo "  Line: $MATCH" >&2
  echo "  Use REPLACE_WITH_BCRYPT_HASH_FROM_INFISICAL placeholder instead." >&2
  exit 2
fi

# Check for password values that look real (not placeholders)
# Extract lines with PASSWORD/SECRET/TOKEN keys and check their values
while IFS= read -r line; do
  # Skip comments
  [[ "$line" =~ ^[[:space:]]*# ]] && continue

  # Match password-like keys with a colon separator
  if echo "$line" | grep -qiE '(PASSWORD|_SECRET|_TOKEN|API_KEY|CREDENTIALS)\s*:'; then
    # Extract the value part (everything after the last colon, trimmed)
    value=$(echo "$line" | awk -F: '{for(i=2;i<=NF;i++) printf "%s%s",(i>2?":":""),$i; print ""}' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^["'"'"']//;s/["'"'"']$//')

    # Skip if value is empty or a placeholder
    [ -z "$value" ] && continue
    echo "$value" | grep -qiE '(REPLACE_|CHANGE_ME|REPLACE_ME|TODO|FIXME|your[_-]|example|placeholder|xxxxxxxx|REDACTED)' && continue
    echo "$value" | grep -qF '${' && continue
    echo "$value" | grep -qF '<YOUR' && continue
    echo "$value" | grep -qF '?' && continue  # ${VAR:?msg} shell expansion

    # Block if value looks like a real credential (8+ chars, alphanumeric with special chars)
    if [ ${#value} -ge 8 ] && echo "$value" | grep -qE '[A-Za-z].*[0-9!@#$%^&_-]|[0-9].*[A-Za-z]'; then
      echo "BLOCKED: Detected what looks like a real secret in $FILE_PATH." >&2
      echo "  Line: $line" >&2
      echo "  Value: $value" >&2
      echo "  Use a placeholder (REPLACE_FROM_INFISICAL, \${VAR}, CHANGE_ME) instead of hardcoded values." >&2
      echo "  Secrets must be managed via Infisical (vault.gostoa.dev), not committed to git." >&2
      exit 2
    fi
  fi
done <<< "$CONTENT"

exit 0
