"""A Model Context Protocol server over stdio: `voxstudio mcp`.

It is a thin layer over the HTTP API. If a Vox Studio server is already running it talks to that one (so the
agent and the browser app share voices, projects and the audio cache); otherwise it starts one in this process.
The protocol is small enough (JSON-RPC 2.0, one JSON object per line) that it is written out here rather than
pulling in a dependency.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

from . import NAME, __version__

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_URL = "http://127.0.0.1:7860"


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


_VOICE = {"type": "string", "description": "A voice id (af_heart), a blend (af_heart:0.6,bf_emma:0.4) or a saved signature (@narrator)."}
TOOLS = [
    {"name": "speak", "description": "Speak one line to a WAV file on this machine. Returns the file path, duration and word timings count. Identical requests are served from a cache.",
     "inputSchema": _schema({"text": {"type": "string", "description": "What to say, up to 2000 characters."}, "voice": _VOICE,
                             "speed": {"type": "number", "description": "0.5-2.0, default 1.0"}, "pitch": {"type": "number", "description": "Semitones, -12..12, default 0"},
                             "effect": {"type": "string", "description": "none, radio, deep, tiny, robot, echo, inner, crystal or ghost"},
                             "space": {"type": "string", "description": "dry, room, hall, cave, phone or outdoor"},
                             "project": {"type": "string", "description": "A project slug, to apply that project's pronunciations."}}, ["text"])},
    {"name": "list_voices", "description": "List the voices, blends and saved signatures, optionally filtered by a search word (name, accent, character, use).",
     "inputSchema": _schema({"query": {"type": "string"}}, [])},
    {"name": "create_project", "description": "Create a narration project from a script. Blank lines separate blocks; 'NAME: line' dialogue, Markdown and SRT are detected. Returns the slug and the blocks.",
     "inputSchema": _schema({"title": {"type": "string"}, "script": {"type": "string"}, "voice": {**_VOICE, "description": "Voice for every block (default af_heart)."},
                             "voices": {"type": "object", "description": "For dialogue: speaker name -> voice.", "additionalProperties": {"type": "string"}}}, ["title", "script"])},
    {"name": "export_project", "description": "Render a project and write audio plus captions. Returns the file paths. Blocks already rendered are reused.",
     "inputSchema": _schema({"slug": {"type": "string"}, "format": {"type": "string", "enum": ["wav", "mp3"], "description": "Default wav; mp3 needs ffmpeg with libmp3lame."},
                             "captions": {"type": "array", "items": {"type": "string", "enum": ["srt", "vtt"]}, "description": "Default both."}}, ["slug"])},
    {"name": "list_projects", "description": "List narration projects with their block and word counts.", "inputSchema": _schema({}, [])},
    {"name": "set_pronunciation", "description": "Fix how a word is said: a respelling (Chun-druh-yaan) or phonemes between slashes (/pɹˈʌɡjɑn/). Shared by every project unless a project slug is given.",
     "inputSchema": _schema({"word": {"type": "string"}, "say": {"type": "string"}, "project": {"type": "string"}}, ["word", "say"])},
    {"name": "save_signature", "description": "Save a blend of voices under a name, usable anywhere as @name.",
     "inputSchema": _schema({"name": {"type": "string", "description": "lowercase letters, digits, - and _"}, "mix": {"type": "string", "description": "e.g. af_heart:0.6,bf_emma:0.4"},
                             "speed": {"type": "number"}, "pitch": {"type": "number"}, "note": {"type": "string"}, "overwrite": {"type": "boolean"}}, ["name", "mix"])},
]


class ToolError(Exception):
    pass


class HttpBackend:
    """request(method, path, body) -> parsed JSON; raises ToolError with the server's plain-language detail."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def __call__(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=600) as res:
                return json.loads(res.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise ToolError(str(detail or f"{e.code} {e.reason}")) from None
        except urllib.error.URLError as e:
            raise ToolError(f"Can't reach Vox Studio at {self.base_url}: {e.reason}") from None


class Server:
    def __init__(self, request, base_url: str = ""):
        self.request, self.base_url = request, base_url
        self._root = None

    # ---- tools ---------------------------------------------------------------------------

    def root(self) -> str:
        if self._root is None:
            self._root = self.request("GET", "/api/health")["workspace"]
        return self._root

    def tool_speak(self, text: str, voice: str = "af_heart", speed: float = 1.0, pitch: float = 0, effect: str = "none",
                   space: str = "dry", project: str | None = None):
        r = self.request("POST", "/api/speak", {"text": text, "voice": voice, "speed": speed, "pitch": pitch, "effect": effect, "space": space, "project": project})
        return {"file": os.path.join(self.root(), "cache", f"{r['key']}.wav"), "duration": r["duration"], "cached": r["cached"],
                "words": len(r.get("words") or []), "format": "24 kHz mono 16-bit WAV"}

    def tool_list_voices(self, query: str = ""):
        q = query.strip().lower()
        out = []
        for v in self.request("GET", "/api/voices")["voices"]:
            hay = " ".join(str(x) for x in [v["id"], v.get("name"), v.get("accent"), v.get("character"), *v.get("uses", []), *v.get("tags", [])]).lower()
            if q and q not in hay:
                continue
            out.append({k: v[k] for k in ("id", "kind", "name", "accent", "gender", "grade", "character", "uses", "favourite", "rating") if v.get(k) not in (None, "", [], 0, False)})
        return {"voices": out, "count": len(out)}

    def tool_create_project(self, title: str, script: str, voice: str = "af_heart", voices: dict | None = None):
        p = self.request("POST", "/api/projects", {"title": title, "script": script, "voice": voice, "voices": voices or {}})
        return {"slug": p["slug"], "title": p["title"], "blocks": [{"id": b["id"], "voice": b["voice"], "speaker": b.get("speaker"), "text": b["text"][:80]} for b in p["blocks"]]}

    def tool_export_project(self, slug: str, format: str = "wav", captions: list | None = None):
        job_id = self.request("POST", f"/api/projects/{slug}/export", {"format": format, "captions": ["srt", "vtt"] if captions is None else captions})["job_id"]
        while True:
            job = self.request("GET", f"/api/jobs/{job_id}")
            if job["status"] == "failed":
                raise ToolError(job["error"] or "The export failed")
            if job["status"] == "done":
                break
            time.sleep(0.2)
        folder = os.path.join(self.root(), "exports", slug)
        return {"duration": job["result"]["duration"], "caption_cues": job["result"]["cues"], "files": [os.path.join(folder, f["name"]) for f in job["result"]["files"]]}

    def tool_list_projects(self):
        return self.request("GET", "/api/projects")

    def tool_set_pronunciation(self, word: str, say: str, project: str | None = None):
        scope = "project" if project else "shared"
        self.request("PUT", f"/api/pronunciations/{scope}/{urllib.request.quote(word, safe='')}", {"say": say, **({"project": project} if project else {})})
        return {"saved": word, "say": say, "scope": project or "shared"}

    def tool_save_signature(self, name: str, mix: str, speed: float = 1.0, pitch: float = 0, note: str = "", overwrite: bool = False):
        self.request("PUT", f"/api/signatures/{urllib.request.quote(name, safe='')}", {"mix": mix, "speed": speed, "pitch": pitch, "note": note, "overwrite": overwrite})
        return {"saved": f"@{name}", "mix": mix}

    # ---- protocol ------------------------------------------------------------------------

    def handle(self, msg: dict) -> dict | None:
        """One JSON-RPC message in, one out (None for notifications)."""
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method is None or mid is None:
            return None   # a notification (or a response to us): nothing to answer

        def ok(result):
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        if method == "initialize":
            wanted = params.get("protocolVersion")
            return ok({"protocolVersion": wanted if wanted in PROTOCOLS else PROTOCOLS[0], "capabilities": {"tools": {}},
                       "serverInfo": {"name": "voxstudio", "title": NAME, "version": __version__},
                       "instructions": "Local text to speech. Files are written on this machine and their paths returned; nothing is uploaded."})
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": TOOLS})
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            fn = getattr(self, f"tool_{name}", None)
            if fn is None or name not in {t["name"] for t in TOOLS}:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
            try:
                result = fn(**args)
                return ok({"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=1)}], "isError": False})
            except (ToolError, TypeError, KeyError) as e:   # the model should see the reason and can retry
                return ok({"content": [{"type": "text", "text": str(e)}], "isError": True})
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def _alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=2) as res:
            return bool(json.loads(res.read()).get("ok"))
    except (OSError, ValueError):
        return False


def start_local(workspace: str | None, engine: str) -> str:
    """Start a Vox Studio server in this process on a free port and return its URL."""
    import uvicorn

    from .api import create_app
    from .cli import free_port
    from .workspace import Workspace

    port = free_port(7870)
    server = uvicorn.Server(uvicorn.Config(create_app(Workspace(workspace), engine_name=engine), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, name="voxstudio-http", daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if _alive(url):
            return url
        time.sleep(0.1)
    raise SystemExit("Vox Studio did not start")


def run_stdio(url: str | None = None, workspace: str | None = None, engine: str = "kokoro") -> None:
    # Keep the protocol channel clean: anything a library prints goes to stderr, never into the JSON stream.
    out = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    base = url or os.environ.get("VOXSTUDIO_URL") or DEFAULT_URL
    if workspace or not _alive(base):   # an explicit workspace always gets its own server
        base = start_local(workspace, engine)
    print(f"{NAME} MCP server using {base}", file=sys.stderr)
    server = Server(HttpBackend(base), base)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            continue
        for one in msg if isinstance(msg, list) else [msg]:
            reply = server.handle(one) if isinstance(one, dict) else None
            if reply is not None:
                out.write(json.dumps(reply, ensure_ascii=False) + "\n")
