"""
SnapMemory Vision / OCR pipeline.

Local fallback: pytesseract + the tesseract binary (both actually present
and verified in this build — this is real OCR, not a stub).

Qualcomm AI Hub hook point: a vision/OCR or captioning model from AI Hub
(e.g. an ONNX text-detection/recognition model) can be wired in via
QualcommVisionProvider below. Not implemented here because it requires a
downloaded model artifact (no network in the authoring sandbox).
"""
import os
import shutil
from ai.providers import registry, ModelStatus

_TESSERACT_BIN = shutil.which("tesseract")


class TesseractOcrProvider:
    name = "Tesseract OCR (local CPU)"

    def __init__(self):
        import pytesseract
        self._pytesseract = pytesseract
        if _TESSERACT_BIN:
            pytesseract.pytesseract.tesseract_cmd = _TESSERACT_BIN

    def extract(self, image_path: str) -> dict:
        from PIL import Image
        img = Image.open(image_path)
        text = self._pytesseract.image_to_string(img)
        width, height = img.size
        description = f"Image ({width}x{height}px)."
        if text.strip():
            description += f" Contains {len(text.split())} words of detected text."
        else:
            description += " No text detected by OCR."
        return {"ocr_text": text.strip(), "description": description}


class QualcommVisionProvider:
    """Not implemented in this build — see module docstring."""
    name = "Qualcomm AI Hub vision model (not configured)"

    def __init__(self):
        raise RuntimeError(
            "No Qualcomm AI Hub vision model configured. Set "
            "SNAPMEMORY_VISION_MODEL_PATH to a downloaded AI Hub OCR/vision "
            "ONNX model to enable NPU-accelerated vision. See SNAPDRAGON_SETUP.md."
        )


def get_vision_provider():
    use_qualcomm = os.environ.get("SNAPMEMORY_VISION_PROVIDER") == "qualcomm"
    if use_qualcomm:
        try:
            p = QualcommVisionProvider()
            registry.register(ModelStatus(
                capability="vision", model_name="Qualcomm AI Hub vision model",
                runtime="ONNX Runtime", execution_provider="NPU", installed=True))
            return p
        except RuntimeError as e:
            registry.register(ModelStatus(
                capability="vision", model_name="Qualcomm AI Hub vision model",
                runtime="ONNX Runtime", execution_provider="Not installed",
                installed=False, notes=str(e)))

    if _TESSERACT_BIN:
        p = TesseractOcrProvider()
        registry.register(ModelStatus(
            capability="vision", model_name="Tesseract OCR",
            runtime=p.name, execution_provider="CPU", installed=True))
        return p

    registry.register(ModelStatus(
        capability="vision", model_name="Tesseract OCR",
        runtime="Not installed", execution_provider="Unavailable",
        installed=False, notes="tesseract binary not found on PATH."))
    return None


_provider = None


def provider():
    global _provider
    if _provider is None:
        _provider = get_vision_provider()
    return _provider


def process_image(image_path: str) -> dict:
    p = provider()
    if p is None:
        return {"ocr_text": "", "description": "OCR unavailable: tesseract not installed."}
    return p.extract(image_path)
