"""
SnapMemory AI Provider abstraction layer.

This is the single place in the codebase that decides HOW inference for a
given capability (embeddings / LLM / speech / vision) actually runs. It is
designed so a Snapdragon-optimized backend can be dropped in later without
touching any application code — and so the app is honest at all times about
what is actually executing.

Selection order (RULE 29 in the build spec):

    Qualcomm AI Hub / QNN execution provider (NPU)
        -> if unavailable
    Local ONNX Runtime (CPU/GPU execution provider actually present)
        -> if unavailable
    Local CPU fallback (pure-Python / numpy / scikit-learn implementations)

There is NO cloud provider in this chain by default (RULE 45). A cloud
fallback, if ever wired in for development convenience, must be opt-in via
SNAPMEMORY_ALLOW_CLOUD_FALLBACK=1 and is never silently substituted.

IMPORTANT — what this file does NOT do:
    It does not claim NPU execution unless onnxruntime actually reports a
    Qualcomm execution provider (QNNExecutionProvider / QualcommExecutionProvider)
    as *available* on this machine. On a normal x86 dev machine (e.g. the
    Mac this was authored on) that provider will never be present, and the
    UI will correctly show "CPU" / "Unavailable" rather than pretending.
"""
from dataclasses import dataclass, field
from typing import Optional
import platform

try:
    import onnxruntime as ort
    _ORT_AVAILABLE = True
except ImportError:
    ort = None
    _ORT_AVAILABLE = False


QUALCOMM_PROVIDER_NAMES = {"QNNExecutionProvider", "QualcommExecutionProvider"}


@dataclass
class DeviceReport:
    cpu: str
    os_name: str
    onnxruntime_installed: bool
    onnxruntime_providers: list
    npu_provider_detected: Optional[str]
    is_snapdragon_host: bool


def detect_device() -> DeviceReport:
    """Real, verifiable hardware/runtime detection. No guessing."""
    cpu = platform.processor() or platform.machine()
    os_name = f"{platform.system()} {platform.release()}"

    providers = []
    npu = None
    if _ORT_AVAILABLE:
        try:
            providers = list(ort.get_available_providers())
        except Exception:
            providers = []
        for p in providers:
            if p in QUALCOMM_PROVIDER_NAMES:
                npu = p
                break

    # A very conservative, honest heuristic: we only ever claim
    # "Snapdragon host" if the machine literally reports an ARM Qualcomm
    # string OR a Qualcomm execution provider is actually loadable. We never
    # infer this from OS name alone.
    machine = platform.machine().lower()
    is_snapdragon_host = npu is not None or "snapdragon" in cpu.lower()

    return DeviceReport(
        cpu=cpu or machine,
        os_name=os_name,
        onnxruntime_installed=_ORT_AVAILABLE,
        onnxruntime_providers=providers,
        npu_provider_detected=npu,
        is_snapdragon_host=is_snapdragon_host,
    )


@dataclass
class ModelStatus:
    capability: str          # embedding | llm | speech | vision
    model_name: str
    runtime: str              # e.g. "ONNX Runtime", "TF-IDF (pure Python)", "tesseract"
    execution_provider: str   # NPU | CPU | GPU | Unknown / Not installed
    installed: bool
    notes: str = ""


class AIProviderRegistry:
    """Central place the rest of the app asks 'what is actually running
    for capability X right now'. Populated once at startup by probing each
    subsystem (see ai/embeddings.py, ai/rag.py, ai/transcription.py,
    ai/vision.py)."""

    def __init__(self):
        self.device = detect_device()
        self._statuses: dict[str, ModelStatus] = {}

    def register(self, status: ModelStatus):
        self._statuses[status.capability] = status

    def all_statuses(self):
        return [s.__dict__ for s in self._statuses.values()]

    def status_for(self, capability: str):
        s = self._statuses.get(capability)
        return s.__dict__ if s else None


registry = AIProviderRegistry()
