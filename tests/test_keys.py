import json
import sys

from wuzapi_mcp.keys import main


def test_create_revoke_recreate_without_printing_secret(tmp_path, monkeypatch, capsys):
    file = tmp_path / "clients.json"

    def call(action):
        monkeypatch.setattr(sys, "argv", ["keys", action, "composio", "--file", str(file)])
        main()

    call("create")
    secret = (tmp_path / "composio.key").read_text().strip()
    assert secret not in capsys.readouterr().out
    assert secret not in file.read_text()
    assert file.stat().st_mode & 0o077 == 0
    call("revoke")
    assert json.loads(file.read_text()) == []
    assert not (tmp_path / "composio.key").exists()
    call("create")
    assert (tmp_path / "composio.key").read_text().strip() != secret
