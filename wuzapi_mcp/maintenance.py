"""Backup e atualização rootless. Nunca envia mensagens nem apaga backups."""
import argparse
import asyncio
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from .catalog import generate, UPSTREAM

REQUIRED_ROUTES = {("POST", "/chat/send/text"), ("POST", "/chat/send/buttons"),
                   ("POST", "/session/pairphone"), ("GET", "/session/qr"),
                   ("GET", "/admin/users"), ("POST", "/admin/users"),
                   ("GET", "/session/status")}


def run(*args, cwd=None, env=None, timeout=900) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if logfile := os.environ.get("WUZAPI_COMMAND_LOG"):
        with Path(logfile).open("a") as log:
            log.write(f"\n--- {Path(args[0]).name}: exit {result.returncode} ---\n")
            log.write(result.stdout + result.stderr)
    if result.returncode:
        # Commands are fixed; avoid echoing arbitrary subprocess output or credentials.
        raise RuntimeError(f"Falhou {Path(args[0]).name}, exit={result.returncode}")
    return result.stdout.strip()


def user_service(action, *units):
    run("systemctl", "--user", action, *units, timeout=90)


def wait_health(url, seconds=30):
    deadline = time.monotonic() + seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=2) as response:
                data = json.load(response)
                if response.status == 200 and data.get("status") == "ok":
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Serviço não ficou saudável no prazo")


def validate_catalog(catalog):
    actual = {(op["method"], op["path"]) for op in catalog["operations"]}
    if not REQUIRED_ROUTES <= actual:
        raise RuntimeError("WuzAPI removeu endpoints necessários ao MCP")


def switch_release(root: Path, release: Path):
    temporary = root / "next"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release)
    temporary.replace(root / "current")


def snapshot(root: Path) -> Path:
    size = sum(path.stat().st_size for folder in (root / "data", root / "secrets")
               for path in folder.rglob("*") if path.is_file())
    if shutil.disk_usage(root).free < size + 512 * 1024 * 1024:
        raise RuntimeError("Espaço insuficiente para backup e reserva de 512 MiB; dados não alterados")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = root / "backups" / stamp
    destination.mkdir(parents=True, mode=0o700)
    try:
        shutil.copytree(root / "data", destination / "data")
        shutil.copytree(root / "secrets", destination / "secrets")
        (destination / "release").write_text(str((root / "current").resolve()))
        (destination / "COMPLETE").touch()
    except Exception:
        # Incomplete snapshots are retained for inspection and never used for restore.
        raise RuntimeError("Backup incompleto; atualização não aplicada") from None
    return destination


def restore_snapshot(root: Path, backup: Path):
    if backup.resolve().parent != (root / "backups").resolve() or not (backup / "COMPLETE").is_file():
        raise ValueError("Backup inválido ou incompleto")
    release = Path((backup / "release").read_text()).resolve()
    if release.parent != (root / "releases").resolve() or not (release / "wuzapi").is_file():
        raise ValueError("Binário anterior indisponível")
    # Preserve state produced during a failed rollout instead of deleting it.
    archive = root / "failed-state" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    archive.mkdir(parents=True, mode=0o700)
    for name in ("data", "secrets"):
        replacement = archive / (name + "-restored")
        shutil.copytree(backup / name, replacement)
    for name in ("data", "secrets"):
        (root / name).rename(archive / name)
        (archive / (name + "-restored")).rename(root / name)
    switch_release(root, release)


def smoke_candidate(release: Path):
    with tempfile.TemporaryDirectory(prefix="wuzapi-candidate-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        admin = secrets.token_urlsafe(32)
        token = secrets.token_urlsafe(32)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": temp,
               "WUZAPI_ADMIN_TOKEN": admin, "WUZAPI_GLOBAL_ENCRYPTION_KEY": secrets.token_hex(16),
               "LOG_LEVEL": "error"}
        proc = subprocess.Popen([str(release / "wuzapi"), "-address=127.0.0.1", f"-port={port}",
                                 f"-datadir={temp}"], cwd=release, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            origin = f"http://127.0.0.1:{port}"
            wait_health(origin + "/health")
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def request(path, body=None, headers=None):
                req = urllib.request.Request(origin + path, headers=headers or {},
                                             data=json.dumps(body).encode() if body is not None else None)
                with opener.open(req, timeout=5) as response:
                    return json.load(response)

            try:
                request("/admin/users")
            except urllib.error.HTTPError as exc:
                if exc.code != 401:
                    raise RuntimeError("Contrato de autenticação mudou") from None
            else:
                raise RuntimeError("WuzAPI aceitou administração sem autenticação")
            created = request("/admin/users", {"name": "mcp-compatibility-test", "token": token},
                              {"Authorization": admin, "Content-Type": "application/json"})
            if not created.get("success") or not created.get("data", {}).get("id"):
                raise RuntimeError("Contrato de criação de instância mudou")
            users = request("/admin/users", headers={"Authorization": admin})
            if not isinstance(users.get("data"), list) or users["data"][0].get("token") != token:
                raise RuntimeError("Contrato de listagem de instâncias mudou")
            status = request("/session/status", headers={"Token": token})
            if not status.get("success"):
                raise RuntimeError("Contrato de status de sessão mudou")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


async def probe_mcp(root):
    from fastmcp import Client
    key = (root / "secrets" / "openbot.key").read_text().strip()
    async with Client("http://127.0.0.1:8082/mcp", auth=key, timeout=15) as client:
        tools = {tool.name for tool in await client.list_tools()}
        if not {"send_buttons", "send_text", "list_instances", "pairing_code"} <= tools:
            raise RuntimeError("Ferramentas MCP necessárias indisponíveis")
        result = await client.call_tool("health", {})
        if result.is_error:
            raise RuntimeError("MCP não acessou o WuzAPI")


def start_services(root):
    user_service("start", "wuzapi.service")
    wait_health("http://127.0.0.1:8081/health")
    user_service("start", "wuzapi-mcp.service")
    wait_health("http://127.0.0.1:8082/healthz")
    asyncio.run(probe_mcp(root))


def deploy(root: Path, release: Path):
    backup = None
    user_service("stop", "wuzapi-mcp.service", "wuzapi.service")
    try:
        backup = snapshot(root)
        switch_release(root, release)
        start_services(root)
    except Exception:
        user_service("stop", "wuzapi-mcp.service", "wuzapi.service")
        if backup:
            restore_snapshot(root, backup)
        start_services(root)
        raise
    return backup


def update(root: Path, project: Path):
    source = root / "source"
    if run("git", "remote", "get-url", "origin", cwd=source) not in {UPSTREAM, UPSTREAM + ".git"}:
        raise RuntimeError("Origin não é o repositório oficial autorizado")
    if run("git", "status", "--porcelain", cwd=source):
        raise RuntimeError("Checkout contém alterações locais; elas serão preservadas")
    run("git", "fetch", "--depth=1", "origin", "main", cwd=source)
    commit = run("git", "rev-parse", "FETCH_HEAD", cwd=source)
    current = (root / "current" / "UPSTREAM_COMMIT").read_text().strip()
    if current == commit:
        return {"state": "up_to_date", "commit": commit}
    release = root / "releases" / commit
    if not (release / "VERIFIED").exists():
        release.mkdir(parents=True, exist_ok=True, mode=0o700)
        build = root / "builds" / commit
        build.parent.mkdir(exist_ok=True)
        if build.exists():
            raise RuntimeError("Build anterior incompleto preservado; examine antes de repetir")
        run("git", "worktree", "add", "--detach", str(build), commit, cwd=source)
        try:
            env = {**os.environ, "CGO_ENABLED": "0", "GOMAXPROCS": "2"}
            go = os.environ["WUZAPI_GO_BIN"]
            run(go, "test", "./...", "-timeout=10m", cwd=build, env=env)
            run(go, "build", "-o", str(release / "wuzapi"), ".", cwd=build, env=env)
            catalog = generate(build, commit)
            validate_catalog(catalog)
            (release / "mcp-operations.json").write_text(json.dumps(catalog, ensure_ascii=False))
            (release / "UPSTREAM_COMMIT").write_text(commit + "\n")
            for directory in ("static",):
                shutil.copytree(build / directory, release / directory, dirs_exist_ok=True)
            shutil.copy2(build / "API.md", release / "API.md")
            run(str(project / ".venv/bin/python"), "-m", "pytest", "-q", cwd=project)
            smoke_candidate(release)
            (release / "VERIFIED").touch()
        finally:
            # Remove only this disposable official worktree, never user application data.
            run("git", "worktree", "remove", "--force", str(build), cwd=source)
    backup = deploy(root, release)
    return {"state": "updated", "commit": commit, "backup": str(backup)}


def main():
    load_dotenv(os.environ.get("WUZAPI_MCP_ENV_FILE", ".env"), override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["update", "backup", "status", "restore"])
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(os.environ["WUZAPI_RUNTIME_DIR"])
    project = Path(os.environ["WUZAPI_MCP_PROJECT_DIR"])
    os.environ["WUZAPI_COMMAND_LOG"] = str(root / "maintenance-commands.log")
    if args.action == "status":
        path = root / "last-update.json"
        print(path.read_text() if path.exists() else '{"state":"not_run"}')
        return
    with (root / "maintenance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if args.action == "update":
                result = update(root, project)
            elif args.action == "backup":
                user_service("stop", "wuzapi-mcp.service", "wuzapi.service")
                try:
                    result = {"state": "backup_complete", "backup": str(snapshot(root))}
                finally:
                    start_services(root)
            else:
                if not args.backup:
                    parser.error("restore exige --backup")
                user_service("stop", "wuzapi-mcp.service", "wuzapi.service")
                try:
                    restore_snapshot(root, args.backup)
                    result = {"state": "restored", "backup": str(args.backup)}
                finally:
                    start_services(root)
        except Exception as exc:
            result = {"state": "failed", "error": str(exc), "utc": datetime.now(timezone.utc).isoformat()}
            (root / "last-update.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
            raise SystemExit(1) from None
        result["utc"] = datetime.now(timezone.utc).isoformat()
        (root / "last-update.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))


if __name__ == "__main__":
    main()
