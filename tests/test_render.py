"""Project rendering, captions and exports, with the fake engine (0.2 s per word)."""
import time
from itertools import pairwise

import pytest
import soundfile as sf

from voxstudio import fx
from voxstudio.render import group_captions, srt, vtt
from voxstudio.scan import candidates


def wait(client, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_captions_group_by_length_gap_and_time():
    words = [(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(30)]
    cues = group_captions(words, max_chars=20)
    assert all(len(c["text"]) <= 20 for c in cues) and cues[0]["start"] == 0 and cues[-1]["end"] > 14.5
    assert all(a["end"] <= b["start"] for a, b in pairwise(cues))
    gap = [("one", 0, 0.3), ("two", 0.4, 0.7), ("three", 3.0, 3.3)]
    assert [c["text"] for c in group_captions(gap)] == ["one two", "three"]
    assert srt(group_captions(gap)).startswith("1\n00:00:00,000 --> 00:00:01,300\none two\n\n2\n")
    assert vtt(group_captions(gap)).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.300\none two\n")
    assert group_captions([]) == []


def test_scan_finds_names_not_common_words():
    texts = ["The rover Pragyan left Vikram at dawn. Vikram waited. Today it rains in Toconao.", "ISRO is in Bengaluru."]
    found = {c["word"]: c["count"] for c in candidates(texts, known={"ISRO"})}
    assert found["Vikram"] == 2 and "Pragyan" in found and "Toconao" in found and "Bengaluru" in found
    assert "The" not in found and "Today" not in found and "ISRO" not in found


def test_render_project_reports_blocks_and_only_rerenders_changes(client, engine):
    p = client.post("/api/projects", json={"title": "Chapter One", "script": "Hello there friend.\n\nSecond block here.", "voice": "@host"}).json()
    assert all(not s["cached"] for s in p["status"]) and p["duration"] is None
    job = wait(client, client.post(f"/api/projects/{p['slug']}/render").json()["job_id"])
    assert job["status"] == "done" and job["done"] == 2 and not job["failed"]
    assert job["result"]["duration"] == pytest.approx(0.6 + 0.5 + 0.6 + 0.5, abs=0.02)
    assert job["result"]["spans"][1]["start"] == pytest.approx(1.1, abs=0.01)
    said = len(engine.said)
    p = client.get(f"/api/projects/{p['slug']}").json()
    assert all(s["cached"] for s in p["status"]) and p["duration"] == pytest.approx(2.2, abs=0.02)
    blocks = p["blocks"]
    blocks[1]["text"] = "Second block changed."
    client.put(f"/api/projects/{p['slug']}", json={"blocks": blocks, "etag": p["etag"]})
    job = wait(client, client.post(f"/api/projects/{p['slug']}/render").json()["job_id"])
    assert job["result"]["blocks"][0]["cached"] is True and job["result"]["blocks"][1]["cached"] is False
    assert len(engine.said) == said + 1
    assert client.post("/api/projects/nope/render").status_code == 404


def test_render_reports_a_bad_block_without_crashing(client, workspace):
    p = client.post("/api/projects", json={"title": "Bad", "script": "Fine line."}).json()
    blocks = p["blocks"] + [{"id": "b2", "text": "Uses a signature", "voice": "@host"}]
    client.put(f"/api/projects/{p['slug']}", json={"blocks": blocks, "etag": p["etag"]})
    workspace.signatures.path.write_text("")  # edited by hand: now b2 points at a missing signature
    assert client.get(f"/api/projects/{p['slug']}").json()["status"][1]["error"].startswith("Unknown signature")
    job = wait(client, client.post(f"/api/projects/{p['slug']}/render").json()["job_id"])
    assert job["status"] == "done" and job["failed"][0]["id"] == "b2" and job["result"]["duration"] is None


def test_export_wav_with_captions(client, workspace):
    p = client.post("/api/projects", json={"title": "Export Me", "script": "Hello there friend.\n\nSecond block, here we go."}).json()
    job = wait(client, client.post(f"/api/projects/{p['slug']}/export", json={"format": "wav", "captions": ["srt", "vtt"]}).json()["job_id"])
    assert job["status"] == "done", job["error"]
    names = [f["name"] for f in job["result"]["files"]]
    assert names == ["export-me.wav", "export-me.srt", "export-me.vtt", "timing.json"]
    info = sf.info(workspace.exports / "export-me" / "export-me.wav")
    assert info.samplerate == 24000 and info.duration == pytest.approx(job["result"]["duration"], abs=0.01)
    text = client.get("/exports/export-me/export-me.srt").text
    assert "Hello there friend." in text and "Second block, here we go." in text and "-->" in text
    assert client.get("/exports/export-me/export-me.vtt").text.startswith("WEBVTT")
    listed = client.get(f"/api/projects/{p['slug']}/exports").json()["files"]
    assert [f["name"] for f in listed] == sorted(names)
    assert client.get("/exports/export-me/../../library.yaml").status_code in (404, 422)
    assert client.get("/exports/export-me/.hidden").status_code == 404
    assert client.post(f"/api/projects/{p['slug']}/export", json={"format": "ogg"}).status_code == 422
    client.delete(f"/api/projects/{p['slug']}")
    assert not (workspace.exports / "export-me").exists()


@pytest.mark.skipif(not fx.Capabilities.detect().mp3, reason="no mp3 encoder in this ffmpeg")
def test_export_mp3(client, workspace):
    p = client.post("/api/projects", json={"title": "Mp3", "script": "Hello there."}).json()
    job = wait(client, client.post(f"/api/projects/{p['slug']}/export", json={"format": "mp3", "captions": []}).json()["job_id"])
    assert job["status"] == "done" and [f["name"] for f in job["result"]["files"]] == ["mp3.mp3", "timing.json"]
    assert (workspace.exports / "mp3" / "mp3.mp3").stat().st_size > 1000


def test_scan_and_suggest_routes(client):
    client.post("/api/projects", json={"title": "Moon", "script": "Pragyan rolled out of Vikram. Vikram stayed."})
    words = client.post("/api/pronunciations/scan", json={"project": "moon"}).json()["words"]
    assert words[0] == {"word": "Vikram", "count": 2}
    r = client.post("/api/pronunciations/suggest", json={"word": "Pragyan"})
    assert r.status_code in (200, 501)
    if r.status_code == 200:
        assert r.json()["ipa"].startswith("/") and r.json()["ipa"].endswith("/")
