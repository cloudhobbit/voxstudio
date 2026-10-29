"""The voice catalogue: ids, display names and plain-language notes.

Grades come from Kokoro's VOICES.md (quality and amount of training data). A and B voices sound the most
natural; C and D voices are usable for side characters, especially with an effect on top.
"""

GRADE_NOTES = {
    "A": "Trained on many hours of clean audio: natural on almost any line.",
    "B": "Well trained: natural on most lines, occasionally flat on long ones.",
    "C": "Average training data: fine for shorter lines and characters.",
    "D": "Little training data: can sound thin; good for minor characters or under an effect.",
    "F": "Very little data: use only with heavy effects.",
}


def grade_note(grade: str) -> str:
    return GRADE_NOTES.get(grade[:1], "")


def _v(name, accent, gender, grade, character, *uses):
    language = {"US": "en-US", "UK": "en-GB", "Hindi": "hi-IN"}[accent]
    return {"name": name, "accent": accent, "language": language, "gender": gender, "grade": grade,
            "character": character, "uses": list(uses)}


VOICES = {
    "af_heart":    _v("Heart", "US", "F", "A", "warm, clear, friendly", "narrator", "explainer", "facts"),
    "af_bella":    _v("Bella", "US", "F", "A-", "bright, energetic, upbeat", "host", "shorts", "countdown"),
    "af_nicole":   _v("Nicole", "US", "F", "B-", "soft, close to the mic, intimate", "mystery", "bedtime", "inner voice"),
    "af_aoede":    _v("Aoede", "US", "F", "C+", "even, pleasant", "supporting"),
    "af_kore":     _v("Kore", "US", "F", "C+", "clear, slightly formal", "supporting"),
    "af_sarah":    _v("Sarah", "US", "F", "C+", "calm, matter-of-fact", "reporter", "scientist", "news"),
    "af_alloy":    _v("Alloy", "US", "F", "C", "neutral, steady", "side character"),
    "af_nova":     _v("Nova", "US", "F", "C", "cool, precise", "side character", "computer"),
    "af_sky":      _v("Sky", "US", "F", "C-", "young, light", "young character"),
    "af_jessica":  _v("Jessica", "US", "F", "D", "plain, quiet", "minor character"),
    "af_river":    _v("River", "US", "F", "D", "relaxed, low-key", "minor character"),
    "am_michael":  _v("Michael", "US", "M", "C+", "steady, trustworthy", "narrator", "documentary"),
    "am_fenrir":   _v("Fenrir", "US", "M", "C+", "tough, intense", "soldier", "villain"),
    "am_puck":     _v("Puck", "US", "M", "C+", "lively, playful", "comic relief", "podcaster", "sidekick"),
    "am_echo":     _v("Echo", "US", "M", "D", "flat, quiet", "minor character"),
    "am_eric":     _v("Eric", "US", "M", "D", "plain, mid-range", "minor character"),
    "am_liam":     _v("Liam", "US", "M", "D", "young, casual", "young man"),
    "am_onyx":     _v("Onyx", "US", "M", "D", "deep, cold", "antagonist", "trailer"),
    "am_adam":     _v("Adam", "US", "M", "F+", "rough", "only with heavy effects"),
    "am_santa":    _v("Santa", "US", "M", "D-", "jolly, old", "cartoon grandpa"),
    "bf_emma":     _v("Emma", "UK", "F", "B-", "polished, measured", "narrator", "history", "documentary"),
    "bf_isabella": _v("Isabella", "UK", "F", "C", "gentle, articulate", "supporting"),
    "bf_alice":    _v("Alice", "UK", "F", "D", "older, wise", "elder", "mentor"),
    "bf_lily":     _v("Lily", "UK", "F", "D", "young, bright", "young character"),
    "bm_george":   _v("George", "UK", "M", "C", "deep, storytelling", "storyteller", "trailer"),
    "bm_fable":    _v("Fable", "UK", "M", "C", "warm, theatrical", "fairy tale", "narrator"),
    "bm_lewis":    _v("Lewis", "UK", "M", "D+", "older, kindly", "mentor", "elder"),
    "bm_daniel":   _v("Daniel", "UK", "M", "D", "plain, steady", "side character"),
    "hf_alpha":    _v("Alpha", "Hindi", "F", "C", "clear Hindi", "narrator"),
    "hf_beta":     _v("Beta", "Hindi", "F", "C", "softer Hindi", "narrator"),
    "hm_omega":    _v("Omega", "Hindi", "M", "C", "steady Hindi", "narrator"),
    "hm_psi":      _v("Psi", "Hindi", "M", "C", "lighter Hindi", "narrator"),
}

# Preset blends: equal mixes that give distinct new voices for bigger casts.
BLENDS = {
    "af_heart,bf_emma":     "Warm narrator with a touch of British polish",
    "af_bella,af_nicole":   "Energetic but softer and breathier",
    "am_michael,bm_george": "Deep, neutral-accent male narrator",
    "am_fenrir,am_onyx":    "Hard, cold male: villain or soldier",
    "am_puck,af_sky":       "Youthful, cartoonish character",
}

# Lines the Library plays so voices can be compared on the same words.
SAMPLE_LINES = {
    "narration": "Seventy-two hours earlier, I was certain I knew who the monsters were.",
    "facts": "Did you know the Moon is drifting away from Earth, about four centimetres every year?",
    "story": "The door creaked open, and for a moment nobody in the room dared to breathe.",
    "kids": "Hello, little explorers! Today we are going on an adventure to the bottom of the sea.",
    "hype": "This is it. The biggest launch of the year, and you are watching it live!",
    "news": "Good evening. Markets closed higher today after the central bank held rates steady.",
    "dialogue": "Look, I never said it would be easy. I said it would be worth it.",
    "hindi": "नमस्ते, आज हम चाँद के बारे में कुछ रोचक बातें जानेंगे।",
}
