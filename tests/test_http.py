import json

import httpx2 as httpx

from wuzapi_mcp.server import create_server

from test_mcp import keys, backend, KEY


async def test_http_auth_and_legacy_mcp_handshake(keys, backend):
    api, _ = backend
    server = create_server(api, keys)
    app = server.http_app(path="/mcp", stateless_http=True, json_response=True)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "composio-compatible-test", "version": "1"}}}
            headers = {"Accept": "application/json, text/event-stream"}
            response = await client.post("/mcp", json=payload, headers=headers)
            assert response.status_code == 401
            response = await client.post("/mcp", json=payload, headers={**headers, "Authorization": "Bearer invalid"})
            assert response.status_code == 401
            headers["Authorization"] = "Bearer " + KEY
            response = await client.post("/mcp", json=payload, headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["result"]["serverInfo"]["name"] == "WuzAPI MCP"
            headers["MCP-Protocol-Version"] = "2025-06-18"
            response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers)
            assert response.status_code == 200
            assert "send_buttons" in {t["name"] for t in response.json()["result"]["tools"]}
            keys.path.write_text("[]")
            response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, headers=headers)
            assert response.status_code == 401
