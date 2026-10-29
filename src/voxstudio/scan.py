"""Find words in a script that may need a pronunciation entry, and ask espeak-ng for a phonetic starting point."""
import re
import shutil
import subprocess
from collections import Counter

# Common capitalised words that are not names (sentence starts are handled separately).
COMMON = set("""
a an the and but or nor so yet for of in on at to by with from as is are was were be been being am do does did
have has had will would shall should can could may might must i you he she it we they me him her us them my your
his its our their this that these those there here when where why how what which who whom whose if then than
because while after before until since during about above below over under again further once all any both each
few more most other some such no not only own same too very just also now new one two three four five six seven
eight nine ten first second third last next yes okay oh well hello hi thanks thank please today tomorrow yesterday
monday tuesday wednesday thursday friday saturday sunday january february march april may june july august
september october november december mr mrs ms dr god earth sun moon
""".split())


def candidates(texts: list[str], known: set[str]) -> list[dict]:
    """Capitalised words that are not common, not already in a pronunciation table, ranked by how often they appear."""
    counts: Counter = Counter()
    mid_sentence: set[str] = set()
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            words = re.findall(r"[A-Za-z][A-Za-z'’-]*", sentence)
            for i, w in enumerate(words):
                if w[0].isupper() and len(w) > 1 and w.lower() not in COMMON and w not in known:
                    counts[w] += 1
                    if i > 0:
                        mid_sentence.add(w)
    # a word only ever seen at a sentence start is probably just a capitalised common word; keep it only if unusual
    out = []
    for w, n in counts.most_common():
        if w in mid_sentence or re.search(r"[A-Z].*[A-Z]|[^aeiouyAEIOUY\W]{4}|'", w):
            out.append({"word": w, "count": n})
    return out


def espeak_ipa(word: str, voice: str = "en-us") -> str | None:
    """IPA from espeak-ng, or None when it is not installed."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe or not word.strip():
        return None
    try:
        out = subprocess.run([exe, "-q", "--ipa", "-v", voice, word.strip()], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    ipa = out.strip().replace(" ", "")
    return ipa or None
