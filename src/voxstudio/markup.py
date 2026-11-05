"""Inline control inside a line of text.

    [pause 0.8]          silence, in seconds (up to 10)
    *word* or *a phrase*  emphasis
    [slow] ... [/slow]    this stretch 20 % slower
    [fast] ... [/fast]    this stretch 20 % faster

The marks never reach captions: `plain()` gives the words alone. `segments()` cuts a line into stretches that are
spoken one after another, each with its own pace and the pause that follows it.
"""
import re

TAG = re.compile(r"\[pause\s+([0-9]*\.?[0-9]+)\s*s?\]|\[(slow|fast)\]|\[/(slow|fast)\]", re.I)
PAUSE_TAG = re.compile(r"\[pause\s+[0-9]*\.?[0-9]+\s*s?\]", re.I)
LEADING_PUNCTUATION = re.compile(r"^([^\w\s\[*(]+)\s*(.*)$", re.S)
EMPHASIS = re.compile(r"(?<![\w*\\])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
PACE = {"slow": 0.8, "fast": 1.2}
MAX_PAUSE = 10.0


def has_markup(text: str) -> bool:
    return bool(TAG.search(text) or EMPHASIS.search(text))


def plain(text: str) -> str:
    """The words as a reader would see them: no tags, no emphasis stars."""
    return " ".join(EMPHASIS.sub(r"\1", TAG.sub("", PAUSE_TAG.sub(" ", text))).split())


def emphasise(text: str, mark) -> str:
    """Replace each *stretch* with mark(stretch): the engine decides how emphasis is written."""
    return EMPHASIS.sub(lambda m: mark(m.group(1)), text)


def segments(text: str) -> list[dict]:
    """-> [{text, pace, pause}]: text still carries *emphasis*; pace multiplies the speed; pause follows the text."""
    out: list[dict] = []
    paces: list[float] = []
    pos = 0

    def add(chunk: str) -> None:
        chunk = " ".join(chunk.split())
        tail = LEADING_PUNCTUATION.match(chunk)
        if tail and out and out[-1]["text"] and not out[-1]["pause"]:
            out[-1]["text"] += tail.group(1)   # "[slow]now[/slow]." keeps its full stop with "now"
            chunk = tail.group(2)
        if chunk:
            out.append({"text": chunk, "pace": paces[-1] if paces else 1.0, "pause": 0.0})

    for m in TAG.finditer(text):
        add(text[pos:m.start()])
        pos = m.end()
        if m.group(1) is not None:
            seconds = float(m.group(1))
            if seconds and out:      # a pause follows whatever was just said; two in a row add up
                out[-1]["pause"] = round(min(MAX_PAUSE, out[-1]["pause"] + seconds), 3)
            elif seconds:            # the line opens with silence
                out.append({"text": "", "pace": 1.0, "pause": round(min(MAX_PAUSE, seconds), 3)})
        elif m.group(2):
            paces.append(PACE[m.group(2).lower()])
        elif paces:
            paces.pop()
    add(text[pos:])
    return out
