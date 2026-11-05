"""The language model: any server that speaks the OpenAI chat-completions API, streamed.

That covers Ollama, LM Studio, llama.cpp and vLLM on this machine, and hosted services when you point it at one.
`stream(messages)` yields text as it arrives; closing the iterator drops the connection, which stops the server.
"""
import http.client
import json
import re
from collections.abc import Iterator
from typing import Protocol
from urllib.parse import urlsplit

LOOPBACK = {"localhost", "127.0.0.1", "::1"}
THINK = re.compile(r"<think>.*?</think>\s*", re.S)


class LLM(Protocol):
    name: str
    local: bool

    def stream(self, messages: list[dict]) -> Iterator[str]: ...


class FakeLLM:
    """Scripted replies, token by token; with none left it answers "You said: ...". Remembers what it was asked."""
    name, local = "fake", True

    def __init__(self, replies: list[str] | None = None, delay: float = 0.0):
        self.replies, self.delay, self.asked = list(replies or []), delay, []

    def stream(self, messages: list[dict]) -> Iterator[str]:
        import time
        self.asked.append([dict(m) for m in messages])
        reply = self.replies.pop(0) if self.replies else f"You said: {messages[-1]['content']}"
        for token in re.findall(r"\S+\s*", reply):
            time.sleep(self.delay)
            yield token


class OpenAICompatLLM:
    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", model: str = "", api_key: str = "", extra: dict | None = None,
                 max_tokens: int = 300, temperature: float = 0.7):
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.max_tokens, self.temperature = max_tokens, temperature
        u = urlsplit(self.base_url)
        self.local = (u.hostname or "") in LOOPBACK
        # Ollama's thinking models spend their first tokens on hidden reasoning unless told not to.
        self.extra = extra if extra is not None else ({"reasoning_effort": "none"} if u.port == 11434 else {})
        self.name = model or "(no model set)"

    def _connect(self):
        u = urlsplit(self.base_url)
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        return cls(u.hostname, u.port, timeout=120), u.path

    def models(self) -> list[str]:
        conn, path = self._connect()
        try:
            conn.request("GET", path + "/models", headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
            return [m["id"] for m in json.loads(conn.getresponse().read()).get("data", [])]
        finally:
            conn.close()

    def stream(self, messages: list[dict]) -> Iterator[str]:
        if not self.model:
            raise RuntimeError("No language model is set. Start one (for example `ollama run qwen3:4b`) or set VOXSTUDIO_LLM_MODEL.")
        body = {"model": self.model, "messages": messages, "stream": True, "max_tokens": self.max_tokens, "temperature": self.temperature, **self.extra}
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        conn, path = self._connect()
        try:
            try:
                conn.request("POST", path + "/chat/completions", body=json.dumps(body), headers=headers)
                res = conn.getresponse()
            except OSError as e:
                raise RuntimeError(f"Can't reach the language model at {self.base_url}: {e}") from None
            if res.status >= 400:
                detail = res.read().decode(errors="replace")[:300]
                raise RuntimeError(f"The language model answered {res.status}: {detail}")
            thinking, held = False, ""
            for raw in res:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                text = delta.get("content") or ""
                if not text:
                    continue
                # some servers inline the reasoning as <think>...</think>; never speak it
                held += text
                if thinking or "<think>" in held:
                    thinking = "</think>" not in held
                    if thinking:
                        continue
                    held = THINK.sub("", held)
                if "<" in held[-7:] and "<think>".startswith(held[held.rfind("<"):]):
                    continue   # might be the start of a tag; wait for more
                if held:
                    yield held
                    held = ""
            if held and not thinking:
                yield held
        finally:
            conn.close()


def pick_local_model(base_url: str = "http://127.0.0.1:11434/v1") -> str:
    """The smallest model an Ollama on this machine already has (small answers sooner), or "" if none is found."""
    u = urlsplit(base_url)
    try:
        conn = http.client.HTTPConnection(u.hostname, u.port, timeout=2)
        conn.request("GET", "/api/tags")
        models = json.loads(conn.getresponse().read()).get("models", [])
        conn.close()
        chat = [m for m in models if "embed" not in m["name"]]
        return min(chat, key=lambda m: m.get("size", 0))["name"] if chat else ""
    except (OSError, ValueError, KeyError):
        try:
            found = OpenAICompatLLM(base_url).models()
            return found[0] if found else ""
        except (OSError, ValueError, RuntimeError):
            return ""
