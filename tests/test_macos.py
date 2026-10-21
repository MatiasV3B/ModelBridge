"""macOS port: the helpers that do not need a real Mac."""

import plistlib
import shlex

from core import macos


def test_login_shell_command_quotes_paths_with_spaces():
    cmd = macos.login_shell_command("/Users/me/My Tools/claude", "auth", "login", auto_close=True)
    assert shlex.split(cmd.split(";")[0]) == ["/Users/me/My Tools/claude", "auth", "login"]
    assert cmd.endswith("exit")


def test_applescript_string_escapes_quotes():
    assert macos._applescript_str('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'


def test_find_bin_looks_in_user_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(macos.Path, "home", lambda: tmp_path)
    folder = tmp_path / ".local" / "bin"
    folder.mkdir(parents=True)
    exe = folder / "agy"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    assert macos.find_bin("agy") == str(exe)
    assert macos.find_bin("nope") is None


def test_login_item_writes_a_headless_launch_agent(tmp_path, monkeypatch):
    agent = tmp_path / "LaunchAgents" / "bridge.plist"
    monkeypatch.setattr(macos, "LAUNCH_AGENT", agent)
    monkeypatch.setattr(macos.subprocess, "run", lambda *a, **k: None)
    macos.set_login_item(True)
    assert macos.is_login_item_enabled()
    data = plistlib.loads(agent.read_bytes())
    assert data["ProgramArguments"][-2:] == [str(macos.ROOT / "main.py"), "--headless"]
    assert data["RunAtLoad"] is True
    macos.set_login_item(False)
    assert not macos.is_login_item_enabled()
