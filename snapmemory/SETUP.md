# SETUP.md — Local Development Setup

## Prerequisites

- Python 3.10+
- `tesseract-ocr` binary on PATH (for image OCR). Install:
  - macOS: `brew install tesseract`
  - Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
  - Windows: install from https://github.com/UB-Mannheim/tesseract/wiki and add to PATH

## Install

```bash
cd snapmemory
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

This installs only the core dependencies (Flask, numpy, scikit-learn, pdfplumber, pypdf,
python-pptx, pillow, pytesseract, onnxruntime). No model weights are downloaded — the app runs
entirely in local-fallback mode out of the box.

## Configure (optional)

```bash
cp .env.example .env
```

Defaults work with no changes. See `.env.example` for retrieval tuning and optional Qualcomm
AI Hub model paths.

## Initialize and run

```bash
python run.py
```

This creates `data/snapmemory.db` and `data/files/` on first run, then starts the server at
**http://127.0.0.1:5057**.

## Try it immediately

Click **"Load Demo Data"** in the top bar — this seeds a small synthetic dataset (documents, a
slide deck, a screenshot, and a meeting transcript) through the real ingestion pipeline so you
can try Ask/citations/meeting intelligence/privacy/benchmark without providing your own files.

## Run tests

```bash
python -m unittest discover -s tests -v
```

24 tests covering chunking, validation, database schema, deduplication, retrieval/citation
mapping, and meeting-intelligence grounding (no-hallucination checks).

## Enable real audio transcription (optional, CPU/dev)

```bash
pip install faster-whisper
```

No other configuration needed — `ai/transcription.py` will detect and use it automatically on
the next meeting upload.

## Enable Qualcomm AI Hub acceleration

See `SNAPDRAGON_SETUP.md`.
