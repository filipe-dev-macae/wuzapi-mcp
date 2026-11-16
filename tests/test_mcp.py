import hashlib
import json

from fastmcp import Client
from fastmcp.exceptions import ToolError
import httpx2 as httpx
from pydantic import ValidationError
import pytest

from wuzapi_mcp.auth import APIKeys
from wuzapi_mcp.backend import Backend, redact, segment
from wuzapi_mcp import server

KEY = "test-" + "x" * 40
ADMIN = "admin-" + "a" * 40
INSTANCE_TOKEN = "session-" + "s" * 40


@pytest.fixture
def keys(tmp_path):
    path = tmp_path / "clients.json"
    path.write_text(json.dumps([{"name": "test", "sha256": hashlib.sha256(KEY.encode()).hexdigest(),
                                 "scopes": ["read", "send", "write", "admin"], "instances": ["*"]}]))
    path.chmod(0o600)
    return APIKeys(path, "http://localhost:8082")


@pytest.fixture
def backend():
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path.startswith("/admin/"):
            assert request.headers["Authorization"] == ADMIN
            if request.method == "GET":
                return httpx.Response(200, json={"data": [{"id": "one", "token": INSTANCE_TOKEN, "name": "One"},
                                                          {"id": "two", "token": "another-secret", "name": "Two"}]})
            if request.method == "POST":
                return httpx.Response(201, json={"data": {"id": "new", **json.loads(request.content)}})
        assert request.headers["Token"] == INSTANCE_TOKEN
        return httpx.Response(200, json={"success": True, "data": {"Details": "Sent", "Id": "id"}})

    return Backend("http://127.0.0.1:8081", ADMIN, httpx.MockTransport(handle)), calls


async def test_keys_invalid_revoked_and_private(keys):
    assert await keys.verify_token(KEY)
    assert await keys.verify_token("wrong-" + "y" * 40) is None
    keys.path.write_text("[]")
    assert await keys.verify_token(KEY) is None
    keys.path.chmod(0o644)
    with pytest.raises(ValueError, match="600"):
        keys.entries()


async def test_mixed_buttons_and_preview_mapping(keys, backend, monkeypatch):
    api, calls = backend
    access = await keys.verify_token(KEY)
    monkeypatch.setattr(server, "get_access_token", lambda: access)
    mcp = server.create_server(api, keys)
    async with Client(mcp) as client:
        result = await client.call_tool("send_buttons", {
            "instance_id": "one", "phone": "5511999999999", "text": "Teste",
            "buttons": [{"type": "reply", "title": "Sim", "id": "yes"},
                        {"type": "cta_url", "title": "Abrir", "url": "https://example.com"},
                        {"type": "copy", "title": "Copiar", "copy_code": "TEST123"},
                        {"type": "cta_call", "title": "Ligar", "phone_number": "+5511999999999"}],
        })
        assert not result.is_error
        payload = json.loads(calls[-1].content)
        assert calls[-1].url.path == "/chat/send/buttons"
        assert payload["Buttons"][2]["copy_code"] == "TEST123"
        assert len(payload["Id"]) == 32
        assert payload["Envelope"] == "original"
        await client.call_tool("send_text", {"instance_id": "one", "phone": "5511999999999",
                                            "text": "https://example.com", "link_preview": True})
        assert json.loads(calls[-1].content)["LinkPreview"] is True


async def test_scopes_instances_and_revocation_enforced(keys, backend, monkeypatch):
    api, calls = backend
    entries = keys.entries()
    entries[0]["scopes"] = ["read"]
    entries[0]["instances"] = ["one"]
    keys.path.write_text(json.dumps(entries))
    access = await keys.verify_token(KEY)
    monkeypatch.setattr(server, "get_access_token", lambda: access)
    async with Client(server.create_server(api, keys)) as client:
        result = await client.call_tool("list_instances", {})
        text = json.dumps(result.data)
        assert "One" in text and "Two" not in text and INSTANCE_TOKEN not in text
        count = len(calls)
        result = await client.call_tool("session", {"instance_id": "two", "action": "status"}, raise_on_error=False)
        assert result.is_error and len(calls) == count
        result = await client.call_tool("send_text", {"instance_id": "one", "phone": "5511999999999", "text": "x"}, raise_on_error=False)
        assert result.is_error and len(calls) == count
        keys.path.write_text("[]")
        result = await client.call_tool("list_instances", {}, raise_on_error=False)
        assert result.is_error and len(calls) == count


async def test_invalid_input_and_generic_endpoint_guard(keys, backend, monkeypatch):
    api, calls = backend
    access = await keys.verify_token(KEY)
    monkeypatch.setattr(server, "get_access_token", lambda: access)
    async with Client(server.create_server(api, keys)) as client:
        for params in [{"method": "GET", "path_template": "https://attacker.invalid"},
                       {"method": "POST", "path_template": "/chat/send/text", "instance_id": "one", "body": {}},
                       {"method": "GET", "path_template": "/admin/users/{id}", "path_params": {"id": "../users"}}]:
            result = await client.call_tool("api_call", params, raise_on_error=False)
            assert result.is_error
        assert not calls
        result = await client.call_tool("create_instance", {"name": "New"})
        assert "token" in json.dumps(result.data) and "REDACTED" in json.dumps(result.data)
        sent_token = json.loads(calls[-1].content)["token"]
        assert sent_token not in json.dumps(result.data)


@pytest.mark.parametrize("button", [
    {"type": "cta_url", "title": "Abrir"},
    {"type": "cta_url", "title": "Abrir", "url": "https://user:password@example.com"},
    {"type": "copy", "title": "Copiar"},
    {"type": "reply", "title": "x" * 21},
    {"type": "cta_call", "title": "Ligar"},
])
def test_button_validation(button):
    with pytest.raises(ValidationError):
        server.Button(**button)


async def test_no_retry_on_timeout_or_redirect():
    count = 0

    def timeout(request):
        nonlocal count
        count += 1
        raise httpx.ReadTimeout("uncertain", request=request)

    api = Backend("http://127.0.0.1:8081", ADMIN, httpx.MockTransport(timeout))
    with pytest.raises(ToolError, match="não repita"):
        await api.request("POST", "/chat/send/text", token=INSTANCE_TOKEN, body={})
    assert count == 1

    def redirect(request):
        return httpx.Response(302, headers={"Location": "https://attacker.invalid"}, json={"error": "redirect"})

    api = Backend("http://127.0.0.1:8081", ADMIN, httpx.MockTransport(redirect))
    with pytest.raises(ToolError, match="302"):
        await api.request("GET", "/admin/users")


def test_redaction_and_validation():
    result = redact({"token": "x", "nested": [{"secret_key": "y", "qrcode": "z"}], "message": ADMIN}, (ADMIN,))
    assert "REDACTED" in json.dumps(result) and ADMIN not in json.dumps(result)
    with pytest.raises(ValueError):
        Backend("http://public.example.com", ADMIN)
    with pytest.raises(ToolError):
        segment("../admin")
