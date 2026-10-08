import io
import json
import os
import zipfile

from core import updater


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return zipfile.ZipFile(io.BytesIO(buf.getvalue()))


def test_overlay_copies_only_the_inner_folder_and_skips(tmp_path):
    zf = _zip({
        "Autono-main/README.md": "x",
        "Autono-main/Autono/manifest.json": "{}",
        "Autono-main/Autono/side-panel/a.js": "a",
        "Autono-main/Autono/node_modules/p/i.js": "n",
    })
    written = updater._overlay(zf, "Autono", str(tmp_path), skip=("node_modules",))
    assert written == 2
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "side-panel" / "a.js").exists()
    assert not (tmp_path / "node_modules").exists()
    assert not (tmp_path / "README.md").exists()


def test_overlay_never_writes_outside_the_folder(tmp_path):
    dest = tmp_path / "ext"
    dest.mkdir()
    zf = _zip({"r-main/Autono/../../evil.txt": "bad", "r-main/Autono/ok.txt": "ok"})
    updater._overlay(zf, "Autono", str(dest))
    assert (dest / "ok.txt").exists()
    assert not (tmp_path / "evil.txt").exists()


def test_extension_folder_comes_from_the_chrome_profile(tmp_path, monkeypatch):
    ext = tmp_path / "Autono"
    ext.mkdir()
    (ext / "manifest.json").write_text("{}")
    prefs = tmp_path / "Secure Preferences"
    prefs.write_text(json.dumps({"extensions": {"settings": {"abcdefgh": {"path": str(ext)}}}}))
    monkeypatch.setattr(updater, "_chrome_profiles", lambda: [str(prefs)])
    assert updater.find_extension_folder("abcdefgh") == os.path.abspath(str(ext))
    assert updater.find_extension_folder("zzzzzzzz") is None
    assert updater.find_extension_folder("../etc") is None
    assert updater.resolve_extension_folder("zzzzzzzz", str(ext)) == os.path.abspath(str(ext))


def test_zip_install_baseline_then_update_available(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "STATE_FILE", str(tmp_path / "updates.json"))
    monkeypatch.setattr(updater, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(updater, "_git_root", lambda p: None)
    shas = iter(["aaa", "aaa", "bbb"])
    monkeypatch.setattr(updater, "latest_sha", lambda repo, force=False: next(shas))
    first = updater._check("bridge", "o/r", str(tmp_path), True)
    assert first["update_available"] is False  # first look sets today's version as the baseline
    assert updater._check("bridge", "o/r", str(tmp_path), True)["update_available"] is False
    assert updater._check("bridge", "o/r", str(tmp_path), True)["update_available"] is True
