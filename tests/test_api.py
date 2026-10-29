"""Every route, with the fake engine, so the suite runs in seconds."""
import time

import pytest
import soundfile as sf

from voxstudio import fx


def wait(client, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_health_reports_engine_and_capabilities(client):
    for _ in range(50):
        h = client.get("/api/health").json()
        if h["languages"]:
            break
        time.sleep(0.05)
    assert h["ok"] and h["engine"] == "fake" and h["languages"] == ["en-US", "en-GB"]
    assert set(h["capabilities"]) == {"ffmpeg", "ffmpeg_version", "rubberband", "mp3"}


def test_speak_then_cache_hit_with_words(client, engine):
    first = client.post("/api/speak", json={"text": "Hello there friend", "voice": "af_heart"}).json()
    assert first["cached"] is False and abs(first["duration"] - 0.6) < 0.05
    assert [w[0] for w in first["words"]] == ["Hello", "there", "friend"]
    again = client.post("/api/speak", json={"text": "Hello there friend", "voice": "af_heart"}).json()
    assert again["cached"] is True and again["key"] == first["key"] and again["words"] == first["words"]
    assert engine.said == ["Hello there friend"]
    wav = client.get(first["url"])
    assert wav.status_code == 200 and wav.headers["content-type"] == "audio/wav" and "immutable" in wav.headers["cache-control"]
    assert client.get("/audio/not-a-key.wav").status_code == 404
    assert client.get("/audio/../etc/passwd").status_code in (404, 422)


def test_pronunciations_and_signatures_shape_what_is_said(client, engine):
    client.post("/api/speak", json={"text": "ISRO launched.", "voice": "@host"})
    assert engine.said[-1] == "Iss-roh launched."
    client.post("/api/speak", json={"text": "ISRO launched.", "voice": "@host", "pronounce": False})
    assert engine.said[-1] == "ISRO launched."
    r1 = client.post("/api/speak", json={"text": "Same words", "voice": "af_heart"}).json()
    r2 = client.post("/api/speak", json={"text": "Same words", "voice": "@host"}).json()
    assert r1["key"] != r2["key"]


@pytest.mark.skipif(not fx.find_ffmpeg(), reason="ffmpeg not installed")
def test_effect_pitch_and_space_go_through_ffmpeg(client, workspace):
    r = client.post("/api/speak", json={"text": "Deep in a cave", "voice": "am_onyx", "pitch": -3, "effect": "deep",
                                        "space": "cave"}).json()
    info = sf.info(workspace.cache_dir / f"{r['key']}.wav")
    assert info.samplerate == 24000 and info.channels == 1 and info.duration > 0.5


@pytest.mark.parametrize("body, message", [
    ({"text": "x", "voice": "af_nobody"}, "Unknown voice"),
    ({"text": "x", "voice": "@nope"}, "Unknown signature"),
    ({"text": "x", "voice": "af_heart", "effect": "laser"}, "Unknown effect"),
    ({"text": "x", "voice": "af_heart", "space": "moon"}, "Unknown space"),
])
def test_bad_requests_say_why(client, body, message):
    r = client.post("/api/speak", json=body)
    assert r.status_code == 422 and message in r.json()["detail"]


def test_limits(client):
    assert client.post("/api/speak", json={"text": "x" * 2001, "voice": "af_heart"}).status_code == 422
    assert client.post("/api/speak", json={"text": "x", "voice": "af_heart", "speed": 3}).status_code == 422
    assert client.post("/api/speak", json={"text": "x", "voice": "af_heart", "pitch": 13}).status_code == 422


def test_batch_job_reports_progress_and_failures(client):
    job_id = client.post("/api/speak/batch", json=[{"text": "one", "voice": "af_heart"},
                                                   {"text": "two", "voice": "af_nobody"}]).json()["job_id"]
    job = wait(client, job_id)
    assert job["status"] == "done" and job["done"] == 2 and job["urls"][0] and job["urls"][1] is None
    assert job["failed"][0]["index"] == 1 and "Unknown voice" in job["failed"][0]["error"]
    assert client.get("/api/jobs/nope").status_code == 404


def test_voices_catalogue_with_library_notes(client):
    voices = client.get("/api/voices").json()["voices"]
    by_id = {v["id"]: v for v in voices}
    assert by_id["af_heart"]["name"] == "Heart" and by_id["af_heart"]["grade_note"].startswith("Trained")
    assert by_id["@host"]["kind"] == "signature" and by_id["@host"]["described"] == "60% Heart + 40% Emma"
    assert by_id["af_heart,bf_emma"]["kind"] == "blend"
    r = client.patch("/api/voices/af_heart", json={"favourite": True, "rating": 5, "tags": ["Warm"]}).json()
    assert r["entry"] == {"favourite": True, "rating": 5, "tags": ["warm"]}
    assert client.patch("/api/voices/af_nobody", json={"rating": 1}).status_code == 404
    assert client.patch("/api/voices/af_heart", json={"rating": 1, "etag": "stale"}).status_code == 409
    v = {v["id"]: v for v in client.get("/api/voices").json()["voices"]}["af_heart"]
    assert v["favourite"] and v["rating"] == 5 and v["tags"] == ["warm"]
    assert client.get("/api/sample-lines").json()["lines"]["narration"]
    e = client.get("/api/effects").json()
    assert {x["id"] for x in e["effects"]} == set(fx.EFFECTS) and {x["id"] for x in e["spaces"]} == set(fx.SPACES)


def test_signatures_crud_rename_and_guarded_delete(client):
    tag = client.get("/api/signatures").json()["etag"]
    r = client.put("/api/signatures/narrator", json={"mix": "af_heart:0.7,am_michael:0.3", "pitch": -1, "note": "calm", "etag": tag})
    assert r.status_code == 200
    assert client.put("/api/signatures/narrator", json={"mix": "af_heart"}).status_code == 422   # exists
    assert client.put("/api/signatures/narrator", json={"mix": "af_heart", "overwrite": True}).status_code == 200
    assert client.put("/api/signatures/Bad Name", json={"mix": "af_heart"}).status_code == 422
    assert client.put("/api/signatures/x", json={"mix": "@host"}).status_code == 422
    assert client.put("/api/signatures/x", json={"mix": "af_heart", "etag": "stale"}).status_code == 409
    p = client.post("/api/projects", json={"title": "Demo", "script": "Hi there.\n\nBye now.", "voice": "@narrator"}).json()
    sig = {s["name"]: s for s in client.get("/api/signatures").json()["signatures"]}["narrator"]
    assert sig["used_in"] == ["demo"] and sig["mix"] == "af_heart"
    assert client.delete("/api/signatures/narrator").status_code == 422
    r = client.post("/api/signatures/narrator/rename", json={"new_name": "teller"}).json()
    assert r["updated_projects"] == ["demo"]
    assert all(b["voice"] == "@teller" for b in client.get(f"/api/projects/{p['slug']}").json()["blocks"])
    client.delete(f"/api/projects/{p['slug']}")
    assert client.delete("/api/signatures/teller").status_code == 200
    assert client.delete("/api/signatures/teller").status_code == 404


def test_presets(client):
    assert client.put("/api/presets/villain", json={"voice": "am_onyx", "pitch": -2, "effect": "deep", "space": "cave"}).status_code == 200
    assert client.put("/api/presets/bad", json={"voice": "am_onyx", "effect": "laser"}).status_code == 422
    presets = client.get("/api/presets").json()["presets"]
    assert presets == [{"name": "villain", "voice": "am_onyx", "speed": 1.0, "pitch": -2.0, "effect": "deep", "space": "cave"}]
    assert client.delete("/api/presets/villain").status_code == 200
    assert client.delete("/api/presets/villain").status_code == 404


def test_pronunciations_shared_project_and_preview(client, engine):
    shared = client.get("/api/pronunciations").json()
    assert shared["entries"] == [{"word": "ISRO", "say": "Iss-roh", "type": "respelling", "overrides_shared": False}]
    assert client.put("/api/pronunciations/shared/Pragyan", json={"say": "/pɹˈʌɡjɑn/", "etag": shared["etag"]}).status_code == 200
    assert client.put("/api/pronunciations/shared/X", json={"say": "y", "etag": shared["etag"]}).status_code == 409
    client.post("/api/projects", json={"title": "Moon"})
    assert client.put("/api/pronunciations/project/ISRO", json={"say": "Eye-ess-ar-oh", "project": "moon"}).status_code == 200
    proj = client.get("/api/pronunciations?scope=project&project=moon").json()["entries"]
    assert proj[0]["overrides_shared"] is True
    client.post("/api/speak", json={"text": "ISRO and Pragyan", "voice": "af_heart", "project": "moon"})
    assert engine.said[-1] == "Eye-ess-ar-oh and [Pragyan](/pɹˈʌɡjɑn/)"
    hits = client.post("/api/pronunciations/preview", json={"text": "ISRO sent Pragyan", "project": "moon"}).json()["hits"]
    assert [(h["word"], h["start"]) for h in hits] == [("ISRO", 0), ("Pragyan", 10)]
    assert client.delete("/api/pronunciations/project/ISRO?project=moon").status_code == 200
    assert client.delete("/api/pronunciations/project/ISRO?project=moon").status_code == 404
    assert client.get("/api/pronunciations?scope=bogus").status_code == 422


def test_projects_crud_and_validation(client):
    r = client.post("/api/projects", json={"title": "Chapter One", "script": "First para.\n\nSecond  para\nsame block.\n\n\n"})
    assert r.status_code == 201
    p = r.json()
    assert p["slug"] == "chapter-one" and [b["text"] for b in p["blocks"]] == ["First para.", "Second para same block."]
    assert p["blocks"][0] == {"id": "b1", "text": "First para.", "voice": "af_heart", "speed": 1.0, "pitch": 0.0,
                              "effect": "none", "space": "dry", "pause": 0.5}
    listed = client.get("/api/projects").json()["projects"]
    assert listed[0]["slug"] == "chapter-one" and listed[0]["blocks"] == 2 and listed[0]["words"] == 6
    blocks = p["blocks"] + [{"id": "b3", "text": "Third.", "voice": "@host", "effect": "robot"}]
    r = client.put("/api/projects/chapter-one", json={"blocks": blocks, "title": "Chapter 1", "etag": p["etag"]})
    assert r.status_code == 200 and r.json()["title"] == "Chapter 1" and len(r.json()["blocks"]) == 3
    assert client.put("/api/projects/chapter-one", json={"blocks": blocks, "etag": p["etag"]}).status_code == 409
    bad = client.put("/api/projects/chapter-one", json={"blocks": [{"text": "x", "voice": "af_nobody"}]})
    assert bad.status_code == 422 and "Block 1" in bad.json()["detail"]
    assert client.get("/api/projects/nope").status_code == 404
    assert client.get("/api/projects/../x").status_code == 404
    assert client.delete("/api/projects/chapter-one").status_code == 200
    assert client.get("/api/projects").json()["projects"] == []


def test_cache_stats_and_trim(client):
    client.post("/api/speak", json={"text": "cache me", "voice": "af_heart"})
    assert client.get("/api/cache").json()["files"] == 1
    assert client.delete("/api/cache?older_than_days=0").json()["files"] == 0


def test_other_hosts_and_cross_site_writes_are_refused(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 403
    r = client.post("/api/speak", json={"text": "x", "voice": "af_heart"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.get("/api/health", headers={"origin": "https://evil.example"}).status_code == 200  # reads are fine


def test_placeholder_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Vox Studio" in r.text


@pytest.mark.slow
def test_real_kokoro_speaks_and_caches(tmp_path):
    from fastapi.testclient import TestClient

    from voxstudio.api import create_app
    from voxstudio.workspace import Workspace

    app = create_app(Workspace(tmp_path), engine_name="kokoro", extra_hosts={"testserver"})
    c = TestClient(app)
    started = time.time()
    r = c.post("/api/speak", json={"text": "Vox Studio is running on this machine.", "voice": "af_heart:0.7,bf_emma:0.3"}).json()
    print(f"first line: {time.time() - started:.1f}s, {r['duration']}s of audio, {len(r['words'])} words")
    assert r["duration"] > 1 and r["cached"] is False and r["words"][0][0] == "Vox"
    started = time.time()
    assert c.post("/api/speak", json={"text": "Vox Studio is running on this machine.", "voice": "af_heart:0.7,bf_emma:0.3"}).json()["cached"]
    assert time.time() - started < 0.5
