#!/usr/bin/env bash
# Publish worktree changes on a dedicated branch and open or update a pull
# request into main. Never pushes main, never force-pushes, never merges.
# GitHub: GH_TOKEN. GitLab: GITLAB_TOKEN. The caller sets the git identity.
set -euo pipefail
BRANCH=""
TITLE=""
BODY_FILE=""
MESSAGE_FILE=""
REPO="${GITHUB_REPOSITORY:-}"
FORGE="github"
GITLAB_PROJECT_NAME=""
PATHS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --title) TITLE="${2:-}"; shift 2 ;;
    --body-file) BODY_FILE="${2:-}"; shift 2 ;;
    --message-file) MESSAGE_FILE="${2:-}"; shift 2 ;;
    --repo) REPO="${2:-}"; shift 2 ;;
    --forge) FORGE="${2:-}"; shift 2 ;;
    --gitlab-project) GITLAB_PROJECT_NAME="${2:-}"; shift 2 ;;
    --path) PATHS+=("${2:-}"); shift 2 ;;
    *) echo "::error::unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$BRANCH" || -z "$TITLE" || -z "$BODY_FILE" || -z "$MESSAGE_FILE" || ${#PATHS[@]} -eq 0 ]]; then
  echo "::error::--branch, --title, --body-file, --message-file and --path are required" >&2
  exit 2
fi
case "$BRANCH" in
  main|master|refs/heads/main|refs/heads/master)
    echo "::error::refusing to publish ${BRANCH}" >&2
    exit 1
    ;;
esac
case "$FORGE" in
  github|gitlab) ;;
  *) echo "::error::unsupported forge: ${FORGE}" >&2; exit 2 ;;
esac
if [[ ! -f "$BODY_FILE" || ! -f "$MESSAGE_FILE" ]]; then
  echo "::error::body or message file is missing" >&2
  exit 2
fi
# Stage only the requested paths. A missing, untracked path is not a change.
staged_any=false
for path in "${PATHS[@]}"; do
  if [[ -e "$path" ]] || git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
    git add -A -- "$path"
    staged_any=true
  else
    echo "Path not present, skipping: $path"
  fi
done
if [[ "$staged_any" == false ]] || git diff --cached --quiet; then
  echo "No changes to commit"
  exit 0
fi
snapshot="$(mktemp -d)"
manifest="${snapshot}/manifest.txt"
: > "$manifest"
for path in "${PATHS[@]}"; do
  if [[ -e "$path" ]]; then
    mkdir -p "${snapshot}/tree/$(dirname "$path")"
    cp -a "$path" "${snapshot}/tree/${path}"
    printf 'present %s\n' "$path" >> "$manifest"
  elif git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
    printf 'absent %s\n' "$path" >> "$manifest"
  fi
done
git reset --hard HEAD
for path in "${PATHS[@]}"; do
  git clean -fd -- "$path" >/dev/null 2>&1 || true
done
# checkout -B from origin/main tracks main. Drop that upstream.
checkout_from_main() {
  git checkout -B "$1" origin/main
  git branch --unset-upstream >/dev/null 2>&1 || true
}
git fetch origin main
selected="$BRANCH"
run_branch="${BRANCH}-${GITHUB_RUN_ID:-local}"
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git fetch origin "refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}"
  git checkout -B "$BRANCH" "origin/${BRANCH}"
  if ! git merge --no-edit origin/main; then
    echo "::warning::Cannot merge origin/main into ${BRANCH} without a force-push; opening ${run_branch}"
    git merge --abort || true
    selected="$run_branch"
    checkout_from_main "$selected"
  fi
else
  checkout_from_main "$selected"
fi
case "$selected" in
  main|master|refs/heads/main|refs/heads/master)
    echo "::error::refusing to publish ${selected}" >&2
    exit 1
    ;;
esac
while read -r state path; do
  [[ -z "${state:-}" ]] && continue
  if [[ "$state" == "present" ]]; then
    mkdir -p "$(dirname "$path")"
    rm -rf "$path"
    cp -a "${snapshot}/tree/${path}" "$path"
  else
    rm -rf "$path"
  fi
done < "$manifest"
rm -rf "$snapshot"
git add -A -- "${PATHS[@]}"
if git diff --cached --quiet; then
  echo "No changes to commit on ${selected}"
  exit 0
fi
git commit -F "$MESSAGE_FILE"
git push origin "HEAD:refs/heads/${selected}"
if [[ "$FORGE" == "github" ]]; then
  if [[ -z "${GH_TOKEN:-${GITHUB_TOKEN:-}}" ]]; then
    echo "::error::GH_TOKEN is required to open the pull request" >&2
    exit 1
  fi
  export GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"
  repo_args=()
  [[ -n "$REPO" ]] && repo_args=(--repo "$REPO")
  existing="$(gh pr list "${repo_args[@]}" --head "$selected" --base main --state open --json number --jq '.[0].number')"
  if [[ -n "$existing" && "$existing" != "null" ]]; then
    gh pr edit "$existing" "${repo_args[@]}" --title "$TITLE" --body-file "$BODY_FILE" >/dev/null
    pr_url="$(gh pr view "$existing" "${repo_args[@]}" --json url --jq '.url')"
  else
    pr_url="$(gh pr create "${repo_args[@]}" --base main --head "$selected" --title "$TITLE" --body-file "$BODY_FILE")"
  fi
else
  if [[ -z "$GITLAB_PROJECT_NAME" || -z "${GITLAB_TOKEN:-}" ]]; then
    echo "::error::GITLAB_PROJECT and GITLAB_TOKEN are required for GitLab" >&2
    exit 1
  fi
  project_enc="$(jq -rn --arg p "$GITLAB_PROJECT_NAME" '$p|@uri')"
  branch_enc="$(jq -rn --arg b "$selected" '$b|@uri')"
  api="https://gitlab.com/api/v4/projects/${project_enc}/merge_requests"
  existing="$(curl -fsS --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    "${api}?source_branch=${branch_enc}&target_branch=main&state=opened")"
  iid="$(jq -r '.[0].iid // empty' <<<"$existing")"
  if [[ -n "$iid" ]]; then
    pr_url="$(curl -fsS --request PUT --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
      --data-urlencode "title=${TITLE}" \
      --data-urlencode "description@${BODY_FILE}" \
      "${api}/${iid}" | jq -r '.web_url')"
  else
    pr_url="$(curl -fsS --request POST --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
      --data-urlencode "source_branch=${selected}" \
      --data-urlencode "target_branch=main" \
      --data-urlencode "title=${TITLE}" \
      --data-urlencode "description@${BODY_FILE}" \
      "$api" | jq -r '.web_url')"
  fi
fi
if [[ -z "$pr_url" || "$pr_url" == "null" ]]; then
  echo "::error::pull request URL missing" >&2
  exit 1
fi
echo "Pull request: ${pr_url}"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'pr_url=%s\nbranch=%s\n' "$pr_url" "$selected" >> "$GITHUB_OUTPUT"
fi
