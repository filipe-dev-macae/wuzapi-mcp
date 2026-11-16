import json
from pathlib import Path

import pytest
from collections import namedtuple

from wuzapi_mcp import maintenance as ops
from wuzapi_mcp.catalog import generate


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path / "runtime"
    for name in ("data/dbdata", "secrets", "releases/old", "releases/new"):
        (root / name).mkdir(parents=True)
    (root / "data/dbdata/main.db").write_text("old-data")
    (root / "secrets/admin-token").write_text("old-secret")
    for release in ("old", "new"):
        (root / f"releases/{release}/wuzapi").touch()
    ops.switch_release(root, root / "releases/old")
    return root


def test_restore_keeps_failed_state(runtime):
    backup = ops.snapshot(runtime)
    (runtime / "data/dbdata/main.db").write_text("new-data")
    (runtime / "secrets/admin-token").write_text("new-secret")
    ops.switch_release(runtime, runtime / "releases/new")
    ops.restore_snapshot(runtime, backup)
    assert (runtime / "data/dbdata/main.db").read_text() == "old-data"
    assert (runtime / "secrets/admin-token").read_text() == "old-secret"
    assert (runtime / "current").resolve().name == "old"
    archive = next((runtime / "failed-state").iterdir())
    assert (archive / "data/dbdata/main.db").read_text() == "new-data"
    assert (archive / "secrets/admin-token").read_text() == "new-secret"


def test_backup_rejects_full_disk_before_copy(runtime, monkeypatch):
    disk = namedtuple("disk", "total used free")
    monkeypatch.setattr(ops.shutil, "disk_usage", lambda path: disk(1000, 999, 1))
    with pytest.raises(RuntimeError, match="Espaço insuficiente"):
        ops.snapshot(runtime)
    assert not (runtime / "backups").exists()
    assert (runtime / "data/dbdata/main.db").read_text() == "old-data"


def test_failed_deploy_rolls_back(runtime, monkeypatch):
    calls = []
    monkeypatch.setattr(ops, "user_service", lambda *args: calls.append(args))
    attempts = 0

    def start(root):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            (root / "data/dbdata/main.db").write_text("migration")
            raise RuntimeError("unhealthy")

    monkeypatch.setattr(ops, "start_services", start)
    with pytest.raises(RuntimeError, match="unhealthy"):
        ops.deploy(runtime, runtime / "releases/new")
    assert attempts == 2
    assert (runtime / "current").resolve().name == "old"
    assert (runtime / "data/dbdata/main.db").read_text() == "old-data"
    assert calls[0][0] == "stop"


def test_reject_incomplete_or_external_backup(runtime, tmp_path):
    for backup in (tmp_path, runtime / "backups/missing"):
        with pytest.raises(ValueError):
            ops.restore_snapshot(runtime, backup)
    assert (runtime / "data/dbdata/main.db").read_text() == "old-data"


def test_catalog_required_routes_and_inactive_comments(tmp_path):
    source = tmp_path / "source"
    (source / "static/api").mkdir(parents=True)
    routes = [f's.router.Handle("/test/{i}", handler).Methods("GET")' for i in range(20)]
    routes += ['// s.router.Handle("/inactive", handler).Methods("POST")',
               'adminRoutes.Handle("/users", handler).Methods("GET")']
    (source / "routes.go").write_text("\n".join(routes))
    (source / "static/api/spec.yml").write_text("paths: {}\ndefinitions:\n  Legacy: {type: string}\ncomponents:\n  schemas:\n    Modern: {type: integer}\n")
    catalog = generate(source, "fake-commit")
    assert len(catalog["operations"]) == 21
    assert any(op["path"] == "/admin/users" for op in catalog["operations"])
    assert not any(op["path"] == "/inactive" for op in catalog["operations"])
    assert catalog["schemas"] == {"Legacy": {"type": "string"}, "Modern": {"type": "integer"}}
    with pytest.raises(RuntimeError, match="endpoints"):
        ops.validate_catalog(catalog)


def test_bundled_catalog_has_required_routes():
    catalog = json.loads((Path(__file__).parents[1] / "wuzapi_mcp/operations.json").read_text())
    ops.validate_catalog(catalog)
    assert {"MessageText", "ReactionText", "CreateGroup"} <= catalog["schemas"].keys()
