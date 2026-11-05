"""Turn a pasted or uploaded script into blocks.

Formats: plain text (blank lines separate blocks), Markdown (markup stripped, headings become their own block),
SRT/WebVTT captions (cues joined back into paragraphs), and dialogue ("NAME: line", one speaker per block).
"""
import re

FORMATS = ("auto", "text", "markdown", "srt", "dialogue")
SPEAKER = re.compile(r"^\s*([A-Za-z][\w .'’-]{0,29}?)\s*:\s+(\S.*)$")
CUE_TIME = re.compile(r"(\d{1,2}:)?(\d{1,2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}:)?(\d{1,2}):(\d{2})[,.](\d{3})")
MAX_SPEAKERS = 12


def _squash(text: str) -> str:
    return " ".join(text.split())


def detect(text: str) -> str:
    if CUE_TIME.search(text):
        return "srt"
    lines = [ln for ln in text.splitlines() if ln.strip()]
    hits = [SPEAKER.match(ln) for ln in lines]
    names = {m.group(1).strip().lower() for m in hits if m}
    if len(lines) >= 2 and sum(1 for m in hits if m) >= max(2, 0.6 * len(lines)) and len(names) <= MAX_SPEAKERS:
        return "dialogue"
    if re.search(r"^#{1,6}\s|^\s*[-*+]\s+\S|\*\*\S|```|\]\(https?://", text, re.M):
        return "markdown"
    return "text"


def _plain(text: str) -> list[dict]:
    return [{"text": _squash(p)} for p in re.split(r"\n\s*\n", text.replace("\r", "")) if p.strip()]


def _markdown(text: str) -> list[dict]:
    text = re.sub(r"```.*?```", "", text.replace("\r", ""), flags=re.S)       # code is not narration
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                           # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)                       # links keep their words
    text = re.sub(r"<[^>]+>", "", text)
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        lines = []
        for ln in para.splitlines():
            heading = re.match(r"^\s*#{1,6}\s+(.*?)\s*#*\s*$", ln)
            if heading:   # a heading is read on its own, with a full stop so the voice lands it
                if lines:
                    blocks.append(" ".join(lines))
                    lines = []
                title = _inline(heading.group(1))
                if title:
                    blocks.append(title if title[-1] in ".!?" else title + ".")
                continue
            if re.match(r"^\s*([-*_])\s*(\1\s*){2,}$", ln) or re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", ln):
                continue   # horizontal rules and table separators
            ln = re.sub(r"^\s*(>+|[-*+]|\d+[.)])\s+", "", ln)
            lines.append(_inline(ln.replace("|", " ")))
        if lines:
            blocks.append(" ".join(lines))
    return [{"text": _squash(b)} for b in blocks if b.strip()]


def _inline(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"*\2*", text)        # bold and italics both become spoken emphasis
    text = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"*\1*", text)
    return re.sub(r"~~(.+?)~~", r"\1", text).strip()


def _seconds(h, m, s, ms) -> float:
    return (int(h[:-1]) if h else 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _captions(text: str) -> list[dict]:
    """Cues back into paragraphs: a new block after a long gap, or at a sentence end once the block is long enough."""
    cues, cur = [], None
    for ln in text.replace("\r", "").splitlines():
        m = CUE_TIME.search(ln)
        if m:
            cur = {"start": _seconds(*m.groups()[:4]), "end": _seconds(*m.groups()[4:]), "lines": []}
            cues.append(cur)
        elif cur is not None and ln.strip() and not ln.strip().isdigit():
            cur["lines"].append(re.sub(r"<[^>]+>|\{[^}]*\}", "", ln).strip())
        elif not ln.strip():
            cur = None if cur is not None and cur["lines"] else cur
    blocks, acc, last_end = [], [], None
    for cue in cues:
        words = _squash(" ".join(cue["lines"]))
        if not words:
            continue
        joined = " ".join(acc)
        if acc and ((last_end is not None and cue["start"] - last_end > 1.5) or (joined[-1] in ".!?" and len(joined) >= 180)):
            blocks.append(joined)
            acc = []
        acc.append(words)
        last_end = cue["end"]
    if acc:
        blocks.append(" ".join(acc))
    return [{"text": b} for b in blocks]


def _dialogue(text: str) -> list[dict]:
    blocks: list[dict] = []
    names: dict[str, str] = {}   # lower-case -> first spelling seen, so "ANNA" and "Anna" are one speaker
    for ln in text.replace("\r", "").splitlines():
        if not ln.strip():
            continue
        m = SPEAKER.match(ln)
        if m:
            name = names.setdefault(m.group(1).strip().lower(), m.group(1).strip())
            blocks.append({"text": _squash(m.group(2)), "speaker": name})
        elif blocks:
            blocks[-1]["text"] += " " + _squash(ln)   # a wrapped line belongs to whoever was speaking
        else:
            blocks.append({"text": _squash(ln)})
    return blocks


def parse(text: str, fmt: str = "auto") -> dict:
    """-> {format, blocks: [{text, speaker?}], speakers: [names in order of appearance]}"""
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format '{fmt}' (use {', '.join(FORMATS)})")
    text = text or ""
    fmt = detect(text) if fmt == "auto" else fmt
    blocks = {"text": _plain, "markdown": _markdown, "srt": _captions, "dialogue": _dialogue}[fmt](text)
    speakers = list(dict.fromkeys(b["speaker"] for b in blocks if b.get("speaker")))
    if len(speakers) > MAX_SPEAKERS:
        raise ValueError(f"{len(speakers)} speakers found; that looks like plain text with colons. Import it as text.")
    return {"format": fmt, "blocks": blocks, "speakers": speakers}
