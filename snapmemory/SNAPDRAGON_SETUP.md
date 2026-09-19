# SNAPDRAGON_SETUP.md — Running SnapMemory on a Snapdragon-powered HP PC

This document explains how to move SnapMemory from local-fallback mode (TF-IDF embeddings,
extractive answering, no transcription) to full Snapdragon-accelerated mode on the actual
target hardware. **None of these steps could be completed in the authoring sandbox** (no
internet access, no Snapdragon hardware) — they are written from Qualcomm's published AI Hub
documentation and are the exact integration points already wired into the codebase.

## 0. Prerequisites

- An HP laptop with a Snapdragon X Series (or later) processor, running Windows 11 on ARM.
- Python 3.10+ for ARM64 (Qualcomm/Microsoft provide ARM64-native Python builds; using x64
  Python under emulation will work but will not use the NPU).
- The [Qualcomm AI Hub](https://aihub.qualcomm.com/) account and CLI:
  ```bash
  pip install qai-hub
  qai-hub configure --api_token <YOUR_TOKEN>
  ```
- `onnxruntime-qnn` (the Qualcomm QNN execution provider build of ONNX Runtime), which exposes
  `QNNExecutionProvider` to `onnxruntime.get_available_providers()` — this is exactly what
  `ai/providers.py::detect_device()` checks for.

## 1. Verify NPU detection

After installing `onnxruntime-qnn` on the Snapdragon device, run:

```bash
python -c "from ai.providers import detect_device; print(detect_device())"
```

You should see `npu_provider_detected='QNNExecutionProvider'` and `is_snapdragon_host=True`.
If you don't, the rest of the app will correctly continue reporting "CPU" / "Not detected" —
it will not fabricate NPU execution, by design.

## 2. Embedding model

1. On [AI Hub Models](https://aihub.qualcomm.com/models), obtain (or export via AI Hub) a
   sentence-embedding model as ONNX, targeted at your specific Snapdragon device.
2. Set in `.env`:
   ```
   SNAPMEMORY_EMBEDDING_PROVIDER=onnx
   SNAPMEMORY_EMBEDDING_MODEL_PATH=C:\path\to\embedding_model.onnx
   ```
3. Implement the body of `OnnxEmbeddingProvider` in `ai/embeddings.py` to load the model via
   `onnxruntime.InferenceSession(model_path, providers=["QNNExecutionProvider", "CPUExecutionProvider"])`
   and run inference. No other file needs to change — `ai/rag.py` and the ingestion pipeline
   consume `embeddings.embed_texts()` / `embed_query()` only.

## 3. Whisper (meeting transcription)

1. Obtain the AI-Hub-optimized Whisper model (Base first; Small if latency on your target
   device is acceptable — see AI Hub's published latency numbers for your specific device
   before committing to Small).
2. Set:
   ```
   SNAPMEMORY_WHISPER_MODEL_PATH=C:\path\to\whisper_base.onnx
   ```
3. Implement `QualcommWhisperProvider.transcribe()` in `ai/transcription.py` (currently a
   documented stub that raises rather than fakes a transcript) using the AI Hub model's
   documented input/output format (mel-spectrogram in, token ids out, decoded via the
   tokenizer AI Hub ships alongside the model).
4. No changes needed to `app.py` or the meeting-upload flow — `transcription.transcribe()` is
   the only entry point they call.

## 4. Vision / OCR (optional upgrade over Tesseract)

1. Obtain an AI Hub OCR/vision model as ONNX.
2. Set `SNAPMEMORY_VISION_PROVIDER=qualcomm` and `SNAPMEMORY_VISION_MODEL_PATH=...`.
3. Implement `QualcommVisionProvider` in `ai/vision.py`. Tesseract remains the fallback if this
   isn't configured — it is a real, working local OCR path, not a placeholder.

## 5. Local LLM (generative answers)

The current `LocalExtractiveAnswerer` in `ai/rag.py` never hallucinates because it only ever
stitches together sentences that literally exist in retrieved chunks. To upgrade to fluent
generative answers while keeping that guarantee:

1. Choose a small instruction-tuned model AI Hub supports for your Snapdragon device (or a
   GGUF model run via `llama-cpp-python` as a CPU/GPU reference path).
2. Set `SNAPMEMORY_LLM_PROVIDER=local_llm`.
3. Implement `LocalLlmAnswerer.answer()` in `ai/rag.py`. Use a system prompt that enforces:
   "Answer using ONLY the provided context. If the context is insufficient, say so explicitly.
   Never state a fact, name, date, or decision that is not present in the context."
4. Keep citation construction exactly as-is (`ask()` already builds citations from the
   retrieved chunk set independently of how the answer text was generated).

## 6. Offline testing

Once models are installed locally:

1. Disable networking on the device (airplane mode, or disconnect Wi-Fi/Ethernet).
2. Confirm document import, image OCR, Ask, and (if configured) transcription still work.
3. The Privacy Center's "Internet required: NO" / "Cloud API calls: 0" should remain accurate
   throughout — if it isn't, something introduced a network dependency and should be reverted.

## 7. Benchmarking on-device

Use the built-in benchmark (Performance tab → "Start Benchmark", or `POST /api/benchmark/run`)
to record real embedding throughput, retrieval latency, and end-to-end query latency on the
actual Snapdragon hardware. Export results via "Export JSON" for your submission.

## Record what you actually used

Once configured, update the table in `README.md` and note here:

- Embedding model: ___________
- Whisper model: ___________
- Vision model (if used): ___________
- LLM (if used): ___________
- Measured NPU inference latency (from the benchmark): ___________
