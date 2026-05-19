#!/usr/bin/env bash
# build-sidecar.sh — PyInstaller-build the driver into a single executable
# named for Tauri's sidecar convention.
#
# Tauri 2 looks up sidecars as `<basename>-<rust-target-triple>` next to the
# Cargo manifest. We emit ours into ../src-tauri/binaries/ with the triple in
# the filename so tauri.conf.json's `externalBin` can reference it as
# "binaries/driver" without target-specific entries.
#
# Run locally:
#   cd binary/driver
#   ./build-sidecar.sh
#
# Run in CI: see .github/workflows/release.yml.

set -euo pipefail

cd "$(dirname "$0")"

# Resolve the Tauri triple. Prefer the env override (CI sets it per matrix
# leg) and fall back to rustc, then to uname heuristics.
TRIPLE="${TAURI_TARGET:-}"
if [[ -z "${TRIPLE}" ]] && command -v rustc >/dev/null 2>&1; then
  TRIPLE="$(rustc -vV | awk '/^host:/ {print $2}')"
fi
if [[ -z "${TRIPLE}" ]]; then
  case "$(uname -s)" in
    Darwin)
      case "$(uname -m)" in
        arm64) TRIPLE="aarch64-apple-darwin" ;;
        x86_64) TRIPLE="x86_64-apple-darwin" ;;
      esac
      ;;
    Linux)
      case "$(uname -m)" in
        x86_64) TRIPLE="x86_64-unknown-linux-gnu" ;;
        aarch64) TRIPLE="aarch64-unknown-linux-gnu" ;;
      esac
      ;;
    MINGW*|MSYS*|CYGWIN*)
      TRIPLE="x86_64-pc-windows-msvc"
      ;;
  esac
fi
if [[ -z "${TRIPLE}" ]]; then
  echo "could not determine Rust target triple (set TAURI_TARGET)" >&2
  exit 1
fi

OUT_DIR="$(cd ../src-tauri && pwd)/binaries"
mkdir -p "${OUT_DIR}"

# Install build deps. PyInstaller needs to bundle the anthropic SDK.
python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller anthropic

# On Windows, PyInstaller will emit driver-<triple>.exe automatically.
# On Unix, the filename has no extension.
NAME="driver-${TRIPLE}"

echo "Building sidecar: ${OUT_DIR}/${NAME}"
python3 -m PyInstaller \
  --onefile \
  --name "${NAME}" \
  --distpath "${OUT_DIR}" \
  --workpath /tmp/sidecar-build-work \
  --specpath /tmp/sidecar-build-spec \
  --collect-all anthropic \
  --noconfirm \
  orchestrator_driver.py

# Tauri expects executable permissions on Unix.
if [[ -f "${OUT_DIR}/${NAME}" ]]; then
  chmod +x "${OUT_DIR}/${NAME}"
fi

ls -la "${OUT_DIR}/"
echo "sidecar built: ${OUT_DIR}/${NAME}"
