"""The OpenAI-compatible routes and script import through the API."""
import io

import pytest
import soundfile as sf

from voxstudio import fx


def test_speech_returns_audio_in_the_asked_format(client, engine):
    r = client.post("/v1/audio/speech", json={"model": "tts-1", "input": "Hello there friend", "voice": "alloy", "response_format": "wav"},
                    headers={"authorization": "Bearer anything"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.headers["x-voxstudio-cached"] == "false"
    audio, sr = sf.read(io.BytesIO(r.content))
    assert sr == 24000 and abs(len(audio) / sr - 0.6) < 0.05
    pcm = client.post("/v1/audio/speech", json={"input": "Hello there friend", "voice": "alloy", "response_format": "pcm"})
    assert pcm.headers["content-type"] == "audio/pcm" and len(pcm.content) == len(audio) * 2 and pcm.headers["x-voxstudio-cached"] == "true"
    flac = client.post("/v1/audio/speech", json={"input": "Hello there friend", "voice": "alloy", "response_format": "flac"})
    assert flac.content[:4] == b"fLaC" and len(engine.said) == 1


def test_speech_accepts_vox_voices_and_extras(client, engine):
    a = client.post("/v1/audio/speech", json={"input": "ISRO calling", "voice": "@host", "response_format": "wav", "speed": 1.5})
    b = client.post("/v1/audio/speech", json={"input": "ISRO calling", "voice": {"id": "af_heart:0.6,bf_emma:0.4"}, "response_format": "wav", "speed": 1.5})
    assert a.status_code == b.status_code == 200 and a.headers["x-voxstudio-key"] == b.headers["x-voxstudio-key"]
    assert engine.said[-1] == "Iss-roh calling"   # shared pronunciations apply here too


@pytest.mark.skipif(not fx.Capabilities.detect().mp3, reason="no mp3 encoder in this ffmpeg")
def test_speech_defaults_to_mp3_and_takes_effects(client):
    r = client.post("/v1/audio/speech", json={"input": "Default format", "voice": "onyx", "pitch": -2, "space": "hall"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 500


@pytest.mark.parametrize("body, param, message", [
    ({"voice": "alloy"}, "input", "required"),
    ({"input": "x" * 4097, "response_format": "wav"}, "input", "limit is 4096"),
    ({"input": "x", "response_format": "ogg9"}, "response_format", "Unknown response_format"),
    ({"input": "x", "voice": "af_nobody", "response_format": "wav"}, "voice", "Unknown voice"),
    ({"input": "x", "speed": 9, "response_format": "wav"}, "speed", "between 0.25 and 4.0"),
    ({"input": "x", "effect": "laser", "response_format": "wav"}, None, "Unknown effect"),
])
def test_speech_errors_use_the_openai_shape(client, body, param, message):
    r = client.post("/v1/audio/speech", json=body)
    err = r.json()["error"]
    assert r.status_code == 400 and message in err["message"] and err["param"] == param and err["type"] == "invalid_request_error"


def test_models_and_voices(client):
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert "tts-1" in ids and "kokoro" in ids
    v = client.get("/v1/audio/voices").json()
    assert v["aliases"]["alloy"] == "af_alloy" and any(x["id"] == "af_heart" for x in v["voices"])


def test_import_parse_route(client):
    r = client.post("/api/import/parse", json={"text": "Anna: Hi.\nBen: Hello."}).json()
    assert r["format"] == "dialogue" and r["speakers"] == ["Anna", "Ben"]
    assert client.post("/api/import/parse", json={"text": "x", "format": "docx"}).status_code == 422


def test_project_from_dialogue_maps_speakers_to_voices(client):
    p = client.post("/api/projects", json={"title": "Two Hander", "script": "ANNA: Did you hear that?\nBEN: Hear what?\nANNA: The door.",
                                           "voice": "af_heart", "voices": {"Ben": "bm_george"}}).json()
    assert [(b["speaker"], b["voice"]) for b in p["blocks"]] == [("ANNA", "af_heart"), ("BEN", "bm_george"), ("ANNA", "af_heart")]
    saved = client.put(f"/api/projects/{p['slug']}", json={"blocks": p["blocks"], "etag": p["etag"]}).json()
    assert saved["blocks"][1]["speaker"] == "BEN"   # the speaker label survives a save
    plain = client.post("/api/projects", json={"title": "Plain", "script": "One.\n\nTwo."}).json()
    assert "speaker" not in plain["blocks"][0] and len(plain["blocks"]) == 2
    bad = client.post("/api/projects", json={"title": "Bad", "script": "A: x\nB: y", "voices": {"A": "af_nobody"}})
    assert bad.status_code == 422 and "Block 1" in bad.json()["detail"]
