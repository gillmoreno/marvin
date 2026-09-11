import numpy as np

from marvin.stt.vad import SileroVAD, VADIterator


def test_silence_has_low_probability_and_no_events():
    vad = SileroVAD()
    assert vad(np.zeros(512, dtype=np.float32)) < 0.1
    it = VADIterator(SileroVAD(), min_silence_duration_ms=100)
    assert all(it(np.zeros(512, dtype=np.float32)) is None for _ in range(50))


def test_synthetic_burst_produces_start_then_end():
    """A noise burst is not speech, so we only check the state machine on forced probabilities."""

    class Fake:
        def __init__(self, seq):
            self.seq = iter(seq)

        def reset_states(self):
            pass

        def __call__(self, x, sr):
            return next(self.seq)

    probs = [0.1, 0.1, 0.9, 0.9, 0.9, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]
    it = VADIterator(Fake(probs), threshold=0.5, min_silence_duration_ms=100, speech_pad_ms=0)  # 100 ms = ~3.1 windows
    events = [it(np.zeros(512, dtype=np.float32)) for _ in probs]
    starts = [e for e in events if e and "start" in e]
    ends = [e for e in events if e and "end" in e]
    assert len(starts) == 1 and len(ends) == 1
    assert ends[0]["end"] > starts[0]["start"]
