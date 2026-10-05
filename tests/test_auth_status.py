"""Unit tests for provider login detection (pure parsing, no CLIs required)."""

import base64
import json

from core.auth_status import (
    ProviderStatus,
    parse_claude_status,
    read_antigravity_login,
    read_codex_login,
)


def _jwt(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"h.{body}.s"


def test_claude_logged_in():
    raw = json.dumps({"loggedIn": True, "email": "a@b.co", "orgName": "Org"})
    assert parse_claude_status(raw) == (True, "a@b.co")


def test_claude_logged_out_and_garbage():
    assert parse_claude_status(json.dumps({"loggedIn": False})) == (False, "")
    assert parse_claude_status("not json") == (False, "")
    assert parse_claude_status("") == (False, "")


def test_claude_tolerates_leading_noise():
    raw = 'warning...\n{"loggedIn": true, "email": "x@y.z"}\n'
    assert parse_claude_status(raw) == (True, "x@y.z")


def test_antigravity_logged_in(tmp_path):
    (tmp_path / "oauth_creds.json").write_text(json.dumps({"refresh_token": "r"}))
    (tmp_path / "google_accounts.json").write_text(json.dumps({"active": "me@g.com", "old": []}))
    assert read_antigravity_login(tmp_path) == (True, "me@g.com")


def test_antigravity_no_creds(tmp_path):
    assert read_antigravity_login(tmp_path) == (False, "")


def test_antigravity_logged_out_account(tmp_path):
    (tmp_path / "oauth_creds.json").write_text(json.dumps({"refresh_token": "r"}))
    (tmp_path / "google_accounts.json").write_text(json.dumps({"active": "", "old": ["a"]}))
    assert read_antigravity_login(tmp_path)[0] is False


def test_codex_chatgpt_tokens(tmp_path):
    tokens = {"access_token": "t", "id_token": _jwt({"email": "c@d.ef"})}
    (tmp_path / "auth.json").write_text(json.dumps({"tokens": tokens}))
    assert read_codex_login(tmp_path) == (True, "c@d.ef")


def test_codex_api_key(tmp_path):
    (tmp_path / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": "sk-x"}))
    assert read_codex_login(tmp_path) == (True, "API key")


def test_codex_missing_or_empty(tmp_path):
    assert read_codex_login(tmp_path) == (False, "")
    (tmp_path / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": None, "tokens": None}))
    assert read_codex_login(tmp_path) == (False, "")


def test_active_requires_install_and_login():
    assert ProviderStatus("codex", installed=False, logged_in=True).active is False
    assert ProviderStatus("codex", installed=True, logged_in=False).active is False
    assert ProviderStatus("codex", installed=True, logged_in=True).active is True
