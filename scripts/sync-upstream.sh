#!/usr/bin/env bash
# sync-upstream.sh — refresh agents/upstream/ snapshots and diff against our adapted versions.
#
# Usage: scripts/sync-upstream.sh [role]
#   With no args, syncs every role in UPSTREAM.md.
#   With a role name (e.g. "pm"), syncs only that one.
#
# This script is a stub. It will be filled in once we lock the source repos in UPSTREAM.md.
# Until then it prints what it WOULD do.

set -euo pipefail

SWE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="$SWE_DIR/agents/upstream"
AGENTS_DIR="$SWE_DIR/agents"

echo "[sync-upstream] SWE root: $SWE_DIR"
echo "[sync-upstream] This is a stub. Once UPSTREAM.md has source URLs, this script will:"
echo "  1. Fetch each source file via curl/gh into $UPSTREAM_DIR/<role>.upstream.md"
echo "  2. diff $UPSTREAM_DIR/<role>.upstream.md $AGENTS_DIR/<role>.md"
echo "  3. Print a per-role summary of upstream changes since last sync"
echo
echo "Add sources to UPSTREAM.md and replace this stub with the real implementation."
