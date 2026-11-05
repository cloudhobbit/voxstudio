"""Turn a stream of model tokens into pieces worth speaking.

The first piece leaves as early as it sensibly can (a clause, or a dozen words), because the listener is waiting
in silence. After that whole sentences are sent, which sound better.
"""
import re

from ..textsplit import sentences

CLAUSE = re.compile(r"[,;:—–]\s")
MARKUP = re.compile(r"[*_#`~]+|^\s*[-•]\s+", re.M)
FIRST_MIN_WORDS = 3
FIRST_MAX_WORDS = 14


def clean(text: str) -> str:
    """Models write for the eye; drop what makes no sense aloud."""
    return " ".join(MARKUP.sub("", text).split())


class Speakable:
    def __init__(self):
        self.buf = ""
        self.sent_first = False

    def feed(self, token: str) -> list[str]:
        self.buf += token
        out = []
        if not self.sent_first:
            piece = self._first()
            if piece is None:
                return out
            out.append(piece)
            self.sent_first = True
        parts = sentences(self.buf)
        if len(parts) > 1:   # everything but the last is finished: more text followed it
            out.extend(parts[:-1])
            self.buf = self.buf[self.buf.rfind(parts[-1]):]   # keep the space that follows the unfinished part
        return [c for c in (clean(p) for p in out) if c]

    def _first(self) -> str | None:
        parts = sentences(self.buf)
        if len(parts) > 1:
            self.buf = self.buf[self.buf.index(parts[0]) + len(parts[0]):].lstrip()
            return parts[0]
        for m in CLAUSE.finditer(self.buf):
            if len(self.buf[:m.start()].split()) >= FIRST_MIN_WORDS:
                piece, self.buf = self.buf[:m.start() + 1], self.buf[m.end():]
                return piece
        words = self.buf.split()
        if len(words) > FIRST_MAX_WORDS and self.buf[-1:].isspace():
            piece, self.buf = " ".join(words[:FIRST_MAX_WORDS]), " ".join(words[FIRST_MAX_WORDS:]) + " "
            return piece
        return None

    def flush(self) -> list[str]:
        rest, self.buf = clean(self.buf), ""
        self.sent_first = True
        return [rest] if rest else []
