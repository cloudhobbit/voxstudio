"""Cut text into pieces for streaming: the first sentence alone, so sound starts early, then longer stretches,
which give the voice more context and fewer joins."""
import re

# A sentence ends at . ! ? or … (plus closing quotes or brackets) when whitespace and a likely sentence start follow.
END = re.compile(r"""([.!?…]+["'”’)\]]*)\s+(?=["'“‘(\[]?[A-Z0-9*\[])""")
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e", "no", "inc", "ltd", "co",
                 "fig", "approx", "dept", "est", "gen", "col", "lt", "sgt", "capt", "rev", "hon", "mt", "ft", "a.m", "p.m"}
FIRST_MIN = 12     # "Wait." alone is too short to carry a voice; join it to what follows
REST_MAX = 240     # later pieces are grouped up to about this many characters


def sentences(text: str) -> list[str]:
    out, start = [], 0
    for m in END.finditer(text):
        before = text[start:m.start()]
        last = before.split()[-1].lower().strip("\"'“‘([") if before.split() else ""
        if m.group(1).startswith(".") and (last in ABBREVIATIONS or (len(last) == 1 and last.isalpha())):
            continue   # "Dr. Smith", "J. K. Rowling": not an ending
        if before.count("[") > before.count("]") or before.count("(") > before.count(")"):
            continue   # inside a bracketed mark such as [word](/phonemes/)
        out.append(text[start:m.end(1)].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def pieces(text: str, first_min: int = FIRST_MIN, rest_max: int = REST_MAX) -> list[str]:
    """The first sentence (joined to the next while it is very short), then sentences grouped up to rest_max."""
    sents = sentences(text)
    if not sents:
        return []
    out = [sents[0]]
    i = 1
    while i < len(sents) and len(out[0]) < first_min:
        out[0] += " " + sents[i]
        i += 1
    for s in sents[i:]:
        if len(out) > 1 and len(out[-1]) + 1 + len(s) <= rest_max:
            out[-1] += " " + s
        else:
            out.append(s)
    return out
