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
    parser.add_argument("action", choices=["create", "revoke", "list", "rotate-prepare",
                                           "rotate-finish", "rotate-cancel"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--file", type=Path, default=Path(os.environ.get("MCP_CLIENTS_FILE", "clients.json")))
    parser.add_argument("--scopes", nargs="+", choices=sorted(SCOPES), default=sorted(SCOPES))
    parser.add_argument("--instances", nargs="+", default=["*"])
    parser.add_argument("--client-updated", action="store_true",
                        help="Declara que o cliente foi migrado e testado com a chave nova")
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
    if args.action.startswith("rotate-"):
        rotate(args, parser, entries)
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
        removed = {args.name}
        if any(e["name"] == f"{args.name}-next" and e.get("rotation_of") == args.name for e in entries):
            removed.add(f"{args.name}-next")
        entries = [e for e in entries if e["name"] not in removed]
    save_entries(args.file, entries)
    if args.action == "revoke":
        for name in removed:
            args.file.with_name(f"{name}.key").unlink(missing_ok=True)
    print(f"Cadastro atualizado: {args.file}")
    if args.action == "create":
        print(f"Segredo salvo em arquivo protegido: {keyfile}")


def save_entries(path, entries):
    temp = path.with_suffix(".tmp")
    with temp.open("x") as output:
        json.dump(entries, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temp.replace(path)


def rotate(args, parser, entries):
    original = next((e for e in entries if e["name"] == args.name), None)
    if not original or original.get("rotation_of"):
        parser.error("Cliente base não encontrado ou é uma chave de transição")
    name = f"{args.name}-next"
    pending = next((e for e in entries if e["name"] == name), None)
    keyfile = args.file.with_name(f"{name}.key")
    if args.action == "rotate-prepare":
        if pending or keyfile.exists():
            parser.error("Transição ou arquivo pendente já existe; examine antes de repetir")
        key = secrets.token_urlsafe(32)
        with keyfile.open("x") as output:
            output.write(key + "\n")
            output.flush()
            os.fsync(output.fileno())
        save_entries(args.file, [*entries, {**original, "name": name,
            "sha256": hashlib.sha256(key.encode()).hexdigest(), "rotation_of": args.name}])
        print(f"Chave de transição salva em arquivo protegido: {keyfile}")
        print("A chave anterior continua válida. Migre e teste o cliente antes de finalizar.")
        return
    if args.action == "rotate-cancel":
        if not pending or pending.get("rotation_of") != args.name:
            parser.error("Transição não encontrada; finalização interrompida exige rotate-finish")
        save_entries(args.file, [e for e in entries if e["name"] != name])
        keyfile.unlink(missing_ok=True)
        print("Transição cancelada; chave anterior preservada.")
        return
    if not args.client_updated:
        parser.error("Finalização exige --client-updated após migrar e testar o cliente")
    digest = hashlib.sha256(private_text(keyfile).encode()).hexdigest()
    if pending:
        if (pending.get("rotation_of") != args.name or pending["sha256"] != digest
                or pending["scopes"] != original["scopes"] or pending["instances"] != original["instances"]):
            parser.error("Transição inconsistente; nenhuma chave foi revogada")
        save_entries(args.file, [{**e, "sha256": digest} if e["name"] == args.name else e
                                 for e in entries if e["name"] != name])
    elif original["sha256"] != digest:
        parser.error("Transição não encontrada ou arquivo não corresponde à chave ativa")
    # Registry commits first; on interruption the valid new key remains in -next.key.
    keyfile.replace(args.file.with_name(f"{args.name}.key"))
    print("Rotação concluída; chave anterior revogada, arquivo principal atualizado.")


if __name__ == "__main__":
    main()
