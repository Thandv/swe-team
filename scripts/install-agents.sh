#!/usr/bin/env bash
# install-agents.sh — install adapted SWE agents into Claude Code's discovery path.
#
# Reads each /Users/gokulpm/Claude/SWE/agents/<role>.md, translates the portable
# capability vocabulary (`read, edit, shell, web, spawn`) into concrete Claude Code
# tool names (`Read, Edit, Write, Bash, WebFetch, WebSearch, Task`), and writes the
# transformed copy to /Users/gokulpm/Claude/.claude/agents/<role>.md.
#
# The source files are the SDK-portable source of truth. This script is the
# Claude-Code-specific install step. Phase 2 (binary + SDK) does NOT use this
# script — it reads the source files directly.
#
# Usage:
#   scripts/install-agents.sh          # install all roles
#   scripts/install-agents.sh pm       # install just one role

set -euo pipefail

SWE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$SWE_DIR/agents"
DST_DIR="$(cd "$SWE_DIR/.." && pwd)/.claude/agents"

mkdir -p "$DST_DIR"

translate_one() {
  local role="$1"
  local src="$SRC_DIR/$role.md"
  local dst="$DST_DIR/$role.md"

  if [[ ! -f "$src" ]]; then
    echo "[install-agents] skip: $src not found" >&2
    return 1
  fi

  python3 - "$src" "$dst" <<'PY'
import re
import sys
from pathlib import Path

src_path, dst_path = Path(sys.argv[1]), Path(sys.argv[2])
text = src_path.read_text()

# Map portable capability tokens to Claude Code tool names.
CAP_TO_TOOLS = {
    "read":  ["Read"],
    "edit":  ["Edit", "Write"],
    "shell": ["Bash"],
    "web":   ["WebFetch", "WebSearch"],
    "spawn": ["Task"],
}

fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
if not fm_match:
    dst_path.write_text(text)
    sys.exit(0)

frontmatter = fm_match.group(1)
body = text[fm_match.end():]

def translate_tools(match):
    raw = match.group(1).strip()
    # Accept "[read, edit]" or "read, edit"
    raw = raw.strip("[]")
    caps = [c.strip().strip("'\"") for c in raw.split(",") if c.strip()]
    tools = []
    for cap in caps:
        if cap in CAP_TO_TOOLS:
            for t in CAP_TO_TOOLS[cap]:
                if t not in tools:
                    tools.append(t)
        else:
            # Unknown capability — pass through verbatim, in case upstream had a real tool name.
            if cap not in tools:
                tools.append(cap)
    return "tools: " + ", ".join(tools)

new_fm = re.sub(r"^tools:\s*(.+)$", translate_tools, frontmatter, count=1, flags=re.MULTILINE)
dst_path.write_text(f"---\n{new_fm}\n---\n{body}")
PY

  echo "[install-agents] installed $role → $dst"
}

if [[ $# -gt 0 ]]; then
  translate_one "$1"
else
  for src in "$SRC_DIR"/*.md; do
    [[ -f "$src" ]] || continue
    role="$(basename "$src" .md)"
    translate_one "$role"
  done
fi

echo "[install-agents] done. Agents available to Claude Code at $DST_DIR"
