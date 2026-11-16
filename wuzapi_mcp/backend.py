import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx2 as httpx
from fastmcp.exceptions import ToolError

SENSITIVE = {"token", "admintoken", "authorization", "password", "secret",
             "secretkey", "accesskey", "hmackey", "apikey", "qrcode", "proxyurl",
             "mediakey", "messagesecret", "fileenckey", "globalencryptionkey",
             "accesstoken", "refreshtoken", "clientsecret"}
MAX_BODY = 32 * 1024 * 1024


def redact(value, secrets=()):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = re.sub(r"[^a-z]", "", key.lower())
            if name in SENSITIVE:
                result[key] = "[REDACTED]"
            elif name == "datajson" and isinstance(item, str) and item:
                # History embeds protobuf JSON in a string, including encryption keys.
                try:
                    result[key] = json.dumps(redact(json.loads(item), secrets), ensure_ascii=False)
                except ValueError:
                    result[key] = "[REDACTED: invalid data_json]"
            else:
                result[key] = redact(item, secrets)
        return result
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def unpack(value):
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def segment(value: str) -> str:
    if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_@.+:-]{1,200}", value):
        raise ToolError("Identificador inválido")
    return value


class Backend:
    def __init__(self, base_url: str, admin_token: str, transport=None):
        url = urlsplit(base_url)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                or url.password or url.query or url.fragment or url.path not in {"", "/"}):
            raise ValueError("WUZAPI_BASE_URL deve ser uma origem HTTP(S), sem credenciais")
        if url.scheme == "http" and url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("HTTP sem TLS só é permitido em loopback")
        if len(admin_token) < 16:
            raise ValueError("Token administrativo ausente ou muito curto")
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.transport = transport

    async def request(self, method: str, path: str, *, token=None, body=None, query=None):
        if not path.startswith("/") or path.startswith("//") or any(c in path for c in "?#%\\"):
            raise ToolError("Caminho de API inválido")
        if body is not None and len(json.dumps(body).encode()) > MAX_BODY:
            raise ToolError("Payload excede 32 MiB")
        headers = {"Authorization": self.admin_token} if path.startswith("/admin/") else {}
        if token:
            headers["Token"] = token
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=60,
                                        follow_redirects=False, trust_env=False,
                                        transport=self.transport) as client:
                async with client.stream(method, path, headers=headers, json=body, params=query) as response:
                    data = bytearray()
                    async for part in response.aiter_bytes():
                        data.extend(part)
                        if len(data) > MAX_BODY:
                            raise ToolError("Resposta excede 32 MiB; reduza a consulta")
                    try:
                        result = json.loads(data)
                    except ValueError:
                        raise ToolError(f"WuzAPI retornou resposta não JSON (HTTP {response.status_code})") from None
                    if response.status_code >= 300 or (isinstance(result, dict) and result.get("success") is False):
                        safe = redact(result, (self.admin_token, token))
                        raise ToolError(f"WuzAPI HTTP {response.status_code}: {json.dumps(safe, ensure_ascii=False)[:1000]}")
                    return result
        except httpx.RequestError:
            raise ToolError("Falha de rede ou timeout. Resultado pode estar incerto; não repita envios automaticamente.") from None

    async def instance_token(self, instance_id: str) -> str:
        result = unpack(await self.request("GET", f"/admin/users/{segment(instance_id)}"))
        users = result if isinstance(result, list) else [result]
        for user in users:
            if isinstance(user, dict) and user.get("id") == instance_id and user.get("token"):
                return user["token"]
        raise ToolError("Instância não encontrada")

    async def instance_request(self, instance_id, method, path, body=None, query=None):
        token = await self.instance_token(instance_id)
        result = await self.request(method, path, token=token, body=body, query=query)
        return redact(result, (self.admin_token, token))


def load_operations(path: Path | None = None) -> list[dict]:
    return json.loads((path or Path(__file__).with_name("operations.json")).read_text())["operations"]
