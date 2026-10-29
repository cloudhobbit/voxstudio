import pytest

from voxstudio.workspace import Conflict, NotFound, Workspace, replace_top_level_block


def test_replace_block_keeps_comments():
    text = "title: X  # keep me\nblocks:\n  - id: b1\n    text: hi\n\n# trailing comment\npronunciations: {}\n"
    out = replace_top_level_block(text, "pronunciations", {"ISRO": "Iss-roh"})
    assert "# keep me" in out and "# trailing comment" in out and "ISRO: Iss-roh" in out
    out = replace_top_level_block(out, "blocks", [{"id": "b2", "text": "yo"}])
    assert "b2" in out and "b1" not in out and "ISRO: Iss-roh" in out


def test_signatures_read_both_forms_and_write_extended(tmp_path):
    ws = Workspace(tmp_path)
    ws.signatures.path.write_text("old: af_heart\n")
    entries, tag = ws.signatures.entries()
    assert entries["old"] == {"mix": "af_heart", "speed": 1.0, "pitch": 0.0, "note": ""}
    ws.signatures.put("new", "af_heart:0.6,bf_emma:0.4", 0.9, -1, "warm", tag)
    entries, tag2 = ws.signatures.entries()
    assert entries["new"]["pitch"] == -1 and entries["old"]["mix"] == "af_heart"
    with pytest.raises(ValueError, match="already exists"):
        ws.signatures.put("new", "af_heart", 1, 0, "", tag2)
    with pytest.raises(Conflict):
        ws.signatures.put("other", "af_heart", 1, 0, "", tag)   # stale etag
    ws.signatures.rename("new", "newer", None)
    assert "newer" in ws.signatures.entries()[0]
    with pytest.raises(ValueError, match="used by"):
        ws.signatures.delete("newer", None, ["demo"])
    ws.signatures.delete("newer", None, [])
    with pytest.raises(NotFound):
        ws.signatures.delete("newer", None, [])


def test_library_patch_drops_empty_fields(tmp_path):
    ws = Workspace(tmp_path)
    entry = ws.library.patch("af_heart", {"favourite": True, "rating": 4, "tags": ["Warm", "host", " "]}, None)
    assert entry == {"favourite": True, "rating": 4, "tags": ["host", "warm"]}
    entry = ws.library.patch("af_heart", {"favourite": False, "rating": None, "tags": []}, None)
    assert entry == {} and ws.library.load()[0] == {}
    with pytest.raises(ValueError, match="1-5"):
        ws.library.patch("af_heart", {"rating": 9}, None)


def test_projects_create_save_validate_delete(tmp_path):
    ws = Workspace(tmp_path)
    slug = ws.projects.create("Chapter One!")
    assert slug == "chapter-one" and ws.projects.create("Chapter One") == "chapter-one-2"
    data, tag = ws.projects.load(slug)
    data["blocks"] = [{"text": "Hello there.", "voice": "@host"}, {"text": "Bye.", "pitch": 2, "pause": 1}]
    saved, tag2 = ws.projects.save(slug, data, {"host": "af_heart"}, tag)
    assert saved["blocks"][0]["id"] == "b1" and saved["blocks"][0]["speed"] == 1.0
    assert saved["blocks"][1]["pitch"] == 2.0 and saved["blocks"][1]["pause"] == 1.0
    assert ws.projects.uses_voice("@host") == [slug] and ws.projects.uses_voice("af_heart") == [slug]
    with pytest.raises(Conflict):
        ws.projects.save(slug, data, {"host": "af_heart"}, tag)
    data["blocks"] = [{"text": "x", "voice": "@nobody"}]
    with pytest.raises(ValueError, match="Block 1: Unknown signature"):
        ws.projects.save(slug, data, {}, tag2)
    data["blocks"] = [{"text": "x", "effect": "laser"}]
    with pytest.raises(ValueError, match="unknown effect"):
        ws.projects.save(slug, data, {}, tag2)
    ws.projects.delete(slug)
    with pytest.raises(NotFound):
        ws.projects.load(slug)
    with pytest.raises(NotFound):
        ws.projects.folder("../etc")


def test_pronunciation_table_merges_project_over_shared(tmp_path):
    ws = Workspace(tmp_path)
    ws.pronunciations.put("ISRO", "Iss-roh", None)
    ws.pronunciations.put("Pragyan", "/pɹˈʌɡjɑn/", None)
    slug = ws.projects.create("p")
    data, tag = ws.projects.load(slug)
    data["pronunciations"] = {"ISRO": "Eye-ess-ar-oh"}
    ws.projects.save(slug, data, {}, tag)
    assert ws.pronunciation_table(slug) == {"ISRO": "Eye-ess-ar-oh", "Pragyan": "/pɹˈʌɡjɑn/"}
    assert ws.pronunciation_table(None)["ISRO"] == "Iss-roh"
