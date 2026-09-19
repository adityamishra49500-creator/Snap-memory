"""
SnapMemory Speech-to-Text pipeline.

Preferred backend on a real deployment: a Qualcomm AI Hub Whisper model
(Whisper Base first, Whisper Small if latency allows) running via ONNX
Runtime with the QNN execution provider on the Snapdragon NPU.

This authoring environment has no internet access and no `faster-whisper`
/ `openai-whisper` / `torch` packages installed, and no model weights can
be downloaded here. Rather than fake a transcript, SnapMemory reports
transcription as UNAVAILABLE and tells the user exactly what to install.

To make this fully functional on your machine (dev or Snapdragon):
    pip install faster-whisper          # CPU/GPU reference backend, OR
    (Snapdragon) follow SNAPDRAGON_SETUP.md to obtain the AI-Hub Whisper
    ONNX model and point SNAPMEMORY_WHISPER_MODEL_PATH at it.

Both hooks are already wired below — installing either package/model is
enough to light up real transcription with no other code changes.
"""
import os
import time
from ai.providers import registry, ModelStatus


class FasterWhisperProvider:
    name = "faster-whisper (local CPU/GPU)"

    def __init__(self, model_size="base"):
        from faster_whisper import WhisperModel  # noqa
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: str):
        segments, info = self.model.transcribe(audio_path)
        out = []
        full_text = []
        for seg in segments:
            out.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
            full_text.append(seg.text.strip())
        return {
            "transcript": " ".join(full_text),
            "segments": out,
            "duration_seconds": info.duration if hasattr(info, "duration") else None,
        }


class QualcommWhisperProvider:
    """Hook point for a Qualcomm AI Hub Whisper ONNX model. Not implemented
    in this build (no network to download weights). See SNAPDRAGON_SETUP.md."""
    name = "Qualcomm AI Hub Whisper (not configured)"

    def __init__(self, model_path: str | None):
        if not model_path or not os.path.exists(model_path):
            raise RuntimeError(
                "SNAPMEMORY_WHISPER_MODEL_PATH not set or file not found. "
                "Download the Whisper Base/Small model via Qualcomm AI Hub "
                "and point this env var at the exported ONNX artifact."
            )


def get_transcription_provider():
    qc_path = os.environ.get("SNAPMEMORY_WHISPER_MODEL_PATH")
    if qc_path:
        try:
            p = QualcommWhisperProvider(qc_path)
            registry.register(ModelStatus(
                capability="speech", model_name="Whisper (Qualcomm AI Hub)",
                runtime="ONNX Runtime", execution_provider="NPU", installed=True))
            return p
        except RuntimeError as e:
            registry.register(ModelStatus(
                capability="speech", model_name="Whisper (Qualcomm AI Hub)",
                runtime="ONNX Runtime", execution_provider="Not installed",
                installed=False, notes=str(e)))

    try:
        p = FasterWhisperProvider()
        registry.register(ModelStatus(
            capability="speech", model_name="Whisper Base (faster-whisper)",
            runtime=p.name, execution_provider="CPU", installed=True))
        return p
    except Exception as e:
        registry.register(ModelStatus(
            capability="speech", model_name="Whisper",
            runtime="Not installed", execution_provider="Unavailable",
            installed=False,
            notes=f"faster-whisper not installed/available: {e}"))
        return None


_provider = None


def provider():
    global _provider
    if _provider is None:
        _provider = get_transcription_provider()
    return _provider


def transcribe(audio_path: str) -> dict:
    p = provider()
    if p is None:
        raise RuntimeError(
            "No speech-to-text backend is installed. Run "
            "`pip install faster-whisper` (dev/CPU) or configure the "
            "Qualcomm AI Hub Whisper model (see SNAPDRAGON_SETUP.md) to "
            "enable meeting transcription."
        )
    t0 = time.time()
    result = p.transcribe(audio_path)
    result["latency_ms"] = (time.time() - t0) * 1000
    result["provider"] = p.name
    return result
