"""Voice specs, the strings that name a voice anywhere in Vox Studio.

    "af_heart"                                    one voice
    "af_heart,bf_emma"                            equal blend
    "af_heart:0.55,bf_emma:0.30,af_nicole:0.15"   weighted blend
    "@narrator"                                   a signature voice saved in the workspace
"""
import re

from .catalogue import VOICES

Parts = list[tuple[str, float]]
_NAME = re.compile(r"^[a-z]{2}_[a-z]+$")


class SpecError(ValueError):
    pass


def signature_mix(entry) -> str:
    """A signature entry is either the mix string or {mix, speed, pitch, note}."""
    return entry["mix"] if isinstance(entry, dict) else str(entry)


def parse_voice(spec: str, signatures: dict | None = None) -> Parts:
    """Spec -> [(voice id, weight)] with weights summing to 1."""
    spec = (spec or "").strip()
    if spec.startswith("@"):
        sigs = signatures or {}
        if spec[1:] not in sigs:
            raise SpecError(f"Unknown signature voice '{spec}'. Saved ones: {', '.join(sigs) or 'none yet'}")
        spec = signature_mix(sigs[spec[1:]])
    if not spec:
        raise SpecError("Empty voice")
    parts: Parts = []
    for item in spec.split(","):
        name, _, weight = item.strip().partition(":")
        if not _NAME.match(name):
            raise SpecError(f"'{name}' is not a voice id (like af_heart) in voice '{spec}'")
        if name not in VOICES:
            raise SpecError(f"Unknown voice '{name}'")
        try:
            w = float(weight) if weight else 1.0
        except ValueError:
            raise SpecError(f"Bad weight '{weight}' in voice '{spec}'") from None
        if w <= 0:
            raise SpecError(f"Weights must be positive in voice '{spec}'")
        parts.append((name, w))
    if not parts:
        raise SpecError("Empty voice")
    total = sum(w for _, w in parts)
    return [(n, round(w / total, 4)) for n, w in parts]


def spec_of(parts: Parts) -> str:
    if len(parts) == 1:
        return parts[0][0]
    return ",".join(f"{n}:{w:.2f}" for n, w in parts)


def describe(spec: str, signatures: dict | None = None) -> str:
    parts = parse_voice(spec, signatures)
    return " + ".join(f"{round(w * 100)}% {VOICES[n]['name']}" if len(parts) > 1 else VOICES[n]["name"] for n, w in parts)
