# TROUBLESHOOTING.md

## "OCR unavailable: tesseract not installed"

Install the tesseract binary (not just the Python package):
- macOS: `brew install tesseract`
- Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
- Windows: https://github.com/UB-Mannheim/tesseract/wiki, then add the install dir to PATH.

Restart the app after installing — provider detection happens once at process start.

## "No speech-to-text backend is installed" when uploading audio

Either:
```bash
pip install faster-whisper
```
and re-upload (CPU/GPU reference path, works on any machine), or configure the Qualcomm AI Hub
Whisper model per `SNAPDRAGON_SETUP.md` on the target Snapdragon device.

## "The file already exists in SnapMemory"

SnapMemory hashes every file (SHA-256) and rejects re-importing an identical file by default.
This is intentional duplicate detection, not a bug. To force re-indexing, delete the existing
entry first (Documents/Meetings/Images tab → ✕) or extend the upload form with
`duplicate_action=replace`.

## Performance tab shows "CPU" instead of "NPU"

This is expected and correct on any machine without a working Qualcomm QNN execution provider
— including the author's development machine. See `SNAPDRAGON_SETUP.md` to enable real NPU
execution on Snapdragon hardware. The app will never claim NPU execution it hasn't verified via
`onnxruntime.get_available_providers()`.

## Retrieval / Ask returns weak or irrelevant answers

The local-fallback embedding model is TF-IDF, which is good at exact term overlap and weaker
at paraphrase/semantic matching than a neural embedding model. Try:
- Rephrasing the question using words that actually appear in your documents.
- Configuring a real Qualcomm AI Hub embedding model (`SNAPMEMORY_EMBEDDING_PROVIDER=onnx`) for
  meaningfully better semantic retrieval.

## "Could not extract text from PDF (corrupted or encrypted?)"

SnapMemory tries `pdfplumber` first, then falls back to `pypdf`. If both fail, the PDF is
likely password-protected, a scanned image with no text layer (needs OCR, not currently wired
into the PDF path), or genuinely corrupted. Password-protected PDFs must be decrypted before
import.

## Server won't start / port already in use

Another process is using port 5057. Either stop it, or edit the port in `run.py`.

## Database looks empty after restart

Check `SNAPMEMORY_DATA_DIR` (default `./data`) — if you're running the app from a different
working directory each time, or changed this env var, you'll be pointed at a different
(empty) database file. Set it explicitly in `.env` for a stable location.

## I changed `requirements.txt` / added a package and nothing happens

Restart the Flask process — provider detection (`ai/providers.py`, `ai/embeddings.py`,
`ai/vision.py`, `ai/transcription.py`) runs once at import time, not per-request.
