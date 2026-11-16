import json
import sys
from pathlib import Path

import pytest

from wuzapi_mcp.keys import main
from wuzapi_mcp.auth import APIKeys


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


@pytest.fixture
def rotation(tmp_path, monkeypatch):
    file = tmp_path / "clients.json"

    def call(action, *options, name="composio"):
        monkeypatch.setattr(sys, "argv", ["keys", action, name, "--file", str(file), *options])
        main()

    call("create", "--scopes", "read", "--instances", "one")
    return file, call


async def test_rotation_overlap_preserves_grants_and_needs_client_migration(rotation, capsys):
    file, call = rotation
    old = file.with_name("composio.key").read_text().strip()
    call("rotate-prepare", "--scopes", "admin", "--instances", "*")
    pending = file.with_name("composio-next.key")
    new = pending.read_text().strip()
    verifier = APIKeys(file, "http://localhost:8082")
    assert await verifier.verify_token(old)
    access = await verifier.verify_token(new)
    assert access.scopes == ["read"] and access.claims["instances"] == ["one"]
    assert pending.stat().st_mode & 0o077 == 0
    with pytest.raises(SystemExit):
        call("rotate-finish")
    assert await verifier.verify_token(old)
    with pytest.raises(SystemExit):
        call("rotate-prepare")
    call("rotate-finish", "--client-updated")
    assert await verifier.verify_token(old) is None
    assert (await verifier.verify_token(new)).client_id == "composio"
    assert file.with_name("composio.key").read_text().strip() == new
    assert not pending.exists()
    output = capsys.readouterr()
    assert old not in output.out + output.err and new not in output.out + output.err


async def test_rotation_cancel_and_revoke_do_not_leave_active_transition(rotation):
    file, call = rotation
    old = file.with_name("composio.key").read_text().strip()
    call("create", name="other")
    call("rotate-prepare")
    new = file.with_name("composio-next.key").read_text().strip()
    verifier = APIKeys(file, "http://localhost:8082")
    call("rotate-cancel")
    assert await verifier.verify_token(old)
    assert await verifier.verify_token(new) is None
    call("rotate-prepare")
    new = file.with_name("composio-next.key").read_text().strip()
    call("revoke")
    assert await verifier.verify_token(old) is None
    assert await verifier.verify_token(new) is None
    assert not file.with_name("composio-next.key").exists()
    assert (await verifier.verify_token(file.with_name("other.key").read_text().strip())).client_id == "other"


async def test_finish_can_resume_after_registry_commit(rotation, monkeypatch):
    file, call = rotation
    call("rotate-prepare")
    pending = file.with_name("composio-next.key")
    old = file.with_name("composio.key").read_text().strip()
    new = pending.read_text().strip()
    replace = Path.replace

    def interrupted(path, target):
        if path == pending:
            raise OSError("simulated interruption")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", interrupted)
    with pytest.raises(OSError, match="simulated"):
        call("rotate-finish", "--client-updated")
    verifier = APIKeys(file, "http://localhost:8082")
    assert await verifier.verify_token(new)
    assert await verifier.verify_token(old) is None
    with pytest.raises(SystemExit):
        call("rotate-cancel")
    monkeypatch.setattr(Path, "replace", replace)
    call("rotate-finish", "--client-updated")
    assert not pending.exists()
    assert file.with_name("composio.key").read_text().strip() == new


def test_prepare_rejects_missing_client_and_unrelated_name_collision(rotation):
    file, call = rotation
    with pytest.raises(SystemExit):
        call("rotate-prepare", name="missing")
    call("create", name="composio-next")
    other = file.with_name("composio-next.key").read_bytes()
    with pytest.raises(SystemExit):
        call("rotate-prepare")
    call("revoke")
    assert file.with_name("composio-next.key").read_bytes() == other


def test_finish_rejects_changed_permissions(rotation):
    file, call = rotation
    call("rotate-prepare")
    entries = json.loads(file.read_text())
    entries[0]["scopes"] = ["send"]
    file.write_text(json.dumps(entries))
    before = file.read_bytes()
    with pytest.raises(SystemExit):
        call("rotate-finish", "--client-updated")
    assert file.read_bytes() == before
