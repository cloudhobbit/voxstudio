"""The conversation loop, piece by piece and end to end, with fakes for hearing, thinking and speaking."""
import http.server
import json
import threading
import time

import numpy as np
import pytest

from voxstudio.talk.llm import FakeLLM, OpenAICompatLLM
from voxstudio.talk.loop import Conversation, Persona
from voxstudio.talk.speakable import Speakable, clean
from voxstudio.talk.stt import FakeSTT
from voxstudio.talk.vad import FRAME, EnergyVAD
from voxstudio.talk.ws import TalkParts

RATE = 16000


def tone(seconds: float, amp: float = 0.3) -> bytes:
    t = np.arange(int(seconds * RATE)) / RATE
    return (amp * 32767 * np.sin(2 * np.pi * 220 * t)).astype("<i2").tobytes()


def quiet(seconds: float, amp: float = 0.0005) -> bytes:
    rng = np.random.default_rng(0)
    return (amp * 32767 * rng.standard_normal(int(seconds * RATE))).astype("<i2").tobytes()


def frames(pcm: bytes):
    a = np.frombuffer(pcm, dtype="<i2")
    return [a[i:i + FRAME] for i in range(0, len(a) - FRAME + 1, FRAME)]


# ---- end-of-turn detection ---------------------------------------------------------------------

def test_vad_marks_the_start_and_end_of_a_turn():
    vad = EnergyVAD(end_silence_ms=500)
    events = [(i, e) for i, f in enumerate(frames(quiet(0.5) + tone(1.0) + quiet(1.0))) if (e := vad.feed(f))]
    assert [e for _, e in events] == ["start", "end"]
    assert events[0][0] == 25 + 2          # three loud frames in a row, 60 ms after the tone begins
    assert events[1][0] == 25 + 50 + 24    # 500 ms of quiet after it stops


def test_vad_ignores_clicks_and_a_short_gap_inside_a_turn():
    vad = EnergyVAD()
    assert [vad.feed(f) for f in frames(quiet(0.3) + tone(0.04) + quiet(0.3))] == [None] * 32
    vad = EnergyVAD()
    events = [e for f in frames(quiet(0.3) + tone(0.5) + quiet(0.3) + tone(0.5) + quiet(0.8)) if (e := vad.feed(f))]
    assert events == ["start", "end"]     # a 300 ms breath does not end the turn


def test_vad_learns_a_noisy_room():
    vad = EnergyVAD()
    noisy = quiet(2.0, amp=0.02)           # a steady fan, far above the default floor
    events = [e for f in frames(noisy + tone(0.6) + quiet(1.0, amp=0.02)) if (e := vad.feed(f))]
    assert events[-2:] == ["start", "end"] and vad.noise_db > -45


# ---- pieces worth speaking -----------------------------------------------------------------------

def feed_all(text: str) -> list[str]:
    s, out = Speakable(), []
    for token in [w + " " for w in text.split()]:
        out += s.feed(token)
    return out + s.flush()


def test_the_first_piece_leaves_at_a_clause_then_sentences_follow():
    # "In Kyoto," is two words: too little to open with, so the first piece runs to the end of the sentence
    assert feed_all("In Kyoto, visit the red gates at dawn. Then walk the bamboo grove. It is quiet early") == [
        "In Kyoto, visit the red gates at dawn.", "Then walk the bamboo grove.", "It is quiet early"]
    out = feed_all("The tallest mountain in the world is Everest, at about 8,849 metres. It is in Nepal.")
    assert out == ["The tallest mountain in the world is Everest,", "at about 8,849 metres.", "It is in Nepal."]
    assert feed_all("Sure. Here is the answer you wanted.") == ["Sure.", "Here is the answer you wanted."]


def test_a_long_first_clause_is_cut_after_a_dozen_words_and_nothing_is_lost():
    text = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen. Then more."
    out = feed_all(text)
    assert out[0] == "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
    assert " ".join(out) == text


def test_markup_from_the_model_is_not_spoken():
    assert clean("**Sure!** Here's a `tip`:\n- _first_ thing") == "Sure! Here's a tip: first thing"
    assert feed_all("# Title\n\nHello *there*, friend.")[-1].endswith("friend.") and "*" not in "".join(feed_all("Hello *there*, friend."))


# ---- the language model client ---------------------------------------------------------------------

@pytest.fixture
def sse_server():
    state = {"chunks": [], "status": 200, "seen": None, "closed_early": False}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"data": [{"id": "m-small"}, {"id": "m-big"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            state["seen"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["auth"] = self.headers.get("Authorization")
            self.send_response(state["status"])
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                if state["status"] != 200:
                    self.wfile.write(b'{"error": "model not found"}')
                    return
                for c in state["chunks"]:
                    self.wfile.write(f"data: {json.dumps({'choices': [{'delta': c}]})}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.01)
                self.wfile.write(b"data: [DONE]\n\n")
            except (BrokenPipeError, ConnectionResetError):
                state["closed_early"] = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1", state
    server.shutdown()


def test_llm_streams_content_and_never_the_thinking(sse_server):
    url, state = sse_server
    state["chunks"] = [{"role": "assistant", "content": ""}, {"reasoning": "let me think"}, {"content": "<thi"}, {"content": "nk>secret plan</think>"},
                       {"content": "Hello"}, {"content": " there."}, {"content": " 2 < 3 is true."}]
    llm = OpenAICompatLLM(url, "m-small", api_key="k")
    assert "".join(llm.stream([{"role": "user", "content": "hi"}])) == "Hello there. 2 < 3 is true."
    assert state["seen"]["model"] == "m-small" and state["seen"]["stream"] is True and state["auth"] == "Bearer k"
    assert llm.local is True and llm.models() == ["m-small", "m-big"]
    assert "reasoning_effort" not in state["seen"]
    assert OpenAICompatLLM("http://127.0.0.1:11434/v1", "x").extra == {"reasoning_effort": "none"}
    assert OpenAICompatLLM("https://api.example.com/v1", "x").local is False


def test_llm_errors_say_what_happened(sse_server):
    url, state = sse_server
    state["status"] = 404
    with pytest.raises(RuntimeError, match=r"answered 404.*model not found"):
        list(OpenAICompatLLM(url, "nope").stream([{"role": "user", "content": "hi"}]))
    with pytest.raises(RuntimeError, match="No language model is set"):
        list(OpenAICompatLLM(url, "").stream([]))
    with pytest.raises(RuntimeError, match="Can't reach"):
        list(OpenAICompatLLM("http://127.0.0.1:9/v1", "x").stream([]))


def test_closing_the_stream_hangs_up_on_the_model(sse_server):
    url, state = sse_server
    state["chunks"] = [{"content": f"word{i} "} for i in range(400)]
    stream = OpenAICompatLLM(url, "m").stream([{"role": "user", "content": "hi"}])
    assert next(stream).startswith("word0")
    stream.close()
    time.sleep(0.3)
    assert state["closed_early"]


# ---- the conversation -------------------------------------------------------------------------------

class Recorder:
    def __init__(self):
        self.items, self.lock = [], threading.Lock()

    def __call__(self, item):
        with self.lock:
            self.items.append(item)

    def events(self):
        return [i for i in self.items if isinstance(i, dict)]

    def types(self):
        return [e["type"] for e in self.events()]

    def audio(self):
        return b"".join(i for i in self.items if isinstance(i, bytes | bytearray))

    def one(self, kind):
        return next(e for e in self.events() if e["type"] == kind)


@pytest.fixture
def talk(client):
    made = []

    def make(stt=None, llm=None, persona=None, **kw):
        rec = Recorder()
        conv = Conversation(client.app.state.synth, stt or FakeSTT(["What is the tallest mountain?"]),
                            llm or FakeLLM(["It is Everest, in Nepal. About 8,849 metres."]), persona, rec, **kw)
        made.append(conv)
        return conv, rec

    yield make
    for c in made:
        c.close()


def test_a_spoken_turn_is_heard_answered_and_measured(talk):
    stt, llm = FakeSTT(["What is the tallest mountain?"]), FakeLLM(["It is Everest, in Nepal. About 8,849 metres."])
    conv, rec = talk(stt, llm)
    conv.feed(quiet(0.3) + tone(1.2) + quiet(0.8))
    assert conv.wait(10)
    assert rec.types()[:3] == ["speech_start", "thinking", "final"] and rec.one("final")["text"] == "What is the tallest mountain?"
    assert [e["text"] for e in rec.events() if e["type"] == "speaking"] == ["It is Everest,", "in Nepal.", "About 8,849 metres."]
    assert len(rec.audio()) == int(8 * 0.2 * 24000) * 2            # eight words from the fake voice, 24 kHz 16-bit
    m = rec.one("metrics")
    assert m["eager_stt"] is True and m["end_silence_ms"] == 500 and m["from_speech_end_ms"] == m["voice_to_voice_ms"] + 500
    assert {"stt_ms", "llm_first_token_ms", "llm_first_piece_ms", "tts_first_audio_ms", "reply_ms"} <= set(m)
    assert rec.events()[-1] == {"type": "done", "text": "It is Everest, in Nepal. About 8,849 metres.", "interrupted": False}
    assert conv.history == [{"role": "user", "content": "What is the tallest mountain?"}, {"role": "assistant", "content": "It is Everest, in Nepal. About 8,849 metres."}]
    assert llm.asked[0][0]["role"] == "system" and llm.asked[0][-1]["content"] == "What is the tallest mountain?"
    # transcription began during the closing silence, on about 200 ms of lead-in + the speech + 250 ms of quiet
    assert len(stt.heard) == 1 and abs(stt.heard[0] / RATE - (0.2 + 1.2 + 0.25)) < 0.1


def test_the_wait_is_measured_to_the_first_sound_not_the_last(talk):
    conv, rec = talk(llm=FakeLLM(["First piece here now. " + "Then a later sentence follows. " * 6], delay=0.03))
    conv.say("go")
    assert conv.wait(20)
    m = rec.one("metrics")
    assert m["voice_to_voice_ms"] < m["reply_ms"] / 2 and m["tts_first_audio_ms"] < 200


def test_talking_again_after_a_pause_restarts_the_hearing(talk):
    stt = FakeSTT(["first try", "the whole thing"])
    conv, rec = talk(stt, FakeLLM(["Okay."]))
    conv.feed(quiet(0.3) + tone(0.6) + quiet(0.35) + tone(0.6) + quiet(0.8))   # a 350 ms breath: longer than eager, shorter than the end
    assert conv.wait(10)
    assert rec.one("final")["text"] == "the whole thing" and len(stt.heard) == 2 and stt.heard[1] > stt.heard[0]
    assert rec.types().count("speech_start") == 1


def test_a_cough_is_not_a_turn_and_silence_from_the_ears_is_not_answered(talk):
    conv, rec = talk()
    conv.feed(quiet(0.3) + tone(0.1) + quiet(0.8))
    assert rec.types() == ["speech_start", "listening"] and conv.history == []
    conv, rec = talk(FakeSTT(["  "]))
    conv.feed(quiet(0.3) + tone(1.0) + quiet(0.8))
    assert conv.wait(10) and rec.types() == ["speech_start", "thinking", "listening"]


def test_speaking_over_the_reply_stops_it(talk):
    llm = FakeLLM(["One two three four. " * 30, "Sorry, go on."], delay=0.01)
    conv, rec = talk(FakeSTT(["tell me a long story", "stop"]), llm)
    conv.feed(quiet(0.3) + tone(1.0) + quiet(0.8))
    deadline = time.time() + 5
    while "speaking" not in rec.types() and time.time() < deadline:
        time.sleep(0.01)
    spoken_before = len([e for e in rec.events() if e["type"] == "speaking"])
    conv.feed(tone(0.8) + quiet(0.8))                      # the person talks over it
    assert conv.wait(10)
    types = rec.types()
    assert "interrupted" in types and types.index("interrupted") > types.index("speaking")
    first_done = next(e for e in rec.events() if e["type"] == "done")
    assert first_done["interrupted"] is True and len(first_done["text"]) < len("One two three four. " * 30)
    assert spoken_before < 30
    assert conv.history[1]["content"].endswith("…") and conv.history[-1] == {"role": "assistant", "content": "Sorry, go on."}
    assert rec.events()[-1] == {"type": "done", "text": "Sorry, go on.", "interrupted": False}


def test_push_to_talk_typed_turns_and_a_greeting(talk):
    conv, rec = talk(FakeSTT(["held the button"]), FakeLLM(["Got it.", "Typed reply."]), Persona(voice="@host", greeting="Hello, I am ready."))
    conv.greet()
    assert conv.wait(10) and rec.one("speaking")["text"] == "Hello, I am ready." and conv.history[0]["role"] == "assistant"
    conv.begin_turn()
    conv.feed(quiet(1.0, amp=0.0001))                      # push-to-talk ignores loudness: whatever is held is the turn
    conv.end_turn()
    assert conv.wait(10) and rec.one("final")["text"] == "held the button"
    assert rec.one("metrics")["end_silence_ms"] == 0 and rec.one("metrics")["eager_stt"] is False
    conv.say("typed words")
    assert conv.wait(10) and rec.events()[-1]["text"] == "Typed reply." and conv.history[-2]["content"] == "typed words"
    with pytest.raises(ValueError, match="Unknown voice"):
        talk(persona=Persona(voice="af_nobody"))


def test_a_failing_model_is_reported_not_swallowed(talk):
    class Broken(FakeLLM):
        def stream(self, messages):
            raise RuntimeError("Can't reach the language model at http://x")
            yield ""

    conv, rec = talk(llm=Broken())
    conv.say("hello")
    assert conv.wait(10) and rec.events()[-1] == {"type": "error", "message": "Can't reach the language model at http://x"}


# ---- the WebSocket ---------------------------------------------------------------------------------

def read_until(ws, kind, limit=200):
    seen, audio = [], 0
    for _ in range(limit):
        msg = ws.receive()
        if msg.get("bytes") is not None:
            audio += len(msg["bytes"])
            continue
        event = json.loads(msg["text"])
        seen.append(event)
        if event["type"] == kind:
            return seen, audio
    raise AssertionError(f"no {kind} in {[e['type'] for e in seen]}")


def test_websocket_conversation(client):
    client.app.state.talk.stt, client.app.state.talk.llm = FakeSTT(["hello there"]), FakeLLM(["Hi! How can I help?", "Typed answer."])
    with client.websocket_connect("/api/talk") as ws:
        ws.send_text(json.dumps({"type": "text", "text": "too early"}))
        assert json.loads(ws.receive()["text"])["type"] == "error"
        ws.send_text(json.dumps({"type": "start", "persona": {"voice": "af_nobody"}}))
        assert "Unknown voice" in json.loads(ws.receive()["text"])["message"]
        ws.send_text(json.dumps({"type": "start", "persona": {"voice": "bf_emma", "speed": 1.0}, "end_silence_ms": 400}))
        ready = json.loads(ws.receive()["text"])
        assert ready == {"type": "ready", "stt": "fake", "llm": "fake", "llm_local": True, "mic_rate": 16000, "speech_rate": 24000}
        audio = quiet(0.3) + tone(1.0) + quiet(0.8)
        for i in range(0, len(audio), 3200):
            ws.send_bytes(audio[i:i + 3200])
        seen, n = read_until(ws, "done")
        assert [e["type"] for e in seen][:3] == ["speech_start", "thinking", "final"] and seen[2]["text"] == "hello there"
        assert n == int(5 * 0.2 * 24000) * 2 and seen[-1]["text"] == "Hi! How can I help?"
        ws.send_text(json.dumps({"type": "text", "text": "and typed"}))
        seen, _ = read_until(ws, "done")
        assert seen[-1]["text"] == "Typed answer."


def test_websocket_refuses_other_hosts_and_origins(client):
    from starlette.websockets import WebSocketDisconnect
    for headers in ({"host": "evil.example"}, {"origin": "https://evil.example"}):
        with pytest.raises(WebSocketDisconnect) as e, client.websocket_connect("/api/talk", headers=headers):
            pass
        assert e.value.code == 1008


def test_health_describes_talk(client):
    t = client.get("/api/health").json()["talk"]
    assert t["stt"] == "fake" and t["llm"] == "fake" and t["llm_local"] is True and "available" in t and t["default_system"]
    assert TalkParts(fake=True).describe()["llm"] == "fake"
