"""Tests for the Mac app launcher and the installer scripts.

The launcher runs for real in a temporary home folder, with every command that would
touch the Mac replaced by a stub that records its arguments.
"""

import os
import plistlib
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LABEL = "org.vicar.sponge-lab.server"
APP_NAME = "Sponge Lab by VICAR"

STUBS = {
    "launchctl": r"""
echo "launchctl $*" >> "$STUB_STATE/calls.log"
case "$1" in
  print) [ -e "$STUB_STATE/loaded" ] ;;
  bootstrap)
    if [ -e "$STUB_STATE/bootstrap_fails" ]; then echo "Bootstrap failed: 5" >&2; exit 5; fi
    touch "$STUB_STATE/loaded" ;;
  kickstart)
    [ -e "$STUB_STATE/loaded" ] || exit 113
    rm -f "$STUB_STATE/pid"
    [ -e "$STUB_STATE/server_never_answers" ] || touch "$STUB_STATE/healthy" ;;
  bootout) rm -f "$STUB_STATE/loaded" ;;
esac
""",
    "curl": r"""[ -e "$STUB_STATE/healthy" ] || exit 7
[ -z "$(cat "$STUB_STATE/pid" 2>/dev/null)" ] || kill -0 "$(cat "$STUB_STATE/pid")" 2>/dev/null || exit 7
echo "{\"ok\": true, \"version\": \"$(cat "$STUB_STATE/version" 2>/dev/null || echo 1.0.0)\"}"
""",
    "lsof": r"""if [ -e "$STUB_STATE/pid" ] && kill -0 "$(cat "$STUB_STATE/pid")" 2>/dev/null; then cat "$STUB_STATE/pid"; fi""",
    "open": r"""echo "open $*" >> "$STUB_STATE/calls.log" """,
    "osascript": r"""echo "osascript $*" >> "$STUB_STATE/calls.log" """,
    "sleep": "true",
}


class Rig:
    """An installed copy of the launcher in a temporary home folder."""

    def __init__(self, base: Path, home_name: str = "home") -> None:
        """Lay out the app and the stubs.

        Args:
            base: An empty temporary folder.
            home_name: The name of the home folder.
        """
        self.home = base / home_name
        self.state = base / "state"
        self.bin = base / "bin"
        self.state.mkdir()
        self.bin.mkdir()
        contents = self.home / "Applications" / f"{APP_NAME}.app" / "Contents"
        (contents / "MacOS").mkdir(parents=True)
        (contents / "Resources" / "app").mkdir(parents=True)
        self.launcher = contents / "MacOS" / "launch"
        shutil.copy(ROOT / "packaging" / "launch.sh", self.launcher)
        with (contents / "Info.plist").open("wb") as handle:
            plistlib.dump({"CFBundleShortVersionString": "1.0.0"}, handle)
        self.requirements = contents / "Resources" / "app" / "requirements.txt"
        self.requirements.write_text("numpy==1\n")
        self.launcher.chmod(self.launcher.stat().st_mode | stat.S_IEXEC)
        self.support = self.home / "Library" / "Application Support" / APP_NAME
        self.plist_path = self.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        for name, body in STUBS.items():
            path = self.bin / name
            path.write_text("#!/bin/bash\n" + body + "\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def add_runtime(self) -> None:
        """Link this test's Python in as the runtime the installer would have downloaded."""
        python = self.support / "runtime" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        shutil.copy(self.requirements, self.support / "runtime" / ".complete")

    def launch(self) -> subprocess.CompletedProcess:
        """Run the launcher, as a click on the Dock icon does."""
        env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}", "STUB_STATE": str(self.state)}
        return subprocess.run([str(self.launcher)], env=env, capture_output=True, text=True, timeout=120)

    def calls(self) -> list:
        """Return the recorded stub calls."""
        path = self.state / "calls.log"
        return path.read_text().splitlines() if path.exists() else []

    def plist(self) -> dict:
        """Read the service definition."""
        with self.plist_path.open("rb") as handle:
            return plistlib.load(handle)


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    """Return a rig with its runtime in place."""
    made = Rig(tmp_path)
    made.add_runtime()
    return made


def test_first_click_loads_starts_and_opens_the_browser(rig: Rig):
    result = rig.launch()
    assert result.returncode == 0, result.stderr
    calls = rig.calls()
    service = f"gui/{os.getuid()}/{LABEL}"
    assert f"launchctl bootstrap gui/{os.getuid()} {rig.plist_path}" in calls
    assert f"launchctl kickstart {service}" in calls
    assert calls[-1] == "open -a Google Chrome http://127.0.0.1:8771/"


def test_service_keeps_everything_in_the_app_folders(rig: Rig):
    rig.launch()
    plist = rig.plist()
    env = plist["EnvironmentVariables"]
    assert plist["ProgramArguments"][0] == str(rig.support / "runtime" / "bin" / "python")
    assert plist["ProgramArguments"][1:] == [str(Path(plist["WorkingDirectory"]) / "screener.py"), "--no-browser"]
    assert env["SCREENER_DATA_DIR"] == str(rig.support / "data")
    assert env["SCREENER_CACHE_DIR"] == str(rig.support / "cache")
    assert env["SCREENER_TRACK_PYTHON"] == str(rig.support / "runtime" / "bin" / "python")
    assert env["PATH"].startswith(str(rig.support / "runtime" / "ffmpeg"))


def test_service_starts_only_when_asked(rig: Rig):
    rig.launch()
    plist = rig.plist()
    assert plist.get("RunAtLoad", False) is False and plist.get("KeepAlive", False) is False


def write_setup(rig: Rig, body: str) -> None:
    """Put a stand-in for the setup script next to the app's resources."""
    (rig.launcher.parent.parent / "Resources" / "setup.sh").write_text("#!/bin/bash\n" + body + "\n")


def test_first_open_runs_setup_then_starts(tmp_path: Path):
    made = Rig(tmp_path)
    write_setup(made, f'mkdir -p "{made.support}/runtime/bin"; ln -s "{sys.executable}" "{made.support}/runtime/bin/python"; cp "{made.requirements}" "{made.support}/runtime/.complete"')
    result = made.launch()
    assert result.returncode == 0, result.stderr
    assert any("display dialog" in call for call in made.calls())
    assert made.calls()[-1].startswith("open -a Google Chrome")


def test_failed_setup_says_so_and_starts_nothing(tmp_path: Path):
    made = Rig(tmp_path)
    write_setup(made, "exit 1")
    assert made.launch().returncode == 1
    assert any("Setup could not finish" in call for call in made.calls())
    assert not [call for call in made.calls() if "bootstrap" in call or "kickstart" in call]


def test_cancelled_setup_quits_quietly(tmp_path: Path):
    made = Rig(tmp_path)
    (made.bin / "osascript").write_text("#!/bin/bash\nexit 1\n")
    write_setup(made, 'touch "$HOME/setup_ran"')
    assert made.launch().returncode == 0
    assert not (made.home / "setup_ran").exists()


def test_unfinished_runtime_sets_up_again(tmp_path: Path):
    made = Rig(tmp_path)
    made.add_runtime()
    (made.support / "runtime" / ".complete").unlink()
    write_setup(made, 'touch "$HOME/setup_ran"; exit 1')
    assert made.launch().returncode == 1
    assert (made.home / "setup_ran").exists()


def test_server_that_never_answers_shows_an_alert(rig: Rig):
    (rig.state / "server_never_answers").touch()
    assert rig.launch().returncode == 1
    calls = rig.calls()
    assert any(call.startswith("osascript") and "server.log" in call for call in calls)
    assert not [call for call in calls if call.startswith("open")]


def test_refusal_from_macos_lands_in_the_log(rig: Rig):
    (rig.state / "bootstrap_fails").touch()
    assert rig.launch().returncode == 1
    assert "Bootstrap failed: 5" in (rig.support / "data" / "server.log").read_text()


def test_running_server_only_opens_the_browser(rig: Rig):
    (rig.state / "healthy").touch()
    (rig.state / "loaded").touch()
    assert rig.launch().returncode == 0
    assert [call for call in rig.calls() if "kickstart" in call or "bootstrap" in call] == []


def test_awkward_home_folder_survives(tmp_path: Path):
    made = Rig(tmp_path, "Reef & Video's $HOME|Lab (2026)")
    made.add_runtime()
    result = made.launch()
    assert result.returncode == 0, result.stderr
    assert made.plist()["EnvironmentVariables"]["SCREENER_DATA_DIR"] == str(made.support / "data")


def stand_in_server() -> int:
    """Start a process with no parent in this test, so it disappears as soon as it is killed."""
    command = "/bin/sleep 60 >/dev/null 2>&1 & echo $!"
    return int(subprocess.check_output(["/bin/sh", "-c", command], text=True).strip())


def test_server_from_another_version_is_replaced(rig: Rig):
    server = stand_in_server()
    (rig.state / "pid").write_text(str(server))
    (rig.state / "healthy").touch()
    (rig.state / "version").write_text("0.9.0")
    try:
        assert rig.launch().returncode == 0
        with pytest.raises(ProcessLookupError):
            os.kill(server, 0)
    finally:
        try:
            os.kill(server, signal.SIGKILL)
        except ProcessLookupError:
            pass
    assert any(call.startswith("launchctl kickstart") for call in rig.calls())


def test_server_of_this_version_keeps_running(rig: Rig):
    server = stand_in_server()
    (rig.state / "pid").write_text(str(server))
    (rig.state / "healthy").touch()
    try:
        assert rig.launch().returncode == 0
        os.kill(server, 0)
    finally:
        os.kill(server, signal.SIGKILL)
    assert not any("kickstart" in call for call in rig.calls())


def test_a_start_reloads_the_definition_launchd_holds(rig: Rig):
    (rig.state / "loaded").touch()
    assert rig.launch().returncode == 0
    calls = rig.calls()
    order = [call.split()[1] for call in calls if call.startswith("launchctl")]
    assert order == ["bootout", "bootstrap", "kickstart"]


def test_python_that_was_removed_sets_up_again(tmp_path: Path):
    made = Rig(tmp_path)
    python = made.support / "runtime" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(tmp_path / "python-that-is-gone")
    shutil.copy(made.requirements, made.support / "runtime" / ".complete")
    write_setup(made, 'touch "$HOME/setup_ran"; exit 1')
    assert made.launch().returncode == 1
    assert (made.home / "setup_ran").exists()


def test_new_requirements_set_up_again(rig: Rig):
    rig.requirements.write_text("numpy==2\n")
    write_setup(rig, 'touch "$HOME/setup_ran"; exit 1')
    assert rig.launch().returncode == 1
    assert (rig.home / "setup_ran").exists()


@pytest.mark.parametrize("script", ["packaging/launch.sh", "packaging/scripts/postinstall", "packaging/setup.sh", "packaging/build_pkg.sh"])
def test_shell_scripts_parse_under_the_system_bash(script: str):
    assert subprocess.run(["/bin/bash", "-n", str(ROOT / script)]).returncode == 0


def test_setup_looks_for_python_where_a_dock_app_cannot_see_it():
    text = (ROOT / "packaging" / "setup.sh").read_text()
    assert 'UV_PYTHON_PREFERENCE="system"' in text and "/opt/homebrew/bin" in text


def test_requirements_pin_every_download():
    lines = [line for line in (ROOT / "requirements.txt").read_text().splitlines() if line.strip()]
    assert lines and all("==" in line for line in lines)
    assert any(line.startswith("opencv-contrib-python-headless==") for line in lines)


def test_project_runs_without_the_private_photos():
    guide = (ROOT / "config" / "guide_text.json").read_text(encoding="utf-8")
    assert '"images": []' in guide and ".jpeg" not in guide
