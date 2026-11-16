import hashlib
import hmac
import json
from pathlib import Path
import re

from fastmcp.server.auth import AccessToken, TokenVerifier

SCOPES = {"read", "send", "write", "admin"}


def private_text(path: Path) -> str:
    if path.stat().st_mode & 0o077:
        raise ValueError(f"Arquivo deve ter permissão 600: {path}")
    return path.read_text().strip()


class APIKeys(TokenVerifier):
    def __init__(self, path: Path, public_url: str):
        super().__init__(base_url=public_url)
        self.path = path
        self.entries()  # Fail closed before listening if configuration is invalid.

    def entries(self) -> list[dict]:
        entries = json.loads(private_text(self.path))
        if not isinstance(entries, list) or not entries:
            raise ValueError("Configure ao menos uma chave MCP")
        names = set()
        for entry in entries:
            if (not isinstance(entry, dict) or not isinstance(entry.get("name"), str)
                    or not isinstance(entry.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                    or not isinstance(entry.get("scopes"), list)
                    or not all(isinstance(s, str) for s in entry["scopes"])
                    or not set(entry.get("scopes", [])) <= SCOPES
                    or not isinstance(entry.get("instances"), list)
                    or not all(isinstance(i, str) for i in entry["instances"])
                    or entry["name"] in names):
                raise ValueError("Cadastro de chaves MCP inválido")
            names.add(entry["name"])
        return entries

    async def verify_token(self, token: str) -> AccessToken | None:
        if len(token) < 32 or len(token) > 512:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        try:
            entries = self.entries()
        except (OSError, ValueError, TypeError):
            return None
        for entry in entries:
            if hmac.compare_digest(digest, entry["sha256"]):
                return AccessToken(token=token, client_id=entry["name"],
                                   scopes=entry["scopes"],
                                   claims={"instances": entry["instances"]})
        return None
