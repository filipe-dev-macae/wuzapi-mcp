"""Gerenciamento local de chaves; o segredo nunca é impresso no terminal."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

from .auth import SCOPES, private_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "revoke", "list"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--file", type=Path, default=Path(os.environ.get("MCP_CLIENTS_FILE", "clients.json")))
    parser.add_argument("--scopes", nargs="+", choices=sorted(SCOPES), default=sorted(SCOPES))
    parser.add_argument("--instances", nargs="+", default=["*"])
    args = parser.parse_args()
    os.umask(0o077)
    if args.action != "list" and (not args.name or not re.fullmatch(r"[a-z0-9_-]{1,50}", args.name)):
        parser.error("Nome obrigatório: letras minúsculas, números, _ ou -")
    with args.file.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manage(args, parser)


def manage(args, parser):
    entries = json.loads(private_text(args.file)) if args.file.exists() else []
    if args.action == "list":
        print(json.dumps([{k: v for k, v in e.items() if k != "sha256"} for e in entries], indent=2))
        return
    found = any(e["name"] == args.name for e in entries)
    if args.action == "create" and found:
        parser.error("Nome já cadastrado; revogue antes de recriar")
    if args.action == "revoke" and not found:
        parser.error("Chave não encontrada")
    if args.action == "create":
        key = secrets.token_urlsafe(32)
        keyfile = args.file.with_name(f"{args.name}.key")
        with keyfile.open("x") as output:
            output.write(key + "\n")
        entries.append({"name": args.name, "sha256": hashlib.sha256(key.encode()).hexdigest(),
                        "scopes": args.scopes, "instances": args.instances})
    else:
        entries = [e for e in entries if e["name"] != args.name]
    temp = args.file.with_suffix(".tmp")
    with temp.open("x") as output:
        json.dump(entries, output, indent=2)
    temp.replace(args.file)
    if args.action == "revoke":
        args.file.with_name(f"{args.name}.key").unlink(missing_ok=True)
    print(f"Cadastro atualizado: {args.file}")
    if args.action == "create":
        print(f"Segredo salvo em arquivo protegido: {keyfile}")


if __name__ == "__main__":
    main()
