import json

from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.skills import SkillsClientExtension
import pytest

from wuzapi_mcp import server
from test_mcp import backend, keys, KEY


async def test_skill_discovery_resources_and_tool_share_the_same_files(keys, backend, monkeypatch):
    api, calls = backend
    access = await keys.verify_token(KEY)
    monkeypatch.setattr(server, "get_access_token", lambda: access)
    mcp = server.create_server(api, keys)
    async with Client(mcp, extensions=[SkillsClientExtension()]) as client:
        discovered = await client.list_skills()
        assert len(discovered) == 1
        assert str(discovered[0].uri) == "skill://wuzapi-mcp/SKILL.md"
        skill = await client.read_skill("skill://wuzapi-mcp/SKILL.md")
        assert set(skill.files) == {"SKILL.md", "references/messages.md",
                                    "references/administration.md", "references/operations.md"}
        for section, filename in [("overview", "SKILL.md"), ("messages", "references/messages.md"),
                                  ("administration", "references/administration.md"),
                                  ("operations", "references/operations.md")]:
            result = await client.call_tool("get_usage_guide", {"section": section})
            expected = skill.files[filename].decode("utf-8")
            assert result.content[0].text == expected
            resource = await client.read_resource("skill://wuzapi-mcp/" + filename)
            assert resource[0].text == expected
        with pytest.raises(ToolError):
            await client.call_tool("get_usage_guide", {"section": "../../secrets/mcp.env"})
    assert calls == []


async def test_usage_guide_requires_read_scope(keys, backend, monkeypatch):
    api, calls = backend
    entries = json.loads(keys.path.read_text())
    entries[0]["scopes"] = ["send"]
    keys.path.write_text(json.dumps(entries))
    access = await keys.verify_token(KEY)
    monkeypatch.setattr(server, "get_access_token", lambda: access)
    async with Client(server.create_server(api, keys)) as client:
        with pytest.raises(ToolError, match="read"):
            await client.call_tool("get_usage_guide", {})
    assert calls == []
