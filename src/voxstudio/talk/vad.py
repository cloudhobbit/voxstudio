"""End-of-turn detection from loudness alone.

A frame counts as speech when it is clearly louder than the room. The room's level is measured in the first
moments of a connection and then tracked: it drops at once when things get quieter and creeps up when they get
louder, so a fan raises the bar instead of holding a turn open. A turn starts after a few loud frames in a row
and ends after a stretch of quiet (or, as a last resort, after it has run very long).
"""
import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME = SAMPLE_RATE * FRAME_MS // 1000   # samples per frame


class EnergyVAD:
    CALIBRATE_FRAMES = 15    # the first 300 ms set the room's level
    RISE_DB = 0.04           # per frame: the room estimate climbs 2 dB a second towards a louder room
    NOISE_CEILING_DB = -20.0

    def __init__(self, start_ms: int = 60, end_silence_ms: int = 500, margin_db: float = 10.0, floor_db: float = -45.0,
                 max_turn_ms: int = 60000):
        self.start_frames = max(1, start_ms // FRAME_MS)
        self.end_silence_ms, self.max_turn_ms = end_silence_ms, max_turn_ms
        self.margin_db, self.floor_db = margin_db, floor_db
        self.noise_db = -60.0
        self.in_speech = False
        self.silence_ms = 0      # quiet since the last loud frame, while in a turn
        self._loud_run = 0
        self._seen: list[float] = []
        self._turn_ms = 0

    @staticmethod
    def level_db(frame: np.ndarray) -> float:
        x = frame.astype(np.float32) / 32768.0 if frame.dtype == np.int16 else frame.astype(np.float32)
        return float(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9)) if len(x) else -180.0

    def feed(self, frame: np.ndarray) -> str | None:
        """One 20 ms frame in; "start" when a turn begins, "end" when it is over, else None."""
        db = self.level_db(frame)
        if len(self._seen) < self.CALIBRATE_FRAMES:
            self._seen.append(db)
            self.noise_db = min(self.NOISE_CEILING_DB, sorted(self._seen)[len(self._seen) // 2])
            return None
        self.noise_db = db if db < self.noise_db else min(self.NOISE_CEILING_DB, self.noise_db + self.RISE_DB)
        loud = db > max(self.noise_db + self.margin_db, self.floor_db)
        if not self.in_speech:
            self._loud_run = self._loud_run + 1 if loud else 0
            if self._loud_run >= self.start_frames:
                self.in_speech, self.silence_ms, self._loud_run, self._turn_ms = True, 0, 0, 0
                return "start"
            return None
        self.silence_ms = 0 if loud else self.silence_ms + FRAME_MS
        self._turn_ms += FRAME_MS
        if self.silence_ms >= self.end_silence_ms or self._turn_ms >= self.max_turn_ms:
            self.in_speech = False
            return "end"
        return None

    def reset(self) -> None:
        self.in_speech, self.silence_ms, self._loud_run = False, 0, 0
