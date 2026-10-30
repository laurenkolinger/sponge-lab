#!/bin/bash
# Download everything Sponge Lab runs on into the app's own folder: Python, OpenCV for
# tracking, and ffmpeg. Nothing else on the computer changes, and no administrator
# password is needed. The app runs this on its first open, because macOS gives package
# installers no network. A failure stops here and leaves the reason in the log.
set -euo pipefail

APP_NAME="Sponge Lab by VICAR"
UV_VERSION="0.13.6"
PYTHON_VERSION="3.14"
HERE="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="$HOME/Library/Application Support/$APP_NAME"
RUNTIME="$SUPPORT/runtime"
LOG="$HOME/Library/Logs/$APP_NAME install.log"

# Tell the person which step is running.
step() {
  echo "$1"
  osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title "Setting up Sponge Lab"' -e 'end run' "$1" > /dev/null 2>&1 || true
}

mkdir -p "$SUPPORT" "$(dirname "$LOG")"
exec > "$LOG" 2>&1
echo "Installing $APP_NAME on $(date)"

case "$(uname -m)" in
  arm64) UV_ARCH="aarch64" ;;
  x86_64) UV_ARCH="x86_64" ;;
  *) echo "This Mac's processor, $(uname -m), is not supported."; exit 1 ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
step "Step 1 of 4: downloading the setup tool"
curl -fsSL --retry 3 --connect-timeout 20 --max-time 300 "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$UV_ARCH-apple-darwin.tar.gz" \
  | tar -xz -C "$WORK" --strip-components=1
export UV_PYTHON_INSTALL_DIR="$SUPPORT/python"
export UV_CACHE_DIR="$WORK/cache"
# Use a Python 3.14 already on the computer, and download one only if there is none.
export UV_PYTHON_PREFERENCE="system"
# An app opened from the Dock searches only the system folders, so name the usual installs.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/$PYTHON_VERSION/bin:$PATH"

step "Step 2 of 4: finding Python"
rm -rf "$RUNTIME"
"$WORK/uv" venv --python "$PYTHON_VERSION" "$RUNTIME"

step "Step 3 of 4: downloading OpenCV"
"$WORK/uv" pip install --python "$RUNTIME/bin/python" -r "$HERE/app/requirements.txt"

step "Step 4 of 4: downloading ffmpeg"
mkdir -p "$RUNTIME/ffmpeg"
"$RUNTIME/bin/python" - "$RUNTIME/ffmpeg" <<'PY'
import shutil
import sys

from static_ffmpeg import run

ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
for tool in (ffmpeg, ffprobe):
    shutil.copy2(tool, sys.argv[1])
PY

echo "Checking the result"
"$RUNTIME/bin/python" -c 'import cv2, numpy; cv2.TrackerCSRT_create; print("OpenCV", cv2.__version__, "numpy", numpy.__version__)'
"$RUNTIME/ffmpeg/ffmpeg" -version | head -1
"$RUNTIME/ffmpeg/ffprobe" -version | head -1

# The app treats a runtime without this copy of the requirements as unfinished and sets up again.
cp "$HERE/app/requirements.txt" "$RUNTIME/.complete"
echo "Installed."
