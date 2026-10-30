#!/bin/bash
# Start Sponge Lab by VICAR and open it in the browser. macOS stops any process an app
# leaves behind when the app exits, so launchd runs the server as a service. A server
# older than the installed code is restarted.
APP_NAME="Sponge Lab by VICAR"
LABEL="org.vicar.sponge-lab.server"
PORT="8771"
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HERE/../Resources/app"
SUPPORT="$HOME/Library/Application Support/$APP_NAME"
PYTHON="$SUPPORT/runtime/bin/python"
TOOLS="$SUPPORT/runtime/ffmpeg"
LOG="$SUPPORT/data/server.log"
DOMAIN="gui/$(id -u)"
SERVICE="$DOMAIN/$LABEL"
AGENT_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
URL="http://127.0.0.1:$PORT/"
START_WAIT_TENTHS=300
STOP_WAIT_TENTHS=50

# Show one alert. The message travels as an argument, so a quote in a path cannot break it.
alert() {
  osascript -e 'on run argv' -e 'display alert (item 1 of argv) message (item 2 of argv)' -e 'end run' "$APP_NAME did not start" "$1" > /dev/null
}

# True when the server answers its health check.
healthy() { curl -s -m 2 "${URL}api/health" | grep -q '"ok": true'; }

# The process listening on the port, or nothing.
server_pid() { lsof -t -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1; }

# The version of the running server, and the version of this app.
server_version() { curl -s -m 2 "${URL}api/health" | sed -n 's/.*"version": *"\([^"]*\)".*/\1/p'; }
app_version() { /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$HERE/../Info.plist" 2>/dev/null; }

# True when the runtime finished setup for this version's requirements.
runtime_ready() { [ -x "$PYTHON" ] && cmp -s "$PROJECT/requirements.txt" "$SUPPORT/runtime/.complete"; }

if ! runtime_ready; then
  osascript -e 'display dialog "Sponge Lab needs Python, OpenCV, and ffmpeg. It will download about 400 MB into its own folder and tell you each step. This takes a few minutes." with title "Set up Sponge Lab" buttons {"Cancel", "Download"} default button "Download"' > /dev/null || exit 0
  # Setup replaces the Python a running server uses, so the server stops first.
  launchctl bootout "$SERVICE" > /dev/null 2>&1
  if ! /bin/bash "$HERE/../Resources/setup.sh"; then
    alert "Setup could not finish. Check your internet connection and open Sponge Lab again. The reason is at the end of $HOME/Library/Logs/$APP_NAME install.log."
    exit 1
  fi
fi
mkdir -p "$SUPPORT/data" "$SUPPORT/cache" "$(dirname "$AGENT_PLIST")"

# Write the service definition. It starts only when asked and stays stopped when stopped.
"$PYTHON" - "$AGENT_PLIST" "$LABEL" "$PROJECT" "$SUPPORT" "$PYTHON" "$TOOLS" "$LOG" <<'PY'
import os
import plistlib
import sys

path, label, project, support, python, tools, log = sys.argv[1:]
project = os.path.realpath(project)
service = {
    "Label": label,
    "ProgramArguments": [python, f"{project}/screener.py", "--no-browser"],
    "WorkingDirectory": project,
    "EnvironmentVariables": {
        "PATH": f"{tools}:/usr/bin:/bin:/usr/sbin:/sbin",
        "SCREENER_DATA_DIR": f"{support}/data",
        "SCREENER_CACHE_DIR": f"{support}/cache",
        "SCREENER_EXPORT_ROOT": os.path.expanduser("~/Documents/Sponge Lab Exports"),
        "SCREENER_TRACK_PYTHON": python,
    },
    "StandardOutPath": log,
    "StandardErrorPath": log,
    "ProcessType": "Interactive",
}
with open(path, "wb") as handle:
    plistlib.dump(service, handle)
PY

# A server from another version stops, so the new code runs.
pid="$(server_pid)"
if [ -n "$pid" ] && healthy && [ "$(server_version)" != "$(app_version)" ]; then
  kill "$pid"
  for _ in $(seq 1 "$STOP_WAIT_TENTHS"); do [ -z "$(server_pid)" ] && break; sleep 0.1; done
fi
if ! healthy; then
  # launchd keeps a loaded definition in memory, so reload it to read the file written above.
  launchctl bootout "$SERVICE" >> "$LOG" 2>&1
  launchctl bootstrap "$DOMAIN" "$AGENT_PLIST" >> "$LOG" 2>&1
  launchctl kickstart "$SERVICE" >> "$LOG" 2>&1
  for _ in $(seq 1 "$START_WAIT_TENTHS"); do healthy && break; sleep 0.1; done
  if ! healthy; then
    alert "The reason is at the end of $LOG."
    exit 1
  fi
fi
open -a "Google Chrome" "$URL" 2>/dev/null || open "$URL"
