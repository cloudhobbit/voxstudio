"""Pronunciations: replace whole words with how they should be said.

A value like "Chun-druh-yaan" is a respelling; a value between slashes ("/pɹˈʌɡjɑn/") is passed to the engine
as exact phonemes (Kokoro's [word](/phonemes/) syntax).
"""
import re


def apply(text: str, table: dict) -> str:
    for word in sorted(table, key=len, reverse=True):  # longest first, so "New Delhi" wins over "Delhi"
        say = str(table[word])
        repl = f"[{word}]({say})" if say.startswith("/") else say
        text = re.sub(rf"(?<![\w\[]){re.escape(word)}(?![\w\]])", lambda m, repl=repl: repl, text)
    return text


def preview(text: str, table: dict) -> list[dict]:
    """Which words of `text` would be replaced, with positions, for underlining in the UI."""
    hits = []
    for word in sorted(table, key=len, reverse=True):
        for m in re.finditer(rf"(?<![\w\[]){re.escape(word)}(?![\w\]])", text):
            if not any(h["start"] <= m.start() < h["end"] for h in hits):
                hits.append({"word": word, "say": str(table[word]), "start": m.start(), "end": m.end()})
    return sorted(hits, key=lambda h: h["start"])
