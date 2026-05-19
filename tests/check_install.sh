#!/usr/bin/env bash
# check_install.sh — verify install-agents.sh produces well-formed Claude Code
# subagent files.
#
# Runs the installer into a tempdir (so we don't touch the real
# Claude/.claude/agents/), then inspects each output: it must have frontmatter,
# `name` must match the filename, and `tools` must contain only real Claude Code
# tool names — never the portable capability vocabulary that lives in the source
# files.
#
# Exit 0 = clean, exit 1 = at least one check failed.

set -euo pipefail

SWE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$SWE_DIR/agents"
INSTALLER="$SWE_DIR/scripts/install-agents.sh"
TMP="$(mktemp -d -t swe-install-check.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# install-agents.sh resolves its destination relative to SWE_DIR's parent — to
# redirect it cleanly, we copy the script into a sandboxed layout where the
# "parent of SWE/" is the tempdir.
mkdir -p "$TMP/SWE/scripts" "$TMP/SWE/agents"
cp -R "$SRC_DIR"/. "$TMP/SWE/agents/"
cp "$INSTALLER" "$TMP/SWE/scripts/install-agents.sh"
chmod +x "$TMP/SWE/scripts/install-agents.sh"

"$TMP/SWE/scripts/install-agents.sh" >/dev/null

DST="$TMP/.claude/agents"
if [[ ! -d "$DST" ]]; then
  echo "FAIL: installer did not create $DST"
  exit 1
fi

# Portable capability tokens — must NOT appear in installed `tools:` line.
PORTABLE_RE='^(read|edit|shell|web|spawn)$'
# Allowed Claude Code tool names after translation.
ALLOWED_CC_TOOLS=(Read Edit Write Bash WebFetch WebSearch Task)

fails=0
checked=0
for f in "$DST"/*.md; do
  checked=$((checked + 1))
  base="$(basename "$f" .md)"

  # Extract frontmatter block.
  fm=$(awk '/^---$/{c++; next} c==1{print} c>=2{exit}' "$f")
  if [[ -z "$fm" ]]; then
    echo "  FAIL: $base: no frontmatter in installed file"
    fails=$((fails + 1)); continue
  fi

  name_line=$(echo "$fm" | grep -E '^name:' || true)
  tools_line=$(echo "$fm" | grep -E '^tools:' || true)
  if [[ -z "$name_line" ]]; then
    echo "  FAIL: $base: missing name in installed file"
    fails=$((fails + 1)); continue
  fi
  if [[ "${name_line#name:}" != " $base" ]] && [[ "${name_line#name: }" != "$base" ]]; then
    echo "  FAIL: $base: installed name field does not match filename ($name_line)"
    fails=$((fails + 1))
  fi

  if [[ -z "$tools_line" ]]; then
    echo "  WARN: $base: no tools field after install (all tools granted)"
    continue
  fi

  # Parse the tools list.
  tools_csv=$(echo "$tools_line" | sed -E 's/^tools:[[:space:]]*//; s/[][]//g')
  IFS=',' read -ra tool_arr <<<"$tools_csv"
  for raw in "${tool_arr[@]}"; do
    tool=$(echo "$raw" | tr -d '[:space:]"'"'")
    [[ -z "$tool" ]] && continue
    if [[ "$tool" =~ $PORTABLE_RE ]]; then
      echo "  FAIL: $base: installed tools still contains portable capability '$tool' — translation broke"
      fails=$((fails + 1))
      continue
    fi
    valid=0
    for allowed in "${ALLOWED_CC_TOOLS[@]}"; do
      if [[ "$tool" == "$allowed" ]]; then valid=1; break; fi
    done
    if [[ $valid -eq 0 ]]; then
      echo "  WARN: $base: unexpected tool '$tool' (not in allow-list, may still be valid)"
    fi
  done
done

if [[ $fails -gt 0 ]]; then
  echo "check_install: FAIL — $fails error(s) across $checked file(s)"
  exit 1
fi

echo "check_install: PASS — $checked file(s) translated cleanly"
