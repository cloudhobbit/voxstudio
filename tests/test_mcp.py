"""The MCP server, driven message by message, with the API behind it served by the test client."""
import json
import os

from voxstudio.mcp import PROTOCOLS, TOOLS, Server, ToolError


def backend(client):
    def request(method, path, body=None):
        r = client.request(method, path, json=body)
        if r.status_code >= 400:
            raise ToolError(str(r.json().get("detail")))
        return r.json()
    return request


def call(server, tool, /, **args):
    reply = server.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": tool, "arguments": args}})
    result = reply["result"]
    return result["isError"], result["content"][0]["text"]


def test_handshake_and_tool_list(client):
    s = Server(backend(client))
    init = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}})
    assert init["result"]["protocolVersion"] == "2024-11-05" and init["result"]["capabilities"] == {"tools": {}}
    assert init["result"]["serverInfo"]["name"] == "voxstudio"
    newer = s.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}})
    assert newer["result"]["protocolVersion"] == PROTOCOLS[0]
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert s.handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})["result"] == {}
    tools = s.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in tools] == [t["name"] for t in TOOLS] and all(t["inputSchema"]["type"] == "object" for t in tools)
    assert all(hasattr(s, f"tool_{t['name']}") for t in TOOLS)
    assert s.handle({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})["error"]["code"] == -32601


def test_speak_returns_a_file_that_exists(client, workspace):
    s = Server(backend(client))
    is_error, text = call(s, "speak", text="Hello from an agent", voice="@host", pitch=0)
    out = json.loads(text)
    assert not is_error and os.path.isfile(out["file"]) and out["file"].startswith(str(workspace.root)) and out["words"] == 4
    is_error, text = call(s, "speak", text="x", voice="af_nobody")
    assert is_error and "Unknown voice" in text
    is_error, text = call(s, "speak", wrong_argument=1)
    assert is_error
    assert s.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "rm_rf"}})["error"]["code"] == -32602


def test_project_export_voices_pronunciation_and_signature(client, workspace):
    s = Server(backend(client))
    _, text = call(s, "create_project", title="Agent Demo", script="ANNA: Hi there.\nBEN: Hello you.", voices={"BEN": "bm_george"})
    made = json.loads(text)
    assert made["slug"] == "agent-demo" and [b["voice"] for b in made["blocks"]] == ["af_heart", "bm_george"]
    is_error, text = call(s, "export_project", slug="agent-demo", captions=["srt"])
    out = json.loads(text)
    assert not is_error and out["caption_cues"] == 2 and all(os.path.isfile(f) for f in out["files"])
    assert [os.path.basename(f) for f in out["files"]] == ["agent-demo.wav", "agent-demo.srt", "timing.json"]
    assert json.loads(call(s, "list_projects")[1])["projects"][0]["slug"] == "agent-demo"
    voices = json.loads(call(s, "list_voices", query="british")[1])
    assert voices["count"] == 0 or all("british" in json.dumps(v).lower() for v in voices["voices"])
    assert json.loads(call(s, "list_voices", query="UK")[1])["count"] >= 8
    assert not call(s, "set_pronunciation", word="Toconao", say="Toh-koh-NAH-oh")[0]
    assert workspace.pronunciations.load()[0]["Toconao"] == "Toh-koh-NAH-oh"
    assert not call(s, "save_signature", name="teller", mix="af_heart:0.7,bm_george:0.3", note="warm")[0]
    is_error, text = call(s, "save_signature", name="teller", mix="af_heart")
    assert is_error and "already exists" in text
    assert call(s, "export_project", slug="nope")[0]
