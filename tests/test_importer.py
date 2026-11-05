import pytest

from voxstudio.importer import detect, parse


def test_plain_text_splits_on_blank_lines():
    r = parse("First para\nwraps here.\n\n\nSecond one.\r\n\r\nThird.")
    assert r["format"] == "text" and [b["text"] for b in r["blocks"]] == ["First para wraps here.", "Second one.", "Third."]
    assert r["speakers"] == [] and parse("")["blocks"] == []


def test_dialogue_gives_one_block_per_line_with_speakers():
    text = "ANNA: Did you hear that?\nBen: Hear what?\nAnna: The door.\nIt creaked again.\n\nBEN: Stay here."
    r = parse(text)
    assert r["format"] == "dialogue" and r["speakers"] == ["ANNA", "Ben"]
    assert [(b["speaker"], b["text"]) for b in r["blocks"]] == [("ANNA", "Did you hear that?"), ("Ben", "Hear what?"),
                                                                ("ANNA", "The door. It creaked again."), ("Ben", "Stay here.")]


def test_one_colon_line_is_not_dialogue():
    assert detect("Note: this is prose.\n\nIt goes on for a while and has no speakers at all.") == "text"
    assert detect("Time: 10:30 was when it happened, and nobody spoke.") == "text"


def test_markdown_is_stripped_to_words_and_keeps_emphasis():
    md = "# Chapter One\n\nThe **quick** fox, see [the docs](https://x.y/z), ran `fast`.\n\n- first point\n- second point\n\n```\ncode()\n```\n\n> quoted _line_\n\n---\n"
    r = parse(md)
    assert r["format"] == "markdown"
    assert [b["text"] for b in r["blocks"]] == ["Chapter One.", "The *quick* fox, see the docs, ran fast.", "first point second point", "quoted *line*"]


def test_captions_are_joined_back_into_paragraphs():
    srt = ("1\n00:00:00,000 --> 00:00:02,000\nHello <i>there</i>,\n\n2\n00:00:02,000 --> 00:00:04,000\nhow are you?\n\n"
           "3\n00:00:09,000 --> 00:00:11,000\nA new thought\nafter a pause.\n")
    r = parse(srt)
    assert r["format"] == "srt" and [b["text"] for b in r["blocks"]] == ["Hello there, how are you?", "A new thought after a pause."]
    vtt = "WEBVTT\n\n00:01.000 --> 00:02.000\nShort form.\n"
    assert parse("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nLong form.\n")["blocks"] == [{"text": "Long form."}]
    assert detect(vtt) in ("text", "srt")   # mm:ss cues are rare; either reading is acceptable


def test_forced_format_and_bad_format():
    assert parse("A: one\nB: two", "text")["blocks"] == [{"text": "A: one B: two"}]
    with pytest.raises(ValueError, match="Unknown format"):
        parse("x", "docx")
