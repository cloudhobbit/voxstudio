import numpy as np
import pytest
import soundfile as sf

from voxstudio import fx
from voxstudio.specs import SpecError, describe, parse_voice, spec_of


def test_specs_parse_and_normalise():
    assert parse_voice("af_heart") == [("af_heart", 1.0)]
    assert parse_voice("af_heart,bf_emma") == [("af_heart", 0.5), ("bf_emma", 0.5)]
    assert parse_voice("af_heart:3,bf_emma:1") == [("af_heart", 0.75), ("bf_emma", 0.25)]
    assert parse_voice("@host", {"host": "af_heart:0.6,bf_emma:0.4"}) == [("af_heart", 0.6), ("bf_emma", 0.4)]
    assert parse_voice("@host", {"host": {"mix": "am_onyx"}}) == [("am_onyx", 1.0)]
    assert spec_of(parse_voice("af_heart:3,bf_emma:1")) == "af_heart:0.75,bf_emma:0.25"
    assert describe("af_heart:0.6,bf_emma:0.4") == "60% Heart + 40% Emma"
    assert describe("af_heart") == "Heart"


@pytest.mark.parametrize("spec, message", [
    ("", "Empty"), ("nope", "not a voice id"), ("af_nobody", "Unknown voice"), ("af_heart:x", "Bad weight"),
    ("af_heart:0", "positive"), ("@ghost", "Unknown signature"),
])
def test_spec_errors_say_why(spec, message):
    with pytest.raises(SpecError, match=message):
        parse_voice(spec, {})


def test_pitch_filter_falls_back_without_rubberband():
    with_rb = fx.Capabilities("ffmpeg", rubberband=True)
    without = fx.Capabilities("ffmpeg", rubberband=False)
    assert fx.pitch_filter(fx.semitones_ratio(-2), with_rb).startswith("rubberband=pitch=0.89")
    assert fx.pitch_filter(fx.semitones_ratio(-2), without) == "asetrate=21381,aresample=24000,atempo=1.12246"
    assert fx.pitch_filter(1.0, with_rb) == ""
    assert fx.chain(0, "none", "dry", without) == ""
    assert fx.chain(0, "deep", "dry", without).startswith("asetrate=")   # the effect's own pitch shift
    assert "lowpass" in fx.chain(0, "deep", "cave", without) and "aecho" in fx.chain(0, "deep", "cave", without)


def test_chain_rejects_unknown_names():
    caps = fx.Capabilities("ffmpeg")
    with pytest.raises(ValueError, match="Unknown effect"):
        fx.chain(0, "laser", "dry", caps)
    with pytest.raises(ValueError, match="Unknown space"):
        fx.chain(0, "none", "moon", caps)


@pytest.mark.skipif(not fx.find_ffmpeg(), reason="ffmpeg not installed")
@pytest.mark.parametrize("pitch, effect, space", [(0, e, "dry") for e in fx.EFFECTS] + [(0, "none", s) for s in fx.SPACES]
                         + [(-3, "none", "dry"), (5, "tiny", "hall")])
def test_every_effect_and_space_renders_with_this_ffmpeg(tmp_path, pitch, effect, space):
    caps = fx.Capabilities.detect()
    t = np.arange(fx.SAMPLE_RATE) / fx.SAMPLE_RATE
    tone = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    src, out = tmp_path / "in.wav", tmp_path / "out.wav"
    sf.write(src, tone, fx.SAMPLE_RATE, subtype="FLOAT")
    fx.apply_chain(src, out, pitch, effect, space, caps)
    audio, sr = sf.read(out, dtype="float32")
    assert sr == fx.SAMPLE_RATE and 0.8 < len(audio) / sr < 2.0 and float(np.abs(audio).max()) > 0.01


@pytest.mark.skipif(not fx.find_ffmpeg(), reason="ffmpeg not installed")
def test_fallback_pitch_keeps_duration(tmp_path):
    caps = fx.Capabilities(fx.find_ffmpeg(), rubberband=False)
    t = np.arange(2 * fx.SAMPLE_RATE) / fx.SAMPLE_RATE
    sf.write(tmp_path / "in.wav", (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), fx.SAMPLE_RATE)
    fx.apply_chain(tmp_path / "in.wav", tmp_path / "out.wav", 7, "none", "dry", caps)
    assert abs(sf.info(tmp_path / "out.wav").duration - 2.0) < 0.1
