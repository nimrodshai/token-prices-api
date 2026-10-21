#!/usr/bin/env bash
# Archive the public snapshot during CI. Weekly data commits also keep this
# public repository active so GitHub does not disable its scheduled workflow.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${GITHUB_REF:-}" != "refs/heads/main" ]]; then
  echo "Snapshot commits are only supported in GitHub Actions on main." >&2
  exit 1
fi
if [[ ! -f _site/api/openai/prices.json ]]; then
  echo "Build the static API before archiving its snapshot." >&2
  exit 1
fi
if ! git diff --cached --quiet; then
  echo "Refusing to commit while unrelated staged changes exist." >&2
  exit 1
fi

echo "Archiving the published pricing snapshot in data/openai-prices.json"
mkdir -p data
cp _site/api/openai/prices.json data/openai-prices.json
git add -- data/openai-prices.json
if git diff --cached --quiet; then
  echo "The archived snapshot is already current."
  exit 0
fi
git -c user.name='github-actions[bot]' \
    -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
    commit -m 'Refresh public token pricing snapshot'
git push origin HEAD:main
