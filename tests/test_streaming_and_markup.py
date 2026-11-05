"""Streaming, inline control and loudness levelling, with the fake engine (0.2 s per word, one piece per sentence)."""
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from voxstudio import fx, markup
from voxstudio.engines.fake import FakeEngine
from voxstudio.worker import TTSWorker

SR = 24000


def wait(client, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# ---- markup ----------------------------------------------------------------------------------

def test_plain_text_is_one_segment():
    assert markup.segments("Hello there.") == [{"text": "Hello there.", "pace": 1.0, "pause": 0.0}]
    assert not markup.has_markup("Hello there.") and markup.plain("Hello   there.") == "Hello there."


def test_pauses_pace_and_emphasis_are_parsed():
    segs = markup.segments("Wait. [pause 0.8] [PAUSE .2s] Now [slow]very *slowly*[/slow] and [fast]quick[/fast] done.")
    assert segs == [{"text": "Wait.", "pace": 1.0, "pause": 1.0}, {"text": "Now", "pace": 1.0, "pause": 0.0},
                    {"text": "very *slowly*", "pace": 0.8, "pause": 0.0}, {"text": "and", "pace": 1.0, "pause": 0.0},
                    {"text": "quick", "pace": 1.2, "pause": 0.0}, {"text": "done.", "pace": 1.0, "pause": 0.0}]
    assert markup.segments("[pause 99] Late.")[0] == {"text": "", "pace": 1.0, "pause": 10.0}
    assert markup.plain("Wait. [pause 0.8] Now [slow]very *slowly*[/slow].") == "Wait. Now very slowly."
    assert [s["text"] for s in markup.segments("Go [slow]now[/slow]. Then stop.")] == ["Go", "now.", "Then stop."]
    assert markup.emphasise("a *big deal* here", lambda s: f"<{s}>") == "a <big deal> here"


@pytest.mark.parametrize("text", ["2 * 3 * 4 is 24", "a*b*c", "rated ***** by all", "[note] not a tag", "*", "* list item"])
def test_ordinary_stars_and_brackets_are_left_alone(text):
    assert markup.plain(text) == text and len(markup.segments(text)) == 1


# ---- worker and effects chain ------------------------------------------------------------------

def test_worker_streams_sentences_and_cancels_when_the_listener_leaves():
    class Slow(FakeEngine):
        def speak_stream(self, text, parts, speed):
            for piece in super().speak_stream(text, parts, speed):
                self.made = getattr(self, "made", 0) + 1
                time.sleep(0.05)
                yield piece

    engine = Slow()
    worker = TTSWorker(engine, warm=False)
    text = "One two. Three four. Five six. Seven eight. Nine ten."
    pieces = list(worker.stream(text, [("af_heart", 1.0)], 1.0))
    assert len(pieces) == 5 and [w[0] for _, ws in pieces for w in ws][:3] == ["One", "two", "Three"]
    assert pieces[1][1][0][1] == pytest.approx(0.4)   # word times count from the start of the whole text
    joined, words = worker.speak_timed(text, [("af_heart", 1.0)], 1.0)
    assert len(joined) == sum(len(a) for a, _ in pieces) and len(words) == 10
    engine.made = 0
    stream = worker.stream(text, [("af_heart", 1.0)], 1.0)
    next(stream)
    stream.close()
    time.sleep(0.4)
    assert engine.made <= 2 and worker.queued == 0


def test_worker_stream_passes_engine_errors_on():
    class Broken(FakeEngine):
        def speak_stream(self, text, parts, speed):
            yield from super().speak_stream("ok.", parts, speed)
            raise ValueError("the model fell over")

    with pytest.raises(ValueError, match="fell over"):
        list(TTSWorker(Broken(), warm=False).stream("x", [("af_heart", 1.0)], 1.0))


@pytest.mark.skipif(not fx.find_ffmpeg(), reason="ffmpeg not installed")
def test_stream_chain_matches_the_file_chain_and_starts_early(tmp_path):
    caps = fx.Capabilities.detect()
    t = np.arange(SR) / SR
    tone = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(tmp_path / "in.wav", np.concatenate([tone] * 3), SR, subtype="FLOAT")
    fx.apply_chain(tmp_path / "in.wav", tmp_path / "out.wav", -2, "none", "room", caps)
    whole, _ = sf.read(tmp_path / "out.wav", dtype="int16")
    fed = threading.Event()

    def slow_chunks():
        yield tone
        yield tone
        fed.wait(5)          # the third second only arrives after some output has been read
        yield tone

    out = bytearray()
    for data in fx.stream_chain(slow_chunks(), -2, "none", "room", caps):
        out += data
        if len(out) > SR:    # half a second of sound has left before the input ended
            fed.set()
    assert fed.is_set()
    streamed = np.frombuffer(bytes(out), dtype="<i2")
    assert abs(len(streamed) - len(whole)) < SR * 0.1
    assert np.abs(streamed[:SR].astype(int) - whole[:SR].astype(int)).mean() < 200
    assert b"".join(fx.stream_chain(iter([tone]), 0, "none", "dry", caps)) == fx.to_s16(tone)


@pytest.mark.skipif(not fx.find_ffmpeg(), reason="ffmpeg not installed")
def test_stream_chain_reports_engine_errors():
    def chunks():
        yield np.zeros(SR, dtype=np.float32)
        raise ValueError("the model fell over")

    with pytest.raises(ValueError, match="fell over"):
        list(fx.stream_chain(chunks(), 0, "none", "hall", fx.Capabilities.detect()))


# ---- API ---------------------------------------------------------------------------------------

def test_stream_route_sends_pcm_then_the_line_is_cached(client, engine):
    body = {"text": "One two three. Four five six.", "voice": "af_heart"}
    with client.stream("POST", "/api/speak/stream", json=body) as r:
        assert r.status_code == 200 and r.headers["content-type"] == "audio/pcm"
        assert r.headers["x-voxstudio-cached"] == "false" and r.headers["x-voxstudio-sample-rate"] == "24000"
        key = r.headers["x-voxstudio-key"]
        data = b"".join(r.iter_bytes())
    assert len(data) == int(1.2 * SR) * 2
    after = client.post("/api/speak", json=body).json()
    assert after["cached"] is True and after["key"] == key and len(after["words"]) == 6 and after["duration"] == pytest.approx(1.2)
    with client.stream("POST", "/api/speak/stream", json=body) as r:
        assert r.headers["x-voxstudio-cached"] == "true" and b"".join(r.iter_bytes()) == data
    assert engine.said == ["One two three. Four five six."]
    assert client.post("/api/speak/stream", json={"text": "x", "voice": "af_nobody"}).status_code == 422


def test_inline_pause_pace_and_emphasis_shape_the_audio(client, engine):
    plain = client.post("/api/speak", json={"text": "Wait. Now go.", "voice": "af_heart"}).json()
    marked = client.post("/api/speak", json={"text": "Wait. [pause 0.5] Now *go*.", "voice": "af_heart"}).json()
    assert marked["key"] != plain["key"] and marked["duration"] == pytest.approx(plain["duration"] + 0.5, abs=0.01)
    assert engine.said[-2:] == ["Wait.", "Now [go](+2)."]
    assert marked["words"][0][0] == "Wait" and marked["words"][1][1] == pytest.approx(0.7, abs=0.01)
    slow = client.post("/api/speak", json={"text": "[slow]One two three four.[/slow]", "voice": "af_heart"}).json()
    assert slow["duration"] == pytest.approx(0.8 / 0.8, abs=0.02)
    only = client.post("/api/speak", json={"text": "[pause 1]", "voice": "af_heart"}).json()
    assert only["duration"] == pytest.approx(1.0) and only["words"] == []
    assert client.post("/api/speak", json={"text": "[slow][/slow]", "voice": "af_heart"}).status_code == 422


def test_pronunciation_wins_over_emphasis_on_the_same_word(client, engine):
    client.post("/api/speak", json={"text": "*ISRO* called.", "voice": "af_heart"})
    assert engine.said[-1] == "[Iss-roh](+2) called."
    client.put("/api/pronunciations/shared/Pragyan", json={"say": "/pɹˈʌɡjɑn/"})
    client.post("/api/speak", json={"text": "*Pragyan* rolled.", "voice": "af_heart"})
    assert engine.said[-1] == "[Pragyan](/pɹˈʌɡjɑn/) rolled."


def test_captions_never_show_the_marks(client):
    p = client.post("/api/projects", json={"title": "Marks", "script": "Hello *there* friend. [pause 1] Bye [slow]now[/slow]."}).json()
    job = wait(client, client.post(f"/api/projects/{p['slug']}/export", json={"captions": ["srt"], "loudness": None}).json()["job_id"])
    assert job["status"] == "done", job["error"]
    srt = client.get("/exports/marks/marks.srt").text
    assert "Hello there friend." in srt and "Bye now." in srt and "*" not in srt and "[" not in srt
    assert job["result"]["duration"] == pytest.approx(4 * 0.2 + 1 + 0.2 / 0.8 + 0.5, abs=0.05) and job["result"]["levelled"] is None


def test_openai_pcm_is_streamed(client):
    with client.stream("POST", "/v1/audio/speech", json={"input": "One two. Three four.", "voice": "alloy", "response_format": "pcm"}) as r:
        assert r.status_code == 200 and r.headers["content-type"] == "audio/pcm" and "content-length" not in r.headers
        assert len(b"".join(r.iter_bytes())) == int(0.8 * SR) * 2


# ---- loudness ----------------------------------------------------------------------------------

@pytest.mark.skipif(not fx.find_ffmpeg(), reason="ffmpeg not installed")
def test_measure_and_gain(tmp_path):
    caps = fx.Capabilities.detect()
    t = np.arange(3 * SR) / SR
    for name, amp in (("loud", 0.5), ("quiet", 0.05)):
        sf.write(tmp_path / f"{name}.wav", (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32), SR)
    loud, quiet = fx.measure_loudness(tmp_path / "loud.wav", caps), fx.measure_loudness(tmp_path / "quiet.wav", caps)
    assert loud[0] - quiet[0] == pytest.approx(20, abs=0.5) and loud[1] == pytest.approx(-6, abs=0.5)
    assert fx.levelling_gain(*quiet) == pytest.approx(-16 - quiet[0], abs=0.01)
    assert fx.levelling_gain(-30.0, -1.5) == 0.5          # the peak ceiling holds the gain back
    sf.write(tmp_path / "silent.wav", np.zeros(SR, dtype=np.float32), SR)
    assert fx.measure_loudness(tmp_path / "silent.wav", caps) is None
    assert fx.measure_loudness(tmp_path / "loud.wav", fx.Capabilities(None)) is None


@pytest.mark.skipif(not fx.find_ffmpeg(), reason="ffmpeg not installed")
def test_export_levels_blocks_to_within_one_lu(client, workspace, tmp_path):
    caps = fx.Capabilities.detect()
    script = "One two three four five six seven eight nine ten.\n\nEleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty."
    p = client.post("/api/projects", json={"title": "Level", "script": script}).json()
    wait(client, client.post(f"/api/projects/{p['slug']}/render").json()["job_id"])
    status = client.get(f"/api/projects/{p['slug']}").json()["status"]
    quiet = workspace.cache_dir / f"{status[1]['key']}.wav"       # make the second block 14 dB quieter in the cache
    audio, _ = sf.read(quiet, dtype="float32")
    sf.write(quiet, audio * 0.2, SR, subtype="PCM_16")
    job = wait(client, client.post(f"/api/projects/{p['slug']}/export", json={"captions": []}).json()["job_id"])
    assert job["status"] == "done", job["error"]
    gains = job["result"]["levelled"]["gains"]
    assert job["result"]["levelled"]["target"] == -16 and gains[1] - gains[0] == pytest.approx(14, abs=0.6)
    out, _ = sf.read(workspace.exports / "level" / "level.wav", dtype="float32")
    half = int(2.5 * SR)
    for i, part in enumerate((out[:2 * SR], out[half:half + 2 * SR])):
        sf.write(tmp_path / f"part{i}.wav", part, SR)
    first, second = (fx.measure_loudness(tmp_path / f"part{i}.wav", caps)[0] for i in range(2))
    assert abs(first - second) < 1.0 and abs(first + 16) < 1.0
    assert client.post(f"/api/projects/{p['slug']}/export", json={"loudness": -3}).status_code == 422
