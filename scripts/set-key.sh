#!/usr/bin/env bash
# set-key.sh — paste a key into ~/.config/swe-team/keys.env without echoing it.
#
# Usage:
#   scripts/set-key.sh ANTHROPIC_API_KEY        # prompts you to paste, hidden
#   scripts/set-key.sh GEMINI_API_KEY
#
# What this script does (and doesn't):
#   - Reads the value silently via `read -rs`. Key never appears on screen
#     and never appears in shell history because we don't put it on the
#     command line.
#   - Writes (or replaces) the named key in ~/.config/swe-team/keys.env,
#     with mode 0600 (only you can read it).
#   - Does NOT log the key anywhere. The script's stdout only mentions
#     the key NAME and the file path.

set -euo pipefail

NAME="${1:-}"
if [[ -z "$NAME" ]]; then
  echo "usage: $0 <KEY_NAME>" >&2
  echo "       e.g. $0 ANTHROPIC_API_KEY" >&2
  echo "       e.g. $0 GEMINI_API_KEY" >&2
  exit 2
fi

# Validate key name shape — only the kind of names a real env var would have.
if [[ ! "$NAME" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
  echo "error: '$NAME' doesn't look like an env-var name (need UPPER_SNAKE)" >&2
  exit 2
fi

DIR="$HOME/.config/swe-team"
FILE="$DIR/keys.env"
mkdir -p "$DIR"
chmod 700 "$DIR"
touch "$FILE"
chmod 600 "$FILE"

# Prompt for the key with silent input. -r prevents backslash interpretation.
printf "paste the value for %s (input hidden, press enter when done): " "$NAME" >&2
read -rs VALUE
printf "\n" >&2

if [[ -z "$VALUE" ]]; then
  echo "error: empty value, nothing written" >&2
  exit 1
fi

# Replace any existing line for this key, or append if missing.
# Use python so we don't need to worry about sed dialect differences (BSD vs GNU).
python3 - "$FILE" "$NAME" "$VALUE" <<'PY'
import sys
from pathlib import Path

path, name, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
existing = path.read_text().splitlines() if path.is_file() else []
out_lines = []
replaced = False
for line in existing:
    stripped = line.strip()
    if "=" in stripped and not stripped.startswith("#"):
        k, _, _ = stripped.partition("=")
        if k.strip() == name:
            out_lines.append(f"{name}={value}")
            replaced = True
            continue
    out_lines.append(line)
if not replaced:
    out_lines.append(f"{name}={value}")
# Trailing newline.
path.write_text("\n".join(out_lines).rstrip() + "\n")
PY

# Re-apply tight perms in case the python write changed anything.
chmod 600 "$FILE"

# Don't echo the key. Show only enough metadata to confirm success.
LEN=${#VALUE}
unset VALUE
echo "wrote $NAME ($LEN chars) to $FILE"
echo "file mode: $(stat -f '%Lp' "$FILE" 2>/dev/null || stat -c '%a' "$FILE")"
echo
echo "the driver will pick this up automatically on its next run."
echo "to verify without running the team:"
echo "  grep -c '^$NAME=' '$FILE'    # should print 1"
