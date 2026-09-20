"""Empty MARVIN_LANGUAGE must autodetect, not be sent to faster-whisper as ''."""
import numpy as np

from marvin.stt.whisper_local import WhisperSegmenter, whisper_language


def test_whisper_language_blank_is_autodetect():
    assert whisper_language(None) is None
    assert whisper_language("") is None
    assert whisper_language("  ") is None
    assert whisper_language("auto") is None
    assert whisper_language("EN") == "en"


def test_segmenter_passes_none_when_language_is_empty():
    seen: dict = {}

    class Model:
        def transcribe(self, audio, language=None, **kw):
            seen["language"] = language
            return [], None

    WhisperSegmenter(Model(), "gil", lambda s: None, language="")._run_whisper(np.zeros(16, dtype=np.float32))
    assert seen["language"] is None
