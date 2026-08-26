"""Tests for Sherpa-ONNX ASR engine."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from asr_sherpa.engine import SherpaASREngine

MODULE = "asr_sherpa.engine"


@pytest.fixture
def sherpa(tmp_path):
    """Mock _load_sherpa internals; yield an engine factory plus mocks.

    Returns ``(factory, recognizer, stream)`` where ``factory()`` builds a
    SherpaASREngine against a real (empty) model dir — Path handling stays
    real, only the sherpa-onnx symbols are mocked.
    """
    stream = MagicMock(name="stream")
    recognizer = MagicMock(name="recognizer")
    recognizer.create_stream.return_value = stream
    recognizer_cls = MagicMock(name="OnlineRecognizer", return_value=recognizer)
    recognizer_config_cls = MagicMock(name="OnlineRecognizerConfig")

    # Order must match the tuple _load_sherpa() returns / __init__ unpacks.
    components = (
        MagicMock(name="EndpointConfig"),
        MagicMock(name="FeatureExtractorConfig"),
        MagicMock(name="OnlineCtcFstDecoderConfig"),
        MagicMock(name="OnlineLMConfig"),
        MagicMock(name="OnlineModelConfig"),
        recognizer_cls,
        recognizer_config_cls,
        MagicMock(name="OnlineTransducerModelConfig"),
    )

    with patch(f"{MODULE}._load_sherpa", return_value=components):
        yield (
            (lambda: SherpaASREngine(model_dir=str(tmp_path))),
            recognizer,
            stream,
            recognizer_config_cls,
        )


class TestEngineInit:
    def test_endpoint_detection_disabled(self, sherpa):
        """Endpoint detection is off — turn-ending is the VAD segmenter's job."""
        factory, _, _, recognizer_config_cls = sherpa
        factory()

        # OnlineRecognizerConfig is called positionally:
        # (feat, model, lm, endpoint, ctc_decoder, enable_endpoint, method)
        args, _kwargs = recognizer_config_cls.call_args
        assert args[5] is False  # enable_endpoint

    def test_missing_model_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            SherpaASREngine(model_dir=str(tmp_path / "missing"))


class TestStreamLifecycle:
    def test_start_creates_fresh_stream(self, sherpa):
        factory, recognizer, _, _ = sherpa
        stream = factory().create_stream()
        stream.start()

        recognizer.create_stream.assert_called()

    def test_process_pcm_without_session_returns_empty(self, sherpa):
        factory, _, mock_stream, _ = sherpa
        stream = factory().create_stream()

        text = stream.process_pcm(np.zeros(320, dtype=np.float32))

        assert text == ""
        mock_stream.accept_waveform.assert_not_called()

    def test_process_pcm_feeds_waveform_and_returns_text(self, sherpa):
        factory, recognizer, mock_stream, _ = sherpa
        stream = factory().create_stream()
        stream.start()

        recognizer.is_ready.return_value = False
        result = MagicMock()
        result.text = " hello world "
        recognizer.get_result.return_value = result

        pcm = np.zeros(320, dtype=np.float32)
        text = stream.process_pcm(pcm)

        assert text == "hello world"
        mock_stream.accept_waveform.assert_called_once_with(16000, pcm)

    def test_stop_flushes_decoder_and_returns_final(self, sherpa):
        factory, recognizer, mock_stream, _ = sherpa
        stream = factory().create_stream()
        stream.start()

        recognizer.is_ready.side_effect = [True, False]  # one pending decode step
        result = MagicMock()
        result.text = " done "
        recognizer.get_result.return_value = result

        text = stream.stop()

        assert text == "done"
        mock_stream.input_finished.assert_called_once()
        recognizer.decode_stream.assert_called_once_with(mock_stream)

    def test_stop_falls_back_to_last_partial(self, sherpa):
        factory, recognizer, _, _ = sherpa
        stream = factory().create_stream()
        stream.start()

        recognizer.is_ready.return_value = False
        partial = MagicMock()
        partial.text = " partial text "
        recognizer.get_result.return_value = partial
        stream.process_pcm(np.zeros(320, dtype=np.float32))

        final = MagicMock()
        final.text = ""
        recognizer.get_result.return_value = final

        assert stream.stop() == "partial text"


def test_create_engine_factory():
    """create_engine returns a SherpaASREngine with config values."""
    with patch(f"{MODULE}.SherpaASREngine.__init__", return_value=None) as mock_init:
        from asr_sherpa import create_engine

        create_engine({
            "model_dir": "/my/model",
            "num_threads": 2,
            "sample_rate": 8000,
        })

        mock_init.assert_called_once_with(
            model_dir="/my/model",
            num_threads=2,
            sample_rate=8000,
        )
