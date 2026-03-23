#!/usr/bin/env bash
# ── Push to GitHub ────────────────────────────────────────────────────────────
# Usage: ./scripts/push_to_github.sh your-github-username
#
# Prerequisites:
#   1. Install GitHub CLI: https://cli.github.com/
#   2. Authenticate:       gh auth login
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GITHUB_USERNAME="${1:-YOUR_USERNAME}"
REPO_NAME="openstack-vm-api"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 Publishing $REPO_NAME to GitHub..."

cd "$ROOT_DIR"

# Init git if needed
if [ ! -d ".git" ]; then
  git init
  git branch -M main
fi

# Stage and commit
git add -A
git commit -m "feat: OpenStack VM Lifecycle Management API

- FastAPI REST API with full VM CRUD
- Lifecycle actions: start/stop/reboot/suspend/resume/pause/resize
- Snapshot management
- Console URL generation
- VM resource metrics
- Mock OpenStack service (no cluster needed to run)
- Real OpenStack SDK integration stub
- 70 tests, 85% coverage
- Docker + docker-compose + Kubernetes manifests
- GitHub Actions CI pipeline
- Structured JSON logging" 2>/dev/null || echo "(nothing new to commit)"

# Create GitHub repo (requires gh CLI)
if command -v gh &>/dev/null; then
  echo "Creating GitHub repository..."
  gh repo create "$GITHUB_USERNAME/$REPO_NAME" \
    --public \
    --description "REST API for OpenStack VM lifecycle management — FastAPI · Python 3.11 · Docker" \
    --push \
    --source . \
    || echo "Repo may already exist, pushing to existing..."
  git remote set-url origin "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git" 2>/dev/null || true
  git push -u origin main
else
  echo "gh CLI not found. Create the repo manually, then run:"
  echo ""
  echo "  git remote add origin https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"
  echo "  git push -u origin main"
fi

echo ""
echo "✅ Done!"
echo "   Repo: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
echo "   Docs: http://localhost:8000/api/v1/docs  (after docker-compose up)"
