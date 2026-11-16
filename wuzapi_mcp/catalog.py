"""Extrai somente rotas ativas e documentação do checkout oficial do WuzAPI."""
import argparse
import json
from pathlib import Path
import re

import yaml

UPSTREAM = "https://github.com/asternic/wuzapi"


def generate(source: Path, commit: str) -> dict:
    routes = (source / "routes.go").read_text()
    spec = yaml.safe_load((source / "static/api/spec.yml").read_text())
    operations = []
    for line in routes.splitlines():
        line = line.strip()
        if line.startswith("//"):
            continue
        match = re.search(r'(s\.router|adminRoutes)\.Handle\("([^"]+)".*\.Methods\("([A-Z]+)"\)', line)
        if not match:
            continue
        router, path, method = match.groups()
        if router == "adminRoutes":
            path = "/admin" + path
        docs = spec.get("paths", {}).get(path, {}).get(method.lower(), {})
        content = docs.get("requestBody", {}).get("content", {})
        operations.append({"method": method, "path": path,
                           "summary": docs.get("summary", "Consulte API.md do WuzAPI para detalhes"),
                           "parameters": docs.get("parameters", []),
                           "body_schema": content.get("application/json", {}).get("schema", {}),
                           "multipart_only": bool(content) and "application/json" not in content})
    if len(operations) < 20:
        raise ValueError("Formato das rotas mudou; catálogo incompleto, atualização bloqueada")
    # Include component schemas so callers can resolve documented $refs.
    return {"upstream": UPSTREAM, "commit": commit, "operations": operations,
            "schemas": spec.get("components", {}).get("schemas", {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("commit")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(generate(args.source, args.commit), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
